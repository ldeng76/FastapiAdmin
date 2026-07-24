"""anon 医疗查询层 — 基于 lnrs_anon_* 表的患者中心查询。

仿 medical_query.py（基于 med_*）的接口，但数据源换成 anon 体系。

字段映射（med_* → anon 风格）：
- gender → sex
- source_center → center_code
- is_deleted 软删除 → deleted_at IS NULL
- demographics + medical_history JSONB 合并 → patient_meta JSONB

详情模态分组简化（anon 体系没有独立 med_* 子表）：
- 原 4 模态（clinical/pathology/genetic/imaging）→ 4 个分类（按 exam_type 区分）
- clinical：visit + surgery
- genetic：exam_type='Genetic' 的 exam + exam_detail
- pathology：exam_type='Pathology'/'IHC' 的 exam + exam_detail + report_text
- imaging：exam_type='CT' 的 exam + exam_detail

注：详情 shape 与旧 med_* 体系不同（前端需配合改造）。本次按"前端配合改"策略，
不强行保持 100% 兼容。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .anon_model import (
    AnonExamDetailModel,
    AnonExamModel,
    AnonPatientModel,
    AnonReportTextModel,
    AnonSurgeryModel,
    AnonVisitModel,
)

# 4 模态分组（与 med_* 一致，方便前端理解）
MODALITIES = ("clinical", "genetic", "pathology", "imaging")

# exam_type → 模态分组
EXAM_TYPE_TO_MODALITY: dict[str, str] = {
    "CT": "imaging",
    "Pathology": "pathology",
    "IHC": "pathology",
    "Genetic": "genetic",
}

# 模态 → 中文标签（前端折叠面板标题）
MODALITY_LABEL: dict[str, str] = {
    "clinical": "临床模态（就诊/手术）",
    "genetic": "基因模态（基因检测）",
    "pathology": "病理模态（病理标本/免疫组化）",
    "imaging": "影像模态（CT 检查）",
}

# AnonPatientModel 业务列（排除审计列 + center_code/anon_id/bmi/created_batch_id 等）
PATIENT_LIST_COLS = [
    AnonPatientModel.patient_id,
    AnonPatientModel.center_code,
    AnonPatientModel.sex,
    AnonPatientModel.birth_date,
    AnonPatientModel.ethnicity,
    AnonPatientModel.native_place,
    AnonPatientModel.abo_blood_type,
    AnonPatientModel.rh_blood_type,
    AnonPatientModel.smoking_status,
    AnonPatientModel.first_nodule_date,
]

# 详情查询列（含 patient_meta JSONB 兜底）
PATIENT_DETAIL_COLS = PATIENT_LIST_COLS + [
    AnonPatientModel.patient_meta,
]


def _row_to_dict(row, cols: list) -> dict[str, Any]:
    """SQLAlchemy Row → 纯 dict（按列 key）。"""
    return {col.key: getattr(row, col.key) for col in cols}


# --------------------------------------------------------------------------- #
# 公共查询
# --------------------------------------------------------------------------- #


async def anon_list_centers(db: AsyncSession) -> list[str]:
    """枚举数据中出现的中心（按 center_code 字段）。"""
    stmt = (
        select(AnonPatientModel.center_code)
        .where(
            AnonPatientModel.center_code.isnot(None),
            AnonPatientModel.deleted_at.is_(None),
        )
        .distinct()
        .order_by(AnonPatientModel.center_code)
    )
    result = await db.execute(stmt)
    return [row[0] for row in result.all()]


async def anon_list_patients(
    db: AsyncSession,
    center: str | None = None,
    keyword: str | None = None,
    offset: int = 0,
    limit: int = 10,
) -> tuple[list[dict[str, Any]], int]:
    """患者分页列表（基于 AnonPatientModel）。返回 (行列表, 总数)。"""
    conditions = [AnonPatientModel.deleted_at.is_(None)]
    if center:
        conditions.append(AnonPatientModel.center_code == center)
    if keyword:
        kw = f"%{keyword}%"
        conditions.append(
            or_(
                AnonPatientModel.patient_id.ilike(kw),
                AnonPatientModel.center_code.ilike(kw),
            )
        )

    # 总数
    count_stmt = (
        select(func.count()).select_from(AnonPatientModel).where(*conditions)
    )
    total = (await db.execute(count_stmt)).scalar_one()

    # 分页
    list_stmt = (
        select(*PATIENT_LIST_COLS)
        .where(*conditions)
        .order_by(AnonPatientModel.center_code, AnonPatientModel.patient_id)
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(list_stmt)).all()
    items = [_row_to_dict(row, PATIENT_LIST_COLS) for row in rows]
    return items, total


async def anon_get_patient_detail(
    db: AsyncSession,
    patient_id: str,
    center: str | None = None,
) -> dict[str, Any]:
    """患者多模态详情（基于 anon 体系 4 表 JOIN：patient + exam + visit + surgery）。

    返回 shape（与 med_* 不同，前端需配合改造）：
        {
            "patient": {patient_id, center_code, sex, birth_date, ethnicity, ...},
            "clinical": [{"anon_visit_id", "visit_ordinal", ...}],  # visit
            "genetic": [{"anon_exam_id", "exam_type", "exam_date", "detail_json"}, ...],
            "pathology": [...],  # exam_type in (Pathology, IHC)
            "imaging": [...],    # exam_type=CT
        }
    """
    # 1) 患者基本信息
    p_conditions = [
        AnonPatientModel.patient_id == patient_id,
        AnonPatientModel.deleted_at.is_(None),
    ]
    if center:
        p_conditions.append(AnonPatientModel.center_code == center)

    p_stmt = select(*PATIENT_DETAIL_COLS).where(*p_conditions)
    p_row = (await db.execute(p_stmt)).first()
    if not p_row:
        return {}

    patient = _row_to_dict(p_row, PATIENT_DETAIL_COLS)

    # 2) 就诊（clinical 模态的一部分）
    visit_stmt = (
        select(AnonVisitModel)
        .where(AnonVisitModel.patient_id == patient_id)
        .order_by(AnonVisitModel.created_at.desc())
    )
    visit_rows = (await db.execute(visit_stmt)).scalars().all()
    clinical_visits = [
        {
            "anon_visit_id": v.anon_visit_id,
            "center_code": v.center_code,
            "visit_ordinal": v.visit_ordinal,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        }
        for v in visit_rows
    ]

    # 3) 手术（clinical 模态的另部分）
    surgery_stmt = (
        select(AnonSurgeryModel)
        .where(AnonSurgeryModel.patient_id == patient_id)
        .order_by(AnonSurgeryModel.surgery_date.desc().nullslast())
    )
    surgery_rows = (await db.execute(surgery_stmt)).scalars().all()
    clinical_surgeries = [
        {
            "surgery_id": s.surgery_id,
            "anon_visit_id": s.anon_visit_id,
            "center_code": s.center_code,
            "surgery_date": s.surgery_date.isoformat() if s.surgery_date else None,
            "procedure_name": s.procedure_name,
            "resection_scope": s.resection_scope,
            "surgical_approach": s.surgical_approach,
            "procedure_detail": s.procedure_detail,
        }
        for s in surgery_rows
    ]

    # 4) 检查 + 报告 + 详情（按 exam_type 分模态）
    exam_stmt = (
        select(AnonExamModel, AnonReportTextModel, AnonExamDetailModel)
        .outerjoin(AnonReportTextModel, AnonReportTextModel.anon_exam_id == AnonExamModel.anon_exam_id)
        .outerjoin(AnonExamDetailModel, AnonExamDetailModel.anon_exam_id == AnonExamModel.anon_exam_id)
        .where(AnonExamModel.patient_id == patient_id)
        .order_by(AnonExamModel.exam_date.desc())
    )
    exam_rows = (await db.execute(exam_stmt)).all()

    modalities: dict[str, list[dict[str, Any]]] = {m: [] for m in MODALITIES}

    for exam, report, detail in exam_rows:
        modality = EXAM_TYPE_TO_MODALITY.get(exam.exam_type or "", "clinical")
        # 临床模态的 exam 也归 clinical
        if modality not in modalities:
            modality = "clinical"
        modalities[modality].append(
            {
                "anon_exam_id": exam.anon_exam_id,
                "exam_type": exam.exam_type,
                "exam_date": exam.exam_date.isoformat() if exam.exam_date else None,
                "anon_visit_id": exam.anon_visit_id,
                "report_text": {
                    "body_clean": report.body_clean if report else None,
                    "pii_replaced_count": report.pii_replaced_count if report else 0,
                    "review_status": report.review_status if report else None,
                } if report else None,
                "detail_json": detail.detail_json if detail else None,
            }
        )

    # clinical 模态 = visits + surgeries
    modalities["clinical"] = clinical_visits + clinical_surgeries + modalities["clinical"]

    return {
        "patient": patient,
        "clinical": modalities["clinical"],
        "genetic": modalities["genetic"],
        "pathology": modalities["pathology"],
        "imaging": modalities["imaging"],
    }
