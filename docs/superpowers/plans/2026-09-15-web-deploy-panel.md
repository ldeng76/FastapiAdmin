# Web 部署面板（固定密码 URL 触发部署）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 访问 `http://<h196_3>:8610/ops/<slug>` 输入固定密码即可执行 `./deploy-h196_3.sh deploy --frontend --force`，并实时查看部署日志与结果。

**Architecture:** FastAPI 后端内新增独立 ops 路由模块（`/ops/<slug>` 页面 + run/status 两个 POST），固定密码常量时间比对鉴权；触发时通过 `sudo systemd-run` 起瞬态 oneshot 单元 `lnrs-web-deploy`（独立 cgroup，避免被 `systemctl stop lnrs-backend` 的 control-group 清理连带杀掉），状态/日志从 systemctl 属性与 `backend/.run/web-deploy.log` 读取，页面每 3s 轮询。

**Tech Stack:** FastAPI、pydantic-settings、fastapi_limiter（项目已有）、systemd-run、pytest + fastapi TestClient。

## Global Constraints

- 设计文档：`docs/superpowers/specs/2026-09-15-web-deploy-panel-design.md`（已批准）。
- 本机即 h196_3 部署机；`lnrs-backend` systemd 服务运行中（:8610），**开发期间不得重启它**，dev 验证走 :8001。
- 工作区有用户未提交的改动（`module_medical` 等 5 个文件），**严禁触碰、严禁整库 git add**。
- 代码注释可中文；标识符/日志英文为主；路由 `include_in_schema=False` 不进 Swagger。
- 配置字段：`OPS_DEPLOY_PASSWORD` / `OPS_DEPLOY_SLUG` / `OPS_DEPLOY_SCRIPT` / `OPS_DEPLOY_RUN_DIR`；密码或 slug 任一为空 → 全部 404。
- 部署命令参数写死：`deploy --frontend --force`。
- 测试不触发真实部署单元（mock 掉 `_systemctl` / `subprocess.run`）。
- 运行测试/命令都在 `backend/` 下用 `uv run`。

---

### Task 1: 配置项与环境文件

**Files:**
- Modify: `backend/app/config/setting.py:261`（`LNRS_DATA_ROOT` 行之后、请求限制配置节之前）
- Modify: `backend/env/.env.h196_3`（文件末尾追加）
- Modify: `backend/env/.env.dev`（gitignore 文件，仅本机追加）
- Create: `scripts/web-deploy-dummy.sh`

**Interfaces:**
- Produces: `settings.OPS_DEPLOY_PASSWORD: str`、`settings.OPS_DEPLOY_SLUG: str`、`settings.OPS_DEPLOY_SCRIPT: str`、`settings.OPS_DEPLOY_RUN_DIR: Path`（默认 `backend/.run`）。

- [ ] **Step 1: setting.py 增加 OPS 配置节**

在 `LNRS_DATA_ROOT: Path = BASE_DIR.parent / "data"`（line 261）之后插入：

```python
    # ================================================= #
    # ************ OPS Web 部署面板配置 **************** #
    # ================================================= #
    # 固定密码 + 随机路径段触发 ./deploy-h196_3.sh 部署。
    # 任一为空 → /ops 全部路由 404（功能关闭）。
    OPS_DEPLOY_PASSWORD: str = ""
    OPS_DEPLOY_SLUG: str = ""
    OPS_DEPLOY_SCRIPT: str = "/home/dzy/wk/lnrs/deploy-h196_3.sh"
    OPS_DEPLOY_RUN_DIR: Path = BASE_DIR / ".run"
```

- [ ] **Step 2: 追加 env 值**

`backend/env/.env.h196_3` 末尾追加：

```
# Web 部署面板（固定密码 URL 部署, 设计: docs/superpowers/specs/2026-09-15-web-deploy-panel-design.md）
OPS_DEPLOY_PASSWORD = "JrhWEk231yPQ-ZTy"
OPS_DEPLOY_SLUG = "TbnQz0L-"
```

