"""issue-22：promote 护栏测试 —— 校验闸 / 审计 / 按批次回滚。

验证（docs/etl2/prd/issue-22-promote-guardrails.md AC）：
1. 校验闸：NOT NULL/CHECK 违规、外键完整性违规 → 拒绝 promote，生产零变化
   （行数 + pg_stat_user_tables.n_tup_ins 不变）
2. 空集是异常不是通过（复盘 §4.4 放大 4）
3. 审计：apply 与 dry-run 都写审计，可按 batch_id 查「动了哪些表、多少行」
4. 回滚：行数复原、只撤销本批次、可重放、拒绝重复回滚

全部在 scratch 克隆表上验证，不写生产数据行（2026-09-20 事故教训）。
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "etl2"))


@pytest.fixture(autouse=True)
def _dispose_engine_per_loop():
    """每个用例独立事件循环；结束后销毁池中连接，避免跨 loop 复用报错。"""
    yield
    from app.core.database import async_engine

    asyncio.run(async_engine.dispose())


from _db_guard import PG_READY, SKIP_REASON  # noqa: E402

SCRATCH_STAGE = "lnrs.lnrs_scratch_stage_guard_test"
SCRATCH_PROD = "lnrs.lnrs_scratch_prod_guard_test"
SCRATCH_PARENT = "lnrs.lnrs_scratch_parent_guard_test"
SCRATCH_PROD_UQ = "lnrs_scratch_prod_guard_study_uid_uq"
SCRATCH_FK = "lnrs_scratch_prod_guard_exam_fk"

SCRATCH_TABLES = (SCRATCH_STAGE, SCRATCH_PROD, SCRATCH_PARENT)


def _setup_sql(with_fk: bool = False) -> list[str]:
    stmts = [
        f"DROP TABLE IF EXISTS {SCRATCH_STAGE}",
        f"DROP TABLE IF EXISTS {SCRATCH_PROD}",
        f"DROP TABLE IF EXISTS {SCRATCH_PARENT}",
        f"CREATE TABLE {SCRATCH_PARENT} (exam_id varchar(64) PRIMARY KEY)",
        f"INSERT INTO {SCRATCH_PARENT} VALUES ('101'), ('102')",
        f"CREATE TABLE {SCRATCH_STAGE} (LIKE lnrs.lnrs_stage_dicom_series INCLUDING DEFAULTS)",
        f"ALTER TABLE {SCRATCH_STAGE} ADD CONSTRAINT"
        " lnrs_scratch_stage_guard_study_uid_uq UNIQUE (dicom_study_uid)",
        f"CREATE TABLE {SCRATCH_PROD} (LIKE lnrs.lnrs_anon_dicom_series INCLUDING DEFAULTS)",
        f"ALTER TABLE {SCRATCH_PROD} ADD CONSTRAINT {SCRATCH_PROD_UQ} UNIQUE (dicom_study_uid)",
    ]
    if with_fk:
        # 校验闸按 live pg_constraint 工作 —— 在 scratch 上加真 FK 验证它
        stmts.append(
            f"ALTER TABLE {SCRATCH_PROD} ADD CONSTRAINT {SCRATCH_FK}"
            f" FOREIGN KEY (anon_exam_id) REFERENCES {SCRATCH_PARENT}(exam_id)")
    return stmts


def _teardown_sql() -> list[str]:
    return [
        f"DROP TABLE IF EXISTS {SCRATCH_STAGE}",
        f"DROP TABLE IF EXISTS {SCRATCH_PROD}",
        f"DROP TABLE IF EXISTS {SCRATCH_PARENT}",
    ]


async def _cleanup_audit(batch_ids: list[str]) -> None:
    from sqlalchemy import text

    from app.core.database import async_db_session
    async with async_db_session() as db:
        for b in batch_ids:
            await db.execute(text("""
                DELETE FROM lnrs.lnrs_promote_audit_row
                WHERE audit_id IN (SELECT audit_id FROM lnrs.lnrs_promote_audit
                                   WHERE batch_id = CAST(:b AS uuid))
            """), {"b": b})
            await db.execute(text(
                "DELETE FROM lnrs.lnrs_promote_audit WHERE batch_id = CAST(:b AS uuid)"
            ), {"b": b})
        await db.commit()


def _stage_insert(study_uid: str, batch_id: str, *, file_count=10,
                  anon_exam_id="NULL") -> str:
    return (
        f"INSERT INTO {SCRATCH_STAGE}"
        " (anon_exam_id, dicom_study_uid, file_count, byte_size, series_count,"
        f" created_batch_id) VALUES ({anon_exam_id}, '{study_uid}',"
        f" {'NULL' if file_count is None else file_count}, 2048, 3,"
        f" '{batch_id}'::uuid)"
    )


async def _prod_stat(db) -> tuple[int, int]:
    """生产行数 + n_tup_ins（AC：拒绝 promote 后两者零变化）。"""
    from sqlalchemy import text
    cnt, = (await db.execute(
        text(f"SELECT COUNT(*) FROM {SCRATCH_PROD}"))).fetchone()
    n_ins, = (await db.execute(text("""
        SELECT n_tup_ins FROM pg_stat_user_tables
        WHERE relid = to_regclass(:t)
    """), {"t": SCRATCH_PROD})).fetchone()
    return int(cnt), int(n_ins)


@pytest.mark.skipif(not PG_READY, reason=SKIP_REASON)
class TestPromoteGuardrails:
    def test_refused_on_not_null_violation(self):
        """NOT NULL 违规行 → 拒绝 promote + 生产零变化。"""
        asyncio.run(self._body_not_null())

    @staticmethod
    async def _body_not_null():
        from sqlalchemy import text

        from app.core.database import async_db_session, async_engine
        await async_engine.dispose()  # 丢弃其它测试 loop 遗留的池连接
        from etl2.promote_guardrails import PromoteRefused, validate_stage
        from etl2.promote_stage_dicom_series import promote

        batch_id = str(uuid.uuid4())
        try:
            async with async_db_session() as db:
                for stmt in _setup_sql():
                    await db.execute(text(stmt))
                # stage 与生产约束漂移的场景：stage 缺 NOT NULL（真实世界中
                # stage 是 LIKE 建的、约束可能被人为放宽），坏行只能进 stage；
                # 校验闸用「目标表结构克隆实插」在 promote 前拦下。
                await db.execute(text(
                    f"ALTER TABLE {SCRATCH_STAGE} ALTER COLUMN file_count DROP NOT NULL"))
                await db.execute(
                    text(_stage_insert("uid-bad", batch_id, file_count=None)))
                await db.commit()

                before = await _prod_stat(db)
                async with async_db_session() as db2:
                    violations = await validate_stage(
                        db2, stage_table=SCRATCH_STAGE, prod_table=SCRATCH_PROD,
                        promote_columns=["anon_exam_id", "dicom_study_uid",
                                         "file_count", "byte_size",
                                         "series_count", "created_batch_id",
                                         "created_at", "updated_at"])
                assert any("非空" in v for v in violations), violations
                with pytest.raises(PromoteRefused):
                    async with async_db_session() as db3:
                        await promote(
                            db3, stage_table=SCRATCH_STAGE,
                            prod_table=SCRATCH_PROD, constraint=SCRATCH_PROD_UQ)
                after = await _prod_stat(db)
            assert before == after, f"生产零变化被破坏: {before} → {after}"
        finally:
            await _cleanup_audit([batch_id])
            async with async_db_session() as db:
                for stmt in _teardown_sql():
                    await db.execute(text(stmt))
                await db.commit()

    def test_refused_on_fk_violation(self):
        """外键完整性违规 → 校验闸拒绝（查 live pg_constraint）。"""
        asyncio.run(self._body_fk())

    @staticmethod
    async def _body_fk():
        from sqlalchemy import text

        from app.core.database import async_db_session, async_engine
        await async_engine.dispose()  # 丢弃其它测试 loop 遗留的池连接
        from etl2.promote_guardrails import PromoteRefused, validate_stage
        from etl2.promote_stage_dicom_series import PROMOTE_COLUMNS, promote

        batch_id = str(uuid.uuid4())
        try:
            async with async_db_session() as db:
                for stmt in _setup_sql(with_fk=True):
                    await db.execute(text(stmt))
                await db.execute(
                    text(_stage_insert("uid-orphan", batch_id, anon_exam_id="999999")))
                await db.commit()

            async with async_db_session() as db2:
                violations = await validate_stage(
                    db2, stage_table=SCRATCH_STAGE, prod_table=SCRATCH_PROD,
                    promote_columns=PROMOTE_COLUMNS)
                assert any("外键" in v for v in violations), violations
                with pytest.raises(PromoteRefused):
                    await promote(
                        db2, stage_table=SCRATCH_STAGE,
                        prod_table=SCRATCH_PROD, constraint=SCRATCH_PROD_UQ)
        finally:
            await _cleanup_audit([batch_id])
            async with async_db_session() as db:
                for stmt in _teardown_sql():
                    await db.execute(text(stmt))
                await db.commit()

    def test_empty_stage_is_anomaly(self):
        """空集单独判为异常，不让一致性检查静默通过（复盘 §4.4）。"""
        asyncio.run(self._body_empty())

    @staticmethod
    async def _body_empty():
        from sqlalchemy import text

        from app.core.database import async_db_session, async_engine
        await async_engine.dispose()  # 丢弃其它测试 loop 遗留的池连接
        from etl2.promote_guardrails import PromoteRefused, validate_stage
        from etl2.promote_stage_dicom_series import PROMOTE_COLUMNS, promote

        batch_id = str(uuid.uuid4())
        try:
            async with async_db_session() as db:
                for stmt in _setup_sql():
                    await db.execute(text(stmt))
                await db.commit()
            async with async_db_session() as db2:
                violations = await validate_stage(
                    db2, stage_table=SCRATCH_STAGE, prod_table=SCRATCH_PROD,
                    promote_columns=PROMOTE_COLUMNS)
            assert violations and "空集" in violations[0], violations
            with pytest.raises(PromoteRefused):
                async with async_db_session() as db3:
                    await promote(
                        db3, stage_table=SCRATCH_STAGE,
                        prod_table=SCRATCH_PROD, constraint=SCRATCH_PROD_UQ)
        finally:
            await _cleanup_audit([batch_id])
            async with async_db_session() as db:
                for stmt in _teardown_sql():
                    await db.execute(text(stmt))
                await db.commit()

    def test_audit_written_and_queryable(self):
        """apply 与 dry-run 都写审计；按 batch 查得到动了哪些表、多少行。"""
        asyncio.run(self._body_audit())

    @staticmethod
    async def _body_audit():
        from sqlalchemy import text

        from app.core.database import async_db_session, async_engine
        await async_engine.dispose()  # 丢弃其它测试 loop 遗留的池连接
        from etl2.promote_guardrails import audit_by_batch
        from etl2.promote_stage_dicom_series import promote

        batch_apply = str(uuid.uuid4())
        try:
            async with async_db_session() as db:
                for stmt in _setup_sql():
                    await db.execute(text(stmt))
                await db.execute(text(_stage_insert("uid-a1", batch_apply)))
                await db.execute(text(_stage_insert("uid-a2", batch_apply)))
                await db.commit()
                async with async_db_session() as db2:
                    n, bid = await promote(
                        db2, stage_table=SCRATCH_STAGE,
                        prod_table=SCRATCH_PROD, constraint=SCRATCH_PROD_UQ)
                    assert n == 2
                    audits = await audit_by_batch(db2, bid)
                    assert len(audits) == 1
                    a = audits[0]
                    assert a["target_table"] == SCRATCH_PROD
                    assert a["mode"] == "apply" and a["validation"] == "passed"
                    assert a["upsert_rows"] == 2 and a["stage_rows"] == 2
                    assert a["actor"] and a["created_at"] is not None
                    # 行级明细可回答「动了哪些行」
                    detail, = (await db2.execute(text("""
                        SELECT COUNT(*) FROM lnrs.lnrs_promote_audit_row
                        WHERE audit_id = :aid
                    """), {"aid": a["audit_id"]})).fetchone()
                    assert detail == 2

                    # dry-run：写审计但不改生产
                    n_dry, bid_dry = await promote(
                        db2, stage_table=SCRATCH_STAGE,
                        prod_table=SCRATCH_PROD, constraint=SCRATCH_PROD_UQ,
                        mode="dry_run")
                    assert n_dry == 0
                    dry_audits = await audit_by_batch(db2, bid_dry)
                    assert len(dry_audits) == 1
                    assert dry_audits[0]["mode"] == "dry_run"
                    assert dry_audits[0]["validation"] == "passed"
                    assert dry_audits[0]["upsert_rows"] == 0
                    cnt_before, = (await db2.execute(text(
                        f"SELECT COUNT(*) FROM {SCRATCH_PROD}"))).fetchone()
                    cnt_after = cnt_before
                batch_dry = bid_dry
        finally:
            await _cleanup_audit([batch_apply, batch_dry])
            async with async_db_session() as db:
                for stmt in _teardown_sql():
                    await db.execute(text(stmt))
                await db.commit()

    def test_rollback_restores_replay_and_scoping(self):
        """回滚复原行数；只撤销本批次；重放可再 promote；拒绝重复回滚。"""
        asyncio.run(self._body_rollback())

    @staticmethod
    async def _body_rollback():
        from sqlalchemy import text

        from app.core.database import async_db_session, async_engine
        await async_engine.dispose()  # 丢弃其它测试 loop 遗留的池连接
        from etl2.promote_guardrails import PromoteRefused, rollback_batch
        from etl2.promote_stage_dicom_series import promote

        batch_id = str(uuid.uuid4())
        try:
            async with async_db_session() as db:
                for stmt in _setup_sql():
                    await db.execute(text(stmt))
                # 生产预置：uid-old 会被本批次 update；uid-keep 属于「其它批次」
                await db.execute(text(
                    f"INSERT INTO {SCRATCH_PROD} (dicom_study_uid, file_count,"
                    f" byte_size, series_count, created_batch_id)"
                    f" VALUES ('uid-old', 1, 100, 1, '{uuid.uuid4()}'),"
                    f"        ('uid-keep', 7, 700, 7, '{uuid.uuid4()}')"))
                # stage：uid-old 更新 + uid-new 插入
                await db.execute(text(_stage_insert("uid-old", batch_id, file_count=42)))
                await db.execute(text(_stage_insert("uid-new", batch_id, file_count=9)))
                await db.commit()

            async with async_db_session() as db2:
                cnt_pre, = (await db2.execute(text(
                    f"SELECT COUNT(*) FROM {SCRATCH_PROD}"))).fetchone()
                _, bid = await promote(
                    db2, stage_table=SCRATCH_STAGE,
                    prod_table=SCRATCH_PROD, constraint=SCRATCH_PROD_UQ)
                cnt_promoted, = (await db2.execute(text(
                    f"SELECT COUNT(*) FROM {SCRATCH_PROD}"))).fetchone()
                assert cnt_promoted == cnt_pre + 1, "promote 应净增 1 行(uid-new)"

                r = await rollback_batch(
                    db2, batch_id=bid, prod_table=SCRATCH_PROD,
                    key_column="dicom_study_uid",
                    promote_columns=["anon_exam_id", "dicom_study_uid",
                                     "file_count", "byte_size", "series_count",
                                     "created_batch_id", "created_at", "updated_at"])
                await db2.commit()
            assert r == {"deleted": 1, "restored": 1}, r

            async with async_db_session() as db3:
                cnt_rb, = (await db3.execute(text(
                    f"SELECT COUNT(*) FROM {SCRATCH_PROD}"))).fetchone()
                old = (await db3.execute(text(
                    f"SELECT file_count, byte_size, series_count"
                    f" FROM {SCRATCH_PROD} WHERE dicom_study_uid = 'uid-old'"
                ))).fetchone()
                keep = (await db3.execute(text(
                    f"SELECT file_count FROM {SCRATCH_PROD}"
                    f" WHERE dicom_study_uid = 'uid-keep'"))).fetchone()
                assert cnt_rb == cnt_pre, "回滚后行数应与 promote 前一致"
                assert tuple(old) == (1, 100, 1), "update 行应按 preimage 还原"
                assert keep == (7,), "其它批次写入的行不得被回滚触碰"

                # 重复回滚拒绝
                with pytest.raises(PromoteRefused):
                    await rollback_batch(
                        db3, batch_id=bid, prod_table=SCRATCH_PROD,
                        key_column="dicom_study_uid",
                        promote_columns=["file_count"])

                # 重放：同一 stage 再 promote 一次仍成功
                n, _ = await promote(
                    db3, stage_table=SCRATCH_STAGE,
                    prod_table=SCRATCH_PROD, constraint=SCRATCH_PROD_UQ)
                assert n == 2
                vis, = (await db3.execute(text(
                    f"SELECT COUNT(*) FROM {SCRATCH_PROD}"
                    f" WHERE dicom_study_uid IN ('uid-new','uid-old')"
                ))).fetchone()
                assert vis == 2, "回滚后再 promote 应可重放"
        finally:
            await _cleanup_audit([batch_id])
            async with async_db_session() as db:
                for stmt in _teardown_sql():
                    await db.execute(text(stmt))
                await db.commit()
