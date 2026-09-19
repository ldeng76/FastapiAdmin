-- 新桥 CT 影像导入验证（h196_3 / lnrs）
-- 用法：PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres -f docs/etl2/verify_xinqiao_imaging.sql
-- 期望值来源：2026-09-20 实测（见 docs/etl2/plan-xinqiao-3disk-import.md §1）
\pset pager off
\echo '=== V1  xinqiao patient 总数（期望 14,xxx） ==='
SELECT COUNT(*) AS patients_xinqiao
FROM lnrs.lnrs_anon_patient WHERE center_code = 'xinqiao';

\echo '=== V2  imaging_study 按 source 分布 ==='
SELECT source, COUNT(*) AS studies
FROM lnrs.lnrs_anon_imaging_study
WHERE center_code = 'xinqiao'
GROUP BY source ORDER BY source;

\echo '=== V3  imaging_study 总数 / 去重 StudyUID / 去重 patient ==='
SELECT COUNT(*) AS studies,
       COUNT(DISTINCT dicom_study_uid) AS distinct_uid,
       COUNT(DISTINCT patient_id)      AS distinct_patient
FROM lnrs.lnrs_anon_imaging_study WHERE center_code = 'xinqiao';

\echo '=== V4  dicom_series 覆盖（期望 = V3 distinct_uid） ==='
SELECT COUNT(*) AS series_rows
FROM lnrs.lnrs_anon_dicom_series ds
WHERE ds.dicom_study_uid IN (
    SELECT dicom_study_uid FROM lnrs.lnrs_anon_imaging_study WHERE center_code = 'xinqiao');

\echo '=== V5  dicom_series 字段填充（file_count>0 / byte_size>0 / series_count>0） ==='
SELECT COUNT(*) AS total,
       COUNT(*) FILTER (WHERE file_count > 0)   AS fc_positive,
       COUNT(*) FILTER (WHERE byte_size  > 0)   AS bs_positive,
       COUNT(*) FILTER (WHERE series_count > 0) AS sc_positive
FROM lnrs.lnrs_anon_dicom_series ds
WHERE ds.dicom_study_uid IN (
    SELECT dicom_study_uid FROM lnrs.lnrs_anon_imaging_study WHERE center_code = 'xinqiao');

\echo '=== V6  exam 关联（B 方案：期望 anon_exam_id 全 NULL） ==='
SELECT COUNT(*) AS studies,
       COUNT(*) FILTER (WHERE anon_exam_id IS NULL) AS exam_null
FROM lnrs.lnrs_anon_imaging_study WHERE center_code = 'xinqiao';

\echo '=== V7  phi_audit（本批 batch 行数 / strategy） ==='
SELECT b.batch_id, b.source_locator, b.status, COUNT(a.audit_id) AS audits
FROM lnrs.lnrs_anon_ingest_batch b
LEFT JOIN lnrs.lnrs_anon_phi_audit a ON a.batch_id = b.batch_id
WHERE b.center_code = 'xinqiao' AND b.source_kind = 'dicom_dir'
GROUP BY b.batch_id, b.source_locator, b.status ORDER BY b.source_locator;

\echo '=== V8  phi_audit strategy 分布 ==='
SELECT a.strategy, COUNT(*) AS n
FROM lnrs.lnrs_anon_phi_audit a
JOIN lnrs.lnrs_anon_ingest_batch b ON b.batch_id = a.batch_id
WHERE b.center_code = 'xinqiao' AND b.source_kind = 'dicom_dir'
GROUP BY a.strategy;

\echo '=== V9  created_batch_id 一致性（期望 0 行未挂 batch） ==='
SELECT COUNT(*) AS orphan_batch_refs
FROM lnrs.lnrs_anon_imaging_study s
WHERE s.center_code = 'xinqiao'
  AND s.created_batch_id IS NULL;

\echo '=== V10 跨 source 重复 StudyUID（期望 0） ==='
SELECT COUNT(*) AS uid_in_multi_source FROM (
  SELECT dicom_study_uid
  FROM lnrs.lnrs_anon_imaging_study WHERE center_code = 'xinqiao'
  GROUP BY dicom_study_uid HAVING COUNT(DISTINCT source) > 1
) t;

\echo '=== V11  patient 占位标记（期望 is_placeholder 全 TRUE） ==='
SELECT is_placeholder, COUNT(*) FROM lnrs.lnrs_anon_patient
WHERE center_code = 'xinqiao' GROUP BY is_placeholder;

\echo '=== V12  image_path 全部为绝对路径且在 03_disk/xinqiao 下（期望 bad=0） ==='
SELECT COUNT(*) AS bad_paths FROM lnrs.lnrs_anon_imaging_study
WHERE center_code = 'xinqiao'
  AND image_path NOT LIKE '/data/wlx/DATABASE/03_disk/xinqiao/%';

\echo '=== V13  modality 分布 ==='
SELECT modality, COUNT(*) FROM lnrs.lnrs_anon_imaging_study
WHERE center_code = 'xinqiao' GROUP BY modality ORDER BY 2 DESC;