`backend/env/.env.dev` 末尾追加（该文件 gitignore，仅本机 dev 测试用，dummy 脚本保证 dev 触发不碰真实服务）：

```
# Web 部署面板（dev 测试值；脚本指向 dummy，触发不会重启真实服务）
OPS_DEPLOY_PASSWORD = "dev-deploy-123"
OPS_DEPLOY_SLUG = "devops01"
OPS_DEPLOY_SCRIPT = "/home/dzy/wk/lnrs/scripts/web-deploy-dummy.sh"
```

- [ ] **Step 3: 创建 dummy 部署脚本**

`scripts/web-deploy-dummy.sh`：

```bash
#!/usr/bin/env bash
# dev 环境用的无害假部署脚本（验证 web 部署面板触发链路用）
set -euo pipefail
echo "[dummy] start $*"
sleep 2
echo "[dummy] done"
```

`chmod +x scripts/web-deploy-dummy.sh`。

- [ ] **Step 4: 验证配置加载**

```bash
cd backend
ENVIRONMENT=h196_3 uv run python -c "from app.config.setting import settings; print(settings.OPS_DEPLOY_PASSWORD, settings.OPS_DEPLOY_SLUG, settings.OPS_DEPLOY_SCRIPT)"
ENVIRONMENT=dev uv run python -c "from app.config.setting import settings; print(settings.OPS_DEPLOY_PASSWORD, settings.OPS_DEPLOY_SLUG, settings.OPS_DEPLOY_SCRIPT)"
```

预期：第一行 `JrhWEk231yPQ-ZTy TbnQz0L- /home/dzy/wk/lnrs/deploy-h196_3.sh`；
第二行 `dev-deploy-123 devops01 /home/dzy/wk/lnrs/scripts/web-deploy-dummy.sh`。

- [ ] **Step 5: Commit**

```bash
git add backend/app/config/setting.py backend/env/.env.h196_3 scripts/web-deploy-dummy.sh docs/superpowers/specs/2026-09-15-web-deploy-panel-design.md docs/superpowers/plans/2026-09-15-web-deploy-panel.md
git commit -m "feat(ops): web 部署面板配置项与 dummy 脚本"
```

---

### Task 2: ops 模块（TDD）

**Files:**
- Create: `backend/app/api/v1/module_ops/__init__.py`
- Create: `backend/app/api/v1/module_ops/deploy.py`
- Test: `backend/tests/test_ops_deploy.py`

**Interfaces:**
- Consumes: Task 1 的 4 个 settings 字段。
- Produces: `ops_router: APIRouter`（prefix `/ops`）；模块内函数 `_check_slug(slug)`、`_check_password(password, request)`、`_log_tail(lines=300)`、`_systemctl(*args) -> str`、`_unit_active() -> bool`、`_deploy_status() -> dict`、`_build_run_command(log_file: Path, script: str) -> list[str]`、`_start_deploy() -> dict`。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_ops_deploy.py`：

```python
"""Web 部署面板测试 — 状态解析 / 鉴权 / 命令构造（不触发真实部署单元）。"""
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.v1.module_ops import deploy as ops
from app.config.setting import settings

UNIT = "lnrs-web-deploy"


@pytest.fixture()
def ops_enabled(monkeypatch, tmp_path):
    """开启功能并隔离运行目录。"""
    monkeypatch.setattr(settings, "OPS_DEPLOY_PASSWORD", "test-pw")
    monkeypatch.setattr(settings, "OPS_DEPLOY_SLUG", "tests001")
    monkeypatch.setattr(settings, "OPS_DEPLOY_RUN_DIR", str(tmp_path))
    return tmp_path


