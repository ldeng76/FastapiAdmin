"""4 表 stage 注册表与 promote 驱动（issue-23）。

「先暂存再上」的表级注册表 + FK 顺序 promote。issue-20 只打通
dicom_series；issue-23 把 patient / exam / imaging_study 接入同一套
「写 stage → 校验闸 → 审计 → 幂等 upsert」，并把驱动泛化：

- `STAGE_REGISTRY`：FK 依赖序（patient → exam → imaging_study →
  dicom_series，实测 live pg_constraint）；每张表声明 stage/prod 表、
  幂等键约束、promote 列与 DO UPDATE SET 列。
- `promote_stage_table`：单表 promote（复用 issue-22 的校验闸/审计/明细）。
- `promote_stage_all`：按注册序全量 promote。
- FK 顺序闸：promote 表 T 前检查所有更早的表 —— 若其 stage 中存在
  生产还没有的键（未 promote 的新键），报错拒绝，不静默跳过。

各表 promote 口径（与写入脚本语义一致）：
- patient：占位语义 —— DO UPDATE 只刷 last_seen_batch_id + 复活软删，
  不覆盖人口学（与引擎 _batch_upsert_patients(is_placeholder=True) 一致）。
- exam：DO UPDATE last_seen_batch_id + exam_date（exam_type/patient_id
  保留首值，与 _batch_upsert_exams 一致）。
- imaging_study：issue-13/issue-6 的 stage 行是「prod 现行行拷贝 +
  新 anon_exam_id」，DO UPDATE anon_exam_id / updated_at。
- dicom_series：沿用 issue-20 口径（issue-22 加护栏）。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from etl2.promote_guardrails import (
    PromoteRefused,
    finalize_audit,
    record_audit,
    record_batch_detail,
    validate_stage,
)


@dataclass(frozen=True)
class StageTableSpec:
    """一张表的 stage→promote 声明。"""

    name: str
    stage_table: str
    prod_table: str
    constraint: str          # prod 幂等键 UNIQUE 约束名
    key_column: str          # 业务键（审计明细/回滚定位）
    promote_columns: list[str]
    update_columns: list[str]  # DO UPDATE SET（None = 除键外全部）
    order_note: str = ""


def _cols(*names: str) -> list[str]:
    return list(names)


STAGE_REGISTRY: list[StageTableSpec] = [
    StageTableSpec(
        name="patient",
        stage_table="lnrs.lnrs_stage_patient",
        prod_table="lnrs.lnrs_anon_patient",
        constraint="lnrs_anon_uq_patient_center",
        key_column="patient_id",
        promote_columns=_cols(
            "patient_id", "center_code", "anon_id", "sex", "birth_date",
            "is_placeholder", "ethnicity", "smoking_status", "abo_blood_type",
            "rh_blood_type", "native_place", "first_nodule_date", "bmi",
            "patient_meta", "created_batch_id", "last_seen_batch_id",
            "created_at", "updated_at",
            "deleted_at", "deleted_reason", "deleted_batch_id",
        ),
        # 占位语义：不覆盖人口学/稳定属性，只刷 last_seen + 复活软删
        # （与引擎 _batch_upsert_patients(is_placeholder=True) 一致）
        update_columns=_cols(
            "last_seen_batch_id", "deleted_at", "deleted_reason", "deleted_batch_id",
        ),
        order_note="无父表",
    ),
    StageTableSpec(
        name="exam",
        stage_table="lnrs.lnrs_stage_exam",
        prod_table="lnrs.lnrs_anon_exam",
        constraint="lnrs_anon_uq_exam_source",
        key_column="anon_exam_id",
        promote_columns=_cols(
            "anon_exam_id", "patient_id", "center_code", "exam_type",
            "exam_date", "source_exam_hash", "anon_visit_id",
            "created_batch_id", "last_seen_batch_id", "created_at", "updated_at",
        ),
        # exam_type/patient_id 保留首值（与引擎 _batch_upsert_exams 一致）
        update_columns=_cols("last_seen_batch_id", "exam_date", "updated_at"),
        order_note="patient_id → patient",
    ),
    StageTableSpec(
        name="imaging_study",
        stage_table="lnrs.lnrs_stage_imaging_study",
        prod_table="lnrs.lnrs_anon_imaging_study",
        constraint="lnrs_anon_uq_imaging_study",
        key_column="study_key",
        promote_columns=_cols(
            "study_key", "patient_id", "center_code", "dicom_study_uid",
            "modality", "image_path", "sop_count", "source", "anon_exam_id",
            "created_batch_id", "created_at", "updated_at",
        ),
        # stage 行是「prod 现行行拷贝 + 新 anon_exam_id」，只需刷回填列
        update_columns=_cols("anon_exam_id", "updated_at"),
        order_note="patient_id → patient",
    ),
    StageTableSpec(
        name="dicom_series",
        stage_table="lnrs.lnrs_stage_dicom_series",
        prod_table="lnrs.lnrs_anon_dicom_series",
        constraint="lnrs_anon_dicom_series_dicom_study_uid_key",
        key_column="dicom_study_uid",
        # series_id（PK）不参与 promote：新行由生产表 sequence 现场分配
        # （issue-20），stage 行拷贝自 prod 时 series_id 与现值一致，无碍
        promote_columns=_cols(
            "anon_exam_id", "dicom_study_uid", "file_count", "byte_size",
            "series_count", "created_batch_id", "created_at", "updated_at",
        ),
        update_columns=_cols(
            "anon_exam_id", "file_count", "byte_size", "series_count", "updated_at",
        ),
        order_note="anon_exam_id → exam, created_batch_id → ingest_batch",
    ),
]

REGISTRY_BY_NAME = {s.name: s for s in STAGE_REGISTRY}


async def _unpromoted_key_count(db: AsyncSession, spec: StageTableSpec) -> int:
    """stage 中生产还没有的键数（= 未 promote 的新键）。"""
    r = await db.execute(text(f"""
        SELECT COUNT(*) FROM {spec.stage_table} s
        WHERE NOT EXISTS (
          SELECT 1 FROM {spec.prod_table} p
          WHERE p.{spec.key_column} = s.{spec.key_column}
        )
    """))
    return int(r.scalar() or 0)


async def assert_fk_order(
    db: AsyncSession,
    spec: StageTableSpec,
    registry: list[StageTableSpec] | None = None,
) -> None:
    """FK 顺序闸：promote spec 前，更早的表不得还有未 promote 的新键。

    只看「新键」而非「stage 非空」——promote 不清 stage（幂等重放是
    特性），已 promote 过的旧键不构成顺序违反。
    registry：默认生产注册表；测试可注入 scratch 副本（同名同序）。
    """
    reg = registry if registry is not None else STAGE_REGISTRY
    idx = next(i for i, s in enumerate(reg) if s.name == spec.name)
    for earlier in reg[:idx]:
        n = await _unpromoted_key_count(db, earlier)
        if n:
            raise PromoteRefused([
                f"FK 顺序违反: {earlier.name} stage 尚有 {n} 个未 promote 的新键，"
                f"必须先 promote {earlier.name} 再 promote {spec.name}"
                f"（依赖: {earlier.order_note}）"
            ])


async def promote_stage_table(
    db: AsyncSession,
    spec: StageTableSpec,
    *,
    mode: str = "apply",
    check_order: bool = True,
    registry: list[StageTableSpec] | None = None,
) -> tuple[int, str]:
    """单表带护栏 promote（issue-22 闸/审计 + issue-23 顺序闸）。

    返回 (upsert 行数, batch_id)。check_order=False 供 dicom_series 单表
    命令（issue-20/22 语义：不检查其它表）与 scratch 注入测试使用。
    """
    from app.plugin.module_medical.hospital.anon_pg_copy import copy_then_merge

    batch_id = uuid.uuid4()
    if check_order:
        await assert_fk_order(db, spec, registry=registry)

    rows = (await db.execute(
        text(f"SELECT {', '.join(spec.promote_columns)} FROM {spec.stage_table}")
    )).mappings().all()
    n_stage = int((await db.execute(
        text(f"SELECT COUNT(*) FROM {spec.stage_table}")
    )).scalar() or 0)

    violations = await validate_stage(
        db, stage_table=spec.stage_table, prod_table=spec.prod_table,
        promote_columns=spec.promote_columns)
    if violations:
        audit_id = await record_audit(
            db, batch_id=batch_id, target_table=spec.prod_table, mode=mode,
            stage_rows=n_stage, validation="rejected", violations=violations)
        await db.commit()
        raise PromoteRefused(violations)

    audit_id = await record_audit(
        db, batch_id=batch_id, target_table=spec.prod_table, mode=mode,
        stage_rows=n_stage, validation="passed",
        upsert_rows=len(rows) if mode == "apply" else 0)
    if mode == "dry_run":
        await db.commit()
        return 0, str(batch_id)

    await record_batch_detail(
        db, audit_id=audit_id, stage_table=spec.stage_table,
        prod_table=spec.prod_table, key_column=spec.key_column)
    n = await copy_then_merge(
        db,
        target_table_name=spec.prod_table,
        rows=[dict(r) for r in rows],
        constraint=spec.constraint,
        update_set=dict.fromkeys(spec.update_columns, 1),
        column_order=spec.promote_columns,
    )
    await finalize_audit(db, audit_id=audit_id, upsert_rows=n)
    await db.commit()
    return n, str(batch_id)




async def promote_stage_all(
    db: AsyncSession,
    *,
    names: list[str] | None = None,
    mode: str = "apply",
    registry: list[StageTableSpec] | None = None,
) -> list[tuple[str, int, str]]:
    """按 FK 序 promote（默认全部 4 张）。返回 [(name, n, batch_id), ...]。

    registry：默认生产注册表；测试可注入 scratch 副本（同名同序）。
    """
    reg = registry if registry is not None else STAGE_REGISTRY
    order = [s.name for s in reg]
    by_name = {s.name: s for s in reg}
    targets = names or order
    unknown = [n for n in targets if n not in by_name]
    if unknown:
        raise PromoteRefused([f"未知表名: {unknown}（可选: {order}）"])
    # 显式名单也要按注册序执行，防调用方乱序
    targets = [n for n in order if n in set(targets)]
    results = []
    for name in targets:
        n, bid = await promote_stage_table(
            db, by_name[name], mode=mode, registry=reg)
        results.append((name, n, bid))
    return results
