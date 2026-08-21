#!/usr/bin/env bash
# ==========================================================================
# 本机部署脚本 — lnrs (systemd 后端 + 可选前端构建, 含 SOCKS5 代理支持)
#   目标环境:  h196_3   (systemd 单元: lnrs-backend.service)
#   后端监听:  127.0.0.1:8610
#   后端日志:  backend/.run/h196_3.log
#   前端产物:  frontend/web/dist  (FastAPI 直接挂载, 不走 nginx)
#   外网通道:  SOCKS5 127.0.0.1:1080 (需先 net-on; uv/pnpm 均接受 socks5h://)
#
# 与 deploy-ci.sh / run-h42.sh 的区别:
#   - deploy-ci.sh 由 GitLab CI 调用 (强制拉取 origin/main, 需要 GITLAB_FETCH_TOKEN)
#   - run-h42.sh    是 conda + nohup 启动 (h42 环境, 不走 systemd)
#   - 本脚本        本地手工部署: 可选 pull/分支/commit, 走 systemd, 无 token 门槛
#
# 用法:
#   ./deploy-h196_3.sh status                          查看 service / 端口 / 日志
#   ./deploy-h196_3.sh restart                         仅重启后端 (代码不变)
#   ./deploy-h196_3.sh deploy                          pull main + 后端同步 + restart
#   ./deploy-h196_3.sh deploy --frontend               同时重建前端 dist
#   ./deploy-h196_3.sh deploy --frontend --force       强制重建前端 (忽略新鲜度判断)
#   ./deploy-h196_3.sh deploy --no-proxy               关闭代理环境变量 (内网/离线场景)
#   ./deploy-h196_3.sh deploy --no-net-on              不自动调 net-on (代理已自启)
#   ./deploy-h196_3.sh deploy --branch=feature/x
#   ./deploy-h196_3.sh deploy --commit=<sha>
#   ./deploy-h196_3.sh rollback <sha>                  回滚后端代码
#   ./deploy-h196_3.sh build-frontend [--force]        仅构建前端 (不动代码/不重启)
#   ./deploy-h196_3.sh logs [-n 200]                   tail 后端日志
#   ./deploy-h196_3.sh doctor                          环境自检
# ==========================================================================
set -euo pipefail

# ---- 路径配置 (本机专属, 按需修改) ---------------------------------------
REPO_ROOT="/home/dzy/wk/lnrs"
BACKEND_DIR="${REPO_ROOT}/backend"
FRONTEND_DIR="${REPO_ROOT}/frontend/web"
FRONTEND_DIST="${FRONTEND_DIR}/dist"

ENV_NAME="h196_3"                                       # .env.h196_3
SERVICE_NAME="lnrs-backend"                             # /etc/systemd/system/<SERVICE_NAME>.service
BACKEND_PORT="${BACKEND_PORT:-8610}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:${BACKEND_PORT}/api/v1/docs}"
BACKEND_LOG="${BACKEND_DIR}/.run/${ENV_NAME}.log"
DIAG="/tmp/deploy-${ENV_NAME}.diag"

BRANCH="main"                                           # 默认部署分支
DO_FRONTEND=0                                           # --frontend 显式打开
FRONTEND_FORCE=0                                        # --force 强制重建前端
WAIT_PORT_SEC=60
WAIT_HTTP_SEC=90

# ---- 网络代理 -------------------------------------------------------------
# 本机默认不通外网, uv/pnpm 拉依赖需走 SOCKS5 隧道. socks5h = SOCKS5 + 远端解析 DNS.
PROXY_URL="socks5h://127.0.0.1:1080"
PROXY_HOST_PORT="127.0.0.1:1080"
PROXY_PROBE_HOST="ifconfig.io"
PROBE_TIMEOUT=5
NO_PROXY=0                                              # --no-proxy 显式关闭
NO_NET_ON=0                                              # --no-net-on 跳过自动启通道
# --------------------------------------------------------------------------

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
die() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >&2; exit 1; }

