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

import asyncio
import json
import re
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

# 来源表名校验：仅允许字母/数字/下划线，避免 path traversal
_SRC_TABLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

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

    安全：
    - 拒绝包含路径分隔符或 .. 的 src_table（MappingRuleModel 在 DB 中可写）
    - 解析后的绝对路径必须仍在 data_dir 内
    """
    if not _SRC_TABLE_RE.match(src_table):
        raise ValueError(f"非法的源表名: {src_table!r}")
    parquet_path = (data_dir / f"{src_table}.parquet").resolve()
    try:
        data_dir_resolved = data_dir.resolve()
    except OSError as e:
        raise ValueError(f"无法解析 data_dir: {data_dir}") from e
    if data_dir_resolved not in parquet_path.parents and parquet_path.parent != data_dir_resolved:
        raise ValueError(f"源表路径越界: {parquet_path}")
    if not parquet_path.exists():
        raise FileNotFoundError(f"源数据文件不存在: {parquet_path}")

    con = duckdb.connect(database=":memory:")
    try:
        # 使用参数化读文件，避免 f-string 拼接路径
        cur = con.execute("SELECT * FROM read_parquet(?)", [parquet_path.as_posix()])
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
    dict_cache: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    """按映射规则转换单行，返回目标表列名→值的字典。

    步骤：
    1. rename: tgt_field = row_dict[src_field]
    2. constant: tgt_field = transform_value
    3. expression: tgt_field = TRANSFORM_FUNCTIONS[key](row_dict[src_field])
    4. dict: tgt_field = 通过 dict_cache 查标准值（预加载的映射缓存）
    5. 注入 tenant_id
    6. JSONB 列：str → json.loads → dict；解析失败记日志后保留原值让 INSERT 报错

    dict_cache: {dict_type: {raw_label_lower: dict_value}}，由 import_one_table 预加载。
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
        elif rule.transform_type == "dict":
            # 字典映射：通过预加载的 dict_cache 查标准值
            src_val = row_dict.get(rule.src_field)
            val = _lookup_dict_cache(dict_cache, rule.transform_value, src_val)
        else:
            # schema 层已校验只允许 rename/constant/expression/dict；
            # 留此兜底防止未来扩展 transform_type 时静默丢列
            log.error(
                "ETL: 未知 transform_type=%r (tgt_field=%s)，已跳过该列",
                rule.transform_type,
                rule.tgt_field,
            )
            continue

        # JSONB 列：JSON 字符串转 dict；解析失败记日志后保留原值让 INSERT 报错
        if rule.tgt_field in jsonb_columns and isinstance(val, str):
            try:
                val = json.loads(val)
            except (ValueError, TypeError) as e:
                log.warning(
                    "ETL: JSONB 列 %s 解析失败: %s (src=%s.%s)",
                    rule.tgt_field, e, rule.src_table, rule.src_field,
                )

        result[rule.tgt_field] = val

    return result


def _lookup_dict_cache(
    dict_cache: dict[str, dict[str, str]] | None,
    dict_type: str | None,
    raw_label: Any,
) -> str | None:
    """从预加载的 dict_cache 中查找标准值。

    dict_cache 结构: {dict_type: {raw_label_lower: dict_value}}
    未命中返回 None（由调用方决定是否写 unmatched）。
    """
    if not dict_cache or not dict_type or raw_label is None:
        return None
    type_cache = dict_cache.get(dict_type)
    if not type_cache:
        return None
    return type_cache.get(str(raw_label).strip().lower())


async def _preload_dict_cache(
    rules: list[MappingRuleModel],
    tenant_id: int,
    hospital_id: int | None,
    redis: Any,
) -> dict[str, dict[str, str]]:
    """预加载 dict 类型规则的映射缓存。

    返回 {dict_type: {raw_label_lower: dict_value}}，供 _transform_row 快速查表。
    无 dict 规则或缺少 redis/hospital_id 时返回空 dict。
    """
    if not redis or not hospital_id:
        # 有 dict 规则但缺 redis/hospital_id 时，所有 dict 列将静默产出 None
        has_dict_rules = any(
            r.transform_type == "dict" for r in rules
        )
        if has_dict_rules:
            log.warning(
                "ETL: dict 缓存未预热（redis=%s, hospital_id=%s），"
                "配置了 dict 规则的列将产出 None",
                bool(redis), hospital_id,
            )
        return {}

    # 收集所有 dict 类型规则涉及的 dict_type
    dict_types: set[str] = set()
    for rule in rules:
        if rule.transform_type == "dict" and rule.transform_value:
            dict_types.add(rule.transform_value)

    if not dict_types:
        return {}

    cache: dict[str, dict[str, str]] = {}
    try:
        from app.plugin.module_medical.dict_mapping.service import DictMappingService

        # 构造一个轻量 auth 对象（仅用于传递 tenant_id 和 db）
        # 注意：ETL 场景无真实用户，使用独立 session 查映射
        for dict_type in dict_types:
            # 查该类型的所有映射（跨医院 + 平台默认）
            mappings = await _fetch_dict_mappings(dict_type, tenant_id, hospital_id)
            if mappings:
                cache[dict_type] = mappings
    except Exception as e:
        log.warning(f"ETL: dict 缓存预加载失败: {e!s}")

    return cache


