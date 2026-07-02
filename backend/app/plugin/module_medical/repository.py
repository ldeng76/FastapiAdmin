"""医学数据访问层（DuckDB 直读 parquet，不入库）。

设计要点：
- DuckDB 以只读、内存模式连接，所有查询经 read_parquet 读 `backend/data/medical/`。
- 跨院统一表（patient/pathology_specimen/surgery_record/genetic_test）用 glob + union_by_name 合并。
- 复合类型（struct/list）由 _normalize() 转 JSON 可序列化结构。
- 文件读取异常向上抛出，由 service 层封装为业务异常。
"""

from __future__ import annotations

import threading
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

from app.config.path_conf import BASE_DIR

DATA_DIR = BASE_DIR / "data" / "medical"

# 各院独有表的目录映射（统一表用通配读取）
SHENGYI_DIR = DATA_DIR / "shengyi"
ZHUJIANG_DIR = DATA_DIR / "zhujiang_xinqiao"

# 省医独有子表
SHENGYI_ONLY = ("visit_record", "drug_order", "lab_result", "imaging_report")
# 珠江独有子表
ZHUJIANG_ONLY = ("nodule_imaging", "ihc_result", "follow_up")
# 跨院统一表（按文档定义，列名已对齐）
UNIFIED = ("pathology_specimen", "surgery_record", "genetic_test")

# --------------------------------------------------------------------------- #
# 连接管理
# --------------------------------------------------------------------------- #

_lock = threading.Lock()
_con: duckdb.DuckDBPyConnection | None = None


def _get_con() -> duckdb.DuckDBPyConnection:
    """单例只读连接。DuckDB 连接非线程安全，加锁串行化查询（demo 数据量小，可接受）。"""
    global _con
    if _con is None:
        _con = duckdb.connect(database=":memory:", read_only=False)
    return _con


def _glob(table: str) -> str:
    """统一表的 parquet 通配路径（合并两院）。"""
    return f"'{DATA_DIR.as_posix()}/*/{table}.parquet'"


def _file(center_dir: Path, table: str) -> str:
    """某院独有表的 parquet 路径。"""
    return f"'{(center_dir / f'{table}.parquet').as_posix()}'"


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
# 类型归一化（struct/list/date/Decimal → JSON 可序列化）
# --------------------------------------------------------------------------- #

def _normalize(value: Any) -> Any:
    """递归把 DuckDB 返回的复合类型转为 JSON 可序列化的 Python 对象。"""
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


# --------------------------------------------------------------------------- #
# 查询接口
# --------------------------------------------------------------------------- #

def list_patients(
    center: str | None = None,
    keyword: str | None = None,
    offset: int = 0,
    limit: int = 10,
) -> tuple[list[dict[str, Any]], int]:
    """患者列表（跨院合并）。返回 (行列表, 总数)。"""
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
        f"FROM read_parquet({_glob('patient')}, union_by_name=true) {where_sql} "
        f"ORDER BY source_center, patient_id LIMIT ? OFFSET ?"
    )
    rows = _query(sql, params + [limit, offset])

    count_sql = f"SELECT count(*) FROM read_parquet({_glob('patient')}, union_by_name=true) {where_sql}"
    total = _query_one(count_sql, params)
    return rows, total


def _rows_for(table: str, patient_id: str, center: str | None = None) -> list[dict[str, Any]]:
    """统一表：仅按 patient_id 过滤。

    统一表（pathology_specimen/surgery_record/genetic_test）不含 source_center 列，
    中心归属由 patient 表决定；同一 patient_id 不会跨院重复，故无需按 center 消歧。
    center 参数保留以兼容调用签名。
    """
    sql = (
        f"SELECT * FROM read_parquet({_glob(table)}, union_by_name=true) "
        f"WHERE patient_id = ?"
    )
    return _query(sql, [patient_id])


def _rows_in(center_dir: Path, table: str, patient_id: str) -> list[dict[str, Any]]:
    """某院独有表：按 patient_id 过滤。"""
    sql = f"SELECT * FROM read_parquet({_file(center_dir, table)}) WHERE patient_id = ?"
    return _query(sql, [patient_id])


def get_patient_detail(patient_id: str, center: str | None = None) -> dict[str, Any]:
    """患者多模态详情，按四模态分组。中心由 patient 表自身决定（取首行的 source_center）。"""
    # 1) 患者基本信息
    psql = f"SELECT * FROM read_parquet({_glob('patient')}, union_by_name=true) WHERE patient_id = ?"
    if center:
        psql += " AND source_center = ?"
        prows = _query(psql, [patient_id, center])
    else:
        prows = _query(psql, [patient_id])
    if not prows:
        return {}
    patient = prows[0]
    src_center = patient.get("source_center")

    # 2) 按模态分组
    clinical: list[dict[str, Any]] = []
    imaging: list[dict[str, Any]] = []
    pathology: list[dict[str, Any]] = []
    genetic: list[dict[str, Any]] = []

    # 统一表（两家都有；统一表无 source_center 列，仅按 patient_id 过滤）
    pathology.extend(_rows_for("pathology_specimen", patient_id))
    genetic.extend(_rows_for("genetic_test", patient_id))
    # 手术记录归入临床
    surgery = _rows_for("surgery_record", patient_id)
    clinical.extend([{"_table": "手术记录", **s} for s in surgery])

    # 省医独有
    if src_center == "省医":
        for t in SHENGYI_ONLY:
            label = {
                "visit_record": "就诊记录",
                "drug_order": "药物医嘱",
                "lab_result": "检验报告",
                "imaging_report": "影像学报告",
            }[t]
            data = _rows_in(SHENGYI_DIR, t, patient_id)
            if t == "imaging_report":
                imaging.extend([{"_table": label, **d} for d in data])
            else:
                clinical.extend([{"_table": label, **d} for d in data])

    # 珠江-新桥独有
    if src_center in ("珠江", "新桥"):
        for t in ZHUJIANG_ONLY:
            label = {
                "nodule_imaging": "结节影像",
                "ihc_result": "免疫组化",
                "follow_up": "随访结局",
            }[t]
            data = _rows_in(ZHUJIANG_DIR, t, patient_id)
            if t == "nodule_imaging":
                imaging.extend([{"_table": label, **d} for d in data])
            else:
                clinical.extend([{"_table": label, **d} for d in data])

    return {
        "patient": patient,
        "clinical": clinical,
        "genetic": genetic,
        "pathology": pathology,
        "imaging": imaging,
    }
