"""医院注册表模型 — 平台级元数据。

设计要点：
- 每家医院对应一个租户（sys_tenant），通过 tenant_id 外键关联。
- 不继承 TenantMixin：作为平台级元数据，所有超管可见全部医院记录，
  不按 tenant_id 做访问隔离（详见 ADR 0001、0004）。
- 就绪状态用 lifecycle_status 字段，与 ModelMixin.status（启用/禁用开关）正交。
"""

from datetime import date, datetime
from enum import Enum

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base_model import ModelMixin, TenantMixin, UserMixin


class HospitalStatus(str, Enum):
    """医院就绪状态（生命周期）"""

    REGISTERED = "registered"               # 已注册
    MAPPING_CONFIGURED = "mapping_configured"  # 映射已配置
    DATA_IMPORTED = "data_imported"         # 数据已导入
    LIVE = "live"                           # 已上线


class HospitalModel(ModelMixin, UserMixin):
    """医院注册表 — 平台级元数据，每家医院对应一个租户。

    不继承 TenantMixin：所有超管/医院管理员可见全部医院记录，
    通过 API 权限点 hospital:query 控制访问，而非 tenant_id 过滤。
    """

    __tablename__ = "med_hospital"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_med_hospital_tenant"),
        {"comment": "医院注册表（平台级元数据）"},
    )

    # 医院基本信息
    code: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, comment="医院编码（shengyi / zhujiang_xinqiao）"
    )
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="医院名称"
    )
    full_name: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="医院全称"
    )

    # 租户关联（数据来源标记，不做访问隔离）
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sys_tenant.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
        comment="关联租户ID",
    )

    # 就绪状态（与 ModelMixin.status 正交：后者是启用/禁用开关）
    lifecycle_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=HospitalStatus.REGISTERED.value,
        index=True,
        comment="就绪状态(registered/mapping_configured/data_imported/live)",
    )

    # 机构信息
    contact_name: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="联系人")
    contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="联系电话")
    contact_email: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="联系邮箱")
    address: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="机构地址")

    # 数据目录（ETL 读取 parquet 的路径，相对项目根或绝对路径）
    data_dir: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="原始数据目录路径（parquet 文件所在目录）"
    )

    # 数据导入
    last_import_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="最近导入时间"
    )
    last_import_rows: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="最近导入行数"
    )
    import_error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="导入失败时的错误信息"
    )

    # 关联
    tenant: Mapped["TenantModel"] = relationship("TenantModel", lazy="selectin")
    mapping_rules: Mapped[list["MappingRuleModel"]] = relationship(
        "MappingRuleModel",
        lazy="selectin",
        back_populates="hospital",
        cascade="all, delete-orphan",
    )
    dict_mappings: Mapped[list["DictMappingModel"]] = relationship(
        "DictMappingModel",
        lazy="selectin",
        back_populates="hospital",
        cascade="all, delete-orphan",
    )


class MappingTransform(str, Enum):
    """映射转换类型"""

    RENAME = "rename"           # 字段重命名（源字段名→目标字段名，值不变）
    CONSTANT = "constant"       # 常量填充（目标字段 = 固定值）
    EXPRESSION = "expression"   # 表达式变换（目标字段 = 注册函数 key，见 ETL 引擎）
    DICT = "dict"               # 字典映射（目标字段 = 标准字典值，通过 med_dict_mapping 配置）


class MappingRuleModel(ModelMixin, UserMixin):
    """字段映射规则 — (源表, 源字段) → (目标表, 目标字段, 转换)

    每家医院的映射规则独立存储，注册时可从模板复制，之后可自由编辑。
    """

    __tablename__ = "med_mapping_rule"
    __table_args__ = (
        UniqueConstraint(
            "hospital_id", "src_table", "src_field",
            name="uq_med_mapping_rule",
        ),
        {"comment": "字段映射规则表"},
    )

    hospital_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("med_hospital.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属医院",
    )

    # 源
    src_table: Mapped[str] = mapped_column(String(100), nullable=False, comment="源表名")
    src_field: Mapped[str] = mapped_column(String(100), nullable=False, comment="源字段名")

    # 目标
    tgt_table: Mapped[str] = mapped_column(String(100), nullable=False, comment="目标表名")
    tgt_field: Mapped[str] = mapped_column(String(100), nullable=False, comment="目标字段名")

    # 转换
    transform_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=MappingTransform.RENAME.value,
        comment="转换类型(rename/constant/expression/dict)",
    )
    transform_value: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="转换值（CONSTANT=常量值 / EXPRESSION=注册函数 key / DICT=dict_type名 / RENAME=空）",
    )

    description: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="规则说明"
    )
    sort: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="执行顺序（先核心字段后扩展）"
    )

    # 关联
    hospital: Mapped["HospitalModel"] = relationship(
        "HospitalModel", lazy="selectin", back_populates="mapping_rules"
    )

