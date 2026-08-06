"""lnrs_anon_* 脱敏窄表 ORM 模型 — ADR-0006。

与 `docs/adr/0006-anonymized-schema-lnrs.sql` 一一对应（schema='lnrs'）。
表自带主键（非自增 id），故**不继承 ModelMixin**，独立定义所有列。

实现范围（与用户确认的本轮 ETL-2 边界）：
- 落库：ingest_batch / patient / exam / report_text / phi_audit / exam_finding
- 本轮 finding 表实际不写入（自由文本不拆分），但模型保留
- 不建模：dicom_series / dicom_instance / dicom_uid_map（本轮无 DICOM 源，
  uid_map 按 ADR 物理隔离不进生产库）
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
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
# 注册表 — 供 ETL 引擎与查询层使用
# --------------------------------------------------------------------------- #
#
# TODO(后续迭代): 本轮未建模的 DDL 表（接入 DICOM 源时补齐）：
#   - lnrs_anon_dicom_series    （DICOM 序列元数据 + NAS/OSS 路径）
#   - lnrs_anon_dicom_instance  （关键实例级，按需建）
#   - lnrs_anon_dicom_uid_map   （原 UID ↔ 新 UID，仅审计物理隔离库，不进生产库）
# DDL 已在 backend/sql/postgres/0006-anonymized-schema-lnrs.sql 中定义。


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
}
