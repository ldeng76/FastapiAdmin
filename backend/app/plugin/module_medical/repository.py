"""医学数据访问层（DuckDB 直读 parquet，不入库）。

设计要点：
- DuckDB 以内存模式连接，所有查询经 read_parquet 读真实样本数据目录。
- 真实数据为珠江-新桥单中心扁平布局（`docs/zhujiang_xinqiao_parq/*.parquet`）；
  `_read_parquet` 自动适配扁平单文件与「按中心子目录」的多中心布局（glob + union_by_name）。
- 复合类型（JSON 串/struct/list/date/Decimal）由 _normalize 转 JSON 可序列化结构。
- 文件读取异常向上抛出，由 service 层封装为业务异常。
"""

from __future__ import annotations

import json
import threading
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

from app.config.path_conf import BASE_DIR

# 真实样本数据目录（项目根下 docs/zhujiang_xinqiao_parq，已 gitignore）
DATA_DIR = BASE_DIR.parent / "docs" / "zhujiang_xinqiao_parq"

# 子表 → 展示模态映射（patient 为基本信息，单独处理）
TABLE_TO_MODALITY: dict[str, str] = {
    "surgery_record": "clinical",   # 手术记录 → 临床
    "follow_up": "clinical",        # 随访结局 → 临床
    "pathology_specimen": "pathology",  # 病理标本 → 病理
    "ihc_result": "pathology",      # 免疫组化 → 病理
    "genetic_test": "genetic",      # 基因检测 → 基因
    "nodule_imaging": "imaging",    # 结节影像 → 影像
}
# 子表 → 中文标签（前端折叠面板分组标题用）
TABLE_LABEL: dict[str, str] = {
    "surgery_record": "手术记录",
    "follow_up": "随访结局",
    "pathology_specimen": "病理标本",
    "ihc_result": "免疫组化",
    "genetic_test": "基因检测",
    "nodule_imaging": "结节影像",
}
# 四模态
MODALITIES = ("clinical", "genetic", "pathology", "imaging")

# --------------------------------------------------------------------------- #
# 连接管理
# --------------------------------------------------------------------------- #

_lock = threading.Lock()
_con: duckdb.DuckDBPyConnection | None = None


def _get_con() -> duckdb.DuckDBPyConnection:
    """单例内存连接。DuckDB 单连接非线程安全，加锁串行化查询（demo 数据量可接受）。"""
    global _con
    if _con is None:
        _con = duckdb.connect(database=":memory:", read_only=False)
    return _con


def _read_parquet(table: str) -> str:
    """构造 read_parquet(...) 调用片段，自动适配布局。

    - 扁平布局（单文件）：`DATA_DIR/{table}.parquet` 直接读；
    - 按中心子目录布局：`DATA_DIR/*/{table}.parquet` 用 glob + union_by_name 合并多中心。
    """
    flat = DATA_DIR / f"{table}.parquet"
    if flat.exists():
        return f"read_parquet('{flat.as_posix()}')"
    return f"read_parquet('{DATA_DIR.as_posix()}/*/{table}.parquet', union_by_name=true)"


def _query(sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    """执行查询，返回归一化后的 dict 行列表。"""
    with _lock:
        con = _get_con()
        cur = con.execute(sql, params or [])
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    return [_normalize({c: v for c, v in zip(cols, row)}) for row in rows]


def _query_one(sql: str, params: list[Any] | None = None) -> Any:
    """执行聚合查询，返回单个值（如 count）。"""
    with _lock:
        con = _get_con()
        return con.execute(sql, params or []).fetchone()[0]


# --------------------------------------------------------------------------- #
# 类型归一化（JSON 串/struct/list/date/Decimal → JSON 可序列化）
# --------------------------------------------------------------------------- #

def _try_parse_json(value: str) -> Any:
    """尝试把 JSON 文本解析为 Python 对象；失败则原样返回。"""
    if not value or value[0] not in "{[":
        return value
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return value


def _normalize(value: Any) -> Any:
    """递归把 DuckDB 返回的复合类型转为 JSON 可序列化的 Python 对象。

    DuckDB 的 JSON 类型经 Python 绑定返回为 str（JSON 文本），此处解析为 dict/list，
    便于前端按对象渲染（而非二次转义的字符串）。
    """
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    if isinstance(value, str):
        return _try_parse_json(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


# --------------------------------------------------------------------------- #
# 查询接口
# --------------------------------------------------------------------------- #

def list_centers() -> list[str]:
    """枚举数据中出现的来源中心（供前端下拉）。"""
    rows = _query(
        f"SELECT DISTINCT source_center FROM {_read_parquet('patient')} "
        f"WHERE source_center IS NOT NULL ORDER BY source_center"
    )
    return [r["source_center"] for r in rows]


def list_patients(
    center: str | None = None,
    keyword: str | None = None,
    offset: int = 0,
    limit: int = 10,
) -> tuple[list[dict[str, Any]], int]:
    """患者分页列表。返回 (行列表, 总数)。"""
    where = []
    params: list[Any] = []
    if center:
        where.append("source_center = ?")
        params.append(center)
    if keyword:
        where.append("(patient_id ILIKE ? OR source_center ILIKE ?)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    sql = (
        f"SELECT patient_id, source_center, gender, birth_date, ethnicity, "
        f"native_place, abo_blood_type, rh_blood_type, smoking_status, first_nodule_date "
        f"FROM {_read_parquet('patient')} {where_sql} "
        f"ORDER BY source_center, patient_id LIMIT ? OFFSET ?"
    )
    rows = _query(sql, params + [limit, offset])

    count_sql = f"SELECT count(*) FROM {_read_parquet('patient')} {where_sql}"
    total = _query_one(count_sql, params)
    return rows, total


def get_patient_detail(patient_id: str, center: str | None = None) -> dict[str, Any]:
    """患者多模态详情，按四模态分组。中心由 patient 表 source_center 决定。"""
    # 1) 患者基本信息
    psql = f"SELECT * FROM {_read_parquet('patient')} WHERE patient_id = ?"
    if center:
        psql += " AND source_center = ?"
        prows = _query(psql, [patient_id, center])
    else:
        prows = _query(psql, [patient_id])
    if not prows:
        return {}
    patient = prows[0]

    # 2) 按模态聚合各子表（仅按 patient_id 过滤）
    modalities: dict[str, list[dict[str, Any]]] = {m: [] for m in MODALITIES}
    for table, modality in TABLE_TO_MODALITY.items():
        rows = _query(
            f"SELECT * FROM {_read_parquet(table)} WHERE patient_id = ?",
            [patient_id],
        )
        label = TABLE_LABEL[table]
        modalities[modality].extend({"_table": label, **r} for r in rows)

    return {
        "patient": patient,
        "clinical": modalities["clinical"],
        "genetic": modalities["genetic"],
        "pathology": modalities["pathology"],
        "imaging": modalities["imaging"],
    }
