"""issue-23：多表 stage promote 驱动测试（FK 顺序 / 幂等 / 完整性）。

验证（docs/etl2/prd/issue-23-remaining-tables-and-scripts.md AC）：
1. FK 顺序闸：promote 某表时更早的表还有未 promote 的新键 → 报错拒绝
2. 按序 promote patient → exam → imaging_study：可见性、幂等、完整性
3. 引擎 stage_mode：exam/patient 写 stage，生产零变化

scratch 克隆表验证，不写生产数据行（2026-09-20 事故教训）。
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "etl2"))


@pytest.fixture(autouse=True)
def _dispose_engine_per_loop():
    yield
    from app.core.database import async_engine

    asyncio.run(async_engine.dispose())


from _db_guard import PG_READY, SKIP_REASON  # noqa: E402
from stage_promote import (  # noqa: E402
    STAGE_REGISTRY,
    StageTableSpec,
    assert_fk_order,
    promote_stage_all,
    promote_stage_table,
)

# scratch 表（按注册表 3 表的形状克隆；dicom_series 已有 issue-20/22 用例）
S_PAT = "lnrs.lnrs_scratch_i23_patient"
S_EXA = "lnrs.lnrs_scratch_i23_exam"
S_STU = "lnrs.lnrs_scratch_i23_study"
P_PAT = "lnrs.lnrs_scratch_i23_patient_prod"
P_EXA = "lnrs.lnrs_scratch_i23_exam_prod"
P_STU = "lnrs.lnrs_scratch_i23_study_prod"
BATCH = str(uuid.uuid4())

_NAMES = ("patient", "exam", "imaging_study")
_TABLE_MAP = {
    "lnrs.lnrs_stage_patient": S_PAT, "lnrs.lnrs_anon_patient": P_PAT,
    "lnrs.lnrs_stage_exam": S_EXA, "lnrs.lnrs_anon_exam": P_EXA,
    "lnrs.lnrs_stage_imaging_study": S_STU, "lnrs.lnrs_anon_imaging_study": P_STU,
}


_CONSTRAINT_MAP = {
    "patient": "scr_i23_patp_uq",
    "exam": "scr_i23_exap_uq",
    "imaging_study": "scr_i23_stup_uq",
}


def _spec(name: str) -> StageTableSpec:
    """scratch 注入的注册表副本（表名/约束名替换，口径同生产 spec）。"""
    base = {s.name: s for s in STAGE_REGISTRY}[name]
    return StageTableSpec(
        name=base.name, stage_table=_TABLE_MAP[base.stage_table],
        prod_table=_TABLE_MAP[base.prod_table],
        # scratch 约束名与生产不同，promote 的 ON CONFLICT 用 scratch 名
        constraint=_CONSTRAINT_MAP[name], key_column=base.key_column,
        promote_columns=base.promote_columns, update_columns=base.update_columns,
        order_note=base.order_note,
    )


SCRATCH_SPECS = {n: _spec(n) for n in _NAMES}


def _setup_sql() -> list[str]:
    tables = (S_PAT, S_EXA, S_STU, P_PAT, P_EXA, P_STU)
    stmts = [f"DROP TABLE IF EXISTS {t}" for t in tables]
    shape = [
        (S_PAT, "lnrs.lnrs_anon_patient",
         "scr_i23_pat_uq UNIQUE (center_code, anon_id)"),
        (S_EXA, "lnrs.lnrs_anon_exam",
         "scr_i23_exa_uq UNIQUE (center_code, source_exam_hash)"),
        (S_STU, "lnrs.lnrs_anon_imaging_study",
         "scr_i23_stu_uq UNIQUE (patient_id, dicom_study_uid, source)"),
        (P_PAT, "lnrs.lnrs_anon_patient",
         "scr_i23_patp_uq UNIQUE (center_code, anon_id)"),
        (P_EXA, "lnrs.lnrs_anon_exam",
         "scr_i23_exap_uq UNIQUE (center_code, source_exam_hash)"),
        (P_STU, "lnrs.lnrs_anon_imaging_study",
         "scr_i23_stup_uq UNIQUE (patient_id, dicom_study_uid, source)"),
    ]
    for tbl, like, uq in shape:
        stmts.append(f"CREATE TABLE {tbl} (LIKE {like} INCLUDING DEFAULTS)")
        stmts.append(f"ALTER TABLE {tbl} ADD CONSTRAINT {uq}")
    return stmts


TEARDOWN = [f"DROP TABLE IF EXISTS {t}" for t in
            (S_PAT, S_EXA, S_STU, P_PAT, P_EXA, P_STU)]


async def _counts(db) -> dict[str, int]:
    from sqlalchemy import text
    out = {}
    for label, t in (("pat", P_PAT), ("exa", P_EXA), ("stu", P_STU)):
        out[label] = int((await db.execute(
            text(f"SELECT COUNT(*) FROM {t}"))).scalar() or 0)
    return out


@pytest.mark.skipif(not PG_READY, reason=SKIP_REASON)
class TestStagePromoteAll:
    def test_fk_order_gate_refuses(self):
        """exam stage 有未 promote 新键时，promote imaging_study 被拒。"""
        asyncio.run(self._body_order())

    @staticmethod
    async def _body_order():
        from sqlalchemy import text

        from app.core.database import async_db_session
        from etl2.promote_guardrails import PromoteRefused

        async with async_db_session() as db:
            for stmt in _setup_sql():
                await db.execute(text(stmt))
            await db.commit()
            try:
                # exam stage 一行新键，生产 exam 无此键
                await db.execute(text(f"""
                    INSERT INTO {S_EXA}
                      (anon_exam_id, patient_id, center_code, exam_type,
                       exam_date, source_exam_hash, created_batch_id,
                       last_seen_batch_id)
                    VALUES ('EX_1', 'PT_X', 'c1', 'CT', '2026-01-01', 'h1',
                            '{BATCH}', '{BATCH}')
                """))
                await db.commit()
                with pytest.raises(PromoteRefused, match="FK 顺序违反"):
                    await assert_fk_order(
                        db, SCRATCH_SPECS["imaging_study"],
                        registry=list(SCRATCH_SPECS.values()))
            finally:
                for stmt in TEARDOWN:
                    await db.execute(text(stmt))
                await db.commit()

    def test_promote_in_order_visibility_idempotent(self):
        """按序 promote：可见 → 幂等重放 → 完整性（孤儿 = 0）。"""
        asyncio.run(self._body_promote())

    @staticmethod
    async def _body_promote():
        from sqlalchemy import text

        from app.core.database import async_db_session
        from etl2.promote_guardrails import PromoteRefused

        async with async_db_session() as db:
            for stmt in _setup_sql():
                await db.execute(text(stmt))
            try:
                # stage 数据：patient 1 + exam 1（引用该 patient）+ study 1（同）
                await db.execute(text(f"""
                    INSERT INTO {S_PAT}
                      (patient_id, anon_id, center_code, sex, is_placeholder,
                       created_batch_id, last_seen_batch_id)
                    VALUES ('PT_1', 'AN_1', 'c1', '0', TRUE, '{BATCH}', '{BATCH}')
                """))
                await db.execute(text(f"""
                    INSERT INTO {S_EXA}
                      (anon_exam_id, patient_id, center_code, exam_type,
                       exam_date, source_exam_hash, created_batch_id, last_seen_batch_id)
                    VALUES ('EX_1', 'PT_1', 'c1', 'CT', '2026-01-01', 'h1', '{BATCH}', '{BATCH}')
                """))
                await db.execute(text(f"""
                    INSERT INTO {S_STU}
                      (study_key, patient_id, center_code, dicom_study_uid,
                       modality, image_path, sop_count, source, anon_exam_id,
                       created_batch_id)
                    VALUES (9001, 'PT_1', 'c1', 'UID_1', 'CT', '/x', 3,
                            'ct_backfill', 'EX_1', '{BATCH}')
                """))
                await db.commit()

                # 乱序保护：promote imaging_study 前须先 promote patient/exam
                # （scratch registry 上仍有未 promote 新键 → 顺序闸拒绝）
                with pytest.raises(PromoteRefused):
                    await promote_stage_table(
                        db, SCRATCH_SPECS["imaging_study"],
                        registry=list(SCRATCH_SPECS.values()))

                # 按序 promote
                r = await promote_stage_all(
                    db, names=["patient", "exam", "imaging_study"],
                    registry=list(SCRATCH_SPECS.values()))
                assert [n for n, _, _ in r] == ["patient", "exam", "imaging_study"]

                # 可见性
                rows = (await db.execute(text(
                    f"SELECT patient_id, sex, is_placeholder FROM {P_PAT}"
                ))).fetchall()
                assert rows == [("PT_1", "0", True)]
                exam = (await db.execute(text(
                    f"SELECT anon_exam_id, patient_id, exam_type FROM {P_EXA}"
                ))).fetchone()
                assert tuple(exam) == ("EX_1", "PT_1", "CT")
                stu = (await db.execute(text(
                    f"SELECT study_key, anon_exam_id FROM {P_STU}"
                ))).fetchone()
                assert tuple(stu) == (9001, "EX_1")

                # 幂等：重放一次，行数不变
                before = await _counts(db)
                await promote_stage_all(
                    db, names=["patient", "exam", "imaging_study"],
                    registry=list(SCRATCH_SPECS.values()))
                assert await _counts(db) == before

                # 完整性（AC 孤儿引用口径）：study.patient_id 全部可解析
                orphan = (await db.execute(text(f"""
                    SELECT COUNT(*) FROM {P_STU} s
                    WHERE NOT EXISTS (
                      SELECT 1 FROM {P_PAT} p WHERE p.patient_id = s.patient_id)
                """))).scalar()
                assert orphan == 0
            finally:
                for stmt in TEARDOWN:
                    await db.execute(text(stmt))
                await db.commit()

    def test_engine_stage_mode_writes_stage_only(self):
        """引擎 stage_mode：patient/exam 进真实 stage 表，生产零变化。

        用真实 stage 表（沙箱允许写、TRUNCATE 安全），使引擎硬编码的
        stage 约束名（迁移 p6q7r8s9t0u1）原样生效。
        """
        asyncio.run(self._body_engine())

    @staticmethod
    async def _body_engine():
        from sqlalchemy import text

        from app.core.database import async_db_session
        from app.plugin.module_medical.hospital.anon_etl_engine import (
            _batch_upsert_exams,
            _batch_upsert_patients,
        )

        STAGE_PAT = "lnrs.lnrs_stage_patient"
        STAGE_EXA = "lnrs.lnrs_stage_exam"

        async def _prod_snapshot(db):
            out = {}
            for label, t in (("patient", "lnrs.lnrs_anon_patient"),
                             ("exam", "lnrs.lnrs_anon_exam")):
                cnt, = (await db.execute(
                    text(f"SELECT COUNT(*) FROM {t}"))).fetchone()
                ins, = (await db.execute(text("""
                    SELECT n_tup_ins FROM pg_stat_user_tables
                    WHERE relid = to_regclass(:t)
                """), {"t": t})).fetchone()
                out[label] = (int(cnt), int(ins))
            return out

        async with async_db_session() as db:
            # 清空 stage 起点（stage 可安全 TRUNCATE，issue-20 AC）
            await db.execute(text(f"TRUNCATE {STAGE_PAT}"))
            await db.execute(text(f"TRUNCATE {STAGE_EXA}"))
            await db.commit()
            before = await _prod_snapshot(db)
            try:
                pid_map = await _batch_upsert_patients(
                    db, center_code="zz_test",
                    patient_records=[{"local_id": "p1", "anon_id": "AN_I23_1",
                                      "sex": "0", "birth_date": None}],
                    batch_id=BATCH, is_placeholder=True,
                    target_table=STAGE_PAT,
                )
                await db.commit()
                assert set(pid_map) == {"AN_I23_1"}
                await _batch_upsert_exams(
                    db,
                    exam_rows=[{"anon_exam_id": "EX_I23_1",
                                "patient_id": pid_map["AN_I23_1"],
                                "center_code": "zz_test", "exam_type": "CT",
                                "exam_date": date(2026, 1, 1),
                                "source_exam_hash": "h_i23_1",
                                "created_batch_id": BATCH,
                                "last_seen_batch_id": BATCH}],
                    target_table=STAGE_EXA,
                )
                await db.commit()
                after = await _prod_snapshot(db)
                assert before == after, f"生产零变化被破坏: {before} → {after}"
                n_pat = (await db.execute(
                    text(f"SELECT COUNT(*) FROM {STAGE_PAT}"))).scalar()
                n_exa = (await db.execute(
                    text(f"SELECT COUNT(*) FROM {STAGE_EXA}"))).scalar()
                assert n_pat >= 1 and n_exa >= 1
            finally:
                # 清理本测试写入的 stage 行（按 batch_id 定位）
                await db.execute(text(
                    f"DELETE FROM {STAGE_PAT} WHERE created_batch_id = :b"
                ), {"b": BATCH})
                await db.execute(text(
                    f"DELETE FROM {STAGE_EXA} WHERE created_batch_id = :b"
                ), {"b": BATCH})
                await db.commit()
