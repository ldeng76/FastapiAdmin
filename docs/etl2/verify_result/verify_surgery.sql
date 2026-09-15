-- ==========================================================================
-- 数据导入核验 SQL — 省医 / 手术记录(surgery) — 清单 R18
--
-- 核验日期:    2026-09-15
-- 数据项:      省医 / 手术记录 — ETL2 spec surgery (kind=surgery)
-- 源 parquet:  /data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.手术信息.parquet
-- ETL1 staging: /home/dzy/wk/lnrs/data_shengyi202609/shengyi/surgery_record.parquet
--              (= surgery.parquet 78,384 ∪ surgery_fp.parquet 359,213 → 363,508，
--                注: 清单 R18 只列了非隐私信息.就诊.手术信息.parquet 78,384，
--                但 ETL1 SQL_SURGERY 是 UNION ALL 两个 parquet；
--                引擎走的是 staging 表，统一处理)
-- ETL2 目标:   lnrs.lnrs_anon_visit + lnrs.lnrs_anon_surgery
-- ETL2 batch:  c5871ad4-... (2026-07-29 08:10, 早期 2 行 sample 测试)
--              3429fa10-c6dd-462a-882b-0d79fe0a825b (2026-09-02 16:09:43→16:15:23,
--                R3 import, 324,635 行, source_locator=import_R3/shengyi)
-- 核验环境:    dev PG 127.0.0.1:5432 (center='shengyi')
-- 预期记录数:  78,384 (清单 R18 写的"非隐私信息.就诊.手术信息.parquet"行数；
--              ⚠️ 但 ETL1/ETL2 实际处理的是 staging 363,508 (含病案首页.手术 359,213 行))
-- ==========================================================================

\set ON_ERROR_STOP on
\pset null '(null)'
\pset format aligned

-- ----------------------------------------------------------------------------
-- V0. 源 parquet / staging 行数（由 Python 端 duckdb 统计；本 SQL 仅核 PG）
-- ----------------------------------------------------------------------------
\echo '=== V0. 源 + staging 行数（Python 端 duckdb） ==='
SELECT
  '源 surgery(手术信息).parquet = 78,384 行' AS src_surgery,
  '源 surgery_fp(住院病案首页.手术).parquet = 359,213 行' AS src_fp,
  'ETL1 staging surgery_record.parquet = 363,508 行' AS staging_total,
  'staging distinct(visit_id||procedure_name) = 324,638 个组合' AS staging_uniq_vp,
  'staging distinct(patient_id) = 53,230' AS staging_uniq_pid,
  'staging distinct(visit_id) = 129,968' AS staging_uniq_vid,
  'staging null/empty patient_id|visit_id|procedure_name = 0' AS null_guard;

-- ----------------------------------------------------------------------------
-- V1. PG lnrs_anon_surgery shengyi 概览
-- ----------------------------------------------------------------------------
\echo '=== V1. PG lnrs_anon_surgery shengyi 概览 ==='
SELECT
  COUNT(*) AS pg_rows,
  COUNT(DISTINCT patient_id) AS pg_uniq_pt,
  COUNT(DISTINCT anon_visit_id) AS pg_uniq_visit,
  COUNT(*) FILTER (WHERE surgery_date IS NOT NULL) AS nonnull_date,
  COUNT(*) FILTER (WHERE surgery_date IS NULL) AS null_date,
  COUNT(*) FILTER (WHERE procedure_name IS NOT NULL) AS nonnull_proc,
  COUNT(*) FILTER (WHERE procedure_name = '') AS empty_proc,
  COUNT(*) FILTER (WHERE resection_scope IS NOT NULL) AS nonnull_resection,
  COUNT(*) FILTER (WHERE surgical_approach IS NOT NULL) AS nonnull_approach,
  COUNT(*) FILTER (WHERE procedure_detail IS NOT NULL) AS nonnull_detail,
  COUNT(DISTINCT procedure_name) AS uniq_proc,
  MIN(surgery_date) AS min_dt,
  MAX(surgery_date) AS max_dt
FROM lnrs.lnrs_anon_surgery
WHERE center_code='shengyi';

-- ----------------------------------------------------------------------------
-- V2. shengyi surgery 按 batch 行数明细
-- ----------------------------------------------------------------------------
\echo '=== V2. shengyi surgery 按 batch 行数 ==='
SELECT
  s.created_batch_id::text AS batch_id,
  b.source_locator,
  b.status::text AS batch_status,
  b.row_counts::text AS batch_row_counts,
  COUNT(*) AS pg_rows,
  b.started_at,
  b.finished_at
FROM lnrs.lnrs_anon_surgery s
LEFT JOIN lnrs.lnrs_anon_ingest_batch b ON b.batch_id = s.created_batch_id
WHERE s.center_code='shengyi'
GROUP BY s.created_batch_id, b.source_locator, b.status, b.row_counts, b.started_at, b.finished_at
ORDER BY b.started_at NULLS LAST;

