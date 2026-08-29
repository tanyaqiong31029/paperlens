#!/usr/bin/env bash
# PaperLens 一键启动脚本（安装请用 setup.sh）
# 用法:
#   bash start.sh                # 默认 127.0.0.1:8765 —— 仅本机可访问
#   bash start.sh 9000           # 自定义端口
#   HOST=0.0.0.0 PAPERLENS_ADMIN_TOKEN=xxx bash start.sh 8765 0.0.0.0
#                                # 局域网开放：必须显式指定地址 + 管理员令牌
set -e
cd "$(dirname "$0")"

PORT="${1:-8765}"
HOST="${2:-127.0.0.1}"
PYTHON="${PYTHON:-python3}"

# 非回环地址 = 向局域网/外网开放：强制要求管理员令牌
case "$HOST" in
  127.0.0.1|localhost|::1)
    ;;
  *)
    if [ -z "$PAPERLENS_ADMIN_TOKEN" ]; then
      echo "错误：绑定非回环地址（$HOST）会向局域网开放服务，必须先设置管理员令牌：" >&2
      echo "  export PAPERLENS_ADMIN_TOKEN=\$(openssl rand -hex 16)" >&2
      echo "然后重新运行：HOST=$HOST bash start.sh $PORT $HOST" >&2
      exit 1
    fi
    ;;
esac

if [ ! -f frontend/dist/index.html ]; then
  echo "==> 前端尚未构建，请先运行: bash setup.sh" >&2
  exit 1
fi

echo "==> 启动: http://$HOST:$PORT  (数据目录: backend/data)"
cd backend && exec $PYTHON -m uvicorn app.main:app --host "$HOST" --port "$PORT"
