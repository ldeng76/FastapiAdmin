"""ETL-1 列映射辅助函数 (共享给各 center config)。

Review M4: 此前 shengyi.py 和 zhujiang.py 各定义了 _str/_text/_date/_int/_dec/_ts,
代码重复; 后续中心扩展会无限复制。统一到本模块供所有 center 调用。

使用:
    from app.plugin.module_medical.hospital.etl1.column_specs import col_str, col_text

注意: 各 center 历史代码使用的 `_str/_text/_date` 是私有命名, 本模块统一用 `col_*`
前缀避免与可能的用户代码冲突; 各 center 可自行决定是否迁移到本模块。
"""

from __future__ import annotations

from .config import ColumnSpec


def col_str(src: str, tgt: str, *, required: bool = False) -> ColumnSpec:
    """string 列。"""
    return ColumnSpec(src=src, tgt=tgt, type="string", required=required)


def col_text(src: str, tgt: str) -> ColumnSpec:
    """text 列 (长文本, 经 normalize_newlines 清洗 \\r\\n → \\n)。"""
    return ColumnSpec(src=src, tgt=tgt, type="text", transform="normalize_newlines")


def col_date(src: str, tgt: str) -> ColumnSpec:
    """date 列。

    type="date" 由 core.cast_expr_for_type 走 TRY_CAST(... AS DATE) 处理;
    无需额外 transform (Review C1: parse_date 未注册为 Python UDF)。
    """
    return ColumnSpec(src=src, tgt=tgt, type="date")


def col_ts(src: str, tgt: str) -> ColumnSpec:
    """timestamp 列。"""
    return ColumnSpec(src=src, tgt=tgt, type="timestamp", transform="parse_timestamp")


def col_int(src: str, tgt: str) -> ColumnSpec:
    """int 列。"""
    return ColumnSpec(src=src, tgt=tgt, type="int", transform="to_int")


def col_dec(src: str, tgt: str) -> ColumnSpec:
    """decimal 列。"""
    return ColumnSpec(src=src, tgt=tgt, type="decimal", transform="to_decimal")