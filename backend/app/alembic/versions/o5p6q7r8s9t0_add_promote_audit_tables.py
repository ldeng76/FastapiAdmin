"""新增 promote 审计表 — promote 护栏（issue-22）

Revision ID: o5p6q7r8s9t0
Revises: n4o5p6q7r8s9
Create Date: 2026-09-20

背景 (Issue 22: docs/etl2/prd/issue-22-promote-guardrails.md)：

issue-20 打通了 stage→promote，但 promote 自身出错没护栏。本迁移建两张
审计表：

- `lnrs.lnrs_promote_audit`：每次 promote（含 dry-run）一条 —— batch_id /
  目标表 / 模式 / stage 行数 / 实际 upsert 行数 / 校验结果 / 违规明细 /
  触发者 / 时间戳 / 回滚时间。
- `lnrs.lnrs_promote_audit_row`：批次行级明细 —— 业务键（如 dicom_study_uid）、
  动作（insert/update）、update 行的 promote 前完整像（jsonb）。
  回滚 = 删 insert 行 + 按 preimage 还原 update 行，只撤销该批次。

关键约束（AC）：审计表**不在任何 promote 目标路径上**（promote 目标是
`lnrs_anon_*` 生产表），因此永远不会被 promote 覆盖或清空。
"""
from collections.abc import Sequence

from alembic import op

revision: str = "o5p6q7r8s9t0"
down_revision: str | None = "n4o5p6q7r8s9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AUDIT_DDL = [
    """
    CREATE TABLE IF NOT EXISTS lnrs.lnrs_promote_audit (
      audit_id     bigserial PRIMARY KEY,
      batch_id     uuid        NOT NULL,
      target_table text        NOT NULL,
      mode         text        NOT NULL CHECK (mode IN ('dry_run', 'apply')),
      stage_rows   integer     NOT NULL,
      upsert_rows  integer     NOT NULL DEFAULT 0,
      validation   text        NOT NULL CHECK (validation IN ('passed', 'rejected')),
      violations   jsonb       NOT NULL DEFAULT '[]'::jsonb,
      actor        text        NOT NULL,
      created_at   timestamptz NOT NULL DEFAULT now(),
      rolled_back_at timestamptz
    )
    """,
    """
    CREATE INDEX lnrs_promote_audit_batch_id_idx
      ON lnrs.lnrs_promote_audit (batch_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS lnrs.lnrs_promote_audit_row (
      id           bigserial PRIMARY KEY,
      audit_id     bigint  NOT NULL REFERENCES lnrs.lnrs_promote_audit(audit_id),
      business_key text    NOT NULL,
      action       text    NOT NULL CHECK (action IN ('insert', 'update')),
      preimage     jsonb
    )
    """,
    """
    CREATE INDEX lnrs_promote_audit_row_audit_idx
      ON lnrs.lnrs_promote_audit_row (audit_id)
    """,
    """
    COMMENT ON TABLE lnrs.lnrs_promote_audit IS
      'promote 审计 (issue-22): 每次 promote/dry-run 一条, 回滚按 batch_id 定位。
       2026-09-20 (issue-22, 源自 incident-20260920 复盘 §10)'
    """,
]


def upgrade() -> None:
    for ddl in _AUDIT_DDL:
        op.execute(ddl)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lnrs.lnrs_promote_audit_row;")
    op.execute("DROP TABLE IF EXISTS lnrs.lnrs_promote_audit;")