def test_check_slug_disabled_404(monkeypatch):
    monkeypatch.setattr(settings, "OPS_DEPLOY_PASSWORD", "")
    monkeypatch.setattr(settings, "OPS_DEPLOY_SLUG", "")
    with pytest.raises(HTTPException) as e:
        ops._check_slug("anything")
    assert e.value.status_code == 404


def test_check_slug_wrong_404(ops_enabled):
    with pytest.raises(HTTPException) as e:
        ops._check_slug("WRONGSLUG")
    assert e.value.status_code == 404


def test_check_slug_right_ok(ops_enabled):
    ops._check_slug("tests001")  # 不抛异常即通过


def test_log_tail_truncates(ops_enabled):
    (Path(ops_enabled) / "web-deploy.log").write_text("\n".join(f"line-{i}" for i in range(500)))
    tail = ops._log_tail()
    assert len(tail) == 300
    assert tail[0] == "line-200"
    assert tail[-1] == "line-499"


def test_log_tail_missing_file(ops_enabled):
    assert ops._log_tail() == []


def _fake_systemctl(active: str, result: str, exec_status: str):
    def fake(*args):
        if args[:2] == ("is-active", UNIT):
            return active
        if "Result" in args:
            return result
        if "ExecMainStatus" in args:
            return exec_status
        return "2026-09-15 10:00:00 CST"  # ActiveEnterTimestamp

    return fake


def test_status_idle_when_unknown(ops_enabled, monkeypatch):
    monkeypatch.setattr(ops, "_systemctl", _fake_systemctl("unknown", "", ""))
    d = ops._deploy_status()
    assert d["state"] == "idle"
    assert d["exit_code"] is None
    assert d["tail"] == []


def test_status_running(ops_enabled, monkeypatch):
    monkeypatch.setattr(ops, "_systemctl", _fake_systemctl("active", "", ""))
    d = ops._deploy_status()
    assert d["state"] == "running"
    assert d["exit_code"] is None
    assert d["started_at"] == "2026-09-15 10:00:00 CST"


def test_status_succeeded(ops_enabled, monkeypatch):
    monkeypatch.setattr(ops, "_systemctl", _fake_systemctl("inactive", "success", "0"))
    d = ops._deploy_status()
    assert d["state"] == "succeeded"
    assert d["exit_code"] == 0


def test_status_failed_nonzero(ops_enabled, monkeypatch):
    monkeypatch.setattr(ops, "_systemctl", _fake_systemctl("inactive", "success", "1"))
    d = ops._deploy_status()
    assert d["state"] == "failed"
    assert d["exit_code"] == 1


def test_status_failed_result_not_success(ops_enabled, monkeypatch):
    monkeypatch.setattr(ops, "_systemctl", _fake_systemctl("inactive", "protocol", "255"))
    d = ops._deploy_status()
    assert d["state"] == "failed"


def test_status_unknown_no_exit_code(ops_enabled, monkeypatch):
    monkeypatch.setattr(ops, "_systemctl", _fake_systemctl("inactive", "success", ""))
    d = ops._deploy_status()
    assert d["state"] == "unknown"
    assert d["exit_code"] is None


def test_build_run_command(ops_enabled):
    cmd = ops._build_run_command(Path(ops_enabled) / "web-deploy.log", "/home/dzy/wk/lnrs/deploy-h196_3.sh")
    assert (cmd[0], cmd[1], cmd[2]) == ("sudo", "-n", "systemd-run")
    joined = " ".join(cmd)
    assert f"--unit={UNIT}" in joined
    assert "Type=oneshot" in joined
    assert "deploy --frontend --force" in joined
    assert "socks5-tunnel.sh" in joined  # wrapper 预热 net-on


def test_start_deploy_409_when_running(ops_enabled, monkeypatch):
    monkeypatch.setattr(ops, "_unit_active", lambda: True)
    with pytest.raises(HTTPException) as e:
        ops._start_deploy()
    assert e.value.status_code == 409


