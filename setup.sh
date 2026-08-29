#!/usr/bin/env bash
# 一次性安装/构建脚本（与 start.sh 分离）
set -e
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"

echo "==> [1/3] 安装后端依赖（版本已锁定）"
$PYTHON -m pip install -q -r backend/requirements.txt

echo "==> [2/3] 安装前端依赖（npm ci 按锁文件安装）"
(cd frontend && npm ci --no-fund --no-audit)

echo "==> [3/3] 构建前端"
(cd frontend && npm run build)

echo "完成。运行 bash start.sh 启动（默认 http://127.0.0.1:8765）"
