"""ETL-1: Excel/CSV → Parquet（多医院可扩展）。

与 ETL-2（etl_engine.py，Parquet → PostgreSQL）配套：

    医院原始 Excel/CSV  ──ETL-1─►  data/<center>/*.parquet  ──ETL-2─►  med_* (PG)

本子包职责：
1. 把医院原始 Excel（含中文全路径表头、inline string cell、父子表冗余）
   清洗为 snake_case 英文字段的 parquet 文件，按 unified_table_schema.md 落地。
2. 通过 per-center config 描述「sheet → 目标表 / 列重命名 / 类型转换 / 去重 / visit 反查」
   等规则，core 引擎不写死医院名。
3. 不做脱敏（PHI 处理在 ETL-2 之后的 0006-anonymized-schema-patch-visit 流水线）。

模块构成：
- config.py        配置 schema (pydantic) + CenterConfig 加载入口
- excel_reader.py  duckdb excel 扩展封装 (已验证 4 项可行性)
- transforms.py    注册式清洗函数 (日期/数值/文本规范化)
- visit_resolver.py  (patient_id, m) → visit_id 跨表反查
- manifest.py      生成 conversion_manifest.json (仿 zhujiang_xinqiao_parq/_meta/)
- core.py          主循环: 单 sheet + 跨表合并 + visit 反查 + manifest
- service.py       FastAPI 后台任务入口 (仿 etl_service.py)
- centers/         每个医院一份 Python 常量 config
"""

from __future__ import annotations

# 对外暴露的核心入口
from .config import (
    CenterConfig,
    ColumnSpec,
    DerivedSpec,
    SourceKind,
    SheetSpec,
    TargetType,
    get_center_config,
    list_centers,
)
from .core import run_etl1

__all__ = [
    "CenterConfig",
    "ColumnSpec",
    "DerivedSpec",
    "SourceKind",
    "SheetSpec",
    "TargetType",
    "get_center_config",
    "list_centers",
    "run_etl1",
]
