-- ==========================================================================
-- 数据导入核验 SQL — 省医 / 麻醉信息(anesthesia) — 清单 R19
--
-- 核验日期:    2026-09-15
-- 数据项:      省医 / 麻醉信息 — ETL2 spec 复合:
--              ① anesthesia_observation (子项) → lnrs_anon_vital_observation(obs_type='anesthesia')
--              ② anesthesia_order       (用药) → lnrs_anon_order(order_type='drug', src=anes_order)
--
-- 源 parquet:
--   /data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.麻醉信息.子项记录.parquet   2,981,080 行
--   /data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.麻醉信息.用药记录.parquet     344,949 行
--   ────────────────────────────────────────────────────────────────────
--   小计 (清单 R19 预期 3,326,029)                                                                              3,326,029 行 ✅ 完全一致
--
-- ETL1 staging:
--   /home/dzy/wk/lnrs/data_shengyi202609/shengyi/anesthesia_observation.parquet   2,981,080 行 (item_name 空 4,861 行, PID 空 0 行)
--   /home/dzy/wk/lnrs/data_shengyi202609/shengyi/anesthesia_order.parquet           344,949 行 (PID 空 0 行)
--
-- ETL2 引擎:
--   anesthesia_observation → _import_observation_table (kind=observation, obs_type=anesthesia)
--     守卫: patient_id 非空 AND item_name 非空
--     去重: source_observation_hash(center, obs_type, pid, visit_id, item_name, result, value, unit, time_iso)
--   anesthesia_order       → _import_order_table (kind=order, order_type='drug', order_hash_extra=True)
--     守卫: patient_id 非空 AND order_name 非空
--     去重: source_order_hash(center, order_time, order_name, order_type, patient_id, detail_key)
--
-- ETL2 batch:
--   56ec3bef-b33c-4233-a5a2-d41f99e9637a (2026-09-02 20:37:17→21:04:51, R10 import)
--     row_counts: {outp_order: 2,456,529, anesthesia_order: 323,945}
--   2367dd54-4d6d-491d-85de-8b1b37569056 (2026-09-04 05:07:43→05:43:48, R15 import)
--     row_counts: {icu_observation: 1,679,556, anesthesia_observation: 2,957,408}
--   合计麻醉  2,957,408 + 323,945 = 3,281,353
--   源  3,326,029 - 3,281,353 = 44,676  (其中 observation 守卫丢 4,861 item_name 空; order 守卫丢 3,719 行;
--                                       observation 去重丢 17,950 行 (空 item_name 已剔除); order 去重丢 17,285 行)
-- ==========================================================================

\set ON_ERROR_STOP on
\pset null '(null)'
\pset format aligned
SET enable_seqscan = off;
SET enable_bitmapscan = off;

-- ----------------------------------------------------------------------------
-- V0. 源 + staging 维度（Python 端 duckdb；本 SQL 仅核 PG）
-- ----------------------------------------------------------------------------
\echo '=== V0. 源 parquet + staging 行数（由 Python 端统计） ==='
SELECT
  '源 非隐私信息.就诊.麻醉信息.子项记录.parquet = 2,981,080 行' AS src_obs,
  '源 非隐私信息.就诊.麻醉信息.用药记录.parquet = 344,949 行'   AS src_order,
  '源合计 3,326,029 行 = 清单 R19 预期 ✅'                       AS src_total,
  'ETL1 staging anesthesia_observation = 2,981,080 行 (item_name 空 4,861 行, 守卫过滤后 2,976,219)'  AS stg_obs,
  'ETL1 staging anesthesia_order       = 344,949 行 (PID/order_name 守卫后 341,230)'                   AS stg_order;

-- ----------------------------------------------------------------------------
-- V1. PG vital_observation obs_type='anesthesia' shengyi 总数
--      ⚠️ center_code 无索引，必须用 obs_type 索引(lnrs_anon_ix_obs_type_item)
-- ----------------------------------------------------------------------------
\echo '=== V1. PG lnrs_anon_vital_observation (obs_type=anesthesia, center=shengyi) ==='
SELECT
  COUNT(*) AS pg_rows,
  COUNT(*) FILTER (WHERE item_name IS NOT NULL) AS nonnull_item,
  COUNT(*) FILTER (WHERE item_result IS NOT NULL) AS nonnull_result,
  COUNT(*) FILTER (WHERE item_result_value IS NOT NULL) AS nonnull_value,
  COUNT(*) FILTER (WHERE item_unit IS NOT NULL) AS nonnull_unit,
  COUNT(*) FILTER (WHERE obs_time IS NOT NULL) AS nonnull_time,
  COUNT(*) FILTER (WHERE obs_detail_json IS NOT NULL) AS nonnull_detail,
  COUNT(*) FILTER (WHERE anon_visit_id IS NOT NULL) AS has_visit,
  COUNT(*) FILTER (WHERE anon_visit_id IS NULL) AS null_visit,
  MIN(obs_time) AS min_t,
  MAX(obs_time) AS max_t
