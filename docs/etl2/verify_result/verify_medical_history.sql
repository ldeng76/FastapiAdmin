-- 数据导入核验 SQL — 省医 / 病历文书 — 灌库后（清单 R15）
-- 数据项：省医 / 病历文书（清单 R15，第 1 个【完成状态】为空的行）
-- 数据存放目录：/data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.病史.parquet
-- 预期记录数：1,403,598（源 parquet 行）
-- ETL1 staging：/home/dzy/wk/lnrs/data_shengyi202609/import_R13/shengyi/medical_history.parquet
-- ETL2 PG 表：lnrs_anon_medical_history
-- ETL2 spec：shengyi spec #22 "medical_history" kind=history（anon_etl_engine.py:2528-2531）
-- staging hash 文件（前置生成）：/tmp/stg_hashes.txt
--   生成命令见报告 §5，引擎分隔符 `:` + _clean_str / _clean_date 归一化后写入

-- =========================================================================
-- V1. PG medical_history shengyi 概览
-- =========================================================================
\echo === V1. shengyi medical_history 概览 ===
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE center_code='shengyi') AS shengyi_total,
  COUNT(DISTINCT patient_id) AS uniq_patient,
  COUNT(*) FILTER (WHERE record_date IS NOT NULL) AS with_date,
  COUNT(*) FILTER (WHERE data_source IS NOT NULL AND TRIM(data_source)<>'') AS with_data_source,
  COUNT(DISTINCT data_source) FILTER (WHERE data_source IS NOT NULL AND TRIM(data_source)<>'') AS uniq_data_source,
  COUNT(*) FILTER (WHERE created_batch_id='1d2c8847-9a5c-4a34-845f-f3e623738420') AS from_r13_batch
FROM lnrs_anon_medical_history
WHERE center_code='shengyi';

-- =========================================================================
-- V1b. ingest_batch 信息
-- =========================================================================
\echo
\echo === V1b. ingest_batch 信息 ===
SELECT started_at, batch_id, source_locator, source_kind, row_counts
FROM lnrs_anon_ingest_batch
WHERE batch_id='1d2c8847-9a5c-4a34-845f-f3e623738420';

-- =========================================================================
-- V2. staging hash → PG medical_history 命中 (需先把 staging hash 导入 tmp 表)
-- =========================================================================
DROP TABLE IF EXISTS tmp_stg_hashes;
CREATE TEMP TABLE tmp_stg_hashes (h char(64));
\COPY tmp_stg_hashes(h) FROM '/tmp/stg_hashes.txt' WITH (FORMAT text);

\echo === V2. staging hash → PG medical_history 命中 ===
SELECT
  COUNT(*) FILTER (WHERE m.source_hist_hash IS NOT NULL) AS hit,
  COUNT(*) FILTER (WHERE m.source_hist_hash IS NULL) AS miss,
  COUNT(*) AS total
FROM tmp_stg_hashes s
LEFT JOIN lnrs_anon_medical_history m
  ON m.center_code='shengyi' AND m.source_hist_hash=s.h;

-- =========================================================================
-- V3. staging hash 唯一性自检
-- =========================================================================
\echo
\echo === V3. staging hash 唯一性自检 ===
SELECT COUNT(*) AS stg_total, COUNT(DISTINCT h) AS stg_distinct FROM tmp_stg_hashes;

-- =========================================================================
-- V4. PG 反向：所有 PG 行都属于 staging hash?
-- =========================================================================
\echo
\echo === V4. PG 反向：所有 PG 行都属于 staging hash? ===
SELECT
  COUNT(*) FILTER (WHERE s.h IS NOT NULL) AS pg_in_staging,
  COUNT(*) FILTER (WHERE s.h IS NULL) AS pg_not_in_staging,
  COUNT(*) AS pg_total
FROM lnrs_anon_medical_history m
LEFT JOIN tmp_stg_hashes s ON s.h = m.source_hist_hash
WHERE m.center_code='shengyi';

-- =========================================================================
-- V5. PG medical_history FK (patient 孤儿)
-- =========================================================================
\echo
\echo === V5. PG medical_history FK (patient 孤儿) ===
SELECT
  COUNT(*) FILTER (WHERE p.patient_id IS NULL) AS orphan_patient,
  COUNT(*) FILTER (WHERE p.patient_id IS NOT NULL) AS valid_patient,
  COUNT(*) AS total
FROM lnrs_anon_medical_history m
LEFT JOIN lnrs_anon_patient p ON p.patient_id = m.patient_id
WHERE m.center_code='shengyi';

-- =========================================================================
-- V6. PG medical_history 日期分布
-- =========================================================================
\echo
\echo === V6. PG medical_history 日期分布 ===
SELECT
  COUNT(*) FILTER (WHERE record_date IS NOT NULL) AS with_date,
  COUNT(*) FILTER (WHERE record_date IS NULL) AS no_date,
  COUNT(*) AS total,
  MIN(record_date) AS min_date,
  MAX(record_date) AS max_date
FROM lnrs_anon_medical_history
WHERE center_code='shengyi';

-- =========================================================================
-- V7. data_source 分布 + uniq patient
-- =========================================================================
\echo
\echo === V7. data_source 分布 + uniq patient ===
SELECT data_source, COUNT(*) AS n,
       COUNT(DISTINCT patient_id) AS uniq_pat
FROM lnrs_anon_medical_history
WHERE center_code='shengyi'
GROUP BY data_source ORDER BY COUNT(*) DESC;

-- =========================================================================
-- V8. 200 抽样 SHA256 → PG 反查
-- =========================================================================
\echo
\echo === V8. 200 抽样 SHA256 → PG 反查 ===
WITH sample AS (
  SELECT h FROM tmp_stg_hashes ORDER BY RANDOM() LIMIT 200
)
SELECT
  COUNT(*) FILTER (WHERE m.source_hist_hash IS NOT NULL) AS hit,
  COUNT(*) FILTER (WHERE m.source_hist_hash IS NULL) AS miss,
  COUNT(*) AS total
FROM sample s
LEFT JOIN lnrs_anon_medical_history m
  ON m.center_code='shengyi' AND m.source_hist_hash=s.h;

-- =========================================================================
-- V9. source_hist_hash 全局唯一性
-- =========================================================================
\echo
\echo === V9. source_hist_hash 全局唯一性 ===
SELECT
  COUNT(*) AS total,
  COUNT(DISTINCT source_hist_hash) AS distinct_hashes,
  COUNT(*) - COUNT(DISTINCT source_hist_hash) AS dup_count
FROM lnrs_anon_medical_history
WHERE center_code='shengyi';

-- =========================================================================
-- V10. 涉及 unique patient_id + 全表记录日期范围
-- =========================================================================
\echo
\echo === V10. 涉及 unique patient_id ===
SELECT COUNT(DISTINCT patient_id) AS uniq_patient FROM lnrs_anon_medical_history WHERE center_code='shengyi';

\echo
\echo === V11. record_date 年份分布 ===
SELECT
  EXTRACT(YEAR FROM record_date) AS yr,
  COUNT(*) AS n
FROM lnrs_anon_medical_history
WHERE center_code='shengyi' AND record_date IS NOT NULL
GROUP BY yr ORDER BY yr;
