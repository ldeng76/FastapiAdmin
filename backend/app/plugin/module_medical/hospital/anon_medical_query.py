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

import logging
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .anon_model import (
    AnonExamDetailModel,
    AnonExamModel,
    AnonLabResultModel,
    AnonOrderModel,
    AnonPatientModel,
    AnonReportTextModel,
    AnonSurgeryModel,
    AnonVisitDetailModel,
    AnonVisitModel,
)

log = logging.getLogger(__name__)


def _flatten_jsonb(row: dict[str, Any], jsonb_key: str) -> dict[str, Any]:
    """把 row[jsonb_key] 这个 JSONB dict 顶层展开到 row 自身。

    冲突策略：JSONB 子键覆盖现有顶层 key（设计意图：visit 全部字段都在
    visit_detail_json 里，ORM 仅保留 anon_visit_id/visit_ordinal 等桥列）。
    """
    blob = row.pop(jsonb_key, None)
    if not blob or not isinstance(blob, dict):
        return row
    for k, v in blob.items():
        row[k] = v
    return row


def _tag_row(row: dict[str, Any], table_label: str, modality: str) -> dict[str, Any]:
    """为前端折叠面板打分组标签。"""
    row["_table"] = table_label
    row["_modality"] = modality
    return row

# 4 模态分组（与 med_* 一致，方便前端理解）
MODALITIES = ("clinical", "genetic", "pathology", "imaging")

