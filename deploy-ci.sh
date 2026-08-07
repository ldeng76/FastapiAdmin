#!/bin/bash
set -euo pipefail
DIAG=/tmp/deploy-ci.diag
exec > >(tee -a "$DIAG") 2>&1
export HOME="/home/dzy"
export PATH="/home/dzy/.local/bin:/usr/local/bin:/usr/bin:/usr/local/sbin:/usr/sbin"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/home/dzy/.cache/uv}"
export PATH="/home/dzy/pg18/bin:/opt/node24/bin:$PATH"
eval "$(fnm env)" 2>/dev/null || true
# 避免 pnpm 检测到 node_modules 与 lockfile 不一致时交互式询问"是否整体重装"
export PNPM_CONFIG_CONFIRM_MODULES_PURGE=false

DEPLOY_DIR="/home/dzy/wk/lnrs"
BACKEND_DIR="${DEPLOY_DIR}/backend"
FRONTEND_DIR="${DEPLOY_DIR}/frontend/web"
ENVIRONMENT="${ENVIRONMENT:-h196_3}"
BACKEND_PORT="${BACKEND_PORT:-8610}"
BACKEND_HEALTH_URL="${BACKEND_HEALTH_URL:-http://127.0.0.1:${BACKEND_PORT}/api/v1/docs}"
BACKEND_LOG="${DEPLOY_DIR}/backend/.run/${ENVIRONMENT}.log"
BRANCH="main"
cd "${DEPLOY_DIR}"
log ">>> 开始部署 lnrs (profile=${ENVIRONMENT})"

OLD_HEAD=$(git rev-parse HEAD 2>/dev/null || echo "")
if [ -z "${GITLAB_FETCH_TOKEN:-}" ]; then
    log ">>> 错误: 未提供 GITLAB_FETCH_TOKEN（在 GitLab CI/CD Variables 配置，或本地运行时导出）" >&2
    exit 1
fi
git -c http.extraHeader="PRIVATE-TOKEN: ${GITLAB_FETCH_TOKEN}" fetch origin
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
BACKEND_SERVICE="${BACKEND_SERVICE:-lnrs-backend}"
# 用 systemd 拉起后端, 失败自动重启由 systemd 兜底
if ! sudo systemctl restart "${BACKEND_SERVICE}"; then
    log ">>> 部署失败: sudo systemctl restart ${BACKEND_SERVICE} 失败" >&2
    exit 1
fi

# 等待端口监听（最多 30s; systemd 启动 + uv sync 较慢）
for i in $(seq 1 30); do
    ss -tln 2>/dev/null | grep -q ":${BACKEND_PORT}\b" && break
    sleep 1
done

# 端口监听后, HTTP 200 探活（最多再等 60s; 后端初始化慢）
for i in $(seq 1 60); do
    code=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 5 "${BACKEND_HEALTH_URL}" 2>/dev/null || echo "000")
    if [ "$code" = "200" ]; then
        log ">>> 部署成功: HTTP 200 @ ${BACKEND_HEALTH_URL}"
        exit 0
    fi
    sleep 1
done

log ">>> 部署失败: ${BACKEND_HEALTH_URL} 在 60s 内未返回 200" >&2
log ">>> service 状态:" >&2
sudo systemctl status "${BACKEND_SERVICE}" --no-pager 2>&1 | tail -30 >&2 || true
log ">>> 最近日志:" >&2
tail -50 "${BACKEND_LOG}" >&2 || true
# 端口在但 HTTP 不通 — 让 systemd 看着重启
sudo systemctl restart "${BACKEND_SERVICE}" 2>/dev/null || true
exit 1
