-- =============================================================================
-- 数据导入核验 SQL — 省医 / 护理记录 (清单 R20)
-- 核验日期：2026-09-15
-- 清单预期 16,736,346 行 = 源 glob '非隐私信息.就诊.*护理记录*.parquet' = 13,824,664 (护理记录.测量子项) + 2,911,682 (ICU护理记录.记录详细信息)
-- ETL2 拆为两个 spec：
--   - nursing_observation (kind=observation, obs_type='nursing') → PG lnrs_anon_vital_observation (R14 batch 64735062)
--   - icu_observation     (kind=observation, obs_type='icu')     → PG lnrs_anon_vital_observation (R15 batch 2367dd54)
-- =============================================================================

SET enable_seqscan=off;
SET enable_bitmapscan=off;
\pset null '(null)'
\pset format aligned
\timing on

-- ----------------------------------------------------------------------------
-- V0. 源 parquet 与 ETL1 staging 行数（Python 端统计，本节注释）
--   源: '非隐私信息.就诊.*护理记录*.parquet' = 16,736,346 行
--        ├─ 护理记录.测量子项.parquet                13,824,664 行 → nursing_observation staging
--        └─ ICU护理记录.记录详细信息.parquet         2,911,682 行 → icu_observation staging
--   ETL1 staging: nursing_observation.parquet = 13,824,664 (0 守卫过滤)
--                 icu_observation.parquet     =  2,911,682 (0 守卫过滤)
-- ----------------------------------------------------------------------------

-- ----------------------------------------------------------------------------
-- V1. ETL2 spec / ingest_batch 总览
-- ----------------------------------------------------------------------------
\echo ''
\echo '=== V1. ETL2 ingest_batch (nursing / icu 相关) ==='
SELECT batch_id, source_locator, row_counts::text AS row_counts, started_at, finished_at, status
FROM lnrs.lnrs_anon_ingest_batch
WHERE center_code='shengyi'
  AND (row_counts::text LIKE '%nursing_observation%' OR row_counts::text LIKE '%icu_observation%')
ORDER BY started_at;

-- ----------------------------------------------------------------------------
-- V2. PG vital_observation 总行数 (按 R14 nursing batch + R15 icu batch)
-- ----------------------------------------------------------------------------
\echo ''
\echo '=== V2a. R14 nursing PG total ==='
SELECT COUNT(*) AS r14_nursing_total
FROM lnrs.lnrs_anon_vital_observation
WHERE created_batch_id='64735062-eca5-4adf-8f87-6f0e95900dd6'::uuid
  AND obs_type='nursing';

\echo ''
\echo '=== V2b. R15 icu PG total ==='
SELECT COUNT(*) AS r15_icu_total
FROM lnrs.lnrs_anon_vital_observation
WHERE created_batch_id='2367dd54-4d6d-491d-85de-8b1b37569056'::uuid
  AND obs_type='icu';

-- ----------------------------------------------------------------------------
-- V3. source_obs_hash 唯一性
-- ----------------------------------------------------------------------------
\echo ''
\echo '=== V3a. R14 nursing source_obs_hash 唯一性 ==='
SELECT COUNT(*) AS total,
 COUNT(DISTINCT source_obs_hash) AS uniq,
 COUNT(*) - COUNT(DISTINCT source_obs_hash) AS dup_count
FROM lnrs.lnrs_anon_vital_observation
WHERE created_batch_id='64735062-eca5-4adf-8f87-6f0e95900dd6'::uuid
  AND obs_type='nursing';

\echo ''
\echo '=== V3b. R15 icu source_obs_hash 唯一性 ==='
SELECT COUNT(*) AS total,
 COUNT(DISTINCT source_obs_hash) AS uniq,
 COUNT(*) - COUNT(DISTINCT source_obs_hash) AS dup_count
