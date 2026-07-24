"""医院管理模块 Pydantic schema（2026-07-24 清理）。

清理说明：
- 删了 med_* 业务表相关 schema（PatientListOut/PatientPageOut/PatientDetailOut）
- 删了 mapping rule 相关 schema（MappingRuleIn/Out/Batch + TemplateOut/Detail）
- 删了 ETL-1/2 旧 schema（EtlImportResponse/Status, Etl1Run*, Etl1Status）
- 删了 HospitalDataSummaryOut（med_* 数据摘要，anon 版由 AnonDataSummaryOut 替代）
- 保留 3 个医院 CRUD schema（HospitalCreate/Update/Out）— 医院注册/管理仍需
- 保留 3 个 anon schema（AnonImportTriggerRequest/Status/AnonDataSummaryOut）— 批次 2/5 新增
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.base_schema import BaseSchema


# =========================================================================== #
# 医院 CRUD（保留：医院注册/管理仍需）
# =========================================================================== #


class HospitalCreate(BaseModel):
    """注册医院入参"""

    code: str = Field(..., min_length=1, max_length=50, description="医院编码（全局唯一）")
    name: str = Field(..., min_length=1, max_length=100, description="医院名称")
    full_name: str | None = Field(None, max_length=200, description="医院全称")
    data_dir: str | None = Field(None, max_length=500, description="原始数据目录路径（parquet 所在目录）")
    contact_name: str | None = Field(None, max_length=64, description="联系人")
    contact_phone: str | None = Field(None, max_length=20, description="联系电话")
    contact_email: str | None = Field(None, max_length=128, description="联系邮箱")
    address: str | None = Field(None, max_length=255, description="机构地址")


class HospitalUpdate(BaseModel):
    """更新医院入参（全字段可选）"""

    name: str | None = Field(None, min_length=1, max_length=100)
    full_name: str | None = Field(None, max_length=200)
    data_dir: str | None = Field(None, max_length=500)
    contact_name: str | None = Field(None, max_length=64)
    contact_phone: str | None = Field(None, max_length=20)
    contact_email: str | None = Field(None, max_length=128)
    address: str | None = Field(None, max_length=255)


class HospitalOut(HospitalCreate, BaseSchema):
    """医院出参（包含 lifecycle_status 等动态字段）"""

    id: int
    tenant_id: int
    lifecycle_status: str
    last_import_time: datetime | None = None
    last_import_rows: int = 0
    import_error: str | None = None


# =========================================================================== #
# anon ETL 导入（2026-07-24 补全）
# =========================================================================== #


class AnonImportTriggerRequest(BaseModel):
    """anon ETL 导入触发请求体（可选字段，不传则走默认）"""

    center_codes: list[str] | None = Field(
        default=None,
        description="要导入的中心列表（shengyi/xinqiao/zhujiang）；None=全部",
    )
    data_dir_override: str | None = Field(
        default=None,
        description="覆盖 hospital.data_dir（临时指定 parquet 路径）",
    )


class AnonImportStatus(BaseModel):
    """anon ETL 导入状态（轮询返回）"""

    job_id: str = Field(default="", description="任务ID")
    status: str = Field(default="idle", description="状态(idle/pending/running/completed/failed)")
    total: int = Field(default=0, description="总行数")
    processed: int = Field(default=0, description="已处理行数")
    centers: list[str] = Field(default_factory=list, description="本次导入的中心列表")
    error: str | None = Field(default=None, description="错误信息")
    started_at: datetime | None = Field(default=None, description="开始时间")
    completed_at: datetime | None = Field(default=None, description="完成时间")
    results: list[dict] | None = Field(
        default=None,
        description="每中心导入结果 [{center, status, rows, batch_id, error?}]（仅 completed）",
    )


class AnonDataSummaryOut(BaseModel):
    """anon 数据摘要出参（lnrs_anon_* 各表行数）"""

    hospital_id: int = Field(..., description="医院ID")
    lifecycle_status: str = Field(..., description="就绪状态")
    center_codes: list[str] = Field(default_factory=list, description="统计的中心列表")
    total_rows: int = Field(..., description="各表行数合计")
    tables: dict[str, int] = Field(
        default_factory=dict,
        description="每张 anon 表的行数（key: patient/exam/report_text/exam_detail/visit/surgery/ingest_batch）",
    )
