"""ETL1 适配：珠江医院病案首页 face.parquet → 引擎期望 staging schema。

源文件：/data/wlx/DATABASE/extracted_tables/zhujiang/face.parquet
- 71 列中文名
- 9567 行 = 9567 次住院（visit_id='patient_N'）

目标 staging：
  data_zj_face/zhujiang/face_sheet_visit.parquet       → spec kind=visit_detail
  data_zj_face/zhujiang/face_sheet_diagnosis.parquet   → spec kind=diagnosis
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import duckdb

DEFAULT_SRC = "/data/wlx/DATABASE/extracted_tables/zhujiang/face.parquet"
DEFAULT_OUT = "/home/dzy/wk/lnrs/data_zj_face/zhujiang"

DATE_RE = "(\\d+)年(\\d+)月(\\d+)日(?:\\s*(\\d+)时(\\d+)分)?"
DATE_REPLACE_DT = "\\1-\\2-\\3 \\4:\\5:00"

JSON_COLS_VISIT = [
    "医疗付费方式", "性别", "出生日期", "年龄（岁）", "民族", "出生地", "籍贯",
    "职业", "婚姻状况", "院内共感染次数", "病例分型", "抢救次数", "抢救成功次数",
    "损伤、中毒的外部原因", "损伤、中毒的外部原因编码",
    "肿瘤分期类型", "T", "N", "M", "分期", "恶性肿瘤分化程度",
    "药物过敏", "过敏药物", "尸检记录", "血型", "Rh", "是否输血", "输血反应",
    "HBsAg检验结果", "HCV-Ab检验结果", "Anti-HIV1/2",
    "总费用", "自付金额", "一般医疗服务费", "一般治疗操作费", "护理费", "其他费",
    "病理诊断费", "实验室诊断费", "影像学诊断费", "临床诊断项目费",
    "非手术治疗项目费", "临床物理治疗费", "手术治疗费", "麻醉费", "手术费",
    "康复费", "中医治疗费", "西药费", "抗菌药物费用", "中成药费", "中草药费",
    "血费", "白蛋白类制品费", "球蛋白类制品费", "凝血因子类制品费", "细胞因子类制品费",
    "检查用一次性医用材料费", "治疗用一次性医用材料费", "手术用一次性医用材料费", "其他费用",
    "产科分娩婴儿记录表", "肿瘤专科病人治疗记录表",
]


def _clean_expr(col: str) -> str:
    return (
        f'CASE WHEN CAST("{col}" AS VARCHAR) IN '
        f'(\'-\',\'None\',\'\',\'nan\') OR "{col}" IS NULL '
        f'THEN NULL ELSE CAST("{col}" AS VARCHAR) END'
    )


def _content_md5(path: Path) -> str:
    con = duckdb.connect()
    rows = con.execute(
        f"SELECT * FROM read_parquet('{path}') ORDER BY 1, 2, 3"
    ).fetchall()
    h = hashlib.md5()
    for row in rows:
        h.update(repr(row).encode("utf-8"))
    return h.hexdigest()


def _iso_date_expr(col: str) -> str:
    """`YYYY年MM月DD日[HH时MM分]` → ISO string。"""
    return (
        f'regexp_replace(CAST("{col}" AS VARCHAR), '
        f"'{DATE_RE}', '{DATE_REPLACE_DT}')"
    )


def _visit_sql(src_path: str) -> str:
    json_lines = [
        f'{_clean_expr(col)} AS "_json_{col}"'
        for col in JSON_COLS_VISIT
    ]
    age_expr = (
        'TRY_CAST(regexp_extract(CAST("年龄（岁）" AS VARCHAR), '
        "'Y?([0-9]+)', 1) AS INTEGER)"
    )

    sql_tpl = """
    SELECT
      CAST("id" AS VARCHAR) AS patient_id,
      CAST("visit_id" AS VARCHAR) AS visit_id,
      CAST('inpatient' AS VARCHAR) AS visit_category,
      __ADMISSION_TIME__ AS admission_time,
      __DISCHARGE_TIME__ AS discharge_date,
      CASE WHEN CAST("医疗付费方式" AS VARCHAR) IN ('-','None','') THEN NULL
           ELSE CAST("医疗付费方式" AS VARCHAR) END AS payment_method,
      CASE WHEN CAST("年龄（岁）" AS VARCHAR) IN ('-','None','') THEN NULL
           ELSE __AGE_EXPR__ END AS visit_age,
      CASE WHEN CAST("入院诊断" AS VARCHAR) IN ('-','None','') THEN NULL
           ELSE CAST("入院诊断" AS VARCHAR) END AS admission_dept_raw,
      CASE WHEN CAST("实际住院天数" AS VARCHAR) IN ('-','None','') THEN NULL
           ELSE TRY_CAST(CAST("实际住院天数" AS VARCHAR) AS INTEGER) END AS length_of_stay,
      __JSON_COLS__
    FROM read_parquet('__SRC__')
    """
    return (
        sql_tpl
        .replace("__ADMISSION_TIME__", _iso_date_expr("入院时间"))
        .replace("__DISCHARGE_TIME__", _iso_date_expr("出院时间"))
        .replace("__AGE_EXPR__", age_expr)
        .replace("__JSON_COLS__", ",\n      ".join(json_lines))
        .replace("__SRC__", src_path)
    )


def _diag_sql(src_path: str) -> str:
    detail_struct = (
        "struct_pack(\n"
        f"        icd_external_code := {_clean_expr('损伤、中毒的外部原因编码')},\n"
        f"        icd_external_desc := {_clean_expr('损伤、中毒的外部原因')},\n"
        f"        stage_type := {_clean_expr('肿瘤分期类型')},\n"
        f"        stage_T := {_clean_expr('T')},\n"
        f"        stage_N := {_clean_expr('N')},\n"
        f"        stage_M := {_clean_expr('M')},\n"
        f"        stage_composite := {_clean_expr('分期')},\n"
        f"        differentiation := {_clean_expr('恶性肿瘤分化程度')},\n"
        f"        allergy_drugs := {_clean_expr('过敏药物')},\n"
        f"        blood_type_abo := {_clean_expr('血型')},\n"
        f"        blood_type_rh := {_clean_expr('Rh')},\n"
        '        total_cost := TRY_CAST(CAST("总费用" AS VARCHAR) AS DOUBLE),\n'
        '        self_pay := TRY_CAST(CAST("自付金额" AS VARCHAR) AS DOUBLE)\n'
        "      )"
    )

    sql_tpl = """
    WITH src AS (SELECT * FROM read_parquet('__SRC__'))
    SELECT
      CAST("id" AS VARCHAR) AS patient_id,
      CASE WHEN CAST("门急诊诊断" AS VARCHAR) IN ('-','None','') THEN NULL
           ELSE CAST("门急诊诊断" AS VARCHAR) END AS diagnosis_name,
      CASE WHEN CAST("门急诊诊断-疾病编码" AS VARCHAR) IN ('-','None','') THEN NULL
           ELSE CAST("门急诊诊断-疾病编码" AS VARCHAR) END AS diagnosis_code,
      CAST('outpatient' AS VARCHAR) AS diagnosis_category,
      __ADMISSION_TIME__ AS diagnosis_date,
      CAST('Y' AS VARCHAR) AS is_primary,
      __DETAIL_STRUCT__ AS detail
    FROM src
    UNION ALL
    SELECT
      CAST("id" AS VARCHAR),
      CASE WHEN CAST("入院诊断" AS VARCHAR) IN ('-','None','') THEN NULL
           ELSE CAST("入院诊断" AS VARCHAR) END,
      CASE WHEN CAST("门急诊诊断-疾病编码" AS VARCHAR) IN ('-','None','') THEN NULL
           ELSE CAST("门急诊诊断-疾病编码" AS VARCHAR) END,
      CAST('admission' AS VARCHAR),
      __ADMISSION_TIME__,
      CAST('Y' AS VARCHAR),
      __DETAIL_STRUCT__
    FROM src
    """
    return (
        sql_tpl
        .replace("__SRC__", src_path)
        .replace("__ADMISSION_TIME__", _iso_date_expr("入院时间"))
        .replace("__DETAIL_STRUCT__", detail_struct)
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=DEFAULT_SRC)
    ap.add_argument("--out-dir", default=DEFAULT_OUT)
    args = ap.parse_args()

    src = Path(args.src)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    visit_path = out / "face_sheet_visit.parquet"
    diag_path = out / "face_sheet_diagnosis.parquet"

    con = duckdb.connect()

    print(f"[ETL1] 写 visit staging → {visit_path}")
    sql_visit = _visit_sql(str(src))
    con.execute(f"COPY ({sql_visit}) TO '{visit_path}' (FORMAT PARQUET)")
    n_visit = con.execute(
        f"SELECT COUNT(*) FROM read_parquet('{visit_path}')"
    ).fetchone()[0]
    print(f"[ETL1] visit staging rows: {n_visit}")

    print(f"[ETL1] 写 diagnosis staging → {diag_path}")
    sql_diag = _diag_sql(str(src))
    con.execute(f"COPY ({sql_diag}) TO '{diag_path}' (FORMAT PARQUET)")
    n_diag = con.execute(
        f"SELECT COUNT(*) FROM read_parquet('{diag_path}')"
    ).fetchone()[0]
    print(f"[ETL1] diagnosis staging rows: {n_diag}")

    hashes = []
    for _ in range(3):
        con.execute(f"COPY ({sql_visit}) TO '{visit_path}' (FORMAT PARQUET)")
        hashes.append(_content_md5(visit_path))
    print(f"[ETL1] visit 3 次内容哈希: {hashes}")
    if len(set(hashes)) != 1:
        raise RuntimeError(f"内容哈希不一致：{hashes}")
    print("[ETL1] visit 哈希一致 ✓")

    print("\n[ETL1] visit 抽样 3 行：")
    df = con.execute(
        f"SELECT patient_id, visit_id, admission_time, discharge_date, "
        f"payment_method, visit_age, length_of_stay "
        f"FROM read_parquet('{visit_path}') LIMIT 3"
    ).fetch_df()
    print(df.to_string())
    print("\n[ETL1] diagnosis 抽样 2 行（首个 patient）：")
    df = con.execute(
        f"SELECT patient_id, diagnosis_name, diagnosis_code, "
        f"diagnosis_category, diagnosis_date, is_primary "
        f"FROM read_parquet('{diag_path}') "
        f"WHERE patient_id = (SELECT patient_id FROM read_parquet('{diag_path}') LIMIT 1)"
    ).fetch_df()
    print(df.to_string())

    print("\n[ETL1] DONE")


if __name__ == "__main__":
    main()
