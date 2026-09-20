"""copy_then_merge（COPY+temp table 批量 upsert）的行为测试。

被测函数原为 anon_etl_engine._copy_then_merge，issue-19 抽到
anon_pg_copy 模块供 ETL 引擎与 promote 命令共用；本测试锁住其语义：

1. 首次 upsert：全部 INSERT
2. 重复 upsert（ON CONFLICT DO UPDATE）：行数不变、指定字段被更新
3. 空行列表：no-op 返回 0

沙箱用法：cd backend && ENVIRONMENT=test uv run pytest tests/anon_etl/test_pg_copy_merge.py
"""

from __future__ import annotations

import asyncio

import pytest

from _db_guard import PG_READY, SKIP_REASON

SCRATCH_TABLE = "lnrs.lnrs_scratch_copy_merge_test"


def _setup_sql() -> list[str]:
    return [
        f"DROP TABLE IF EXISTS {SCRATCH_TABLE}",
        f"CREATE TABLE {SCRATCH_TABLE} ("
        "  id integer PRIMARY KEY,"
        "  payload text NOT NULL,"
        "  rev integer NOT NULL DEFAULT 0)",
        f"ALTER TABLE {SCRATCH_TABLE} ADD CONSTRAINT"
        " lnrs_scratch_copy_merge_uq UNIQUE (id)",
    ]


@pytest.mark.skipif(not PG_READY, reason=SKIP_REASON)
class TestCopyThenMerge:
    def test_upsert_insert_then_update_idempotent(self):
        asyncio.run(self._body())

    @staticmethod
    async def _body():
        from sqlalchemy import text

        from app.core.database import async_db_session
        from app.plugin.module_medical.hospital.anon_pg_copy import copy_then_merge

        async with async_db_session() as session:
            for stmt in _setup_sql():
                await session.execute(text(stmt))
            try:
                # 1) 首次 upsert → 全部 INSERT
                n = await copy_then_merge(
                    session,
                    target_table_name=SCRATCH_TABLE,
                    rows=[{"id": 1, "payload": "a", "rev": 1},
                          {"id": 2, "payload": "b", "rev": 1}],
                    constraint="lnrs_scratch_copy_merge_uq",
                    update_set={"payload": 1, "rev": 1},
                    column_order=["id", "payload", "rev"],
                )
                await session.commit()
                assert n == 2
                cnt, = (await session.execute(
                    text(f"SELECT COUNT(*) FROM {SCRATCH_TABLE}"))).fetchone()
                assert cnt == 2

                # 2) 重放含 1 行更新 + 1 行新增 → upsert 语义
                n = await copy_then_merge(
                    session,
                    target_table_name=SCRATCH_TABLE,
                    rows=[{"id": 2, "payload": "b2", "rev": 2},
                          {"id": 3, "payload": "c", "rev": 1}],
                    constraint="lnrs_scratch_copy_merge_uq",
                    update_set={"payload": 1, "rev": 1},
                    column_order=["id", "payload", "rev"],
                )
                await session.commit()
                assert n == 2
                rows = (await session.execute(text(
                    f"SELECT id, payload, rev FROM {SCRATCH_TABLE}"
                    " ORDER BY id"))).fetchall()
                assert rows == [(1, "a", 1), (2, "b2", 2), (3, "c", 1)]

                # 3) 空行 → no-op
                n = await copy_then_merge(
                    session,
                    target_table_name=SCRATCH_TABLE,
                    rows=[],
                    constraint="lnrs_scratch_copy_merge_uq",
                    update_set={"payload": 1},
                    column_order=["id", "payload", "rev"],
                )
                assert n == 0
            finally:
                await session.execute(text(f"DROP TABLE IF EXISTS {SCRATCH_TABLE}"))
                await session.commit()
