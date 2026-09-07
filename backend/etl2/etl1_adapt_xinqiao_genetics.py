"""ETL-1 适配: xinqiao genetics.parquet → ETL-2 引擎期望的 genetic_test.parquet 布局。

源文件: /data/wlx/DATABASE/extracted_tables/xinqiao/genetics.parquet (4,717 行, 24 列)
  关键列:
    patient_id, pat_local_id, 病理.送检部位, exam_date(VARCHAR 时间戳),
    sample_source, test_method, panel_size,
    egfr/egfr_vaf_pct, kras/kras_vaf_pct, alk_fusion, ros1_fusion, ret_fusion,
    ntrk_fusion, braf, her2, met, tp53, other_variants,
    tmb_per_mb, tmb_level, msi, mmr, raw_text

与珠江 0825 genetics 的差异:
  - **无 exam_id 列** → 本脚本合成确定性 test_id:
      'XQG' || substr(md5(patient_id || '|' || exam_date || '|' ||
                         COALESCE(sample_source,'') || '|' ||
                         COALESCE(test_method,'')), 1, 16)
    四元组 (patient_id, exam_date, sample_source, test_method) 行级唯一
    （实测 4,717 行 4,717 组, NULL 参与分组），无需跨行合并。
  - 多一列 病理.送检部位（与检测内容无关的留档列，不入 detail）。

数据特征 (2026-09-04 实测):
  - 4,717 行 / 4,035 患者; raw_text 100% 非空
  - sample_source 2,793 行 NULL / test_method 2,958 行 NULL（COALESCE 参与 id）
  - 0 行完全重复; (patient,date) 同天多检 154 组（≤2 检, 靠 source/method 区分）

xinqiao spec (anon_etl_engine.py) 期望的 genetic_test 列:
  id_field = "test_id", date_field = "test_date"
  detail_fields = ["test_meta", "variant_result", "driver_mutations", "immune_markers"]

本适配 (1 检测 1 行):
  - patient_id   <- patient_id (原样)
  - test_id      <- 合成（见上）
  - test_date    <- CAST(exam_date AS DATE)
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
    ./.venv/bin/python etl2/etl1_adapt_xinqiao_genetics.py
    # 或指定路径:
    ./.venv/bin/python etl2/etl1_adapt_xinqiao_genetics.py \
        --src /data/wlx/DATABASE/extracted_tables/xinqiao/genetics.parquet \
        --out-dir ../data_xq0904/xinqiao

幂等: COPY OVERWRITE_OR_IGNORE。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb


def main() -> int:
    parser = argparse.ArgumentParser(description="xinqiao genetics.parquet → ETL-2 genetic_test.parquet 适配")
    parser.add_argument(
        "--src",
        default=None,
        help="源 parquet (默认 /data/wlx/DATABASE/extracted_tables/xinqiao/genetics.parquet)",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="输出目录 (默认 ../data_xq0904/xinqiao 相对 backend/)",
    )
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parent.parent
    default_src = Path("/data/wlx/DATABASE/extracted_tables/xinqiao/genetics.parquet")
    src = Path(args.src).resolve() if args.src else default_src.resolve()
    out_dir = Path(args.out_dir).resolve() if args.out_dir else (backend_dir.parent / "data_xq0904" / "xinqiao").resolve()

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
                -- 合成确定性 test id（四元组行级唯一, md5 前 16 hex = 64 bit）
                'XQG' || substr(md5(
                    patient_id || '|' || exam_date || '|' ||
                    COALESCE(sample_source, '') || '|' || COALESCE(test_method, '')
                ), 1, 16)                    AS test_id,
                CAST(exam_date AS DATE)      AS test_date,
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
    n_no_date = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE test_date IS NULL", [dst.as_posix()]
    ).fetchone()[0]
    print(
        f"[OK] {dst} 已生成\n"
        f"     总行数: {n} (源: 4,717)\n"
        f"     重复 test_id: {n_dup}\n"
        f"     test_meta 非空: {n_meta}\n"
        f"     variant_result 非空: {n_variant}\n"
        f"     driver_mutations 非空: {n_driver}\n"
        f"     immune_markers 非空: {n_immune}\n"
        f"     test_date 空: {n_no_date}"
    )
    if n_dup > 0:
        print("[ERR] test_id 存在重复, 引擎将静默去重丢行!", file=sys.stderr)
        return 1
    if n_no_date > 0:
        print("[WARN] 存在 test_date 空行, 引擎将跳过这些行!", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
