"""promote 护栏（issue-22）：前置校验闸 + 审计记录 + 按批次回滚。

三道护栏（docs/etl2/prd/issue-22-promote-guardrails.md）：

1. **前置校验闸** `validate_stage`：promote 前校验 stage 数据的不变量 ——
   非空（空集是异常不是通过，复盘 §4.4 放大 4 教训）、行数一致、
   NOT NULL/CHECK（temp 克隆目标表结构实插验证）、外键完整性
   （查 live `pg_constraint`，不读 DDL 文件 —— 复盘 §3.1 教训）。
   任一不过 → 拒绝 promote，生产库零变化。
2. **审计记录** `record_audit` / 行级明细：每次 promote（含 dry-run）写
   `lnrs.lnrs_promote_audit`（+ 明细 `lnrs_promote_audit_row`）。审计表
   不在任何 promote 目标路径上，不会被覆盖。
3. **按批次回滚** `rollback_batch`：明细表存 insert 行的业务键 + update 行
   的 promote 前完整像（preimage jsonb）。回滚 = 删 insert 行 + 按
   preimage 还原 update 行，只撤销该批次，不碰其它批次写入的行。

选型（PRD Notes 二选一）：选 (a) 审计表记「本批次主键集合 + update 前像」，
不选 (b) 全表快照 —— dicom_series 88 MB / patient 193 MB / exam 750 MB，
按行集撤销的成本与批次行数成正比，远低于整表快照。

依赖约束：只依赖 sqlalchemy + 标准库（同 anon_pg_copy 的理由，
issue-19 复盘 §4.3），供 promote 脚本与测试共同 import。
"""
from __future__ import annotations

import getpass
import json
import uuid
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

AUDIT_TABLE = "lnrs.lnrs_promote_audit"
AUDIT_ROW_TABLE = "lnrs.lnrs_promote_audit_row"


class PromoteRefused(Exception):
    """校验闸拒绝 promote —— 携带违规不变量清单。"""

    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        super().__init__("; ".join(violations))


async def current_actor() -> str:
    """promote 触发者：登录用户名，取不到退回 unknown。"""
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


# --------------------------------------------------------------------------- #
# 1. 前置校验闸
# --------------------------------------------------------------------------- #


async def validate_stage(
    db: AsyncSession,
    *,
    stage_table: str,
    prod_table: str,
    promote_columns: list[str],
) -> list[str]:
    """校验 stage 数据不变量，返回违规清单；空清单 = 通过。

    检查项（AC）：
    - 非空：空集单独判为异常（复盘 §4.4：「空集会让任何一致性检查通过」）；
    - 行数一致：读到的行数与 stage COUNT(*) 一致（本次预计 promote 集合）；
    - NOT NULL / CHECK：temp 克隆目标表（含 CHECK 约束；NOT NULL 恒复制）
      实插 stage 行验证，SAVEPOINT 包裹防事务污染；
    - 外键完整性：查 live pg_constraint（单列 FK），stage 行引用的父行
      必须在生产表存在（本次批次只 promote 一张表，父行在生产）。
    """
    violations: list[str] = []

    n_stage = int((await db.execute(
        text(f"SELECT COUNT(*) FROM {stage_table}")
    )).scalar() or 0)
    if n_stage == 0:
        return [f"空集异常: {stage_table} 为空，拒绝 promote"
                "（空集会让任何一致性检查通过，复盘 §4.4）"]

    rows = (await db.execute(
        text(f"SELECT {', '.join(promote_columns)} FROM {stage_table}")
    )).mappings().all()
    if len(rows) != n_stage:
        violations.append(
            f"行数不一致: stage COUNT(*)={n_stage} 但本次预计 promote 读到 {len(rows)} 行")

    violations += await _check_not_null_check(
        db, stage_table=stage_table, prod_table=prod_table,
        promote_columns=promote_columns)
    violations += await _check_fk(
        db, stage_table=stage_table, prod_table=prod_table,
        promote_columns=promote_columns)
    return violations


