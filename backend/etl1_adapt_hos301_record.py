"""ETL-1 适配: 301 医院 record.parquet → ETL-2 引擎期望的 visit_record.parquet 布局。

源文件: /data/wlx/DATABASE/extracted_tables/hos301/record.parquet (261,271 行 / 17,997 visit)
  schema (2026-09-04 重抽版):
    patient_id (VARCHAR)
    visit_id (BIGINT)             — 全局自增序号(1/2/3...), (patient_id, visit_id) 唯一
    admissionDateTime (TIMESTAMP)  100% 非空
    dischargeDateTime (TIMESTAMP)  116/261271 NULL (可空)
    deptAdmissionTo (VARCHAR)
    docId (VARCHAR)               — 病历文档 ID (visit 内多 doc 平铺成多行)
    docTime (TIMESTAMP)           — 病历文档时间
    docTitle (VARCHAR)            — 病历文档标题
    raw_text (VARCHAR)            — 病历文档内容 (HTML/XML, 19-22KB/行)

  旧版 (2026-09-01) Doc LIST<STRUCT(...)> 已展平: 17,997 visit × 多 doc → 261,271 行。
  旧版 78/17997 visit_id NULL 在新版消失 (visit_id 0 NULL)。

关键观察:
  - (patient_id, admissionDateTime) 唯一 → visit 唯一标识 (17,997)
  - 源 visit_id 是全局自增序号 (1,2,3...), 多 patient 共享同一 visit_id
  - **visit_id 派生**: RANK() OVER (PARTITION BY patient_id ORDER BY admissionDateTime)
    保证 record 与 order 同一 (patient_id, admissionDateTime) 派生同一 visit_id,
    这样 ETL-2 引擎端 visit_lookup 可命中,order 能挂到正确 visit 桥。
  - 单 visit 最多 195 doc (Y9303816/visit=1), 平均 14.5 doc/visit
  - 261,271 - 17,997 = 243,274 多余行 → 引擎层 seen_visit_hash 丢弃
  - 单 visit 首次出现的行 = "visit 主行" (含 patient/visit/admission/discharge/dept)

ETL2 hos301 spec: src_table='visit_record', kind='visit_detail',
                 id_field='visit_id', date_field='admissionDateTime'

引擎读 parquet 后从 rd 提取:
  patient_id, visit_id (id_field, 派生自 RANK), admission_time (date_field),
  discharge_date, admission_dept (=deptAdmissionTo),
  visit_category / length_of_stay / visit_age / visit_detail_json
其余字段 (docId/docTime/docTitle/raw_text) → visit_detail_json
(同 visit 多 doc 时仅 first row 的 doc 字段进 JSONB,后续行 dedup 丢弃)
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

    # 同 visit 多 doc 行被引擎 dedup 丢弃 (保留 first row 的 docId/docTime/docTitle/raw_text)。
    # 引擎 known 列: {patient_id, id_field, visit_id, admission_time, discharge_date,
    #                   admission_dept, discharge_dept, length_of_stay,
    #                   payment_method, visit_age, visit_category}
    sql = f"""
        COPY (
            WITH derived AS (
                SELECT
                    patient_id,
                    RANK() OVER (PARTITION BY patient_id ORDER BY admissionDateTime)
                        AS visit_id_ranked,
                    admissionDateTime,
                    dischargeDateTime,
                    deptAdmissionTo,
                    docId,
                    docTime,
                    docTitle,
                    raw_text
                FROM read_parquet('{src.as_posix()}')
            )
            SELECT
                CAST(patient_id      AS VARCHAR)    AS patient_id,
                CAST(visit_id_ranked AS VARCHAR)    AS visit_id,
                admissionDateTime                   AS admission_time,
                dischargeDateTime                   AS discharge_date,
                CAST(deptAdmissionTo AS VARCHAR)    AS admission_dept,
                CAST(NULL AS VARCHAR)               AS discharge_dept,
                CAST(NULL AS INTEGER)               AS length_of_stay,
                CAST(NULL AS VARCHAR)               AS payment_method,
                CAST(NULL AS DOUBLE)                AS visit_age,
                CAST(NULL AS VARCHAR)               AS visit_category,
                docId                               AS visit_docId,
                docTime                             AS visit_docTime,
                docTitle                            AS visit_docTitle,
                raw_text                            AS visit_raw_text
            FROM derived
            WHERE visit_id_ranked IS NOT NULL
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