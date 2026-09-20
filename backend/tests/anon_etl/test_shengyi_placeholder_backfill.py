"""Issue 9 — shengyi 占位标记回填脚本的回归测试。

锁定契约：
1. ``PLACEHOLDER_WHERE_BASE`` 与 0018 migration 同口径（8 个人口学列全 NULL）。
2. ``run_dry_run_async`` 是只读（多次执行返回同一 affected）。
3. ``run_apply`` → ``run_rollback`` 往返：is_placeholder 翻回 apply 前值。
4. UPDATE 的 WHERE 与 0018 migration 字符级一致。

无 DB 环境自动跳过（_pg_available 检测）。
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from sqlalchemy import text


def _pg_available() -> bool:
    if os.getenv("ENVIRONMENT") != "dev":
        return False
    try:
        import asyncpg
    except ImportError:
        return False
    try:

        async def _t():
            conn = await asyncpg.connect(
                host="127.0.0.1", port=5432, user="lnrs",
                password="lnrs_pwd", database="postgres",
            )
            await conn.close()

        asyncio.run(_t())
        return True
    except Exception:
        return False


PG_READY = _pg_available()
SKIP_REASON = "需要 ENVIRONMENT=dev 且本地 PG（lnrs:lnrs_pwd@127.0.0.1:5432/postgres）"


# 与 0018 migration 一致的 8 个人口学列
PLACEHOLDER_DEMOGRAPHIC_COLUMNS = (
    "birth_date", "ethnicity", "smoking_status", "abo_blood_type",
    "rh_blood_type", "native_place", "first_nodule_date", "bmi",
)


async def _dispose_engine() -> None:
    """释放连接池：避免跨 asyncio.run 时的「不同 loop」错误。"""
    from app.core.database import async_engine
    await async_engine.dispose()


async def _seed_placeholder_patients(session, test_center: str, count: int = 5) -> str:
    """通过 ETL2 引擎 _batch_upsert_patients 插入 N 个占位患者，返回 batch_id。

    走引擎路径自动生成 patient_id（PT_<8 位数字）+ anon_id（ANON_<12 hex），
    避免手写 SQL 撞 DDL CHECK 约束（lnrs_anon_ck_patient_id_fmt /
    lnrs_anon_ck_anon_id_fmt）。
    """
    from app.plugin.module_medical.hospital import anon_etl_engine

    test_batch = str(uuid.uuid4())
    records = [
        {
            "local_id": f"T{uuid.uuid4().hex[:8]}{i}",
            "anon_id": None,  # 由 compute_anon_id 自动生成
            "sex": "0",
            "birth_date": None,
        }
        for i in range(count)
    ]
    # 引擎内部按 (center, local_id) 算 anon_id；预填也行。
    from app.plugin.module_medical.hospital.anonymize import compute_anon_id
    for r in records:
        r["anon_id"] = compute_anon_id(test_center, r["local_id"])

    # is_placeholder=False 模拟 shengyi R16 漏标场景
    await anon_etl_engine._batch_upsert_patients(
        session,
        center_code=test_center,
        patient_records=records,
        batch_id=test_batch,
        is_placeholder=False,
    )
    return test_batch


async def _cleanup_test_center(session, test_center: str, test_batch: str) -> None:
    """清理：删 patient + 删 batch + 删备份表。"""
    await session.execute(
        text("DELETE FROM lnrs.lnrs_anon_patient WHERE center_code = :c"),
        {"c": test_center},
    )
    await session.execute(
        text("DELETE FROM lnrs.lnrs_anon_ingest_batch WHERE batch_id = :b"),
        {"b": test_batch},
    )
    await session.execute(text("DROP TABLE IF EXISTS lnrs.p_shengyi_placeholder_bak"))
    await session.commit()


@pytest.mark.skipif(not PG_READY, reason=SKIP_REASON)
class TestPlaceholderRule:
    """0018 同口径占位判据：与 migration SQL 字符级一致。"""

    def test_where_clause_matches_0018_migration(self):
        """回填脚本的 WHERE 必须与 0018 同口径。"""
        from etl2.backfill_shengyi_patient_placeholder import (
            PLACEHOLDER_WHERE_BASE,
        )

        expected_nulls = " AND ".join(
            f"{c} IS NULL" for c in PLACEHOLDER_DEMOGRAPHIC_COLUMNS
        )
        expected = f"sex = '0' AND NOT is_placeholder AND {expected_nulls}"
        assert PLACEHOLDER_WHERE_BASE.strip() == expected, (
            f"PLACEHOLDER_WHERE_BASE 不与 0018 同口径；\n"
            f"  got:  {PLACEHOLDER_WHERE_BASE!r}\n"
            f"  want: {expected!r}"
        )


@pytest.mark.skipif(not PG_READY, reason=SKIP_REASON)
class TestBackfillScriptSemantics:
    """回填脚本的语义契约。"""

    def test_dry_run_is_idempotent_and_readonly(self):
        """dry-run 是只读；多次调用返回同一 affected。"""
        asyncio.run(self._body_dry_run())

    @staticmethod
    async def _body_dry_run():
        from etl2.backfill_shengyi_patient_placeholder import (
            run_dry_run_async,
        )
        before = await run_dry_run_async()
        after = await run_dry_run_async()

        assert before == after, (
            f"dry-run 多次调用应返回同一 affected；before={before} after={after}"
        )
        assert before > 0, (
            f"shengyi 应至少 1 行符合占位判据（PRD 82,682），实际 {before}"
        )
        await _dispose_engine()

    def test_apply_then_rollback_round_trip(self):
        """apply → rollback 必须把 is_placeholder 翻回 apply 前的值。"""
        asyncio.run(self._body_apply_rollback())

    @staticmethod
    async def _body_apply_rollback():
        from app.core.database import async_db_session
        from etl2.backfill_shengyi_patient_placeholder import (
            run_apply,
            run_rollback,
        )

        test_center = f"ph_bak_{uuid.uuid4().hex[:8]}"
        test_batch = ""

        async with async_db_session() as session:
            try:
                test_batch = await _seed_placeholder_patients(
                    session, test_center, count=5,
                )
                await session.commit()

                before_false = (await session.execute(
                    text(
                        "SELECT COUNT(*)::int FROM lnrs.lnrs_anon_patient "
                        "WHERE center_code=:c AND NOT is_placeholder"
                    ),
                    {"c": test_center},
                )).scalar()
                assert before_false == 5

                affected = await run_apply(test_center)
                assert affected == 5, f"apply 应返回 5，实际 {affected}"

                after_true = (await session.execute(
                    text(
                        "SELECT COUNT(*)::int FROM lnrs.lnrs_anon_patient "
                        "WHERE center_code=:c AND is_placeholder"
                    ),
                    {"c": test_center},
                )).scalar()
                assert after_true == 5

                rolled_back = await run_rollback(test_center)
                assert rolled_back == 5

                restored = (await session.execute(
                    text(
                        "SELECT COUNT(*)::int FROM lnrs.lnrs_anon_patient "
                        "WHERE center_code=:c AND NOT is_placeholder"
                    ),
                    {"c": test_center},
                )).scalar()
                assert restored == 5, (
                    f"rollback 后应回到 5 行 FALSE，实际 {restored}"
                )

                await _cleanup_test_center(session, test_center, test_batch)
            finally:
                await _dispose_engine()

    def test_apply_does_not_touch_other_columns(self):
        """apply 只改 is_placeholder 一列；其余 8 个人口学列保持 NULL。"""
        asyncio.run(self._body_other_columns())

    @staticmethod
    async def _body_other_columns():
        from app.core.database import async_db_session
        from etl2.backfill_shengyi_patient_placeholder import (
            run_apply,
            run_rollback,
        )

        test_center = f"ph_cols_{uuid.uuid4().hex[:8]}"
        test_batch = ""

        async with async_db_session() as session:
            try:
                test_batch = await _seed_placeholder_patients(
                    session, test_center, count=1,
                )
                await session.commit()

                await run_apply(test_center)

                row = (await session.execute(
                    text(
                        "SELECT sex, birth_date, ethnicity, smoking_status, "
                        " abo_blood_type, rh_blood_type, native_place, "
                        " first_nodule_date, bmi "
                        "FROM lnrs.lnrs_anon_patient "
                        "WHERE center_code=:c"
                    ),
                    {"c": test_center},
                )).fetchone()
                assert row[0] == "0", f"sex 应保持 '0'，实际 {row[0]!r}"
                for i, col in enumerate(PLACEHOLDER_DEMOGRAPHIC_COLUMNS, start=1):
                    assert row[i] is None, (
                        f"{col} 应保持 NULL，实际 {row[i]!r}"
                    )

                await run_rollback(test_center)
                await _cleanup_test_center(session, test_center, test_batch)
            finally:
                await _dispose_engine()
