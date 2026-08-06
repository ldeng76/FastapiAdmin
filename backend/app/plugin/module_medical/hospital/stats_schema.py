"""数据统计模块 Pydantic schema — 数据概览仪表板出参。

采用维度数组结构（ADR-0007 决策 4），支持未来新增维度而无需改前端：
- filters: 可选筛选条件及其当前值
- kpi: 核心指标卡数组
- dimensions: 维度数组，每项含 chart_type + data，前端按 chart_type 选组件渲染
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

# 图表类型枚举 — 前端按此字段选渲染组件
ChartType = Literal["bar", "pie", "h-bar", "line"]


# ── 查询参数 ──────────────────────────────────

class StatsFiltersIn(BaseModel):
    """仪表板查询筛选参数（封装所有 Query 参数）。"""

    center: str | None = Field(None, description="中心编码筛选")
    gender: str | None = Field(None, description="性别筛选（0=未知, 1=男, 2=女, 9=其他）")
    modality: str | None = Field(None, description="模态筛选（如 CT/MR/US 等）")
    age_bucket: str | None = Field(None, description="年龄段筛选（0-17/18-29/30-39/40-49/50-59/60-69/70-79/80+）")
    abo_blood_type: str | None = Field(None, description="ABO血型筛选（1=A型, 2=B型, 3=O型, 4=AB型, 5=不详, 6=未查）")
    smoking_status: str | None = Field(None, description="吸烟状态筛选（1=从不, 2=既往, 3=现在, 9=未知）")


# ── 筛选条件 ──────────────────────────────────


class FilterOption(BaseModel):
    """单个筛选项的当前状态 + 可选值。"""

    applied: str | None = Field(None, description="当前应用的筛选值（null=未筛选）")
    options: list[str] | list[dict[str, Any]] | dict[str, Any] | None = Field(None, description="可选值列表")


class FiltersOut(BaseModel):
    """仪表板可用的筛选条件。"""

    center: FilterOption | None = Field(None, description="按中心筛选")
    gender: FilterOption | None = Field(None, description="按性别筛选")
    modality: FilterOption | None = Field(None, description="按模态筛选")
    age_bucket: FilterOption | None = Field(None, description="按年龄段筛选")
    abo_blood_type: FilterOption | None = Field(None, description="按ABO血型筛选")
    smoking_status: FilterOption | None = Field(None, description="按吸烟状态筛选")
    year_range: FilterOption | None = Field(None, description="按年份范围筛选")


# ── KPI 卡 ───────────────────────────────────


class KpiOut(BaseModel):
    """单个 KPI 指标卡。"""

    key: str = Field(..., description="指标标识")
    label: str = Field(..., description="显示标签")
    value: int = Field(..., description="指标值")
    format: Literal["number", "wan"] = Field(default="number", description="显示格式")


# ── 维度 ─────────────────────────────────────


class DimensionOut(BaseModel):
    """单个统计维度 — 前端按 chart_type 选图表组件渲染。"""

    key: str = Field(..., description="维度标识")
    label: str = Field(..., description="显示标签")
    chart_type: Annotated[ChartType, Field(..., description="图表类型 → 前端选组件")]
    data: list[dict[str, Any]] = Field(..., description="图表数据")


# ── 总出参 ───────────────────────────────────


class DashboardOverviewOut(BaseModel):
    """仪表板全量概览 — 维度数组结构（ADR-0007）。"""

    filters: FiltersOut | None = Field(None, description="可用筛选条件")
    kpis: list[KpiOut] = Field(..., description="KPI 指标卡数组")
    dimensions: list[DimensionOut] = Field(..., description="统计维度数组")
