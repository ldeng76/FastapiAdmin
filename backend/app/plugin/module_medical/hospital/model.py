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


# --------------------------------------------------------------------------- #
# 医疗数据统一表
# --------------------------------------------------------------------------- #


class PatientModel(ModelMixin, TenantMixin, UserMixin):
    """患者基本信息表（统一表）。

    粒度：每患者一行。业务主键 (tenant_id, patient_id)。
    tenant_id 仅作数据来源标记，不做访问隔离（ADR 0005）。
    """

    __tablename__ = "med_patient"
    __table_args__ = (
        UniqueConstraint("tenant_id", "patient_id", name="uq_med_patient_tenant_patient"),
        {"comment": "患者基本信息表（统一表）"},
    )

    patient_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="患者编号")
    source_center: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="来源中心")
    gender: Mapped[str | None] = mapped_column(String(10), nullable=True, comment="性别")
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="出生日期")
    ethnicity: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="民族")
    native_place: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="籍贯")
    abo_blood_type: Mapped[str | None] = mapped_column(String(10), nullable=True, comment="ABO血型")
    rh_blood_type: Mapped[str | None] = mapped_column(String(10), nullable=True, comment="RH血型")
    smoking_status: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="吸烟状态")
    first_nodule_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="首次发现结节日期")

    # JSON 扩展字段
    demographics: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="人口学扩展")
    medical_history: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="既往病史")


class PathologySpecimenModel(ModelMixin, TenantMixin, UserMixin):
    """病理标本表（统一表）。粒度：每份病理标本/报告一行。"""

    __tablename__ = "med_pathology_specimen"
    __table_args__ = (
        UniqueConstraint("tenant_id", "specimen_id", name="uq_med_pathology_specimen_tenant_specimen"),
        {"comment": "病理标本表（统一表）"},
    )

    patient_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="患者编号")
    visit_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="就诊编号")
    specimen_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="标本号")
    submission_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="送检日期")
    report_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="报告日期")
    specimen_type: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="标本类型")
    sampling_site: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="取材部位")
    specimen_name: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="标本名称")
    exam_name: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="检查名称")
    exam_type: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="检查类型")
    exam_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="检查日期")
    histology_class: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="组织学大类")
    pathology_diagnosis: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="病理诊断")
    tumor_total_size_mm: Mapped[float | None] = mapped_column(Float, nullable=True, comment="肿瘤总大小(mm)")

    # JSON 扩展字段
    exam_detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="检查详情")
    specimen_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="标本元数据")
    adenocarcinoma_subtypes: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="腺癌亚型")
    tumor_measurement: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="肿瘤测量")
    high_risk_factors: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="高危因素")
    staging: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="病理分期")
    exam_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="检查元数据")


class SurgeryRecordModel(ModelMixin, TenantMixin, UserMixin):
    """手术记录表（统一表）。粒度：每次手术一行。"""

    __tablename__ = "med_surgery_record"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "patient_id", "surgery_date", "procedure_name",
            name="uq_med_surgery_record_tenant_patient_date_proc",
        ),
        {"comment": "手术记录表（统一表）"},
    )

    patient_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="患者编号")
    visit_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="就诊编号")
    surgery_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="手术日期")
    procedure_name: Mapped[str] = mapped_column(String(200), nullable=False, comment="手术及操作名称")
    resection_scope: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="切除范围")
    surgical_approach: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="手术入路")

    # JSON 扩展字段
    procedure_detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="手术详情")


class GeneticTestModel(ModelMixin, TenantMixin, UserMixin):
    """基因检测表（统一表）。粒度：每份基因检测报告一行。"""

    __tablename__ = "med_genetic_test"
    __table_args__ = (
        UniqueConstraint("tenant_id", "test_id", name="uq_med_genetic_test_tenant_test"),
        {"comment": "基因检测表（统一表）"},
    )

    patient_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="患者编号")
    visit_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="就诊编号")
    test_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="检测唯一号")
    test_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="检测日期")
    variant_type: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="变异类型")
    test_method: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="检测方法")

    # JSON 扩展字段
    test_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="检测元数据")
    variant_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="变异结果")
    driver_mutations: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="驱动基因突变")
    immune_markers: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="免疫相关标志物")


class NoduleImagingModel(ModelMixin, TenantMixin, UserMixin):
    """结节影像表（珠江-新桥独有）。粒度：一次CT中的一个结节。"""

    __tablename__ = "med_nodule_imaging"
    __table_args__ = (
        UniqueConstraint("tenant_id", "exam_id", "nodule_no", name="uq_med_nodule_imaging_tenant_exam_nodule"),
        {"comment": "结节影像表"},
    )

    patient_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="患者编号")
    exam_id: Mapped[str] = mapped_column(Text, nullable=False, comment="检查唯一号（可能含多个逗号分隔ID）")
    exam_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="检查日期时间")
    exam_type: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="检查类型")
    nodule_no: Mapped[str] = mapped_column(
        String(20), nullable=False, default="UNKNOWN",
        comment="结节编号（源数据为空时填哨兵值 UNKNOWN，保证唯一约束有效）",
    )
    nodule_location: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="结节位置")
    long_diameter: Mapped[float | None] = mapped_column(Float, nullable=True, comment="长径(mm)")
    density_type: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="密度类型")

    # JSON 扩展字段
    exam_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="检查元数据")
    nodule_morphology: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="结节形态")
    nodule_quantitative: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="结节定量")
    follow_up_comparison: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="对比既往")


class IHCResultModel(ModelMixin, TenantMixin, UserMixin):
    """免疫组化结果表（珠江-新桥独有）。粒度：每份标本的免疫组化一行。"""

    __tablename__ = "med_ihc_result"
    __table_args__ = (
        UniqueConstraint("tenant_id", "specimen_id", name="uq_med_ihc_result_tenant_specimen"),
        {"comment": "免疫组化结果表"},
    )

    patient_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="患者编号")
    specimen_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="病理标本号")
    ki67_pct: Mapped[float | None] = mapped_column(Float, nullable=True, comment="Ki-67(%)")

    # JSON 扩展字段
    markers: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="免疫组化标志物")


class FollowUpModel(ModelMixin, TenantMixin, UserMixin):
    """随访结局表（珠江-新桥独有）。粒度：每患者一行。"""

    __tablename__ = "med_follow_up"
    __table_args__ = (
        UniqueConstraint("tenant_id", "patient_id", name="uq_med_follow_up_tenant_patient"),
        {"comment": "随访结局表"},
    )

    patient_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="患者编号")
    last_followup_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="末次随访日期")
    recurrence: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="是否复发")
    survival_status: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="生存状态")

    # JSON 扩展字段
    treatment_detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="辅助治疗详情")
    recurrence_detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="复发详情")


# 目标表名 → ORM 模型映射（供 ETL 引擎和查询层使用）
TGT_TABLE_MODELS: dict[str, type[ModelMixin]] = {
    "med_patient": PatientModel,
    "med_pathology_specimen": PathologySpecimenModel,
    "med_surgery_record": SurgeryRecordModel,
    "med_genetic_test": GeneticTestModel,
    "med_nodule_imaging": NoduleImagingModel,
    "med_ihc_result": IHCResultModel,
    "med_follow_up": FollowUpModel,
}
