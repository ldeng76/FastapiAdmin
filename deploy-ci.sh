#!/bin/bash
set -euo pipefail
DIAG=/tmp/deploy-ci.diag
exec > >(tee -a "$DIAG") 2>&1

export HOME="/home/dzy"
export PATH="/home/dzy/.local/bin:/usr/local/bin:/usr/bin:/usr/local/sbin:/usr/sbin"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/home/dzy/.cache/uv}"
export PATH="/home/dzy/pg18/bin:$PATH"
eval "$(fnm env)" 2>/dev/null || true
# 避免 pnpm 检测到 node_modules 与 lockfile 不一致时交互式询问"是否整体重装"
export PNPM_CONFIG_CONFIRM_MODULES_PURGE=false

DEPLOY_DIR="/home/dzy/wk/lnrs"
BACKEND_DIR="${DEPLOY_DIR}/backend"
FRONTEND_DIR="${DEPLOY_DIR}/frontend/web"
ENVIRONMENT="${ENVIRONMENT:-h196_3}"
BACKEND_PORT="${BACKEND_PORT:-8610}"
BACKEND_LOG="${DEPLOY_DIR}/backend/.run/${ENVIRONMENT}.log"
BRANCH="main"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

cd "${DEPLOY_DIR}"

log ">>> 开始部署 lnrs (profile=${ENVIRONMENT})"

OLD_HEAD=$(git rev-parse HEAD 2>/dev/null || echo "")
git -c http.extraHeader="PRIVATE-TOKEN: glpat-U4_Phcn8ruP819zB-EIdrm86MQp1OjEH.01.0w1y85m2b" fetch origin
git checkout "${BRANCH}"
git reset --hard "origin/${BRANCH}"
NEW_HEAD=$(git rev-parse HEAD)

if [ "$OLD_HEAD" = "$NEW_HEAD" ]; then
    log "代码无变化，检查前端构建产物新鲜度..."
    # 上次部署若前端构建中断/失败，src 会比 dist 新，需要重建前端
    if [ -f "${FRONTEND_DIR}/dist/index.html" ] && \
       [ -z "$(find "${FRONTEND_DIR}/src" -type f \( -name '*.vue' -o -name '*.ts' \) \
              -newer "${FRONTEND_DIR}/dist/index.html" -print -quit)" ]; then
        log ">>> dist 是最新，跳过部署"
        exit 0
    fi
    log ">>> src 较 dist 更新，仅重建前端（后端代码未变，跳过重启）"
    cd "${FRONTEND_DIR}"
    pnpm install --frozen-lockfile || pnpm install
    pnpm vite build
    log ">>> 前端重建完成"
    exit 0
fi

log "代码更新: ${OLD_HEAD:0:8} -> ${NEW_HEAD:0:8}"
git log --oneline "${OLD_HEAD}..${NEW_HEAD}" 2>/dev/null | sed 's/^/  /' || true

log ">>> uv sync (后端依赖)"
cd "${BACKEND_DIR}"
uv sync

log ">>> pnpm install & vite build (前端)"
cd "${FRONTEND_DIR}"
pnpm install --frozen-lockfile || pnpm install
pnpm vite build

log ">>> 重启后端服务 (profile=${ENVIRONMENT})"
# 停掉旧进程（匹配 main.py run 或 uvicorn 监听 BACKEND_PORT）
pkill -f "main.py run" 2>/dev/null || true
pkill -f "uvicorn.*:${BACKEND_PORT}" 2>/dev/null || true
sleep 2

mkdir -p "$(dirname "${BACKEND_LOG}")"
cd "${BACKEND_DIR}"
ENVIRONMENT="${ENVIRONMENT}" \
    nohup uv run main.py run --env="${ENVIRONMENT}" \
    >>"${BACKEND_LOG}" 2>&1 &
BACKEND_PID=$!
disown "${BACKEND_PID}" 2>/dev/null || true
log ">>> 后端进程已启动: pid=${BACKEND_PID}, 日志=${BACKEND_LOG}"

# 等待端口就绪（最多 30s）
for i in $(seq 1 30); do
    if ss -tln 2>/dev/null | grep -q ":${BACKEND_PORT}\b"; then
        log ">>> 部署成功: 端口 ${BACKEND_PORT} 已监听"
        exit 0
    fi
    sleep 1
done

log ">>> 部署失败: 端口 ${BACKEND_PORT} 在 30s 内未监听" >&2
log ">>> 最近日志:" >&2
tail -50 "${BACKEND_LOG}" >&2 || true
exit 1
