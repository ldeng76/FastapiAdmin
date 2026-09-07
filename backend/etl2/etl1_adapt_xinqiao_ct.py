"""ETL-1 适配: xinqiao ct.parquet → ETL-2 引擎期望的 nodule_imaging.parquet 布局。

源文件: /data/wlx/DATABASE/extracted_tables/xinqiao/ct.parquet (124,045 行, 12 列)
  关键列:
    patient_id, exam_id, pat_local_id(100% NULL), exam_date(VARCHAR 时间戳),
    exam_name, contrast, slice_thickness_mm, nodules (LIST of 13 字段 STRUCT,
    内含 per-nodule lung_rads), mediastinal_lymphadenopathy, pleural_effusion,
    vs_prior, raw_text

与珠江 0825 ct (extracted_tables/zhujiang/ct.parquet) 完全同构（12 列同名同型，
仅列序不同）。差异在正文标题:
  - 珠江: DESCRIPTION / IMPRESSION（英文标题）
  - 新桥: 检查所见 / 检查结论（中文标题，124,045 行 100% 命中）
  珠江正则对新桥 0 命中 → 本脚本换中文正则，正文不丢。

xinqiao spec (anon_etl_engine.py) 期望的 nodule_imaging 列:
  id_field = "exam_id", body_fields = ["findings", "impression"]
  detail_fields = ["nodule_no", "nodule_location", "long_diameter",
                   "density_type", "exam_meta", "nodule_morphology", "raw_text"]
  ordinal_field = "nodule_no"

本适配 (按 nodules[] 1:N 展开，同 etl1_adapt_zhujiang_ct_2025.py):
  - findings   <- regexp_extract(raw_text, '检查所见...检查结论', 's')
  - impression <- regexp_extract(raw_text, '检查结论...$', 's')
  - exam_date  <- CAST(exam_date AS DATE)  (VARCHAR 'YYYY-MM-DD HH:MM:SS' -> DATE)
  - nodules 长度 N>=1: 展开 N 行, nodule_no='n1'..'nN'
  - nodules 长度 0/NULL (7,491 行): 占位 1 行 nodule_no='n0', 标量全 NULL
  - exam_meta      <- struct_pack 原生 STRUCT（非 to_json 字符串，
                      避免 0825 文档记录的 detail 双重编码坑）
  - nodule_morphology <- [nodule] 单元素原生 LIST(STRUCT)（占位行 NULL；
                      lung_rads 等全部 13 字段随 struct 保留）

用法:
    cd backend
    ./.venv/bin/python etl2/etl1_adapt_xinqiao_ct.py
    # 或指定路径:
    ./.venv/bin/python etl2/etl1_adapt_xinqiao_ct.py \
        --src /data/wlx/DATABASE/extracted_tables/xinqiao/ct.parquet \
        --out-dir ../data_xq0904/xinqiao

幂等: COPY OVERWRITE_OR_IGNORE。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb


def main() -> int:
    parser = argparse.ArgumentParser(description="xinqiao ct.parquet → ETL-2 nodule_imaging.parquet 适配")
    parser.add_argument(
        "--src",
        default=None,
        help="源 parquet (默认 /data/wlx/DATABASE/extracted_tables/xinqiao/ct.parquet)",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="输出目录 (默认 ../data_xq0904/xinqiao 相对 backend/)",
    )
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parent.parent
    default_src = Path("/data/wlx/DATABASE/extracted_tables/xinqiao/ct.parquet")
    src = Path(args.src).resolve() if args.src else default_src.resolve()
    out_dir = Path(args.out_dir).resolve() if args.out_dir else (backend_dir.parent / "data_xq0904" / "xinqiao").resolve()

    if not src.exists():
        print(f"[ERR] 源文件不存在: {src}", file=sys.stderr)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / "nodule_imaging.parquet"

    con = duckdb.connect(":memory:")
    src_posix = src.as_posix()
    dst_posix = dst.as_posix()
    # f-string 内复杂正则易踩坑, 先 raw string 拼好（新桥中文标题 + 显式 's' flag）
    findings_pat = r"检查所见[\r\n]+(.*?)[\r\n]+检查结论"
    impression_pat = r"检查结论[\r\n]+(.*?)$"
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
                CASE
                    WHEN is_placeholder THEN NULL
                    ELSE struct_pack(
                        pat_local_id := pat_local_id,
                        exam_name := exam_name,
                        contrast := contrast,
                        slice_thickness_mm := slice_thickness_mm,
                        vs_prior := vs_prior,
                        mediastinal_lymphadenopathy := mediastinal_lymphadenopathy,
                        pleural_effusion := pleural_effusion,
                        report_date := exam_date,
                        source := 'xinqiao_ct.parquet'
                    )
                END                                  AS exam_meta,
                -- nodule_morphology: 展开行单元素原生 LIST(STRUCT)（13 字段全保留）
                -- 占位行 NULL（引擎 _build_detail_json 跳过 None）
                CASE
                    WHEN is_placeholder THEN NULL
                    ELSE [nodule]
                END                                  AS nodule_morphology,
                coalesce(
                    nullif(trim(regexp_extract(raw_text, '{findings_pat}', 1, 's')), ''),
                    ''
                )                                   AS findings,
                coalesce(
                    nullif(trim(regexp_extract(raw_text, '{impression_pat}', 1, 's')), ''),
                    ''
                )                                   AS impression,
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
    n_meta = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE exam_meta IS NOT NULL",
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
    n_no_date = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE exam_date IS NULL",
        [dst.as_posix()],
    ).fetchone()[0]

    print(
        f"[OK] {dst} 已生成\n"
        f"     总行数: {n}\n"
        f"     唯一 exam_id: {n_unique_exam} (源: 124,045)\n"
        f"     占位 (n0, 0/NULL 结节): {n_placeholder}\n"
        f"     展开 (n1..nN): {n_nodule_rows}\n"
        f"     重复 (exam_id, nodule_no): {n_dup_key}\n"
        f"     findings 非空: {n_findings}\n"
        f"     impression 非空: {n_impression}\n"
        f"     exam_meta 非空: {n_meta}\n"
        f"     nodule_morphology 非空: {n_morph}\n"
        f"     exam_date 空: {n_no_date}"
    )
    if n_no_date > 0:
        print("[WARN] 存在 exam_date 空行, 引擎将跳过这些行!", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
