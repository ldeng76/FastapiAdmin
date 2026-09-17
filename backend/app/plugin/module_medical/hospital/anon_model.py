"""lnrs_anon_* 脱敏窄表 ORM 模型 — ADR-0006。

与 `docs/adr/0006-anonymized-schema-lnrs.sql` 一一对应（schema='lnrs'）。
表自带主键（非自增 id），故**不继承 ModelMixin**，独立定义所有列。

实现范围（与用户确认的本轮 ETL-2 边界）：
- 落库：ingest_batch / patient / exam / report_text / phi_audit / exam_finding
- 本轮 finding 表实际不写入（自由文本不拆分），但模型保留
- dicom_series：ORM 模型已声明，ETL-2 增量阶段按 study 目录解析后落库
  （匿名 anon_exam_id 由 0012 imaging_study 回填；离线灌库场景下 anon_exam_id
  为空时跳过 series 落库，与 DDL NOT NULL 约束一致）
- 不建模：dicom_uid_map（按 ADR 物理隔离不进生产库）

2026-08-28 增：lnrs_anon_imaging_study（影像研究桥接表，patient_id ↔ 影像
绝对路径；仅存脱敏 ID；ETL-2 回写 + 离线灌库双通道）。

2026-09-15 增：lnrs_anon_dicom_series（series 级元数据，与 lnrs_anon_dicom_instance
的 ORM 一起补齐；DICOM 影像可统计：series_count / instance_count / byte_size）。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import MappedBase

# --------------------------------------------------------------------------- #
# PG ENUM 类型 — 名字与 DDL 中 CREATE TYPE 严格对齐
# --------------------------------------------------------------------------- #
# create_type=False：DDL 已在数据库里建好 ENUM，ORM 不重复创建，只引用。

_ingest_status_enum = ENUM(
    "running", "success", "failed", "partial",
    name="lnrs_anon_ingest_status_enum", create_type=False,
)
_source_kind_enum = ENUM(
    "csv_report", "dicom_dir", "dicom_zip",
    name="lnrs_anon_source_kind_enum", create_type=False,
)
_review_status_enum = ENUM(
    "pending", "reviewed", "flagged",
    name="lnrs_anon_review_status_enum", create_type=False,
)
_laterality_enum = ENUM(
    "L", "R", "Bilateral", "N/A",
    name="lnrs_anon_laterality_enum", create_type=False,
)
_clean_method_enum = ENUM(
    "regex_only", "regex+llm", "manual_review",
    name="lnrs_anon_clean_method_enum", create_type=False,
)
_phi_strategy_enum = ENUM(
    "hmac", "clear", "partial_keep", "llm_replace", "manual_review",
    name="lnrs_anon_phi_strategy_enum", create_type=False,
)


# --------------------------------------------------------------------------- #
# 表模型
# --------------------------------------------------------------------------- #


class AnonIngestBatchModel(MappedBase):
    """导入批次元数据 — 每次导入一行。

    记录"用了什么密钥版本、什么 schema 版本、清洗了哪些表/字段、统计行数"。
    """

    __tablename__ = "lnrs_anon_ingest_batch"
    __table_args__ = (
        UniqueConstraint(
            "center_code", "secret_version", "key_fingerprint", "schema_hash", "started_at",
            name="lnrs_anon_uq_batch_center_secret",
        ),
        {"schema": "lnrs", "comment": "脱敏导入批次元数据"},
    )

    batch_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    center_code: Mapped[str] = mapped_column(String(32), nullable=False)
    source_kind: Mapped[str] = mapped_column(_source_kind_enum, nullable=False)
    source_locator: Mapped[str] = mapped_column(Text, nullable=False)
    source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    secret_version: Mapped[str] = mapped_column(String(32), nullable=False)
    key_fingerprint: Mapped[str] = mapped_column(String(16), nullable=False)
    schema_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    row_counts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(
        _ingest_status_enum, nullable=False, default="running"
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class AnonPatientModel(MappedBase):
    """病人主表（双 ID 体系 + 软删除，Rev 2026-07-19）。

    - patient_id (PT_+8位) 是对外业务 ID 也是物理 PK
    - anon_id (ANON_+12hex) 是内部 HMAC 反查键
    """

    __tablename__ = "lnrs_anon_patient"
    __table_args__ = (
        UniqueConstraint("center_code", "anon_id", name="lnrs_anon_uq_patient_center"),
        CheckConstraint("patient_id ~ '^PT_[0-9]{8}$'", name="lnrs_anon_ck_patient_id_fmt"),
        CheckConstraint("anon_id ~ '^ANON_[0-9a-f]{12}$'", name="lnrs_anon_ck_anon_id_fmt"),
        CheckConstraint(
            "(deleted_at IS NULL AND deleted_reason IS NULL AND deleted_batch_id IS NULL) "
            "OR (deleted_at IS NOT NULL AND deleted_reason IS NOT NULL)",
            name="lnrs_anon_ck_deleted_consistency",
        ),
        CheckConstraint(
            "sex IN ('0','1','2','9')", name="lnrs_anon_ck_patient_sex"
        ),
        CheckConstraint(
            "ethnicity IS NULL OR ethnicity ~ '^[0-9]{2}$'",
            name="lnrs_anon_ck_patient_ethnicity",
        ),
        CheckConstraint(
            "smoking_status IS NULL OR smoking_status IN ('1','2','3','9')",
            name="lnrs_anon_ck_patient_smoking",
        ),
        CheckConstraint(
            "abo_blood_type IS NULL OR abo_blood_type IN ('1','2','3','4','5','6')",
            name="lnrs_anon_ck_patient_abo",
        ),
        CheckConstraint(
            "rh_blood_type IS NULL OR rh_blood_type IN ('1','2','3')",
            name="lnrs_anon_ck_patient_rh",
        ),
        CheckConstraint(
            "center_code ~ '^[a-z][a-z0-9_]*$'",
            name="lnrs_anon_ck_patient_center",
        ),
        {"schema": "lnrs", "comment": "脱敏病人主表（双 ID + 软删除）"},
    )

    patient_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    anon_id: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    center_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    sex: Mapped[str] = mapped_column(String(10), nullable=False, default="0")
    ethnicity: Mapped[str | None] = mapped_column(String(2), nullable=True)
    smoking_status: Mapped[str | None] = mapped_column(String(1), nullable=True)
    abo_blood_type: Mapped[str | None] = mapped_column(String(1), nullable=True)
    rh_blood_type: Mapped[str | None] = mapped_column(String(1), nullable=True)
    # 患者稳定属性（医疗宽表直入扩展，从 patient.parquet 直接承载）
    native_place: Mapped[str | None] = mapped_column(String(100), nullable=True)
    first_nodule_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    bmi: Mapped[float | None] = mapped_column(Numeric(5, 1), nullable=True)
    # 占位标记：True = 由 exam/visit/surgery 导入路径为保证 FK 自动发号的占位患者
    # （无人口学，sex 恒为 '0'）；完整 patient 记录 upsert 时翻回 False。
    is_placeholder: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # 兜底 JSONB：家族史/既往肿瘤/合并症/发现途径/吸烟包年等终身属性
    patient_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_batch_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("lnrs.lnrs_anon_ingest_batch.batch_id", ondelete="CASCADE"),
        nullable=False,
    )
    last_seen_batch_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("lnrs.lnrs_anon_ingest_batch.batch_id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    # 软删除
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    deleted_batch_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("lnrs.lnrs_anon_ingest_batch.batch_id"),
        nullable=True,
    )


class AnonExamModel(MappedBase):
    """检查主表（跨模态桥梁）— 一次 CT/病理检查一行。"""

    __tablename__ = "lnrs_anon_exam"
    __table_args__ = (
        UniqueConstraint(
            "center_code", "source_exam_hash", name="lnrs_anon_uq_exam_source"
        ),
        # 值域 = docs/all_modalities.json 26 键 + Other（0022 SQL 在库内加同名约束）
        CheckConstraint(
            "exam_type IS NULL OR exam_type IN ("
            "'CT', 'pathology_WSI', 'pathology_text', 'gene', 'medical_record', "
            "'imaging_report', 'basic_medical_info', 'diagnosis', 'drug_prescription', "
            "'medical_orders', 'medical_testing', 'radiology', 'ultrasound', "
            "'pulmonary_function', 'MRI', 'nuclear_medicine', 'bronchoscope', 'ECG', "
            "'case_history', 'progress_note', 'basic_info', 'inhospital_record', "
            "'IHC_record', 'operation', 'anesthesia', 'nursing', 'Other')",
            name="lnrs_anon_ck_exam_type",
        ),
        {"schema": "lnrs", "comment": "脱敏检查主表（跨模态桥梁）"},
    )

    anon_exam_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    patient_id: Mapped[str] = mapped_column(
        String(16),
        ForeignKey("lnrs.lnrs_anon_patient.patient_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    center_code: Mapped[str] = mapped_column(String(32), nullable=False)
    exam_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    exam_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_exam_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # visit 桥列（可空）：ETL 反查 visit 成功则回填，失败置 null
    anon_visit_id: Mapped[str | None] = mapped_column(
        String(40),
        ForeignKey("lnrs.lnrs_anon_visit.anon_visit_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_batch_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("lnrs.lnrs_anon_ingest_batch.batch_id", ondelete="CASCADE"),
        nullable=False,
    )
    last_seen_batch_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("lnrs.lnrs_anon_ingest_batch.batch_id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )


class AnonReportTextModel(MappedBase):
    """报告自由文本（已清洗）— 与 exam 一对一。

    本轮 clean_method='regex_only'、review_status='pending'（用户决策暂不清洗）。
    """

    __tablename__ = "lnrs_anon_report_text"
    __table_args__ = (
        {"schema": "lnrs", "comment": "脱敏报告自由文本"},
    )

    anon_exam_id: Mapped[str] = mapped_column(
        String(40),
        ForeignKey("lnrs.lnrs_anon_exam.anon_exam_id", ondelete="CASCADE"),
        primary_key=True,
    )
    body_clean: Mapped[str] = mapped_column(Text, nullable=False)
    pii_replaced_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    clean_method: Mapped[str] = mapped_column(_clean_method_enum, nullable=False)
    llm_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    review_status: Mapped[str] = mapped_column(
        _review_status_enum, nullable=False, default="pending"
    )
    created_batch_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("lnrs.lnrs_anon_ingest_batch.batch_id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )


class AnonExamFindingModel(MappedBase):
    """结构化指标（一次检查多个发现）— 本轮 ETL 不写入，保留模型供后续扩展。"""

    __tablename__ = "lnrs_anon_exam_finding"
    __table_args__ = (
        UniqueConstraint(
            "anon_exam_id", "finding_type", "raw_value_hash",
            name="lnrs_anon_uq_finding",
        ),
        CheckConstraint(
            "value_numeric IS NOT NULL OR value_text IS NOT NULL",
            name="lnrs_anon_ck_finding_value",
        ),
        {"schema": "lnrs", "comment": "脱敏结构化指标（按检查一查多）"},
    )

    finding_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    anon_exam_id: Mapped[str] = mapped_column(
        String(40),
        ForeignKey("lnrs.lnrs_anon_exam.anon_exam_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    finding_type: Mapped[str] = mapped_column(String(32), nullable=False)
    value_numeric: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    value_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    laterality: Mapped[str] = mapped_column(
        _laterality_enum, nullable=False, default="N/A"
    )
    raw_value_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_batch_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("lnrs.lnrs_anon_ingest_batch.batch_id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )


class AnonPhiAuditModel(MappedBase):
    """字段级 PHI 清洗审计 — 每个被脱敏字段一行，满足合规回放。"""

    __tablename__ = "lnrs_anon_phi_audit"
    __table_args__ = (
        {"schema": "lnrs", "comment": "字段级 PHI 清洗审计"},
    )

    audit_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    batch_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("lnrs.lnrs_anon_ingest_batch.batch_id"),
        nullable=False,
    )
    source_table: Mapped[str] = mapped_column(String(64), nullable=False)
    source_field: Mapped[str] = mapped_column(String(64), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy: Mapped[str] = mapped_column(_phi_strategy_enum, nullable=False)
    confidence: Mapped[float] = mapped_column(
        Numeric(4, 3), nullable=False, default=1.0
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )


# --------------------------------------------------------------------------- #
# DICOM series / instance 元数据（2026-09-15 补齐，ETL-2 增量阶段落库）
# --------------------------------------------------------------------------- #
#
# 数据源：lnrs.lnrs_anon_imaging_study.image_path（0012 离线灌库或 ETL-2 回写），
# ETL-2 增量阶段遍历这些目录，调用 DicomIndexer.register_folder 拿到 series
# 元数据后批量 upsert 到 dicom_series；dicom_instance 仅声明模型留作 ETL-3。
#
# DDL 字段顺序与 0006-anonymized-schema-lnrs.sql §7 / §8 严格对齐；
# 不增列、不改类型 — 任何漂移都需先走 DDL 迁移。


class AnonDicomSeriesModel(MappedBase):
    """DICOM 影像研究级元数据 — 一个 study 一行（2026-09-15 重构自 series 级）。

    设计要点：
    - anon_exam_id NOT NULL：要求该 study 在 lnrs_anon_imaging_study 中已
      回填 exam 关联（离线 CSV 灌库场景跳过 series 落库以避免约束违约）
    - dicom_study_uid UNIQUE：upsert 幂等键（ETL-2 重跑安全）；
      与 lnrs_anon_imaging_study.dicom_study_uid 对齐
    - file_count：study 目录下文件数（不过滤非图像模态 SR/SEG/PR/...；
      可能略大于真实 image instance 数）；CHECK >= 0
    - byte_size NOT NULL：累加目录下所有 .dcm 的 st_size（字节）；
      通过 file_count * 平均文件大小估算总容量
    - 重构来源：原 series 级 schema 含 dicom_series_uid/modality/body_part/
      series_no/file_root/file_count_actual 字段，已在 2026-09-15 迁移移除。
      DICOMweb 实时接口（DicomViewer）仍走 DicomIndexer 内存索引（路径不变）。
    """

    __tablename__ = "lnrs_anon_dicom_series"
    __table_args__ = (
        CheckConstraint(
            "file_count >= 0",
            name="lnrs_anon_ck_dicom_series_file_count",
        ),
        {"schema": "lnrs", "comment": "DICOM 影像研究级元数据（study-level；2026-09-15 重构自 series-level）"},
    )

    series_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    anon_exam_id: Mapped[str] = mapped_column(
        String(40),
        ForeignKey("lnrs.lnrs_anon_exam.anon_exam_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dicom_study_uid: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    file_count: Mapped[int] = mapped_column(Integer, nullable=False)
    series_no: Mapped[int] = mapped_column(Integer, nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_batch_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("lnrs.lnrs_anon_ingest_batch.batch_id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )


class AnonDicomInstanceModel(MappedBase):
    """DICOM 关键实例（series 内 SOP 级）— 本轮 ETL 不写入，模型留作 ETL-3。

    设计要点：
    - 联合主键 (series_id, instance_no)：按 series 内序号稳定排序
    - sop_instance_uid UNIQUE：跨 series 去重（理论上不应重复）
    - byte_offset：用于 OSS/NAS 远程读取时跳过头部；本轮 ETL 不填
    """

    __tablename__ = "lnrs_anon_dicom_instance"
    __table_args__ = (
        CheckConstraint(
            "instance_no > 0",
            name="lnrs_anon_ck_instance_no",
        ),
        {"schema": "lnrs", "comment": "DICOM SOP 级实例表（ETL-3 实施，本轮仅声明）"},
    )

    series_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("lnrs.lnrs_anon_dicom_series.series_id", ondelete="CASCADE"),
        primary_key=True,
    )
    sop_instance_uid: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    instance_no: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    byte_offset: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

# --------------------------------------------------------------------------- #
# 医疗宽表直入扩展（2026-07-24 嫁接）: visit / surgery / exam_detail
# --------------------------------------------------------------------------- #


class AnonVisitModel(MappedBase):
    """就诊桥 — 从 surgery_record.visit_id 反推生成。

    visit 层是"非影像就诊数据"的挂载点（手术记录等）。
    FK 指向 patient_id（与全表体系一致，不用 anon_id）。
    """

    __tablename__ = "lnrs_anon_visit"
    __table_args__ = (
        UniqueConstraint(
            "center_code", "source_visit_hash", name="lnrs_anon_uq_visit_source"
        ),
        UniqueConstraint(
            "patient_id", "visit_ordinal", name="lnrs_anon_uq_visit_patient"
        ),
        {"schema": "lnrs", "comment": "脱敏就诊桥（visit 级，从手术记录反推）"},
    )

    anon_visit_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    patient_id: Mapped[str] = mapped_column(
        String(16),
        ForeignKey("lnrs.lnrs_anon_patient.patient_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    center_code: Mapped[str] = mapped_column(String(32), nullable=False)
    visit_ordinal: Mapped[str] = mapped_column(String(64), nullable=False)
    source_visit_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_batch_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("lnrs.lnrs_anon_ingest_batch.batch_id", ondelete="CASCADE"),
        nullable=False,
    )
    last_seen_batch_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("lnrs.lnrs_anon_ingest_batch.batch_id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )


class AnonSurgeryModel(MappedBase):
    """visit 级手术记录 — 每次手术一行。"""

    __tablename__ = "lnrs_anon_surgery"
    __table_args__ = (
        UniqueConstraint(
            "anon_visit_id", "source_surgery_hash", name="lnrs_anon_uq_surgery"
        ),
        {"schema": "lnrs", "comment": "脱敏手术记录表（visit 级）"},
    )

    surgery_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    anon_visit_id: Mapped[str] = mapped_column(
        String(40),
        ForeignKey("lnrs.lnrs_anon_visit.anon_visit_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    patient_id: Mapped[str] = mapped_column(
        String(16),
        ForeignKey("lnrs.lnrs_anon_patient.patient_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    center_code: Mapped[str] = mapped_column(String(32), nullable=False)
    surgery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    procedure_name: Mapped[str] = mapped_column(String(200), nullable=False)
    resection_scope: Mapped[str | None] = mapped_column(String(100), nullable=True)
    surgical_approach: Mapped[str | None] = mapped_column(String(50), nullable=True)
    procedure_detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source_surgery_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_batch_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("lnrs.lnrs_anon_ingest_batch.batch_id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )


class AnonExamDetailModel(MappedBase):
    """exam 级 JSONB 深结构 — 承载病理/基因/IHC/结节的嵌套数据。

    与扁平的 lnrs_anon_exam_finding 互补：
    - finding 装 EAV 标量（结节长径、位置）
    - detail 装嵌套 JSONB（driver_mutations 13 基因、staging pT/pN/pM、腺癌亚型）
    detail_type 区分结构语义，detail_json 原样保留 parquet 的 struct。

    Rev 2026-07-24: PK 改为 (anon_exam_id, detail_type, detail_ordinal) 实现 1:N：
    - 同一 exam 可承载多个同类型 detail（如 CT 下 n1/n2/n3/n4 多结节）
    - 不同类型 detail（pathology/ihc 共享 specimen_id）各自独立成行，不互相覆盖
    - detail_ordinal 默认 1：无 ordinal 的 detail（pathology/genetic/ihc）单行
    """

    __tablename__ = "lnrs_anon_exam_detail"
    __table_args__ = (
        {"schema": "lnrs", "comment": "脱敏检查深结构详情（JSONB，按 detail_type 区分）"},
    )

    anon_exam_id: Mapped[str] = mapped_column(
        String(40),
        ForeignKey("lnrs.lnrs_anon_exam.anon_exam_id", ondelete="CASCADE"),
        primary_key=True,
    )
    detail_type: Mapped[str] = mapped_column(String(32), primary_key=True, index=True)
    detail_ordinal: Mapped[int] = mapped_column(
        "detail_ordinal", SmallInteger, primary_key=True, default=1,
        comment="同类型多实例序号（如多结节 n1/n2/n3/n4），无 ordinal 的 detail 默认 1",
    )
    detail_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_batch_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("lnrs.lnrs_anon_ingest_batch.batch_id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )


class AnonVisitDetailModel(MappedBase):
    """visit 1:1 富信息 — 省医 visit_record 的病案首页/病史/诊断/临床文档。

    与 lnrs_anon_visit 轻量桥表 1:1：visit 桥只存关联键，visit_detail 存富信息。
    visit_detail_json 忠实保留原始嵌套结构（inpatient_front_page/medical_history/
    diagnoses[]/clinical_documents[]），不做语义对齐。
    前置: lnrs_anon_visit 桥行由 ETL _import_visit_detail_table 自建（不依赖 surgery 反推）。
    """

    __tablename__ = "lnrs_anon_visit_detail"
    __table_args__ = (
        UniqueConstraint("anon_visit_id", name="lnrs_anon_uq_visit_detail"),
        {"schema": "lnrs", "comment": "脱敏就诊富信息（visit 1:1，省医扩展）"},
    )

    visit_detail_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    anon_visit_id: Mapped[str] = mapped_column(
        String(40),
        ForeignKey("lnrs.lnrs_anon_visit.anon_visit_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    patient_id: Mapped[str] = mapped_column(
        String(16),
        ForeignKey("lnrs.lnrs_anon_patient.patient_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    center_code: Mapped[str] = mapped_column(String(32), nullable=False)
    visit_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    admission_time: Mapped[date | None] = mapped_column(Date, nullable=True)
    discharge_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    admission_dept: Mapped[str | None] = mapped_column(String(100), nullable=True)
    discharge_dept: Mapped[str | None] = mapped_column(String(100), nullable=True)
    length_of_stay: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(100), nullable=True)
    visit_age: Mapped[float | None] = mapped_column(Numeric(5, 1), nullable=True)
    visit_detail_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_visit_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_batch_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("lnrs.lnrs_anon_ingest_batch.batch_id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )


class AnonLabResultModel(MappedBase):
    """visit 级检验结果 — 省医 lab_result。

    提取关键标量列（report_id/test_name/item_name/item_result/item_result_value/
    item_unit/collection_time），test_detail 等剩余结构落 lab_detail_json。
    anon_visit_id 可空: visit_id 缺失时退化为只挂 patient。
    """

    __tablename__ = "lnrs_anon_lab_result"
    __table_args__ = (
        UniqueConstraint("source_lab_hash", name="lnrs_anon_uq_lab_result"),
        {"schema": "lnrs", "comment": "脱敏检验结果（visit 级，省医扩展）"},
    )

    lab_result_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    anon_visit_id: Mapped[str | None] = mapped_column(
        String(40),
        ForeignKey("lnrs.lnrs_anon_visit.anon_visit_id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    patient_id: Mapped[str] = mapped_column(
        String(16),
        ForeignKey("lnrs.lnrs_anon_patient.patient_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    center_code: Mapped[str] = mapped_column(String(32), nullable=False)
    report_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    test_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    item_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    item_result: Mapped[str | None] = mapped_column(String(255), nullable=True)
    item_result_value: Mapped[float | None] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    item_unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    collection_time: Mapped[date | None] = mapped_column(Date, nullable=True)
    lab_detail_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source_lab_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_batch_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("lnrs.lnrs_anon_ingest_batch.batch_id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )


class AnonOrderModel(MappedBase):
    """visit 级医嘱 — 省医 drug_order + no_drug_order 合并，order_type 区分。

    提取 order_name/order_time/order_source，order_detail struct 落 order_detail_json。
    anon_visit_id 可空: visit_id 缺失时退化为只挂 patient。
    """

    __tablename__ = "lnrs_anon_order"
    __table_args__ = (
        UniqueConstraint("source_order_hash", name="lnrs_anon_uq_order"),
        {"schema": "lnrs", "comment": "脱敏医嘱（visit 级，drug+non_drug 合并，省医扩展）"},
    )

    order_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    anon_visit_id: Mapped[str | None] = mapped_column(
        String(40),
        ForeignKey("lnrs.lnrs_anon_visit.anon_visit_id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    patient_id: Mapped[str] = mapped_column(
        String(16),
        ForeignKey("lnrs.lnrs_anon_patient.patient_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    center_code: Mapped[str] = mapped_column(String(32), nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    order_name: Mapped[str] = mapped_column(String(200), nullable=False)
    order_time: Mapped[date | None] = mapped_column(Date, nullable=True)
    order_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    order_detail_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source_order_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_batch_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("lnrs.lnrs_anon_ingest_batch.batch_id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )


class AnonDiagnosisModel(MappedBase):
    """患者级诊断 — 省医 2026-09 全量批次扩展（0014）。

    就诊.诊断 + 住院病案首页.诊断 合并，source 区分。
    """

    __tablename__ = "lnrs_anon_diagnosis"
    __table_args__ = (
        UniqueConstraint("source_diag_hash", name="lnrs_anon_uq_diagnosis"),
        {"schema": "lnrs", "comment": "脱敏诊断（患者级，省医扩展）"},
    )

    diagnosis_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    patient_id: Mapped[str] = mapped_column(
        String(16),
        ForeignKey("lnrs.lnrs_anon_patient.patient_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    center_code: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    diagnosis_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    diagnosis_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    diagnosis_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_primary: Mapped[str | None] = mapped_column(String(8), nullable=True)
    diagnosis_category: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    diagnosis_detail_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source_diag_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_batch_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("lnrs.lnrs_anon_ingest_batch.batch_id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )


class AnonClinicalDocumentModel(MappedBase):
    """病程记录文档 — 省医 2026-09 全量批次扩展（0014）。自由文本。"""

    __tablename__ = "lnrs_anon_clinical_document"
    __table_args__ = (
        UniqueConstraint("source_doc_hash", name="lnrs_anon_uq_clinical_doc"),
        {"schema": "lnrs", "comment": "脱敏病程记录文档（患者级，省医扩展）"},
    )

    document_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    patient_id: Mapped[str] = mapped_column(
        String(16),
        ForeignKey("lnrs.lnrs_anon_patient.patient_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    center_code: Mapped[str] = mapped_column(String(32), nullable=False)
    doc_type: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    doc_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    doc_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_doc_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_batch_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("lnrs.lnrs_anon_ingest_batch.batch_id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )


class AnonMedicalHistoryModel(MappedBase):
    """就诊病史 — 省医 2026-09 全量批次扩展（0014）。"""

    __tablename__ = "lnrs_anon_medical_history"
    __table_args__ = (
        UniqueConstraint("source_hist_hash", name="lnrs_anon_uq_medical_history"),
        {"schema": "lnrs", "comment": "脱敏病史（患者级，省医扩展）"},
    )

    history_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    patient_id: Mapped[str] = mapped_column(
        String(16),
        ForeignKey("lnrs.lnrs_anon_patient.patient_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    center_code: Mapped[str] = mapped_column(String(32), nullable=False)
    chief_complaint: Mapped[str | None] = mapped_column(Text, nullable=True)
    present_illness: Mapped[str | None] = mapped_column(Text, nullable=True)
    past_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    personal_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    marriage_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    family_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    record_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    data_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_hist_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_batch_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("lnrs.lnrs_anon_ingest_batch.batch_id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )


class AnonVitalObservationModel(MappedBase):
    """生命体征/观察测量 — 省医 2026-09 全量批次扩展（0014）。

    护理记录 + ICU 护理 + 麻醉子项 合并，obs_type 区分。
    obs_time 为 TIMESTAMP（日内多次测量保留时分秒）。
    """

    __tablename__ = "lnrs_anon_vital_observation"
    __table_args__ = (
        UniqueConstraint("source_obs_hash", name="lnrs_anon_uq_vital_observation"),
        {"schema": "lnrs", "comment": "脱敏生命体征/观察测量（省医扩展）"},
    )

    observation_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    anon_visit_id: Mapped[str | None] = mapped_column(
        String(40),
        ForeignKey("lnrs.lnrs_anon_visit.anon_visit_id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    patient_id: Mapped[str] = mapped_column(
        String(16),
        ForeignKey("lnrs.lnrs_anon_patient.patient_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    center_code: Mapped[str] = mapped_column(String(32), nullable=False)
    obs_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    item_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    item_result: Mapped[str | None] = mapped_column(String(255), nullable=True)
    item_result_value: Mapped[float | None] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    item_unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    obs_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    obs_detail_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source_obs_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_batch_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("lnrs.lnrs_anon_ingest_batch.batch_id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )


class AnonImagingStudyModel(MappedBase):
    """影像研究桥接表 — patient_id (PT_xxx) ↔ 影像绝对路径。

    设计要点（2026-08-28 新增）：
    - 仅存脱敏 ID（patient_id FK 到 lnrs_anon_patient）；原始 pat_local_id 不入库
    - dicom_study_uid 明文，便于 dicom/repository 内存索引反查
    - image_path 存磁盘上 Study 根目录的绝对路径（不含 Series/SOP 拆解）
    - anon_exam_id 可空：ETL-2 回写时填充；离线灌库（CSV → imaging_study）为空
    - 同一 (patient_id, dicom_study_uid, source) 唯一；跨源（盘 1 + 盘 2）允许重复
    - 与已有 lnrs_anon_dicom_series 语义正交：后者填 series-level 明细，
      本表填 study-level 桥接（用于"在患者记录处点击打开影像"）
    """

    __tablename__ = "lnrs_anon_imaging_study"
    __table_args__ = (
        UniqueConstraint(
            "patient_id", "dicom_study_uid", "source",
            name="lnrs_anon_uq_imaging_study",
        ),
        CheckConstraint(
            "center_code ~ '^[a-z][a-z0-9_]*$'",
            name="lnrs_anon_ck_imaging_center",
        ),
        CheckConstraint(
            "modality IN ('CT','MR','XR','US','PET','NM','Pathology','Genetic','Other')",
            name="lnrs_anon_ck_imaging_modality",
        ),
        {"schema": "lnrs", "comment": "影像研究桥接表（PT_xxx ↔ 影像绝对路径）"},
    )

    study_key: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(
        String(16),
        ForeignKey("lnrs.lnrs_anon_patient.patient_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    center_code: Mapped[str] = mapped_column(String(32), nullable=False)
    dicom_study_uid: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    modality: Mapped[str] = mapped_column(String(16), nullable=False, default="CT")
    image_path: Mapped[str] = mapped_column(Text, nullable=False)
    sop_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="disk_index")
    anon_exam_id: Mapped[str | None] = mapped_column(
        String(40),
        ForeignKey("lnrs.lnrs_anon_exam.anon_exam_id", ondelete="SET NULL"),
        nullable=True,
    )
    created_batch_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("lnrs.lnrs_anon_ingest_batch.batch_id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )


class AnonImagingOrphanModel(MappedBase):
    """影像孤儿登记表/中间表(2026-09-03)。

    业务 ID `study_orphan_id` 由 `(center_code, rel_path_from_dicom_root)` SHA256[:8] 哈希派生,
    同一 dicom 子路径(去掉 dicom 根绝对前缀) → 同一 ID(可反查);不依赖任何全局序列。
    `source_orphan_hash` 是跨中心唯一锚(对齐 source_*_hash 模式)。
    主表本身就是 ID↔元数据映射表(无需另建映射表)。
    """

    __tablename__ = "lnrs_anon_imaging_orphan"
    __table_args__ = (
        UniqueConstraint("study_orphan_id", name="lnrs_anon_uq_imaging_orphan_id"),
        UniqueConstraint("source_orphan_hash", name="lnrs_anon_uq_imaging_orphan_hash"),
        UniqueConstraint(
            "center_code", "dicom_study_uid", "image_path",
            name="lnrs_anon_uq_imaging_orphan_path",
        ),
        {"schema": "lnrs", "comment": "影像孤儿登记表(SHA256 映射 ID + 状态机,中间表语义)"},
    )

    orphan_key: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    study_orphan_id: Mapped[str] = mapped_column(String(18), nullable=False)
    center_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    patient_id: Mapped[str | None] = mapped_column(
        String(16),
        ForeignKey("lnrs.lnrs_anon_patient.patient_id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    dicom_study_uid: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    image_path: Mapped[str] = mapped_column(Text, nullable=False)
    source_orphan_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    path_date_prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    modality: Mapped[str] = mapped_column(String(16), nullable=False, default="CT")
    sop_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="orphan_audit_2026_09_03")
    orphan_kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    orphan_status: Mapped[str] = mapped_column(String(16), nullable=False, default="discovered", index=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    audit_batch_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("lnrs.lnrs_anon_orphan_audit_batch.audit_batch_id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class AnonOrphanAuditBatchModel(MappedBase):
    """孤儿审计批次元数据(2026-09-03)。"""

    __tablename__ = "lnrs_anon_orphan_audit_batch"
    __table_args__ = (
        {"schema": "lnrs", "comment": "孤儿审计批次元数据(非 ETL 灌库,仅审计锚定)"},
    )

    audit_batch_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    center_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    audit_locator: Mapped[str] = mapped_column(Text, nullable=False)
    audit_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    discovered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    patient_missing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dual_disk_copy_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    empty_dir_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    other_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ran_by: Mapped[str] = mapped_column(String(64), nullable=False)
    ran_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


ANON_TABLE_MODELS: dict[str, type[MappedBase]] = {
    "lnrs_anon_ingest_batch": AnonIngestBatchModel,
    "lnrs_anon_patient": AnonPatientModel,
    "lnrs_anon_exam": AnonExamModel,
    "lnrs_anon_report_text": AnonReportTextModel,
    "lnrs_anon_exam_finding": AnonExamFindingModel,
    "lnrs_anon_phi_audit": AnonPhiAuditModel,
    "lnrs_anon_visit": AnonVisitModel,
    "lnrs_anon_surgery": AnonSurgeryModel,
    "lnrs_anon_exam_detail": AnonExamDetailModel,
    "lnrs_anon_visit_detail": AnonVisitDetailModel,
    "lnrs_anon_lab_result": AnonLabResultModel,
    "lnrs_anon_order": AnonOrderModel,
    "lnrs_anon_diagnosis": AnonDiagnosisModel,
    "lnrs_anon_clinical_document": AnonClinicalDocumentModel,
    "lnrs_anon_medical_history": AnonMedicalHistoryModel,
    "lnrs_anon_vital_observation": AnonVitalObservationModel,
    "lnrs_anon_imaging_study": AnonImagingStudyModel,
    "lnrs_anon_imaging_orphan": AnonImagingOrphanModel,
    "lnrs_anon_orphan_audit_batch": AnonOrphanAuditBatchModel,
    "lnrs_anon_dicom_series": AnonDicomSeriesModel,
    "lnrs_anon_dicom_instance": AnonDicomInstanceModel,
}
