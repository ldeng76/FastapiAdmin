"""ETL-1 适配: 301 医院 lab.parquet → ETL-2 引擎期望的 lab_result.parquet 布局。

源文件: /data/wlx/DATABASE/extracted_tables/hos301/lab.parquet (285,811 test 行)
  schema:
    patient_id (VARCHAR)
    test_id (VARCHAR)              唯一 285811 行
    labTestMaster LIST<STRUCT(8 列)>  几乎全部长度 1
    labResult LIST<STRUCT(...)>      展平后 ~3.5M 行

关键约束:
  - 顶层无 visit_id；引擎 lab handler 退化为只挂 patient
  - resultDateTime 是 VARCHAR，引擎 _clean_date 解析
  - **labTestMaster[1].notesForSpcm 有 7 行尾部含 \\u0000** (PG VARCHAR 拒绝 NUL)
    → ETL1 端对所有 VARCHAR 列 replace(..., chr(0), '') 清洗
  - **labResult.result 含 4 行 DNA 病毒载量 > 1E8** (乙型肝炎 DNA, 最大 2.1E8)
    → 超过 PG NUMERIC(12,4) 上限 (99999999.9999)
    → ETL1 端把溢出行的 item_result_value 置 NULL（原始字符串保留在 item_result/lab_detail_json）

ETL2 hos301 spec: src_table='lab_result', kind='lab', id_field='test_id'

DuckDB 关键技巧:
  - LATERAL unnest(labResult) AS unnest → 通过 unnest.reportItemName 访问 struct 子字段
  - list[1].field 取 LIST 首元素；空/NULL list 返 NULL
  - chr(0) 表示 NUL；replace(str, chr(0), '') 清洗
  - TRY_CAST(expr AS DOUBLE) 安全数值转换；CASE WHEN 范围限制
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb


def _safe_varchar(expr: str) -> str:
    """包裹 replace(..., chr(0), '') 清洗 NUL 字符。"""
    return f"replace({expr}, chr(0), '')"


def _safe_numeric(expr: str) -> str:
    """包裹 TRY_CAST + 范围限制，溢出值置 NULL（保留原始字符串进 lab_detail_json）。

    引擎写死 NUMERIC(12,4) 列；超出此范围的数值（|x| > 99999999.9999）在 ETL1 端置 NULL。
    """
    return (
        f"CASE WHEN TRY_CAST({expr} AS DOUBLE) IS NULL THEN NULL "
        f"WHEN TRY_CAST({expr} AS DOUBLE) > 99999999.9999 THEN NULL "
        f"WHEN TRY_CAST({expr} AS DOUBLE) < -99999999.9999 THEN NULL "
        f"ELSE TRY_CAST({expr} AS DOUBLE) END"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="hos301 lab.parquet → ETL-2 lab_result.parquet 适配")
    parser.add_argument("--src", default=None, help="源 parquet（默认 /data/wlx/.../hos301/lab.parquet）")
    parser.add_argument("--out-dir", default=None, help="输出目录（默认 ../data_hos301/hos301）")
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parent
    src = (
        Path(args.src).resolve()
        if args.src
        else Path("/data/wlx/DATABASE/extracted_tables/hos301/lab.parquet").resolve()
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
    dst = out_dir / "lab_result.parquet"

    con = duckdb.connect(":memory:")
    # 所有 VARCHAR 列必须清洗 NUL；item_result_value 用 _safe_numeric 限值范围
    sql = f"""
        COPY (
            SELECT
                {_safe_varchar("CAST(patient_id AS VARCHAR)")} AS patient_id,
                {_safe_varchar("CAST(test_id    AS VARCHAR)")} AS test_id,
                CAST(NULL AS VARCHAR) AS visit_id,
                {_safe_varchar("COALESCE(labTestMaster[1].subject, NULL)::VARCHAR")} AS test_name,
                {_safe_varchar("CAST(unnest.reportItemName AS VARCHAR)")} AS item_name,
                {_safe_varchar("CAST(unnest.result         AS VARCHAR)")} AS item_result,
                {_safe_numeric("unnest.result")}             AS item_result_value,
                {_safe_varchar("CAST(unnest.units          AS VARCHAR)")} AS item_unit,
                {_safe_varchar("CAST(unnest.resultDateTime AS VARCHAR)")} AS collection_time,
                {_safe_varchar("COALESCE(labTestMaster[1].notesForSpcm, NULL)::VARCHAR")} AS labTestMaster_notesForSpcm,
                {_safe_varchar("COALESCE(labTestMaster[1].orderingDept, NULL)::VARCHAR")} AS labTestMaster_orderingDept,
                {_safe_varchar("COALESCE(labTestMaster[1].performedBy, NULL)::VARCHAR")}  AS labTestMaster_performedBy,
                COALESCE(labTestMaster[1].requestedDateTime, NULL) AS labTestMaster_requestedDateTime,
                {_safe_varchar("COALESCE(labTestMaster[1].resultStatus, NULL)::VARCHAR")} AS labTestMaster_resultStatus,
                COALESCE(labTestMaster[1].resultsRptDateTime, NULL) AS labTestMaster_resultsRptDateTime,
                {_safe_varchar("COALESCE(labTestMaster[1].specimen, NULL)::VARCHAR")} AS labTestMaster_specimen,
                {_safe_varchar("COALESCE(labTestMaster[1].subject, NULL)::VARCHAR")}  AS labTestMaster_subject,
                {_safe_varchar("CAST(unnest.abnormalIndicator AS VARCHAR)")} AS labResult_abnormalIndicator,
                {_safe_varchar("CAST(unnest.instrumentId      AS VARCHAR)")} AS labResult_instrumentId,
                {_safe_varchar("CAST(unnest.printContext      AS VARCHAR)")} AS labResult_printContext,
                {_safe_varchar("CAST(unnest.reportItemCode    AS VARCHAR)")} AS labResult_reportItemCode,
                {_safe_varchar("CAST(unnest.resultType        AS VARCHAR)")} AS labResult_resultType,
                CAST(unnest.id.itemNo     AS BIGINT) AS labResult_itemNo,
                CAST(unnest.id.printOrder AS BIGINT) AS labResult_printOrder,
                {_safe_varchar("CAST(unnest.id.testNo AS VARCHAR)")} AS labResult_testNo
            FROM read_parquet('{src.as_posix()}'),
                 LATERAL unnest(labResult) AS unnest
        ) TO '{dst.as_posix()}' (FORMAT PARQUET, OVERWRITE_OR_IGNORE)
    """
    con.execute(sql)

    n = con.execute("SELECT COUNT(*) FROM read_parquet(?)", [dst.as_posix()]).fetchone()[0]
    n_null_pid = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE patient_id IS NULL", [dst.as_posix()]
    ).fetchone()[0]
    n_null_tid = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE test_id IS NULL", [dst.as_posix()]
    ).fetchone()[0]
    n_null_val = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE item_result_value IS NULL", [dst.as_posix()]
    ).fetchone()[0]
    print(
        f"[OK] {dst} 已生成: {n} labResult 行, "
        f"patient_id NULL {n_null_pid}, test_id NULL {n_null_tid}, "
        f"item_result_value NULL {n_null_val} (含非数值 + 溢出)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())