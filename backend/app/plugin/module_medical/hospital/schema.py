"""医院管理模块 Pydantic schema。

字段说明：
- code/name 必填，作为医院身份字段，注册后不可修改。
- tenant_id 由 service 层自动填入（关联 sys_tenant），不由前端传入。
- lifecycle_status 由 service 层状态机管理，前端不可直接改。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.enums import QueueEnum
from app.core.base_schema import BaseSchema
from app.core.validator import DateTimeStr


class HospitalCreate(BaseModel):
    """医院注册入参"""

    code: str = Field(..., max_length=50, description="医院编码")
    name: str = Field(..., max_length=100, description="医院名称")
    full_name: str | None = Field(default=None, max_length=200, description="医院全称")
    contact_name: str | None = Field(default=None, max_length=64, description="联系人")
    contact_phone: str | None = Field(default=None, max_length=20, description="联系电话")
    contact_email: str | None = Field(default=None, max_length=128, description="联系邮箱")
    address: str | None = Field(default=None, max_length=255, description="机构地址")
    data_dir: str | None = Field(default=None, max_length=500, description="原始数据目录路径")
    template_code: str | None = Field(
        default=None, max_length=50, description="映射模板编码（注册时预填映射规则）"
    )

    @field_validator("code")
    @classmethod
    def _validate_code(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("编码不能为空")
        # 允许字母、数字、下划线（center_code 如 zhujiang_xinqiao 含下划线）
        if not re.match(r"^[A-Za-z0-9_]+$", v):
            raise ValueError("编码只能包含字母、数字和下划线")
        return v

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("名称不能为空")
        return v


class HospitalUpdate(BaseModel):
    """医院更新入参 — 不允许修改 code/tenant_id（身份字段）"""

    name: str | None = Field(default=None, max_length=100, description="医院名称")
    full_name: str | None = Field(default=None, max_length=200, description="医院全称")
    contact_name: str | None = Field(default=None, max_length=64, description="联系人")
    contact_phone: str | None = Field(default=None, max_length=20, description="联系电话")
    contact_email: str | None = Field(default=None, max_length=128, description="联系邮箱")
    address: str | None = Field(default=None, max_length=255, description="机构地址")
    data_dir: str | None = Field(default=None, max_length=500, description="原始数据目录路径")


class HospitalOut(HospitalCreate, BaseSchema):
    """医院出参 — 含 id/审计字段/tenant_id/lifecycle_status"""

    model_config = ConfigDict(from_attributes=True)

    tenant_id: int = Field(..., description="关联租户ID")
    lifecycle_status: str = Field(..., description="就绪状态")
    data_dir: str | None = Field(default=None, description="原始数据目录路径")
    last_import_time: DateTimeStr | None = Field(default=None, description="最近导入时间")
    last_import_rows: int = Field(default=0, description="最近导入行数")


class HospitalDataSummaryOut(BaseModel):
    """医院数据摘要出参（各业务表行数）"""

    hospital_id: int = Field(..., description="医院ID")
    lifecycle_status: str = Field(..., description="就绪状态")
    tenant_id: int = Field(..., description="租户ID")
    total_rows: int = Field(..., description="各表行数合计")
    tables: dict[str, int] = Field(default_factory=dict, description="每张业务表的行数（key=表名）")


class HospitalQueryParam:
    """医院查询参数 — 支持 name/code/lifecycle_status 筛选"""

    def __init__(
        self,
        name: str | None = Query(None, description="医院名称（模糊）"),
        code: str | None = Query(None, description="医院编码（模糊）"),
        lifecycle_status: str | None = Query(
            None, description="就绪状态(registered/mapping_configured/data_imported/live)"
        ),
        status: str | None = Query(None, description="启用状态(0:正常 1:禁用)"),
        created_time: list[DateTimeStr] | None = Query(
            None,
            description="创建时间范围",
            examples=["2025-01-01 00:00:00", "2025-12-31 23:59:59"],
        ),
    ) -> None:
        if name:
            self.name = (QueueEnum.like.value, name)
        if code:
            self.code = (QueueEnum.like.value, code)
        if lifecycle_status:
            self.lifecycle_status = (QueueEnum.eq.value, lifecycle_status)
        if status:
            self.status = (QueueEnum.eq.value, status)
        if created_time and len(created_time) == 2:
            self.created_time = (
                QueueEnum.between.value,
                (created_time[0], created_time[1]),
            )


# --------------------------------------------------------------------------- #
# 映射规则
# --------------------------------------------------------------------------- #


class MappingRuleIn(BaseModel):
    """单条映射规则入参"""

    src_table: str = Field(..., max_length=100, description="源表名")
    src_field: str = Field(..., max_length=100, description="源字段名")
    tgt_table: str = Field(..., max_length=100, description="目标表名")
    tgt_field: str = Field(..., max_length=100, description="目标字段名")
    transform_type: str = Field(default="rename", description="转换类型(rename/constant/expression)")
    transform_value: str | None = Field(default=None, description="转换值")
    description: str | None = Field(default=None, max_length=255, description="规则说明")
    sort: int = Field(default=0, description="执行顺序")

    @field_validator("transform_type")
    @classmethod
    def _validate_transform_type(cls, v: str) -> str:
        allowed = {"rename", "constant", "expression"}
        if v not in allowed:
            raise ValueError(f"transform_type 只能是 {allowed} 之一")
        return v

    @model_validator(mode="after")
    def _validate_transform_value(self):
        """constant/expression 必须有 transform_value；rename 忽略。"""
        if self.transform_type in ("constant", "expression") and not self.transform_value:
            raise ValueError(f"transform_type={self.transform_type} 时 transform_value 不能为空")
        return self


class MappingRuleOut(MappingRuleIn, BaseSchema):
    """映射规则出参"""

    model_config = ConfigDict(from_attributes=True)

    hospital_id: int = Field(..., description="所属医院ID")


class MappingRuleBatch(BaseModel):
    """批量替换映射规则 — 全量替换该医院的映射规则集"""

    rules: list[MappingRuleIn] = Field(..., description="规则列表（全量替换）")


# --------------------------------------------------------------------------- #
# 映射模板
# --------------------------------------------------------------------------- #


class TemplateOut(BaseModel):
    """映射模板出参"""

    code: str = Field(..., description="模板编码")
    name: str = Field(..., description="模板名称")
    description: str = Field(..., description="模板说明")
    rule_count: int = Field(..., description="规则数量")


class MappingTemplateDetailOut(TemplateOut):
    """映射模板详情（含规则列表）"""

    rules: list[dict[str, Any]] = Field(default_factory=list, description="模板规则（与 MappingRuleIn 同结构）")


# --------------------------------------------------------------------------- #
# ETL 导入
# --------------------------------------------------------------------------- #


class EtlImportResponse(BaseModel):
    """ETL 导入触发响应"""

    job_id: str = Field(..., description="任务ID（用于轮询状态）")
    status: str = Field(..., description="初始状态(pending)")


class EtlImportStatus(BaseModel):
    """ETL 导入状态（轮询返回）"""

    job_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="状态(pending/running/completed/failed)")
    total: int = Field(default=0, description="总行数")
    processed: int = Field(default=0, description="已处理行数")
    error: str | None = Field(default=None, description="错误信息")
    started_at: DateTimeStr | None = Field(default=None, description="开始时间")
    completed_at: DateTimeStr | None = Field(default=None, description="完成时间")


# =========================================================================== #
# ETL-1: Excel → Parquet
# =========================================================================== #


class Etl1RunRequest(BaseModel):
    """ETL-1 触发请求体。"""

    xlsx_path: str = Field(
        ...,
        description="Excel 文件绝对路径或相对仓库根的路径 (服务器侧可访问)",
    )
    center_code: str | None = Field(
        default=None,
        description="医院代号 (shengyi/zhujiang_xinqiao...); 不传则用 hospital.code",
    )
    only_tables: list[str] | None = Field(
        default=None,
        description="只处理这些 target_table (开发期增量调试); 不传=全部",
    )
    dry_run: bool = Field(
        default=False,
        description="True 时只校验配置不写文件",
    )


class Etl1RunResponse(BaseModel):
    """ETL-1 触发响应。"""

    job_id: str = Field(..., description="任务ID (轮询状态用)")
    status: str = Field(..., description="初始状态(pending)")
    center_code: str = Field(..., description="实际使用的医院代号")


class Etl1Status(BaseModel):
    """ETL-1 任务状态 (轮询返回)。

    与 EtlImportStatus 的区别:
    - 多 current_table / tables_done / tables_total (按表粒度, 而非按行)
    - 多 target_tables / rows_per_table (完成后的明细)
    - xlsx_path / center_code 便于审计
    """

    job_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="状态(pending/running/completed/failed)")
    center_code: str = Field(default="", description="医院代号")
    xlsx_path: str = Field(default="", description="源 Excel 路径")
    tables_total: int = Field(default=0, description="目标表总数")
    tables_done: int = Field(default=0, description="已完成表数")
    current_table: str = Field(default="", description="正在处理的表名")
    total_rows: int = Field(default=0, description="累计行数")
    rows_per_table: dict[str, int] = Field(
        default_factory=dict, description="各表行数 (完成后填充)"
    )
    error: str | None = Field(default=None, description="错误信息")
    started_at: DateTimeStr | None = Field(default=None, description="开始时间")
    completed_at: DateTimeStr | None = Field(default=None, description="完成时间")
