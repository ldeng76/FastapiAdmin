"""脱敏数据统计查询层 — 基于 ETL2 落库的 lnrs_anon_* 表。

为数据概览仪表板提供聚合统计，返回 {kpis, dimensions} 结构（ADR-0007）。

查询逻辑封装在 StatsQuery 类中：筛选条件作为实例属性统一管理，
新增筛选参数只需扩展 __init__ + _patient_filters / _exam_filters。
维度定义在 DIMENSIONS 注册表集中管理：新增维度只需加一条 + 实现对应方法。
"""

from __future__ import annotations

from datetime import date
from typing import Any
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .anon_model import AnonDicomSeriesModel, AnonExamModel, AnonPatientModel
from .stats_schema import StatsFiltersIn


def _calc_age(birth_date: date | None, ref: date | None = None) -> int | None:
    """根据出生日期计算年龄，birth_date 为空时返回 None。"""
    if not birth_date:
        return None
    today = ref or date.today()
    age = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        age -= 1
    return age

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

# BMI 分档（中国成人标准：偏瘦 <18.5 / 正常 18.5-23.9 / 超重 24-27.9 / 肥胖 ≥28）
BMI_BUCKETS: list[tuple[float, float, str]] = [
    (0, 18.5, "<18.5"),
    (18.5, 24, "18.5-23.9"),
    (24, 28, "24.0-27.9"),
    (28, 10000, "28.0+"),
]

BMI_BUCKET_OPTIONS = [{"value": label, "label": label} for _, _, label in BMI_BUCKETS]

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


def _bmi_bucket_expr():
    """构造 BMI 分档的 CASE 表达式（按 BMI_BUCKETS 左闭右开分档）。"""
    return case(
        *[
            (
                AnonPatientModel.bmi.is_not(None)
                & (AnonPatientModel.bmi >= lo)
                & (AnonPatientModel.bmi < hi),
                label,
            )
            for lo, hi, label in BMI_BUCKETS
        ],
        else_=None,
    )


