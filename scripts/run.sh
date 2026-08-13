#!/usr/bin/env bash
# ============================================================
# Band Live API — Linux 部署 / 启动脚本
#
# 用法（仓库根目录执行）：
#   1. 首次准备：cp .env.example .env 并填写 DATABASE_URL_PRIMARY / TOKEN_SECRET
#   2. 安装依赖：python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
#   3. 启动：    bash scripts/run.sh
#
# 脚本行为：
#   * 自动加载根目录 .env（若存在）
#   * 校验必填变量 DATABASE_URL_PRIMARY / TOKEN_SECRET
#   * 按顺序应用迁移 V1__schema.sql → V2__permissions.sql → V3__platform.sql
#     - V1 仅建库时运行一次（其 CREATE TABLE 非幂等，已存在则跳过）；
#     - V2 / V3 为幂等设计（IF NOT EXISTS / DO 块），可重复执行。
#   * 用 uvicorn 启动 API：backend.main:app --host 0.0.0.0 --port 8000
#     （HOST / PORT 可用环境变量覆盖）
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
  echo ">> 未找到 .env，跳过（将使用已导出的环境变量）"
fi

# ---- 2) 必填变量校验 ----
: "${DATABASE_URL_PRIMARY:?DATABASE_URL_PRIMARY 未设置，请先 cp .env.example .env 并填写}"
: "${TOKEN_SECRET:?TOKEN_SECRET 未设置，请先 cp .env.example .env 并填写}"

# ---- 3) 按顺序应用数据库迁移 ----
echo ">> 应用迁移 V1__schema.sql（仅首次初始化执行）"
if psql "$DATABASE_URL_PRIMARY" -tAc "SELECT to_regclass('public.lives')" 2>/dev/null | grep -q "lives"; then
  echo "   lives 表已存在，跳过 V1（V1 非幂等，只建库时运行一次）"
else
  psql "$DATABASE_URL_PRIMARY" -v ON_ERROR_STOP=1 -f database/migrations/V1__schema.sql
fi

echo ">> 应用迁移 V2__permissions.sql"
psql "$DATABASE_URL_PRIMARY" -v ON_ERROR_STOP=1 -f database/migrations/V2__permissions.sql

echo ">> 应用迁移 V3__platform.sql"
psql "$DATABASE_URL_PRIMARY" -v ON_ERROR_STOP=1 -f database/migrations/V3__platform.sql

# ---- 4) 启动 API ----
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
echo ">> 启动 uvicorn: uvicorn backend.main:app --host $HOST --port $PORT"
exec uvicorn backend.main:app --host "$HOST" --port "$PORT"
