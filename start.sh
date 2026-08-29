#!/usr/bin/env bash
# PaperLens 一键启动脚本
# 用法: bash start.sh   （默认端口 8765）
set -e
cd "$(dirname "$0")"

PORT="${1:-8765}"
PYTHON="${PYTHON:-python3}"

echo "==> [1/3] 检查后端依赖"
$PYTHON -m pip install -q -r backend/requirements.txt

echo "==> [2/3] 构建前端（若 dist 不存在）"
if [ ! -f frontend/dist/index.html ]; then
  (cd frontend && npm install && npm run build)
fi

echo "==> [3/3] 启动服务: http://localhost:$PORT"
cd backend && exec $PYTHON -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
