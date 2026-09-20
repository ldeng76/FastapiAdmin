-- =====================================================================
-- Issue 8 — zhujiang 零文件 study 处置 验收 SQL（方案 c 视图层过滤）
-- 调研报告：docs/etl2/verify_result/zhujiang_empty_studies_20260920.md
-- 迁移：backend/sql/postgres/0026-imaging-study-counts-filter-zero-sop.sql
--
-- 用法：PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres \
--          -f docs/etl2/verify_issue8_zhujiang_empty_studies.sql
--
-- 验收标准（与 issue-8 §Acceptance criteria 对应）：
--   A1. B 子集陈旧计数修复（sop_count=0 ↔ file_count=0 一致性）→ 当前 B=0 自然满足
--   A2. 视图过滤守卫对 A 子集生效（zero-sop study 不出现在视图中）
--   A3. sop_count>0 的 study 完全不受影响
--   A4. 不修改 lnrs_anon_imaging_study 数据
-- =====================================================================

\pset pager off

\echo '=== A1. B 子集陈旧计数一致性 (PRD §修复后一致性断言) ==='
\echo '期望返回 0: zhujiang 中心 (sop_count=0) <> (ds.file_count=0) 应无错位'
SELECT COUNT(*) AS mismatches
FROM lnrs.lnrs_anon_imaging_study s
JOIN lnrs.lnrs_anon_dicom_series ds ON ds.dicom_study_uid = s.dicom_study_uid
WHERE s.center_code = 'zhujiang'
  AND (s.sop_count = 0) <> (ds.file_count = 0);

\echo ''
\echo '=== A2. 视图过滤守卫对 A 子集生效 (方案 c 关键验收) ==='
\echo '期望: zhujiang 在视图中的行数 = 86,512 = 86,927 - 415（A 子集）'
SELECT center_code, COUNT(*) AS view_rows
FROM lnrs.lnrs_anon_v_imaging_study_counts
WHERE center_code = 'zhujiang'
GROUP BY center_code;

\echo ''
\echo '=== A3. sop_count>0 的 study 行为不变 (回归断言) ==='
\echo '期望: 视图里 zhujiang sop_count>0 的 study 数 = 86,512（等于 imaging_study 的非零 sop 行数）'
WITH src AS (
    SELECT COUNT(*) AS nonzero_sop_studies
    FROM lnrs.lnrs_anon_imaging_study
    WHERE center_code='zhujiang' AND sop_count > 0
),
view_ct AS (
    SELECT COUNT(*) AS view_nonzero_sop
    FROM lnrs.lnrs_anon_v_imaging_study_counts v
    JOIN lnrs.lnrs_anon_imaging_study s ON s.study_key = v.study_key
    WHERE s.center_code='zhujiang' AND s.sop_count > 0
)
SELECT src.nonzero_sop_studies AS imaging_study_nonzero_sop,
       view_ct.view_nonzero_sop AS view_nonzero_sop,
       CASE WHEN src.nonzero_sop_studies = view_ct.view_nonzero_sop THEN 'OK' ELSE 'FAIL' END AS verdict
FROM src, view_ct;

\echo ''
\echo '=== A4. 不修改 imaging_study 数据 (回归断言) ==='
\echo '期望: imaging_study 行数与 zero-sop 行数完全不变（与调研基线一致）'
SELECT
    COUNT(*) AS total_studies,
    COUNT(*) FILTER (WHERE sop_count = 0) AS zero_sop_studies,
    COUNT(*) FILTER (WHERE sop_count > 0) AS nonzero_sop_studies
FROM lnrs.lnrs_anon_imaging_study
WHERE center_code='zhujiang';

\echo ''
\echo '=== 附: 视图全量（多中心）行数对照 ==='
SELECT center_code, COUNT(*) AS view_rows
FROM lnrs.lnrs_anon_v_imaging_study_counts
GROUP BY center_code
ORDER BY center_code;