async def _fetch_dict_mappings(
    dict_type: str, tenant_id: int, hospital_id: int,
) -> dict[str, str]:
    """从 DB 加载某 dict_type 的全部映射，返回 {raw_label_lower: dict_value}。

    优先查 hospital_id 专属映射，再查平台默认（tenant_id=1）映射。
    """
    from sqlalchemy import select

    from app.api.v1.module_system.dict.model import DictDataModel, DictTypeModel
    from app.core.database import async_db_session
    from app.plugin.module_medical.dict_mapping.model import DictMappingModel

    result: dict[str, str] = {}

    async with async_db_session() as db:
        # 查 dict_type_id
        dt_result = await db.execute(
            select(DictTypeModel).where(DictTypeModel.dict_type == dict_type)
        )
        dt_obj = dt_result.scalars().first()
        if not dt_obj:
            return result

        # 查映射（该医院 + 平台默认）
        sql = select(DictMappingModel).where(
            DictMappingModel.dict_type_id == dt_obj.id,
            DictMappingModel.hospital_id.in_([hospital_id, 1]),  # 1 = 平台默认
        )
        mappings_result = await db.execute(sql)
        mappings = mappings_result.scalars().all()

        for m in mappings:
            if m.dict_data_id:
                dd_result = await db.execute(
                    select(DictDataModel).where(DictDataModel.id == m.dict_data_id)
                )
                dd_obj = dd_result.scalars().first()
                if dd_obj:
                    result[m.raw_label.lower()] = dd_obj.dict_value

    return result


def _normalize_value(val: Any) -> Any:
    """把 DuckDB 返回的复合类型转为 PG 可接受的 Python 对象。

    注意：Decimal 不要转 float，会丢精度 — PG NUMERIC 原生支持 Decimal。
    """
    if isinstance(val, (datetime, date)):
        return val  # SQLAlchemy 能正确处理
    return val  # Decimal/str/int/float 全部透传


def _clean_row(row: dict[str, Any], model) -> dict[str, Any]:
    """过滤掉目标模型不存在的列，并归一化值类型。

    未知列会被丢弃并打 warning，避免模型字段重命名后旧规则静默丢数据。
    nullable=False 且有 default 的列：源值为 None 时用 default 填充（哨兵值模式）。
    """
    valid_cols = {c.name for c in model.__table__.columns}
    cleaned: dict[str, Any] = {}
    for k, v in row.items():
        if k in valid_cols:
            # nullable=False 且源值为 None：用列 default 填充（如 nodule_no → "UNKNOWN"）
            if v is None:
                col = getattr(model, k, None)
                if col is not None and hasattr(col, "property"):
                    column = col.property.columns[0]
                    if not column.nullable and column.default is not None:
                        # callable default（如 datetime.now）或 scalar default
                        default_val = column.default.arg() if callable(column.default.arg) else column.default.arg
                        cleaned[k] = default_val
                        continue
            cleaned[k] = _normalize_value(v)
        else:
            log.warning(
                "ETL: 目标表 %s 不存在列 %s，已丢弃", model.__tablename__, k
            )
    return cleaned


async def import_one_table(
    db: AsyncSession,
    data_dir: Path,
    src_table: str,
    rules: list[MappingRuleModel],
    tenant_id: int,
    hospital_id: int | None = None,
    redis: Any = None,
) -> int:
    """导入单张源表到对应目标表，返回实际入库行数。

    流程：
    1. DuckDB 读 parquet
    2. 预加载 dict 类型映射缓存（如有 dict 规则）
    3. 应用映射规则转换每一行
    4. DELETE 旧数据（幂等）
    5. 批量 INSERT（用 ON CONFLICT DO NOTHING 跳过重复键）

    注意：本函数不会自动 commit，由调用方控制事务。
    若需单表原子性，调用方应在执行前后 begin/commit；
    若需整体事务，调用方在外层用 begin() 包裹。
    """
    tgt_table = rules[0].tgt_table
    model = TGT_TABLE_MODELS.get(tgt_table)
    if model is None:
        raise ValueError(f"未知目标表: {tgt_table}（源表 {src_table}）")

    jsonb_cols = _JSONB_COLUMNS.get(tgt_table, set())

    # 1. 读 parquet（同步阻塞操作，放到线程池避免阻塞事件循环）
    cols, raw_rows = await asyncio.to_thread(_read_parquet_rows, data_dir, src_table)
    if not raw_rows:
        log.warning(f"ETL: 源表 {src_table} 无数据，跳过")
        return 0

    # 2. 预加载 dict 映射缓存（避免逐行查 Redis/DB）
    dict_cache = await _preload_dict_cache(rules, tenant_id, hospital_id, redis)

    # 3. 转换每一行
    transformed_rows = []
    for raw in raw_rows:
        row_dict = {col: val for col, val in zip(cols, raw)}
        row_dict = _transform_row(row_dict, rules, tenant_id, jsonb_cols, dict_cache)
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
    hospital_id: int | None = None,
    redis: Any = None,
) -> dict[str, int]:
    """运行完整 ETL 管线：按源表分组逐表导入。

    事务模型：
    - 本函数不提交，调用方应在外层 `async with async_db_session()`
      内运行并在结束时 commit；
    - 单张表抛错时整体事务回滚（包括已 DELETE 旧数据），
      对应 hospital 仍处于 mapping_configured 状态；
    - 每张表内部把不预期的异常记录到 result 并继续处理后续表，
      但不会自动重试或回滚已经 INSERT 的行。

    参数:
        db: 独立的数据库会话（调用方负责 begin/commit）
        data_dir: 源数据目录（已解析的绝对路径）
        tenant_id: 租户/医院 ID（写入每行的 tenant_id）
        mapping_rules: 该医院的全部映射规则
        on_table_done: 每张表导入完成后的回调
        hospital_id: 医院 ID（dict 映射需要， tenant_id 可能不等于 hospital_id）
        redis: Redis 连接（dict 映射缓存需要）

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
                hospital_id=hospital_id,
                redis=redis,
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
