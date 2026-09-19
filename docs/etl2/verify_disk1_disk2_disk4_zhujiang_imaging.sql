-- =====================================================================
-- 珠江 CT 三盘（disk1+disk2+disk4）导入验证 SQL（V1-V10）
-- 2026-09-19
-- 期望规模（实测基线）：
--   patient_zhujiang            61,392（含本批 dicom_dir 60,385 + pre-existing csv_report 1,007）
--   imaging_study zhujiang      86,927
--   imaging_study by source: disk1=26,940 / disk2=19,417 / disk4=40,570
--   dicom_series zhujiang        86,203（= 去重 StudyUID；UNIQUE 键 dicom_study_uid 单列；跨盘 724 UID 只一行）
--   phi_audit (本次 dicom_dir batch) 86,927
--   byte_size > 0               85,929
--   series_count NOT NULL        0（按设计：B 方案等 exam 灌库）
-- 使用：psql -h 127.0.0.1 -U lnrs -d postgres -f verify_disk1_disk2_disk4_zhujiang_imaging.sql
-- =====================================================================

-- ----- V1: zhujiang patient 数 -----
SELECT 'V1 patient_zhujiang' AS check_name,
       COUNT(*)                AS actual,
       61392                   AS expected,
       CASE WHEN COUNT(*) BETWEEN 61000 AND 62000 THEN 'OK' ELSE '❌' END AS flag
FROM lnrs.lnrs_anon_patient
WHERE center_code = 'zhujiang' AND deleted_at IS NULL;

-- ----- V2: imaging_study zhujiang by source -----
SELECT 'V2 imaging_study' AS check_name, source, COUNT(*) AS actual,
       CASE source
         WHEN 'disk1_zhujiang' THEN 26940
         WHEN 'disk2_zhujiang_supplement' THEN 19417
         WHEN 'disk4_zhujiang' THEN 40570
       END AS expected,
       CASE WHEN
         CASE source
           WHEN 'disk1_zhujiang' THEN COUNT(*) BETWEEN 26500 AND 27500
           WHEN 'disk2_zhujiang_supplement' THEN COUNT(*) BETWEEN 19000 AND 20000
           WHEN 'disk4_zhujiang' THEN COUNT(*) BETWEEN 40000 AND 41000
           ELSE FALSE
         END
       THEN 'OK' ELSE '❌' END AS flag
FROM lnrs.lnrs_anon_imaging_study
WHERE source IN ('disk1_zhujiang','disk2_zhujiang_supplement','disk4_zhujiang')
GROUP BY source
ORDER BY source;

-- ----- V3: dicom_series zhujiang（按去重 StudyUID；UNIQUE 键 dicom_study_uid 单列） -----
-- dicom_series 全表 = zhujiang(去重) + shengyi(82,057) + 其他
-- 我们只校验 zhujiang 部分：通过 imaging_study 的 dicom_study_uid 反查
SELECT 'V3 dicom_series_zhujiang' AS check_name,
       COUNT(*) AS actual,
       86203    AS expected,
       CASE WHEN COUNT(*) BETWEEN 86000 AND 86500 THEN 'OK' ELSE '❌' END AS flag
FROM lnrs.lnrs_anon_dicom_series ds
WHERE EXISTS (
    SELECT 1 FROM lnrs.lnrs_anon_imaging_study s
    WHERE s.dicom_study_uid = ds.dicom_study_uid
      AND s.source IN ('disk1_zhujiang','disk2_zhujiang_supplement','disk4_zhujiang')
);

-- ----- V4: imaging_study 无 anon_exam_id（B 方案：本批 exam 表空，anon_exam_id 全空） -----
SELECT 'V4 study_without_exam' AS check_name,
       COUNT(*) AS actual,
       86927   AS expected,
       CASE WHEN COUNT(*) BETWEEN 86000 AND 88000 THEN 'OK' ELSE '❌' END AS flag
FROM lnrs.lnrs_anon_imaging_study
WHERE source IN ('disk1_zhujiang','disk2_zhujiang_supplement','disk4_zhujiang')
  AND anon_exam_id IS NULL;

-- ----- V5: phi_audit rows for the most recent zhujiang dicom_dir batch -----
WITH latest_batch AS (
    SELECT batch_id FROM lnrs.lnrs_anon_ingest_batch
    WHERE center_code = 'zhujiang' AND source_kind = 'dicom_dir'
    ORDER BY started_at DESC LIMIT 1
)
SELECT 'V5 phi_audit_latest_zhujiang_batch' AS check_name,
       COUNT(*) AS actual,
       86927   AS expected,
       CASE WHEN COUNT(*) BETWEEN 86000 AND 88000 THEN 'OK' ELSE '❌' END AS flag
