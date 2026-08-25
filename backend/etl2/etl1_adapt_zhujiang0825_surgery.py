"""ETL-1 适配: operation.parquet → ETL-2 引擎期望的 surgery_record.parquet 布局。

源文件: /data/wlx/DATABASE/extracted_tables/zhujiang/operation.parquet
  (18,326 行, 手术/操作记录, 1 行 1 手术)
  关键列:
    patient_id, inpatient_id, operation_name, operation_date(DATE),
    icd9cm3_code, resection_scope, surgical_approach, asa_score, los_days

zhujiang spec (anon_etl_engine.py) 期望的 surgery_record 列 (kind=surgery):
  patient_id, visit_id, procedure_name, surgery_date,
  resection_scope, surgical_approach, procedure_detail
  引擎守卫: patient_id / visit_id / procedure_name 任一为空则跳过该行
  (visit 桥从 visit_id 反推生成)。

本适配:
  - patient_id     <- patient_id (原样)
  - visit_id       <- inpatient_id
  - procedure_name <- operation_name
  - surgery_date   <- operation_date (已是 DATE, 原样)
  - resection_scope / surgical_approach <- 原样
  - procedure_detail <- struct_pack(icd9cm3_code, asa_score, los_days)  原生 STRUCT
  引擎 _build_detail_json 直接取 Python 值做 JSON 序列化, 故 detail 列必须是
  原生 struct 列(struct_pack), 不能是 to_json 字符串 (否则双重编码)。

用法:
    cd backend
    ./.venv/bin/python etl1_adapt_zhujiang0825_surgery.py
    # 或指定路径:
    ./.venv/bin/python etl1_adapt_zhujiang0825_surgery.py \
        --src /data/wlx/DATABASE/extracted_tables/zhujiang/operation.parquet \
        --out-dir ../data_zj0825/zhujiang

幂等: COPY OVERWRITE_OR_IGNORE。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb


def main() -> int:
    parser = argparse.ArgumentParser(description="operation.parquet → ETL-2 surgery_record.parquet 适配")
    parser.add_argument(
        "--src",
        default=None,
        help="源 parquet (默认 /data/wlx/DATABASE/extracted_tables/zhujiang/operation.parquet)",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="输出目录 (默认 ../data_zj0825/zhujiang 相对 backend/)",
    )
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parent.parent
    default_src = Path("/data/wlx/DATABASE/extracted_tables/zhujiang/operation.parquet")
    src = Path(args.src).resolve() if args.src else default_src.resolve()
    out_dir = Path(args.out_dir).resolve() if args.out_dir else (backend_dir.parent / "data_zj0825" / "zhujiang").resolve()

    if not src.exists():
        print(f"[ERR] 源文件不存在: {src}", file=sys.stderr)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / "surgery_record.parquet"

    con = duckdb.connect(":memory:")
    src_posix = src.as_posix()
    dst_posix = dst.as_posix()
    sql = f"""
        COPY (
            SELECT
                patient_id,
                inpatient_id                    AS visit_id,
                operation_name                  AS procedure_name,
                operation_date                  AS surgery_date,
                resection_scope,
                surgical_approach,
                struct_pack(
                    icd9cm3_code := icd9cm3_code,
                    asa_score := asa_score,
                    los_days := los_days
                )                               AS procedure_detail
            FROM read_parquet('{src_posix}')
        ) TO '{dst_posix}' (FORMAT PARQUET, OVERWRITE_OR_IGNORE)
    """
    con.execute(sql)

    n = con.execute("SELECT COUNT(*) FROM read_parquet(?)", [dst.as_posix()]).fetchone()[0]
    n_visit_empty = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE visit_id IS NULL OR visit_id = ''",
        [dst.as_posix()],
    ).fetchone()[0]
    n_name_empty = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE procedure_name IS NULL OR procedure_name = ''",
        [dst.as_posix()],
    ).fetchone()[0]
    n_pid_empty = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE patient_id IS NULL OR patient_id = ''",
        [dst.as_posix()],
    ).fetchone()[0]
    print(
        f"[OK] {dst} 已生成\n"
        f"     总行数: {n}\n"
        f"     patient_id 空: {n_pid_empty}\n"
        f"     visit_id 空: {n_visit_empty}\n"
        f"     procedure_name 空: {n_name_empty}  (引擎对三者任一为空即跳过该行)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