port_pid() {
  local out
  out=$(ss -ltnp 2>/dev/null \
          | awk -v p=":$1 " '$4 ~ p {print $0}' \
          | grep -oP 'pid=\K[0-9]+' | head -1) || true
  printf '%s' "${out:-}"
}

need_root() { sudo -n true 2>/dev/null || die "本脚本需要免密 sudo (systemctl)"; }

# ---- 网络代理辅助 ---------------------------------------------------------
ensure_net() {
  if [ "${NO_NET_ON}" = "1" ]; then
    log "    --no-net-on: 跳过自动启 SOCKS5 通道"
    return 0
  fi
  if declare -F net-on >/dev/null 2>&1; then
    log ">>> net-on: 启动/续期 SOCKS5 通道 (30 分钟计时)"
    net-on || die "net-on 失败, 无法继续"
  else
    log ">>> 未检测到 net-on 函数, 假定 SOCKS5 已就绪 (${PROXY_URL})"
  fi
}

proxy_probe() {
  local out
  out=$(curl --socks5-hostname "${PROXY_HOST_PORT}" -sS --max-time "${PROBE_TIMEOUT}" \
          "https://${PROXY_PROBE_HOST}" 2>/dev/null) || return 1
  [ -n "${out}" ] && return 0 || return 1
}

apply_proxy() {
  # 在子 shell 入口 export 代理变量, 让 uv/pnpm 自动走 SOCKS5
  if [ "${NO_PROXY}" = "1" ]; then
    log "    --no-proxy: 跳过代理环境变量"
    return 0
  fi
  if ! proxy_probe; then
    die "代理 ${PROXY_URL} 不通 (curl socks5h 取 ${PROXY_PROBE_HOST} 失败), 用 --no-proxy 跳过或先 net-on"
  fi
  export HTTPS_PROXY="${PROXY_URL}"
  export HTTP_PROXY="${PROXY_URL}"
  export ALL_PROXY="${PROXY_URL}"
  # 内网直连 (PG / Redis / 后端自身)
  export NO_PROXY="127.0.0.1,localhost,10.0.0.0/8,192.168.0.0/16,*.local,postgres,redis"
  log "    代理已生效: HTTPS_PROXY=${PROXY_URL}"
}

# ---- 前置检查 --------------------------------------------------------------
doctor() {
  log ">>> doctor: 自检环境"
  command -v git       >/dev/null || die "git 未安装"
  command -v uv        >/dev/null || die "uv 未安装 (systemd ExecStart 依赖 /usr/local/bin/uv)"
  command -v curl      >/dev/null || die "curl 未安装"
  command -v ss        >/dev/null || die "ss 未安装"
  command -v systemctl >/dev/null || die "systemctl 不可用"
  [ -d "${BACKEND_DIR}" ]                || die "后端目录不存在: ${BACKEND_DIR}"
  [ -f "${BACKEND_DIR}/pyproject.toml" ] || die "后端 pyproject.toml 不存在"
  systemctl cat "${SERVICE_NAME}" >/dev/null 2>&1 \
    || die "systemd 单元不存在: ${SERVICE_NAME} (检查 /etc/systemd/system/${SERVICE_NAME}.service)"
  if [ "${DO_FRONTEND}" = "1" ]; then
    command -v node >/dev/null || die "前端构建需要 node"
    command -v pnpm  >/dev/null || die "前端构建需要 pnpm (systemd 单元 PATH 已含 /opt/node24/bin)"
    [ -f "${FRONTEND_DIR}/package.json" ] || die "前端 package.json 不存在: ${FRONTEND_DIR}"
  fi
  log "    OK"
}

# ---- service 状态 (status 子命令专用) ------------------------------------
svc_status() {
  local pid
  pid=$(port_pid "$BACKEND_PORT")
  echo "----- systemd: ${SERVICE_NAME} -----"
  systemctl status "${SERVICE_NAME}" --no-pager 2>&1 | sed -n '1,12p' || true
  echo "----- 端口: ${BACKEND_PORT} -----"
  if [ -n "$pid" ]; then echo "[backend] 运行中 pid=${pid}  port=${BACKEND_PORT}"
  else                  echo "[backend] 未监听 port=${BACKEND_PORT}"; fi
  echo "----- 日志尾部 -----"
  if [ -f "${BACKEND_LOG}" ]; then tail -20 "${BACKEND_LOG}"
  else echo "(日志文件不存在: ${BACKEND_LOG})"; fi
}