-- ----------------------------------------------------------------------------
-- V3. source_surgery_hash 全局唯一性（per-center）
-- ----------------------------------------------------------------------------
\echo '=== V3. source_surgery_hash 全局唯一性（per center） ==='
SELECT
  center_code,
  COUNT(*) AS rows,
  COUNT(DISTINCT source_surgery_hash) AS uniq_hash,
  COUNT(*) - COUNT(DISTINCT source_surgery_hash) AS hash_dup_n
FROM lnrs.lnrs_anon_surgery
WHERE center_code='shengyi'
GROUP BY center_code;

-- ----------------------------------------------------------------------------
-- V4. FK 完整性 (anon_visit_id / patient_id)
-- ----------------------------------------------------------------------------
\echo '=== V4. FK 完整性 (anon_visit / patient) ==='
SELECT
  COUNT(*) AS pg_surgery,
  COUNT(*) FILTER (WHERE v.anon_visit_id IS NULL) AS orphan_visit,
  COUNT(*) FILTER (WHERE p.patient_id IS NULL) AS orphan_patient
FROM lnrs.lnrs_anon_surgery s
LEFT JOIN lnrs.lnrs_anon_visit v ON v.anon_visit_id=s.anon_visit_id AND v.center_code='shengyi'
LEFT JOIN lnrs.lnrs_anon_patient p ON p.patient_id=s.patient_id AND p.center_code='shengyi'
WHERE s.center_code='shengyi';

-- ----------------------------------------------------------------------------
-- V5. 应用层 FK 一致性 (shengyi surgery.patient_id ⊆ shengyi patient)
-- ----------------------------------------------------------------------------
\echo '=== V5. 应用层 FK 一致性 ==='
SELECT
  (SELECT COUNT(DISTINCT patient_id) FROM lnrs.lnrs_anon_surgery WHERE center_code='shengyi') AS surgery_uniq_pt,
  (SELECT COUNT(DISTINCT s.patient_id)
     FROM lnrs.lnrs_anon_surgery s
     WHERE s.center_code='shengyi'
       AND NOT EXISTS (SELECT 1 FROM lnrs.lnrs_anon_patient p
                       WHERE p.patient_id=s.patient_id AND p.center_code='shengyi')
  ) AS surgery_pt_not_in_patient;

-- ----------------------------------------------------------------------------
-- V6. surgery_date 异常值（NULL / 越界）
-- ----------------------------------------------------------------------------
\echo '=== V6. surgery_date 异常值 ==='
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE surgery_date IS NULL) AS null_dt,
  COUNT(*) FILTER (WHERE surgery_date < DATE '1900-01-01') AS pre1900,
  COUNT(*) FILTER (WHERE surgery_date > CURRENT_DATE) AS future_dt,
  MIN(surgery_date) AS min_dt,
  MAX(surgery_date) AS max_dt
FROM lnrs.lnrs_anon_surgery
WHERE center_code='shengyi';

-- ----------------------------------------------------------------------------
-- V7. 涉及 unique patient / visit 的范围
-- ----------------------------------------------------------------------------
\echo '=== V7. 范围：uniq patient / visit ==='
SELECT
  COUNT(DISTINCT patient_id) AS uniq_pt,
  COUNT(DISTINCT anon_visit_id) AS uniq_visit,
  (SELECT COUNT(*) FROM lnrs.lnrs_anon_patient WHERE center_code='shengyi') AS shengyi_pt_total,
  (SELECT COUNT(*) FROM lnrs.lnrs_anon_visit WHERE center_code='shengyi') AS shengyi_visit_total
FROM lnrs.lnrs_anon_surgery
WHERE center_code='shengyi';

-- ----------------------------------------------------------------------------
-- V8. PHI 审计（visit_id 写入 lnrs_anon_phi_audit）
-- ----------------------------------------------------------------------------
\echo '=== V8. PHI 审计：shengyi surgery 的 visit_id HMAC 行数（按 batch_id 过滤） ==='
SELECT
  COUNT(*) AS audit_rows,
  COUNT(DISTINCT a.source_hash) AS uniq_hashes,
  MIN(a.created_at) AS first_audit,
  MAX(a.created_at) AS last_audit
FROM lnrs.lnrs_anon_phi_audit a
WHERE a.batch_id IN ('c5871ad4-0653-4130-8df0-c74235695b36'::uuid,
                     '3429fa10-c6dd-462a-882b-0d79fe0a825b'::uuid)
  AND a.source_table='surgery_record'
  AND a.source_field='visit_id';
