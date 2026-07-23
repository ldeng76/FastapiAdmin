"""医疗字典值映射 — Pydantic 请求/响应模型。"""

from datetime import datetime

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.common.enums import QueueEnum
from app.core.base_schema import BaseSchema


# --------------------------------------------------------------------------- #
# DictMapping
# --------------------------------------------------------------------------- #


class DictMappingCreateSchema(BaseModel):
    """创建映射规则。"""

    hospital_id: int = Field(..., ge=1, description="医院ID")
    dict_type_id: int = Field(..., ge=1, description="字典类型ID")
    dict_data_id: int | None = Field(None, ge=1, description="映射到的字典数据ID")
    raw_label: str = Field(..., max_length=200, description="原始标签")
    raw_value: str | None = Field(None, max_length=200, description="原始值")

    @field_validator("raw_label")
    @classmethod
    def validate_raw_label(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("原始标签不能为空")
        return value.strip()


class DictMappingUpdateSchema(BaseModel):
    """更新映射规则（所有字段可选，支持部分更新）。"""

    hospital_id: int | None = Field(None, ge=1, description="医院ID")
    dict_type_id: int | None = Field(None, ge=1, description="字典类型ID")
    dict_data_id: int | None = Field(None, ge=1, description="映射到的字典数据ID")
    raw_label: str | None = Field(None, max_length=200, description="原始标签")
    raw_value: str | None = Field(None, max_length=200, description="原始值")

    @field_validator("raw_label")
    @classmethod
    def validate_raw_label(cls, v: str | None) -> str | None:
        """原始标签非空时去首尾空格。"""
        if v is not None and not v.strip():
            raise ValueError("原始标签不能为空")
        return v.strip() if v is not None else None


class DictMappingOutSchema(DictMappingCreateSchema, BaseSchema):
    """映射规则响应模型。"""

    model_config = ConfigDict(from_attributes=True)

    dict_type_name: str | None = Field(None, description="字典类型名称")
    dict_data_label: str | None = Field(None, description="标准字典标签")
    dict_data_value: str | None = Field(None, description="标准字典值")


class DictMappingQueryParam:
    """映射规则查询参数。"""

    def __init__(
        self,
        hospital_id: int | None = Query(None, description="医院ID"),
        dict_type_id: int | None = Query(None, description="字典类型ID"),
        raw_label: str | None = Query(None, description="原始标签"),
        status: str | None = Query(None, description="状态"),
    ) -> None:
        self.hospital_id = (QueueEnum.eq.value, hospital_id)
        self.dict_type_id = (QueueEnum.eq.value, dict_type_id)
        self.raw_label = (QueueEnum.like.value, raw_label)
        self.status = (QueueEnum.eq.value, status)


class DictMappingBatchSchema(BaseModel):
    """批量创建映射规则。"""

    items: list[DictMappingCreateSchema] = Field(..., min_length=1, description="映射规则列表")


# --------------------------------------------------------------------------- #
# DictUnmatched
# --------------------------------------------------------------------------- #


class DictUnmatchedOutSchema(BaseModel):
    """未匹配记录响应模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    hospital_id: int
    dict_type_id: int
    dict_type_name: str | None = None
    raw_label: str
    raw_value: str | None = None
    occurrence_count: int
    last_seen_at: datetime | None = None
    resolution: str | None = None


class DictUnmatchedQueryParam:
    """未匹配记录查询参数。"""

    def __init__(
        self,
        hospital_id: int | None = Query(None, description="医院ID"),
        dict_type_id: int | None = Query(None, description="字典类型ID"),
        status: str | None = Query(None, description="状态"),
    ) -> None:
        self.hospital_id = (QueueEnum.eq.value, hospital_id)
        self.dict_type_id = (QueueEnum.eq.value, dict_type_id)
        self.status = (QueueEnum.eq.value, status)


class UnmatchedResolveSchema(BaseModel):
    """解决未匹配记录。"""

    mapping_id: int | None = Field(None, description="关联映射ID（为空则仅标记忽略）")


# --------------------------------------------------------------------------- #
# Normalize（运行时 API）
# --------------------------------------------------------------------------- #


class NormalizeIn(BaseModel):
    """单值归一化请求。"""

    hospital_id: int = Field(..., ge=1, description="医院ID")
    dict_type: str = Field(..., min_length=1, description="字典类型（如 med_sex）")
    raw_label: str = Field(..., max_length=200, description="原始标签")

    @field_validator("raw_label")
    @classmethod
    def validate_raw_label(cls, v: str) -> str:
        """原始标签去首尾空格，拒绝空白。与 DictMappingCreateSchema 对齐。"""
        if not v or not v.strip():
            raise ValueError("原始标签不能为空")
        return v.strip()


class NormalizeBatchIn(BaseModel):
    """批量归一化请求。"""

    hospital_id: int = Field(..., ge=1, description="医院ID")
    dict_type: str = Field(..., min_length=1, description="字典类型")
    raw_labels: list[str] = Field(..., min_length=1, description="原始标签列表")


class NormalizeResult(BaseModel):
    """归一化结果。"""

    raw_label: str
    dict_value: str | None = None
    matched: bool


# --------------------------------------------------------------------------- #
# Backfill（异步任务签名占位）
# --------------------------------------------------------------------------- #


class BackfillIn(BaseModel):
    """回填请求（骨架，完整实现留待后续）。"""

    table: str = Field(..., description="目标表名")
    field: str = Field(..., description="目标字段名")
    dict_type: str = Field(..., description="字典类型")
    hospital_id: int = Field(..., ge=1, description="医院ID")
