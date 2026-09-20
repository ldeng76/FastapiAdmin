-- =====================================================================
-- issue: 新桥 dicom_series.series_count / byte_size PACS 权威值校正（2026-09-20）
-- 数据源: /data/wlx/DATABASE/extracted_tables/xinqiao/ct_mapped.parquet
-- 脚本:   backend/etl2/backfill_xinqiao_series_counts_from_pacs.py
-- 备份表: lnrs.lnrs_anon_dicom_series_bak_20260920_191056（校正前 xinqiao 33,314 行快照）
-- 执行:   PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres -f 本文件
-- =====================================================================

-- V1 方向性断言：series_count 全部单调不减（PACS 值 ≥ 磁盘扫描实测；预期 0）
--    （「现值 == PACS 值」由脚本 apply 后的独立连接验收保证；read_parquet 仅 duckdb 可用）
SELECT 'V1_nonmonotonic' AS k, COUNT(*) AS v
FROM lnrs.lnrs_anon_dicom_series s
JOIN lnrs.lnrs_anon_dicom_series_bak_20260920_191056 b USING (dicom_study_uid)
WHERE s.series_count < b.series_count;

-- V2 页面口径现值（预期 33,314 / 4,359,981,928,899 / 143,609）
SELECT 'V2_xinqiao_now' AS k, COUNT(*) AS studies, SUM(s.byte_size) AS total_bytes,
       COUNT(*) + SUM(GREATEST(COALESCE(s.series_count,0)-1,0)) AS page_file_count
FROM lnrs.lnrs_anon_dicom_series s
JOIN lnrs.lnrs_anon_imaging_study i USING (dicom_study_uid)
WHERE i.center_code = 'xinqiao';

-- V3 校正前基线（备份表，预期 33,314 / 4,358,671,594,046 / 79,864）
SELECT 'V3_baseline_bak' AS k, COUNT(*) AS studies, SUM(byte_size) AS total_bytes,
       COUNT(*) + SUM(GREATEST(COALESCE(series_count,0)-1,0)) AS page_file_count
FROM lnrs.lnrs_anon_dicom_series_bak_20260920_191056;

-- V4 备份表与现表的差异行数 = 本次 UPDATE 行数（预期 19,239）
SELECT 'V4_updated_rows' AS k, COUNT(*) AS v
FROM lnrs.lnrs_anon_dicom_series s
JOIN lnrs.lnrs_anon_dicom_series_bak_20260920_191056 b USING (dicom_study_uid)
WHERE (s.series_count, s.byte_size) IS DISTINCT FROM (b.series_count, b.byte_size);

-- V5 zhujiang 零漂移（预期 86,927 / 20,487,229,514,795）
SELECT 'V5_zhujiang' AS k, COUNT(*) AS studies, SUM(s.byte_size) AS total_bytes
FROM lnrs.lnrs_anon_dicom_series s
JOIN lnrs.lnrs_anon_imaging_study i USING (dicom_study_uid)
WHERE i.center_code = 'zhujiang';

-- V6 shengyi 零漂移（预期 82,897 / 16,365,795,902,838）
SELECT 'V6_shengyi' AS k, COUNT(*) AS studies, SUM(s.byte_size) AS total_bytes
FROM lnrs.lnrs_anon_dicom_series s
JOIN lnrs.lnrs_anon_imaging_study i USING (dicom_study_uid)
WHERE i.center_code = 'shengyi';

-- V7 exam 侧对账存证：ct.parquet hash 与库内 exam 全对应（预期 124,045 / 0）
--    （duckdb 侧重算 sha256('xinqiao:'||exam_id) 与 DB hash 比对，见报告 §2）
SELECT 'V7_exam_rows' AS k, COUNT(*) AS v
FROM lnrs.lnrs_anon_exam WHERE center_code = 'xinqiao';
