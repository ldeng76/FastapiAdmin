"""ETL-1 后处理: 给珠江 patient.parquet 注入 first_nodule_date。

珠江 xlsx 没有结构化的 birth_date/first_nodule_date, 但可以从 nodule_imaging.parquet
按 patient_id 聚合 MIN(exam_date) 派生 first_nodule_date (unified_table_schema.md §1)。

用法:
    cd backend
    PYTHONPATH=. ./.venv/Scripts/python.exe etl1_postprocess_zhujiang.py
    # 或指定目录:
    PYTHONPATH=. ./.venv/Scripts/python.exe etl1_postprocess_zhujiang.py --data-dir ../data/zhujiang

幂等: 可重复运行。
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import duckdb


def main() -> int:
    parser = argparse.ArgumentParser(description="珠江 patient.parquet 注入 first_nodule_date")
    parser.add_argument(
        "--data-dir",
        default=None,
        help="数据目录 (默认 ../data/zhujiang 相对 backend/)",
    )
    args = parser.parse_args()

    if args.data_dir:
        data_dir = Path(args.data_dir).resolve()
    else:
        data_dir = (Path(__file__).resolve().parent.parent / "data" / "zhujiang").resolve()

    patient_pq = data_dir / "patient.parquet"
    nodule_pq = data_dir / "nodule_imaging.parquet"
    tmp_pq = patient_pq.with_suffix(".parquet.tmp")

    if not patient_pq.exists():
        print(f"[ERR] {patient_pq} 不存在, 请先跑 ETL-1", file=sys.stderr)
        return 1
    if not nodule_pq.exists():
        print(f"[ERR] {nodule_pq} 不存在, 需先落 nodule_imaging.parquet", file=sys.stderr)
        return 1

    con = duckdb.connect(":memory:")
    # 派生 first_nodule_date: 每个 patient 取 nodule_imaging 中最早 exam_date
    # Review M6: 用 p.* 而不是显式列名, 避免后续 patient 配置新增列时脚本静默丢列
    sql = f"""
        COPY (
            SELECT
                p.*,
                CAST(MIN(n.exam_date) AS DATE) AS first_nodule_date
            FROM read_parquet('{patient_pq.as_posix()}') p
            LEFT JOIN read_parquet('{nodule_pq.as_posix()}') n
              ON p.patient_id = n.patient_id
            GROUP BY p.*
        ) TO '{tmp_pq.as_posix()}' (FORMAT PARQUET, OVERWRITE_OR_IGNORE)
    """
    con.execute(sql)

    # 统计
    n_total = con.execute(
        "SELECT count(*) FROM read_parquet(?)", [patient_pq.as_posix()]
    ).fetchone()[0]
    n_with_date = con.execute(
        "SELECT count(*) FROM read_parquet(?) WHERE first_nodule_date IS NOT NULL",
        [tmp_pq.as_posix()],
    ).fetchone()[0]

    # 原子替换
    shutil.move(str(tmp_pq), str(patient_pq))
    print(
        f"[OK] {patient_pq} 已更新 "
        f"({n_total} 患者, {n_with_date} 有 first_nodule_date)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())