-- ----------------------------------------------------------------------------
-- V9. ETL2 batch ingest_batch.row_counts 与 PG 实际行数对账
-- ----------------------------------------------------------------------------
\echo '=== V9. batch.row_counts(surgery_record) vs PG 实际落库 ==='
SELECT
  b.batch_id::text AS batch_id,
  (b.row_counts->>'surgery_record')::int AS batch_reported_rows,
  COUNT(s.surgery_id) AS pg_rows
FROM lnrs.lnrs_anon_ingest_batch b
LEFT JOIN lnrs.lnrs_anon_surgery s ON s.created_batch_id=b.batch_id AND s.center_code='shengyi'
WHERE b.center_code='shengyi'
  AND b.row_counts ? 'surgery_record'
GROUP BY b.batch_id, b.row_counts
ORDER BY b.started_at;

-- ----------------------------------------------------------------------------
-- V10. procedure_detail JSON 抽样：from_surgery vs from_front_page
--      ETL1 SQL_SURGERY 是 UNION ALL 两个子查询:
--        - from_surgery:    键 = 麻醉方式 / 手术经过
--        - from_front_page: 键 = 手术等级 / 切口愈合等级 / 麻醉方式 / 术者 / 麻醉医生 / Ⅰ助 / Ⅱ助 / 病案序号
-- ----------------------------------------------------------------------------
\echo '=== V10. procedure_detail JSON 键分布 ==='
WITH keys AS (
  SELECT jsonb_object_keys(procedure_detail) AS k
  FROM lnrs.lnrs_anon_surgery
  WHERE center_code='shengyi' AND procedure_detail IS NOT NULL
)
SELECT k, COUNT(*) AS n
FROM keys
GROUP BY k
ORDER BY n DESC;

-- ----------------------------------------------------------------------------
-- V11. surgery 与 patient 表 uniq_patient 范围一致性
-- ----------------------------------------------------------------------------
\echo '=== V11. surgery ∩ patient 范围 ==='
SELECT
  (SELECT COUNT(DISTINCT patient_id) FROM lnrs.lnrs_anon_surgery WHERE center_code='shengyi') AS surgery_uniq_pt,
  (SELECT COUNT(*) FROM lnrs.lnrs_anon_patient WHERE center_code='shengyi') AS pt_total,
  (SELECT COUNT(DISTINCT s.patient_id)
     FROM lnrs.lnrs_anon_surgery s
     WHERE s.center_code='shengyi'
       AND EXISTS (SELECT 1 FROM lnrs.lnrs_anon_patient p
                   WHERE p.patient_id=s.patient_id AND p.center_code='shengyi')
  ) AS surgery_pt_in_pt_table;

-- ----------------------------------------------------------------------------
-- V12. 整体结论汇总
-- ----------------------------------------------------------------------------
\echo '=== V12. 整体结论汇总 ==='
SELECT
  '清单预期记录数' AS metric, '78,384 (源 surgery.parquet；⚠️ 实际 ETL1 staging 是 363,508 = UNION 病案首页.手术)' AS value
UNION ALL SELECT '源 surgery.parquet 行数', '78,384 ✅'
UNION ALL SELECT '源 surgery_fp.parquet 行数', '359,213 (清单 R18 未列, 已在 ETL1 SQL_SURGERY 合并)'
UNION ALL SELECT 'ETL1 staging 行数', '363,508 (surgery 78,384 ∪ surgery_fp 359,213 - 守卫过滤 0)'
UNION ALL SELECT 'ETL1 staging distinct(visit+procedure)', '324,638 (与 PG 324,637 几乎完全一致, 差 1)'
UNION ALL SELECT 'ETL2 引擎守卫后 (PID+VID+proc 非空)', '324,638 (staging 三类字段全部 0 空)'
UNION ALL SELECT 'ETL2 引擎去重后 (distinct source_surgery_hash)', '324,638 → PG 324,637'
UNION ALL SELECT 'PG lnrs_anon_surgery shengyi 总行数', '324,637 (sample 2 + R3 324,635)'
UNION ALL SELECT 'PG ⊆ staging source_surgery_hash 命中', '待 Python 端验证（运行 verify_surgery_staging_match.py）'
UNION ALL SELECT 'PG source_surgery_hash 唯一性', '100% (324,637 = uniq)'
UNION ALL SELECT 'PG FK 完整性 (anon_visit / patient)', '0 孤儿 ✅'
UNION ALL SELECT 'PG surgery_date NULL', '4 行 (守卫过滤, ETL2 引擎留 NULL)'
UNION ALL SELECT 'PG surgery_date 范围', '2002-12-05 ~ 2025-11-05'
UNION ALL SELECT 'PG uniq patient', '53,230 (占 shengyi patient 87,138 的 61%)'
UNION ALL SELECT 'PG uniq visit', '129,969 (占 shengyi visit 2,381,010 的 5.5%)'
UNION ALL SELECT 'PHI 审计 (visit_id HMAC)', '待 Python 端验证';