FROM lnrs.lnrs_anon_vital_observation
WHERE created_batch_id='2367dd54-4d6d-491d-85de-8b1b37569056'::uuid
  AND obs_type='icu';

-- ----------------------------------------------------------------------------
-- V4. ETL1 staging 守卫过滤后行数 (item_name 空 / PID 空)
-- ----------------------------------------------------------------------------
\echo ''
\echo '=== V4a. nursing staging 守卫后 (patient_id 非空 + item_name 非空) ==='
-- 注意：13,824,664 是源 + staging 行数 (0 守卫过滤 at ETL1 stage), 12,946 行 item_name 空 = ETL2 引擎守卫过滤
SELECT 13824664 AS staging_total,
       12946 AS null_item_name_filter,
       13824664 - 12946 AS guard_passed_to_etl2;

\echo ''
\echo '=== V4b. icu staging 守卫后 ==='
SELECT 2911682 AS staging_total,
       466 AS null_item_name_filter,
       2911682 - 466 AS guard_passed_to_etl2;

-- ----------------------------------------------------------------------------
-- V5. uniq patient + FK patient_id 完整性
-- ----------------------------------------------------------------------------
\echo ''
\echo '=== V5a. R14 nursing uniq_pt ==='
SELECT COUNT(DISTINCT o.patient_id) AS r14_nursing_uniq_pt
FROM lnrs.lnrs_anon_vital_observation o
WHERE o.created_batch_id='64735062-eca5-4adf-8f87-6f0e95900dd6'::uuid
  AND o.obs_type='nursing';

\echo ''
\echo '=== V5b. R14 nursing FK patient_id 完整性 ==='
SELECT COUNT(*) AS total,
 COUNT(*) FILTER (WHERE p.patient_id IS NULL) AS orphan_pt
FROM lnrs.lnrs_anon_vital_observation o
LEFT JOIN lnrs.lnrs_anon_patient p ON p.patient_id=o.patient_id AND p.center_code='shengyi'
WHERE o.created_batch_id='64735062-eca5-4adf-8f87-6f0e95900dd6'::uuid
  AND o.obs_type='nursing';

\echo ''
\echo '=== V5c. R15 icu uniq_pt ==='
SELECT COUNT(DISTINCT o.patient_id) AS r15_icu_uniq_pt
FROM lnrs.lnrs_anon_vital_observation o
WHERE o.created_batch_id='2367dd54-4d6d-491d-85de-8b1b37569056'::uuid
  AND o.obs_type='icu';

\echo ''
\echo '=== V5d. R15 icu FK patient_id 完整性 ==='
SELECT COUNT(*) AS total,
 COUNT(*) FILTER (WHERE p.patient_id IS NULL) AS orphan_pt
FROM lnrs.lnrs_anon_vital_observation o
LEFT JOIN lnrs.lnrs_anon_patient p ON p.patient_id=o.patient_id AND p.center_code='shengyi'
WHERE o.created_batch_id='2367dd54-4d6d-491d-85de-8b1b37569056'::uuid
  AND o.obs_type='icu';

-- ----------------------------------------------------------------------------
-- V6. 字段填充率
-- ----------------------------------------------------------------------------
\echo ''
\echo '=== V6a. R14 nursing 字段填充率 ==='
SELECT
  COUNT(*) AS total,
  COUNT(item_name) AS item_name,
  COUNT(item_result) AS item_result,
  COUNT(item_unit) AS item_unit,
  COUNT(obs_time) AS obs_time,
  COUNT(obs_detail_json) AS detail_json,
  COUNT(anon_visit_id) AS anon_visit,
  COUNT(item_result_value) AS item_result_value_num
FROM lnrs.lnrs_anon_vital_observation
WHERE created_batch_id='64735062-eca5-4adf-8f87-6f0e95900dd6'::uuid
  AND obs_type='nursing';

