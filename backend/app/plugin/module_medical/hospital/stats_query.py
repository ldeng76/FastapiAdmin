"""脱敏数据统计查询层 — 基于 ETL2 落库的 lnrs_anon_* 表。

为数据概览仪表板提供聚合统计，返回 {filters, kpis, dimensions} 结构（ADR-0007）。

维度定义在此集中管理：新增维度只需在 DIMENSIONS 注册表加一条 + 在查询函数中实现。
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .anon_model import AnonExamModel, AnonPatientModel

# ── 年龄分桶 ──────────────────────────────────

AGE_BUCKETS = [
    (0, 18, "0-17"),
    (18, 30, "18-29"),
    (30, 40, "30-39"),
    (40, 50, "40-49"),
    (50, 60, "50-59"),
    (60, 70, "60-69"),
    (70, 80, "70-79"),
    (80, 200, "80+"),
]


def _not_deleted_patient():
    """lnrs_anon_patient 软删除过滤条件。"""
    return AnonPatientModel.deleted_at.is_(None)  # type: ignore[return-value]


def _age_bucket_expr(ref_date: date | None = None):
    """构造年龄分桶的 CASE 表达式。

    使用 PostgreSQL age() 函数精确计算年龄（考虑月日）。
    """
    if ref_date is None:
        ref_date = date.today()
    age_years = func.floor(func.extract("year", func.age(ref_date, AnonPatientModel.birth_date)))
    return case(
        *[
            (
                AnonPatientModel.birth_date.is_not(None)
                & (age_years >= lo)
                & (age_years < hi),
                label,
            )
            for lo, hi, label in AGE_BUCKETS
        ],
        else_=None,
    )


# ── 基础聚合 ──────────────────────────────────


async def _count_patients(db: AsyncSession) -> int:
    stmt = (
        select(func.count())
        .select_from(AnonPatientModel)
        .where(_not_deleted_patient())
    )
    result = await db.execute(stmt)
    return int(result.scalar_one())


async def _count_exams(db: AsyncSession) -> int:
    stmt = select(func.count()).select_from(AnonExamModel)
    result = await db.execute(stmt)
    return int(result.scalar_one())


async def _distinct_centers(db: AsyncSession) -> list[str]:
    """返回去重的中心列表（供 filters.options 使用）。"""
    stmt = (
        select(AnonPatientModel.center_code)
        .where(_not_deleted_patient())
        .distinct()
        .order_by(AnonPatientModel.center_code)
    )
    result = await db.execute(stmt)
    return [row[0] for row in result.all() if row[0]]


async def _distinct_modalities(db: AsyncSession) -> list[str]:
    """返回去重的模态列表。"""
    stmt = (
        select(AnonExamModel.exam_type)
        .where(AnonExamModel.exam_type.is_not(None))
        .distinct()
        .order_by(AnonExamModel.exam_type)
    )
    result = await db.execute(stmt)
    return [row[0] for row in result.all()]


async def _exam_year_range(db: AsyncSession) -> dict[str, int] | None:
    """返回检查日期的最小/最大年份。"""
    stmt = (
        select(
            func.min(func.extract("year", AnonExamModel.exam_date)),
            func.max(func.extract("year", AnonExamModel.exam_date)),
        )
        .select_from(AnonExamModel)
    )
    result = await db.execute(stmt)
    row = result.first()
    if row and row[0] is not None:
        return {"min": int(row[0]), "max": int(row[1])}
    return None


# ── 维度查询 ──────────────────────────────────


async def _query_age_distribution(db: AsyncSession, ref_date: date | None = None) -> list[dict]:
    bucket_col = _age_bucket_expr(ref_date).label("age_group")
    stmt = (
        select(bucket_col, func.count().label("count"))
        .select_from(AnonPatientModel)
        .where(_not_deleted_patient())
        .group_by(bucket_col)
        .order_by(bucket_col)
    )
    result = await db.execute(stmt)
    counts = {row[0]: row[1] for row in result.all()}
    return [
        {"label": label, "count": counts.get(label, 0)}
        for _, _, label in AGE_BUCKETS
    ]


async def _load_dict_labels(db: AsyncSession, dict_type: str) -> dict[str, str]:
    """从 sys_dict_data 加载 {dict_value: dict_label} 映射（复用系统字典）。"""
    from app.api.v1.module_system.dict.model import DictDataModel

    stmt = select(DictDataModel.dict_value, DictDataModel.dict_label).where(
        DictDataModel.dict_type == dict_type
    )
    result = await db.execute(stmt)
    return {value: label for value, label in result.all()}


async def _query_gender_ratio(db: AsyncSession) -> list[dict]:
    stmt = (
        select(AnonPatientModel.sex, func.count().label("count"))
        .select_from(AnonPatientModel)
        .where(_not_deleted_patient())
        .group_by(AnonPatientModel.sex)
        .order_by(AnonPatientModel.sex)
    )
    result = await db.execute(stmt)
    label_map = await _load_dict_labels(db, "med_sex")
    return [
        {"sex": sex, "label": label_map.get(sex, sex), "count": count}
        for sex, count in result.all()
    ]


async def _query_center_distribution(db: AsyncSession) -> list[dict]:
    stmt = (
        select(AnonPatientModel.center_code, func.count().label("count"))
        .select_from(AnonPatientModel)
        .where(_not_deleted_patient())
        .group_by(AnonPatientModel.center_code)
        .order_by(func.count().desc())
    )
    result = await db.execute(stmt)
    return [
        {"center_code": center_code, "count": count}
        for center_code, count in result.all()
    ]


async def _query_modality_counts(db: AsyncSession) -> list[dict]:
    stmt = (
        select(AnonExamModel.exam_type, func.count().label("count"))
        .select_from(AnonExamModel)
        .where(AnonExamModel.exam_type.is_not(None))
        .group_by(AnonExamModel.exam_type)
        .order_by(func.count().desc())
    )
    result = await db.execute(stmt)
    label_map = await _load_dict_labels(db, "med_exam_type")
    return [
        {"exam_type": exam_type, "label": label_map.get(exam_type, exam_type), "count": count}
        for exam_type, count in result.all()
    ]


async def _query_exam_trend(db: AsyncSession) -> list[dict]:
    year_col = func.extract("year", AnonExamModel.exam_date).label("year")
    month_col = func.extract("month", AnonExamModel.exam_date).label("month")
    stmt = (
        select(year_col, month_col, func.count().label("count"))
        .select_from(AnonExamModel)
        .group_by(year_col, month_col)
        .order_by(year_col, month_col)
    )
    result = await db.execute(stmt)
    return [
        {"year": int(year), "month": int(month), "count": count}
        for year, month, count in result.all()
    ]


# ── 维度注册表 ────────────────────────────────

# 新增维度在此加一条：(key, label, chart_type, query_func)
# query_func(db) → list[dict]
DIMENSIONS: list[tuple[str, str, str, object]] = [
    ("age_distribution", "年龄分布", "bar", _query_age_distribution),
    ("gender_ratio", "性别比", "pie", _query_gender_ratio),
    ("center_distribution", "中心分布", "h-bar", _query_center_distribution),
    ("modality_counts", "模态检查量", "pie", _query_modality_counts),
    ("exam_trend", "检查时间趋势", "line", _query_exam_trend),
]


# ── 总出口 ────────────────────────────────────


async def get_dashboard_overview(db: AsyncSession) -> dict:
    """仪表板全量概览 — 返回 {filters, kpis, dimensions} 结构（ADR-0007）。"""
    ref_date = date.today()

    # 基础聚合
    total_patients = await _count_patients(db)
    total_exams = await _count_exams(db)
    centers = await _distinct_centers(db)
    modalities = await _distinct_modalities(db)
    year_range = await _exam_year_range(db)

    # filters
    filters = {
        "center": {
            "applied": None,
            "options": centers,
        },
        "year_range": {
            "applied": None,
            "options": year_range,
        },
    }

    # kpis
    kpis = [
        {"key": "total_patients", "label": "患者总量", "value": total_patients, "format": "number"},
        {"key": "total_exams", "label": "检查总量", "value": total_exams, "format": "number"},
        {"key": "center_count", "label": "来源中心", "value": len(centers), "format": "number"},
        {"key": "modality_count", "label": "检查模态", "value": len(modalities), "format": "number"},
    ]

    # dimensions — 遍历注册表逐一查询
    dimensions = []
    for key, label, chart_type, query_func in DIMENSIONS:
        if key == "age_distribution":
            data = await query_func(db, ref_date)  # 年龄需要参考日期
        else:
            data = await query_func(db)
        dimensions.append({
            "key": key,
            "label": label,
            "chart_type": chart_type,
            "data": data,
        })

    return {
        "filters": filters,
        "kpis": kpis,
        "dimensions": dimensions,
    }
