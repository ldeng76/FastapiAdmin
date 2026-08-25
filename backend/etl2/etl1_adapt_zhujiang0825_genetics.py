"""ETL-1 适配: genetics.parquet → ETL-2 引擎期望的 genetic_test.parquet 布局。

源文件: /data/wlx/DATABASE/extracted_tables/zhujiang/genetics.parquet (1,091 行, 25 列)
  关键列:
    patient_id, exam_id, pat_local_id, exam_date(VARCHAR),
    sample_source, test_method, panel_size,
    tmb_per_mb, tmb_level,
    egfr/egfr_vaf_pct, kras/kras_vaf_pct, alk_fusion, ros1_fusion, ret_fusion,
    ntrk_fusion, braf, her2, met, tp53, other_variants,
    msi, mmr, raw_text

zhujiang spec (anon_etl_engine.py) 期望的 genetic_test 列:
  id_field = "test_id", date_field = "test_date"
  detail_fields = ["test_meta", "variant_result", "driver_mutations", "immune_markers"]

本适配:
  - patient_id   <- patient_id (原样)
  - test_id      <- exam_id
  - test_date    <- CAST(exam_date AS DATE)  (VARCHAR YYYY-MM-DD -> DATE)
  - test_meta    <- struct_pack(sample_source, test_method, panel_size,
                                pat_local_id, raw_text)  原生 STRUCT
  - variant_result <- struct_pack(tmb_per_mb, tmb_level)
  - driver_mutations <- struct_pack(egfr, egfr_vaf_pct, kras, kras_vaf_pct,
                                    alk_fusion, ros1_fusion, ret_fusion,
                                    ntrk_fusion, braf, her2, met, tp53,
                                    other_variants)
  - immune_markers <- struct_pack(msi, mmr)
  引擎 _build_detail_json 直接取 Python 值做 JSON 序列化, 故 detail 列必须是
  原生 struct 列(struct_pack), 不能是 to_json 字符串 (否则双重编码)。

用法:
    cd backend
    ./.venv/bin/python etl1_adapt_zhujiang0825_genetics.py
    # 或指定路径:
    ./.venv/bin/python etl1_adapt_zhujiang0825_genetics.py \
        --src /data/wlx/DATABASE/extracted_tables/zhujiang/genetics.parquet \
        --out-dir ../data_zj0825/zhujiang

幂等: COPY OVERWRITE_OR_IGNORE。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb


def main() -> int:
    parser = argparse.ArgumentParser(description="genetics.parquet → ETL-2 genetic_test.parquet 适配")
    parser.add_argument(
        "--src",
        default=None,
        help="源 parquet (默认 /data/wlx/DATABASE/extracted_tables/zhujiang/genetics.parquet)",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="输出目录 (默认 ../data_zj0825/zhujiang 相对 backend/)",
    )
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parent.parent
    default_src = Path("/data/wlx/DATABASE/extracted_tables/zhujiang/genetics.parquet")
    src = Path(args.src).resolve() if args.src else default_src.resolve()
    out_dir = Path(args.out_dir).resolve() if args.out_dir else (backend_dir.parent / "data_zj0825" / "zhujiang").resolve()

    if not src.exists():
        print(f"[ERR] 源文件不存在: {src}", file=sys.stderr)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / "genetic_test.parquet"

    con = duckdb.connect(":memory:")
    src_posix = src.as_posix()
    dst_posix = dst.as_posix()
    sql = f"""
        COPY (
            SELECT
                patient_id,
                exam_id                     AS test_id,
                CAST(exam_date AS DATE)     AS test_date,
                struct_pack(
                    sample_source := sample_source,
                    test_method := test_method,
                    panel_size := panel_size,
                    pat_local_id := pat_local_id,
                    raw_text := raw_text
                )                           AS test_meta,
                struct_pack(
                    tmb_per_mb := tmb_per_mb,
                    tmb_level := tmb_level
                )                           AS variant_result,
                struct_pack(
                    egfr := egfr,
                    egfr_vaf_pct := egfr_vaf_pct,
                    kras := kras,
                    kras_vaf_pct := kras_vaf_pct,
                    alk_fusion := alk_fusion,
                    ros1_fusion := ros1_fusion,
                    ret_fusion := ret_fusion,
                    ntrk_fusion := ntrk_fusion,
                    braf := braf,
                    her2 := her2,
                    met := met,
                    tp53 := tp53,
                    other_variants := other_variants
                )                           AS driver_mutations,
                struct_pack(
                    msi := msi,
                    mmr := mmr
                )                           AS immune_markers
            FROM read_parquet('{src_posix}')
        ) TO '{dst_posix}' (FORMAT PARQUET, OVERWRITE_OR_IGNORE)
    """
    con.execute(sql)

    n = con.execute("SELECT COUNT(*) FROM read_parquet(?)", [dst.as_posix()]).fetchone()[0]
    n_dup = con.execute(
        "SELECT COUNT(*) - COUNT(DISTINCT test_id) FROM read_parquet(?)", [dst.as_posix()]
    ).fetchone()[0]
    n_meta = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE test_meta IS NOT NULL", [dst.as_posix()]
    ).fetchone()[0]
    n_variant = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE variant_result IS NOT NULL", [dst.as_posix()]
    ).fetchone()[0]
    n_driver = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE driver_mutations IS NOT NULL", [dst.as_posix()]
    ).fetchone()[0]
    n_immune = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE immune_markers IS NOT NULL", [dst.as_posix()]
    ).fetchone()[0]
    print(
        f"[OK] {dst} 已生成\n"
        f"     总行数: {n}\n"
        f"     重复 test_id: {n_dup}\n"
        f"     test_meta 非空: {n_meta}\n"
        f"     variant_result 非空: {n_variant}\n"
        f"     driver_mutations 非空: {n_driver}\n"
        f"     immune_markers 非空: {n_immune}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
