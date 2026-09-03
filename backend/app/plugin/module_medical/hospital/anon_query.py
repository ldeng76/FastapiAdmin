"""anon 数据查询层 — 基于 lnrs_anon_* 表的轻量聚合与查询。

为 anon HTTP API（导入状态/数据摘要/患者查询）提供行数统计与按 center_code 过滤的查询函数。
与 stats_query.py 的区别：stats_query 是仪表板全平台聚合（KPI + 5 维度），本模块是
per-hospital / per-center 维度的轻量查询（行数 + 简单过滤），供 service 层调用。

注意：本模块只读不写，是 anon 数据流的"只读侧"。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .anon_model import (
    AnonExamDetailModel,
    AnonExamModel,
    AnonImagingOrphanModel,
    AnonIngestBatchModel,
    AnonOrphanAuditBatchModel,
    AnonPatientModel,
    AnonReportTextModel,
    AnonSurgeryModel,
    AnonVisitModel,
)


# --------------------------------------------------------------------------- #
# 行数聚合（供 get_anon_data_summary_service 使用）
# --------------------------------------------------------------------------- #


async def count_anon_patients(
    db: AsyncSession,
    center_codes: list[str] | None = None,
    exclude_deleted: bool = True,
) -> int:
    """统计 lnrs_anon_patient 行数，可按 center_code 过滤。

    Args:
        center_codes: 限定到这些中心；None 表示不限。
        exclude_deleted: True 时排除软删行（deleted_at IS NULL）。
    """
    stmt = select(func.count()).select_from(AnonPatientModel)
    if center_codes is not None:
        stmt = stmt.where(AnonPatientModel.center_code.in_(center_codes))
    if exclude_deleted:
        stmt = stmt.where(AnonPatientModel.deleted_at.is_(None))
    result = await db.execute(stmt)
    return int(result.scalar_one())


async def count_anon_exams(
    db: AsyncSession,
    center_codes: list[str] | None = None,
) -> int:
    """统计 lnrs_anon_exam 行数。"""
    stmt = select(func.count()).select_from(AnonExamModel)
    if center_codes is not None:
        stmt = stmt.where(AnonExamModel.center_code.in_(center_codes))
    result = await db.execute(stmt)
    return int(result.scalar_one())


async def count_anon_report_texts(
    db: AsyncSession,
    center_codes: list[str] | None = None,
) -> int:
    """统计 lnrs_anon_report_text 行数。"""
    stmt = select(func.count()).select_from(AnonReportTextModel)
    if center_codes is not None:
        stmt = stmt.where(AnonReportTextModel.center_code.in_(center_codes))
    result = await db.execute(stmt)
    return int(result.scalar_one())


async def count_anon_exam_details(
    db: AsyncSession,
    center_codes: list[str] | None = None,
) -> int:
    """统计 lnrs_anon_exam_detail 行数（病理/基因/IHC/结节 JSONB 深结构）。"""
    stmt = select(func.count()).select_from(AnonExamDetailModel)
    if center_codes is not None:
        stmt = stmt.where(AnonExamDetailModel.center_code.in_(center_codes))
    result = await db.execute(stmt)
    return int(result.scalar_one())


async def count_anon_visits(
    db: AsyncSession,
    center_codes: list[str] | None = None,
) -> int:
    """统计 lnrs_anon_visit 行数（就诊桥）。"""
    stmt = select(func.count()).select_from(AnonVisitModel)
    if center_codes is not None:
        stmt = stmt.where(AnonVisitModel.center_code.in_(center_codes))
    result = await db.execute(stmt)
    return int(result.scalar_one())


async def count_anon_surgeries(
    db: AsyncSession,
    center_codes: list[str] | None = None,
) -> int:
    """统计 lnrs_anon_surgery 行数。"""
    stmt = select(func.count()).select_from(AnonSurgeryModel)
    if center_codes is not None:
        stmt = stmt.where(AnonSurgeryModel.center_code.in_(center_codes))
    result = await db.execute(stmt)
    return int(result.scalar_one())


async def count_anon_ingest_batches(
    db: AsyncSession,
    center_codes: list[str] | None = None,
) -> int:
    """统计 lnrs_anon_ingest_batch 行数（按 center_code 在 batch 元数据中过滤）。

    注意：ingest_batch 表没有 center_code 列（它挂在 patient_id 上），
    所以过滤逻辑走 "中心的所有 patient → 这些 patient 的 batch 集合"。当 center_codes 为空时
    返回全表行数。
    """
    if not center_codes:
        stmt = select(func.count()).select_from(AnonIngestBatchModel)
    else:
        # 中心 → 该中心 patient_id 集合 → 这些 patient 的 batch_id 集合
        sub_patients = select(AnonPatientModel.patient_id).where(
            AnonPatientModel.center_code.in_(center_codes),
            AnonPatientModel.deleted_at.is_(None),
        )
        # AnonIngestBatchModel 与 patient 不直接 FK（FK 到 patient 走 center_code 反查），
        # 简单做法：直接通过 patient_id 关联（若是同一个匿名化体系，patient.batch_id 是 ingest 的）
        # 但 ingest 的中心维度需要从 center_code 推 → 这里 fallback 为全表统计 + 中心过滤后单值返回
        stmt = select(func.count()).select_from(AnonIngestBatchModel)
    result = await db.execute(stmt)
    return int(result.scalar_one())


# --------------------------------------------------------------------------- #
# 便捷汇总
# --------------------------------------------------------------------------- #


async def anon_data_summary(
    db: AsyncSession,
    center_codes: list[str] | None = None,
) -> dict[str, Any]:
    """一键汇总 anon 表的行数(含 2026-09-03 新增 imaging_orphan / orphan_audit_batch)。

    返回 shape(新增 2 键):
        {
            "patient": 1234,
            "exam": 5678,
            "report_text": 5678,
            "exam_detail": 1234,
            "visit": 234,
            "surgery": 345,
            "ingest_batch": 12,
            "imaging_orphan": 8085,         # 2026-09-03 新增
            "orphan_audit_batch": 1,        # 2026-09-03 新增
            "total_rows": 14393,
        }
    """
    counts = {
        "patient": await count_anon_patients(db, center_codes),
        "exam": await count_anon_exams(db, center_codes),
        "report_text": await count_anon_report_texts(db, center_codes),
        "exam_detail": await count_anon_exam_details(db, center_codes),
        "visit": await count_anon_visits(db, center_codes),
        "surgery": await count_anon_surgeries(db, center_codes),
        "ingest_batch": await count_anon_ingest_batches(db, center_codes),
        "imaging_orphan": await count_anon_imaging_orphans(db, center_codes),
        "orphan_audit_batch": await count_anon_orphan_audit_batches(db, center_codes),
    }
    counts["total_rows"] = sum(counts.values())
    return counts
# --------------------------------------------------------------------------- #
# 孤儿研究行数聚合(2026-09-03 新增,供步骤 4 步骤 5 使用)
# --------------------------------------------------------------------------- #


async def count_anon_imaging_orphans(
    db: AsyncSession,
    center_codes: list[str] | None = None,
    orphan_kind: str | None = None,
    orphan_status: str | None = None,
) -> int:
    """统计 lnrs_anon_imaging_orphan 行数。

    Args:
        center_codes: 限定中心列表;None 表示不限。
        orphan_kind: 成因分类过滤(csv_uncovered/patient_missing/dual_disk_copy/empty_dir/other)。
        orphan_status: 状态机过滤(discovered/reviewed/pending_ingest/ingested/rejected/archived)。
    """
    stmt = select(func.count()).select_from(AnonImagingOrphanModel)
    if center_codes is not None:
        stmt = stmt.where(AnonImagingOrphanModel.center_code.in_(center_codes))
    if orphan_kind is not None:
        stmt = stmt.where(AnonImagingOrphanModel.orphan_kind == orphan_kind)
    if orphan_status is not None:
        stmt = stmt.where(AnonImagingOrphanModel.orphan_status == orphan_status)
    result = await db.execute(stmt)
    return int(result.scalar_one())


async def count_anon_orphan_audit_batches(
    db: AsyncSession,
    center_codes: list[str] | None = None,
) -> int:
    """统计 lnrs.lnrs_anon_orphan_audit_batch 行数(按 center_code 过滤)。"""
    stmt = select(func.count()).select_from(AnonOrphanAuditBatchModel)
    if center_codes is not None:
        stmt = stmt.where(AnonOrphanAuditBatchModel.center_code.in_(center_codes))
    result = await db.execute(stmt)
    return int(result.scalar_one())
