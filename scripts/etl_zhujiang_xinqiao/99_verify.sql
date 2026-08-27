-- 99_verify.sql
-- 转换结束后的验证查询

.print === Row counts ===
SELECT 'patient'              AS tbl, count(*) AS n FROM '/data/wlx/DATABASE/0605_small/01disk/zhujiang_xinqiao_parquet/patient.parquet'
UNION ALL SELECT 'pathology_specimen', count(*) FROM '/data/wlx/DATABASE/0605_small/01disk/zhujiang_xinqiao_parquet/pathology_specimen.parquet'
UNION ALL SELECT 'surgery_record',     count(*) FROM '/data/wlx/DATABASE/0605_small/01disk/zhujiang_xinqiao_parquet/surgery_record.parquet'
UNION ALL SELECT 'nodule_imaging',      count(*) FROM '/data/wlx/DATABASE/0605_small/01disk/zhujiang_xinqiao_parquet/nodule_imaging.parquet'
UNION ALL SELECT 'genetic_test',        count(*) FROM '/data/wlx/DATABASE/0605_small/01disk/zhujiang_xinqiao_parquet/genetic_test.parquet'
UNION ALL SELECT 'ihc_result',          count(*) FROM '/data/wlx/DATABASE/0605_small/01disk/zhujiang_xinqiao_parquet/ihc_result.parquet'
UNION ALL SELECT 'follow_up',           count(*) FROM '/data/wlx/DATABASE/0605_small/01disk/zhujiang_xinqiao_parquet/follow_up.parquet'
ORDER BY tbl;

.print === Sanity checks ===
-- (1) patient_id 非空
SELECT 'empty_patient_id' AS check_name, count(*) AS n
FROM '/data/wlx/DATABASE/0605_small/01disk/zhujiang_xinqiao_parquet/patient.parquet'
WHERE patient_id IS NULL OR patient_id = '';

-- (2) surgery_record 可解析日期
SELECT 'null_surgery_date' AS check_name, count(*) AS n
FROM '/data/wlx/DATABASE/0605_small/01disk/zhujiang_xinqiao_parquet/surgery_record.parquet'
WHERE surgery_date IS NULL;

-- (3) nodule_imaging JSON 可解析
SELECT 'bad_json_exam_meta' AS check_name, count(*) AS n
FROM '/data/wlx/DATABASE/0605_small/01disk/zhujiang_xinqiao_parquet/nodule_imaging.parquet'
WHERE TRY_CAST(exam_meta AS JSON) IS NULL;

-- (4) pathology 中文 spot check (diagnosis 实际在 exam_meta.microscopic_findings)
SELECT 'zh_pathology_microscopic' AS check_name, count(*) AS n
FROM '/data/wlx/DATABASE/0605_small/01disk/zhujiang_xinqiao_parquet/pathology_specimen.parquet'
WHERE json_extract_string(exam_meta, '$.microscopic_findings') LIKE '%腺癌%';

.print === Sample rows ===
-- (5) surgery_record 抽样
SELECT patient_id, surgery_date, procedure_name,
       json_extract_string(procedure_detail, '$.icd9cm3_code') AS icd9,
       json_extract_string(procedure_detail, '$.surgeon')        AS surgeon
FROM '/data/wlx/DATABASE/0605_small/01disk/zhujiang_xinqiao_parquet/surgery_record.parquet'
LIMIT 3;

-- (6) nodule_imaging 抽样
SELECT patient_id, exam_id, exam_type, exam_date,
       json_extract_string(exam_meta, '$.impression')  AS impression
FROM '/data/wlx/DATABASE/0605_small/01disk/zhujiang_xinqiao_parquet/nodule_imaging.parquet'
LIMIT 3;

-- (7) pathology_specimen 抽样
SELECT patient_id, specimen_id, submission_date, sampling_site, pathology_diagnosis
FROM '/data/wlx/DATABASE/0605_small/01disk/zhujiang_xinqiao_parquet/pathology_specimen.parquet'
LIMIT 3;