# exam_type → 模态分组
# 数据来源：lnrs_anon_exam.exam_type 列（ETL-2 写入，已规整为英文枚举）
# 珠江用 CT/Pathology/Genetic；省医用 Radiology/Ultrasound（也归影像类）
EXAM_TYPE_TO_MODALITY: dict[str, str] = {
    "CT": "imaging",
    "Radiology": "imaging",
    "Ultrasound": "imaging",
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
    """患者多模态详情（基于 anon 体系 8 表 JOIN）。

    返回 shape:
        {
            "patient":   {基本字段, patient_meta JSONB 已顶层展开},
            "clinical":  [就诊行(_table=就诊), 手术行(_table=手术),
                          检验结果行(_table=检验结果), 医嘱行(_table=医嘱),
                          未映射 exam 类型的 exam 行(_table=exam_type 检查)],
            "genetic":   [exam 行],
            "pathology": [exam 行],
            "imaging":   [exam 行],
        }

    每行：异构字段直平铺到顶层；JSONB 字段 (visit_detail_json / lab_detail_json /
    order_detail_json / patient_meta / detail_json) 已就地顶层展开，键冲突时
    保留原列、丢弃 JSONB 同名键（WARNING 日志）。

    已知限制：
    - AnonLabResultModel / AnonOrderModel / AnonVisitDetailModel 仅省医 schema
      (0010-shengyi-anon-tables.sql) 建表；缺失时本函数 try/except 跳过。
    - exam_detail 多行（多结节）按 detail_ordinal 拆成 N 个顶层行，
      每行的 detail_type 作为 _table 后缀（如 "CT 检查(结节)"）。
    """
    # 1) 患者基本信息（patient_meta JSONB 顶层展开）
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

    patient = _flatten_jsonb(
        _row_to_dict(p_row, PATIENT_DETAIL_COLS), "patient_meta"
    )

    modalities: dict[str, list[dict[str, Any]]] = {m: [] for m in MODALITIES}

    # 2) 就诊（JOIN visit_detail 富信息；visit_detail_json 顶层展开，
    #    不 select ORM 列 visit_category/admission_time 等避免与 JSONB 子键冲突）
    try:
        visit_stmt = (
            select(
                AnonVisitModel.anon_visit_id,
                AnonVisitModel.visit_ordinal,
                AnonVisitModel.center_code,
                AnonVisitModel.created_at,
                AnonVisitDetailModel.visit_detail_json,
            )
            .outerjoin(
                AnonVisitDetailModel,
                AnonVisitDetailModel.anon_visit_id == AnonVisitModel.anon_visit_id,
            )
            .where(AnonVisitModel.patient_id == patient_id)
            .order_by(AnonVisitModel.created_at.desc())
        )
        for row in (await db.execute(visit_stmt)).mappings():
            d = _flatten_jsonb(dict(row), "visit_detail_json")
            for k in ("created_at", "admission_time", "discharge_date"):
                if hasattr(d.get(k), "isoformat"):
                    d[k] = d[k].isoformat()
            modalities["clinical"].append(_tag_row(d, "就诊", "clinical"))
    except Exception:
        # 缺表（省医 schema 未建）时跳过
        log.warning("就诊查询失败（可能 AnonVisitDetailModel 未建表）", exc_info=True)

    # 3) 手术
    surgery_stmt = (
        select(
            AnonSurgeryModel.surgery_id,
            AnonSurgeryModel.anon_visit_id,
            AnonSurgeryModel.center_code,
            AnonSurgeryModel.surgery_date,
            AnonSurgeryModel.procedure_name,
            AnonSurgeryModel.resection_scope,
            AnonSurgeryModel.surgical_approach,
            AnonSurgeryModel.procedure_detail,
        )
        .where(AnonSurgeryModel.patient_id == patient_id)
        .order_by(AnonSurgeryModel.surgery_date.desc().nullslast())
    )
    for row in (await db.execute(surgery_stmt)).mappings():
        d = dict(row)
        if hasattr(d.get("surgery_date"), "isoformat"):
            d["surgery_date"] = d["surgery_date"].isoformat()
        modalities["clinical"].append(_tag_row(d, "手术", "clinical"))

    # 4) 检验结果（省医扩展表，可缺）
    try:
        lab_stmt = (
            select(
                AnonLabResultModel.lab_result_id,
                AnonLabResultModel.anon_visit_id,
                AnonLabResultModel.center_code,
                AnonLabResultModel.report_id,
                AnonLabResultModel.test_name,
                AnonLabResultModel.item_name,
                AnonLabResultModel.item_result,
                AnonLabResultModel.item_result_value,
                AnonLabResultModel.item_unit,
                AnonLabResultModel.collection_time,
                AnonLabResultModel.lab_detail_json,
            )
            .where(AnonLabResultModel.patient_id == patient_id)
            .order_by(AnonLabResultModel.collection_time.desc().nullslast())
        )
        for row in (await db.execute(lab_stmt)).mappings():
            d = _flatten_jsonb(dict(row), "lab_detail_json")
            if hasattr(d.get("collection_time"), "isoformat"):
                d["collection_time"] = d["collection_time"].isoformat()
            modalities["clinical"].append(_tag_row(d, "检验结果", "clinical"))
    except Exception:
        log.warning("检验查询失败（可能 AnonLabResultModel 未建表）", exc_info=True)

    # 5) 医嘱（省医扩展表，可缺）
    try:
        order_stmt = (
            select(
                AnonOrderModel.order_id,
                AnonOrderModel.anon_visit_id,
                AnonOrderModel.center_code,
                AnonOrderModel.order_type,
                AnonOrderModel.order_name,
                AnonOrderModel.order_time,
                AnonOrderModel.order_source,
                AnonOrderModel.order_detail_json,
            )
            .where(AnonOrderModel.patient_id == patient_id)
            .order_by(AnonOrderModel.order_time.desc().nullslast())
        )
        for row in (await db.execute(order_stmt)).mappings():
            d = _flatten_jsonb(dict(row), "order_detail_json")
            if hasattr(d.get("order_time"), "isoformat"):
                d["order_time"] = d["order_time"].isoformat()
            modalities["clinical"].append(_tag_row(d, "医嘱", "clinical"))
    except Exception:
        log.warning("医嘱查询失败（可能 AnonOrderModel 未建表）", exc_info=True)

    # 6) 检查 + 报告 + 详情（按 exam_type 分模态）
    exam_stmt = (
        select(
            AnonExamModel.anon_exam_id,
            AnonExamModel.center_code,
            AnonExamModel.exam_type,
            AnonExamModel.exam_date,
            AnonExamModel.anon_visit_id,
            AnonReportTextModel.body_clean,
            AnonReportTextModel.pii_replaced_count,
            AnonReportTextModel.review_status,
        )
        .outerjoin(
            AnonReportTextModel,
            AnonReportTextModel.anon_exam_id == AnonExamModel.anon_exam_id,
        )
        .where(AnonExamModel.patient_id == patient_id)
        .order_by(AnonExamModel.exam_date.desc())
    )
    exam_rows = (await db.execute(exam_stmt)).mappings().all()

    # 6.1) exam_detail 多行子查询（避免笛卡尔积把 report_text 重复）
    exam_ids = [r["anon_exam_id"] for r in exam_rows]
    detail_by_exam: dict[str, list[AnonExamDetailModel]] = {eid: [] for eid in exam_ids}
    if exam_ids:
        detail_stmt = (
            select(AnonExamDetailModel)
            .where(AnonExamDetailModel.anon_exam_id.in_(exam_ids))
            .order_by(
                AnonExamDetailModel.anon_exam_id,
                AnonExamDetailModel.detail_type,
                AnonExamDetailModel.detail_ordinal,
            )
        )
        for d_obj in (await db.execute(detail_stmt)).scalars().all():
            detail_by_exam.setdefault(d_obj.anon_exam_id, []).append(d_obj)

    for row in exam_rows:
        modality = EXAM_TYPE_TO_MODALITY.get(row["exam_type"] or "", "clinical")
        if modality not in modalities:
            modality = "clinical"
        exam_date = row["exam_date"]
        base = {
            "anon_exam_id": row["anon_exam_id"],
            "center_code": row["center_code"],
            "exam_type": row["exam_type"],
            "exam_date": exam_date.isoformat() if hasattr(exam_date, "isoformat") else exam_date,
            "anon_visit_id": row["anon_visit_id"],
            "report_text": {
                "body_clean": row["body_clean"],
                "pii_replaced_count": row["pii_replaced_count"] or 0,
                "review_status": row["review_status"],
            },
        }
        details = detail_by_exam.get(row["anon_exam_id"], [])
        if not details:
            modalities[modality].append(
                _tag_row(base, f"{row['exam_type'] or '检查'} 检查", modality)
            )
        else:
            # 每个 detail 行各出一行；多结节场景 detail_type='结节'，每行 n1/n2/n3
            for det in details:
                merged = {
                    **base,
                    "detail_type": det.detail_type,
                    "detail_ordinal": det.detail_ordinal,
                    "detail_json": det.detail_json,
                }
                merged = _flatten_jsonb(merged, "detail_json")
                tbl = (
                    f"{det.detail_type} #{det.detail_ordinal}"
                    if det.detail_ordinal and det.detail_ordinal > 1
                    else det.detail_type
                )
                modalities[modality].append(_tag_row(merged, tbl, modality))

    return {
        "patient": patient,
        "clinical": modalities["clinical"],
        "genetic": modalities["genetic"],
        "pathology": modalities["pathology"],
        "imaging": modalities["imaging"],
    }
