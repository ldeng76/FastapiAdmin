"""医疗枚举字段归一化（字典驱动）。

设计要点：
- 5 个枚举字段（sex/ethnicity/smoking_status/abo/rh）的归一化全部走 med_dict_mapping
  字典映射表，无硬编码 fallback。
- 未命中映射时：
  - sex            → '0'（未知）+ 标记 unmatched
  - ethnicity      → None（不写）+ 标记 unmatched
  - smoking_status → '9'（未知）+ 标记 unmatched
  - abo            → '6'（未查）+ 标记 unmatched
  - rh             → '4'（未查）+ 标记 unmatched
- _with_status 版本返回 (value, hit) tuple，hit=False 用于上层写入 med_dict_unmatched 表。
- 空值（None/空串）不算未命中——视为合法缺失，hit=True 但 value=字段默认。
"""
from __future__ import annotations

from typing import Any

from app.core.logger import log

_SEX_MAP_CACHE: dict[str, str] = {}
_ETHNICITY_MAP_CACHE: dict[str, str] = {}
_SMOKING_MAP_CACHE: dict[str, str] = {}
_ABO_MAP_CACHE: dict[str, str] = {}
_RH_MAP_CACHE: dict[str, str] = {}

# 每个枚举字段的默认值（空值或未命中时返回）
_DEFAULTS = {
    "sex": "0",           # 未知
    "ethnicity": None,    # 不写
    "smoking_status": "9",  # 未知
    "abo_blood_type": "6",  # 未查（注意：不是 5=不详）
    "rh_blood_type": "4",   # 未查
}

ENUM_DICT_TYPES = (
    "med_sex", "med_ethnicity", "med_smoking_status",
    "med_blood_type_abo", "med_blood_type_rh",
)


async def load_sex_mapping(db: Any, hospital_id: int | None = None) -> None:
    """批量预热性别映射。"""
    global _SEX_MAP_CACHE
    from app.plugin.module_medical.dict_mapping.service import DictMappingService
    _SEX_MAP_CACHE = await DictMappingService.load_all_mappings(db, "med_sex", hospital_id)


async def _load_enum_mapping(db: Any, dict_type: str, hospital_id: int | None) -> dict[str, str]:
    from app.plugin.module_medical.dict_mapping.service import DictMappingService
    try:
        return await DictMappingService.load_all_mappings(db, dict_type, hospital_id)
    except Exception as exc:
        log.error("ETL2: %s 映射加载失败: %s", dict_type, exc)
        return {}


async def load_ethnicity_mapping(db: Any, hospital_id: int | None = None) -> None:
    global _ETHNICITY_MAP_CACHE
    _ETHNICITY_MAP_CACHE = await _load_enum_mapping(db, "med_ethnicity", hospital_id)


async def load_smoking_status_mapping(db: Any, hospital_id: int | None = None) -> None:
    global _SMOKING_MAP_CACHE
    _SMOKING_MAP_CACHE = await _load_enum_mapping(db, "med_smoking_status", hospital_id)


async def load_abo_blood_type_mapping(db: Any, hospital_id: int | None = None) -> None:
    global _ABO_MAP_CACHE
    _ABO_MAP_CACHE = await _load_enum_mapping(db, "med_blood_type_abo", hospital_id)


async def load_rh_blood_type_mapping(db: Any, hospital_id: int | None = None) -> None:
    global _RH_MAP_CACHE
    _RH_MAP_CACHE = await _load_enum_mapping(db, "med_blood_type_rh", hospital_id)


async def load_all_enum_mappings(db: Any, hospital_id: int | None = None) -> None:
    await load_sex_mapping(db, hospital_id)
    await load_ethnicity_mapping(db, hospital_id)
    await load_smoking_status_mapping(db, hospital_id)
    await load_abo_blood_type_mapping(db, hospital_id)
    await load_rh_blood_type_mapping(db, hospital_id)


def _is_empty(raw: Any) -> bool:
    """空值判定：None 或纯空白字符串视为缺失。"""
    return raw is None or not str(raw).strip()


def _normalize_cached(raw: Any, cache: dict[str, str], default: str | None) -> str | None:
    """归一化：命中返回 dict_value；空值或未命中返回 default。

    与旧版语义一致（保持向后兼容）：
    - 空 raw → default（合法缺失，不算未命中）
    - 未命中 → default（与空值不可区分，故 _with_status 版本用于结构化区分）
    """
    if _is_empty(raw):
        return default
    return cache.get(str(raw).strip().lower(), default)


def _normalize_cached_with_status(
    raw: Any, cache: dict[str, str], default: str | None
) -> tuple[str | None, bool]:
    """带状态归一化，返回 (value, hit)。

    - 空 raw    → (default, True)   合法缺失，hit=True（不算未匹配）
    - 命中映射  → (dict_value, True)
    - 未命中    → (default, False)  hit=False，上层应写 med_dict_unmatched
    """
    if _is_empty(raw):
        return default, True
    key = str(raw).strip().lower()
    if key in cache:
        return cache[key], True
    return default, False


# --------------------------------------------------------------------------- #
# 旧版接口（保持兼容；无 hit 信号）
# --------------------------------------------------------------------------- #


def normalize_sex(raw: Any) -> str:
    return _normalize_cached(raw, _SEX_MAP_CACHE or {}, _DEFAULTS["sex"]) or _DEFAULTS["sex"]


def normalize_ethnicity(raw: Any) -> str | None:
    return _normalize_cached(raw, _ETHNICITY_MAP_CACHE, _DEFAULTS["ethnicity"])


def normalize_smoking_status(raw: Any) -> str | None:
    return _normalize_cached(raw, _SMOKING_MAP_CACHE, _DEFAULTS["smoking_status"])


def normalize_abo_blood_type(raw: Any) -> str | None:
    return _normalize_cached(raw, _ABO_MAP_CACHE, _DEFAULTS["abo_blood_type"])


def normalize_rh_blood_type(raw: Any) -> str | None:
    return _normalize_cached(raw, _RH_MAP_CACHE, _DEFAULTS["rh_blood_type"])


# --------------------------------------------------------------------------- #
# 新版接口（_with_status，返回 (value, hit)；ETL 用 hit=False 攒未匹配）
# --------------------------------------------------------------------------- #


def normalize_sex_with_status(raw: Any) -> tuple[str, bool]:
    v, hit = _normalize_cached_with_status(raw, _SEX_MAP_CACHE or {}, _DEFAULTS["sex"])
    return v or _DEFAULTS["sex"], hit


def normalize_ethnicity_with_status(raw: Any) -> tuple[str | None, bool]:
    return _normalize_cached_with_status(raw, _ETHNICITY_MAP_CACHE, _DEFAULTS["ethnicity"])


def normalize_smoking_status_with_status(raw: Any) -> tuple[str | None, bool]:
    return _normalize_cached_with_status(raw, _SMOKING_MAP_CACHE, _DEFAULTS["smoking_status"])


def normalize_abo_blood_type_with_status(raw: Any) -> tuple[str | None, bool]:
    return _normalize_cached_with_status(raw, _ABO_MAP_CACHE, _DEFAULTS["abo_blood_type"])


def normalize_rh_blood_type_with_status(raw: Any) -> tuple[str | None, bool]:
    return _normalize_cached_with_status(raw, _RH_MAP_CACHE, _DEFAULTS["rh_blood_type"])
