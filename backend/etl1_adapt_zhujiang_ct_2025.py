"""ETL-1 适配: ct.parquet（2025-09 重抽版）→ ETL-2 引擎期望的 nodule_imaging.parquet 布局。

源文件: /data/wlx/DATABASE/extracted_tables/zhujiang/ct.parquet (97,039 行, 16 列)
  关键列:
    patient_id, exam_id, pat_local_id, exam_date(VARCHAR), exam_name, contrast,
    slice_thickness_mm, nodules (LIST of 13 字段 STRUCT, 内含 lung_rads),
    mediastinal_lymphadenopathy, pleural_effusion, vs_prior, raw_text

  vs ct0820 旧版的差异（2025-09 重抽）:
    - lung_rads 从报告顶层（每 exam 一个）下沉到 nodules[] 内每个结节 struct
      （每结节一个 lung_rads）
    - 其它 schema 字段一致

zhujiang spec (anon_etl_engine.py) 期望的 nodule_imaging 列:
  body_fields = ["findings", "impression"]
  detail_fields = ["nodule_no", "nodule_location", "long_diameter", "density_type",
                   "exam_meta", "nodule_morphology", "nodule_quantitative",
                   "follow_up_comparison", "lung_rads", "raw_text"]
  ordinal_field = "nodule_no"

本适配 (vs ct0820 适配脚本):
  - 旧 (ct0820): 1 exam 1 行 (nodule_no='n1', 取 nodules[1] 首结节, lung_rads 在 exam_meta 报告级)
  - 新 (2025-09): 按 nodules[] 1:N 展开
      * nodules 长度 N>=1: 展开为 N 行, nodule_no='n1'..'nN', lung_rads 落每行顶层
      * nodules 长度 N=0 或 NULL: 占位 1 行 (nodule_no='n0', 标量全 NULL, lung_rads NULL)
        引擎仍生成 detail_ordinal=1, 保留 exam 信息 (findings/impression/exam_meta/raw_text)
      * 顺序键: generate_series(1, GREATEST(len, 1)) 的 i 值 → 同 exam 内 nodule_no
        'n' || i 唯一确定 (避开 skill "0825 适配坑": DuckDB FIRST/list ORDER BY 不确定)

DuckDB 坑位 (skill 已踩过):
  - DuckDB 不支持 unnest WITH ORDINALITY; 用 generate_series(1, len) + list_extract 替代
  - len(NULL) 返回 NULL; GREATEST(COALESCE(len, 0), 1) 保证占位 1 行
  - CTE 必须写在 COPY (WITH ... SELECT ...) 括号内部
  - regexp_extract 必须显式 's' flag 让 . 匹配换行
  - f-string 内花括号转义; 正则先在 Python 侧用 raw string 拼好

用法:
    cd backend
    ./.venv/bin/python etl1_adapt_zhujiang_ct_2025.py
    # 或指定路径:
    ./.venv/bin/python etl1_adapt_zhujiang_ct_2025.py \
        --src /data/wlx/DATABASE/extracted_tables/zhujiang/ct.parquet \
        --out-dir ../data_zj_ct2025/zhujiang

幂等: COPY OVERWRITE_OR_IGNORE。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb


def main() -> int:
    parser = argparse.ArgumentParser(description="ct.parquet (2025-09) → ETL-2 nodule_imaging.parquet 适配")
    parser.add_argument(
        "--src",
        default=None,
        help="源 parquet (默认 /data/wlx/DATABASE/extracted_tables/zhujiang/ct.parquet)",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="输出目录 (默认 ../data_zj_ct2025/zhujiang 相对 backend/)",
    )
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parent
    default_src = Path("/data/wlx/DATABASE/extracted_tables/zhujiang/ct.parquet")
    src = Path(args.src).resolve() if args.src else default_src.resolve()
    out_dir = Path(args.out_dir).resolve() if args.out_dir else (backend_dir.parent / "data_zj_ct2025" / "zhujiang").resolve()

    if not src.exists():
        print(f"[ERR] 源文件不存在: {src}", file=sys.stderr)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / "nodule_imaging.parquet"

    con = duckdb.connect(":memory:")
    src_posix = src.as_posix()
    dst_posix = dst.as_posix()
    # f-string 内复杂正则/字典字面量易踩坑, 先 raw string 拼好
    findings_pat = r"DESCRIPTION[\r\n]+(.*?)[\r\n]+IMPRESSION"
    impression_pat = r"IMPRESSION[\r\n]+(.*?)$"
    sql = f"""
        COPY (
            WITH src AS (
                SELECT
                    patient_id,
                    exam_id,
                    CAST(exam_date AS DATE)   AS exam_date,
                    pat_local_id,
                    exam_name,
                    contrast,
                    slice_thickness_mm,
                    mediastinal_lymphadenopathy,
                    pleural_effusion,
                    vs_prior,
                    raw_text,
                    nodules
                FROM read_parquet('{src_posix}')
            ),
            -- 展开：每 exam 生成 GREATEST(len, 1) 行, 0/空/NULL 至少 1 行占位
            -- DuckDB 不支持 WITH ORDINALITY, 用 generate_series 显式拿序号 i
            unnested AS (
                SELECT
                    patient_id, exam_id, exam_date, pat_local_id, exam_name,
                    contrast, slice_thickness_mm, mediastinal_lymphadenopathy,
                    pleural_effusion, vs_prior, raw_text,
                    g.i                              AS ord,
                    list_extract(nodules, g.i)       AS nodule,
                    (nodules IS NULL OR len(nodules) = 0) AS is_placeholder
                FROM src, generate_series(1, GREATEST(COALESCE(len(nodules), 0), 1)) g(i)
            )
            SELECT
                patient_id,
                exam_id,
                exam_date,
                'CT'                                AS exam_type,
                -- 占位 (0/NULL) 标 'n0'; 展开行 'n' || ord (1 起)
                CASE
                    WHEN is_placeholder THEN 'n0'
                    ELSE 'n' || ord::VARCHAR
                END                                  AS nodule_no,
                CASE WHEN is_placeholder THEN NULL ELSE nodule.nodule_location.lobe END
                                                    AS nodule_location,
                CASE WHEN is_placeholder THEN NULL ELSE nodule.long_diameter_mm END
                                                    AS long_diameter,
                CASE WHEN is_placeholder THEN NULL ELSE nodule.density_type END
                                                    AS density_type,
                CASE WHEN is_placeholder THEN NULL ELSE nodule.lung_rads END
                                                    AS lung_rads,
                coalesce(
                    nullif(trim(regexp_extract(raw_text, '{findings_pat}', 1, 's')), ''),
                    ''
                )                                   AS findings,
                coalesce(
                    nullif(trim(regexp_extract(raw_text, '{impression_pat}', 1, 's')), ''),
                    ''
                )                                   AS impression,
                to_json({{
                    'pat_local_id': pat_local_id,
                    'exam_name': exam_name,
                    'contrast': contrast,
                    'slice_thickness_mm': slice_thickness_mm,
                    'vs_prior': vs_prior,
                    'mediastinal_lymphadenopathy': mediastinal_lymphadenopathy,
                    'pleural_effusion': pleural_effusion,
                    'report_date': exam_date,
                    'source': 'ct2025.parquet'
                }})                                  AS exam_meta,
                -- nodule_morphology: 占位空数组, 展开行单元素 LIST (lung_rads 在 struct 内)
                CASE
                    WHEN is_placeholder THEN to_json([]::JSON[])
                    ELSE to_json([nodule])
                END                                  AS nodule_morphology,
                CAST(NULL AS VARCHAR)                AS nodule_quantitative,
                CAST(NULL AS VARCHAR)                AS follow_up_comparison,
                raw_text
            FROM unnested
        ) TO '{dst_posix}' (FORMAT PARQUET, OVERWRITE_OR_IGNORE)
    """
    con.execute(sql)

    n = con.execute("SELECT COUNT(*) FROM read_parquet(?)", [dst.as_posix()]).fetchone()[0]
    n_placeholder = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE nodule_no='n0'",
        [dst.as_posix()],
    ).fetchone()[0]
    n_nodule_rows = n - n_placeholder
    n_dup_key = con.execute(
        "SELECT COUNT(*) - COUNT(DISTINCT (exam_id, nodule_no)) FROM read_parquet(?)",
        [dst.as_posix()],
    ).fetchone()[0]
    n_findings = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE findings IS NOT NULL AND length(findings) > 0",
        [dst.as_posix()],
    ).fetchone()[0]
    n_impression = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE impression IS NOT NULL AND length(impression) > 0",
        [dst.as_posix()],
    ).fetchone()[0]
    n_lung_rads = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE lung_rads IS NOT NULL",
        [dst.as_posix()],
    ).fetchone()[0]
    n_morph = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE nodule_morphology IS NOT NULL",
        [dst.as_posix()],
    ).fetchone()[0]
    n_unique_exam = con.execute(
        "SELECT COUNT(DISTINCT exam_id) FROM read_parquet(?)",
        [dst.as_posix()],
    ).fetchone()[0]

    print(
        f"[OK] {dst} 已生成\n"
        f"     总行数: {n}\n"
        f"     唯一 exam_id: {n_unique_exam} (源: 97039)\n"
        f"     占位 (n0, 0/NULL 结节): {n_placeholder}\n"
        f"     展开 (n1..nN): {n_nodule_rows}\n"
        f"     重复 (exam_id, nodule_no): {n_dup_key}\n"
        f"     findings 非空: {n_findings}\n"
        f"     impression 非空: {n_impression}\n"
        f"     lung_rads 非空: {n_lung_rads}\n"
        f"     nodule_morphology 非空: {n_morph}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
