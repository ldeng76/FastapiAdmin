"""ETL-1 适配: 珠江 CT 与病理 xlsx → ETL-2 staging parquet。

源文件: docs/demodata/珠江的CT与病理数据/CT与病理数据.xlsx (20.2 万行, HIS 视图
  v_exam_patient_rpt 的原始 dump; 11 列, 关键列 EXAM_CLASS 全角 'ＣＴ' / '病理')。
工作表:
  - 'Select v_exam_patient_rpt' (数据, 202619 行)
  - 'SQL Statement'           (源 SQL 文本, 仅元数据, 跳过)

源列 (列序号):
    col0:  序号 (空)
    col1:  EXAM_NO     检查号
    col2:  PAT_LOCAL_ID 患者本地编号
    col3:  SICK_ID     住院号
    col4:  NAME        姓名
    col5:  SEX         性别 (男 / 女)
    col6:  AGE         年龄 (中文带 '岁')
    col7:  EXAM_CLASS  检查类别 (全角 'ＣＴ' / '病理')
    col8:  DESCRIPTION 检查所见 (CT 长文本 / 病理采样部位等)
    col9:  IMPRESSION  检查结论 (CT 长文本 / 病理诊断)
    col10: EXAM_DATE   检查日期 ('YYYY-MM-DD' 字符串)

输出 (落到 ../data/zhujiang/):
  - patient.parquet            (DISTINCT PAT_LOCAL_ID × gender, source_center='珠江')
  - nodule_imaging.parquet     (EXAM_CLASS = 'ＣＴ' 文本肺结节过滤, exam_id = EXAM_NO)
  - pathology_specimen.parquet (EXAM_CLASS = '病理' 文本肺病理过滤, specimen_id = EXAM_NO)

列布局对齐 ETL-2 引擎 anon_etl_engine._CENTER_PARQUET_SPECS["zhujiang"]:
  - nodule_imaging:
      body_fields = ['findings', 'impression']
      detail_fields = ['nodule_no', 'nodule_location', 'long_diameter', 'density_type',
                       'exam_meta', 'nodule_morphology', 'nodule_quantitative',
                       'follow_up_comparison', 'raw_text']
      ordinal_field = 'nodule_no'
  - pathology_specimen:
      body_fields = ['histology_class']
      detail_fields = ['specimen_meta', 'adenocarcinoma_subtypes', 'tumor_measurement',
                       'high_risk_factors', 'staging', 'specimen_type', 'sampling_site',
                       'specimens', 'raw_text']

注:
- 源 xlsx 没有结构化结节/病理字段 (nodule_no / histology_class / specimens...),
  本次只填能取的部分: findings/impression (来自 DESCRIPTION/IMPRESSION); 其余 detail
  字段全部 NULL。后续 ETL-2 引擎见到 NULL detail 时走空 dict 分支, 不报错。
- exam_id (CT) 与 specimen_id (病理) 重复的 192 条按引擎 seen_exam_anon 去重处理,
  本适配层保留 EXAM_NO 原值, 引擎侧 dedup 即可。
- exam_meta 用 struct_pack 包成 struct, 引擎 JSONB 字段可消费。

用法:
    cd backend
    ./.venv/bin/python etl1_adapt_zhujiang_ct_pathology.py
    # 或显式:
    ./.venv/bin/python etl1_adapt_zhujiang_ct_pathology.py \\
        --src /mnt/nfs_d/wlx/DATABASE/01_disk/_字段与原始数据/1珠江/CT与病理数据.xlsx \\
        --out-dir ../data/zhujiang

幂等: COPY OVERWRITE_OR_IGNORE。
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

import duckdb


# 默认源文件 (plan-sess_76eeb724 中提到的 docs/demodata 路径不存在, 实际在 NFS)
DEFAULT_SRC = Path(
    "/mnt/nfs_d/wlx/DATABASE/01_disk/_字段与原始数据/1珠江/CT与病理数据.xlsx"
)

# 数据 sheet 名 (忽略 'SQL Statement' 元数据 sheet)
DATA_SHEET = "Select v_exam_patient_rpt"

# 源列定义 (顺序与 xlsx 第 1 行表头对齐)
COLS = (
    "seq_no",         # 序号 (col0, 空)
    "exam_no",        # EXAM_NO
    "pat_local_id",   # PAT_LOCAL_ID
    "sick_id",        # SICK_ID
    "name",           # NAME
    "sex",            # SEX (男 / 女)
    "age_text",       # AGE (中文 '67岁')
    "exam_class",     # EXAM_CLASS (全角 'ＣＴ' / '病理')
    "description",    # DESCRIPTION
    "impression",     # IMPRESSION
    "exam_date",      # EXAM_DATE (YYYY-MM-DD)
)


def xlsx_to_temp_parquet(xlsx_path: Path, sheet: str = DATA_SHEET) -> Path:
    """读 xlsx 指定 sheet 全部行, 转存为临时 parquet 供 duckdb 消费。

    openpyxl 流式 iter_rows 读 20 万行 ~5s。返回临时 parquet 路径, 调用方负责删除。
    """
    import openpyxl

    tmp_fd, tmp_name = tempfile.mkstemp(suffix=".parquet", prefix="xlsx_")
    os.close(tmp_fd)
    tmp = Path(tmp_name)

    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    if sheet not in wb.sheetnames:
        wb.close()
        raise ValueError(
            f"xlsx 缺少预期 sheet {sheet!r}; 实际 sheets: {wb.sheetnames}"
        )
    ws = wb[sheet]

    rows: list[tuple] = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        rows.append(tuple("" if v is None else str(v) for v in row))
    wb.close()
    if not rows:
        raise ValueError(f"xlsx sheet {sheet!r} 无数据行")

    col_list = ",".join(COLS)
    col_defs = ",".join(c + " VARCHAR" for c in COLS)
    placeholders = ",".join(["?"] * len(COLS))
    con = duckdb.connect(":memory:")
    con.execute(f"CREATE TABLE _x ({col_defs})")
    con.executemany(
        f"INSERT INTO _x ({col_list}) VALUES ({placeholders})", rows
    )
    con.execute(
        f"COPY (SELECT {col_list} FROM _x) TO '{tmp.as_posix()}' (FORMAT PARQUET)"
    )
    con.close()
    print(f"[xlsx] 读取 {len(rows)} 行 -> {tmp}", flush=True)
    return tmp


def _sql_nodule(src_posix: str, dst_posix: str) -> str:
    """nodule_imaging SQL: 文本肺结节过滤。"""
    return f"""COPY (
                SELECT
                    pat_local_id                                            AS patient_id,
                    exam_no                                                 AS exam_id,
                    TRY_CAST(exam_date AS DATE)                             AS exam_date,
                    'CT'                                                    AS exam_type,
                    regexp_replace(description, '\\r\\n|\\r', '\\n', 'g')  AS findings,
                    regexp_replace(impression,  '\\r\\n|\\r', '\\n', 'g')  AS impression,
                    'n1'                                                    AS nodule_no,
                    CAST(NULL AS VARCHAR)                                   AS nodule_location,
                    CAST(NULL AS DOUBLE)                                    AS long_diameter,
                    CAST(NULL AS VARCHAR)                                   AS density_type,
                    {{'pat_local_id': pat_local_id, 'source': 'ct_pathology_xlsx'}} AS exam_meta,
                    CAST(NULL AS JSON)                                      AS nodule_morphology,
                    CAST(NULL AS JSON)                                      AS nodule_quantitative,
                    CAST(NULL AS VARCHAR)                                   AS follow_up_comparison,
                    regexp_replace(
                        COALESCE(description, '') || E'\\n---\\n' || COALESCE(impression, ''),
                        '\\r\\n|\\r', '\\n', 'g'
                    )                                                       AS raw_text
                FROM read_parquet('{src_posix}')
                WHERE exam_class = 'ＣＴ'
                  AND (
                      impression  ILIKE '%肺%'
                   OR impression  ILIKE '%结节%'
                   OR description ILIKE '%肺%'
                   OR description ILIKE '%结节%'
                   OR description ILIKE '%胸部CT%'
                  )
            ) TO '{dst_posix}' (FORMAT PARQUET, OVERWRITE_OR_IGNORE)"""


def _sql_pathology(src_posix: str, dst_posix: str) -> str:
    """pathology_specimen SQL: 文本肺病理过滤。"""
    return f"""COPY (
                WITH src AS (
                    SELECT
                        pat_local_id,
                        exam_no,
                        exam_date,
                        regexp_replace(impression,  '\\r\\n|\\r', '\\n', 'g')  AS pathology_diagnosis,
                        regexp_replace(description, '\\r\\n|\\r', '\\n', 'g')  AS exam_detail_text,
                        regexp_replace(
                            COALESCE(description, '') || E'\\n---\\n' || COALESCE(impression, ''),
                            '\\r\\n|\\r', '\\n', 'g'
                        ) AS raw_text
                    FROM read_parquet('{src_posix}')
                    WHERE exam_class = '病理'
                      AND (
                          impression  ILIKE '%肺%'
                       OR impression  ILIKE '%结节%'
                       OR impression  ILIKE '%肺癌%'
                       OR impression  ILIKE '%NSCC%'
                       OR impression  ILIKE '%腺癌%'
                       OR impression  ILIKE '%鳞癌%'
                       OR impression  ILIKE '%小细胞%'
                       OR description ILIKE '%肺%'
                      )
                )
                SELECT
                    pat_local_id                                            AS patient_id,
                    exam_no                                                 AS specimen_id,
                    TRY_CAST(exam_date AS DATE)                             AS exam_date,
                    COALESCE(
                        NULLIF(SPLIT_PART(pathology_diagnosis, E'\\n', 1), ''),
                        NULLIF(SPLIT_PART(exam_detail_text,    E'\\n', 1), '')
                    )                                                        AS histology_class,
                    CAST(NULL AS JSON)                                      AS specimen_meta,
                    CAST(NULL AS JSON)                                      AS adenocarcinoma_subtypes,
                    CAST(NULL AS JSON)                                      AS tumor_measurement,
                    CAST(NULL AS JSON)                                      AS high_risk_factors,
                    CAST(NULL AS JSON)                                      AS staging,
                    CAST(NULL AS VARCHAR)                                   AS specimen_type,
                    CAST(NULL AS VARCHAR)                                   AS sampling_site,
                    CAST(NULL AS JSON)                                      AS specimens,
                    TO_JSON({{'raw_text': exam_detail_text}})               AS exam_detail,
                    raw_text
                FROM src
            ) TO '{dst_posix}' (FORMAT PARQUET, OVERWRITE_OR_IGNORE)"""


def _sql_patient(src_posix: str, dst_posix: str) -> str:
    """patient SQL: CT 行去重后建患者维度表 (含中文 SEX, 引擎 enum 兜底)。"""
    return f"""COPY (
                SELECT DISTINCT
                    pat_local_id         AS patient_id,
                    '珠江'                AS source_center,
                    sex                  AS gender,
                    TRY_CAST(NULL AS DATE)  AS birth_date,
                    CAST(NULL AS VARCHAR) AS ethnicity,
                    CAST(NULL AS VARCHAR) AS native_place,
                    CAST(NULL AS VARCHAR) AS abo_blood_type,
                    CAST(NULL AS VARCHAR) AS rh_blood_type,
                    CAST(NULL AS VARCHAR) AS smoking_status,
                    TRY_CAST(NULL AS DATE)  AS first_nodule_date,
                    CAST(NULL AS DOUBLE) AS bmi,
                    CAST(NULL AS JSON)   AS demographics,
                    CAST(NULL AS JSON)   AS medical_history
                FROM read_parquet('{src_posix}')
                WHERE exam_class = 'ＣＴ'
                  AND pat_local_id IS NOT NULL
                  AND pat_local_id <> ''
            ) TO '{dst_posix}' (FORMAT PARQUET, OVERWRITE_OR_IGNORE)"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="珠江 CT 与病理 xlsx → ETL-2 staging parquet 适配"
    )
    parser.add_argument(
        "--src",
        default=None,
        help=f"源 xlsx (默认 {DEFAULT_SRC})",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="输出目录 (默认 ../data/zhujiang 相对 backend/)",
    )
    args = parser.parse_args()
    import hashlib
    import json

    backend_dir = Path(__file__).resolve().parent
    src = Path(args.src).resolve() if args.src else DEFAULT_SRC.resolve()
    out_dir = (
        Path(args.out_dir).resolve()
        if args.out_dir
        else (backend_dir.parent / "data" / "zhujiang").resolve()
    )

    if not src.exists():
        print(f"[ERR] 源文件不存在: {src}", file=sys.stderr)
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) xlsx -> temp parquet (供后续 duckdb SQL 引用)
    tmp_pq = xlsx_to_temp_parquet(src)
    src_posix = tmp_pq.as_posix()

    try:
        con = duckdb.connect(":memory:")

        dst_nodule = out_dir / "nodule_imaging.parquet"
        dst_path = out_dir / "pathology_specimen.parquet"
        dst_patient = out_dir / "patient.parquet"

        # ---- 2) nodule_imaging.parquet ----
        con.execute(_sql_nodule(src_posix, dst_nodule.as_posix()))

        # ---- 3) pathology_specimen.parquet ----
        con.execute(_sql_pathology(src_posix, dst_path.as_posix()))

        # ---- 4) patient.parquet ----
        con.execute(_sql_patient(src_posix, dst_patient.as_posix()))

        # ---- 5) 输出校验摘要 ----
        n_nodule = con.execute(
            "SELECT COUNT(*) FROM read_parquet(?)", [dst_nodule.as_posix()]
        ).fetchone()[0]
        n_nodule_uniq = con.execute(
            "SELECT COUNT(DISTINCT exam_id) FROM read_parquet(?)",
            [dst_nodule.as_posix()],
        ).fetchone()[0]
        n_path = con.execute(
            "SELECT COUNT(*) FROM read_parquet(?)", [dst_path.as_posix()]
        ).fetchone()[0]
        n_path_uniq = con.execute(
            "SELECT COUNT(DISTINCT specimen_id) FROM read_parquet(?)",
            [dst_path.as_posix()],
        ).fetchone()[0]
        n_patient = con.execute(
            "SELECT COUNT(*) FROM read_parquet(?)", [dst_patient.as_posix()]
        ).fetchone()[0]
        n_patient_uniq = con.execute(
            "SELECT COUNT(DISTINCT patient_id) FROM read_parquet(?)",
            [dst_patient.as_posix()],
        ).fetchone()[0]
        print(
            f"[OK] nodule_imaging:      {n_nodule:>7,} 行 (唯一 exam_id: {n_nodule_uniq:,})\n"
            f"[OK] pathology_specimen:  {n_path:>7,} 行 (唯一 specimen_id: {n_path_uniq:,})\n"
            f"[OK] patient:             {n_patient:>7,} 行 (唯一 patient_id: {n_patient_uniq:,})"
        )

        # ---- 6) 写 _meta/conversion_manifest.json (ETL-2 anon_etl_service 依赖) ----
        meta_dir = out_dir / "_meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        src_sha = hashlib.sha256(src.read_bytes()).hexdigest()
        manifest = {
            "source_file": str(src),
            "source_sha256": src_sha,
            "tables": {
                "nodule_imaging": {"rows": n_nodule, "unique_pk": n_nodule_uniq},
                "pathology_specimen": {"rows": n_path, "unique_pk": n_path_uniq},
                "patient": {"rows": n_patient, "unique_pk": n_patient_uniq},
            },
        }
        (meta_dir / "conversion_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(
            f"[OK] {meta_dir / 'conversion_manifest.json'} 已生成 "
            f"(source_sha256: {src_sha[:16]}...)"
        )
        return 0
    finally:
        try:
            tmp_pq.unlink()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    sys.exit(main())