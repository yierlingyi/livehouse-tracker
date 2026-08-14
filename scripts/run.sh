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
#   * 按顺序应用迁移 V1__schema.sql → V2__permissions.sql → V3__platform.sql → V4__cities.sql
#     - V1 仅建库时运行一次（其 CREATE TABLE 非幂等，已存在则跳过）；
#     - V2 / V3 / V4 为幂等设计（IF NOT EXISTS / DO 块 / ON CONFLICT），可重复执行。
#
#   * 默认前台运行（exec uvicorn，Ctrl+C 停止）；
#     设置 DAEMON=1 则 nohup 后台常驻（日志 + PID 文件），例如：
#       DAEMON=1 bash scripts/run.sh
#     或一路从 start.sh 透传：DAEMON=1 bash scripts/start.sh
#     （LOG_FILE / PID_FILE 可用环境变量覆盖，默认 <仓库根>/bandlive.log / bandlive.pid）
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

echo ">> 应用迁移 V4__cities.sql"
psql "$DATABASE_URL_PRIMARY" -v ON_ERROR_STOP=1 -f database/migrations/V4__cities.sql

# ---- 4) 启动 API ----
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
LOG_FILE="${LOG_FILE:-$ROOT_DIR/bandlive.log}"
PID_FILE="${PID_FILE:-$ROOT_DIR/bandlive.pid}"
DAEMON="${DAEMON:-0}"

if [ "$DAEMON" = "1" ]; then
  echo ">> 后台启动 uvicorn（nohup，DAEMON=1）..."
  echo "   日志: $LOG_FILE    PID 文件: $PID_FILE"
  nohup uvicorn backend.main:app --host "$HOST" --port "$PORT" >>"$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  sleep 1
  echo ">> 已后台启动 PID=$(cat "$PID_FILE")"
  echo "   查看日志: tail -f $LOG_FILE"
  echo "   停止进程: kill $(cat "$PID_FILE")（或按 PID 列表 pkill -f uvicorn）"
else
  echo ">> 前台启动 uvicorn: uvicorn backend.main:app --host $HOST --port $PORT"
  echo "   （如需后台常驻：DAEMON=1 bash scripts/start.sh）"
  exec uvicorn backend.main:app --host "$HOST" --port "$PORT"
fi
