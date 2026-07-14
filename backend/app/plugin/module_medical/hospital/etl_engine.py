"""ETL 引擎核心 — DuckDB 读 parquet → 应用映射规则 → 批量写入 PostgreSQL。

设计要点：
- DuckDB 用独立连接（不复用 repository.py 的单例锁，避免阻塞查询 API）
- 写入用 SQLAlchemy Core insert().values() 批量（不用 ORM，慢）
- 幂等性：导入前 DELETE WHERE tenant_id=?，确保重复导入不产生重复行
- JSONB：DuckDB 的 JSON 类型经 Python 绑定返回为 str，需 json.loads 转 dict
- 进度回调：每张表导入后回调，由调用方写 Redis
- 表达式变换用预定义函数字典 TRANSFORM_FUNCTIONS（安全，非 eval）
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

import duckdb
from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.path_conf import BASE_DIR
from app.core.logger import log

from .model import TGT_TABLE_MODELS
from .model import MappingRuleModel

# 预定义转换函数（安全，非 eval；transform_value 存函数 key 而非表达式字符串）
TRANSFORM_FUNCTIONS: dict[str, Callable[[Any], Any]] = {
    "year_to_date": lambda val: f"{int(val)}-01-01" if val else None,
    # 珠江-新桥模板当前全是 rename，无 expression；预留扩展点
}

# JSONB 列名集合（按目标表分组）——这些列的值需要从 str(json) 转 dict
# 从 ORM 模型的 JSONB 列自动推导
_JSONB_COLUMNS: dict[str, set[str]] = {
    table_name: {
        col.name
        for col in model.__table__.columns
        if "JSONB" in str(col.type) or "JSON" in str(col.type)
    }
    for table_name, model in TGT_TABLE_MODELS.items()
}

BATCH_SIZE = 500


def resolve_data_dir(data_dir: str) -> Path:
    """解析数据目录路径。

    相对路径 → 相对项目根（BASE_DIR.parent）解析；
    绝对路径 → 直接用。
    """
    p = Path(data_dir)
    if not p.is_absolute():
        p = BASE_DIR.parent / p
    return p.resolve()


def apply_expression(func_key: str, value: Any) -> Any:
    """安全求值：仅允许 TRANSFORM_FUNCTIONS 字典里已注册的函数。"""
    fn = TRANSFORM_FUNCTIONS.get(func_key)
    if fn is None:
        raise ValueError(f"未注册的转换函数: {func_key}")
    return fn(value)


def _group_rules_by_src(
    rules: list[MappingRuleModel],
) -> dict[str, list[MappingRuleModel]]:
    """按 src_table 分组映射规则。"""
    groups: dict[str, list[MappingRuleModel]] = defaultdict(list)
    for rule in rules:
        groups[rule.src_table].append(rule)
    return groups


def _read_parquet_rows(data_dir: Path, src_table: str) -> tuple[list[str], list[tuple]]:
    """用独立 DuckDB 连接读取 parquet，返回 (列名列表, 行列表)。

    每次调用新建连接，不复用单例（避免与查询 API 的锁竞争）。
    """
    parquet_path = data_dir / f"{src_table}.parquet"
    if not parquet_path.exists():
        raise FileNotFoundError(f"源数据文件不存在: {parquet_path}")

    con = duckdb.connect(database=":memory:")
    try:
        cur = con.execute(f"SELECT * FROM read_parquet('{parquet_path.as_posix()}')")
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        return cols, rows
    finally:
        con.close()


def _transform_row(
    row_dict: dict[str, Any],
    rules: list[MappingRuleModel],
    tenant_id: int,
    jsonb_columns: set[str],
) -> dict[str, Any]:
    """按映射规则转换单行，返回目标表列名→值的字典。

    步骤：
    1. rename: tgt_field = row_dict[src_field]
    2. constant: tgt_field = transform_value
    3. expression: tgt_field = TRANSFORM_FUNCTIONS[key](row_dict[src_field])
    4. 注入 tenant_id
    5. JSONB 列：str → json.loads → dict
    """
    result: dict[str, Any] = {"tenant_id": tenant_id}

    for rule in rules:
        if rule.transform_type == "rename":
            val = row_dict.get(rule.src_field)
        elif rule.transform_type == "constant":
            val = rule.transform_value
        elif rule.transform_type == "expression":
            src_val = row_dict.get(rule.src_field)
            val = apply_expression(rule.transform_value, src_val) if rule.transform_value else None
        else:
            continue

        # JSONB 列：JSON 字符串转 dict
        if rule.tgt_field in jsonb_columns and isinstance(val, str):
            try:
                val = json.loads(val)
            except (ValueError, TypeError):
                pass  # 非 JSON 字符串，保持原值

        result[rule.tgt_field] = val

    return result


def _normalize_value(val: Any) -> Any:
    """把 DuckDB 返回的复合类型转为 PG 可接受的 Python 对象。"""
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, (datetime, date)):
        return val  # SQLAlchemy 能正确处理
    return val


def _clean_row(row: dict[str, Any], model) -> dict[str, Any]:
    """过滤掉目标模型不存在的列，并归一化值类型。"""
    valid_cols = {c.name for c in model.__table__.columns}
    return {
        k: _normalize_value(v) for k, v in row.items() if k in valid_cols
    }


async def import_one_table(
    db: AsyncSession,
    data_dir: Path,
    src_table: str,
    rules: list[MappingRuleModel],
    tenant_id: int,
) -> int:
    """导入单张源表到对应目标表，返回实际入库行数。

    流程：
    1. DuckDB 读 parquet
    2. 应用映射规则转换每一行
    3. DELETE 旧数据（幂等）
    4. 批量 INSERT（用 ON CONFLICT DO NOTHING 跳过重复键）

    注意：本函数不会自动 commit，由调用方控制事务。
    若需单表原子性，调用方应在执行前后 begin/commit；
    若需整体事务，调用方在外层用 begin() 包裹。
    """
    tgt_table = rules[0].tgt_table
    model = TGT_TABLE_MODELS.get(tgt_table)
    if model is None:
        raise ValueError(f"未知目标表: {tgt_table}（源表 {src_table}）")

    jsonb_cols = _JSONB_COLUMNS.get(tgt_table, set())

    # 1. 读 parquet
    cols, raw_rows = _read_parquet_rows(data_dir, src_table)
    if not raw_rows:
        log.warning(f"ETL: 源表 {src_table} 无数据，跳过")
        return 0

    # 2. 转换每一行
    transformed_rows = []
    for raw in raw_rows:
        row_dict = {col: val for col, val in zip(cols, raw)}
        row_dict = _transform_row(row_dict, rules, tenant_id, jsonb_cols)
        row_dict = _clean_row(row_dict, model)
        transformed_rows.append(row_dict)

    # 3. DELETE 旧数据（幂等）
    await db.execute(delete(model).where(model.tenant_id == tenant_id))

    # 4. 批量 INSERT — 用 ON CONFLICT DO NOTHING 跳过重复键
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    inserted = 0
    for i in range(0, len(transformed_rows), BATCH_SIZE):
        batch = transformed_rows[i : i + BATCH_SIZE]
        stmt = pg_insert(model).values(batch).on_conflict_do_nothing()
        result = await db.execute(stmt)
        inserted += result.rowcount if hasattr(result, "rowcount") else len(batch)

    return inserted


async def run_etl_pipeline(
    db: AsyncSession,
    data_dir: Path,
    tenant_id: int,
    mapping_rules: list[MappingRuleModel],
    on_table_done: Callable[[str, int], Any] | None = None,
) -> dict[str, int]:
    """运行完整 ETL 管线：逐表导入，每表独立提交。

    重要：调用方**不要**把此函数包在 `async with session.begin()` 块里，
    否则会与 import_one_table 内部的 SAVEPOINT 行为冲突。
    本函数对每张表独立提交，单表失败不影响其他表。

    参数:
        db: 独立的数据库会话（调用方负责 begin/commit）
        data_dir: 源数据目录（已解析的绝对路径）
        tenant_id: 租户/医院 ID（写入每行的 tenant_id）
        mapping_rules: 该医院的全部映射规则
        on_table_done: 每张表导入完成后的回调

    返回:
        {src_table: rows_imported} 各表导入行数
    """
    grouped = _group_rules_by_src(mapping_rules)
    result: dict[str, int] = {}

    for src_table, rules in grouped.items():
        try:
            rows = await import_one_table(
                db=db,
                data_dir=data_dir,
                src_table=src_table,
                rules=rules,
                tenant_id=tenant_id,
            )
            result[src_table] = rows
            log.info(f"ETL: {src_table} → 导入 {rows} 行")
            if on_table_done:
                if _is_async(on_table_done):
                    await on_table_done(src_table, rows)
                else:
                    on_table_done(src_table, rows)
        except Exception as e:
            log.error(f"ETL: 导入 {src_table} 整体失败: {e!s}")
            result[src_table] = 0

    return result


def _is_async(func: Callable) -> bool:
    """判断回调是否为协程函数。"""
    import asyncio
    return asyncio.iscoroutinefunction(func)
