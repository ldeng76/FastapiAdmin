"""ETL-2 端到端 smoke 测试 — 需要可访问的 PostgreSQL（本地 lnrs 容器）。

无 DB 环境自动跳过（_pg_available 检测）。
幂等性测试：第二次运行行数不变、patient_id 不重新发号。

注：本项目未启用 pytest-asyncio（pyproject 无该依赖），故用 asyncio.run() 包裹
异步调用，保持与现有 tests/ 风格一致（无 async def test_）。
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

# repo root / data root
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_DATA_ROOT = _BACKEND_DIR.parent / "data"


def _pg_available() -> bool:
    """检测本地 PG 是否可连（环境变量 ENVIRONMENT=dev 时读 env/.env.dev）。"""
    if os.getenv("ENVIRONMENT") != "dev":
        return False
    try:
        import asyncpg
    except ImportError:
        return False
    try:
        async def _t():
            conn = await asyncpg.connect(
                host="127.0.0.1", port=5432, user="lnrs", password="lnrs_pwd", database="postgres"
            )
            await conn.close()
        asyncio.run(_t())
        return True
    except Exception:
        return False


def _data_available() -> bool:
    """检测 data/ 是否有 parquet 源。"""
    return (_DATA_ROOT / "zhujiang" / "patient.parquet").exists()


PG_READY = _pg_available()
DATA_READY = _data_available()
SKIP_REASON = (
    "需要 ENVIRONMENT=dev 且本地 PG（lnrs:lnrs_pwd@127.0.0.1:5432/postgres）"
    " 与 ../data/*.parquet 可用"
)


@pytest.mark.skipif(not (PG_READY and DATA_READY), reason=SKIP_REASON)
class TestEtlSmoke:
    """端到端 smoke：跑通单中心 + 验证格式 + 幂等性。

    只跑 shengyi（1016 行，最快），避免单测卡死。
    """

    def test_shengyi_import_and_idempotent(self):
        asyncio.run(self._body())

    @staticmethod
    async def _body():
        from app.plugin.module_medical.hospital.anon_etl_service import run_center
        from sqlalchemy import text
        from app.core.database import async_db_session

        # 第一次运行
        r1 = await run_center("shengyi", data_root=_DATA_ROOT)
        assert r1["status"] == "success", f"第一次运行失败: {r1}"
        assert r1["rows"]["patient"] == 1016

        # 验证格式 + 行数 + 记下 max patient_id
        async with async_db_session() as session:
            n = (await session.execute(text(
                "SELECT COUNT(*) FROM lnrs.lnrs_anon_patient WHERE center_code='shengyi'"
            ))).fetchone()[0]
            assert n == 1016
            bad = (await session.execute(text(
                "SELECT COUNT(*) FROM lnrs.lnrs_anon_patient "
                "WHERE center_code='shengyi' "
                "AND (patient_id !~ '^PT_[0-9]{8}$' OR anon_id !~ '^ANON_[0-9a-f]{12}$')"
            ))).fetchone()[0]
            assert bad == 0
            max_before = (await session.execute(text(
                "SELECT MAX(patient_id) FROM lnrs.lnrs_anon_patient WHERE center_code='shengyi'"
            ))).fetchone()[0]
            await session.rollback()

        # 第二次运行（幂等）
        r2 = await run_center("shengyi", data_root=_DATA_ROOT)
        assert r2["status"] == "success"

        async with async_db_session() as session:
            n2 = (await session.execute(text(
                "SELECT COUNT(*) FROM lnrs.lnrs_anon_patient WHERE center_code='shengyi'"
            ))).fetchone()[0]
            assert n2 == 1016, f"幂等性失败：行数从 1016 变成 {n2}"
            max_after = (await session.execute(text(
                "SELECT MAX(patient_id) FROM lnrs.lnrs_anon_patient WHERE center_code='shengyi'"
            ))).fetchone()[0]
            assert max_after == max_before, (
                f"幂等性失败：patient_id 从 {max_before} 变成 {max_after}（不应重新发号）"
            )
            await session.rollback()

        # #2.3 回归：在同一 event-loop 内验证失败路径——构造无效 parquet，
        # batch 记录必须以 failed 状态保留（不被导入回滚一起带走）。
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            fake_dir = Path(td) / "shengyi"
            fake_dir.mkdir()
            (fake_dir / "patient.parquet").write_bytes(b"not a real parquet file")
            rf = await run_center("shengyi", data_root=Path(td))
            assert rf["status"] == "failed", f"无效 parquet 应失败: {rf}"
            async with async_db_session() as session:
                row = (await session.execute(text(
                    "SELECT status, error FROM lnrs.lnrs_anon_ingest_batch WHERE batch_id=:b"
                ), {"b": rf["batch_id"]})).fetchone()
                assert row is not None, "batch 行必须存在（#2.3 回归：不应被回滚）"
                assert row[0] == "failed", f"batch 应为 failed: {row[0]}"
                assert row[1], "应有错误信息"
                await session.rollback()


@pytest.mark.skipif(not (PG_READY and DATA_READY), reason=SKIP_REASON)
class TestCrossCenterNoCollision:
    """跨中心不碰撞：同一明文 patient_id 在不同中心应得不同 anon_id。

    依赖前序 smoke 或手动 CLI 已把 shengyi + xinqiao + zhujiang 都跑过。
    用 asyncpg 直连，绕开 SQLAlchemy 模块级 engine 的 event-loop 生命周期问题。
    """

    def test_no_shared_anon_id_across_centers(self):
        import asyncpg

        async def _body():
            conn = await asyncpg.connect(
                host="127.0.0.1", port=5432, user="lnrs",
                password="lnrs_pwd", database="postgres",
            )
            try:
                rows = await conn.fetch("""
                    SELECT anon_id, COUNT(DISTINCT center_code) c
                    FROM lnrs.lnrs_anon_patient
                    GROUP BY anon_id HAVING COUNT(DISTINCT center_code) > 1
                """)
                assert len(rows) == 0, f"发现跨中心共享 anon_id: {rows[:3]}"
            finally:
                await conn.close()

        asyncio.run(_body())


@pytest.mark.skipif(not (PG_READY and DATA_READY), reason=SKIP_REASON)
class TestBatchSurvivesImportFailure:
    """#2.3 回归测试占位：见 TestEtlSmoke._body 末尾的失败路径断言。

    真正的 #2.3 断言已合并进 TestEtlSmoke._body（与幂等性测试共享同一 event-loop，
    避免 SQLAlchemy 模块级 engine 跨 asyncio.run 的生命周期问题）。
    这个空类保留作为文档锚点，标记该回归已被覆盖。
    """

