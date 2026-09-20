"""新增 3 张 stage 表 — 其余表接入「先暂存再上」（issue-23）

Revision ID: p6q7r8s9t0u1
Revises: o5p6q7r8s9t0
Create Date: 2026-09-20

背景 (Issue 23: docs/etl2/prd/issue-23-remaining-tables-and-promote.md)：

把 patient / exam / imaging_study 接入 issue-20 的 stage→promote 机制，
另两个 ad-hoc 脚本（issue-6 / issue-13）不再直写生产表。

结构同 n4o5p6q7r8s9（dicom_series stage）：
- `LIKE <生产表> INCLUDING DEFAULTS`：列与默认值一致；
- 显式补与生产表同形的 UNIQUE 约束（改名避免全库重名）——promote 的
  幂等键，也是脚本写 stage 时 ON CONFLICT 的键；
- 不复制 FK / CHECK：stage 无级联风险，TRUNCATE 对生产零影响。

幂等键（实测 live pg_constraint）：
- patient       UNIQUE (center_code, anon_id)
- exam          UNIQUE (center_code, source_exam_hash)
- imaging_study UNIQUE (patient_id, dicom_study_uid, source)
"""
from collections.abc import Sequence

from alembic import op

revision: str = "p6q7r8s9t0u1"
down_revision: str | None = "o5p6q7r8s9t0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STAGE_DDL = [
    # patient
    """
    CREATE TABLE IF NOT EXISTS lnrs.lnrs_stage_patient (
      LIKE lnrs.lnrs_anon_patient INCLUDING DEFAULTS
    )
    """,
    """
    ALTER TABLE lnrs.lnrs_stage_patient
      ADD CONSTRAINT lnrs_stage_patient_uq_center UNIQUE (center_code, anon_id)
    """,
    """
    COMMENT ON TABLE lnrs.lnrs_stage_patient IS
      'patient 暂存表 (issue-23): ad-hoc 脚本先写这里, promote 按幂等键
       (center_code, anon_id) 上生产; 无 FK/CHECK, TRUNCATE 不影响生产'
    """,
    # exam
    """
    CREATE TABLE IF NOT EXISTS lnrs.lnrs_stage_exam (
      LIKE lnrs.lnrs_anon_exam INCLUDING DEFAULTS
    )
    """,
    """
    ALTER TABLE lnrs.lnrs_stage_exam
      ADD CONSTRAINT lnrs_stage_exam_uq_source UNIQUE (center_code, source_exam_hash)
    """,
    """
    COMMENT ON TABLE lnrs.lnrs_stage_exam IS
      'exam 暂存表 (issue-23): 幂等键 (center_code, source_exam_hash),
       promote 在 patient 之后执行 (FK 顺序)'
    """,
    # imaging_study
    """
    CREATE TABLE IF NOT EXISTS lnrs.lnrs_stage_imaging_study (
      LIKE lnrs.lnrs_anon_imaging_study INCLUDING DEFAULTS
    )
    """,
    """
    ALTER TABLE lnrs.lnrs_stage_imaging_study
      ADD CONSTRAINT lnrs_stage_imaging_study_uq
      UNIQUE (patient_id, dicom_study_uid, source)
    """,
    """
    COMMENT ON TABLE lnrs.lnrs_stage_imaging_study IS
      'imaging_study 暂存表 (issue-23): 幂等键 (patient_id, dicom_study_uid,
       source), promote 在 exam 之后执行 (FK 顺序)'
    """,
]


def upgrade() -> None:
    for ddl in _STAGE_DDL:
        op.execute(ddl)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lnrs.lnrs_stage_imaging_study;")
    op.execute("DROP TABLE IF EXISTS lnrs.lnrs_stage_exam;")
    op.execute("DROP TABLE IF EXISTS lnrs.lnrs_stage_patient;")