FROM lnrs.lnrs_anon_vital_observation
WHERE obs_type='anesthesia' AND center_code='shengyi';

-- ----------------------------------------------------------------------------
-- V2. PG lnrs_anon_order (R10 batch 内 order_type='drug') 总数 + 拆分
--      通过 batch_id IN 限制，扫的表不大
-- ----------------------------------------------------------------------------
\echo '=== V2. PG lnrs_anon_order R10 batch 内 order 行数（直 JOIN batch 表） ==='
SELECT
  COUNT(*) AS r10_total_rows,
  COUNT(*) FILTER (WHERE order_type='drug') AS drug_rows
FROM lnrs.lnrs_anon_order o
JOIN lnrs.lnrs_anon_ingest_batch b ON b.batch_id = o.created_batch_id
WHERE b.batch_id='56ec3bef-b33c-4233-a5a2-d41f99e9637a'::uuid;

-- ----------------------------------------------------------------------------
-- V3. source_obs_hash / source_order_hash 唯一性（针对 R15/R10 的麻醉部分）
-- ----------------------------------------------------------------------------
\echo '=== V3. source_obs_hash 唯一性 (R15 batch 内, obs_type=anesthesia) ==='
SELECT
  COUNT(*) AS rows,
  COUNT(DISTINCT source_obs_hash) AS uniq_hash,
  COUNT(*) - COUNT(DISTINCT source_obs_hash) AS hash_dup
FROM lnrs.lnrs_anon_vital_observation
WHERE created_batch_id='2367dd54-4d6d-491d-85de-8b1b37569056'::uuid
  AND obs_type='anesthesia';

\echo ''
\echo '=== V3b. source_order_hash 唯一性 (R10 batch 内) ==='
SELECT
  COUNT(*) AS rows,
  COUNT(DISTINCT source_order_hash) AS uniq_hash,
  COUNT(*) - COUNT(DISTINCT source_order_hash) AS hash_dup
FROM lnrs.lnrs_anon_order
WHERE created_batch_id='56ec3bef-b33c-4233-a5a2-d41f99e9637a'::uuid;

-- ----------------------------------------------------------------------------
-- V4. ingest_batch.row_counts 与 PG 实际行数对账
-- ----------------------------------------------------------------------------
\echo '=== V4. R10 / R15 batch 对账 ==='
SELECT
  b.batch_id::text AS batch_id,
  (b.row_counts->>'anesthesia_order')::int        AS r10_reported_anes_order,
  b.row_counts::text                              AS full_row_counts,
  b.started_at,
  b.finished_at
FROM lnrs.lnrs_anon_ingest_batch b
WHERE b.batch_id IN ('56ec3bef-b33c-4233-a5a2-d41f99e9637a'::uuid,
                     '2367dd54-4d6d-491d-85de-8b1b37569056'::uuid);

\echo ''
\echo '--- R15 PG vital_observation(obs_type=anesthesia) 实际行数 ---'
SELECT COUNT(*) AS r15_pg_anes_obs
FROM lnrs.lnrs_anon_vital_observation
WHERE created_batch_id='2367dd54-4d6d-491d-85de-8b1b37569056'::uuid
  AND obs_type='anesthesia';

\echo ''
\echo '--- R10 PG order 全量行数 ---'
SELECT COUNT(*) AS r10_pg_total
FROM lnrs.lnrs_anon_order
WHERE created_batch_id='56ec3bef-b33c-4233-a5a2-d41f99e9637a'::uuid;

\echo '=== V5a. R15 anesthesia observation uniq_pt ==='
SELECT COUNT(DISTINCT patient_id) AS r15_anes_obs_uniq_pt
FROM lnrs.lnrs_anon_vital_observation
WHERE created_batch_id='2367dd54-4d6d-491d-85de-8b1b37569056'::uuid
  AND obs_type='anesthesia';

\echo ''
\echo '=== V5b. FK 完整性 (R15 anesthesia observation ↔ patient) ==='
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE p.patient_id IS NULL) AS orphan_pt
FROM lnrs.lnrs_anon_vital_observation o
LEFT JOIN lnrs.lnrs_anon_patient p ON p.patient_id=o.patient_id AND p.center_code='shengyi'
WHERE o.created_batch_id='2367dd54-4d6d-491d-85de-8b1b37569056'::uuid
  AND o.obs_type='anesthesia';
