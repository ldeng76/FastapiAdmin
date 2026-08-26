-- 02_pathology_specimen.sql
-- 珠江-新桥 pathology_specimen 表 (unified, Zhujiang side)
-- Source: 5万例时序影像_带病理_新_1.csv (病理部分,2258 个 unique 病理系统编号)
-- Schema 字段 (Zhujiang):
--   patient_id, visit_id (null), specimen_id, submission_date, report_date,
--   specimen_type, sampling_site, histology_class, pathology_diagnosis,
--   tumor_total_size_mm
--   specimen_meta / adenocarcinoma_subtypes / tumor_measurement /
--   high_risk_factors / staging (json)
INSTALL spatial; LOAD spatial;

COPY (
  WITH src AS (
    SELECT *
    FROM read_csv(
      '/data/wlx/DATABASE/0605_small/01disk/_字段与原始数据/5万例时序影像_带病理_新_1.csv',
      header=true, delim=',', quote='"', escape='"',
      null_padding=true, ignore_errors=true, sample_size=-1
    )
    WHERE "病理.病理系统编号" IS NOT NULL
      AND "病理.病理系统编号" <> ''
  ),
  -- 病理时间字段可能为 "2025-03-08 08:45:42,2025-03-08 08:46:30"
  -- 取首项 (冰冻标本)
  cleaned AS (
    SELECT
      CAST("病理.患者ID" AS VARCHAR)                         AS patient_id,
      CAST("病理.病理系统编号" AS VARCHAR)                   AS specimen_id,
      CAST("病理.送检时间" AS VARCHAR)                       AS submission_ts,
      CAST("病理.报告时间" AS VARCHAR)                       AS report_ts,
      CAST("病理.送检部位" AS VARCHAR)                       AS sampling_site,
      CAST("病理.病理诊断" AS VARCHAR)                       AS pathology_diagnosis,
      CAST("病理.病理所见-肉眼所见" AS VARCHAR)              AS gross_findings,
      CAST("病理.病理所见-镜下所见" AS VARCHAR)              AS microscopic_findings,
      CAST("病理.送检科室" AS VARCHAR)                       AS dept_name,
      CAST("病理.报告状态" AS VARCHAR)                       AS report_status
    FROM src
  ),
  first_date AS (
    SELECT
      *,
      TRY_CAST(
        substr(
          regexp_replace(submission_ts, '^([^,]+).*', '\1'),
          1, 10
        ) AS DATE
      )                                                      AS submission_date,
      TRY_CAST(
        substr(
          regexp_replace(report_ts, '^([^,]+).*', '\1'),
          1, 10
        ) AS DATE
      )                                                      AS report_date
    FROM cleaned
  )
  SELECT
    patient_id,
    CAST(NULL AS VARCHAR)                                    AS visit_id,
    specimen_id,
    submission_date,
    report_date,
    CAST(NULL AS VARCHAR)                                    AS specimen_type,
    sampling_site,
    CAST(NULL AS VARCHAR)                                    AS histology_class,
    -- 源数据中 病理.病理诊断 经常是 "," 占位(诊断其实在镜下所见 free-text)
    -- 清洗: 去掉纯逗号/空字符串
    NULLIF(NULLIF(TRIM(pathology_diagnosis), ''), ',')       AS pathology_diagnosis,
    CAST(NULL AS DOUBLE)                                     AS tumor_total_size_mm,
    to_json({
      'frozen':                  CASE
                                  WHEN dept_name LIKE '%冰冻%' THEN '冰冻'
                                  ELSE '石蜡'
                                END,
      'paired_specimen_id':      '',
      'multi_nodule_same_report': false
    })                                                        AS specimen_meta,
    -- 腺癌亚型 / 测量 / 高危 / 分期: 未结构化,保留为 NULL
    CAST(NULL AS JSON)                                       AS adenocarcinoma_subtypes,
    CAST(NULL AS JSON)                                       AS tumor_measurement,
    CAST(NULL AS JSON)                                       AS high_risk_factors,
    CAST(NULL AS JSON)                                       AS staging,
    -- 原始 free-text 存到 exam_meta 供后续 NLP
    to_json({
      'request_id':            '',
      'gross_findings':        gross_findings,
      'microscopic_findings':  microscopic_findings,
      'immunohistochemistry':  '',
      'exam_method':           '',
      'special_markers':       '',
      'remarks':               ''
    })                                                        AS exam_meta
  FROM first_date
) TO '/data/wlx/DATABASE/0605_small/01disk/zhujiang_xinqiao_parquet/pathology_specimen.parquet'
  (FORMAT PARQUET, COMPRESSION 'zstd', ROW_GROUP_SIZE 100000);
