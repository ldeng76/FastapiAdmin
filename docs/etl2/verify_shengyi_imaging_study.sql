-- =====================================================================
-- 验证脚本：shengyi CT影像（含报告）灌库结果
-- 用法：PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres \
--       -f docs/etl2/verify_shengyi_imaging_study.sql
-- 期望：
--   shengyi_patients    = 169,820
--   shengyi_imaging     =  82,153
--   unique_studies      =  82,153
--   disk_06_rows        =  52,340
--   disk_07_rows        =  29,813
--   cross_disk_dup_pids =       0
--   bad_pt_id_count     =       0
--   bad_anon_id_count   =       0
--   missing_image_files = 待确认（disk scan），不应为 0
-- =====================================================================

\echo '--- shengyi CT影像 灌库核验 ---'

\echo ''
\echo '1. patient 总数（shengyi）'
SELECT COUNT(*) AS shengyi_patients
FROM lnrs.lnrs_anon_patient
WHERE center_code = 'shengyi' AND deleted_at IS NULL;

\echo ''
\echo '2. imaging_study 总数（shengyi）+ unique dicom_study_uid'
SELECT
    COUNT(*)                                  AS shengyi_imaging,
    COUNT(DISTINCT dicom_study_uid)           AS unique_studies,
    COUNT(DISTINCT patient_id)                AS unique_patients_in_imaging
FROM lnrs.lnrs_anon_imaging_study
WHERE center_code = 'shengyi';

\echo ''
\echo '3. 按 source 拆分'
SELECT
    source,
    COUNT(*) AS rows,
    COUNT(DISTINCT dicom_study_uid) AS unique_studies
FROM lnrs.lnrs_anon_imaging_study
WHERE center_code = 'shengyi'
GROUP BY source
ORDER BY source;

\echo ''
\echo '4. 跨盘 patient_id 重叠检查（应为 0）'
SELECT COUNT(*) AS cross_disk_dup_pids
FROM (
    SELECT patient_id FROM lnrs.lnrs_anon_imaging_study
     WHERE center_code = 'shengyi' AND source = 'disk_06_shengyi'
    INTERSECT
    SELECT patient_id FROM lnrs.lnrs_anon_imaging_study
     WHERE center_code = 'shengyi' AND source = 'disk_07_shengyi'
) t;

\echo ''
\echo '5. patient_id 格式检查（应全为 PT_<8位>）'
SELECT COUNT(*) AS bad_pt_id_count
FROM lnrs.lnrs_anon_patient
WHERE center_code = 'shengyi'
  AND patient_id !~ '^PT_[0-9]{8}$';

\echo ''
\echo '6. anon_id 格式检查（应全为 ANON_<12hex>）'
SELECT COUNT(*) AS bad_anon_id_count
FROM lnrs.lnrs_anon_patient
WHERE center_code = 'shengyi'
  AND anon_id !~ '^ANON_[0-9a-f]{12}$';

\echo ''
\echo '7. imaging_study 与 patient FK 一致性（imagin FK → patient 应全部命中）'
SELECT COUNT(*) AS orphan_imaging
FROM lnrs.lnrs_anon_imaging_study s
LEFT JOIN lnrs.lnrs_anon_patient p
  ON p.patient_id = s.patient_id AND p.deleted_at IS NULL
WHERE s.center_code = 'shengyi' AND p.patient_id IS NULL;

\echo ''
\echo '8. modality / center_code 分布'
SELECT center_code, modality, COUNT(*) AS rows
FROM lnrs.lnrs_anon_imaging_study
WHERE center_code = 'shengyi'
GROUP BY center_code, modality
ORDER BY center_code, modality;

\echo ''
\echo '--- 核验结束 ---'