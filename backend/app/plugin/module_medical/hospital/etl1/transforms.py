"""注册式清洗函数 (单列 in → out)。

设计要点:
- ColumnSpec.transform 存函数 key (字符串), 不存表达式 (安全, 非 eval)
- 与 etl_engine.py 的 TRANSFORM_FUNCTIONS 风格一致
- 输入全是 str (因 read_xlsx all_varchar=true), 输出按 ColumnSpec.type 决定

类型 cast 的实现策略:
- date/timestamp/decimal/int 用 duckdb 内置 CAST/try_strptime (在 SQL 层做, 快)
- 文本规范化 (\r\n → \n) 用 Python (涉及正则, SQL 不便)
- 本文件提供 Python 版本, 用于 core.py 在 row-level 后处理时调用
- SQL 版本由 core.py 在生成 COPY SQL 时拼接 (见 _cast_expr_for_type)
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

# 单列清洗函数注册表 (key = ColumnSpec.transform)
TRANSFORMS: dict[str, Callable[[Any], Any]] = {
    "normalize_newlines": lambda v: re.sub(r"\r\n?", "\n", v) if isinstance(v, str) else v,
    "parse_date":         lambda v: _parse_date(v),
    "parse_timestamp":    lambda v: _parse_timestamp(v),
    "to_int":             lambda v: _to_int(v),
    "to_decimal":         lambda v: _to_decimal(v),
    "to_bool":            lambda v: _to_bool(v),
    "json_load":          lambda v: json.loads(v) if isinstance(v, str) and v else v,
}

# 空值哨兵 (Excel 里空 cell 或 'null' 字面量都视为 null)
_NULL_SENTINELS = {"", "null", "None", "NULL", "nan", "NaN"}


def apply_transform(key: str | None, value: Any) -> Any:
    """安全调用注册的转换函数。key=None 时直接返回原值。"""
    if key is None:
        return value
    fn = TRANSFORMS.get(key)
    if fn is None:
        raise ValueError(f"未注册的 transform: {key!r}; 已注册: {list(TRANSFORMS.keys())}")
    return fn(value)


def _is_null(v: Any) -> bool:
    return v is None or (isinstance(v, str) and v.strip() in _NULL_SENTINELS)


# ---------------- 具体转换函数 ----------------

_DATE_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})")
_TS_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})[ T](\d{1,2}):(\d{1,2})(?::(\d{1,2}))?")


def _parse_date(v: Any) -> Any:
    """从 'YYYY-MM-DD HH:MM:SS' / 'YYYY-MM-DD' / 其它文本中提取 date。

    返回 Python date 对象 (写入 parquet 时自动转 DATE)。无法解析返回 None。
    """
    if _is_null(v):
        return None
    s = str(v).strip()
    m = _DATE_RE.match(s)
    if not m:
        return None
    try:
        from datetime import date
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except (ValueError, IndexError):
        return None


def _parse_timestamp(v: Any) -> Any:
    """解析 'YYYY-MM-DD HH:MM:SS' / 'YYYY-MM-DD' (退化为 00:00:00) 为 datetime。"""
    if _is_null(v):
        return None
    s = str(v).strip()
    m = _TS_RE.match(s)
    if not m:
        # 退化: 仅日期
        d = _parse_date(s)
        if d is not None:
            from datetime import datetime
            return datetime(d.year, d.month, d.day)
        return None
    try:
        from datetime import datetime
        return datetime(
            int(m.group(1)), int(m.group(2)), int(m.group(3)),
            int(m.group(4)), int(m.group(5)),
            int(m.group(6)) if m.group(6) else 0,
        )
    except (ValueError, IndexError):
        return None


def _to_int(v: Any) -> Any:
    """转 int。空/'null'/无效 → None。支持 '84.0' 形式 (浮点字符串)。"""
    if _is_null(v):
        return None
    try:
        return int(float(str(v).strip()))
    except (ValueError, TypeError):
        return None


def _to_decimal(v: Any) -> Any:
    """转 Decimal。保留精度 (parquet 写入时转 NUMERIC)。"""
    if _is_null(v):
        return None
    try:
        return Decimal(str(v).strip())
    except (InvalidOperation, ValueError, TypeError):
        return None


def _to_bool(v: Any) -> Any:
    """'是'/'否'/'true'/'false' → bool。其它返回 None。"""
    if _is_null(v):
        return None
    s = str(v).strip().lower()
    return {"是": True, "true": True, "1": True, "y": True, "否": False, "false": False, "0": False, "n": False}.get(s)


# ---------------- SQL 表达式生成 (用于 duckdb COPY 时直接 cast) ----------------

def cast_expr_for_type(col_ref: str, target_type: str) -> str:
    """生成 SQL cast 表达式, 用于在 COPY SELECT 里直接做类型转换。

    比 Python 版快得多 (在 duckdb 向量化执行层做)。Python 版用于复杂清洗
    (如 normalize_newlines), 这里只做纯类型 cast。

    col_ref: 列引用, 必须是已转义的标识符, 如 '"非隐私信息.患者基本信息.出生日期"'
              或 'patient_id' (无特殊字符时不用引号)
    target_type: ColumnSpec.type 之一
    """
    if target_type == "string" or target_type == "text":
        # 强制 NULL → 空字符串? 不, 保留 NULL (parquet 支持 null)
        return f"CAST({col_ref} AS VARCHAR)"
    if target_type == "date":
        # try_strptime 失败返回 NULL; 支持多种格式
        return f"TRY_CAST({col_ref} AS DATE)"
    if target_type == "timestamp":
        return f"TRY_CAST({col_ref} AS TIMESTAMP)"
    if target_type == "int":
        # Excel 里数字常以 '84.0' 形式存, 先 float 再 int
        return f"TRY_CAST(TRY_CAST({col_ref} AS DOUBLE) AS BIGINT)"
    if target_type == "decimal":
        return f"TRY_CAST({col_ref} AS DECIMAL(18,3))"
    if target_type == "bool":
        # 不在 SQL 做 (中文 '是/否' SQL 表达式太繁琐), 留给 Python
        return col_ref
    if target_type == "json":
        # JSON 字符串直接 cast 到 JSON 类型
        return f"CAST({col_ref} AS JSON)"
    return col_ref
