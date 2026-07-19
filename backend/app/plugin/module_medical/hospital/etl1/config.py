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

    @field_validator("target_table")
    @classmethod
    def _validate_target(cls, v: str) -> str:
        if not _SRC_TABLE_RE.match(v):
            raise ValueError(
                f"target_table 必须满足 {_SRC_TABLE_RE.pattern} (与 ETL-2 _SRC_TABLE_RE 对齐): {v!r}"
            )
        return v


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

    @field_validator("target_table")
    @classmethod
    def _validate_target(cls, v: str) -> str:
        if not _SRC_TABLE_RE.match(v):
            raise ValueError(f"target_table 必须满足 {_SRC_TABLE_RE.pattern}: {v!r}")
        return v


class DerivedSource(BaseModel):
    """DerivedSpec 的一个输入源。"""

    model_config = ConfigDict(frozen=True)

    spec: SheetSpec = Field(..., description="输入 sheet 的标准 SheetSpec")
    constants: dict[str, Any] = Field(
        default_factory=dict,
        description="注入的常量列, 如 {'diagnosis_source': 'front_page'}",
    )


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
