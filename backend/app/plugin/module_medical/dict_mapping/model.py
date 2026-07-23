"""医疗字典值映射模型 — 医院原始标签 → 标准字典值。

设计要点：
- DictMappingModel：可配置的映射规则，多家医院可配置不同的 raw_label → 同一 dict_value。
  例如：医院 A 上报"男性"、医院 B 上报"m"，均可映射到 dict_value='M'。
- DictUnmatchedModel：记录 ETL 过程中遇到的无映射规则的原始标签，供人工干预。
  系统自动累加 occurrence_count，管理员后续补充映射或标记忽略。
- 表达式唯一约束 (hospital_id, dict_type_id, lower(raw_label))：消除大小写差异，
  "Male" 和 "male" 视为同一条映射。
"""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base_model import ModelMixin, TenantMixin, UserMixin


class DictMappingModel(ModelMixin, TenantMixin, UserMixin):
    """医疗字典值映射表 — 医院原始标签 → 标准字典值。

    粒度：(医院, 字典类型, 原始标签) → 标准字典数据。
    同一标准值可被多家医院的不同标签映射（多对一归一化）。
    """

    __tablename__ = "med_dict_mapping"
    __table_args__ = (
        # 注意：表达式唯一约束 lower(raw_label) 由迁移脚本原生 SQL 创建，
        # ORM 层仅声明普通列唯一约束（避免 text() 在 UniqueConstraint 中触发 "unnamed column" 错误）
        UniqueConstraint(
            "hospital_id", "dict_type_id", "raw_label",
            name="uq_med_dict_mapping",
        ),
        Index("ix_med_dict_mapping_hospital", "hospital_id"),
        Index("ix_med_dict_mapping_dict_type", "dict_type_id"),
        {"comment": "医疗字典值映射表（医院原始标签 → 标准字典值）"},
    )

    hospital_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("med_hospital.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属医院",
    )
    dict_type_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sys_dict_type.id", ondelete="CASCADE"),
        nullable=False,
        comment="字典类型ID",
    )
    dict_data_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("sys_dict_data.id", ondelete="CASCADE"),
        nullable=True,
        comment="映射到的字典数据ID（为空表示暂未指定标准值）",
    )
    raw_label: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="原始标签（医院上报文本）",
    )
    raw_value: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="原始值（如有，供参考）",
    )

    # 关联
    hospital: Mapped["HospitalModel"] = relationship(
        "HospitalModel", lazy="selectin", back_populates="dict_mappings",
    )
    dict_type: Mapped["DictTypeModel"] = relationship("DictTypeModel", lazy="selectin")
    dict_data: Mapped["DictDataModel | None"] = relationship("DictDataModel", lazy="selectin")


class DictUnmatchedModel(ModelMixin):
    """医疗字典未匹配记录 — ETL 过程中遇到的无映射规则的原始标签。

    系统自动写入（不继承 UserMixin），管理员后续处理：
    - 补充映射规则（resolution='resolve'，关联到 resolved_as_mapping_id）
    - 标记忽略（resolution='ignore'，不再提醒）

    status: 0=未处理, 1=已忽略, 2=已解决
    """

    __tablename__ = "med_dict_unmatched"
    __table_args__ = (
        UniqueConstraint(
            "hospital_id", "dict_type_id", "raw_label",
            name="uq_med_dict_unmatched",
        ),
        # 注意：不显式定义 status 索引，因为 ModelMixin.status 已有 index=True（自动生成同名索引）
        Index("ix_med_dict_unmatched_hospital", "hospital_id"),
        Index("ix_med_dict_unmatched_dict_type", "dict_type_id"),
        {"comment": "医疗字典未匹配记录（待人工干预）"},
    )

    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sys_tenant.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
        comment="租户ID",
    )
    hospital_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("med_hospital.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属医院",
    )
    dict_type_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sys_dict_type.id", ondelete="CASCADE"),
        nullable=False,
        comment="字典类型ID",
    )
    raw_label: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="原始标签",
    )
    raw_value: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="原始值",
    )
    occurrence_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="出现次数（UPSERT 累加）",
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="最近出现时间",
    )
    resolution: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="处理方式(ignore/resolve)",
    )
    resolved_by: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="处理人ID",
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="处理时间",
    )
    resolved_as_mapping_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("med_dict_mapping.id", ondelete="SET NULL"),
        nullable=True,
        comment="解决为的映射ID",
    )

    # 关联
    hospital: Mapped["HospitalModel"] = relationship("HospitalModel", lazy="selectin")
    dict_type: Mapped["DictTypeModel"] = relationship("DictTypeModel", lazy="selectin")
    resolved_as_mapping: Mapped["DictMappingModel | None"] = relationship(
        "DictMappingModel", lazy="selectin",
    )
