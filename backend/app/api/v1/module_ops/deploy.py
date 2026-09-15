"""OPS Web 部署面板 — 固定密码触发 ./deploy-h196_3.sh deploy --frontend --force。

路由（OPS_DEPLOY_PASSWORD / OPS_DEPLOY_SLUG 任一为空时全部 404，功能关闭）:
- GET  /ops/{slug}         面板页面（自包含 HTML，无外部依赖）
- POST /ops/{slug}/run     触发部署（systemd-run 瞬态单元，独立 cgroup）
- POST /ops/{slug}/status  查询状态 + 日志尾部 300 行

为什么用 systemd-run 而不是直接 Popen:
deploy 流程末端会 `systemctl stop lnrs-backend`，systemd 默认 KillMode=control-group
会连带杀掉同一 cgroup 内的全部进程 —— 直接 fork 的子进程会死于停服瞬间。
瞬态单元 lnrs-web-deploy 位于 system.slice 独立 cgroup，不受影响。
"""
from __future__ import annotations

import hmac
import os
import pwd
import shlex
import subprocess
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi_limiter.depends import RateLimiter
from pydantic import BaseModel

from app.config.setting import settings
from app.core.logger import log

UNIT_NAME = "lnrs-web-deploy"  # systemd 瞬态 oneshot 单元（独立 cgroup）
DEPLOY_ARGS = ("deploy", "--frontend", "--force")  # 写死的部署命令
LOG_FILE_NAME = "web-deploy.log"
START_FILE_NAME = "web-deploy.started"
TAIL_LINES = 300  # status 接口返回的日志尾部行数

DeployOpsRouter = APIRouter(tags=["OPS 部署面板"], include_in_schema=False)


class DeployPasswordIn(BaseModel):
    password: str


# ---------------------------------------------------------------------
# 纯逻辑辅助（可单测，不依赖真实 systemd）
# ---------------------------------------------------------------------

def _run_dir() -> Path:
    return Path(settings.OPS_DEPLOY_RUN_DIR)


def _log_file() -> Path:
    return _run_dir() / LOG_FILE_NAME


def _read_started() -> str | None:
    """触发时刻（由 _start_deploy 写入；systemd 的 oneshot 单元结束后时间戳属性归 n/a）"""
    try:
        return _run_dir().joinpath(START_FILE_NAME).read_text().strip() or None
    except FileNotFoundError:
        return None


def _enabled() -> bool:
    return bool(settings.OPS_DEPLOY_PASSWORD) and bool(settings.OPS_DEPLOY_SLUG)


def _check_slug(slug: str) -> None:
    """slug 错误或功能关闭 → 404（不泄露面板是否存在）"""
    if not _enabled() or not hmac.compare_digest(slug.encode(), settings.OPS_DEPLOY_SLUG.encode()):
        raise HTTPException(status_code=404, detail="Not Found")


def _check_password(password: str, request: Request) -> None:
    if not hmac.compare_digest(password.encode(), settings.OPS_DEPLOY_PASSWORD.encode()):
        client = request.client.host if request.client else "?"
        log.warning(f"[ops-deploy] 密码错误 ip={client}")
        raise HTTPException(status_code=403, detail="密码错误")


def _log_tail(lines: int = TAIL_LINES) -> list[str]:
    try:
        return _log_file().read_text(errors="replace").splitlines()[-lines:]
    except FileNotFoundError:
        return []


