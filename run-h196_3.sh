#!/usr/bin/env bash
# ==========================================================================
# h196_3 环境 前后端启停脚本（Linux）
#   后端: systemd unit `lnrs-backend` (ExecStart=/usr/local/bin/uv run main.py
#         run --env=h196_3),日志 ${BACKEND_DIR}/.run/h196_3.log
#   前端: 脚本自管, pnpm dev --host --no-open,日志 /tmp/lnrs_frontend_h196_3.log
#
# 用法:
#   ./run-h196_3.sh start     启动后端(systemd) + 前端(nohup) + 双侧 HTTP 探活
#   ./run-h196_3.sh stop      停后端(systemctl stop) + 杀前端端口
#   ./run-h196_3.sh restart   stop + sleep 1 + start
#   ./run-h196_3.sh status    后端 service 状态 + 前端端口/PID
#   ./run-h196_3.sh logs      tail -F 跟踪后端与前端日志 (Ctrl-C 退出)
#
# 依赖: sudo(管理 systemd)、pnpm(前端)、ss(端口查询)、curl(探活)
# 首次上线: chmod +x run-h196_3.sh
# ==========================================================================
set -euo pipefail

# ---- 路径配置 --------------------------------------------------------------
REPO_ROOT="/home/dzy/wk/lnrs"
BACKEND_DIR="$REPO_ROOT/backend"
FRONTEND_DIR="$REPO_ROOT/frontend/web"

BACKEND_SERVICE="lnrs-backend"
ENV_NAME="h196_3"

BACKEND_PORT=8610
FRONTEND_PORT=5610

BACKEND_LOG="$BACKEND_DIR/.run/${ENV_NAME}.log"
FRONTEND_LOG="/tmp/lnrs_frontend_${ENV_NAME}.log"

BACKEND_HEALTH_URL="http://127.0.0.1:${BACKEND_PORT}/api/v1/docs"
FRONTEND_HEALTH_URL="http://127.0.0.1:${FRONTEND_PORT}/web"
# --------------------------------------------------------------------------

# 端口 -> 监听 PID（可能为空）
port_pid() { ss -ltnp 2>/dev/null | grep ":$1 " | grep -oP 'pid=\K[0-9]+' | head -1; }

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# ---- 后端（systemd） -------------------------------------------------------
start_backend() {
  if systemctl is-active --quiet "${BACKEND_SERVICE}"; then
    log "[backend]  systemd: ${BACKEND_SERVICE} 已运行, 跳过 (log: ${BACKEND_LOG})"
    return
  fi
  log "[backend]  启动 ${BACKEND_SERVICE} (log: ${BACKEND_LOG})"
  if ! sudo systemctl restart "${BACKEND_SERVICE}"; then
    log "[backend]  ERROR: systemctl restart ${BACKEND_SERVICE} 失败"
    return 1
  fi
}

stop_backend() {
  if ! systemctl is-active --quiet "${BACKEND_SERVICE}"; then
    log "[backend]  systemd: ${BACKEND_SERVICE} 未运行, 跳过"
    return
  fi
  log "[backend]  停止 ${BACKEND_SERVICE}"
  sudo systemctl stop "${BACKEND_SERVICE}"
}

status_backend() {
  if systemctl is-active --quiet "${BACKEND_SERVICE}"; then
    log "[backend]  systemd: ${BACKEND_SERVICE} active (running)"
  else
    log "[backend]  systemd: ${BACKEND_SERVICE} inactive"
  fi
  if [ -n "$(port_pid "$BACKEND_PORT")" ]; then
    log "[backend]  port  : ${BACKEND_PORT} 监听中"
  else
    log "[backend]  port  : ${BACKEND_PORT} 未监听"
  fi
}

# ---- 前端（脚本自管） -------------------------------------------------------
start_frontend() {
  local pid
  pid=$(port_pid "$FRONTEND_PORT")
  if [ -n "$pid" ]; then
    log "[frontend] 端口 ${FRONTEND_PORT} 已被占用, 跳过 (pid=${pid}, log: ${FRONTEND_LOG})"
    return
  fi
  log "[frontend] 启动中... (cd ${FRONTEND_DIR} && pnpm dev --host --no-open)"
  ( cd "$FRONTEND_DIR" \
    && nohup pnpm dev --host --no-open > "$FRONTEND_LOG" 2>&1 & )
}

kill_port() {  # $1=port  $2=name
  local pid
  pid=$(port_pid "$1")
  if [ -z "$pid" ]; then
    log "[$2] 未在运行 (port $1)"
    return
  fi
  log "[$2] 停止 pid=${pid} (port $1)"
  kill "$pid" 2>/dev/null || true
  sleep 2
  pid=$(port_pid "$1")
  if [ -n "$pid" ]; then
    log "[$2] 强制结束 pid=${pid}"
    kill -9 "$pid" 2>/dev/null || true
  fi
}

stop_frontend() {
  kill_port "$FRONTEND_PORT" frontend
}

status_frontend() {
  local pid
  pid=$(port_pid "$FRONTEND_PORT")
  if [ -n "$pid" ]; then
    log "[frontend] 运行中 pid=${pid}  port=${FRONTEND_PORT}"
  else
    log "[frontend] 未运行  port=${FRONTEND_PORT}"
  fi
}

# ---- 探活 ------------------------------------------------------------------
# $1=url  $2=名称  $3=重试次数(默认 60)
wait_http() {
  local url="$1" name="$2" retries="${3:-60}" code
  for _ in $(seq 1 "$retries"); do
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 2 "$url" || true)
    if [ "$code" = "200" ]; then
      log "[${name}] 就绪 ${url} -> 200"
      return 0
    fi
    sleep 1
  done
  log "[${name}] 未在 ${retries}s 内就绪 (${url}), 请查看日志"
  return 1
}

# ---- 动作 ------------------------------------------------------------------
do_start() {
  start_backend
  start_frontend
  log "等待服务就绪..."
  wait_http "$BACKEND_HEALTH_URL"  backend  60 || true
  wait_http "$FRONTEND_HEALTH_URL" frontend 30 || true
  echo "----------------------------------------------------"
  echo "  前端:     http://localhost:${FRONTEND_PORT}/web"
  echo "  后端文档: ${BACKEND_HEALTH_URL}"
  echo "  后端日志: ${BACKEND_LOG}"
  echo "  前端日志: ${FRONTEND_LOG}"
  echo "----------------------------------------------------"
}

do_stop() {
  stop_frontend
  stop_backend
}

do_status() {
  status_backend
  status_frontend
}

do_logs() {
  local files=()
  [ -f "$BACKEND_LOG" ]  && files+=("$BACKEND_LOG")
  [ -f "$FRONTEND_LOG" ] && files+=("$FRONTEND_LOG")
  if [ ${#files[@]} -eq 0 ]; then
    log "无日志文件: ${BACKEND_LOG} / ${FRONTEND_LOG}"
    return 1
  fi
  exec tail -F "${files[@]}"
}

do_restart() {
  do_stop
  sleep 1
  do_start
}

# ---- main ------------------------------------------------------------------
case "${1:-start}" in
  start)   do_start ;;
  stop)    do_stop ;;
  restart) do_restart ;;
  status)  do_status ;;
  logs)    do_logs ;;
  *) echo "用法: $0 {start|stop|restart|status|logs}"; exit 1 ;;
esac