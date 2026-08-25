"""ETL-1 适配: ct0820.parquet → ETL-2 引擎期望的 nodule_imaging.parquet 布局。

源文件: docs/demodata/珠江的CT与病理数据/ct0820.parquet (97,039 行, 14 列)
  关键列:
    patient_id, exam_id, pat_local_id, exam_date(VARCHAR), exam_name, contrast,
    slice_thickness_mm, nodules (LIST of 13 字段 STRUCT), mediastinal_lymphadenopathy,
    pleural_effusion, lung_rads, vs_prior, raw_text

zhujiang spec (anon_etl_engine.py:1730-1802) 期望的 nodule_imaging 列:
  body_fields = ["findings", "impression"]
  detail_fields = ["nodule_no", "nodule_location", "long_diameter", "density_type",
                   "exam_meta", "nodule_morphology", "nodule_quantitative", "follow_up_comparison"]
  ordinal_field = "nodule_no"

本适配:
  - findings       <- regexp_extract(raw_text, 'DESCRIPTION\n(.*?)\n\nIMPRESSION', 1, '')
  - impression     <- regexp_extract(raw_text, 'IMPRESSION\n(.*?)$', 1, '')
  - exam_date      <- CAST(exam_date AS DATE)  (VARCHAR YYYY-MM-DD -> DATE)
  - exam_type      <- 'CT'  (ct0820 无此列, 写死)
  - nodule_no      <- 'n1'  (单 exam 1 行; 引擎 seen_exam_anon 跳过后续行)
  - nodule_location/long_diameter/density_type <- nodules[1] struct (首结节)
  - exam_meta      <- struct_pack(pat_local_id, exam_name, contrast,
                                  slice_thickness_mm, lung_rads, vs_prior,
                                  mediastinal_lymphadenopathy, pleural_effusion,
                                  report_date=exam_date, source='ct0820.parquet')
  - nodule_morphology <- to_json(nodules)  (完整结节数组保留)
  - nodule_quantitative / follow_up_comparison <- NULL

用法:
    cd backend
    PYTHONPATH=. ./.venv/Scripts/python.exe etl1_adapt_zhujiang_ct0820.py
    # 或指定路径:
    PYTHONPATH=. ./.venv/Scripts/python.exe etl1_adapt_zhujiang_ct0820.py \
        --src "../docs/demodata/珠江的CT与病理数据/ct0820.parquet" \
        --out-dir ../data_ct0820

幂等: COPY OVERWRITE_OR_IGNORE。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb


def main() -> int:
    parser = argparse.ArgumentParser(description="ct0820.parquet → ETL-2 nodule_imaging.parquet 适配")
    parser.add_argument(
        "--src",
        default=None,
        help="源 parquet (默认 ../docs/demodata/珠江的CT与病理数据/ct0820.parquet 相对 backend/)",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="输出目录 (默认 ../data_ct0820/zhujiang 相对 backend/)",
    )
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parent
    default_src = backend_dir.parent / "docs" / "demodata" / "珠江的CT与病理数据" / "ct0820.parquet"
    src = Path(args.src).resolve() if args.src else default_src.resolve()
    out_dir = Path(args.out_dir).resolve() if args.out_dir else (backend_dir.parent / "data_ct0820" / "zhujiang").resolve()

    if not src.exists():
        print(f"[ERR] 源文件不存在: {src}", file=sys.stderr)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / "nodule_imaging.parquet"

    con = duckdb.connect(":memory:")

    # DuckDB LIST/STRUCT 处理要点:
    # - nodules 是 LIST of STRUCT(nodule_location STRUCT(lobe, segment), ...)
    # - list_extract(nodules, 1) 取首元素（数组空时 NULL）
    # - to_json(nodules) 把整个 LIST 序列化为 JSON 字符串
    # - exam_meta 重组：to_json 字典字面量直接生成 JSON
    # - raw_text → findings/impression：用 regexp_extract 配 's' flag 让 . 匹配换行
    src_posix = src.as_posix()
    dst_posix = dst.as_posix()
    # 用 Python 字符串拼接规避 f-string 中复杂正则/字典字面量的转义陷阱
    findings_pat = r"DESCRIPTION[\r\n]+(.*?)[\r\n]+IMPRESSION"
    impression_pat = r"IMPRESSION[\r\n]+(.*?)$"
    sql = f"""
        COPY (
            SELECT
                patient_id,
                exam_id,
                CAST(exam_date AS DATE)               AS exam_date,
                'CT'                                  AS exam_type,
                'n1'                                  AS nodule_no,

                list_extract(nodules, 1).nodule_location.lobe
                    AS nodule_location,
                list_extract(nodules, 1).long_diameter_mm
                    AS long_diameter,
                list_extract(nodules, 1).density_type
                    AS density_type,

                coalesce(
                    nullif(trim(regexp_extract(raw_text, '{findings_pat}', 1, 's')), ''),
                    ''
                )                                       AS findings,
                coalesce(
                    nullif(trim(regexp_extract(raw_text, '{impression_pat}', 1, 's')), ''),
                    ''
                )                                       AS impression,

                to_json({{
                    'pat_local_id': pat_local_id,
                    'exam_name': exam_name,
                    'contrast': contrast,
                    'slice_thickness_mm': slice_thickness_mm,
                    'lung_rads': lung_rads,
                    'vs_prior': vs_prior,
                    'mediastinal_lymphadenopathy': mediastinal_lymphadenopathy,
                    'pleural_effusion': pleural_effusion,
                    'report_date': exam_date,
                    'source': 'ct0820.parquet'
                }})                                      AS exam_meta,

                to_json(nodules)                        AS nodule_morphology,

                CAST(NULL AS VARCHAR)                   AS nodule_quantitative,
                CAST(NULL AS VARCHAR)                   AS follow_up_comparison

            FROM read_parquet('{src_posix}')
        ) TO '{dst_posix}' (FORMAT PARQUET, OVERWRITE_OR_IGNORE)
    """
    con.execute(sql)

    # 统计输出
    n = con.execute("SELECT COUNT(*) FROM read_parquet(?)", [dst.as_posix()]).fetchone()[0]
    n_findings = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE findings IS NOT NULL AND length(findings) > 0",
        [dst.as_posix()],
    ).fetchone()[0]
    n_impression = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE impression IS NOT NULL AND length(impression) > 0",
        [dst.as_posix()],
    ).fetchone()[0]
    n_meta = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE exam_meta IS NOT NULL",
        [dst.as_posix()],
    ).fetchone()[0]
    n_nodules = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE nodule_morphology IS NOT NULL",
        [dst.as_posix()],
    ).fetchone()[0]
    n_dup = con.execute(
        "SELECT COUNT(*) - COUNT(DISTINCT exam_id) FROM read_parquet(?)", [dst.as_posix()]
    ).fetchone()[0]

    print(
        f"[OK] {dst} 已生成\n"
        f"     总行数: {n}\n"
        f"     重复 exam_id: {n_dup}\n"
        f"     findings 非空: {n_findings}\n"
        f"     impression 非空: {n_impression}\n"
        f"     exam_meta 非空: {n_meta}\n"
        f"     nodule_morphology 非空: {n_nodules}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
