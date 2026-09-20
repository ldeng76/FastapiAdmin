"""ETL-1 后处理: 给珠江 patient.parquet 注入 first_nodule_date。

珠江 CT 与病理 xlsx 没有结构化的 birth_date/first_nodule_date, 但可从
nodule_imaging.parquet 按 patient_id 聚合 MIN(exam_date) 派生 first_nodule_date
(参考 unified_table_schema.md §1 patient 表)。

策略:
1. 读 nodule_imaging.parquet, 按 patient_id 聚合 MIN(exam_date) AS first_nodule_date。
2. 读 patient.parquet, LEFT JOIN 派生日期覆盖 first_nodule_date 列。
3. 写回 patient.parquet (OVERWRITE_OR_IGNORE 幂等)。

幂等: 重复运行结果一致 (派生逻辑确定, 仅写入 NULL → 已聚合值的覆盖语义稳定)。
注意: 若 patient.parquet 中已有非 NULL first_nodule_date, 本脚本保留原值不覆盖
(避免人为维护值被派生值覆盖; 用 COALESCE 兼容)。

用法:
    cd backend
    ./.venv/bin/python etl1_postprocess_zhujiang_ct_pathology.py
    # 或显式:
    ./.venv/bin/python etl1_postprocess_zhujiang_ct_pathology.py \\
        --data-dir ../data/zhujiang
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb


def main() -> int:
    parser = argparse.ArgumentParser(
        description="珠江 patient.parquet 注入 first_nodule_date (从 nodule_imaging 派生)"
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="数据目录 (默认 ../data/zhujiang 相对 backend/)",
    )
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parent
    data_dir = (
        Path(args.data_dir).resolve()
        if args.data_dir
        else (backend_dir.parent / "data" / "zhujiang").resolve()
    )

    patient_pq = data_dir / "patient.parquet"
    nodule_pq = data_dir / "nodule_imaging.parquet"

    if not patient_pq.exists():
        print(f"[ERR] 缺少 {patient_pq}, 请先运行 etl1_adapt_zhujiang_ct_pathology.py",
              file=sys.stderr)
        return 1
    if not nodule_pq.exists():
        print(f"[ERR] 缺少 {nodule_pq}, 请先运行 etl1_adapt_zhujiang_ct_pathology.py",
              file=sys.stderr)
        return 1

    con = duckdb.connect(":memory:")
    sql = f"""
        COPY (
            WITH first_nodule AS (
                SELECT patient_id,
                       MIN(exam_date) AS first_nodule_date
                FROM read_parquet('{nodule_pq.as_posix()}')
                WHERE exam_date IS NOT NULL
                GROUP BY patient_id
            )
            SELECT
                p.patient_id,
                p.source_center,
                p.gender,
                p.birth_date,
                p.ethnicity,
                p.native_place,
                p.abo_blood_type,
                p.rh_blood_type,
                p.smoking_status,
                -- 保留 patient 表中已存在的非 NULL first_nodule_date;
                -- 否则用 nodule_imaging 派生值; 都为 NULL 时维持 NULL。
                COALESCE(p.first_nodule_date, fn.first_nodule_date) AS first_nodule_date,
                p.bmi,
                p.demographics,
                p.medical_history
            FROM read_parquet('{patient_pq.as_posix()}') p
            LEFT JOIN first_nodule fn USING (patient_id)
        ) TO '{patient_pq.as_posix()}' (FORMAT PARQUET, OVERWRITE_OR_IGNORE)
    """
    con.execute(sql)

    n_total = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?)", [patient_pq.as_posix()]
    ).fetchone()[0]
    n_with_first = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE first_nodule_date IS NOT NULL",
        [patient_pq.as_posix()],
    ).fetchone()[0]
    n_nodule = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?)", [nodule_pq.as_posix()]
    ).fetchone()[0]
    # 一致性断言: nodule_imaging 中每行的 exam_date >= 该患者的 first_nodule_date
    n_pre = con.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT n.patient_id, n.exam_date,
                   (SELECT MIN(exam_date) FROM read_parquet(?) n2
                    WHERE n2.patient_id = n.patient_id) AS fn
            FROM read_parquet(?) n
        ) WHERE exam_date < fn
        """,
        [nodule_pq.as_posix(), nodule_pq.as_posix()],
    ).fetchone()[0]
    print(
        f"[OK] {patient_pq}\n"
        f"     患者总数: {n_total:,}\n"
        f"     first_nodule_date 非空: {n_with_first:,} ({n_with_first / max(n_total, 1):.1%})\n"
        f"     nodule_imaging exam_date > first_nodule_date: {n_pre:,} / {n_nodule:,} "
        f"(派生一致性断言: 所有行应满足 exam_date >= first_nodule_date)"
    )
    if n_pre > 0:
        print(
            f"[WARN] {n_pre} 行 nodule_imaging exam_date < 患者 first_nodule_date, "
            f"派生数据可能有问题 (正常应为 0)。",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())