# ---- service 重启 --------------------------------------------------------
svc_restart() {
  need_root
  log ">>> systemctl restart ${SERVICE_NAME}"
  sudo systemctl restart "${SERVICE_NAME}"
  wait_port
  wait_http || {
    log ">>> 探活失败, 收集诊断信息" >&2
    sudo systemctl status "${SERVICE_NAME}" --no-pager 2>&1 | tail -30 >&2 || true
    tail -50 "${BACKEND_LOG}" >&2 || true
    return 1
  }
  log ">>> 重启完成"
}

# ---- 等待端口 / HTTP -----------------------------------------------------
wait_port() {
  for _ in $(seq 1 "${WAIT_PORT_SEC}"); do
    if ss -tln 2>/dev/null | grep -q ":${BACKEND_PORT}\b"; then
      log "    端口 ${BACKEND_PORT} 已监听"
      return 0
    fi
    sleep 1
  done
  die "端口 ${BACKEND_PORT} 在 ${WAIT_PORT_SEC}s 内未监听"
}

wait_http() {
  log ">>> 探活: ${HEALTH_URL} (最多 ${WAIT_HTTP_SEC}s)"
  for _ in $(seq 1 "${WAIT_HTTP_SEC}"); do
    local code
    code=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 5 "${HEALTH_URL}" 2>/dev/null || echo "000")
    if [ "$code" = "200" ]; then
      log ">>> 就绪: HTTP 200"
      return 0
    fi
    sleep 1
  done
  return 1
}

# ---- 前端构建 ------------------------------------------------------------
# FastAPI 在启动时扫描 frontend/web/dist (见 init_app.py:register_files)
# 因此: 构建完成必须重启后端才能生效.
frontend_dist_fresh() {
  [ -f "${FRONTEND_DIST}/index.html" ] || return 1
  local newer_src
  newer_src=$(find "${FRONTEND_DIR}/src" -type f \( -name '*.vue' -o -name '*.ts' -o -name '*.tsx' -o -name '*.js' \) \
                -newer "${FRONTEND_DIST}/index.html" -print -quit 2>/dev/null || true)
  [ -z "${newer_src}" ] && return 0 || return 1
}

build_frontend() {
  ensure_net
  apply_proxy
  log ">>> pnpm install (${FRONTEND_DIR})"
  (
    cd "${FRONTEND_DIR}"
    # 锁文件兼容: frozen-lockfile 失败时回退普通 install (与 deploy-ci.sh 一致)
    pnpm install --frozen-lockfile 2>/dev/null || pnpm install
  )

  if frontend_dist_fresh && [ "${FRONTEND_FORCE}" != "1" ]; then
    log ">>> dist/index.html 比 src 新, 跳过 vite build (用 --frontend --force 强制重建)"
    return 0
  fi

  log ">>> pnpm vite build (${FRONTEND_DIR})"
  (
    cd "${FRONTEND_DIR}"
    pnpm vite build
  )
  log ">>> 前端构建完成: ${FRONTEND_DIST}/index.html"
}

# ---- 后端依赖同步 -------------------------------------------------------
sync_backend_deps() {
  ensure_net
  apply_proxy
  log ">>> uv sync (后端依赖, profile=${ENV_NAME})"
  ( cd "${BACKEND_DIR}" && uv sync )
}

