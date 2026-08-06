"""脱敏数据统计查询层 — 基于 ETL2 落库的 lnrs_anon_* 表。

为数据概览仪表板提供聚合统计，返回 {kpis, dimensions} 结构（ADR-0007）。

查询逻辑封装在 StatsQuery 类中：筛选条件作为实例属性统一管理，
新增筛选参数只需扩展 __init__ + _patient_filters / _exam_filters。
维度定义在 DIMENSIONS 注册表集中管理：新增维度只需加一条 + 实现对应方法。
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .anon_model import AnonExamModel, AnonPatientModel
from .stats_schema import StatsFiltersIn

# ── 常量 ──────────────────────────────────────

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

AGE_BUCKET_OPTIONS = [{"value": label, "label": label} for _, _, label in AGE_BUCKETS]

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


# ── 维度注册表 ────────────────────────────────

# 新增维度在此加一条：(key, label, chart_type, method_name)
# method_name 对应 StatsQuery 上的 async 方法，签名统一为 (self) -> list[dict]
DIMENSIONS: list[tuple[str, str, str, str]] = [
    ("age_distribution", "年龄分布", "bar", "query_age_distribution"),
    ("gender_ratio", "性别比", "pie", "query_gender_ratio"),
    ("center_distribution", "中心分布", "h-bar", "query_center_distribution"),
    ("modality_counts", "模态检查量", "pie", "query_modality_counts"),
    ("exam_trend", "检查时间趋势", "line", "query_exam_trend"),
]


class StatsQuery:
    """仪表板统计查询器。

    封装筛选条件，所有查询方法共享同一组实例属性，
    后续新增参数只需扩展 __init__ + _patient_filters / _exam_filters。
    """

    def __init__(
        self,
        db: AsyncSession,
        filters: StatsFiltersIn | None = None,
    ) -> None:
        self.db = db
        self.center = filters.center if filters else None
        self.gender = filters.gender if filters else None
        self.modality = filters.modality if filters else None
        self.age_bucket = filters.age_bucket if filters else None
        self.abo_blood_type = filters.abo_blood_type if filters else None
        self.smoking_status = filters.smoking_status if filters else None
        self._ref_date = date.today()

    # ── 过滤条件构建 ──────────────────────────

    def _patient_filters(self) -> list:
        """构建 patient 表的过滤条件列表。

        modality 通过子查询关联 exam 表；
        age_bucket 通过年龄分桶 CASE 表达式过滤；
        gender / abo_blood_type / smoking_status 直接过滤 patient 表字段。
        """
        conditions = [_not_deleted_patient()]
        if self.center:
            conditions.append(AnonPatientModel.center_code == self.center)
        if self.gender:
            conditions.append(AnonPatientModel.sex == self.gender)
        if self.abo_blood_type:
            conditions.append(AnonPatientModel.abo_blood_type == self.abo_blood_type)
        if self.smoking_status:
            conditions.append(AnonPatientModel.smoking_status == self.smoking_status)
        if self.modality:
            conditions.append(
                AnonPatientModel.patient_id.in_(
                    select(AnonExamModel.patient_id).where(
                        AnonExamModel.exam_type == self.modality
                    )
                )
            )
        if self.age_bucket:
            bucket_expr = _age_bucket_expr(self._ref_date)
            conditions.append(bucket_expr == self.age_bucket)
        return conditions

    def _exam_filters(self) -> list:
        """构建 exam 表的过滤条件列表。

        gender / age_bucket / abo_blood_type / smoking_status 通过 IN 子查询
        关联 patient 表；modality 直接过滤 exam_type。
        """
        conditions = []
        if self.center:
            conditions.append(AnonExamModel.center_code == self.center)
        if self.modality:
            conditions.append(AnonExamModel.exam_type == self.modality)
        patient_attrs = (
            self.gender or self.age_bucket
            or self.abo_blood_type or self.smoking_status
        )
        if patient_attrs:
            sub = select(AnonPatientModel.patient_id).where(_not_deleted_patient())
            if self.gender:
                sub = sub.where(AnonPatientModel.sex == self.gender)
            if self.age_bucket:
                bucket_expr = _age_bucket_expr(self._ref_date)
                sub = sub.where(bucket_expr == self.age_bucket)
            if self.abo_blood_type:
                sub = sub.where(AnonPatientModel.abo_blood_type == self.abo_blood_type)
            if self.smoking_status:
                sub = sub.where(AnonPatientModel.smoking_status == self.smoking_status)
            conditions.append(AnonExamModel.patient_id.in_(sub))
        return conditions

    # ── 基础聚合 ──────────────────────────────

    async def count_patients(self) -> int:
        stmt = (
            select(func.count())
            .select_from(AnonPatientModel)
            .where(*self._patient_filters())
        )
        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def count_exams(self) -> int:
        stmt = select(func.count()).select_from(AnonExamModel)
        conditions = self._exam_filters()
        if conditions:
            stmt = stmt.where(*conditions)
        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def distinct_centers(self) -> list[str]:
        """返回去重的中心列表（供 filters.options 使用）。"""
        stmt = (
            select(AnonPatientModel.center_code)
            .where(*self._patient_filters())
            .distinct()
            .order_by(AnonPatientModel.center_code)
        )
        result = await self.db.execute(stmt)
        return [row[0] for row in result.all() if row[0]]

    async def distinct_modalities(self) -> list[str]:
        """返回去重的模态列表。"""
        conditions = [AnonExamModel.exam_type.is_not(None)]
        conditions.extend(self._exam_filters())
        stmt = (
            select(AnonExamModel.exam_type)
            .where(*conditions)
            .distinct()
            .order_by(AnonExamModel.exam_type)
        )
        result = await self.db.execute(stmt)
        return [row[0] for row in result.all()]

    async def exam_year_range(self) -> dict[str, int] | None:
        """返回检查日期的最小/最大年份。"""
        stmt = (
            select(
                func.min(func.extract("year", AnonExamModel.exam_date)),
                func.max(func.extract("year", AnonExamModel.exam_date)),
            )
            .select_from(AnonExamModel)
        )
        conditions = self._exam_filters()
        if conditions:
            stmt = stmt.where(*conditions)
        result = await self.db.execute(stmt)
        row = result.first()
        if row and row[0] is not None:
            return {"min": int(row[0]), "max": int(row[1])}
        return None

    # ── 维度查询 ──────────────────────────────

    async def query_age_distribution(self) -> list[dict]:
        bucket_col = _age_bucket_expr(self._ref_date).label("age_group")
        stmt = (
            select(bucket_col, func.count().label("count"))
            .select_from(AnonPatientModel)
            .where(*self._patient_filters())
            .group_by(bucket_col)
            .order_by(bucket_col)
        )
        result = await self.db.execute(stmt)
        counts = {row[0]: row[1] for row in result.all()}
        return [
            {"label": label, "count": counts.get(label, 0)}
            for _, _, label in AGE_BUCKETS
        ]

    async def _load_dict_labels(self, dict_type: str) -> dict[str, str]:
        """从 sys_dict_data 加载 {dict_value: dict_label} 映射（复用系统字典）。"""
        from app.api.v1.module_system.dict.model import DictDataModel

        stmt = select(DictDataModel.dict_value, DictDataModel.dict_label).where(
            DictDataModel.dict_type == dict_type
        )
        result = await self.db.execute(stmt)
        return {value: label for value, label in result.all()}

    async def query_gender_ratio(self) -> list[dict]:
        stmt = (
            select(AnonPatientModel.sex, func.count().label("count"))
            .select_from(AnonPatientModel)
            .where(*self._patient_filters())
            .group_by(AnonPatientModel.sex)
            .order_by(AnonPatientModel.sex)
        )
        result = await self.db.execute(stmt)
        label_map = await self._load_dict_labels("med_sex")
        return [
            {"sex": sex, "label": label_map.get(sex, sex), "count": count}
            for sex, count in result.all()
        ]

    async def query_center_distribution(self) -> list[dict]:
        stmt = (
            select(AnonPatientModel.center_code, func.count().label("count"))
            .select_from(AnonPatientModel)
            .where(*self._patient_filters())
            .group_by(AnonPatientModel.center_code)
            .order_by(func.count().desc())
        )
        result = await self.db.execute(stmt)
        return [
            {"center_code": center_code, "count": count}
            for center_code, count in result.all()
        ]

    async def query_modality_counts(self) -> list[dict]:
        conditions = [AnonExamModel.exam_type.is_not(None)]
        conditions.extend(self._exam_filters())
        stmt = (
            select(AnonExamModel.exam_type, func.count().label("count"))
            .select_from(AnonExamModel)
            .where(*conditions)
            .group_by(AnonExamModel.exam_type)
            .order_by(func.count().desc())
        )
        result = await self.db.execute(stmt)
        label_map = await self._load_dict_labels("med_exam_type")
        return [
            {"exam_type": exam_type, "label": label_map.get(exam_type, exam_type), "count": count}
            for exam_type, count in result.all()
        ]

    async def query_exam_trend(self) -> list[dict]:
        year_col = func.extract("year", AnonExamModel.exam_date).label("year")
        month_col = func.extract("month", AnonExamModel.exam_date).label("month")
        stmt = (
            select(year_col, month_col, func.count().label("count"))
            .select_from(AnonExamModel)
        )
        conditions = self._exam_filters()
        if conditions:
            stmt = stmt.where(*conditions)
        stmt = stmt.group_by(year_col, month_col).order_by(year_col, month_col)
        result = await self.db.execute(stmt)
        return [
            {"year": int(year), "month": int(month), "count": count}
            for year, month, count in result.all()
        ]

    # ── 总出口 ────────────────────────────────

    async def get_overview(self) -> dict:
        """仪表板全量概览 — 返回 {filters, kpis, dimensions} 结构（ADR-0007）。"""
        # 基础聚合
        total_patients = await self.count_patients()
        total_exams = await self.count_exams()
        centers = await self.distinct_centers()
        modalities = await self.distinct_modalities()

        # kpis
        kpis = [
            {"key": "total_patients", "label": "患者总量", "value": total_patients, "format": "number"},
            {"key": "total_exams", "label": "检查总量", "value": total_exams, "format": "number"},
            {"key": "center_count", "label": "来源中心", "value": len(centers), "format": "number"},
            {"key": "modality_count", "label": "检查模态", "value": len(modalities), "format": "number"},
        ]

        # dimensions — 遍历注册表逐一查询
        dimensions = []
        for key, label, chart_type, method_name in DIMENSIONS:
            query_func = getattr(self, method_name)
            data = await query_func()
            dimensions.append({
                "key": key,
                "label": label,
                "chart_type": chart_type,
                "data": data,
            })

        return {
            "kpis": kpis,
            "dimensions": dimensions,
        }


# ── 模块级便捷出口（保持 service 层调用不变） ──────


async def get_dashboard_overview(
    db: AsyncSession,
    filters: StatsFiltersIn | None = None,
) -> dict:
    """仪表板全量概览 — 委托给 StatsQuery。"""
    query = StatsQuery(db, filters=filters)
    return await query.get_overview()
