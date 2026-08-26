-- 01_patient.sql
-- 珠江-新桥 patient 表
-- Source: 5万例时序影像_带病理_新_1.csv (10,000 行) → DISTINCT patient_id
-- Schema 字段 (unified, Zhujiang side):
--   patient_id, source_center, gender, birth_date, ethnicity, native_place,
--   abo_blood_type, rh_blood_type, smoking_status, first_nodule_date
--   demographics (json), medical_history (json)
INSTALL spatial; LOAD spatial;

COPY (
  WITH src AS (
    SELECT *
    FROM read_csv(
      '/data/wlx/DATABASE/0605_small/01disk/_字段与原始数据/5万例时序影像_带病理_新_1.csv',
      header=true, delim=',', quote='"', escape='"',
      null_padding=true, ignore_errors=true, sample_size=-1
    )
    WHERE "检查报告.患者ID" IS NOT NULL
  ),
  dedup AS (
    SELECT DISTINCT ON ("检查报告.患者ID")
      "检查报告.患者ID"                                     AS patient_id_raw,
      "patients.性别"                                       AS gender_raw,
      "patients.出生日期"                                   AS birth_date_raw
    FROM src
  )
  SELECT
    CAST(patient_id_raw AS VARCHAR)                          AS patient_id,
    CAST('珠江' AS VARCHAR)                                 AS source_center,
    CASE
      WHEN gender_raw = '男' THEN '男'::VARCHAR
      WHEN gender_raw = '女' THEN '女'::VARCHAR
      ELSE NULL
    END                                                      AS gender,
    TRY_CAST(
      substr(CAST(birth_date_raw AS VARCHAR), 1, 10) AS DATE
    )                                                        AS birth_date,
    CAST(NULL AS VARCHAR)                                    AS ethnicity,
    CAST(NULL AS VARCHAR)                                    AS native_place,
    CAST(NULL AS VARCHAR)                                    AS abo_blood_type,
    CAST(NULL AS VARCHAR)                                    AS rh_blood_type,
    CAST(NULL AS VARCHAR)                                    AS smoking_status,
    CAST(NULL AS DATE)                                       AS first_nodule_date,
    to_json({'bmi': NULL})                                   AS demographics,
    to_json({
      'smoking_pack_years':        NULL,
      'family_lung_cancer':        NULL,
      'family_other_cancer':       NULL,
      'family_other_cancer_type':  '',
      'prior_malignancy':          NULL,
      'comorbid_copd':             NULL,
      'comorbid_old_tb':           NULL,
      'discovery_route':           NULL
    })                                                        AS medical_history
  FROM dedup
) TO '/data/wlx/DATABASE/0605_small/01disk/zhujiang_xinqiao_parquet/patient.parquet'
  (FORMAT PARQUET, COMPRESSION 'zstd', ROW_GROUP_SIZE 100000);
