#!/usr/bin/env bash
# ==========================================================================
# 本机专属启动脚本（CentOS 7 / el7, glibc 2.17）
#   后端: conda 环境 py311 + main.py run --env=h42  (监听 127.0.0.1:8610)
#   前端: conda 环境 node22 (node 22.6.0 + pnpm 9.15.3) + vite dev (127.0.0.1:5610)
#
# 用法:
#   ./run-h42.sh start     启动前后端
#   ./run-h42.sh stop      停止前后端
#   ./run-h42.sh restart   重启
#   ./run-h42.sh status    查看端口/进程状态
#   ./run-h42.sh logs      跟踪查看日志 (Ctrl-C 退出)
# ==========================================================================
set -euo pipefail

# ---- 路径配置（本机专属，按需修改）----------------------------------------
REPO_ROOT="/home/dzy/wk/lnrs"
BACKEND_DIR="$REPO_ROOT/backend"
FRONTEND_DIR="$REPO_ROOT/frontend/web"

PY_BIN="$HOME/.conda/envs/py311/bin/python"      # 后端解释器（含 duckdb 等）
NODE_ENV_DIR="$HOME/miniconda3/envs/node22"       # 前端 node 22 环境
ENV_NAME="h42"                                    # 后端环境标识 (.env.h42)

BACKEND_LOG="/tmp/lnrs_backend.log"
FRONTEND_LOG="/tmp/lnrs_frontend.log"
BACKEND_PORT=8610
FRONTEND_PORT=5610
# --------------------------------------------------------------------------

port_pid() { ss -ltnp 2>/dev/null | grep ":$1 " | grep -oP 'pid=\K[0-9]+' | head -1; }

start_backend() {
  if [ -n "$(port_pid "$BACKEND_PORT")" ]; then
    echo "[backend] 端口 $BACKEND_PORT 已被占用，跳过启动"
    return
  fi
  echo "[backend] 启动中... (log: $BACKEND_LOG)"
  ( cd "$BACKEND_DIR" && nohup "$PY_BIN" main.py run --env="$ENV_NAME" > "$BACKEND_LOG" 2>&1 & )
}

start_frontend() {
  if [ -n "$(port_pid "$FRONTEND_PORT")" ]; then
    echo "[frontend] 端口 $FRONTEND_PORT 已被占用，跳过启动"
    return
  fi
  echo "[frontend] 启动中... (log: $FRONTEND_LOG)"
  ( cd "$FRONTEND_DIR" \
    && export PATH="$NODE_ENV_DIR/bin:$PATH" \
    && export LD_LIBRARY_PATH="$NODE_ENV_DIR/lib" \
    && nohup pnpm dev --host --no-open > "$FRONTEND_LOG" 2>&1 & )
}

wait_http() {  # $1=url  $2=名称
  for _ in $(seq 1 30); do
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 2 "$1" || true)
    [ "$code" = "200" ] && { echo "[$2] 就绪 ($1 -> 200)"; return 0; }
    sleep 1
  done
  echo "[$2] 未在超时内就绪，请查看日志"
  return 1
}

do_start() {
  start_backend
  start_frontend
  echo "等待服务就绪..."
  wait_http "http://127.0.0.1:$BACKEND_PORT/api/v1/docs"  backend  || true
  wait_http "http://127.0.0.1:$FRONTEND_PORT/web"          frontend || true
  echo "----------------------------------------------------"
  echo "  前端:     http://localhost:$FRONTEND_PORT/web"
  echo "  后端文档: http://127.0.0.1:$BACKEND_PORT/api/v1/docs"
  echo "----------------------------------------------------"
}

kill_port() {  # $1=port  $2=名称
  local pid; pid=$(port_pid "$1")
  if [ -n "$pid" ]; then
    echo "[$2] 停止 pid=$pid (port $1)"
    kill "$pid" 2>/dev/null || true
    sleep 2
    pid=$(port_pid "$1")
    [ -n "$pid" ] && { echo "[$2] 强制结束 pid=$pid"; kill -9 "$pid" 2>/dev/null || true; }
  else
    echo "[$2] 未在运行 (port $1)"
  fi
}

do_stop() {
  kill_port "$FRONTEND_PORT" frontend
  kill_port "$BACKEND_PORT"  backend
}

do_status() {
  for p in "$BACKEND_PORT:backend" "$FRONTEND_PORT:frontend"; do
    port="${p%%:*}"; name="${p##*:}"; pid=$(port_pid "$port")
    if [ -n "$pid" ]; then echo "[$name] 运行中 pid=$pid  port=$port"
    else echo "[$name] 未运行  port=$port"; fi
  done
}

case "${1:-start}" in
  start)   do_start ;;
  stop)    do_stop ;;
  restart) do_stop; sleep 1; do_start ;;
  status)  do_status ;;
  logs)    tail -f "$BACKEND_LOG" "$FRONTEND_LOG" ;;
  *) echo "用法: $0 {start|stop|restart|status|logs}"; exit 1 ;;
esac
