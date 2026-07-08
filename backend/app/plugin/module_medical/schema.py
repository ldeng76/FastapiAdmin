"""医学数据模块 Pydantic schema。

字段宽松处理：多模态各行含 JSON 扩展列，结构因表而异，统一用 dict[str, Any] 承载。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PatientListOut(BaseModel):
    """患者列表行（核心字段，跨院统一）。"""

    patient_id: str = Field(..., description="患者编号")
    source_center: str | None = Field(None, description="来源中心")
    gender: str | None = Field(None, description="性别")
    birth_date: Any | None = Field(None, description="出生日期")
    ethnicity: str | None = Field(None, description="民族")
    native_place: str | None = Field(None, description="籍贯")
    abo_blood_type: str | None = Field(None, description="ABO血型")
    rh_blood_type: str | None = Field(None, description="RH血型")
    smoking_status: str | None = Field(None, description="吸烟状态")
    first_nodule_date: Any | None = Field(None, description="首次发现结节日期")


class PatientDetailOut(BaseModel):
    """患者多模态详情：基本信息 + 四模态分组（每组为行字典列表）。"""

    patient: dict[str, Any] = Field(..., description="患者基本信息（含 JSON 扩展列）")
    clinical: list[dict[str, Any]] = Field(default_factory=list, description="临床模态：就诊/手术/药物/检验/随访等")
    genetic: list[dict[str, Any]] = Field(default_factory=list, description="基因模态：基因检测记录")
    pathology: list[dict[str, Any]] = Field(default_factory=list, description="病理模态：病理标本")
    imaging: list[dict[str, Any]] = Field(default_factory=list, description="影像模态：影像学报告/结节影像")


class PatientPageOut(BaseModel):
    """患者分页响应（与 controller response_model 一致）。"""

    page_no: int = Field(..., description="页码（从 1 开始）")
    page_size: int = Field(..., description="每页大小")
    total: int = Field(..., description="总行数")
    has_next: bool = Field(..., description="是否还有下一页")
    items: list[PatientListOut] = Field(default_factory=list, description="当前页患者列表")
