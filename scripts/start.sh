#!/usr/bin/env bash
# ============================================================
# Band Live API — 一键启动脚本（Linux 服务器部署）
#
# 用法（仓库根目录执行）：
#   1. 首次准备：cp .env.example .env 并填写 DATABASE_URL_PRIMARY / TOKEN_SECRET
#   2. 一键启动：bash scripts/start.sh
#   可选 dry-run（只打印将执行的命令，不真正建库/启动）：
#       DRY_RUN=1 bash scripts/start.sh
#
# 与 scripts/run.sh 的关系：
#   start.sh 负责「建库检测 + 建库」，随后委托 run.sh 完成「迁移 + uvicorn 启动」。
#   即完整四步：①检测数据库 → ②创建数据库（如缺失）→ ③应用迁移 → ④启动 API。
#   run.sh 保持原样不动，start.sh 只是在其前面补上建库环节。
#
# 前提（重要）：
#   * DATABASE_URL_PRIMARY 的连接账号必须是 PostgreSQL 超级用户。
#     V1/V2/V3 迁移含 CREATE ROLE / REVOKE ALL ON DATABASE app_db /
#     ALTER FUNCTION ... OWNER TO app_definer，均需超级用户或数据库 owner 权限。
#   * DATABASE_URL_PRIMARY 的库名必须为 app_db（迁移 V1/V2 硬编码该名称）。
#
# 幂等性：
#   * 数据库已存在 → 跳过建库；不存在 → CREATE DATABASE app_db。
#   * run.sh 内 V1 检测到 public.lives 已存在则跳过；V2/V3 为幂等设计，可重复执行。
# ============================================================
set -euo pipefail

# 仓库根目录（脚本位于 scripts/ 下，向上取一级）
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# ---- 1) 加载 .env（如存在）----
if [ -f .env ]; then
  echo ">> 加载 .env"
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
else
  echo ">> 未找到 .env，使用已导出的环境变量"
fi

# ---- 2) 必填变量校验 ----
: "${DATABASE_URL_PRIMARY:?DATABASE_URL_PRIMARY 未设置，请先 cp .env.example .env 并填写}"
: "${TOKEN_SECRET:?TOKEN_SECRET 未设置，请先 cp .env.example .env 并填写}"

# 可选 dry-run：仅打印将执行的命令，不真正执行
DRY_RUN="${DRY_RUN:-0}"

# 目标库名（迁移 V1/V2 硬编码了 app_db，不允许改为其他值）
DB_NAME="app_db"

# ---- 3) 校验库名并推导「服务器级连接串」 ----
# DATABASE_URL_PRIMARY 指向 app_db，但 CREATE DATABASE 不能在目标库内执行，
# 必须先连到维护库 postgres。这里把连接串路径里的库名替换为 postgres。
dsn="${DATABASE_URL_PRIMARY}"
dsn_base="${dsn%%\?*}"                 # 去掉查询参数（?key=value）
query="${dsn#"$dsn_base"}"             # 以 "?" 开头，或为空字符串

# 取 scheme 之后的部分；路径（第一个 / 之后）即库名
rest="${dsn_base#*://}"
if [[ "$rest" != */* ]]; then
  echo ">> 错误：DATABASE_URL_PRIMARY 缺少库名，应为 postgresql://user:pass@host:5432/app_db" >&2
  exit 1
fi
url_db_name="${rest#*/}"

if [ -z "$url_db_name" ]; then
  echo ">> 错误：DATABASE_URL_PRIMARY 缺少库名，应为 postgresql://user:pass@host:5432/app_db" >&2
  exit 1
fi
if [ "$url_db_name" != "$DB_NAME" ]; then
  echo ">> 错误：DATABASE_URL_PRIMARY 的库名必须是 ${DB_NAME}（迁移 V1/V2 硬编码该名称），当前为: ${url_db_name}" >&2
  exit 1
fi

# 服务器级连接串：库名替换为维护库 postgres，保留查询参数（如 sslmode）
server_dsn="${dsn_base%/*}/postgres${query}"

# ---- 4) 步骤①检测 / 步骤②创建数据库 ----
if [ "$DRY_RUN" = "1" ]; then
  echo ">> [DRY-RUN] 步骤① 检测数据库是否已存在，将执行："
  echo "    psql \"${server_dsn}\" -tAc \"SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}'\""
  echo ">> [DRY-RUN] 步骤② 若检测到库不存在，将执行："
  echo "    psql \"${server_dsn}\" -v ON_ERROR_STOP=1 -c \"CREATE DATABASE ${DB_NAME}\""
  echo ">> [DRY-RUN] 步骤③④ 将委托执行：bash scripts/run.sh（迁移 V1/V2/V3 + uvicorn 启动）"
  echo ">> [DRY-RUN] 注意：以上命令含数据库口令，请勿在公开场合泄露。"
  exit 0
fi

# 非 dry-run 才需要 psql 客户端
if ! command -v psql >/dev/null 2>&1; then
  echo ">> 错误：未找到 psql，请先安装 PostgreSQL 客户端（Debian/Ubuntu: apt-get install postgresql-client）" >&2
  exit 1
fi

echo ">> [1/4] 检测数据库 ${DB_NAME} ..."
exists="$(psql "$server_dsn" -tAc "SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}'" 2>&1)" || {
  echo ">> 错误：无法连接 PostgreSQL 维护库 postgres（服务器未启动？账号非超级用户？）" >&2
  echo "   psql 输出: ${exists}" >&2
  exit 1
}

exists="$(printf '%s' "$exists" | tr -d '[:space:]')"
if [ "$exists" = "1" ]; then
  echo "   数据库 ${DB_NAME} 已存在，跳过建库"
else
  echo ">> [2/4] 创建数据库 ${DB_NAME}（连接维护库 postgres）..."
  if psql "$server_dsn" -v ON_ERROR_STOP=1 -c "CREATE DATABASE ${DB_NAME}"; then
    echo "   数据库 ${DB_NAME} 创建成功"
  else
    # 并发首启时其他进程可能已建好，再检测一次
    if [ "$(psql "$server_dsn" -tAc "SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}'" 2>/dev/null | tr -d '[:space:]')" = "1" ]; then
      echo "   数据库 ${DB_NAME} 已由其他进程创建，继续"
    else
      echo ">> 错误：CREATE DATABASE ${DB_NAME} 失败" >&2
      exit 1
    fi
  fi
fi

# ---- 5) 步骤③应用迁移 / 步骤④启动 API（复用 run.sh）----
echo ">> [3/4] 应用迁移 V1/V2/V3（V1 检测 public.lives 已存在则跳过；V2/V3 幂等）"
echo ">> [4/4] 启动 API（uvicorn backend.main:app）"
echo ">> 委托 scripts/run.sh 执行上述两步 ..."
exec bash scripts/run.sh
