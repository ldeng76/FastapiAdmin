from __future__ import annotations

from typing import Any

from app.core.logger import log

_SEX_MAP_CACHE: dict[str, str] = {}
_ETHNICITY_MAP_CACHE: dict[str, str] = {}
_SMOKING_MAP_CACHE: dict[str, str] = {}
_ABO_MAP_CACHE: dict[str, str] = {}
_RH_MAP_CACHE: dict[str, str] = {}

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


def _normalize_cached(raw: Any, cache: dict[str, str], empty: str | None = None) -> str | None:
    if raw is None or not str(raw).strip():
        return empty
    return cache.get(str(raw).strip().lower(), empty)


def normalize_sex(raw: Any) -> str:
    return _normalize_cached(raw, _SEX_MAP_CACHE or {}, "0") or "0"


def normalize_ethnicity(raw: Any) -> str | None:
    return _normalize_cached(raw, _ETHNICITY_MAP_CACHE)


def normalize_smoking_status(raw: Any) -> str | None:
    return _normalize_cached(raw, _SMOKING_MAP_CACHE)


def normalize_abo_blood_type(raw: Any) -> str | None:
    return _normalize_cached(raw, _ABO_MAP_CACHE)


def normalize_rh_blood_type(raw: Any) -> str | None:
    return _normalize_cached(raw, _RH_MAP_CACHE)