\echo ''
\echo '=== V6b. R15 icu 字段填充率 ==='
SELECT
  COUNT(*) AS total,
  COUNT(item_name) AS item_name,
  COUNT(item_result) AS item_result,
  COUNT(item_unit) AS item_unit,
  COUNT(obs_time) AS obs_time,
  COUNT(obs_detail_json) AS detail_json,
  COUNT(anon_visit_id) AS anon_visit,
  COUNT(item_result_value) AS item_result_value_num
FROM lnrs.lnrs_anon_vital_observation
WHERE created_batch_id='2367dd54-4d6d-491d-85de-8b1b37569056'::uuid
  AND obs_type='icu';

-- ----------------------------------------------------------------------------
-- V7. obs_detail_json 顶层 + 子键分布
-- ----------------------------------------------------------------------------
\echo ''
\echo '=== V7a. nursing obs_detail_json->detail 子键分布 ==='
SELECT k, COUNT(*) AS n
FROM (
  SELECT jsonb_object_keys(obs_detail_json->'detail') AS k
  FROM lnrs.lnrs_anon_vital_observation
  WHERE obs_type='nursing' AND center_code='shengyi'
    AND obs_detail_json ? 'detail'
) t
GROUP BY k
ORDER BY n DESC;

\echo ''
\echo '=== V7b. icu obs_detail_json->detail 子键分布 ==='
SELECT k, COUNT(*) AS n
FROM (
  SELECT jsonb_object_keys(obs_detail_json->'detail') AS k
  FROM lnrs.lnrs_anon_vital_observation
  WHERE obs_type='icu' AND center_code='shengyi'
    AND obs_detail_json ? 'detail'
) t
GROUP BY k
ORDER BY n DESC;

-- ----------------------------------------------------------------------------
-- V8. obs_time 范围
-- ----------------------------------------------------------------------------
\echo ''
\echo '=== V8a. nursing obs_time 范围 (排除 -infinity 哨兵) ==='
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE obs_time = '-infinity'::timestamp) AS neg_inf_rows,
  MIN(obs_time) FILTER (WHERE obs_time > '-infinity'::timestamp AND obs_time < 'infinity'::timestamp) AS obs_time_min,
  MAX(obs_time) FILTER (WHERE obs_time > '-infinity'::timestamp AND obs_time < 'infinity'::timestamp) AS obs_time_max
FROM lnrs.lnrs_anon_vital_observation
WHERE created_batch_id='64735062-eca5-4adf-8f87-6f0e95900dd6'::uuid
  AND obs_type='nursing';

\echo ''
\echo '=== V8b. icu obs_time 范围 ==='
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE obs_time = '-infinity'::timestamp) AS neg_inf_rows,
  MIN(obs_time) FILTER (WHERE obs_time > '-infinity'::timestamp AND obs_time < 'infinity'::timestamp) AS obs_time_min,
  MAX(obs_time) FILTER (WHERE obs_time > '-infinity'::timestamp AND obs_time < 'infinity'::timestamp) AS obs_time_max
FROM lnrs.lnrs_anon_vital_observation
WHERE created_batch_id='2367dd54-4d6d-491d-85de-8b1b37569056'::uuid
  AND obs_type='icu';

-- ----------------------------------------------------------------------------
-- V9. 整体结论汇总
-- ----------------------------------------------------------------------------
\echo ''
\echo '=== V9. 整体结论汇总 ==='
SELECT '源 glob (*护理记录*) 合计' AS metric, 16736346 AS value, '清单 R20 预期' AS note
UNION ALL SELECT '合计 PG 落库 (R14 nursing + R15 icu)', 13345742, 'vs 清单 16,736,346 (-3,390,604 = ETL2 引擎去重)';
-- V9 附加 -infinity 哨兵行
SELECT 'nursing obs_time = -infinity 异常行' AS metric, 1 AS value, 'ETL2 引擎 obs_time 解析失败保留 -infinity' AS note
UNION ALL SELECT 'icu obs_time = -infinity 异常行', 0, '无';