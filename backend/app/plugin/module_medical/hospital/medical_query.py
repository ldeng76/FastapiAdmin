"""医疗数据 PostgreSQL 查询层 — 替代旧 repository.py（DuckDB 直读 parquet）。

设计要点：
- 用 SQLAlchemy Core（select/where/ilike）查 med_* 表
- 过滤 is_deleted=False（软删除）
- **不**按 tenant_id 过滤（ADR 0005 开放访问）
- 排除审计列（id/uuid/status/created_time/updated_time/is_deleted/deleted_time/created_id/updated_id/deleted_id/tenant_id/description）
- JSONB 列自动返回 dict（PostgreSQL 原生物）
- _table 中文标签维持 TABLE_LABEL 常量

注意：本模块的 response shape 必须与旧 repository.py 完全一致，
确保前端（Vue/TS）零修改。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .model import (
    FollowUpModel,
    GeneticTestModel,
    IHCResultModel,
    NoduleImagingModel,
    PathologySpecimenModel,
    PatientModel,
    SurgeryRecordModel,
    TGT_TABLE_MODELS,
)

# 子表 → 模态分组（patient 为基本信息，单独处理）
TABLE_TO_MODALITY: dict[str, str] = {
    "med_surgery_record": "clinical",
    "med_follow_up": "clinical",
    "med_pathology_specimen": "pathology",
    "med_ihc_result": "pathology",
    "med_genetic_test": "genetic",
    "med_nodule_imaging": "imaging",
}

# 子表 → 中文标签（前端折叠面板分组标题）
TABLE_LABEL: dict[str, str] = {
    "med_surgery_record": "手术记录",
    "med_follow_up": "随访结局",
    "med_pathology_specimen": "病理标本",
    "med_ihc_result": "免疫组化",
    "med_genetic_test": "基因检测",
    "med_nodule_imaging": "结节影像",
}

MODALITIES = ("clinical", "genetic", "pathology", "imaging")

# patient 表查询时的业务列（排除审计列 + JSONB 扩展列）
# 与旧 repository.py list_patients 保持完全一致
PATIENT_LIST_COLS = [
    PatientModel.patient_id,
    PatientModel.source_center,
    PatientModel.gender,
    PatientModel.birth_date,
    PatientModel.ethnicity,
    PatientModel.native_place,
    PatientModel.abo_blood_type,
    PatientModel.rh_blood_type,
    PatientModel.smoking_status,
    PatientModel.first_nodule_date,
]

# patient 详情查询时的业务列（排除审计列，含 JSONB 扩展列）
PATIENT_DETAIL_COLS = [
    PatientModel.patient_id,
    PatientModel.source_center,
    PatientModel.gender,
    PatientModel.birth_date,
    PatientModel.ethnicity,
    PatientModel.native_place,
    PatientModel.abo_blood_type,
    PatientModel.rh_blood_type,
    PatientModel.smoking_status,
    PatientModel.first_nodule_date,
    PatientModel.demographics,
    PatientModel.medical_history,
]


def _row_to_dict(row, cols: list) -> dict[str, Any]:
    """将 SQLAlchemy Row 转为纯 dict（只包含指定列）。

    JSONB 列自动转为 dict/list（SQLAlchemy 已处理，无需二次解析）。
    """
    return {col.key: getattr(row, col.key) for col in cols}


async def list_centers(db: AsyncSession) -> list[str]:
    """枚举数据中出现的来源中心（供前端下拉）。"""
    stmt = (
        select(PatientModel.source_center)
        .where(PatientModel.source_center.isnot(None), PatientModel.is_deleted == False)  # noqa: E712
        .distinct()
        .order_by(PatientModel.source_center)
    )
    result = await db.execute(stmt)
    return [row[0] for row in result.all()]


async def list_patients(
    db: AsyncSession,
    center: str | None = None,
    keyword: str | None = None,
    offset: int = 0,
    limit: int = 10,
) -> tuple[list[dict[str, Any]], int]:
    """患者分页列表。返回 (行列表, 总数)。"""
    # 构建 WHERE 条件
    conditions = [PatientModel.is_deleted == False]  # noqa: E712
    if center:
        conditions.append(PatientModel.source_center == center)
    if keyword:
        kw = f"%{keyword}%"
        conditions.append(
            or_(
                PatientModel.patient_id.ilike(kw),
                PatientModel.source_center.ilike(kw),
            )
        )

    # 总数
    count_stmt = select(func.count()).select_from(PatientModel).where(*conditions)
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    # 分页列表
    list_stmt = (
        select(*PATIENT_LIST_COLS)
        .where(*conditions)
        .order_by(PatientModel.source_center, PatientModel.patient_id)
        .limit(limit)
        .offset(offset)
    )
    list_result = await db.execute(list_stmt)
    rows = list_result.all()

    items = [_row_to_dict(row, PATIENT_LIST_COLS) for row in rows]
    return items, total


async def get_patient_detail(
    db: AsyncSession,
    patient_id: str,
    center: str | None = None,
) -> dict[str, Any]:
    """患者多模态详情，按四模态分组。中心由 patient 表 source_center 决定。"""
    # 1) 患者基本信息
    p_conditions = [
        PatientModel.patient_id == patient_id,
        PatientModel.is_deleted == False,  # noqa: E712
    ]
    if center:
        p_conditions.append(PatientModel.source_center == center)

    p_stmt = select(*PATIENT_DETAIL_COLS).where(*p_conditions)
    p_result = await db.execute(p_stmt)
    p_row = p_result.first()
    if not p_row:
        return {}

    patient = _row_to_dict(p_row, PATIENT_DETAIL_COLS)

    # 2) 按模态聚合各子表
    modalities: dict[str, list[dict[str, Any]]] = {m: [] for m in MODALITIES}

    for table_name, modality in TABLE_TO_MODALITY.items():
        model = _get_model_by_table_name(table_name)
        if model is None:
            continue

        # 查询子表业务列（排除审计列）
        business_cols = _get_business_columns(model)
        stmt = (
            select(*business_cols)
            .where(
                model.patient_id == patient_id,
                model.is_deleted == False,  # noqa: E712
            )
        )
        result = await db.execute(stmt)
        rows = result.all()

        label = TABLE_LABEL[table_name]
        for row in rows:
            row_dict = _row_to_dict(row, business_cols)
            row_dict["_table"] = label
            modalities[modality].append(row_dict)

    return {
        "patient": patient,
        "clinical": modalities["clinical"],
        "genetic": modalities["genetic"],
        "pathology": modalities["pathology"],
        "imaging": modalities["imaging"],
    }


def _get_model_by_table_name(table_name: str):
    """根据表名返回对应的 ORM 模型类。"""
    mapping = {
        "med_patient": PatientModel,
        "med_pathology_specimen": PathologySpecimenModel,
        "med_surgery_record": SurgeryRecordModel,
        "med_genetic_test": GeneticTestModel,
        "med_nodule_imaging": NoduleImagingModel,
        "med_ihc_result": IHCResultModel,
        "med_follow_up": FollowUpModel,
    }
    return mapping.get(table_name)


def _get_business_columns(model) -> list:
    """获取模型的业务列（排除审计列）。

    排除：id, uuid, status, description, created_time, updated_time,
          is_deleted, deleted_time, created_id, updated_id, deleted_id,
          tenant_id
    """
    audit_cols = {
        "id", "uuid", "status", "description",
        "created_time", "updated_time", "is_deleted", "deleted_time",
        "created_id", "updated_id", "deleted_id", "tenant_id",
    }
    return [col for col in model.__table__.columns if col.name not in audit_cols]
