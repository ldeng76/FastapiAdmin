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

from sqlalchemy import Date, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .anon_model import (
    AnonExamDetailModel,
    AnonExamModel,
    AnonImagingOrphanModel,
    AnonImagingStudyModel,
    AnonLabResultModel,
    AnonOrderModel,
    AnonOrphanAuditBatchModel,
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
MODALITIES = ("clinical","surgery", "ihc","ultrasound","radiology","collection","order","other","genetic", "pathology", "ct")
# Other
# exam_type → 模态分组
# 数据来源：lnrs_anon_exam.exam_type 列（ETL-2 写入，已规整为英文枚举）
# 珠江用 CT/Pathology/Genetic；省医用 Radiology/Ultrasound（也归影像类）
EXAM_TYPE_TO_MODALITY: dict[str, str] = {
    "CT": "ct",
    "Radiology": "radiology",
    "Ultrasound": "ultrasound",
    "Pathology": "pathology",
    "IHC": "ihc",
    "Other" : "other",
    "Genetic": "genetic",
}

# 模态 → 中文标签（前端折叠面板标题）
MODALITY_LABEL: dict[str, str] = {
    "clinical": "临床模态（就诊）",
    "surgery": "临床模态（手术）",
    "genetic": "基因模态（基因检测）",
    "collection": "检验结果",
    "order": "医嘱",
    "pathology": "病理模态（病理标本/免疫组化）",
    "ct": "影像模态（CT 检查）",
}

# AnonPatientModel 业务列（排除审计列 + center_code/anon_id/bmi/created_batch_id 等）
PATIENT_LIST_COLS = [
    AnonPatientModel.patient_id,
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
    keyword: str | None = None,
    sex: str | None = None,
    smoking_status: str | None = None,
    offset: int = 0,
    limit: int = 10,
) -> tuple[list[dict[str, Any]], int]:
    """患者分页列表（基于 AnonPatientModel）。返回 (行列表, 总数)。"""
    conditions = [AnonPatientModel.deleted_at.is_(None)]
    if sex:
        conditions.append(AnonPatientModel.sex == sex)
    if smoking_status:
        conditions.append(AnonPatientModel.smoking_status == smoking_status)
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
            "ct":   [exam 行],
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
                AnonVisitModel.created_at,
                AnonVisitDetailModel.visit_detail_json,
            )
            .outerjoin(
                AnonVisitDetailModel,
                AnonVisitDetailModel.anon_visit_id == AnonVisitModel.anon_visit_id,
            )
            .where(AnonVisitModel.patient_id == patient_id)
            .order_by(
                cast(
                    AnonVisitDetailModel.visit_detail_json.op("->>")("admission_time"),
                    Date,
                )
                .desc()
                .nullslast(),
                AnonVisitModel.created_at.desc(),
            )
        )
        for row in (await db.execute(visit_stmt)).mappings():
            d = _flatten_jsonb(dict(row), "visit_detail_json")
            for k in ("created_at", "admission_time", "discharge_date"):
                if hasattr(d.get(k), "isoformat"):
                    d[k] = d[k].isoformat()
            modalities["clinical"].append(_tag_row(d, "就诊", "clinical"))
    except Exception:
        # 缺表（省医 schema 未建）时跳过；嵌套事务回滚以解除整事务 aborted 状态
        log.warning("就诊查询失败（可能 AnonVisitDetailModel 未建表）", exc_info=True)
        try:
            await db.rollback()
        except Exception:
            pass

    # 3) 手术
    surgery_stmt = (
        select(
            AnonSurgeryModel.surgery_id,
            AnonSurgeryModel.anon_visit_id,
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
        modalities["surgery"].append(_tag_row(d, "手术", "clinical"))

    # 4) 检验结果（省医扩展表，可缺）
    try:
        lab_stmt = (
            select(
                AnonLabResultModel.lab_result_id,
                AnonLabResultModel.anon_visit_id,
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
            modalities["collection"].append(_tag_row(d, "检验结果", "clinical"))
    except Exception:
        log.warning("检验查询失败（可能 AnonLabResultModel 未建表）", exc_info=True)
        try:
            await db.rollback()
        except Exception:
            pass

    # 5) 医嘱（省医扩展表，可缺）
    try:
        order_stmt = (
            select(
                AnonOrderModel.order_id,
                AnonOrderModel.anon_visit_id,
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
            modalities["order"].append(_tag_row(d, "医嘱", "clinical"))
    except Exception:
        log.warning("医嘱查询失败（可能 AnonOrderModel 未建表）", exc_info=True)
        try:
            await db.rollback()
        except Exception:
            pass

    # 6) 检查 + 报告 + 详情（按 exam_type 分模态）
    exam_stmt = (
        select(
            AnonExamModel.anon_exam_id,
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
        modality = EXAM_TYPE_TO_MODALITY.get(row["exam_type"] or "", "other")
        if modality not in modalities:
            modality = "other"

        exam_date = row["exam_date"]
        base = {
            "anon_exam_id": row["anon_exam_id"],
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
                modal_key = tbl if tbl in modalities else modality
                modalities[modal_key].append(_tag_row(merged, tbl, modality))
    return {
        "patient": patient,
        "modal_data":modalities,
    }

# --------------------------------------------------------------------------- #
# 影像研究桥接查询（2026-08-28 新增）
# --------------------------------------------------------------------------- #


# 列出 SQL 列：与前端 DicomStudy 类型对齐
IMAGING_STUDY_LIST_COLS = [
    AnonImagingStudyModel.study_key,
    AnonImagingStudyModel.dicom_study_uid.label("study_uid"),
    AnonImagingStudyModel.modality,
    AnonImagingStudyModel.image_path,
    AnonImagingStudyModel.sop_count,
    AnonImagingStudyModel.source,
    AnonImagingStudyModel.anon_exam_id,
    AnonImagingStudyModel.created_at,
]


async def anon_list_patient_imaging_studies(
    db: AsyncSession,
    patient_id: str,
    center: str | None = None,
    modality: str | None = None,
) -> list[dict[str, Any]]:
    """列出某患者的所有影像研究（study-level）。

    用途：前端"患者详情 → 查看影像"按钮拿到 study 列表，传给
    DicomViewer（cornerstone3D）拉 series/instances。

    返回字段（与前端 DicomStudy 兼容）：
      - study_id      = dicom_study_uid （DicomViewer props.studyId 期望）
      - study_uid     = dicom_study_uid （冗余，便于诊断）
      - modality      = 'CT' / 'Pathology' / ...
      - image_path    = 磁盘上 Study 根目录绝对路径
      - sop_count     = 该 Study 下影像切片数（仅展示）
      - source        = 数据来源盘标识
      - anon_exam_id  = 冗余 FK（ETL-2 回写时有值，离线灌库为空）
      - series_count  = None（本表未填 series-level 明细；前端 DicomViewer
                        会拉 series 接口补齐；UI 显示'系列数加载中'）
      - patient_id    = PT_xxx（脱敏后）
      - patient_name  = 从 lnrs_anon_patient 联表带出（便于 viewer overlay）
      - study_description / study_date：未填，前端 DicomViewer 会用
        listStudies() 接口补齐；本接口不返避免冗余
    """
    conditions = [
        AnonImagingStudyModel.patient_id == patient_id,
        AnonPatientModel.deleted_at.is_(None),
    ]
    if center:
        conditions.append(AnonImagingStudyModel.center_code == center)
    if modality:
        conditions.append(AnonImagingStudyModel.modality == modality)

    stmt = (
        select(
            AnonImagingStudyModel.study_key,
            AnonImagingStudyModel.dicom_study_uid.label("study_uid"),
            AnonImagingStudyModel.modality,
            AnonImagingStudyModel.image_path,
            AnonImagingStudyModel.sop_count,
            AnonImagingStudyModel.source,
            AnonImagingStudyModel.anon_exam_id,
            AnonImagingStudyModel.center_code,
            AnonImagingStudyModel.created_at,
            AnonPatientModel.patient_id.label("patient_id"),
            AnonPatientModel.sex,
            AnonPatientModel.birth_date,
        )
        .join(
            AnonPatientModel,
            AnonPatientModel.patient_id == AnonImagingStudyModel.patient_id,
        )
        .where(*conditions)
        .order_by(
            AnonImagingStudyModel.modality,
            AnonImagingStudyModel.study_key,
        )
    )
    rows = (await db.execute(stmt)).mappings().all()
    items: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        # study_id 别名：DicomViewer props.studyId 期望 = StudyInstanceUID
        d["study_id"] = d["study_uid"]
        d["patient_name"] = None  # 暂未联 patient_name（patient 表无此列）
        if hasattr(d.get("birth_date"), "isoformat"):
            d["birth_date"] = d["birth_date"].isoformat()
        if hasattr(d.get("created_at"), "isoformat"):
            d["created_at"] = d["created_at"].isoformat()
        items.append(d)
    return items


async def anon_get_imaging_study_path(
    db: AsyncSession,
    *,
    patient_id: str,
    dicom_study_uid: str,
) -> str | None:
    """按 (patient_id, study_uid) 反查影像绝对路径。

    用途：DICOMweb 后端在收到 QIDO-RS 请求需要验证 study 是否对当前 patient
    可见时使用；以及 dicom_image_bytes 接口安全校验。
    """
    stmt = select(AnonImagingStudyModel.image_path).where(
        AnonImagingStudyModel.patient_id == patient_id,
        AnonImagingStudyModel.dicom_study_uid == dicom_study_uid,
    ).limit(1)
    return (await db.execute(stmt)).scalar_one_or_none()

# --------------------------------------------------------------------------- #
# 孤儿研究查询(2026-09-03 新增)
# --------------------------------------------------------------------------- #


async def anon_list_patient_imaging_orphans(
    db: AsyncSession,
    patient_id: str,
    center: str | None = None,
    orphan_status: str | None = None,
    orphan_kind: str | None = None,
) -> list[dict[str, Any]]:
    """列出某患者的孤儿研究(2026-09-03 新增)。

    返回元素字段:
      - study_orphan_id      业务编号 OR_<8hex>
      - source_orphan_hash   跨中心指纹
      - center_code, dicom_study_uid, image_path, modality, path_date_prefix,
        sop_count, source, orphan_kind, orphan_status, review_notes,
        audit_batch_id, patient_id, created_at, updated_at
    """
    conditions = [
        AnonImagingOrphanModel.patient_id == patient_id,
    ]
    if center:
        conditions.append(AnonImagingOrphanModel.center_code == center)
    if orphan_status:
        conditions.append(AnonImagingOrphanModel.orphan_status == orphan_status)
    if orphan_kind:
        conditions.append(AnonImagingOrphanModel.orphan_kind == orphan_kind)

    stmt = (
        select(
            AnonImagingOrphanModel.study_orphan_id,
            AnonImagingOrphanModel.source_orphan_hash,
            AnonImagingOrphanModel.center_code,
            AnonImagingOrphanModel.dicom_study_uid,
            AnonImagingOrphanModel.image_path,
            AnonImagingOrphanModel.path_date_prefix,
            AnonImagingOrphanModel.modality,
            AnonImagingOrphanModel.sop_count,
            AnonImagingOrphanModel.source,
            AnonImagingOrphanModel.orphan_kind,
            AnonImagingOrphanModel.orphan_status,
            AnonImagingOrphanModel.review_notes,
            AnonImagingOrphanModel.audit_batch_id,
            AnonImagingOrphanModel.patient_id,
            AnonImagingOrphanModel.created_at,
            AnonImagingOrphanModel.updated_at,
        )
        .where(*conditions)
        .order_by(
            AnonImagingOrphanModel.orphan_kind,
            AnonImagingOrphanModel.orphan_key,
        )
    )
    rows = (await db.execute(stmt)).mappings().all()
    items: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        for k in ("created_at", "updated_at"):
            if hasattr(d.get(k), "isoformat"):
                d[k] = d[k].isoformat()
        items.append(d)
    return items


async def anon_get_imaging_orphan_path(
    db: AsyncSession,
    *,
    patient_id: str,
    study_orphan_id: str,
) -> str | None:
    """按 study_orphan_id 反查孤儿研究磁盘绝对路径(主表反查路径)。"""
    stmt = select(AnonImagingOrphanModel.image_path).where(
        AnonImagingOrphanModel.patient_id == patient_id,
        AnonImagingOrphanModel.study_orphan_id == study_orphan_id,
    ).limit(1)
    return (await db.execute(stmt)).scalar_one_or_none()


async def anon_resolve_orphan_id_from_path(
    db: AsyncSession,
    *,
    center_code: str,
    image_path: str,
    dicom_root: str,
) -> str | None:
    """给定 (center_code, image_path, dicom_root) 反查 study_orphan_id(反向映射:绝对路径 → ID)。

    算法:rel_path = image_path.removeprefix(dicom_root).lstrip('/');OR_xxx = 'OR_' + sha256(f'{center_code}:{rel_path}')[:12](48 bit 空间);
    然后 SELECT study_orphan_id WHERE study_orphan_id = ? 校验存在性(返回表内值或 None)。
    用于:"运维迁移 dicom 根目录"场景下,旧 ID 仍可经此函数从新绝对路径获取(只要 dicom_root 一致)。
    """
    import hashlib

    if image_path.startswith(dicom_root):
        rel_path = image_path[len(dicom_root):].lstrip("/")
    else:
        rel_path = image_path
    payload = f"{center_code}:{rel_path}".encode("utf-8")
    candidate_id = "OR_" + hashlib.sha256(payload).hexdigest()[:12]
    stmt = select(AnonImagingOrphanModel.study_orphan_id).where(
        AnonImagingOrphanModel.study_orphan_id == candidate_id,
        AnonImagingOrphanModel.center_code == center_code,
    ).limit(1)
    return (await db.execute(stmt)).scalar_one_or_none()


async def anon_list_imaging_orphans_by_center(
    db: AsyncSession,
    center: str,
    page: int = 1,
    page_size: int = 50,
    orphan_kind: str | None = None,
    orphan_status: str | None = None,
) -> list[dict[str, Any]]:
    """分页列出某中心的孤儿(医院视角)。"""
    conditions = [AnonImagingOrphanModel.center_code == center]
    if orphan_kind:
        conditions.append(AnonImagingOrphanModel.orphan_kind == orphan_kind)
    if orphan_status:
        conditions.append(AnonImagingOrphanModel.orphan_status == orphan_status)

    offset = max(0, (page - 1) * page_size)
    stmt = (
        select(
            AnonImagingOrphanModel.orphan_key,
            AnonImagingOrphanModel.study_orphan_id,
            AnonImagingOrphanModel.source_orphan_hash,
            AnonImagingOrphanModel.center_code,
            AnonImagingOrphanModel.patient_id,
            AnonImagingOrphanModel.dicom_study_uid,
            AnonImagingOrphanModel.image_path,
            AnonImagingOrphanModel.path_date_prefix,
            AnonImagingOrphanModel.modality,
            AnonImagingOrphanModel.sop_count,
            AnonImagingOrphanModel.orphan_kind,
            AnonImagingOrphanModel.orphan_status,
            AnonImagingOrphanModel.created_at,
        )
        .where(*conditions)
        .order_by(AnonImagingOrphanModel.orphan_key)
        .offset(offset)
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).mappings().all()
    items: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        if hasattr(d.get("created_at"), "isoformat"):
            d["created_at"] = d["created_at"].isoformat()
        items.append(d)
    return items

async def anon_get_orphan_audit_batch(
    db: AsyncSession,
    audit_batch_id: str,
) -> dict[str, Any] | None:
    """反查审计批次元数据。"""
    stmt = select(AnonOrphanAuditBatchModel).where(
        AnonOrphanAuditBatchModel.audit_batch_id == audit_batch_id,
    ).limit(1)
    row = (await db.execute(stmt)).scalars().first()
    if not row:
        return None
    d = {
        "audit_batch_id": row.audit_batch_id,
        "center_code": row.center_code,
        "audit_locator": row.audit_locator,
        "audit_sha256": row.audit_sha256,
        "discovered_count": row.discovered_count,
        "patient_missing_count": row.patient_missing_count,
        "dual_disk_copy_count": row.dual_disk_copy_count,
        "empty_dir_count": row.empty_dir_count,
        "other_count": row.other_count,
        "ran_by": row.ran_by,
        "ran_at": row.ran_at.isoformat() if row.ran_at else None,
        "notes": row.notes,
    }
    return d


async def anon_get_imaging_orphan_by_id(
    db: AsyncSession,
    study_orphan_id: str,
) -> dict[str, Any] | None:
    """按 study_orphan_id 全局反查孤儿详情(主表即中间表的体现)。"""
    stmt = select(
        AnonImagingOrphanModel.orphan_key,
        AnonImagingOrphanModel.study_orphan_id,
        AnonImagingOrphanModel.source_orphan_hash,
        AnonImagingOrphanModel.center_code,
        AnonImagingOrphanModel.patient_id,
        AnonImagingOrphanModel.dicom_study_uid,
        AnonImagingOrphanModel.image_path,
        AnonImagingOrphanModel.path_date_prefix,
        AnonImagingOrphanModel.modality,
        AnonImagingOrphanModel.sop_count,
        AnonImagingOrphanModel.source,
        AnonImagingOrphanModel.orphan_kind,
        AnonImagingOrphanModel.orphan_status,
        AnonImagingOrphanModel.review_notes,
        AnonImagingOrphanModel.audit_batch_id,
        AnonImagingOrphanModel.created_at,
        AnonImagingOrphanModel.updated_at,
    ).where(
        AnonImagingOrphanModel.study_orphan_id == study_orphan_id,
    ).limit(1)
    row = (await db.execute(stmt)).mappings().first()
    if not row:
        return None
    d = dict(row)
    for k in ("created_at", "updated_at"):
        if hasattr(d.get(k), "isoformat"):
            d[k] = d[k].isoformat()
    return d
