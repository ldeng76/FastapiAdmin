"""ETL-1 适配: 301 医院 record.parquet → ETL-2 引擎期望的 visit_record.parquet 布局。

源文件: /data/wlx/DATABASE/extracted_tables/hos301/record.parquet (17,997 行)
  schema:
    patient_id (VARCHAR)
    visit_id (BIGINT)             — 78/17997 NULL；其余非空
    admissionDateTime (TIMESTAMP)  100% 非空
    dischargeDateTime (TIMESTAMP)  13/17997 NULL
    deptAdmissionTo (VARCHAR)
    Doc LIST<STRUCT(docId, docTime VARCHAR, docTitle, content VARCHAR)>

  Doc.content 是 XML/ HTML 文档（带 <!--Copyright...--> + xmlns）；
  26 万 Doc 文档清洗成本高，本次**不导入 Doc 数据**——只把顶层 visit 信息入 visit_detail。

关键观察:
  - 顶层 visit_id 与 (patient_id, admissionDateTime) 1:1
  - 17,997 顶层行 ≈ visit 次数（部分病人多次住院）
  - 78 行 visit_id NULL：引擎 visit handler 要求 visit_id 非空，过滤掉
  - 13 行 dischargeDateTime NULL：引擎 discharge_date 可空，保留

ETL2 hos301 spec: src_table='visit_record', kind='visit_detail',
                 id_field='visit_id', date_field='admissionDateTime'

引擎读 parquet 后从 rd 提取:
  patient_id, visit_id (id_field), admission_time (date_field),
  discharge_date, admission_dept (=deptAdmissionTo),
  visit_category / length_of_stay / visit_age / visit_detail_json
其余字段（含 Doc 等）→ visit_detail_json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb


def main() -> int:
    parser = argparse.ArgumentParser(description="hos301 record.parquet → ETL-2 visit_record.parquet 适配")
    parser.add_argument("--src", default=None, help="源 parquet（默认 /data/wlx/.../hos301/record.parquet）")
    parser.add_argument("--out-dir", default=None, help="输出目录（默认 ../data_hos301/hos301）")
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parent
    src = (
        Path(args.src).resolve()
        if args.src
        else Path("/data/wlx/DATABASE/extracted_tables/hos301/record.parquet").resolve()
    )
    out_dir = (
        Path(args.out_dir).resolve()
        if args.out_dir
        else (backend_dir.parent / "data_hos301" / "hos301").resolve()
    )

    if not src.exists():
        print(f"[ERR] 源文件不存在: {src}", file=sys.stderr)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / "visit_record.parquet"

    con = duckdb.connect(":memory:")
    # 顶层 visit_id 与 admissionDateTime 1:1。不展平 Doc，Doc 字段保留为 list
    # (引擎 visit_detail handler 把所有非 known 列入 JSONB)。
    # 引擎 known 列: {patient_id, id_field, visit_id, admission_time, discharge_date,
    #                   admission_dept, discharge_dept, length_of_stay,
    #                   payment_method, visit_age, visit_category}
    sql = f"""
        COPY (
            SELECT
                CAST(patient_id AS VARCHAR)         AS patient_id,
                CAST(visit_id    AS VARCHAR)        AS visit_id,
                admissionDateTime                   AS admission_time,
                dischargeDateTime                   AS discharge_date,
                CAST(deptAdmissionTo AS VARCHAR)    AS admission_dept,
                CAST(NULL AS VARCHAR)               AS discharge_dept,
                CAST(NULL AS INTEGER)               AS length_of_stay,
                CAST(NULL AS VARCHAR)               AS payment_method,
                CAST(NULL AS DOUBLE)                AS visit_age,
                CAST(NULL AS VARCHAR)               AS visit_category,
                Doc                                 AS visit_Doc
            FROM read_parquet('{src.as_posix()}')
            WHERE visit_id IS NOT NULL
        ) TO '{dst.as_posix()}' (FORMAT PARQUET, OVERWRITE_OR_IGNORE)
    """
    con.execute(sql)

    n = con.execute("SELECT COUNT(*) FROM read_parquet(?)", [dst.as_posix()]).fetchone()[0]
    n_null_pid = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE patient_id IS NULL", [dst.as_posix()]
    ).fetchone()[0]
    n_dup_visit = con.execute(
        "SELECT COUNT(*) - COUNT(DISTINCT visit_id) FROM read_parquet(?)", [dst.as_posix()]
    ).fetchone()[0]
    print(
        f"[OK] {dst} 已生成: {n} visit_detail 行, "
        f"patient_id NULL {n_null_pid}, visit_id 重复 {n_dup_visit}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())