async def _check_not_null_check(
    db: AsyncSession, *, stage_table: str, prod_table: str,
    promote_columns: list[str],
) -> list[str]:
    """把 stage 行实插进目标表结构克隆，捕获 NOT NULL / CHECK 违规。"""
    tmp = f"tmp_validate_{uuid.uuid4().hex[:12]}"
    col_list = ", ".join(promote_columns)
    await db.execute(text(
        f"CREATE TEMP TABLE {tmp}"
        f" (LIKE {prod_table} INCLUDING DEFAULTS INCLUDING CONSTRAINTS)"
    ))
    await db.execute(text("SAVEPOINT before_validate_insert"))
    try:
        await db.execute(text(
            f"INSERT INTO {tmp} ({col_list}) SELECT {col_list} FROM {stage_table}"
        ))
    except Exception as e:  # noqa: BLE001 —— 任何约束违规都算校验失败
        await db.execute(text("ROLLBACK TO SAVEPOINT before_validate_insert"))
        return [f"非空/CHECK 约束违规: {type(e).__name__}: {str(e).splitlines()[0][:300]}"]
    finally:
        await db.execute(text(f"DROP TABLE IF EXISTS {tmp}"))
    return []


async def _check_fk(
    db: AsyncSession, *, stage_table: str, prod_table: str,
    promote_columns: list[str],
) -> list[str]:
    """按 live pg_constraint 逐个校验 stage 外键引用（单列 FK）。"""
    fks = (await db.execute(text("""
        SELECT con.conname AS name,
               sa.attname  AS src_col,
               nsp.nspname || '.' || ct.relname AS ref_table,
               ta.attname  AS ref_col
        FROM pg_constraint con
        JOIN pg_class t   ON t.oid = con.conrelid
        JOIN pg_class ct  ON ct.oid = con.confrelid
        JOIN pg_namespace nsp ON nsp.oid = ct.relnamespace
        JOIN unnest(con.conkey) WITH ORDINALITY AS ck(attnum, ord) ON true
        JOIN unnest(con.confkey) WITH ORDINALITY AS fk(attnum, ord)
          ON fk.ord = ck.ord
        JOIN pg_attribute sa ON sa.attrelid = con.conrelid AND sa.attnum = ck.attnum
        JOIN pg_attribute ta ON ta.attrelid = con.confrelid AND ta.attnum = fk.attnum
        WHERE con.contype = 'f'
          AND con.conrelid = to_regclass(:prod)
          AND cardinality(con.conkey) = 1
    """), {"prod": prod_table})).mappings().all()

    violations: list[str] = []
    for fk in fks:
        src, ref_t, ref_c = fk["src_col"], fk["ref_table"], fk["ref_col"]
        if src not in promote_columns:
            continue  # 该列不参与 promote，stage 值不影响生产
        bad = (await db.execute(text(f"""
            SELECT COUNT(*), MIN(s.{src}::text) FROM {stage_table} s
            LEFT JOIN {ref_t} r ON s.{src} = r.{ref_c}
            WHERE s.{src} IS NOT NULL AND r.{ref_c} IS NULL
        """))).one()
        if bad[0]:
            violations.append(
                f"外键完整性违规 [{fk['name']}]: stage {src} 有 {bad[0]} 行"
                f"（如 {bad[1]}）在 {ref_t}.{ref_c} 无父行")
    return violations


# --------------------------------------------------------------------------- #
# 2. 审计记录
# --------------------------------------------------------------------------- #


async def record_audit(
    db: AsyncSession,
    *,
    batch_id: uuid.UUID,
    target_table: str,
    mode: str,
    stage_rows: int,
    validation: str,
    violations: list[str] | None = None,
    upsert_rows: int = 0,
    actor: str | None = None,
) -> int:
    """写一条 promote 审计，返回 audit_id。供后续行级明细挂靠与回滚定位。"""

    r = await db.execute(text(f"""
        INSERT INTO {AUDIT_TABLE}
          (batch_id, target_table, mode, stage_rows, upsert_rows,
           validation, violations, actor)
        VALUES (:b, :t, :m, :sr, :ur, :v, CAST(:vio AS jsonb), :a)
        RETURNING audit_id
    """), {
        "b": str(batch_id), "t": target_table, "m": mode,
        "sr": stage_rows, "ur": upsert_rows, "v": validation,
        "vio": json.dumps(violations or []), "a": actor or await current_actor(),
    })
    return int(r.scalar_one())