def _systemctl(*args: str) -> str:
    """免密 sudo 执行只读 systemctl 命令，返回 stdout（失败返回空串）"""
    proc = subprocess.run(
        ["sudo", "-n", "systemctl", *args],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return proc.stdout.strip()


def _unit_active() -> bool:
    return _systemctl("is-active", UNIT_NAME) == "active"


def _deploy_status() -> dict:
    """组装状态接口返回: idle / running / succeeded / failed / unknown"""
    unit_state = _systemctl("is-active", UNIT_NAME)
    if unit_state in ("active", "activating", "reloading"):
        return {"state": "running", "started_at": _read_started(), "exit_code": None, "tail": _log_tail()}
    if unit_state == "unknown":  # 单元不存在（未触发过 / 重启过机器）
        return {"state": "idle", "started_at": None, "exit_code": None, "tail": _log_tail()}
    # inactive / failed → 读退出码
    result = _systemctl("show", "-p", "Result", "--value", UNIT_NAME)
    status_val = _systemctl("show", "-p", "ExecMainStatus", "--value", UNIT_NAME)
    try:
        exit_code: int | None = int(status_val)
    except ValueError:
        exit_code = None
    if result == "success" and exit_code == 0:
        state = "succeeded"
    elif exit_code is None and result == "success":
        state = "unknown"  # 未记录到退出码（异常终止），按未知处理
    else:
        state = "failed"
    return {"state": state, "started_at": _read_started(), "exit_code": exit_code, "tail": _log_tail()}


def _build_run_command(log_file: Path, script: str) -> list[str]:
    """构造 systemd-run 命令（纯函数，可单测）。

    wrapper: 先 source profile.d 预热 SOCKS5 隧道（net-on），再 exec 部署脚本，
    输出追加到日志文件。exec 使单元主进程即部署脚本，ExecMainStatus = 部署退出码。
    """
    pw = pwd.getpwuid(os.getuid())
    path = os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")
    workdir = str(Path(script).resolve().parent)
    wrapper = (
        "source /etc/profile.d/socks5-tunnel.sh 2>/dev/null; "
        "net-on >/dev/null 2>&1 || true; "
        f"exec bash {shlex.quote(script)} {' '.join(DEPLOY_ARGS)} "
        f">> {shlex.quote(str(log_file))} 2>&1"
    )
    return [
        "sudo", "-n", "systemd-run",
        f"--unit={UNIT_NAME}",
        "--no-block",  # 关键: 不等 oneshot 单元结束（否则 systemd-run 会阻塞到部署完成）
        "--description=lnrs web deploy (panel)",
        "-p", "Type=oneshot",
        "-p", f"User={pw.pw_name}",
        "-p", f"Group={pw.pw_name}",
        "-p", f"WorkingDirectory={workdir}",
        "-p", f"Environment=HOME={pw.pw_dir}",
        "-p", f"Environment=PATH={path}",
        "bash", "-c", wrapper,
    ]


def _start_deploy() -> dict:
    """触发部署：systemd-run 启动瞬态单元后立即返回"""
    if _unit_active():
        raise HTTPException(status_code=409, detail="部署正在进行中，请稍后再试")
    run_dir = _run_dir()
    run_dir.mkdir(parents=True, exist_ok=True)
    log_file = _log_file()
    with open(log_file, "w", encoding="utf-8"):
        pass  # 截断旧日志
    run_dir.joinpath(START_FILE_NAME).write_text(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    script = settings.OPS_DEPLOY_SCRIPT
    # 清理上次失败态，保证同名瞬态单元可再次 systemd-run
    subprocess.run(
        ["sudo", "-n", "systemctl", "reset-failed", UNIT_NAME],
        capture_output=True,
        timeout=10,
    )
    try:
        proc = subprocess.run(
            _build_run_command(log_file, script),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        log.error("[ops-deploy] systemd-run 超时 (30s)，部署可能未启动，请检查系统状态")
        raise HTTPException(status_code=500, detail="启动部署超时，请检查系统状态后重试")
    if proc.returncode != 0:
        log.error(f"[ops-deploy] systemd-run failed: {proc.stderr.strip()[:300]}")
        raise HTTPException(status_code=500, detail=f"启动部署失败: {proc.stderr.strip()[:200]}")
    log.info(f"[ops-deploy] deploy started unit={UNIT_NAME} job={proc.stdout.strip()[:80]}")
    return {"started": True, "unit": UNIT_NAME}


# ---------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------

@DeployOpsRouter.get(
    "/{slug}",
    include_in_schema=False,
    dependencies=[Depends(RateLimiter(times=30, seconds=60))],
)
async def deploy_panel_page(slug: str) -> HTMLResponse:
    _check_slug(slug)
    return HTMLResponse(_PAGE_HTML)


@DeployOpsRouter.post(
    "/{slug}/run",
    dependencies=[Depends(RateLimiter(times=5, seconds=10))],
)
def deploy_run(slug: str, body: DeployPasswordIn, request: Request) -> JSONResponse:
    _check_slug(slug)
    _check_password(body.password, request)
    _start_deploy()
    client = request.client.host if request.client else "?"
    log.info(f"[ops-deploy] deploy triggered ip={client}")
    return JSONResponse({"started": True, "unit": UNIT_NAME}, status_code=202)


@DeployOpsRouter.post(
    "/{slug}/status",
    dependencies=[Depends(RateLimiter(times=30, seconds=10))],
)
def deploy_status(slug: str, body: DeployPasswordIn, request: Request) -> JSONResponse:
    _check_slug(slug)
    _check_password(body.password, request)
    return JSONResponse(_deploy_status())


# ---------------------------------------------------------------------
# 自包含页面（内联 CSS/JS，零外部依赖）
# ---------------------------------------------------------------------

_PAGE_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>lnrs 部署面板</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; max-width: 860px; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }
  h1 { font-size: 1.4rem; }
  .cmd { font-family: ui-monospace, monospace; background: rgba(127,127,127,.15); padding: .2rem .5rem; border-radius: 4px; font-size: .85rem; }
  .row { display: flex; gap: .5rem; margin: 1rem 0; flex-wrap: wrap; }
  input[type=password] { flex: 1; min-width: 220px; padding: .5rem .6rem; font-size: 1rem; border: 1px solid #8884; border-radius: 6px; background: transparent; color: inherit; }
  button { padding: .5rem 1rem; font-size: 1rem; border: 1px solid #8884; border-radius: 6px; background: transparent; color: inherit; cursor: pointer; }
  button.primary { background: #2563eb; border-color: #2563eb; color: #fff; }
  button:disabled { opacity: .5; cursor: not-allowed; }
  #badge { display: inline-block; padding: .15rem .6rem; border-radius: 999px; font-size: .85rem; border: 1px solid #8884; }
  #badge.running { border-color: #d97706; color: #d97706; }
  #badge.succeeded { border-color: #16a34a; color: #16a34a; }
  #badge.failed, #badge.unknown { border-color: #dc2626; color: #dc2626; }
  #meta { font-size: .85rem; opacity: .8; margin: .5rem 0; min-height: 1.2em; }
  pre { background: rgba(127,127,127,.12); border-radius: 6px; padding: .8rem; font-size: .78rem; overflow: auto; max-height: 420px; white-space: pre-wrap; word-break: break-all; }
  #err { color: #dc2626; margin-top: .5rem; min-height: 1.2em; font-size: .9rem; }
  #restarting { color: #d97706; font-size: .9rem; }
</style>
</head>
<body>
<h1>lnrs 部署面板</h1>
<p>将执行命令：<span class="cmd">./deploy-h196_3.sh deploy --frontend --force</span></p>
<div class="row">
  <input type="password" id="pw" placeholder="输入固定密码" autocomplete="off">
  <button id="btnStatus">刷新状态</button>
  <button id="btnRun" class="primary">开始部署</button>
</div>
<div><span id="badge">--</span></div>
<div id="meta"></div>
<div id="restarting"></div>
<div id="err"></div>
<pre id="log">（输入密码后点「刷新状态」查看部署日志）</pre>
<script>
const base = location.pathname.replace(/\/$/, "");   // /ops/<slug>
const $ = (id) => document.getElementById(id);
let timer = null;
let triggerTime = 0;

function setBadge(state) {
  const b = $("badge");
  const labels = { running: "部署中", idle: "空闲", succeeded: "成功", failed: "失败", unknown: "未知" };
  b.textContent = labels[state] || state;
  b.className = state;
}
function showErr(msg) { $("err").textContent = msg || ""; }

async function api(path, body) {
  const res = await fetch(base + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  let data = null;
  try { data = await res.json(); } catch (e) { /* 非 JSON 响应 */ }
  if (!res.ok) throw new Error((data && (data.msg || data.detail)) || ("HTTP " + res.status));
  return data;
}

function render(d) {
  setBadge(d.state);
  const parts = [];
  if (d.started_at) parts.push("开始于 " + d.started_at);
  if (d.exit_code !== null && d.exit_code !== undefined) parts.push("退出码 " + d.exit_code);
  $("meta").textContent = parts.join(" · ");
  $("log").textContent = (d.tail && d.tail.length) ? d.tail.join("\n") : "（无日志）";
}

function stopPolling() { if (timer) { clearInterval(timer); timer = null; } }

function poll() {
  const pw = $("pw").value;
  api("/status", { password: pw })
    .then((d) => {
      render(d);
      showErr("");
      $("restarting").textContent = "";
      if (d.state === "running") {
        if (triggerTime && Date.now() - triggerTime > 10 * 60 * 1000) {
          stopPolling();
          showErr("轮询超时：10 分钟未收到终态，请手动刷新。");
        }
      } else {
        stopPolling();
        $("btnRun").disabled = false;
      }
    })
    .catch((e) => {
      if (e instanceof TypeError) {
        // 网络层失败 = 后端重启中（部署末端会重启后端）
        $("restarting").textContent = "后端重启中…（部署过程会短暂重启后端，请稍候）";
        showErr("");
        if (triggerTime && Date.now() - triggerTime > 10 * 60 * 1000) {
          stopPolling();
          showErr("轮询超时：10 分钟未收到终态，请手动刷新。");
        }
      } else {
        showErr(e.message);
        stopPolling();
      }
    });
}

function startPolling() {
  stopPolling();
  poll();
  timer = setInterval(poll, 3000);
}

$("btnStatus").addEventListener("click", () => { showErr(""); poll(); });

$("btnRun").addEventListener("click", async () => {
  showErr("");
  if (!confirm("确认执行\n./deploy-h196_3.sh deploy --frontend --force\n\n部署需数分钟，期间后端会重启一次。")) return;
  $("btnRun").disabled = true;
  try {
    await api("/run", { password: $("pw").value });
    triggerTime = Date.now();
    setBadge("running");
    $("meta").textContent = "部署已启动，请稍候。";
    $("log").textContent = "";
    startPolling();
  } catch (e) {
    showErr(e.message);
    $("btnRun").disabled = false;
  }
});
</script>
</body>
</html>
"""
