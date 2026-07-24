"""anon 链路联调骨架脚本（HTTP 级 e2e）。

用途
----
本脚本不依赖 backend Python 模块导入，可独立运行；只通过 HTTP/requests
打通 anon ETL 链路，验证：

  1. dev 后端可达，登录 OK
  2. 触发 anon 导入（parquet → lnrs_anon_*）
  3. 轮询状态直到 completed/failed
  4. 查 anon 数据摘要（lnrs_anon_* 各表行数 > 0）
  5. 探测 /medical/centers 等患者路由（**已知现状：路由已删，期望 404**）

适用环境
--------
- dev 库（已跑过 alembic upgrade head + initialize.py，含种子 admin）
- 样例 parquet：docs/demodata/0723_珠江sample_pq/（含 6 张：patient.pq 等）
- 后端端口默认 8610

使用
----
    # 1) 启动后端（dev 库）
    cd backend && uv run python main.py run --env=dev

    # 2) 跑脚本
    cd backend && uv run python scripts/anon_e2e_smoke.py

    # 自定义参数
    uv run python scripts/anon_e2e_smoke.py \\
        --base-url http://127.0.0.1:8610 \\
        --username admin --password 123456 \\
        --hospital-id 1 \\
        --data-dir ../docs/demodata/0723_珠江sample_pq \\
        --centers zhujiang \\
        --timeout 120

退出码
------
0 = 所有 P0 步骤通过；>=1 = 任意 P0 步骤失败（CI 友好）。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # 兼容：缺 requests 时给出友好提示
    sys.stderr.write(
        "缺少依赖 requests。请先安装：uv add requests --dev\n"
        "或：pip install requests\n"
    )
    raise


# --------------------------------------------------------------------------- #
# 默认配置
# --------------------------------------------------------------------------- #

DEFAULT_BASE_URL = "http://127.0.0.1:8610"
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "123456"
DEFAULT_HOSPITAL_ID = 1
DEFAULT_DATA_DIR = "../docs/demodata/0723_珠江sample_pq"
DEFAULT_TIMEOUT = 120  # 秒（导入完成最大等待）
DEFAULT_POLL_INTERVAL = 2.0  # 秒

# anon ETL 终止状态（任一命中即停止轮询）
TERMINAL_STATUSES = {"completed", "failed", "error"}

# 配色（控制台 ANSI；Windows 现代终端默认支持）
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
RESET = "\033[0m"


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #


def step(title: str) -> None:
    """打印步骤标题（青色）。"""
    print(f"\n{CYAN}{'=' * 70}\n{title}\n{'=' * 70}{RESET}")


def ok(msg: str) -> None:
    print(f"{GREEN}✅ {msg}{RESET}")


def fail(msg: str, detail: Any = None) -> None:
    print(f"{RED}❌ {msg}{RESET}")
    if detail is not None:
        print(f"   详情：{detail}")


def warn(msg: str) -> None:
    print(f"{YELLOW}⚠️  {msg}{RESET}")


def fatal(msg: str, detail: Any = None) -> None:
    fail(msg, detail)
    sys.exit(1)


def info(msg: str) -> None:
    print(f"   {msg}")


def unwrap(resp_json: dict[str, Any]) -> Any:
    """剥一层 `{code, msg, data}` 响应壳。"""
    if isinstance(resp_json, dict) and "data" in resp_json and "code" in resp_json:
        return resp_json["data"]
    return resp_json


# --------------------------------------------------------------------------- #
# 客户端
# --------------------------------------------------------------------------- {


class AnonE2EClient:
    """轻量 HTTP 客户端：登录 + 调 anon API。"""

    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.session = requests.Session()

    # --- 1. 健康检查 ------------------------------------------------------- #

    def health(self) -> bool:
        try:
            r = self.session.get(f"{self.base_url}/common/monitoring/health", timeout=5)
            return r.status_code == 200
        except requests.RequestException:
            return False

    # --- 2. 登录 ----------------------------------------------------------- #

    def login(self) -> str:
        """OAuth2 password 表单登录，返回 access_token。"""
        url = f"{self.base_url}/system/auth/login"
        # 大多数 fastapiadmin 部署：tenant_id=None 视为超级管理员 tenant=1
        data = {
            "username": self.username,
            "password": self.password,
            "grant_type": "password",
            "scope": "",
            "client_id": "",
            "client_secret": "",
        }
        try:
            r = self.session.post(url, data=data, timeout=10)
        except requests.RequestException as e:
            fatal(f"登录请求失败：{type(e).__name__}: {e}")

        if r.status_code != 200:
            fatal(
                f"登录失败 (HTTP {r.status_code})",
                r.text[:500],
            )

        payload = r.json()
        token = None

        # 兼容两种返回结构：
        # A) {code, msg, data: {access_token, ...}}
        # B) 文档请求返回的扁平结构
        data_field = unwrap(payload)
        if isinstance(data_field, dict):
            token = data_field.get("access_token") or data_field.get("token")
        if not token and isinstance(payload, dict):
            token = payload.get("access_token") or payload.get("token")

        if not token:
            fatal("登录响应中找不到 access_token", payload)
        ok(f"登录成功，token 长度 {len(token)}")
        return token

    # --- 3. 请求助手 ------------------------------------------------------- #

    def _headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _request(
        self, method: str, path: str, token: str, **kwargs: Any
    ) -> requests.Response:
        url = f"{self.base_url}{path}"
        headers = kwargs.pop("headers", {})
        headers.update(self._headers(token))
        try:
            return self.session.request(method, url, headers=headers, timeout=30, **kwargs)
        except requests.RequestException as e:
            fatal(f"请求 {method} {path} 失败", str(e))

    # --- 4. 触发 anon 导入 ------------------------------------------------- #

    def trigger_anon_import(
        self,
        token: str,
        hospital_id: int,
        data_dir: str,
        centers: list[str] | None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"data_dir_override": data_dir}
        if centers:
            body["center_codes"] = centers

        r = self._request(
            "POST",
            f"/medical/hospital/{hospital_id}/import/anon",
            token,
            json=body,
        )
        if r.status_code != 200:
            fatal(
                f"触发 anon 导入失败 (HTTP {r.status_code})",
                r.text[:500],
            )
        result = unwrap(r.json())
        ok(f"anon 导入已触发：{result}")
        return result

    # --- 5. 轮询状态 ------------------------------------------------------- #

    def poll_status(
        self, token: str, hospital_id: int, timeout: float, interval: float
    ) -> dict[str, Any]:
        """轮询直到 completed/failed/error 或超时。返回最终状态 dict。"""
        deadline = time.time() + timeout
        last_status: dict[str, Any] = {}
        attempt = 0

        while time.time() < deadline:
            attempt += 1
            r = self._request(
                "GET",
                f"/medical/hospital/{hospital_id}/import/anon/status",
                token,
            )
            if r.status_code != 200:
                warn(f"轮询状态失败 (HTTP {r.status_code})：{r.text[:200]}")
                time.sleep(interval)
                continue

            last_status = unwrap(r.json())
            status = (last_status or {}).get("status", "unknown")
            processed = (last_status or {}).get("processed", 0)
            total = (last_status or {}).get("total", 0)
            print(
                f"   [轮询 {attempt}] status={status} "
                f"processed={processed}/{total}",
                flush=True,
            )

            if status in TERMINAL_STATUSES:
                return last_status

            time.sleep(interval)

        fatal(f"轮询超时（>{timeout:.0f}s），最后状态：{last_status}")

    # --- 6. anon 数据摘要 --------------------------------------------------- #

    def get_anon_data_summary(
        self, token: str, hospital_id: int, centers: list[str] | None
    ) -> dict[str, Any]:
        params = {"center_codes": centers} if centers else None
        r = self._request(
            "GET",
            f"/medical/hospital/{hospital_id}/anon-data-summary",
            token,
            params=params,
        )
        if r.status_code != 200:
            fatal(
                f"获取 anon 数据摘要失败 (HTTP {r.status_code})",
                r.text[:500],
            )
        result = unwrap(r.json())
        return result if isinstance(result, dict) else {}

    # --- 7. 患者 API 探针（已知 404） -------------------------------------- #

    def probe_patient_routes(self, token: str) -> dict[str, int]:
        """探测前端实际调用的 3 个患者 API，返回 {path: status_code}。

        **已知现状**：module_medical/controller.py 已删（批次 5），
        这 3 个路径预期返回 404。如返回 200 则说明 PatientService 已重新挂载。
        """
        paths = [
            "/medical/centers",
            "/medical/patients",
            "/medical/patients/sample-patient-id",
        ]
        results: dict[str, int] = {}
        for path in paths:
            r = self._request("GET", path, token)
            results[path] = r.status_code
        return results


# --------------------------------------------------------------------------- #
# 流程编排
# --------------------------------------------------------------------------- #


def run(
    base_url: str,
    username: str,
    password: str,
    hospital_id: int,
    data_dir: Path,
    centers: list[str] | None,
    timeout: float,
    poll_interval: float,
    skip_probe: bool,
) -> int:
    """主流程，返回 exit code（0=成功，1=失败）。"""

    # ---- 前置检查 -------------------------------------------------------- #
    step("0. 前置检查")
    if not data_dir.exists():
        fatal(f"data_dir 不存在：{data_dir}")
    info(f"data_dir: {data_dir}")
    info(f"base_url: {base_url}")
    info(f"hospital_id: {hospital_id}")
    info(f"centers: {centers or '(全部 KNOWN_CENTERS)'}")

    client = AnonE2EClient(base_url, username, password)
    if not client.health():
        warn(f"健康检查未通过：{base_url}/common/monitoring/health")
        warn("继续尝试登录（可能是健康端点未注册）")
    else:
        ok("健康检查通过")

    # ---- 1. 登录 --------------------------------------------------------- #
    step("1. 登录")
    token = client.login()

    # ---- 2. 触发 anon 导入 ---------------------------------------------- #
    step("2. 触发 anon ETL 导入")
    info(f"data_dir={data_dir}  centers={centers or '(默认全部)'}")
    trigger = client.trigger_anon_import(token, hospital_id, str(data_dir), centers)
    job_id = trigger.get("job_id", "<未知>")
    info(f"job_id={job_id}")

    # ---- 3. 轮询状态 ----------------------------------------------------- #
    step("3. 轮询状态")
    final = client.poll_status(token, hospital_id, timeout, poll_interval)
    status = final.get("status")
    if status == "completed":
        ok(f"导入完成：total={final.get('total')} processed={final.get('processed')}")
    else:
        fail(f"导入未成功结束：status={status}  error={final.get('error')!r}")
        return 1

    # ---- 4. anon 数据摘要 ------------------------------------------------ #
    step("4. anon 数据摘要")
    summary = client.get_anon_data_summary(token, hospital_id, centers)
    tables = (summary or {}).get("tables") or {}
    info(f"hospital_id={summary.get('hospital_id')}")
    info(f"lifecycle_status={summary.get('lifecycle_status')}")
    info(f"total_rows={summary.get('total_rows')}")
    for table, count in tables.items():
        info(f"  - lnrs_anon_{table}: {count}")

    if summary.get("total_rows", 0) <= 0:
        fail("总行数为 0，导入看似未写入数据")
        return 1
    ok(f"摘要返回 {len(tables)} 张 anon 表，共 {summary.get('total_rows')} 行")

    # ---- 5. 患者 API 探针（已知 404） ------------------------------------ #
    if skip_probe:
        step("5. 患者 API 探针（跳过：--skip-probe）")
    else:
        step("5. 患者 API 探针（前端 patient.ts 调用的 3 个路由）")
        info("已知：批次 5 删了 module_medical/controller.py，预期 404")
        info("如未来重新挂载 PatientService，这些路径应返回 200")
        probe_results = client.probe_patient_routes(token)
        all_404 = True
        for path, code in probe_results.items():
            if code == 200:
                ok(f"  {path} → 200（PatientService 已挂载）")
                all_404 = False
            elif code == 404:
                info(f"  {path} → 404（预期：路由未挂载）")
            elif code in (401, 403):
                info(f"  {path} → {code}（权限问题，需 super 用户）")
                all_404 = False
            else:
                warn(f"  {path} → {code}（非预期状态码）")
                all_404 = False

        if all_404:
            warn("所有患者 API 均返回 404 — 与批次 5 后的预期一致")
            warn("前端访问 /medical/centers /medical/patients 会 404，需补 controller")
        else:
            ok("至少一个患者 API 返回 200/401/403 — 可能已修复")

    # ---- 总结 ----------------------------------------------------------- #
    step("🎉 全部 P0 步骤通过")
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="anon ETL 链路 HTTP 联调骨架",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"后端 base URL（默认 {DEFAULT_BASE_URL}）",
    )
    parser.add_argument(
        "--username", default=DEFAULT_USERNAME, help=f"登录用户名（默认 {DEFAULT_USERNAME}）"
    )
    parser.add_argument(
        "--password", default=DEFAULT_PASSWORD, help="登录密码（默认从种子 admin/123456）"
    )
    parser.add_argument(
        "--hospital-id",
        type=int,
        default=DEFAULT_HOSPITAL_ID,
        help=f"目标医院 ID（默认 {DEFAULT_HOSPITAL_ID}）",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(DEFAULT_DATA_DIR),
        help="parquet 数据目录（默认指向 docs/demodata/0723_珠江sample_pq/）",
    )
    parser.add_argument(
        "--centers",
        nargs="+",
        default=None,
        help="限定中心列表（默认 None=全部 KNOWN_CENTERS），如：--centers zhujiang",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"轮询超时秒数（默认 {DEFAULT_TIMEOUT:.0f}）",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL,
        help=f"轮询间隔秒数（默认 {DEFAULT_POLL_INTERVAL:.1f}）",
    )
    parser.add_argument(
        "--skip-probe",
        action="store_true",
        help="跳过步骤 5 的患者 API 探针",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    try:
        exit_code = run(
            base_url=args.base_url,
            username=args.username,
            password=args.password,
            hospital_id=args.hospital_id,
            data_dir=args.data_dir,
            centers=args.centers,
            timeout=args.timeout,
            poll_interval=args.poll_interval,
            skip_probe=args.skip_probe,
        )
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        # fatal 已 sys.exit(1)，这里只是兜底防意外的 KeyboardInterrupt 之类
        print(f"{RED}❌ 未捕获异常：{type(e).__name__}: {e}{RESET}", file=sys.stderr)
        sys.exit(1)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()