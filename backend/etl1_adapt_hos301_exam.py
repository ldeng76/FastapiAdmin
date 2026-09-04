"""ETL-1 适配: 301 医院 exam.parquet → ETL-2 引擎期望的 exam.parquet 布局。

源文件: /data/wlx/DATABASE/extracted_tables/hos301/exam.parquet (199,560 行)
  关键列: patient_id, exam_id(VARCHAR), description, examClass(中文),
          examDateTime, examPara, examSubClass, impression, performedBy,
          recommendation, reqDateTime, reqDept, examItem(VARCHAR[])

  examClass 14 种 (按 0013 种子映射):
      ＣＴ      → CT        (全角 C，301 数据原始字符)
      病理      → Pathology
      超声      → Ultrasound
      其余 (心电图/放射/磁共振/核医学/胃肠镜/肺功能/耳鼻喉/气管镜/其他/体检/泌外) → Other

ETL2 hos301 spec (anon_etl_engine.py) 期望的 exam 表入口参数:
  src_table = "exam"
  kind = "exam_text"
  exam_type = 由 med_dict_mapping 自动归一化 (本脚本不写死)
  id_field = "exam_id"
  body_fields = ["impression", "description", "recommendation"]
  detail_fields = ["examClass", "examPara", "examSubClass", "examItem", "performedBy",
                   "reqDept", "examDateTime", "reqDateTime"]
  date_field = "examDateTime"

本脚本输出 parquet 列:
  patient_id (VARCHAR), exam_id (VARCHAR), examDateTime (TIMESTAMP),
  impression (VARCHAR), description (VARCHAR), recommendation (VARCHAR),
  examClass (VARCHAR), examPara (VARCHAR), examSubClass (VARCHAR),
  examItem (VARCHAR[]), performedBy (VARCHAR), reqDept (VARCHAR),
  reqDateTime (TIMESTAMP)

注:
  - 不在 ETL1 阶段做 examClass → exam_type 归一化（med_dict_mapping 在引擎侧统一处理）
  - examItem 是 LIST<VARCHAR>，DuckDB 直接保留，引擎 _get_nested 不需要解嵌套
  - examDateTime 已是 TIMESTAMP，引擎 birth_date_from 可直接接受

用法:
    cd backend
    ./.venv/bin/python etl1_adapt_hos301_exam.py
    # 或:
    ./.venv/bin/python etl1_adapt_hos301_exam.py \\
        --src /data/wlx/DATABASE/extracted_tables/hos301/exam.parquet \\
        --out-dir ../data_hos301/hos301

幂等: COPY OVERWRITE_OR_IGNORE。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb


def main() -> int:
    parser = argparse.ArgumentParser(description="hos301 exam.parquet → ETL-2 exam.parquet 适配")
    parser.add_argument("--src", default=None, help="源 parquet（默认 /data/wlx/.../hos301/exam.parquet）")
    parser.add_argument("--out-dir", default=None, help="输出目录（默认 ../data_hos301/hos301）")
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parent
    src = (
        Path(args.src).resolve()
        if args.src
        else Path("/data/wlx/DATABASE/extracted_tables/hos301/exam.parquet").resolve()
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
    dst = out_dir / "exam.parquet"

    con = duckdb.connect(":memory:")
    # 源数据本身就是行级（每 exam 一行），无需展平；只确保引擎期望列齐全。
    # 保留原始 examClass 字符串，由 ETL2 引擎的 med_dict_mapping 在 normalize 阶段归一化。
    sql = f"""
        COPY (
            SELECT
                CAST(patient_id  AS VARCHAR) AS patient_id,
                CAST(exam_id     AS VARCHAR) AS exam_id,
                examDateTime,
                CAST(examClass AS VARCHAR)    AS examClass,
                CASE examClass
                    WHEN 'ＣＴ'   THEN 'CT'
                    WHEN '病理'   THEN 'Pathology'
                    WHEN '超声'   THEN 'Ultrasound'
                    ELSE 'Other'
                END                          AS examType,
                CAST(description AS VARCHAR) AS description,
                CAST(recommendation AS VARCHAR) AS recommendation,
                CAST(examPara    AS VARCHAR) AS examPara,
                CAST(examSubClass AS VARCHAR) AS examSubClass,
                examItem,
                CAST(performedBy AS VARCHAR) AS performedBy,
                CAST(reqDept     AS VARCHAR) AS reqDept,
                reqDateTime
            FROM read_parquet('{src.as_posix()}')
        ) TO '{dst.as_posix()}' (FORMAT PARQUET, OVERWRITE_OR_IGNORE)
    """
    con.execute(sql)

    n = con.execute("SELECT COUNT(*) FROM read_parquet(?)", [dst.as_posix()]).fetchone()[0]
    n_dup = con.execute(
        "SELECT COUNT(*) - COUNT(DISTINCT exam_id) FROM read_parquet(?)", [dst.as_posix()]
    ).fetchone()[0]
    n_null_eid = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE exam_id IS NULL", [dst.as_posix()]
    ).fetchone()[0]
    n_null_date = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE examDateTime IS NULL", [dst.as_posix()]
    ).fetchone()[0]
    print(
        f"[OK] {dst} 已生成: {n} exams, 重复 exam_id {n_dup}, "
        f"exam_id NULL {n_null_eid}, examDateTime NULL {n_null_date}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())