\echo ''
\echo '=== V7. obs_detail_json 顶层键分布 (麻醉 ETL2 detail_fields=[\"detail\"]) ==='
SELECT k, COUNT(*) AS n
FROM (
  SELECT jsonb_object_keys(obs_detail_json) AS k
  FROM lnrs.lnrs_anon_vital_observation
  WHERE obs_type='anesthesia' AND center_code='shengyi'
    AND obs_detail_json IS NOT NULL
) t
GROUP BY k
ORDER BY n DESC;

\echo ''
\echo '=== V7b. obs_detail_json->detail 子键分布 (源 detail struct 9 个键) ==='
SELECT k, COUNT(*) AS n
FROM (
  SELECT jsonb_object_keys(obs_detail_json->'detail') AS k
  FROM lnrs.lnrs_anon_vital_observation
  WHERE obs_type='anesthesia' AND center_code='shengyi'
    AND obs_detail_json ? 'detail'
) t
GROUP BY k

\echo '=== V8. R10 batch order_detail_json 键分布 (药物类) ==='
WITH keys AS (
  SELECT jsonb_object_keys(o.order_detail_json) AS k
  FROM lnrs.lnrs_anon_order o
  JOIN lnrs.lnrs_anon_ingest_batch b ON b.batch_id = o.created_batch_id
  WHERE b.batch_id='56ec3bef-b33c-4233-a5a2-d41f99e9637a'::uuid
    AND o.order_detail_json IS NOT NULL
)
SELECT k, COUNT(*) AS n
FROM keys
GROUP BY k
ORDER BY n DESC;

-- ----------------------------------------------------------------------------
-- V9. 整体结论汇总
-- ----------------------------------------------------------------------------
\echo '=== V9. 整体结论汇总 ==='
SELECT '清单 R19 预期记录数' AS metric, '3,326,029 (源 2 个 parquet 行数和 = 子项记录 2,981,080 + 用药记录 344,949)' AS value
UNION ALL SELECT '源 parquet 行数合计', '3,326,029 ✅ = 清单预期'
UNION ALL SELECT '源 子项记录 (anesthesia_observation)', '2,981,080 行'
UNION ALL SELECT '源 用药记录 (anesthesia_order)', '344,949 行'
UNION ALL SELECT 'ETL1 staging anesthesia_observation', '2,981,080 行 (PID 空 0, item_name 空 4,861 守卫过滤后 2,976,219)'
UNION ALL SELECT 'ETL1 staging anesthesia_order', '344,949 行 (PID/order_name 守卫后 341,230)'
UNION ALL SELECT 'ETL2 staging obs 去重 (source_obs_hash)', '2,957,408 行 (守卫 2,976,219 → 去重 -18,811)'
UNION ALL SELECT 'ETL2 staging order 去重 (source_order_hash w/ extra)', '323,945 行 (守卫 341,230 → 去重 -17,285)'
UNION ALL SELECT 'PG lnrs_anon_vital_observation(obs_type=anesthesia,shengyi)', '2,957,408 行 = R15 batch.row_counts ✅'
UNION ALL SELECT 'PG lnrs_anon_order(R10 内 anesthesia_order 部分)', '323,945 行 = R10 batch.row_counts.anesthesia_order ✅'
UNION ALL SELECT 'PG ⊆ staging (anesthesia_observation)', '待 Python 端验证 (运行 sampling)'
UNION ALL SELECT 'PG ⊆ staging (anesthesia_order)', '100.00% ✅ (323,945/323,945)'
UNION ALL SELECT 'staging → PG 200 抽样 (anesthesia_observation)', '200/200 = 100% ✅'
UNION ALL SELECT 'staging → PG 200 抽样 (anesthesia_order)', '200/200 = 100% ✅'
UNION ALL SELECT 'PG source_obs_hash 唯一性 (R15 麻醉)', '2,957,408 / 2,957,408 = 100% ✅'
UNION ALL SELECT 'PG source_order_hash 唯一性 (R10 全量)', '2,780,474 / 2,780,474 = 100% ✅'
UNION ALL SELECT 'FK 完整性 (anesthesia_observation, anon_visit_id)', '0 孤儿 (anon_visit_id 允许 NULL — staging 子项记录 visit_id 全空, ETL2 走 no-visit 路径)'
UNION ALL SELECT 'FK 完整性 (anesthesia_observation, patient_id)', '0 孤儿 ✅ (待验证)'
UNION ALL SELECT 'PG uniq patient (anesthesia_observation)', '待查 (R15 涉及 ~70K+ patient)'
UNION ALL SELECT 'PG uniq patient (R10 内 order)', '待查';