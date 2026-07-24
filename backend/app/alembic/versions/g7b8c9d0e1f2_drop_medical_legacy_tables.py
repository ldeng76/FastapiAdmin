"""drop medical legacy tables (med_* ETL-1 中间层退役)

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-24

退役 7 张 med_* 业务数据表（ETL-1 中间层）：
  med_patient / med_pathology_specimen / med_surgery_record / med_genetic_test /
  med_nodule_imaging / med_ihc_result / med_follow_up

背景：
- 原架构为两层 ETL（Excel → med_* 宽表 → lnrs_anon_* 脱敏表）。
- 宽表直入扩展（2026-07-24 嫁接）让 parquet 直接进 lnrs_anon_*，med_* 中间层退役。
- 本迁移只 DROP 表，不删 ORM 模型/代码引用——代码清理需等 anon 链路补全 HTTP API
  （患者列表/详情查询、医院导入入口、数据摘要闸门）后统一进行，避免破坏前端可用功能。

幂等性：
- DROP TABLE IF EXISTS，重跑不报错。
- downgrade 按 c3d4e5f6a7b8 建表逻辑 + f6a7b8c9d0e1 的 nodule_no 约束修复重建。

⚠️ 执行前置条件（本迁移不检查，由人工保证）：
1. anon ETL-2 已补 HTTP 导入 API（替代 POST /hospital/{id}/import）
2. 患者列表/详情查询已改接 lnrs_anon_*（替代 PatientService）
3. 医院上线闸门已改接 anon 统计（替代 get_data_summary_service）
4. 前端 api/module_medical/patient.ts + views 已对接新 PatientService
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "g7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 退役表清单（反依赖序：子表在前，父表在后）
_LEGACY_TABLES: tuple[str, ...] = (
    "med_follow_up",
    "med_ihc_result",
    "med_nodule_imaging",
    "med_genetic_test",
    "med_surgery_record",
    "med_pathology_specimen",
    "med_patient",
)


# --------------------------------------------------------------------------- #
# downgrade 用的建表辅助（复制自 c3d4e5f6a7b8，保持自包含）
# --------------------------------------------------------------------------- #


def _base_columns() -> list:
    """ModelMixin + UserMixin 字段列表。"""
    return [
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="主键ID"),
        sa.Column("uuid", sa.String(length=64), nullable=False, comment="UUID全局唯一标识"),
        sa.Column("status", sa.String(length=10), nullable=False, comment="状态(0:正常 1:禁用)"),
        sa.Column("description", sa.Text(), nullable=True, comment="备注/描述"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("updated_time", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, comment="是否已删除"),
        sa.Column("deleted_time", sa.DateTime(), nullable=True, comment="删除时间"),
        sa.Column("created_id", sa.Integer(), nullable=True, comment="创建人ID"),
        sa.Column("updated_id", sa.Integer(), nullable=True, comment="更新人ID"),
        sa.Column("deleted_id", sa.Integer(), nullable=True, comment="删除人ID"),
    ]


def _base_constraints(table: str) -> list:
    """ModelMixin + UserMixin 通用约束（PK, uuid 唯一, 审计 FK）。"""
    return [
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid", name=f"uq_{table}_uuid"),
        sa.ForeignKeyConstraint(
            ["created_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["updated_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["deleted_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="SET NULL"
        ),
    ]


def _tenant_constraint(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["tenant_id"], ["sys_tenant.id"], onupdate="CASCADE", ondelete="RESTRICT"
    )


def _set_server_defaults(table: str, extra_defaults: dict | None = None) -> None:
    """给 ModelMixin 字段加 server_default。"""
    defaults = {
        "status": ("0", sa.String(length=10)),
        "created_time": (sa.text("CURRENT_TIMESTAMP"), sa.DateTime()),
        "updated_time": (sa.text("CURRENT_TIMESTAMP"), sa.DateTime()),
        "is_deleted": (sa.text("false"), sa.Boolean()),
    }
    if extra_defaults:
        defaults.update(extra_defaults)
    for col, (value, col_type) in defaults.items():
        op.alter_column(
            table,
            col,
            server_default=value,
            existing_type=col_type,
            existing_nullable=False,
        )


def _create_audit_indexes(table: str) -> None:
    for col in (
        "status", "created_time", "updated_time", "is_deleted",
        "deleted_time", "created_id", "updated_id", "deleted_id", "tenant_id",
    ):
        op.create_index(op.f(f"ix_{table}_{col}"), table, [col])


def _create_gin(table: str, col: str) -> None:
    op.create_index(op.f(f"ix_{table}_{col}_gin"), table, [col], postgresql_using="gin")


def upgrade() -> None:
    """DROP 7 张退役表（幂等，IF EXISTS）。"""
    for tbl in _LEGACY_TABLES:
        op.drop_table(tbl)


def downgrade() -> None:
    """重建 7 张表（按 c3d4e5f6a7b8 建表逻辑 + f6a7b8c9d0e1 的 nodule_no 约束修复）。"""
    # ---- 1. med_patient ----
    op.create_table(
        "med_patient",
        *_base_columns(),
        sa.Column("tenant_id", sa.Integer(), nullable=False, comment="关联租户ID（数据来源标记）"),
        sa.Column("patient_id", sa.String(length=64), nullable=False, comment="患者编号"),
        sa.Column("source_center", sa.String(length=50), nullable=True, comment="来源中心"),
        sa.Column("gender", sa.String(length=10), nullable=True, comment="性别"),
        sa.Column("birth_date", sa.Date(), nullable=True, comment="出生日期"),
        sa.Column("ethnicity", sa.String(length=50), nullable=True, comment="民族"),
        sa.Column("native_place", sa.String(length=100), nullable=True, comment="籍贯"),
        sa.Column("abo_blood_type", sa.String(length=10), nullable=True, comment="ABO血型"),
        sa.Column("rh_blood_type", sa.String(length=10), nullable=True, comment="RH血型"),
        sa.Column("smoking_status", sa.String(length=20), nullable=True, comment="吸烟状态"),
        sa.Column("first_nodule_date", sa.Date(), nullable=True, comment="首次发现结节日期"),
        sa.Column("demographics", JSONB(), nullable=True, comment="人口学扩展"),
        sa.Column("medical_history", JSONB(), nullable=True, comment="既往病史"),
        *_base_constraints("med_patient"),
        sa.UniqueConstraint("tenant_id", "patient_id", name="uq_med_patient_tenant_patient"),
        _tenant_constraint("med_patient"),
        comment="患者基本信息表（统一表）",
    )

    # ---- 2. med_pathology_specimen ----
    op.create_table(
        "med_pathology_specimen",
        *_base_columns(),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.String(length=64), nullable=False, comment="患者编号"),
        sa.Column("visit_id", sa.String(length=64), nullable=True, comment="就诊编号"),
        sa.Column("specimen_id", sa.String(length=64), nullable=False, comment="标本号"),
        sa.Column("submission_date", sa.Date(), nullable=True, comment="送检日期"),
        sa.Column("report_date", sa.Date(), nullable=True, comment="报告日期"),
        sa.Column("specimen_type", sa.String(length=50), nullable=True, comment="标本类型"),
        sa.Column("sampling_site", sa.String(length=100), nullable=True, comment="取材部位"),
        sa.Column("specimen_name", sa.String(length=100), nullable=True, comment="标本名称"),
        sa.Column("exam_name", sa.String(length=100), nullable=True, comment="检查名称"),
        sa.Column("exam_type", sa.String(length=50), nullable=True, comment="检查类型"),
        sa.Column("exam_date", sa.Date(), nullable=True, comment="检查日期"),
        sa.Column("histology_class", sa.String(length=50), nullable=True, comment="组织学大类"),
        sa.Column("pathology_diagnosis", sa.String(length=500), nullable=True, comment="病理诊断"),
        sa.Column("tumor_total_size_mm", sa.Float(), nullable=True, comment="肿瘤总大小(mm)"),
        sa.Column("exam_detail", JSONB(), nullable=True, comment="检查详情"),
        sa.Column("specimen_meta", JSONB(), nullable=True),
        sa.Column("adenocarcinoma_subtypes", JSONB(), nullable=True),
        sa.Column("tumor_measurement", JSONB(), nullable=True),
        sa.Column("high_risk_factors", JSONB(), nullable=True),
        sa.Column("staging", JSONB(), nullable=True, comment="病理分期"),
        sa.Column("exam_meta", JSONB(), nullable=True),
        *_base_constraints("med_pathology_specimen"),
        sa.UniqueConstraint("tenant_id", "specimen_id", name="uq_med_pathology_specimen_tenant_specimen"),
        _tenant_constraint("med_pathology_specimen"),
        comment="病理标本表（统一表）",
    )

    # ---- 3. med_surgery_record ----
    op.create_table(
        "med_surgery_record",
        *_base_columns(),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.String(length=64), nullable=False, comment="患者编号"),
        sa.Column("visit_id", sa.String(length=64), nullable=True, comment="就诊编号"),
        sa.Column("surgery_date", sa.Date(), nullable=True, comment="手术日期"),
        sa.Column("procedure_name", sa.String(length=200), nullable=False, comment="手术及操作名称"),
        sa.Column("resection_scope", sa.String(length=100), nullable=True, comment="切除范围"),
        sa.Column("surgical_approach", sa.String(length=50), nullable=True, comment="手术入路"),
        sa.Column("procedure_detail", JSONB(), nullable=True, comment="手术详情"),
        *_base_constraints("med_surgery_record"),
        sa.UniqueConstraint(
            "tenant_id", "patient_id", "surgery_date", "procedure_name",
            name="uq_med_surgery_record_tenant_patient_date_proc",
        ),
        _tenant_constraint("med_surgery_record"),
        comment="手术记录表（统一表）",
    )

    # ---- 4. med_genetic_test ----
    op.create_table(
        "med_genetic_test",
        *_base_columns(),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.String(length=64), nullable=False, comment="患者编号"),
        sa.Column("visit_id", sa.String(length=64), nullable=True, comment="就诊编号"),
        sa.Column("test_id", sa.String(length=64), nullable=False, comment="检测唯一号"),
        sa.Column("test_date", sa.Date(), nullable=True, comment="检测日期"),
        sa.Column("variant_type", sa.String(length=50), nullable=True, comment="变异类型"),
        sa.Column("test_method", sa.String(length=100), nullable=True, comment="检测方法"),
        sa.Column("test_meta", JSONB(), nullable=True, comment="检测元数据"),
        sa.Column("variant_result", JSONB(), nullable=True, comment="变异结果"),
        sa.Column("driver_mutations", JSONB(), nullable=True, comment="驱动基因突变"),
        sa.Column("immune_markers", JSONB(), nullable=True, comment="免疫相关标志物"),
        *_base_constraints("med_genetic_test"),
        sa.UniqueConstraint("tenant_id", "test_id", name="uq_med_genetic_test_tenant_test"),
        _tenant_constraint("med_genetic_test"),
        comment="基因检测表（统一表）",
    )

    # ---- 5. med_nodule_imaging（按 f6a7b8c9d0e1 修复后的约束：nodule_no NOT NULL） ----
    op.create_table(
        "med_nodule_imaging",
        *_base_columns(),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.String(length=64), nullable=False, comment="患者编号"),
        sa.Column("exam_id", sa.Text(), nullable=False, comment="检查唯一号（可能含多个逗号分隔ID）"),
        sa.Column("exam_date", sa.DateTime(), nullable=True, comment="检查日期时间"),
        sa.Column("exam_type", sa.String(length=50), nullable=True, comment="检查类型"),
        sa.Column("nodule_no", sa.String(length=20), nullable=False, server_default="UNKNOWN", comment="结节编号"),
        sa.Column("nodule_location", sa.String(length=100), nullable=True, comment="结节位置"),
        sa.Column("long_diameter", sa.Float(), nullable=True, comment="长径(mm)"),
        sa.Column("density_type", sa.String(length=50), nullable=True, comment="密度类型"),
        sa.Column("exam_meta", JSONB(), nullable=True),
        sa.Column("nodule_morphology", JSONB(), nullable=True),
        sa.Column("nodule_quantitative", JSONB(), nullable=True),
        sa.Column("follow_up_comparison", JSONB(), nullable=True),
        *_base_constraints("med_nodule_imaging"),
        sa.UniqueConstraint(
            "tenant_id", "exam_id", "nodule_no",
            name="uq_med_nodule_imaging_tenant_exam_nodule",
        ),
        _tenant_constraint("med_nodule_imaging"),
        comment="结节影像表",
    )

    # ---- 6. med_ihc_result ----
    op.create_table(
        "med_ihc_result",
        *_base_columns(),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.String(length=64), nullable=False, comment="患者编号"),
        sa.Column("specimen_id", sa.String(length=64), nullable=False, comment="病理标本号"),
        sa.Column("ki67_pct", sa.Float(), nullable=True, comment="Ki-67(%)"),
        sa.Column("markers", JSONB(), nullable=True, comment="免疫组化标志物"),
        *_base_constraints("med_ihc_result"),
        sa.UniqueConstraint("tenant_id", "specimen_id", name="uq_med_ihc_result_tenant_specimen"),
        _tenant_constraint("med_ihc_result"),
        comment="免疫组化结果表",
    )

    # ---- 7. med_follow_up ----
    op.create_table(
        "med_follow_up",
        *_base_columns(),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.String(length=64), nullable=False, comment="患者编号"),
        sa.Column("last_followup_date", sa.Date(), nullable=True, comment="末次随访日期"),
        sa.Column("recurrence", sa.String(length=20), nullable=True, comment="是否复发"),
        sa.Column("survival_status", sa.String(length=20), nullable=True, comment="生存状态"),
        sa.Column("treatment_detail", JSONB(), nullable=True, comment="辅助治疗详情"),
        sa.Column("recurrence_detail", JSONB(), nullable=True, comment="复发详情"),
        *_base_constraints("med_follow_up"),
        sa.UniqueConstraint("tenant_id", "patient_id", name="uq_med_follow_up_tenant_patient"),
        _tenant_constraint("med_follow_up"),
        comment="随访结局表",
    )

    # ---- 8. server_defaults + 索引 + GIN ----
    for tbl in _LEGACY_TABLES[::-1]:  # 正序（建表序）
        _set_server_defaults(tbl)
        _create_audit_indexes(tbl)
    _create_gin("med_patient", "medical_history")
    _create_gin("med_genetic_test", "driver_mutations")
    _create_gin("med_pathology_specimen", "staging")
