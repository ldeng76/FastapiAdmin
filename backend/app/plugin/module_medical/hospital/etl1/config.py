"""ETL-1 配置 schema + center 注册表。

设计思路：
- 用 pydantic 模型描述每个医院的「sheet → 目标表」全套规则。
- core 引擎只认 CenterConfig，不 import 任何医院特定代码。
- 新增医院只需在 centers/ 下加一份 Python 常量 + 在 _REGISTRY 注册。

与 ETL-2 (etl_engine.py) 的契约：
- target_table 必须是合法 Python 标识符 (^\\w+$)，因为 ETL-2 用它做 parquet 文件名
  且 _SRC_TABLE_RE 白名单只接受 [A-Za-z_][A-Za-z0-9_]*
- tgt 字段名建议用 snake_case 英文，与 med_* 表列名对齐
- 同一张目标表可以被多个 SheetSpec/DerivedSpec 写入 (UNION ALL)，但要保证列集相同
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 与 etl_engine.py:_SRC_TABLE_RE 完全一致
# ETL-1 产出的 parquet 文件名必须满足这个约束, 才能被 ETL-2 直接消费
_SRC_TABLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

SourceKind = Literal["xlsx", "csv"]
TargetType = Literal["string", "date", "timestamp", "int", "decimal", "bool", "text", "json"]


# ---------------- WHERE 子句安全校验 ----------------
# where 是 ETL-1 配置文件中的常量(非 HTTP 输入, trusted source);
# 但仍做基础防注入检查: 禁止分号/多语句/注释, 只允许出现 Excel 列名 + 常见 SQL token。
_FORBIDDEN_TOKEN_RE = re.compile(
    r"(--|;|/\*|\*/|\bunion\b|\bselect\b|\binsert\b|\bupdate\b|\bdelete\b|\bdrop\b|\balter\b|\bcreate\b|\bgrant\b|\brevoke\b|\bexec\b|\bexecute\b)",
    re.IGNORECASE,
)


def _validate_where(v: str | None, *, field: str) -> str | None:
    """校验 WHERE 子句: 仅配置文件可信来源使用; 禁止分号/注释/DDL/DML 多语句。

    返回清理后的字符串, 失败抛 ValueError。

    列引用规则 (2026-07-19 新增: 支持双引号包裹的中文/点号列名):
    - 简单标识符 (英文/数字/下划线): 直接写 EXAM_CLASS / IMPRESSION
    - 中文/点号/带空格的列名: 必须用双引号包裹, 如 "检查报告.检查类别"
    - 双引号内的内容不做 _FORBIDDEN_TOKEN_RE 校验 (因为只是列名)
    """
    if v is None:
        return None
    if not isinstance(v, str):
        raise ValueError(f"{field}: 必须是字符串, 收到 {type(v).__name__}")
    s = v.strip()
    if not s:
        return None
    if ";" in s:
        raise ValueError(f"{field}: 含 ';' (禁止多语句)")
    # 把所有双引号包裹的字符串块 (列名/字面量) 替换成占位符,
    # 这样 _FORBIDDEN_TOKEN_RE 不会误伤列名里的关键字 (如 'select' 出现在列名)
    # 占位符用不会被 _FORBIDDEN_TOKEN_RE 命中的 token
    PLACEHOLDER = "__QUOTED_LITERAL__"
    masked = re.sub(r'"[^"]*"', PLACEHOLDER, s)
    bad = _FORBIDDEN_TOKEN_RE.search(masked)
    if bad:
        raise ValueError(f"{field}: 含禁用 token {bad.group(0)!r}")
    return s


class ColumnSpec(BaseModel):
    """单列映射规则: Excel 表头 → parquet 列名 + 类型 + 可选清洗函数。"""

    model_config = ConfigDict(frozen=True)

    src: str = Field(
        ...,
        description="Excel 表头全路径, 如 '非隐私信息.就诊.病程记录文档.文档内容'。"
                    "匹配时 strip(), 因探索发现 sheet2 '医疗付款方式 ' 有尾随空格",
    )
    tgt: str = Field(
        ...,
        description="目标 parquet 列名, snake_case 英文, 如 'content' / 'patient_id'",
    )
    type: TargetType = Field(
        "string",
        description="parquet 列类型; all_varchar 读入后由 transforms.py 按此 cast",
    )
    required: bool = Field(
        False,
        description="若为 True, 该列在 Excel 表头找不到时整个 sheet 加载失败 (防止配置错)",
    )
    default: Any = Field(
        None,
        description="src 列缺失或值为空时的填充值; 仅在 required=False 时生效",
    )
    transform: str | None = Field(
        None,
        description="transforms.py 里注册的函数 key, 如 'normalize_newlines' / 'parse_date'",
    )

    @field_validator("tgt")
    @classmethod
    def _validate_tgt(cls, v: str) -> str:
        if not v or not v.replace("_", "").isalnum():
            raise ValueError(f"tgt 列名必须是合法标识符 (snake_case): {v!r}")
        return v


class SheetSpec(BaseModel):
    """单个 Excel sheet → 单张 parquet 的映射规则。

    单 sheet 直接转换; 多 sheet 合并请用 DerivedSpec。
    """

    model_config = ConfigDict(frozen=True)

    sheet_name: str = Field(
        ...,
        description="Excel 工作表名, 如 '非隐私信息.患者基本信息' (支持中文/点号)",
    )
    target_table: str = Field(
        ...,
        description="输出 parquet 文件名 (无扩展名), 如 'patient' → patient.parquet",
    )
    columns: list[ColumnSpec] = Field(
        ...,
        min_length=1,
        description="列映射; 未列出的 Excel 列将被丢弃",
    )
    dedup_key: list[str] | None = Field(
        None,
        description="去重键 (tgt 列名列表); None=不去重",
    )
    visit_recovery: bool = Field(
        False,
        description="True=本表缺少 visit_id, 需要 (patient_id, m) 反查 visit_record",
    )
    where: str | None = Field(
        None,
        description=(
            "可选 SQL WHERE 子句 (不含 WHERE 关键字本身), 用于行级过滤。"
            "仅 ETL-1 配置文件使用, 不接受 HTTP 输入; "
            "禁止分号/注释/DDL/DML 多语句 (见 _validate_where)。\n"
            "列引用规则:\n"
            "- 简单标识符 (英文/数字/下划线): 直接写 EXAM_CLASS / IMPRESSION\n"
            "- 中文/点号/带空格的列名: 必须用双引号包裹, 如 `\"检查报告.检查类别\"`\n"
            "- 双引号内的字符串内容不做禁用 token 校验 (列名仅作字面量)"
        ),
    )

    @field_validator("target_table")
    @classmethod
    def _validate_target(cls, v: str) -> str:
        if not _SRC_TABLE_RE.match(v):
            raise ValueError(
                f"target_table 必须满足 {_SRC_TABLE_RE.pattern} (与 ETL-2 _SRC_TABLE_RE 对齐): {v!r}"
            )
        return v

    @field_validator("where")
    @classmethod
    def _validate_where_field(cls, v: str | None) -> str | None:
        return _validate_where(v, field="where")


class DerivedSpec(BaseModel):
    """跨 sheet 合并/展平规则。

    用于以下场景:
    - diagnosis 合并 sheet4 (病案首页) + sheet6 (诊疗过程) → 单张 diagnosis.parquet
      靠 source_tag 区分
    - surgery_record 合并 sheet3 (病案首页) + sheet7 (手术信息)
    - anesthesia_event 合并 sheet8 (medication) + sheet9 (observation)

    合并后的输出表必须列集对齐 (用 NULL/默认值补齐缺失列)。
    """

    model_config = ConfigDict(frozen=True)

    target_table: str = Field(..., description="合并后的 parquet 文件名")
    sources: list["DerivedSource"] = Field(
        ..., min_length=1, description="各输入 sheet 及其额外注入的常量字段"
    )
    dedup_key: list[str] | None = Field(None, description="合并后整体去重键")
    visit_recovery: bool = Field(False, description="是否需要 visit_id 反查")
    where: str | None = Field(
        None,
        description="合并后整体 WHERE 子句 (UNION ALL 之后外层再过滤)",
    )

    @field_validator("target_table")
    @classmethod
    def _validate_target(cls, v: str) -> str:
        if not _SRC_TABLE_RE.match(v):
            raise ValueError(f"target_table 必须满足 {_SRC_TABLE_RE.pattern}: {v!r}")
        return v

    @field_validator("where")
    @classmethod
    def _validate_where_field(cls, v: str | None) -> str | None:
        return _validate_where(v, field="where")


class DerivedSource(BaseModel):
    """DerivedSpec 的一个输入源。"""

    model_config = ConfigDict(frozen=True)

    spec: SheetSpec = Field(..., description="输入 sheet 的标准 SheetSpec")
    constants: dict[str, Any] = Field(
        default_factory=dict,
        description="注入的常量列, 如 {'diagnosis_source': 'front_page'}",
    )
    where: str | None = Field(
        None,
        description="此 source 在 UNION 内的 WHERE 子句 (本 source 单独过滤)",
    )

    @field_validator("where")
    @classmethod
    def _validate_where_field(cls, v: str | None) -> str | None:
        return _validate_where(v, field="where")


class CenterConfig(BaseModel):
    """单个医院的完整 ETL-1 配置。"""

    model_config = ConfigDict(frozen=True)

    code: str = Field(..., description="医院代号, 如 'shengyi' (用于目录名与日志)")
    display_name: str = Field(..., description="医院显示名, 如 '广东省人民医院'")
    source_kind: SourceKind = Field(..., description="源数据类型")
    universal_tables: list[SheetSpec] = Field(
        default_factory=list,
        description="4 张跨院统一表 (patient/pathology_specimen/surgery_record/genetic_test); "
                    "若该院用 DerivedSpec 合并产生 (如 surgery_record), 则此处留空",
    )
    hospital_tables: list[SheetSpec] = Field(
        default_factory=list,
        description="该院独有表 (单 sheet 直接转换)",
    )
    derived_tables: list[DerivedSpec] = Field(
        default_factory=list,
        description="跨 sheet 合并产生的表 (含 surgery/diagnosis/anesthesia)",
    )
    output_dir_template: str = Field(
        "data/{code}",
        description="输出目录模板, 相对仓库根; {code} 用 center.code 替换",
    )
    csv_encoding: str | dict[str, str] | None = Field(
        None,
        description=(
            "CSV 文件编码, 仅 source_kind='csv' 时生效。"
            "None=DuckDB 自动检测 (UTF-8 兼容); "
            "str=所有 sheet 统一编码 (如 'gb18030' 用于 GBK 中文 CSV); "
            "dict=按 sheet_name 单独指定, "
            "  用于一个 center 的多个 sheet 编码不一致场景 "
            "  (如新桥: SUB1=gb18030, SUB2=UTF-8)。"
            "若不设, GBK 中文表头会被当乱码导致 DuckDB 回退到 columnNN 占位列名。"
        ),
    )

    @field_validator("code")
    @classmethod
    def _validate_code(cls, v: str) -> str:
        if not _SRC_TABLE_RE.match(v):
            raise ValueError(f"code 必须满足 {_SRC_TABLE_RE.pattern}: {v!r}")
        return v

    @property
    def output_dir(self) -> Path:
        """相对仓库根的输出目录。"""
        return Path(self.output_dir_template.format(code=self.code))

    def all_target_tables(self) -> list[str]:
        """所有目标表名 (universal + hospital + derived), 去重保序。"""
        seen: list[str] = []
        for spec in self.universal_tables + self.hospital_tables:
            if spec.target_table not in seen:
                seen.append(spec.target_table)
        for d in self.derived_tables:
            if d.target_table not in seen:
                seen.append(d.target_table)
        return seen


# ---------------- Center 注册表 ----------------

_REGISTRY: dict[str, CenterConfig] = {}


def register_center(cfg: CenterConfig) -> None:
    """注册一份 center config。重复注册覆盖 (便于热加载)。"""
    _REGISTRY[cfg.code] = cfg


def get_center_config(code: str) -> CenterConfig:
    """按 code 取 center config。未注册抛 KeyError。"""
    # 触发 centers 包的默认注册
    from . import centers as _centers  # noqa: F401
    if code not in _REGISTRY:
        raise KeyError(
            f"未知 center code: {code!r}; 已注册: {list(_REGISTRY.keys())}"
        )
    return _REGISTRY[code]


def list_centers() -> list[str]:
    """列出所有已注册的 center code。"""
    from . import centers as _centers  # noqa: F401
    return sorted(_REGISTRY.keys())