async def record_batch_detail(
    db: AsyncSession,
    *,
    audit_id: int,
    stage_table: str,
    prod_table: str,
    key_column: str,
) -> None:
    """合并前调用：把本批次「insert 行业务键 + update 行 promote 前像」写进明细。

    服务端两条 INSERT...SELECT 完成，不把行拉回 Python —— 行数与
    dicom_series（88 MB）量级相当时仍是一次顺序写。
    必须在 copy_then_merge **之前**执行（preimage 是合并前的值）。
    """
    await db.execute(text(f"""
        INSERT INTO {AUDIT_ROW_TABLE} (audit_id, business_key, action, preimage)
        SELECT :aid, p.{key_column}, 'update', to_jsonb(p)
        FROM {prod_table} p
        WHERE p.{key_column} IN (SELECT {key_column} FROM {stage_table})
    """), {"aid": audit_id})
    await db.execute(text(f"""
        INSERT INTO {AUDIT_ROW_TABLE} (audit_id, business_key, action)
        SELECT :aid, s.{key_column}, 'insert'
        FROM {stage_table} s
        WHERE NOT EXISTS (
          SELECT 1 FROM {prod_table} p WHERE p.{key_column} = s.{key_column}
        )
    """), {"aid": audit_id})


async def finalize_audit(db: AsyncSession, *, audit_id: int, upsert_rows: int) -> None:
    """合并后回填实际 upsert 行数。"""
    await db.execute(text(
        f"UPDATE {AUDIT_TABLE} SET upsert_rows = :n WHERE audit_id = :aid"
    ), {"n": upsert_rows, "aid": audit_id})


async def audit_by_batch(db: AsyncSession, batch_id: str) -> list[dict[str, Any]]:
    """审计查询：给定 batch_id 回答「动了哪些表、多少行、校验结果如何」。"""
    rows = (await db.execute(text(f"""
        SELECT audit_id, batch_id, target_table, mode, stage_rows, upsert_rows,
               validation, violations, actor, created_at, rolled_back_at
        FROM {AUDIT_TABLE} WHERE batch_id = CAST(:b AS uuid)
        ORDER BY audit_id
    """), {"b": batch_id})).mappings().all()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------- #
# 3. 按批次回滚
# --------------------------------------------------------------------------- #


async def rollback_batch(
    db: AsyncSession,
    *,
    batch_id: str,
    prod_table: str,
    key_column: str,
    promote_columns: list[str],
) -> dict[str, int]:
    """按批次回滚一次 promote，返回 {"deleted": n, "restored": m}。

    - 只撤销该批次：delete/restore 都以明细表的 business_key 定位；
    - update 行按 preimage 整行还原（jsonb_populate_record 转回行类型，
      免去逐列手写类型转换）；
    - 已回滚的批次拒绝重复回滚；dry-run 批次无可回滚影响，同样拒绝。
    """
    audits = (await db.execute(text(f"""
        SELECT audit_id, mode, rolled_back_at FROM {AUDIT_TABLE}
        WHERE batch_id = CAST(:b AS uuid) AND mode = 'apply'
          AND validation = 'passed'
        ORDER BY audit_id
    """), {"b": batch_id})).mappings().all()
    if not audits:
        raise PromoteRefused([f"回滚失败: batch {batch_id} 无可回滚的 apply 审计记录"])
    if any(a["rolled_back_at"] is not None for a in audits):
        raise PromoteRefused([f"回滚失败: batch {batch_id} 已回滚过，拒绝重复回滚"])

    aids = [a["audit_id"] for a in audits]
    restore_set = ", ".join(f"{c} = (s.pre).{c}" for c in promote_columns)


    # 删除 insert 行：业务键来自明细，天然限定本批次
    del_res = await db.execute(text(f"""
        DELETE FROM {prod_table} p
        USING {AUDIT_ROW_TABLE} r
        WHERE r.audit_id IN :aids AND r.action = 'insert'
          AND p.{key_column}::text = r.business_key
    """).bindparams(bindparam("aids", expanding=True)), {"aids": aids})
    n_deleted = del_res.rowcount or 0

    # 还原 update 行：按 preimage
    res = await db.execute(text(f"""
        UPDATE {prod_table} p
        SET {restore_set}
        FROM (
          SELECT r.business_key,
                 jsonb_populate_record(NULL::{prod_table}, r.preimage) AS pre
          FROM {AUDIT_ROW_TABLE} r
          WHERE r.audit_id IN :aids AND r.action = 'update'
        ) s
        WHERE p.{key_column}::text = s.business_key
    """).bindparams(bindparam("aids", expanding=True)), {"aids": aids})
    n_restored = res.rowcount or 0

    await db.execute(text(
        f"UPDATE {AUDIT_TABLE} SET rolled_back_at = now() WHERE audit_id IN :aids"
    ).bindparams(bindparam("aids", expanding=True)), {"aids": aids})
    return {"deleted": n_deleted, "restored": n_restored}