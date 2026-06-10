#!/bin/bash
set -euo pipefail

export HOME="/home/dzy"
export PATH="/home/dzy/.local/bin:/usr/local/bin:/usr/bin:/usr/local/sbin:/usr/sbin"
export UV_CACHE_DIR="/data/uvcache"
export PATH="/home/dzy/pg18/bin:$PATH"
eval "$(fnm env)" 2>/dev/null || true

DEPLOY_DIR="/home/dzy/wk/lnrs_web"
BACKEND_DIR="${DEPLOY_DIR}/backend"
FRONTEND_DIR="${DEPLOY_DIR}/frontend/web"
SERVICE_NAME="lnrs-backend"
BRANCH="main"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

cd "${DEPLOY_DIR}"

log ">>> 开始部署 lnrs_web"

OLD_HEAD=$(git rev-parse HEAD 2>/dev/null || echo "")
git -c http.extraHeader="PRIVATE-TOKEN: glpat-U4_Phcn8ruP819zB-EIdrm86MQp1OjEH.01.0w1y85m2b" fetch origin
git checkout "${BRANCH}"
git reset --hard "origin/${BRANCH}"
NEW_HEAD=$(git rev-parse HEAD)

if [ "$OLD_HEAD" = "$NEW_HEAD" ]; then
    log "代码无变化，跳过部署"
    exit 0
fi

log "代码更新: ${OLD_HEAD:0:8} -> ${NEW_HEAD:0:8}"
git log --oneline "${OLD_HEAD}..${NEW_HEAD}" 2>/dev/null | sed 's/^/  /' || true

log ">>> uv sync (后端依赖)"
cd "${BACKEND_DIR}"
uv sync

log ">>> pnpm install & vite build (前端)"
cd "${FRONTEND_DIR}"
pnpm install --frozen-lockfile 2>/dev/null || pnpm install
pnpm vite build

log ">>> 重启后端服务"
sudo systemctl restart "${SERVICE_NAME}"
sleep 3

if sudo systemctl is-active --quiet "${SERVICE_NAME}"; then
    log ">>> 部署成功: ${SERVICE_NAME} is active"
else
    log ">>> 部署失败: ${SERVICE_NAME} is not active" >&2
    exit 1
fi