def test_start_deploy_systemd_run_failure(ops_enabled, monkeypatch):
    monkeypatch.setattr(ops, "_unit_active", lambda: False)

    class FakeProc:
        returncode = 1
        stdout = ""
        stderr = "boom"

    monkeypatch.setattr(ops.subprocess, "run", lambda *a, **k: FakeProc())
    with pytest.raises(HTTPException) as e:
        ops._start_deploy()
    assert e.value.status_code == 500
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && uv run pytest tests/test_ops_deploy.py -x -q
```
预期：FAIL（`ModuleNotFoundError: app.api.v1.module_ops`）。

- [ ] **Step 3: 实现模块**

`backend/app/api/v1/module_ops/__init__.py`：

```python
from fastapi import APIRouter

from .deploy import DeployOpsRouter

ops_router = APIRouter(prefix="/ops")
ops_router.include_router(DeployOpsRouter)
```

`backend/app/api/v1/module_ops/deploy.py`：

```python
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
    if unit_state == "active":
        started = _systemctl("show", "-p", "ActiveEnterTimestamp", "--value", UNIT_NAME)
        return {"state": "running", "started_at": started, "exit_code": None, "tail": _log_tail()}
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
    started = _systemctl("show", "-p", "ActiveEnterTimestamp", "--value", UNIT_NAME)
    return {"state": state, "started_at": started, "exit_code": exit_code, "tail": _log_tail()}


def _build_run_command(log_file: Path, script: str) -> list[str]:
    """构造 systemd-run 命令（纯函数，可单测）。

    wrapper: 先 source profile.d 预热 SOCKS5 隧道（net-on），再 exec 部署脚本，
    输出追加到日志文件。exec 使单元主进程即部署脚本，ExecMainStatus = 部署退出码。
    """
    user = pwd.getpwuid(os.getuid()).pw_name
    home = pwd.getpwuid(os.getuid()).pw_dir
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
        "--description=lnrs web deploy (panel)",
        "-p", "Type=oneshot",
        "-p", f"User={user}",
        "-p", f"Group={user}",
        "-p", f"WorkingDirectory={workdir}",
        "-p", f"Environment=HOME={home}",
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
    script = settings.OPS_DEPLOY_SCRIPT
    # 清理上次失败态，保证同名瞬态单元可再次 systemd-run
    subprocess.run(
        ["sudo", "-n", "systemctl", "reset-failed", UNIT_NAME],
        capture_output=True,
        timeout=10,
    )
    proc = subprocess.run(
        _build_run_command(log_file, script),
        capture_output=True,
        text=True,
        timeout=30,
    )
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
async def deploy_run(slug: str, body: DeployPasswordIn, request: Request) -> JSONResponse:
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
async def deploy_status(slug: str, body: DeployPasswordIn, request: Request) -> JSONResponse:
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
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && uv run pytest tests/test_ops_deploy.py -q
```
预期：全部 PASS（14 个）。

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/module_ops backend/tests/test_ops_deploy.py
git commit -m "feat(ops): web 部署面板模块（密码鉴权 + systemd-run 异步触发）"
```

---

### Task 3: 注册路由 + 端点测试（TDD）

**Files:**
- Modify: `backend/app/scripts/init_app.py:176`（monitor_router 注册行之后）
- Test: `backend/tests/test_ops_deploy.py`（追加端点用例）

**Interfaces:**
- Consumes: Task 2 的 `ops_router`。
- Produces: 运行中的应用路由 `GET /ops/{slug}`、`POST /ops/{slug}/run`、`POST /ops/{slug}/status`。

- [ ] **Step 1: 追加端点测试**

`backend/tests/test_ops_deploy.py` 末尾追加（复用 Task 2 的 `ops_enabled` fixture）。

注意（执行时发现）：项目级 `test_client` fixture 依赖完整 app lifespan（DB/Redis/租户种子），
在本机环境无法启动（既有问题，`tests/test_main.py` 同样失败，与本功能无关）。
端点测试改用**最小 FastAPI app**（仅挂载 `ops_router`，`dependency_overrides` 禁用限流），保持 hermetic：

