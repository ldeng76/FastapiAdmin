"""issue-20：stage 表结构与 promote 幂等语义测试。

验证（docs/etl2/prd/issue-20-dicom-series-stage-and-promote.md AC）：
1. lnrs.lnrs_stage_dicom_series 存在，列结构与生产表一致，且 dicom_study_uid 唯一
2. promote（copy_then_merge 路径）：首次插入 → 可见性
3. 重放同一批：生产行数与关键字段值不变（幂等）
4. stage 清空重灌后再 promote：行数不变（series_id 不参与 promote，不撞主键）
5. stage TRUNCATE 不影响生产

promote 语义在 scratch 克隆表上验证（LIKE ... INCLUDING ALL），**不写生产表**
（2026-09-20 事故教训：测试绝不碰真实数据行）。
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

import pytest

# 被测脚本在 backend/etl2/（issue 执行脚本惯例）；先入 path 再 import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "etl2"))


@pytest.fixture(autouse=True)
def _dispose_engine_per_loop():
    """每个用例独立事件循环；结束后销毁池中连接，避免跨 loop 复用报错。"""
    yield
    from app.core.database import async_engine

    asyncio.run(async_engine.dispose())


from _db_guard import PG_READY, SKIP_REASON  # noqa: E402

SCRATCH_STAGE = "lnrs.lnrs_scratch_stage_promote_test"
SCRATCH_PROD = "lnrs.lnrs_scratch_stage_prod_test"
# 约束名全库唯一（唯一索引），scratch 表须用独立名，promote 时显式传入
SCRATCH_PROD_UQ = "lnrs_scratch_stage_prod_dicom_study_uid_uq"


def _setup_sql() -> list[str]:
    return [
        f"DROP TABLE IF EXISTS {SCRATCH_STAGE}",
        f"DROP TABLE IF EXISTS {SCRATCH_PROD}",
        # 结构克隆自真实表（列+默认值）；唯一约束须显式补（LIKE 不复制约束，
        # INCLUDING ALL 只复制索引 → ON CONFLICT ON CONSTRAINT 找不到名字）。
        # 不含数据，不碰生产行。
        f"CREATE TABLE {SCRATCH_STAGE} (LIKE lnrs.lnrs_stage_dicom_series INCLUDING DEFAULTS)",
        f"ALTER TABLE {SCRATCH_STAGE} ADD CONSTRAINT"
        " lnrs_scratch_stage_promote_study_uid_uq UNIQUE (dicom_study_uid)",
        f"CREATE TABLE {SCRATCH_PROD} (LIKE lnrs.lnrs_anon_dicom_series INCLUDING DEFAULTS)",
        f"ALTER TABLE {SCRATCH_PROD} ADD CONSTRAINT"
        f" {SCRATCH_PROD_UQ} UNIQUE (dicom_study_uid)",
    ]


def _teardown_sql() -> list[str]:
    return [
        f"DROP TABLE IF EXISTS {SCRATCH_STAGE}",
        f"DROP TABLE IF EXISTS {SCRATCH_PROD}",
    ]


def _stage_row(study_uid: str, batch_id: str, series_count: int | None = 3) -> str:
    return (
        "INSERT INTO " + SCRATCH_STAGE +
        " (anon_exam_id, dicom_study_uid, file_count, byte_size, series_count,"
        " created_batch_id) VALUES (NULL, '%s', 10, 2048, %s, '%s')"
    ) % (study_uid, "NULL" if series_count is None else series_count, batch_id)


@pytest.mark.skipif(not PG_READY, reason=SKIP_REASON)
class TestStageDicomSeriesPromote:
    def test_stage_table_structure_matches_prod(self):
        """AC：stage 表存在、列结构与生产表一致、dicom_study_uid 唯一。"""
        asyncio.run(self._body_structure())

    @staticmethod
    async def _body_structure():
        from sqlalchemy import text

        from app.core.database import async_db_session

        async with async_db_session() as db:
            cols = await db.execute(text("""
                SELECT table_name, column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'lnrs'
                  AND table_name IN
                      ('lnrs_stage_dicom_series', 'lnrs_anon_dicom_series')
                ORDER BY table_name, ordinal_position
            """))
            by_table: dict[str, list] = {}
            for r in cols:
                by_table.setdefault(r.table_name, []).append(
                    (r.column_name, r.data_type, r.is_nullable)
                )
            assert "lnrs_stage_dicom_series" in by_table, "stage 表不存在（迁移未跑？）"
            assert by_table["lnrs_stage_dicom_series"] == \
                by_table["lnrs_anon_dicom_series"], "stage 列结构与生产表不一致"

            uq = await db.execute(text("""
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'lnrs.lnrs_stage_dicom_series'::regclass
                  AND contype = 'u'
                  AND pg_get_constraintdef(oid) LIKE '%%dicom_study_uid%%'
            """))
            assert uq.scalar(), "stage 表缺 dicom_study_uid 唯一约束（promote 幂等键）"

    def test_promote_insert_visibility_idempotent(self):
        """promote：首次插入可见 → 重放幂等 → stage 重灌再 promote 仍幂等。"""
        asyncio.run(self._body_promote())

    @staticmethod
    async def _body_promote():
        from sqlalchemy import text

        from app.core.database import async_db_session
        from etl2.promote_stage_dicom_series import promote

        batch_id = str(uuid.uuid4())
        async with async_db_session() as db:
            for stmt in _setup_sql():
                await db.execute(text(stmt))
            try:
                await db.execute(text(_stage_row("uid-a", batch_id)))
                await db.execute(text(_stage_row("uid-b", batch_id, None)))
                await db.commit()

                # 1) 首次 promote → 生产可见
                n = await promote(
                    db, stage_table=SCRATCH_STAGE, prod_table=SCRATCH_PROD,
                    constraint=SCRATCH_PROD_UQ,
                )
                assert n == 2
                rows = (await db.execute(text(
                    f"SELECT dicom_study_uid, file_count, series_count"
                    f" FROM {SCRATCH_PROD} ORDER BY dicom_study_uid"
                ))).fetchall()
                assert rows == [("uid-a", 10, 3), ("uid-b", 10, None)]

                # 2) 重放同一批 → 行数与字段值不变
                n = await promote(
                    db, stage_table=SCRATCH_STAGE, prod_table=SCRATCH_PROD,
                    constraint=SCRATCH_PROD_UQ,
                )
                assert n == 2
                cnt, = (await db.execute(text(
                    f"SELECT COUNT(*) FROM {SCRATCH_PROD}"))).fetchone()
                assert cnt == 2
                row_a = (await db.execute(text(
                    f"SELECT file_count, byte_size, series_count"
                    f" FROM {SCRATCH_PROD} WHERE dicom_study_uid = 'uid-a'"
                ))).fetchone()
                assert (row_a[0], row_a[1], row_a[2]) == (10, 2048, 3)

                # 3) stage 清空重灌（新 series_id）→ 再 promote 行数不变、值被覆盖
                await db.execute(text(f"TRUNCATE {SCRATCH_STAGE}"))
                await db.execute(text(_stage_row("uid-a", batch_id, 5)))
                await db.commit()
                n = await promote(
                    db, stage_table=SCRATCH_STAGE, prod_table=SCRATCH_PROD,
                    constraint=SCRATCH_PROD_UQ,
                )
                assert n == 1
                cnt, = (await db.execute(text(
                    f"SELECT COUNT(*) FROM {SCRATCH_PROD}"))).fetchone()
                assert cnt == 2, "重灌后 promote 不应新增行"
                sc, = (await db.execute(text(
                    f"SELECT series_count FROM {SCRATCH_PROD}"
                    " WHERE dicom_study_uid = 'uid-a'"))).fetchone()
                assert sc == 5, "重灌后 promote 应更新字段值"

                # 4) TRUNCATE stage 不影响生产
                await db.execute(text(f"TRUNCATE {SCRATCH_STAGE}"))
                await db.commit()
                cnt, = (await db.execute(text(
                    f"SELECT COUNT(*) FROM {SCRATCH_PROD}"))).fetchone()
                assert cnt == 2
            finally:
                for stmt in _teardown_sql():
                    await db.execute(text(stmt))
                await db.commit()

    def test_promote_empty_stage_noop(self):
        """空 stage → no-op 返回 0。"""
        asyncio.run(self._body_empty())

    @staticmethod
    async def _body_empty():
        from sqlalchemy import text

        from app.core.database import async_db_session
        from etl2.promote_stage_dicom_series import promote

        async with async_db_session() as db:
            for stmt in _setup_sql():
                await db.execute(text(stmt))
            try:
                n = await promote(
                    db, stage_table=SCRATCH_STAGE, prod_table=SCRATCH_PROD,
                    constraint=SCRATCH_PROD_UQ,
                )
                assert n == 0
            finally:
                for stmt in _teardown_sql():
                    await db.execute(text(stmt))
                await db.commit()