# ---- 代码同步 (含参数解析) ----
sync_code() {
  local target_branch="${BRANCH}"
  local target_commit=""
  for arg in "$@"; do
    case "$arg" in
      --branch=*)  target_branch="${arg#*=}" ;;
      --commit=*)  target_commit="${arg#*=}" ;;
      --frontend)  DO_FRONTEND=1 ;;
      --force)     FRONTEND_FORCE=1 ;;
      --no-proxy)  NO_PROXY=1 ;;
      --no-net-on) NO_NET_ON=1 ;;
      *) die "未知参数: $arg" ;;
    esac
  done

  cd "${REPO_ROOT}"
  local old
  old=$(git rev-parse HEAD 2>/dev/null || echo "")

  if [ -n "${target_commit}" ]; then
    log ">>> git checkout ${target_commit} (detached)"
    git fetch --all --quiet
    git checkout --quiet "${target_commit}"
  else
    log ">>> git fetch origin && checkout ${target_branch}"
    git fetch origin --quiet
    git checkout --quiet "${target_branch}"
    # 用 pull --rebase 而不是 reset --hard, 避免洗掉本地独有文件/未推送 commit
    log ">>> git pull --rebase origin ${target_branch}"
    git pull --rebase --autostash origin "${target_branch}" || die "git rebase 冲突, 请手动解决后重跑"
  fi
  local new
  new=$(git rev-parse HEAD)
  if [ "$old" = "$new" ]; then
    log "    代码无变化 (HEAD=${new:0:8})"
  else
    log "    代码更新: ${old:0:8} -> ${new:0:8}"
    git log --oneline "${old}..${new}" 2>/dev/null | sed 's/^/      /' || true
  fi
}

# ---- deploy 主流程 ------------------------------------------------------
do_deploy() {
  doctor
  exec > >(tee -a "${DIAG}") 2>&1
  log ">>> 开始部署 lnrs (profile=${ENV_NAME}, frontend=${DO_FRONTEND}, force=${FRONTEND_FORCE}, no-proxy=${NO_PROXY}, no-net-on=${NO_NET_ON})"
  sync_code "$@"
  sync_backend_deps
  if [ "${DO_FRONTEND}" = "1" ]; then
    build_frontend
    log ">>> 前端已构建, 重启后端使 FastAPI 重新挂载 dist/"
  fi
  svc_restart
  log ">>> 部署完成"
}

# ---- 回滚 ----------------------------------------------------------------
do_rollback() {
  local target="${1:?用法: deploy-h196_3.sh rollback <commit-sha>}"
  doctor
  exec > >(tee -a "${DIAG}") 2>&1
  log ">>> 回滚到 ${target}"
  cd "${REPO_ROOT}"
  git fetch --all --quiet
  git checkout --quiet "${target}"
  sync_backend_deps
  svc_restart
  log ">>> 回滚完成, 当前 HEAD=$(git rev-parse --short HEAD)"
}

# ---- 仅构建前端 --------------------------------------------------------
do_build_frontend() {
  doctor
  exec > >(tee -a "${DIAG}") 2>&1
  DO_FRONTEND=1
  for arg in "$@"; do
    case "$arg" in
      --force)     FRONTEND_FORCE=1 ;;
      --no-proxy)  NO_PROXY=1 ;;
      --no-net-on) NO_NET_ON=1 ;;
      *) die "build-frontend 未知参数: $arg" ;;
    esac
  done
  log ">>> 仅构建前端 (不动 git / 不重启后端)"
  build_frontend
}

# ---- 日志 ----------------------------------------------------------------
do_logs() {
  local n="${1:-200}"
  [ -f "${BACKEND_LOG}" ] || die "日志文件不存在: ${BACKEND_LOG}"
  tail -n "$n" -f "${BACKEND_LOG}"
}

# ---- 入口 ----------------------------------------------------------------
cmd="${1:-}"
shift || true

case "$cmd" in
  status)          svc_status ;;
  restart)         doctor && svc_restart ;;
  deploy)          do_deploy "$@" ;;
  rollback)        do_rollback "$@" ;;
  build-frontend)  do_build_frontend "$@" ;;
  logs)            do_logs "$@" ;;
  doctor)          doctor ;;
  -h|--help|help|"")
    sed -n '2,29p' "$0"
    ;;
  *)
    die "未知命令: $cmd  (执行 $0 help 查看用法)"
    ;;
esac