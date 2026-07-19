"""ETL-1 主循环: Excel → Parquet。

执行顺序 (见计划 §3):
1. 单 sheet 直接转换 → parquet (universal_tables + hospital_tables)
2. 跨 sheet 合并 (derived_tables: diagnosis / surgery_record / anesthesia_event)
3. visit_id 反查 (visit_resolver.resolve_visits)
4. manifest 生成

性能策略:
- 列重命名 + 类型 cast 全部在 SQL 层做 (向量化)
- 仅当 ColumnSpec.transform 指向 normalize_newlines/json_load 等需要 Python 的清洗时,
  才走 row-level 后处理 (用 duckdb 的 Python UDF 注册, 仍在 SQL 层调用)
- 大表 (1M+ 行) 直接 COPY, 不物化到 Python 内存

安全策略 (复刻 etl_engine.py):
- target_table 必须满足 _SRC_TABLE_RE
- 输出路径必须解析后仍在 out_dir 内 (防 path traversal)
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import OrderedDict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from app.config.path_conf import BASE_DIR
from app.core.logger import log

from .config import CenterConfig, ColumnSpec, DerivedSpec, SheetSpec
from .csv_reader import CsvReader
from .excel_reader import ExcelReader, SheetView, build_column_map, normalize_header
from .transforms import TRANSFORMS, cast_expr_for_type

# 仅 Python 能做的 transform (涉及正则/JSON 解析)。
# 提前定义, 供 _build_select_for_sheet 引用 (Issue #2: 原来定义在使用之后)
_PYTHON_ONLY_TRANSFORMS = {"normalize_newlines", "json_load"}

# 与 etl_engine.py 一致
_SRC_TABLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


# ---------------- 路径安全 ----------------

def _safe_target_path(out_dir: Path, target_table: str) -> Path:
    """生成 out_dir/<target_table>.parquet, 校验白名单与路径不越界。"""
    if not _SRC_TABLE_RE.match(target_table):
        raise ValueError(f"非法 target_table: {target_table!r}")
    p = (out_dir / f"{target_table}.parquet").resolve()
    out_dir_resolved = out_dir.resolve()
    if p.parent != out_dir_resolved:
        raise ValueError(f"输出路径越界: {p} (out_dir={out_dir_resolved})")
    return p


def _resolve_out_dir(out_dir: str | Path) -> Path:
    """相对路径 → 相对仓库根 (BASE_DIR.parent); 绝对路径直接用。"""
    p = Path(out_dir)
    if not p.is_absolute():
        # BASE_DIR = backend/, BASE_DIR.parent = 仓库根 lnrs/
        p = BASE_DIR.parent / p
    return p.resolve()


# ---------------- SQL 标识符转义 ----------------

def _quote_ident(name: str) -> str:
    """duckdb 标识符转义: 双引号包裹, 内部双引号 doubled。

    用于引用 Excel 表头全路径如 '非隐私信息.患者基本信息.患者编号'。
    """
    return '"' + name.replace('"', '""') + '"'


# ---------------- 列处理: SQL 层 cast ----------------

def _build_select_for_sheet(
    sv: SheetView,
    spec: SheetSpec,
    extra_constants: dict[str, Any] | None = None,
) -> tuple[dict[str, str], list[str], list[str]]:
    """为单 sheet 构造列表达式映射, 返回 (tgt_to_expr, missing_required, present_tgts)。

    2026-07-19 代码评审修复 (Issue #1/#5):
    - 不再调 reader.read_sheet(...) 读表头, 改为接受 SheetView (调用方一次 read_sheet 拿全)
    - 避免每张 sheet 被 read_xlsx 读 2 次 (200MB × 26 sheet 浪费巨大)

    2026-07-19 代码评审修复 (Issue #3):
    - 返回 dict[tgt, expr] 而非已拼接的 SQL 字符串,
      让调用方直接知道每列的表达式, 不再需要 _parse_select_body 反向解析

    逻辑:
    1. 用 SheetView.headers 做 build_column_map 找 Excel 实际列名
    2. 对 spec.columns 生成 {tgt: cast_expr} 映射
    3. 若 required 且找不到 → 加入 missing_required
    4. extra_constants 注入到 tgt_to_expr

    返回的 expr 不含 "AS tgt" 后缀 (调用方拼时自己加)。
    """
    # 列匹配 (用 sv.headers, 不再 read_xlsx)
    src_to_excel = build_column_map(
        excel_headers=sv.headers,
        wanted_src=[c.src for c in spec.columns],
    )

    tgt_to_expr: dict[str, str] = {}
    present_tgts: list[str] = []
    missing_required: list[str] = []

    for col in spec.columns:
        if col.src in src_to_excel:
            excel_col = src_to_excel[col.src]
            ref = _quote_ident(excel_col)

            # 若有 Python-only transform (如 normalize_newlines), 用 UDF;
            # 否则用 SQL cast
            if col.transform and col.transform in _PYTHON_ONLY_TRANSFORMS:
                udf_name = f"py_{col.transform}"
                casted = f"{udf_name}({ref})"
                if col.type not in ("string", "text", "json"):
                    casted = cast_expr_for_type(f"({casted})", col.type)
            else:
                casted = cast_expr_for_type(ref, col.type)

            tgt_to_expr[col.tgt] = casted
            present_tgts.append(col.tgt)
        else:
            if col.required:
                missing_required.append(col.src)
                continue   # 不加入 tgt_to_expr, 让上层报错
            # 缺失非必需列: 注入 NULL 或 default
            null_expr = {
                "string": "CAST(NULL AS VARCHAR)",
                "text": "CAST(NULL AS VARCHAR)",
                "date": "CAST(NULL AS DATE)",
                "timestamp": "CAST(NULL AS TIMESTAMP)",
                "int": "CAST(NULL AS BIGINT)",
                "decimal": "CAST(NULL AS DECIMAL(18,3))",
                "bool": "CAST(NULL AS BOOLEAN)",
                "json": "CAST(NULL AS JSON)",
            }.get(col.type, "NULL")
            if col.default is not None:
                tgt_to_expr[col.tgt] = _sql_literal(col.default, col.type)
            else:
                tgt_to_expr[col.tgt] = null_expr
            present_tgts.append(col.tgt)

    # 注入 constants
    if extra_constants:
        for k, v in extra_constants.items():
            tgt_to_expr[k] = _sql_literal(v, "string")
            present_tgts.append(k)

    return tgt_to_expr, missing_required, present_tgts


def _sql_literal(value: Any, target_type: str) -> str:
    """把 Python 值转为 SQL 字面量。"""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float, Decimal)):
        return str(value)
    # 字符串 (含中文): 单引号包裹, 内部单引号 doubled
    s = str(value).replace("'", "''")
    return f"'{s}'"


# ---------------- UDF 注册 ----------------

def _register_python_udfs(con) -> None:
    """把 normalize_newlines / json_load 等注册为 duckdb Python UDF。

    duckdb 1.5 create_function 无法从 Any 返回类型自动推导, 必须显式声明。
    """
    # 每个 transform 的返回类型 (字符串映射到 duckdb SQL 类型名)
    return_types = {
        "normalize_newlines": "VARCHAR",   # str → str
        "json_load":         "JSON",       # str → dict/list → JSON
    }
    for name in _PYTHON_ONLY_TRANSFORMS:
        fn = TRANSFORMS[name]
        try:
            con.create_function(
                f"py_{name}",
                fn,
                return_type=return_types.get(name, "VARCHAR"),
            )
        except Exception as e:
            # 已注册时忽略 (con 复用场景)
            if "already exists" not in str(e).lower():
                log.warning("ETL1: 注册 UDF {} 失败: {}", name, e)


# ---------------- 单 sheet 主流程 ----------------

def _process_single_sheet(
    reader: "ExcelReader | CsvReader",
    con,
    spec: SheetSpec,
    out_path: Path,
    extra_constants: dict[str, Any] | None = None,
) -> int:
    """读单 sheet → SQL cast → COPY to parquet。返回写入行数。

    2026-07-19 代码评审修复 (Issue #1):
    - 只调一次 reader.read_sheet, 拿到 SheetView (view 名 + 表头)
    - 复用 view 名到 COPY SELECT, 不再重复建 view
    """
    log.info("ETL1: 处理 sheet {!r} → {}", spec.sheet_name, out_path.name)

    # 一次 read_sheet 拿 view + 表头
    sv = reader.read_sheet(spec.sheet_name)
    tgt_to_expr, missing, _ = _build_select_for_sheet(sv, spec, extra_constants)
    if missing:
        raise ValueError(
            f"sheet {spec.sheet_name!r} 缺少 required 列: {missing}; "
            f"实际表头示例: {sv.headers[:5]}"
        )

    # dedup 处理: 单列用 SELECT DISTINCT; 多列也用 SELECT DISTINCT (整行去重)
    select_kw = "SELECT DISTINCT" if spec.dedup_key else "SELECT"

    # 拼接 SELECT 列: '<expr> AS "<tgt>"'
    select_cols = ", ".join(
        f"{expr} AS {_quote_ident(tgt)}" for tgt, expr in tgt_to_expr.items()
    )

    # 可选 WHERE 子句 (ETL-1 配置文件常量, 已通过 _validate_where 校验)
    where_clause = f"WHERE {spec.where}" if spec.where else ""

    sql = f"""
        COPY (
            {select_kw}
                {select_cols}
            FROM {sv.view_name}
            {where_clause}
        ) TO '{out_path.as_posix().replace(chr(39), chr(39)+chr(39))}'
        (FORMAT PARQUET, OVERWRITE_OR_IGNORE)
    """
    log.debug("ETL1: SQL: {}", sql[:200])
    con.execute(sql)

    # 读回行数
    cnt = con.execute(
        "SELECT count(*) FROM read_parquet(?)", [out_path.as_posix()]
    ).fetchone()[0]
    log.info("ETL1: {} → {} 行 (parquet {} KB)",
             out_path.name, cnt, out_path.stat().st_size // 1024)
    return cnt


def _process_union_sheets(
    reader: "ExcelReader | CsvReader",
    con,
    spec_list: list[SheetSpec],
    out_path: Path,
) -> int:
    """多 SheetSpec 合并到同一 target_table (UNION ALL + 跨源 dedup)。

    2026-07-19 新增 (xinqiao 多子目录同表合并需求):
    - 每个 spec 各自 read_sheet + SQL cast 成统一列集
    - UNION ALL 外层 SELECT DISTINCT (用全部列去重, 等价于 dedup_key 全列 dedup)
    - 要求: 各 spec 的列集 (tgt) 必须完全一致; 不一致抛 ValueError

    2026-07-19 review fix (HIGH 1 + HIGH 2):
    - 校验改为列顺序也需一致 (UNION ALL 按位置对齐)
    - 跨源 dedup 改为按 dedup_key (而非全列), 避免长文本微小差异导致同 exam_id 漏去重

    返回: 写入行数
    """
    target_table = spec_list[0].target_table
    log.info("ETL1: UNION 处理 {} 个 sheet → {}",
             len(spec_list), out_path.name)

    # 校验所有 spec 的列集 + 列顺序一致 (UNION ALL 按位置对齐)
    first_order = [c.tgt for c in spec_list[0].columns]
    first_cols_set = set(first_order)
    for spec in spec_list[1:]:
        cur_order = [c.tgt for c in spec.columns]
        cur_cols_set = set(cur_order)
        if cur_order != first_order or cur_cols_set != first_cols_set:
            only_first = first_cols_set - cur_cols_set
            only_cur = cur_cols_set - first_cols_set
            raise ValueError(
                f"target_table={target_table!r} 的 SheetSpec 列集或列顺序不一致:\n"
                f"  {spec_list[0].sheet_name}: {first_order}\n"
                f"  {spec.sheet_name}: {cur_order}\n"
                f"  差集 (只在第一份): {sorted(only_first)}\n"
                f"  差集 (只在当前):  {sorted(only_cur)}"
            )

    # 跨源 dedup_key: 取各 spec dedup_key 的并集; 若任一 spec 没设, 退化为全列去重
    cross_dedup_keys: list[str] = []
    for spec in spec_list:
        for k in spec.dedup_key:
            if k not in cross_dedup_keys:
                cross_dedup_keys.append(k)
    # dedup_key 必须出现在列集里
    cross_dedup_keys = [k for k in cross_dedup_keys if k in first_cols_set]

    # 拼接每个 spec 的 SELECT 子查询
    sub_queries = []
    for spec in spec_list:
        sv = reader.read_sheet(spec.sheet_name)
        tgt_to_expr, missing, _ = _build_select_for_sheet(sv, spec)
        if missing:
            raise ValueError(
                f"sheet {spec.sheet_name!r} 缺少 required 列: {missing}"
            )
        # 各 spec 内 SELECT DISTINCT (行内去重)
        select_kw = "SELECT DISTINCT" if spec.dedup_key else "SELECT"
        select_cols = ", ".join(
            f"{expr} AS {_quote_ident(tgt)}" for tgt, expr in tgt_to_expr.items()
        )
        where_clause = f"WHERE {spec.where}" if spec.where else ""
        sub = f"""
            {select_kw}
                {select_cols}
            FROM {sv.view_name}
            {where_clause}
        """
        sub_queries.append(sub)

    union_sql = "\n            UNION ALL\n            ".join(sub_queries)

    # 跨源 dedup: 按 dedup_key (若有) 或全列 (退化)
    if cross_dedup_keys:
        keys_quoted = ", ".join(_quote_ident(k) for k in cross_dedup_keys)
        # 用 ROW_NUMBER() 保留每组 dedup_key 的第一行
        # (DuckDB 支持 QUALIFY 子句, 比 DISTINCT ON 更标准)
        outer_select = f"""
            SELECT * FROM (
                {union_sql}
            ) QUALIFY ROW_NUMBER() OVER (PARTITION BY {keys_quoted}) = 1
        """
    else:
        outer_select = f"""
            SELECT DISTINCT * FROM (
                {union_sql}
            ) AS _u
        """

    sql = f"""
        COPY (
            {outer_select}
        ) TO '{out_path.as_posix().replace(chr(39), chr(39)+chr(39))}'
        (FORMAT PARQUET, OVERWRITE_OR_IGNORE)
    """
    log.debug("ETL1: UNION SQL (first 300 chars): {}", sql[:300])
    con.execute(sql)

    cnt = con.execute(
        "SELECT count(*) FROM read_parquet(?)", [out_path.as_posix()]
    ).fetchone()[0]
    log.info("ETL1: {} → {} 行 (UNION of {} sheets, dedup_keys={}, parquet {} KB)",
             out_path.name, cnt, len(spec_list),
             cross_dedup_keys or "(全列)", out_path.stat().st_size // 1024)
    return cnt


# ---------------- Derived (多 sheet 合并) ----------------

def _process_derived(
    reader: ExcelReader,
    con,
    spec: DerivedSpec,
    out_dir: Path,
) -> int:
    """处理跨 sheet 合并的表。每个 source 各产出一部分, UNION ALL 后写 parquet。

    约束: 各 source 的列集必须相同 (core 自动用 NULL 补齐缺失列)。

    2026-07-19 代码评审修复 (Issue #1/#3/#5):
    - 每个 source 只 read_sheet 一次, 复用 view 名 (原来读 2 次)
    - 直接用 _build_select_for_sheet 返回的 dict[tgt, expr], 不再反向 SQL parse
    """
    log.info("ETL1: 处理 derived 表 {} ({} 个 source)", spec.target_table, len(spec.sources))

    # 每个 source: read_sheet 一次 + build_select 一次 (拿 dict)
    source_plans: list[tuple[SheetView, dict[str, str]]] = []
    all_tgts: list[str] = []
    for src in spec.sources:
        sv = reader.read_sheet(src.spec.sheet_name)
        tgt_to_expr, missing, present = _build_select_for_sheet(sv, src.spec, src.constants)
        if missing:
            raise ValueError(
                f"derived source sheet {src.spec.sheet_name!r} 缺少 required 列: {missing}"
            )
        source_plans.append((sv, tgt_to_expr))
        for t in present:
            if t not in all_tgts:
                all_tgts.append(t)

    # 每个 source 各做一个 SELECT (补齐缺失列为 NULL), 然后 UNION ALL
    # source 自身的 WHERE (DerivedSource.where) 应用于各自 SELECT 内;
    # DerivedSpec.where 在 UNION 外层再包一层
    #
    # ⚠️ 性能注意 (Review M5):
    # DerivedSpec.where **不会下推**, 会先物化整个 UNION ALL 再过滤;
    # 大数据量下建议尽量用 DerivedSource.where (单 source 内推) 而不是
    # DerivedSpec.where (合并后外推)。
    select_sqls: list[str] = []
    for (sv, tgt_to_expr), src in zip(source_plans, spec.sources):
        parts: list[str] = []
        for t in all_tgts:
            expr = tgt_to_expr.get(t, "NULL")
            parts.append(f"{expr} AS {_quote_ident(t)}")
        src_where = f"WHERE {src.where}" if src.where else ""
        select_sqls.append(
            f"SELECT {', '.join(parts)} FROM {sv.view_name} {src_where}"
        )

    union_body = "\n    UNION ALL\n    ".join(select_sqls)
    if spec.where:
        # 外层 WHERE 不会下推, 配置者应优先用 DerivedSource.where
        union_body = f"SELECT * FROM ({union_body}) WHERE {spec.where}"

    # dedup (整个 UNION 后)
    if spec.dedup_key:
        keys = ", ".join(_quote_ident(k) for k in spec.dedup_key)
        union_body = f"SELECT DISTINCT ON ({keys}) * FROM ({union_body})"

    out_path = _safe_target_path(out_dir, spec.target_table)
    sql = f"""
        COPY ({union_body})
        TO '{out_path.as_posix().replace(chr(39), chr(39)+chr(39))}'
        (FORMAT PARQUET, OVERWRITE_OR_IGNORE)
    """
    con.execute(sql)
    cnt = con.execute(
        "SELECT count(*) FROM read_parquet(?)", [out_path.as_posix()]
    ).fetchone()[0]
    log.info("ETL1: {} → {} 行 (derived)", out_path.name, cnt)
    return cnt


# ---------------- 主入口 ----------------

ProgressCb = Callable[[str, int, int], Any]   # (current_table, done, total)


def run_etl1(
    center: CenterConfig,
    xlsx_path: str | Path,
    out_dir: str | Path | None = None,
    on_table_done: Callable[[str, int], Any] | None = None,
    dry_run: bool = False,
    only_tables: list[str] | None = None,
) -> dict[str, int]:
    """ETL-1 主入口。

    ⚠️ 参数名兼容性: 第一参数 `xlsx_path` 为历史遗留命名 (xlsx 时代)。
    自 source_kind='csv' 引入后, 实际语义已扩展为"源数据路径":
        - source_kind='xlsx' 时: Excel 文件路径 (shengyi / zhujiang)
        - source_kind='csv' 时:  CSV 目录路径 (xinqiao), 内含 .csv 文件
    caller (service.py / __main__.py) 仍以 `xlsx_path` 命名调用, 保持向后兼容;
    后续 service.py 也支持 CSV 时, 可考虑统一改名为 data_path。

    参数:
        center: CenterConfig (从 get_center_config(code) 取)
        xlsx_path: 源数据路径 (见上方兼容性说明)
        out_dir: 输出目录 (None 则用 center.output_dir)
        on_table_done: 每张表完成回调 (table_name, row_count)
        dry_run: True 时只解析不写文件 (校验配置用)
        only_tables: 只处理这些 target_table (开发期增量调试)

    返回: {target_table: row_count}
    """
    resolved_out = _resolve_out_dir(out_dir or center.output_dir)
    resolved_out.mkdir(parents=True, exist_ok=True)
    log.info("ETL1: 启动 center={} source_kind={} out={} dry_run={}",
             center.code, center.source_kind, resolved_out, dry_run)

    # 工厂: 按 center.source_kind 选择 reader (2026-07-19 新增 CSV 分支)
    if center.source_kind == "xlsx":
        reader = ExcelReader(xlsx_path)
    elif center.source_kind == "csv":
        reader = CsvReader(xlsx_path)
    else:
        raise ValueError(
            f"不支持的 source_kind: {center.source_kind!r} (center={center.code})"
        )
    reader.ensure_loaded()
    con = reader.con
    _register_python_udfs(con)

    stats: dict[str, int] = {}

    def _want(t: str) -> bool:
        return only_tables is None or t in only_tables

    try:
        # 阶段 1: 单 sheet 直接转换
        # 2026-07-19 重构 (xinqiao 多源同表合并需求):
        #   同一 target_table 的多个 SheetSpec 用 UNION ALL 合并到一次 COPY,
        #   而不是顺序覆盖写 (后者会丢前批数据)
        # 收集所有 single_spec, 按 target_table 分组
        single_specs = list(center.universal_tables) + list(center.hospital_tables)
        wanted_specs = [s for s in single_specs if _want(s.target_table)]

        # 按 target_table 分组 (保留顺序, 便于 dry_run 输出)
        grouped: "OrderedDict[str, list[SheetSpec]]" = OrderedDict()
        for spec in wanted_specs:
            grouped.setdefault(spec.target_table, []).append(spec)

        for target_table, spec_list in grouped.items():
            out_path = _safe_target_path(resolved_out, target_table)
            if dry_run:
                # 校验所有 spec 的列
                for spec in spec_list:
                    sv = reader.read_sheet(spec.sheet_name)
                    _, missing, _ = _build_select_for_sheet(sv, spec)
                    if missing:
                        raise ValueError(f"{target_table}: 缺列 {missing}")
                stats[target_table] = -1
                continue
            if len(spec_list) == 1:
                n = _process_single_sheet(reader, con, spec_list[0], out_path)
            else:
                n = _process_union_sheets(reader, con, spec_list, out_path)
            stats[target_table] = n
            if on_table_done:
                on_table_done(target_table, n)

        # 阶段 2: 跨 sheet 合并
        for spec in center.derived_tables:
            if not _want(spec.target_table):
                continue
            if dry_run:
                # 校验所有 source 缺列
                for src in spec.sources:
                    sv = reader.read_sheet(src.spec.sheet_name)
                    _, missing, _ = _build_select_for_sheet(sv, src.spec, src.constants)
                    if missing:
                        raise ValueError(
                            f"{spec.target_table} source {src.spec.sheet_name}: 缺列 {missing}"
                        )
                stats[spec.target_table] = -1
                continue
            n = _process_derived(reader, con, spec, resolved_out)
            stats[spec.target_table] = n
            if on_table_done:
                on_table_done(spec.target_table, n)

        # 阶段 3: visit_id 反查
        from .visit_resolver import resolve_visits
        resolve_visits(con, resolved_out, center, only_tables)

        # 阶段 4: manifest
        from .manifest import write_manifest
        write_manifest(center, Path(xlsx_path), resolved_out, stats)

        log.info("ETL1: 完成 center={} 共 {} 张表, 总行数 {}",
                 center.code, len(stats), sum(v for v in stats.values() if v > 0))
    finally:
        reader.close()

    return stats