```python
# 说明: 项目级 test_client fixture 依赖完整 app lifespan（DB/Redis/租户种子），
# 在本机环境无法启动（既有问题, 见 tests/test_main.py）。端点测试改用最小
# FastAPI app（仅挂载 ops 路由 + 依赖覆盖禁用限流），保持 hermetic。


@pytest.fixture(scope="module")
def ops_app():
    from contextlib import asynccontextmanager

    from fastapi import FastAPI
    from fastapi_limiter.depends import RateLimiter

    from app.api.v1.module_ops import ops_router

    @asynccontextmanager
    async def _noop_lifespan(app):
        yield

    app = FastAPI(lifespan=_noop_lifespan)

    def _no_rate_limit():
        return None

    for route in ops_router.routes:
        for dep in route.dependant.dependencies:
            if isinstance(dep.call, RateLimiter):
                app.dependency_overrides[dep.call] = _no_rate_limit
    app.include_router(ops_router)
    return app


def _ops_client(ops_app):
    from fastapi.testclient import TestClient

    return TestClient(ops_app)


def test_endpoint_page_200(ops_app, ops_enabled):
    res = _ops_client(ops_app).get("/ops/tests001")
    assert res.status_code == 200
    assert "lnrs 部署面板" in res.text


def test_endpoint_page_404_wrong_slug(ops_app, ops_enabled):
    assert _ops_client(ops_app).get("/ops/WRONGSLUG").status_code == 404


def test_endpoint_run_wrong_password_403(ops_app, ops_enabled):
    res = _ops_client(ops_app).post("/ops/tests001/run", json={"password": "nope"})
    assert res.status_code == 403


def test_endpoint_run_202(ops_app, ops_enabled, monkeypatch):
    monkeypatch.setattr(ops, "_start_deploy", lambda: {"started": True, "unit": UNIT})
    res = _ops_client(ops_app).post("/ops/tests001/run", json={"password": "test-pw"})
    assert res.status_code == 202
    assert res.json()["started"] is True


def test_endpoint_status_shape(ops_app, ops_enabled, monkeypatch):
    monkeypatch.setattr(
        ops, "_deploy_status",
        lambda: {"state": "idle", "started_at": None, "exit_code": None, "tail": []},
    )
    res = _ops_client(ops_app).post("/ops/tests001/status", json={"password": "test-pw"})
    assert res.status_code == 200
    assert res.json()["state"] == "idle"


def test_endpoint_status_wrong_password_403(ops_app, ops_enabled):
    res = _ops_client(ops_app).post("/ops/tests001/status", json={"password": "nope"})
    assert res.status_code == 403
```

- [ ] **Step 2: 运行端点测试**

（红相说明：最小 app 直接挂载 `ops_router`，端点用例不依赖 init_app 注册，
故无 404 红相；对真实 app 的注册由 Step 4 的路由检查 + Task 4 活体验证覆盖。）

```bash
cd backend && uv run pytest tests/test_ops_deploy.py -q -k endpoint
```
预期：6 个端点用例 PASS。

执行注记（E2E 时发现并修复）：`systemd-run` 对 oneshot 单元**默认阻塞到单元结束**，
必须加 `--no-block`，否则 run 接口会挂到部署完成、202 响应丢失（单元本身不受影响，
独立 cgroup 设计经真实验证成立）。`deploy_run`/`deploy_status` 同步改为普通 `def`
（FastAPI 线程池执行，避免阻塞事件循环）；`_start_deploy` 增加 `TimeoutExpired` → 500。

- [ ] **Step 3: init_app.py 注册路由**

`backend/app/scripts/init_app.py` line 176（`app.include_router(monitor_router, ...)` 之后）插入：