def build_patient_filters(
    filters: StatsFiltersIn | None,
    ref_date: date | None = None,
) -> list:
    """构建 patient 表的过滤条件列表（仪表板统计与患者列表共用）。

    这是筛选逻辑的唯一来源：新增筛选参数时只需改这里 + StatsFiltersIn，
    统计概览（StatsQuery）与患者列表（anon_list_patients）自动同步生效。

    - sex / abo / rh / smoking 直接过滤 patient 表字段
    - modality 通过 exam 表子查询过滤
    - age_bucket / bmi_bucket 通过 CASE 分档表达式过滤
    - patient_id 对患者编号做 ILIKE 模糊匹配
    - is_placeholders 是否包含占位患者（默认 False，排除占位患者）
    """
    conditions = [_not_deleted_patient()]
    if filters is None:
        return conditions

    if filters.sex:
        conditions.append(AnonPatientModel.sex == filters.sex)
    if filters.abo_blood_type:
        conditions.append(AnonPatientModel.abo_blood_type == filters.abo_blood_type)
    if filters.rh_blood_type:
        conditions.append(AnonPatientModel.rh_blood_type == filters.rh_blood_type)
    if filters.smoking_status:
        conditions.append(AnonPatientModel.smoking_status == filters.smoking_status)
    if filters.modality:
        conditions.append(
            AnonPatientModel.patient_id.in_(
                select(AnonExamModel.patient_id).where(
                    AnonExamModel.exam_type == filters.modality
                )
            )
        )
    if filters.age_bucket:
        conditions.append(_age_bucket_expr(ref_date) == filters.age_bucket)
    if filters.bmi_bucket:
        conditions.append(_bmi_bucket_expr() == filters.bmi_bucket)
    if filters.patient_id:
        conditions.append(
            AnonPatientModel.patient_id.ilike(f"%{filters.patient_id}%")
        )
    # 按患者编号搜索时允许定位占位患者；无编号时仍保持列表默认隐藏占位患者。
    if not filters.is_placeholders and not filters.patient_id:
        conditions.append(AnonPatientModel.is_placeholder.is_(False))
    return conditions


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
        self._filters = filters
        self.sex = filters.sex if filters else None
        self.modality = filters.modality if filters else None
        self.age_bucket = filters.age_bucket if filters else None
        self.abo_blood_type = filters.abo_blood_type if filters else None
        self.rh_blood_type = filters.rh_blood_type if filters else None
        self.smoking_status = filters.smoking_status if filters else None
        self.bmi_bucket = filters.bmi_bucket if filters else None
        self.patient_id = filters.patient_id if filters else None
        self.is_placeholders = filters.is_placeholders if filters else False
        self._ref_date = date.today()

    # ── 过滤条件构建 ──────────────────────────

    def _patient_filters(self) -> list:
        """构建 patient 表的过滤条件列表（委托给 build_patient_filters 统一实现）。"""
        return build_patient_filters(self._filters, self._ref_date)

    def _exam_filters(self) -> list:
        """构建 exam 表的过滤条件列表。

        sex / age_bucket / abo_blood_type / smoking_status / bmi_bucket /
        patient_id / is_placeholders 通过 IN 子查询关联 patient 表；
        modality 直接过滤 exam_type。
        """
        conditions = []
        if self.modality:
            conditions.append(AnonExamModel.exam_type == self.modality)
        patient_attrs = (
            self.sex or self.age_bucket
            or self.abo_blood_type or self.rh_blood_type or self.smoking_status
            or self.bmi_bucket or self.patient_id
        )
        # is_placeholders=False（默认）时排除占位患者
        exclude_placeholders = not self.is_placeholders
        if patient_attrs or exclude_placeholders:
            sub = select(AnonPatientModel.patient_id).where(_not_deleted_patient())
            if self.sex:
                sub = sub.where(AnonPatientModel.sex == self.sex)
            if self.age_bucket:
                bucket_expr = _age_bucket_expr(self._ref_date)
                sub = sub.where(bucket_expr == self.age_bucket)
            if self.abo_blood_type:
                sub = sub.where(AnonPatientModel.abo_blood_type == self.abo_blood_type)
            if self.rh_blood_type:
                sub = sub.where(AnonPatientModel.rh_blood_type == self.rh_blood_type)
            if self.smoking_status:
                sub = sub.where(AnonPatientModel.smoking_status == self.smoking_status)
            if self.bmi_bucket:
                sub = sub.where(_bmi_bucket_expr() == self.bmi_bucket)
            if self.patient_id:
                sub = sub.where(
                    AnonPatientModel.patient_id.ilike(f"%{self.patient_id}%")
                )
            if exclude_placeholders:
                sub = sub.where(AnonPatientModel.is_placeholder.is_(False))
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


    async def query_series_counts_by_modality(self) -> list[dict]:
        """按 modality 聚合 dicom_series 的 series_count / instance_count /
        total_bytes（2026-09-15 引入；ETL-2 dicom_series 落库后才会有非零值）。

        走 lnrs_anon_dicom_series 表，JOIN lnrs_anon_imaging_study 以便复用
        现有的患者维度筛选。无 series 数据时返回空列表（GROUP BY 不出哑行，
        前端 0 行更直观）。
        """
        from .anon_model import AnonImagingStudyModel
        # 复用 patient 维度筛选（_patient_filters 返回 lnrs.lnrs_anon_patient.* 条件）
        patient_conditions = self._patient_filters()
        sub_patients = select(AnonPatientModel.patient_id)
        if patient_conditions:
            sub_patients = sub_patients.where(*patient_conditions)

        stmt = (
            select(
                AnonImagingStudyModel.modality.label("modality"),
                func.count(AnonDicomSeriesModel.series_id).label("series_count"),
                func.coalesce(
                    func.sum(AnonDicomSeriesModel.instance_count), 0
                ).label("instance_count"),
                func.coalesce(
                    func.sum(AnonDicomSeriesModel.byte_size), 0
                ).label("total_bytes"),
            )
            .select_from(AnonDicomSeriesModel)
            .join(
                AnonImagingStudyModel,
                AnonImagingStudyModel.dicom_study_uid
                == AnonDicomSeriesModel.dicom_study_uid,
            )
            .where(AnonImagingStudyModel.patient_id.in_(sub_patients))
            .group_by(AnonImagingStudyModel.modality)
            .order_by(func.count(AnonDicomSeriesModel.series_id).desc())
        )
        rows = (await self.db.execute(stmt)).all()
        label_map = await self._load_dict_labels("med_exam_type")
        return [
            {
                "modality": modality,
                "label": label_map.get(modality, modality),
                "series_count": int(s_count),
                "instance_count": int(i_count),
                "total_bytes": int(t_bytes),
            }
            for modality, s_count, i_count, t_bytes in rows
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

    # ── 患者列表查询 ──────────────────────────

    async def patient_list(
        self, current: int = 1, size: int = 10
    ) -> dict[str, Any]:
        """分页查询患者列表。"""
        conditions = self._patient_filters()
        offset = (current - 1) * size

        # 总数统计
        total_stmt = (
            select(func.count())
            .select_from(AnonPatientModel)
            .where(*conditions)
        )
        total = int((await self.db.execute(total_stmt)).scalar_one())

        # 分页数据
        list_stmt = (
            select(
                AnonPatientModel.patient_id,
                AnonPatientModel.center_code,
                AnonPatientModel.birth_date,
                AnonPatientModel.sex,
                AnonPatientModel.ethnicity,
                AnonPatientModel.smoking_status,
                AnonPatientModel.abo_blood_type,
                AnonPatientModel.rh_blood_type,
                AnonPatientModel.native_place,
                AnonPatientModel.bmi,
                AnonPatientModel.first_nodule_date,
            )
            .where(*conditions)
            .order_by(AnonPatientModel.patient_id.desc())
            .offset(offset)
            .limit(size)
        )
        result = await self.db.execute(list_stmt)
        items = []
        for row in result.all():
            item = row._asdict()
            item["age"] = _calc_age(item.get("birth_date"))
            items.append(item)

        return {
            "total": total,
            "current": current,
            "size": size,
            "items": items,
        }

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