FROM lnrs.lnrs_anon_phi_audit a
JOIN latest_batch b ON a.batch_id = b.batch_id;

-- ----- V6: phi_audit strategy 全部 'hmac'（同一 batch） -----
WITH latest_batch AS (
    SELECT batch_id FROM lnrs.lnrs_anon_ingest_batch
    WHERE center_code = 'zhujiang' AND source_kind = 'dicom_dir'
    ORDER BY started_at DESC LIMIT 1
)
SELECT 'V6 phi_audit_strategy_hmac' AS check_name,
       strategy, COUNT(*)
FROM lnrs.lnrs_anon_phi_audit a
JOIN latest_batch b ON a.batch_id = b.batch_id
GROUP BY strategy
ORDER BY strategy;

-- ----- V7: dicom_series nonzero byte_size for zhujiang -----
SELECT 'V7 dicom_series_nonzero_bytes' AS check_name,
       COUNT(*) FILTER (WHERE byte_size > 0)  AS nonzero_count,
       COUNT(*) FILTER (WHERE file_count > 0) AS nonzero_files,
       COUNT(*) AS total_zhujiang_series
FROM lnrs.lnrs_anon_dicom_series ds
WHERE EXISTS (
    SELECT 1 FROM lnrs.lnrs_anon_imaging_study s
    WHERE s.dicom_study_uid = ds.dicom_study_uid
      AND s.source IN ('disk1_zhujiang','disk2_zhujiang_supplement','disk4_zhujiang')
);

-- ----- V8: dicom_series series_count NOT NULL（B 方案：全 NULL，等 exam 灌库后回填） -----
SELECT 'V8 series_count_filled' AS check_name,
       COUNT(*) FILTER (WHERE series_count IS NOT NULL) AS filled,
       COUNT(*) FILTER (WHERE series_count IS NULL)     AS null_count,
       COUNT(*) AS total_zhujiang_series
FROM lnrs.lnrs_anon_dicom_series ds
WHERE EXISTS (
    SELECT 1 FROM lnrs.lnrs_anon_imaging_study s
    WHERE s.dicom_study_uid = ds.dicom_study_uid
      AND s.source IN ('disk1_zhujiang','disk2_zhujiang_supplement','disk4_zhujiang')
);

-- ----- V9: created_batch_id 一致性（imaging_study 全部指向 latest zhujiang dicom_dir batch） -----
WITH latest_batch AS (
    SELECT batch_id FROM lnrs.lnrs_anon_ingest_batch
    WHERE center_code = 'zhujiang' AND source_kind = 'dicom_dir'
    ORDER BY started_at DESC LIMIT 1
)
SELECT 'V9 imaging_batch_consistency' AS check_name,
       COUNT(*) FILTER (WHERE s.created_batch_id = b.batch_id) AS matched,
       COUNT(*) FILTER (WHERE s.created_batch_id IS NULL)      AS null_batch,
       COUNT(*) AS total
FROM lnrs.lnrs_anon_imaging_study s
CROSS JOIN latest_batch b
WHERE s.source IN ('disk1_zhujiang','disk2_zhujiang_supplement','disk4_zhujiang');

-- ----- V10: cross-disk duplicate UID 检测（成像层两行；dicom_series 一行） -----
SELECT 'V10 cross_disk_dup_uid' AS check_name,
       COUNT(*) AS dup_study_count,
       COUNT(*) FILTER (WHERE source_count > 1) AS multi_source_uids
FROM (
    SELECT dicom_study_uid, COUNT(DISTINCT source) AS source_count
    FROM lnrs.lnrs_anon_imaging_study
    WHERE source IN ('disk1_zhujiang','disk2_zhujiang_supplement','disk4_zhujiang')
    GROUP BY dicom_study_uid
    HAVING COUNT(DISTINCT source) > 1
) t;

-- ----- 附: batch summary -----
SELECT '--- latest zhujiang batches ---' AS info;
SELECT batch_id, center_code, source_kind, source_locator,
       status, started_at, finished_at, row_counts
FROM lnrs.lnrs_anon_ingest_batch
WHERE center_code = 'zhujiang'
ORDER BY started_at DESC LIMIT 5;