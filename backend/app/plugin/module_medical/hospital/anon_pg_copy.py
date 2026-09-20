"""COPY+temp table 批量 upsert —— ETL 引擎与 promote 命令共用的单一落点。

## 为什么独立成模块（issue-19 prefactor）

原 `anon_etl_engine._copy_then_merge` 埋在 ETL 引擎里、只有一个调用点；
「先暂存再上」系列（issue-20/22）的 promote 需要同一机制。若 promote
import 整个 `anon_etl_engine` 会被反向拉起 ETL 依赖图；本模块只依赖
sqlalchemy + 标准库，双方都可安全 import，不产生循环依赖。

背景：`docs/etl2/findings/incident-20260920-test-cascade-delete.md` §4.3
（`_pg_available()` 被逐文件复制、没有单一落点的教训）。
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def copy_then_merge(
    db: AsyncSession,
    *,
    target_table_name: str,
    rows: list[dict[str, Any]],
    constraint: str,
    update_set: dict[str, Any],
    column_order: list[str],
) -> int:
    """用 COPY+temp table 路径批量 upsert 行到目标表（省医扩展性能优化）。

    工作流（单事务内）：
      1. CREATE TEMP TABLE tmp_<uuid> (LIKE target INCLUDING DEFAULTS)
      2. asyncpg copy_records_to_table → 流式灌入 tmp
      3. INSERT INTO target SELECT ... FROM tmp ON CONFLICT ON CONSTRAINT DO UPDATE
      4. （finally 显式 DROP，保证清理；崩溃时 PG 自动收 session-level temp）

    性能：COPY 比 executemany(BATCH_SIZE=1000) 快 10-50×（省医 nursing 13.8M 行
    实测 95 min → 预估 ~5-15 min）。

    参数：
      target_table_name: 目标表名（schema 已包含）
      rows: 待 upsert 行（dict，key 在 column_order 中）
      constraint: ON CONFLICT UNIQUE 约束名
      update_set: DO UPDATE SET 字段名列表（用 EXCLUDED 自动引用）
      column_order: 行转 tuple 列顺序（必须与目标表 INSERT 列一致）
    """
    if not rows:
        return 0
    raw = await (await db.connection()).get_raw_connection()
    inner = raw.driver_connection  # type: ignore[attr-defined]

    tmp_name = f"tmp_anon_{uuid.uuid4().hex[:12]}"
    try:
        # 用 LIKE target INCLUDING DEFAULTS 克隆结构（保留 DEFAULT 与 NOT NULL）
        # ON COMMIT DROP 在 asyncpg+SQLAlchemy 组合下偶尔失败，
        # 改用 finally 显式 DROP（保证清理；崩溃时 PG 自动收 session-level temp）
        await inner.execute(
            f"CREATE TEMP TABLE {tmp_name} (LIKE {target_table_name} INCLUDING DEFAULTS)"
        )
        records = [tuple(r.get(c) for c in column_order) for r in rows]
        await inner.copy_records_to_table(tmp_name, records=records, columns=column_order)
        set_clause = ", ".join(f'"{k}" = EXCLUDED."{k}"' for k in update_set.keys())
        col_list = ", ".join(f'"{c}"' for c in column_order)
        sql = (
            f'INSERT INTO {target_table_name} ({col_list}) '
            f'SELECT {col_list} FROM {tmp_name} '
            f'ON CONFLICT ON CONSTRAINT {constraint} DO UPDATE SET {set_clause}'
        )
        await db.execute(text(sql))
        return len(rows)
    finally:
        try:
            await inner.execute(f"DROP TABLE IF EXISTS {tmp_name}")
        except Exception:
            pass
