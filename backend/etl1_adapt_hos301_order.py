"""ETL-1 适配: 301 医院 order.parquet → ETL-2 引擎期望的 order.parquet 布局。

源文件: /data/wlx/DATABASE/extracted_tables/hos301/order.parquet (8,313 visit 行)
  schema (2026-09-04 重抽版):
    patient_id (VARCHAR)
    visit_id (BIGINT)             — **整列 1, 垃圾数据, 不再使用**
    admissionDateTime (TIMESTAMP) — 与 patient_id 一起唯一定位 visit
    deptAdmissionTo (VARCHAR)
    dischargeDateTime (TIMESTAMP)
    order_data LIST<STRUCT(
        administration VARCHAR, dosage DOUBLE, dosageUnits VARCHAR,
        freqDetail VARCHAR, frequency VARCHAR, orderClassName VARCHAR,
        orderNo BIGINT, orderSubNo BIGINT, orderText VARCHAR,
        performSchedule VARCHAR, repeatIndicator VARCHAR,
        startDateTime TIMESTAMP, stopDateTime TIMESTAMP)>

关键观察:
  - 源 visit_id 全 1 (8313/8313) 是垃圾数据, 不能直接用
  - (patient_id, admissionDateTime) 唯一 = visit 真实唯一标识
  - **visit_id 派生**: RANK() OVER (PARTITION BY patient_id ORDER BY admissionDateTime)
    与 etl1_adapt_hos301_record.py 同表达式, 保证 order 与 record 派生同一 visit_id,
    这样 ETL-2 引擎 visit_lookup 能命中, order 挂到正确 visit 桥
  - 8,313 visit 全部 patient 都包含在 record 8350 patient 内 (差 37 是 record 独有)
  - order_data 长度范围 4-1806; 展平后 ~870,800 行
  - orderClassName: 检验/西药/治疗/护理/膳食/检查/其他/手术
  - orderText 即医嘱内容, 映射到引擎 order_name

ETL2 hos301 spec: src_table='order', kind='order',
                 order_type='order', order_name_field='orderText'

引擎读 parquet 后从 rd 提取:
  patient_id, visit_id (派生自 RANK), order_name (=orderText),
  order_time (=startDateTime), order_source (=orderClassName),
  order_detail (整体 dict 进 JSONB)

其余字段 (dosage, frequency 等) → order_detail_json

DuckDB 技巧: 同 lab, LATERAL unnest(order_data) AS unnest 后 unnest.<field> 访问 struct 子字段。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb


def main() -> int:
    parser = argparse.ArgumentParser(description="hos301 order.parquet → ETL-2 order.parquet 适配")
    parser.add_argument("--src", default=None, help="源 parquet（默认 /data/wlx/.../hos301/order.parquet）")
    parser.add_argument("--out-dir", default=None, help="输出目录（默认 ../data_hos301/hos301）")
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parent
    src = (
        Path(args.src).resolve()
        if args.src
        else Path("/data/wlx/DATABASE/extracted_tables/hos301/order.parquet").resolve()
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
    dst = out_dir / "order.parquet"

    con = duckdb.connect(":memory:")
    # 派生 visit_id: RANK() OVER (PARTITION BY patient_id ORDER BY admissionDateTime)
    sql = f"""
        COPY (
            WITH derived AS (
                SELECT
                    patient_id,
                    RANK() OVER (PARTITION BY patient_id ORDER BY admissionDateTime)
                        AS visit_id_ranked,
                    order_data
                FROM read_parquet('{src.as_posix()}')
            )
            SELECT
                CAST(derived.patient_id   AS VARCHAR)        AS patient_id,
                CAST(derived.visit_id_ranked AS VARCHAR)     AS visit_id,
                CAST(unnest.orderText AS VARCHAR)           AS task_name,
                unnest.startDateTime                        AS order_time,
                CAST(unnest.orderClassName AS VARCHAR)      AS order_source,
                unnest.administration                       AS order_administration,
                unnest.dosage                               AS order_dosage,
                CAST(unnest.dosageUnits AS VARCHAR)         AS order_dosageUnits,
                CAST(unnest.freqDetail AS VARCHAR)          AS order_freqDetail,
                CAST(unnest.frequency AS VARCHAR)           AS order_frequency,
                CAST(unnest.orderClassName AS VARCHAR)      AS order_orderClassName,
                unnest.orderNo                              AS order_orderNo,
                unnest.orderSubNo                           AS order_orderSubNo,
                unnest.performSchedule                      AS order_performSchedule,
                CAST(unnest.repeatIndicator AS VARCHAR)     AS order_repeatIndicator,
                unnest.stopDateTime                         AS order_stopDateTime
            FROM derived,
                 LATERAL unnest(derived.order_data) AS unnest
        ) TO '{dst.as_posix()}' (FORMAT PARQUET, OVERWRITE_OR_IGNORE)
    """
    con.execute(sql)

    n = con.execute("SELECT COUNT(*) FROM read_parquet(?)", [dst.as_posix()]).fetchone()[0]
    n_null_pid = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE patient_id IS NULL", [dst.as_posix()]
    ).fetchone()[0]
    n_null_vid = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE visit_id IS NULL", [dst.as_posix()]
    ).fetchone()[0]
    n_null_name = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE task_name IS NULL", [dst.as_posix()]
    ).fetchone()[0]
    print(
        f"[OK] {dst} 已生成: {n} order 行, "
        f"patient_id NULL {n_null_pid}, visit_id NULL {n_null_vid}, task_name NULL {n_null_name}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())