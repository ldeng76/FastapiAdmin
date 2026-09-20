"""anon_etl 测试包的共享配置 —— 沙箱库路径注入 + 安全闸。

本目录下**所有**测试都会写库（`lnrs_anon_*` 表）。两件事在此统一处理，
避免此前「逐文件复制 `_pg_available()`」那种没有单一落点的做法：

1. 把本目录加入 `sys.path`，使各测试文件可以 `from _db_guard import ...`。
2. autouse fixture：在沙箱环境（`ENVIRONMENT=test`）下、任何测试连库之前，
   断言当前 `DATABASE_NAME` 不是真库；命中则 **fail**（不是 skip）。

背景见 `docs/etl2/findings/incident-20260920-test-cascade-delete.md`。
"""
from __future__ import annotations

import sys
from pathlib import Path

#: 让各测试文件能 `from _db_guard import PG_READY, SKIP_REASON`
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

from _db_guard import assert_not_production_db, sandbox_enabled  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _db_sandbox_gate():
    """连库前的安全闸：沙箱环境必须指向非真库，否则 fail。"""
    if sandbox_enabled():
        assert_not_production_db()
    yield
