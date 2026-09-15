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


def test_status_running(ops_enabled, monkeypatch):
    monkeypatch.setattr(ops, "_systemctl", _fake_systemctl("active", "", ""))
    (Path(ops_enabled) / "web-deploy.started").write_text("2026-09-15 10:00:00")
    d = ops._deploy_status()
    assert d["state"] == "running"
    assert d["exit_code"] is None
    assert d["started_at"] == "2026-09-15 10:00:00"


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
    assert "--no-block" in cmd  # 必须非阻塞, 否则 systemd-run 会挂到部署结束
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


def test_start_deploy_writes_started_file(ops_enabled, monkeypatch):
    monkeypatch.setattr(ops, "_unit_active", lambda: False)

    class FakeProc:
        returncode = 0
        stdout = "lnrs-web-deploy.service"
        stderr = ""

    monkeypatch.setattr(ops.subprocess, "run", lambda *a, **k: FakeProc())
    ops._start_deploy()
    assert (Path(ops_enabled) / "web-deploy.started").read_text().strip() != ""



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