```python
    # OPS Web 部署面板（固定密码鉴权，独立于业务 JWT；功能未配置时 404）
    from app.api.v1.module_ops import ops_router

    app.include_router(ops_router)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && uv run pytest tests/test_ops_deploy.py -q
```
预期：全部 PASS（20 个）。

- [ ] **Step 5: Commit**

```bash
git add backend/app/scripts/init_app.py backend/tests/test_ops_deploy.py
git commit -m "feat(ops): 注册 /ops 部署面板路由"
```

---

### Task 4: dev 活体验证（:8001，dummy 脚本，不碰真实服务）

**Files:** 无代码改动（纯验证）。

**Acceptance（全部满足才算过）:**

- [ ] **Step 1: 启动 dev 后端**

```bash
cd backend && ENVIRONMENT=dev uv run main.py run
```
（后台启动，等到 `:8001` 就绪）

- [ ] **Step 2: 页面与鉴权**

```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8001/ops/devops01        # 200
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8001/ops/WRONGSLUG       # 404
curl -s -X POST http://127.0.0.1:8001/ops/devops01/run -H 'Content-Type: application/json' -d '{"password":"bad"}' -w "\n%{http_code}\n"   # 403
```

- [ ] **Step 3: 触发 dummy 部署并轮询到终态**

```bash
curl -s -X POST http://127.0.0.1:8001/ops/devops01/run -H 'Content-Type: application/json' -d '{"password":"dev-deploy-123"}' -w "\n%{http_code}\n"   # 202
sudo systemctl status lnrs-web-deploy --no-pager    # active（dummy 运行中, ~2s）
# 等待 ~10s 后:
curl -s -X POST http://127.0.0.1:8001/ops/devops01/status -H 'Content-Type: application/json' -d '{"password":"dev-deploy-123"}'
# 预期: state=succeeded, exit_code=0, tail 含 "[dummy] start" / "[dummy] done"
cat backend/.run/web-deploy.log    # 含 dummy 输出
```

- [ ] **Step 4: 验证真实服务未受影响**

```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8610/api/v1/docs   # 200（lnrs-backend 从未被重启）
```

- [ ] **Step 5: 停掉 dev 后端，清理**

停 `:8001` 进程；`sudo systemctl reset-failed lnrs-web-deploy 2>/dev/null`（如处于 inactive 可留）。

---

### Task 5: push + 真实部署 + h196_3 E2E

**Files:** 无代码改动（发布 + 验收）。

**Acceptance:**

- [ ] **Step 1: push 到 origin/main**

```bash
cd /home/dzy/wk/lnrs && git push origin main
```
（需 SOCKS5 通道：先 `net-on`。用户未提交的 module_medical 改动不 push、不提交。）

- [ ] **Step 2: 手工执行既有部署命令上线新代码**

```bash
cd /home/dzy/wk/lnrs && ./deploy-h196_3.sh deploy --frontend --force
```
预期：deploy 成功（含前端构建），:8610 探活 200。

- [ ] **Step 3: E2E — 经 Web 面板触发一次真实部署**

```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8610/ops/TbnQz0L-    # 200
curl -s -X POST http://127.0.0.1:8610/ops/TbnQz0L-/run -H 'Content-Type: application/json' -d '{"password":"wrong"}' -w "\n%{http_code}\n"   # 403
curl -s -X POST http://127.0.0.1:8610/ops/TbnQz0L-/run -H 'Content-Type: application/json' -d '{"password":"JrhWEk231yPQ-ZTy"}' -w "\n%{http_code}\n"   # 202
```
轮询 status（注意部署末端后端会重启，curl 会短暂 connection refused，重试即可），直到：
```json
{"state": "succeeded", "exit_code": 0, ...}
```
且 `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8610/api/v1/docs` → 200。
日志 tail 应含「部署完成」。

- [ ] **Step 4: 交付**

向用户报告访问地址 `http://10.12.196.3:8610/ops/TbnQz0L-` 与密码，说明用法与限制（隧道、并发、密码修改方式）。
