-- 04_nodule_imaging.sql
-- 珠江-新桥 nodule_imaging 表 (Zhujiang-Xinqiao 独有)
-- Sources:
--   a) CT与病理数据.xlsx (11 列 × 202,619 行) — EXAM_NO, PAT_LOCAL_ID, SICK_ID, NAME,
--      SEX, AGE, EXAM_CLASS, DESCRIPTION, IMPRESSION, EXAM_DATE, [K col]
--   b) 5万例时序影像_带病理_新_1.csv 检查报告部分
-- 缺失字段 (nodule_no/location/long_diameter/density_type) 全部 NULL,
-- 原文 (DESCRIPTION/IMPRESSION) 存到 exam_meta JSON 供后续 NLP
INSTALL spatial; LOAD spatial;

COPY (
  WITH xlsx AS (
    SELECT
      CAST(EXAM_NO AS VARCHAR)                               AS exam_id,
      CAST(PAT_LOCAL_ID AS VARCHAR)                          AS patient_id,
      TRY_CAST(EXAM_DATE AS DATE)                            AS exam_date,
      CASE
        WHEN EXAM_CLASS LIKE '%CT%'  THEN 'CT'
        WHEN EXAM_CLASS LIKE '%PET%' THEN 'PET-CT'
        WHEN EXAM_CLASS LIKE '%MR%'  THEN 'MRI'
        ELSE CAST(EXAM_CLASS AS VARCHAR)
      END                                                    AS exam_type,
      CAST(NULL AS VARCHAR)                                  AS nodule_no,
      CAST(NULL AS VARCHAR)                                  AS nodule_location,
      CAST(NULL AS DOUBLE)                                   AS long_diameter,
      CAST(NULL AS VARCHAR)                                  AS density_type,
      to_json({
        'report_date':         CAST(EXAM_DATE AS VARCHAR),
        'exam_name':           '胸部CT',
        'contrast':            NULL,
        'slice_thickness_mm':  NULL,
        'description':         DESCRIPTION,
        'impression':          IMPRESSION,
        'source':              'CT与病理数据.xlsx'
      })                                                      AS exam_meta,
      CAST(NULL AS JSON)                                     AS nodule_morphology,
      CAST(NULL AS JSON)                                     AS nodule_quantitative,
      CAST(NULL AS JSON)                                     AS follow_up_comparison
    FROM st_read(
      '/data/wlx/DATABASE/0605_small/01disk/_字段与原始数据/CT与病理数据.xlsx'
    )
    WHERE EXAM_NO IS NOT NULL
  ),
  csv_src AS (
    SELECT
      CAST("检查报告.报告中图像编号" AS VARCHAR)             AS exam_id,
      CAST("检查报告.患者ID" AS VARCHAR)                     AS patient_id,
      TRY_CAST("检查报告.检查日期时间" AS TIMESTAMP)         AS exam_date,
      CAST("检查报告.检查类别" AS VARCHAR)                   AS exam_type,
      CAST(NULL AS VARCHAR)                                  AS nodule_no,
      CAST(NULL AS VARCHAR)                                  AS nodule_location,
      CAST(NULL AS DOUBLE)                                   AS long_diameter,
      CAST(NULL AS VARCHAR)                                  AS density_type,
      to_json({
        'report_date':         CAST("检查报告.报告日期及时间" AS VARCHAR),
        'exam_name':           "检查报告.检查名称",
        'contrast':            NULL,
        'slice_thickness_mm':  NULL,
        'description':         "检查报告.检查所见",
        'impression':          "检查报告.检查结论",
        'source':              '5万例时序影像_带病理_新_1.csv'
      })                                                      AS exam_meta,
      CAST(NULL AS JSON)                                     AS nodule_morphology,
      CAST(NULL AS JSON)                                     AS nodule_quantitative,
      CAST(NULL AS JSON)                                     AS follow_up_comparison
    FROM read_csv(
      '/data/wlx/DATABASE/0605_small/01disk/_字段与原始数据/5万例时序影像_带病理_新_1.csv',
      header=true, delim=',', quote='"', escape='"',
      null_padding=true, ignore_errors=true, sample_size=-1
    )
    WHERE "检查报告.患者ID" IS NOT NULL
      AND "检查报告.报告中图像编号" IS NOT NULL
  )
  SELECT * FROM xlsx
  UNION ALL
  SELECT * FROM csv_src
) TO '/data/wlx/DATABASE/0605_small/01disk/zhujiang_xinqiao_parquet/nodule_imaging.parquet'
  (FORMAT PARQUET, COMPRESSION 'zstd', ROW_GROUP_SIZE 100000);
