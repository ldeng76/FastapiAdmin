"""ETL-1 适配: zhujiang0814.parquet → ETL-2 引擎期望的 patient.parquet 布局。

2026-08-14 珠江新批次 (docs/demodata/zhujiang0814.parquet) 是单表 patient 维度,
列名与 0723 批次 (ETL-2 引擎 _import_patient_table 期望) 不同:
  sex                → gender
  personal_smoking_status → smoking_status
  blood_type_abo     → abo_blood_type
  blood_type_rh      → rh_blood_type
  bmi (标量)         → demographics = {'bmi': ...}
  病史散列 (家族史/既往肿瘤/合并症/吸烟包年/发现途径/raw_text)
                     → medical_history struct (引擎整体序列化进 patient_meta JSONB)

用法:
    cd backend
    ./.venv/Scripts/python.exe etl1_adapt_zhujiang0814.py
    # 或指定路径:
    ./.venv/Scripts/python.exe etl1_adapt_zhujiang0814.py \
        --src ../docs/demodata/zhujiang0814.parquet --out-dir ../data/zhujiang

幂等: 可重复运行 (COPY OVERWRITE_OR_IGNORE)。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb


def main() -> int:
    parser = argparse.ArgumentParser(description="zhujiang0814.parquet → ETL-2 patient.parquet 适配")
    parser.add_argument(
        "--src",
        default=None,
        help="源 parquet (默认 ../docs/demodata/zhujiang0814.parquet 相对 backend/)",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="输出目录 (默认 ../data/zhujiang 相对 backend/)",
    )
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parent
    src = Path(args.src).resolve() if args.src else (backend_dir.parent / "docs" / "demodata" / "zhujiang0814.parquet").resolve()
    out_dir = Path(args.out_dir).resolve() if args.out_dir else (backend_dir.parent / "data" / "zhujiang").resolve()

    if not src.exists():
        print(f"[ERR] 源文件不存在: {src}", file=sys.stderr)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / "patient.parquet"

    con = duckdb.connect(":memory:")
    sql = f"""
        COPY (
            SELECT
                patient_id,
                source_center,
                sex AS gender,
                birth_date,
                ethnicity,
                native_place,
                blood_type_abo AS abo_blood_type,
                blood_type_rh AS rh_blood_type,
                personal_smoking_status AS smoking_status,
                first_nodule_date,
                struct_pack(bmi := bmi) AS demographics,
                struct_pack(
                    smoking_pack_years := personal_smoking_pack_year,
                    family_lung_cancer := family_lung_cancer,
                    family_other_cancer := family_other_cancer,
                    prior_malignancy := prior_malignancy,
                    comorbid_copd := comorbid_copd,
                    comorbid_old_tb := comorbid_old_tb,
                    discovery_route := first_nodule_discovery,
                    raw_text := raw_text
                ) AS medical_history
            FROM read_parquet('{src.as_posix()}')
        ) TO '{dst.as_posix()}' (FORMAT PARQUET, OVERWRITE_OR_IGNORE)
    """
    con.execute(sql)

    n = con.execute("SELECT COUNT(*) FROM read_parquet(?)", [dst.as_posix()]).fetchone()[0]
    n_dup = con.execute(
        "SELECT COUNT(*) - COUNT(DISTINCT patient_id) FROM read_parquet(?)", [dst.as_posix()]
    ).fetchone()[0]
    n_raw = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE medical_history.raw_text IS NOT NULL",
        [dst.as_posix()],
    ).fetchone()[0]
    print(f"[OK] {dst} 已生成: {n} 患者, 重复 patient_id {n_dup}, 带 raw_text {n_raw}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
