"""写库测试的库选择与安全闸 —— **单一落点**。

## 背景

2026-09-20 事故：`test_etl2_cli_defect_fixes.py` 用**真实中心名**（`"zhujiang"` /
`"shengyi"`）驱动 `run_center`，而清理写成按中心删除：

    DELETE FROM lnrs.lnrs_anon_ingest_batch WHERE center_code = :c

该用例把 `_create_batch` monkeypatch 成从不写库的 fake，所以这条 DELETE 删掉的
**全是真实 batch**，经 `dicom_series.created_batch_id` 的 `ON DELETE CASCADE`
连带删除 zhujiang 86,203 + shengyi 82,057 行。

根因不是那条 SQL 写错，而是**测试连的是真库且没有任何隔离**。
复盘：`docs/etl2/findings/incident-20260920-test-cascade-delete.md`

## 为什么取代旧的逐文件 `_pg_available()`

旧守卫是**可用性门**，语义恰好反向 —— 它跳过「PG 不在」（唯一安全场景），
放行「PG 在」（唯一危险场景）；且逐文件复制、没有单一落点。另外
`.gitlab-ci.yml` 没有 test stage，CI 里 PG 不可达 → 这些用例在 CI 中永远 skip，
破坏性路径对 CI 完全不可见。

## 新语义

| 条件 | 行为 |
|---|---|
| `ENVIRONMENT != "test"` | 写库测试 **skip**（不跑就没风险） |
| `ENVIRONMENT == "test"` 且库名命中真库集合 | **fail**（配置错误必须炸，不能静默写真库） |
| `ENVIRONMENT == "test"` 且沙箱库可连 | 正常跑 |

沙箱库是 `lnrs_dev`（同实例的独立**数据库**，schema 名保持 `lnrs`）——
不用独立 schema，因为代码里有 470 处硬编码 `lnrs.` 前缀会绕过 `search_path`。
见 `backend/env/.env.test`。

## 用法

    cd backend && ENVIRONMENT=test uv run pytest tests/anon_etl/

测试文件顶部：

    from tests.anon_etl._db_guard import PG_READY, SKIP_REASON

    @pytest.mark.skipif(not PG_READY, reason=SKIP_REASON)
"""
from __future__ import annotations

import asyncio
import os

#: 只有该环境才允许跑写库测试（加载 env/.env.test → 沙箱库 lnrs_dev）
SANDBOX_ENVIRONMENT = "test"

#: 绝不允许被测试写入的库名（真库）。命中即 fail。
PRODUCTION_DB_NAMES = frozenset({"postgres"})

SKIP_REASON = (
    "写库测试只在 ENVIRONMENT=test（沙箱库 lnrs_dev）下运行；"
    f"当前 ENVIRONMENT={os.getenv('ENVIRONMENT')!r}。"
    "用法：cd backend && ENVIRONMENT=test uv run pytest tests/anon_etl/"
)


def sandbox_enabled() -> bool:
    """是否处于测试沙箱环境（决定写库测试跑还是 skip）。"""
    return os.getenv("ENVIRONMENT") == SANDBOX_ENVIRONMENT


def assert_not_production_db() -> str:
    """确认当前配置指向沙箱库；命中真库名则 **fail**（不是 skip）。返回库名。

    只在 ``sandbox_enabled()`` 为真时才有意义 —— 由
    ``tests/anon_etl/conftest.py`` 的 autouse fixture 调用。
    """
    from app.config.setting import settings

    name = settings.DATABASE_NAME
    if name in PRODUCTION_DB_NAMES:
        raise AssertionError(
            f"拒绝在真库上跑写库测试：DATABASE_NAME={name!r} 属于真库集合 "
            f"{sorted(PRODUCTION_DB_NAMES)}。"
            "请检查 env/.env.test 的 DATABASE_NAME 是否被改成了真库名；"
            "期望值是沙箱库 'lnrs_dev'。"
            "背景见 docs/etl2/findings/incident-20260920-test-cascade-delete.md"
        )
    return name


def db_params() -> dict:
    """从 settings 取沙箱库连接参数（跟随 .env.test，不硬编码库名）。"""
    from app.config.setting import settings

    return {
        "host": settings.DATABASE_HOST,
        "port": int(settings.DATABASE_PORT),
        "user": settings.DATABASE_USER,
        "password": settings.DATABASE_PASSWORD,
        "database": settings.DATABASE_NAME,
    }


def _probe() -> bool:
    """沙箱启用且沙箱库可连时为真。非沙箱环境**不做任何连接**。"""
    if not sandbox_enabled():
        return False
    try:
        import asyncpg  # noqa: PLC0415
    except ImportError:
        return False
    try:
        params = db_params()

        async def _t() -> None:
            conn = await asyncpg.connect(**params)
            await conn.close()

        asyncio.run(_t())
        return True
    except Exception:  # noqa: BLE001
        return False


PG_READY = _probe()
