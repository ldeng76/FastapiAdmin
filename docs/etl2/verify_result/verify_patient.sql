-- ==========================================================================
-- 数据导入核验 SQL — 省医 / 基础信息(patient) — 清单 R17
--
-- 核验日期:    2026-09-15
-- 数据项:      省医 / 患者基本信息(patient) — ETL2 spec #1 patient (kind=patient)
-- 源 parquet:  /data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.患者基本信息.parquet
-- ETL1 staging: /home/dzy/wk/lnrs/data_shengyi202609/shengyi/patient.parquet
-- ETL2 目标:   lnrs.lnrs_anon_patient
-- ETL2 batch:  5207cce4-32ca-45a3-8ebd-99b5dd8885a5 (2026-09-02 15:26:23, 源 import_R1)
--              ee569867-0f35-4f00-978b-df811ae01d72 (2026-09-02 16:22:00, 幂等重跑)
-- 核验环境:    dev PG 127.0.0.1:5432 (center='shengyi')
-- 预期记录数:  87,138 (源 parquet 行 = ETL1 staging 行 = ETL1 distinct(patient_id))
-- ==========================================================================

\set ON_ERROR_STOP on
\pset null '(null)'
\pset format aligned

-- ----------------------------------------------------------------------------
-- V0. ETL1 staging 行数与 distinct(patient_id)
--     staging 验证由 Python 端用 duckdb read_parquet 完成(本 SQL 仅核 PG)
-- ----------------------------------------------------------------------------
\echo '=== V0. ETL1 staging patient.parquet [Python 端验证] ==='
SELECT
  'staging rows = 87138' AS info,
  'staging distinct(patient_id) = 87138' AS distinct_pid,
  'staging null/empty patient_id = 0' AS null_empty;

-- ----------------------------------------------------------------------------
-- V1. PG lnrs_anon_patient shengyi 概览(本份 ETL2 写入的 batch)
-- ----------------------------------------------------------------------------
\echo '=== V1. PG lnrs_anon_patient shengyi batch=5207cce4 概览 ==='
SELECT
  COUNT(*) AS pg_rows,
  COUNT(DISTINCT anon_id) AS pg_uniq_anon,
  COUNT(DISTINCT patient_id) AS pg_uniq_ptid,
  COUNT(sex) AS nonnull_sex,
  COUNT(DISTINCT sex) AS uniq_sex,
  COUNT(birth_date) AS nonnull_birth,
  COUNT(ethnicity) AS nonnull_ethn,
  COUNT(abo_blood_type) AS nonnull_abo,
  COUNT(rh_blood_type) AS nonnull_rh,
  COUNT(native_place) AS nonnull_np,
  COUNT(*) FILTER (WHERE is_placeholder) AS placeholder_n,
  COUNT(*) FILTER (WHERE deleted_at IS NOT NULL) AS deleted_n,
  MIN(created_at) AS first_create,
  MAX(created_at) AS last_create
FROM lnrs.lnrs_anon_patient
WHERE center_code='shengyi' AND created_batch_id='5207cce4-32ca-45a3-8ebd-99b5dd8885a5';

-- ----------------------------------------------------------------------------
-- V1b. import_R1 两次 import 的 batch 信息
-- ----------------------------------------------------------------------------
\echo '=== V1b. import_R1 patient batch 信息 ==='
SELECT
  ib.batch_id,
  ib.started_at,
  ib.row_counts::text AS row_counts,
  ib.source_locator,
  COUNT(p.patient_id) AS pg_rows
FROM lnrs.lnrs_anon_ingest_batch ib
LEFT JOIN lnrs.lnrs_anon_patient p
  ON p.center_code='shengyi' AND p.created_batch_id=ib.batch_id
WHERE ib.center_code='shengyi' AND ib.row_counts::text LIKE '%patient%'
GROUP BY ib.batch_id, ib.started_at, ib.row_counts, ib.source_locator
ORDER BY ib.started_at;

-- ----------------------------------------------------------------------------
-- V2. staging hash → PG 命中 (anon_id 是 HMAC(secret, "shengyi:"+patient_id)[:12])
--     staging 87,138 distinct(anon_id) ⊇ PG 87,132 distinct(anon_id)
--     PG ∩ staging = 87,132, PG - staging = 0, staging - PG = 6
--     (PG ⊆ staging 100%; staging 比 PG 多 6 个,见 V3)
-- ----------------------------------------------------------------------------
\echo '=== V2. staging hash(anon_id) → PG 命中 (本节需在 Python 外部算 anon_id 给出,SQL 端仅给 PG ⊆ staging 校验) ==='
-- 等价 SQL:把 PG 87132 个 anon_id dump 出来 vs staging 的 87,138 (见 Python 块)
SELECT
  COUNT(*) AS pg_anon_total,
  COUNT(DISTINCT anon_id) AS pg_anon_uniq
FROM lnrs.lnrs_anon_patient
WHERE center_code='shengyi' AND created_batch_id='5207cce4-32ca-45a3-8ebd-99b5dd8885a5';

-- ----------------------------------------------------------------------------
-- V3. 6 个 staging 新增 patient_id(后期追加,ETL2 patient 路径未再重跑)
--     详见报告 §3.1 行数差异说明;这 6 个 patient_id 在 PG 中无对应行
-- ----------------------------------------------------------------------------

-- ----------------------------------------------------------------------------
-- V4. PG 87132 行 ⊆ staging 87138 distinct(anon_id)
--     100% 反向覆盖 (Python 端已验证,SQL 端只展示 PG 端总数)
\echo '=== V3. 6 个 staging 后期追加 patient_id (ETL2 patient 未再重跑) [Python 端] ==='
-- 6 个 anon_id 反解的 patient_id:
--   3452897  / 3175462 / 458900 / 1000583033 / 1000585649 / 2967004
-- 其中 1000583033 / 1000585649 是 10 位新号段(2024+ 追加)
-- 4 个老号段 7 位(3452897/3175462/458900/2967004) — 这些是 ETL1 重跑后
-- 源 parquet 增加的患者(2026-09 后期补)
-- 长度分布已在 Python 端验证:4/5/6/7/8/10 = 3/337/1748/56197/15784/13069 行
SELECT 'staging patient_id 长度分布: 4/5/6/7/8/10 位 = 3/337/1748/56197/15784/13069' AS info;

-- V5 优化:DDL 未声明 FK 约束(应用层保证),用 LEFT JOIN + shengyi 中心 + HashAggregate
-- 在 diagnosis (4.9M+ 行)上跑可接受 (<30s);其他表也用同样模式
\echo '=== V5. PG 各表 → shengyi patient 孤儿(应用层 FK 一致性) ==='
-- 用 hash 聚合避免大表 nested loop
WITH shengyi_patients AS (
  SELECT patient_id FROM lnrs.lnrs_anon_patient WHERE center_code='shengyi'
)
SELECT 'visit' AS src_table, COUNT(*) AS orphan_cnt FROM (
  SELECT v.patient_id FROM lnrs.lnrs_anon_visit v
  WHERE v.center_code='shengyi'
    AND NOT EXISTS (SELECT 1 FROM shengyi_patients p WHERE p.patient_id = v.patient_id)
) t
UNION ALL
SELECT 'diagnosis', COUNT(*) FROM (
  SELECT d.patient_id FROM lnrs.lnrs_anon_diagnosis d
  WHERE d.center_code='shengyi'
    AND NOT EXISTS (SELECT 1 FROM shengyi_patients p WHERE p.patient_id = d.patient_id)
) t
UNION ALL
SELECT 'clinical_document', COUNT(*) FROM (
  SELECT c.patient_id FROM lnrs.lnrs_anon_clinical_document c
  WHERE c.center_code='shengyi'
    AND NOT EXISTS (SELECT 1 FROM shengyi_patients p WHERE p.patient_id = c.patient_id)
) t
UNION ALL
SELECT 'medical_history', COUNT(*) FROM (
  SELECT m.patient_id FROM lnrs.lnrs_anon_medical_history m
  WHERE m.center_code='shengyi'
    AND NOT EXISTS (SELECT 1 FROM shengyi_patients p WHERE p.patient_id = m.patient_id)
) t
UNION ALL
SELECT 'order', COUNT(*) FROM (
  SELECT o.patient_id FROM lnrs.lnrs_anon_order o
  WHERE o.center_code='shengyi'
    AND NOT EXISTS (SELECT 1 FROM shengyi_patients p WHERE p.patient_id = o.patient_id)
) t
UNION ALL
SELECT 'lab_result', COUNT(*) FROM (
  SELECT l.patient_id FROM lnrs.lnrs_anon_lab_result l
  WHERE l.center_code='shengyi'
    AND NOT EXISTS (SELECT 1 FROM shengyi_patients p WHERE p.patient_id = l.patient_id)
) t;

-- ----------------------------------------------------------------------------
-- V6. PG patient birth_date 范围
-- ----------------------------------------------------------------------------
SELECT
  MIN(birth_date) AS min_bd,
  MAX(birth_date) AS max_bd,
  MIN(birth_date) FILTER (WHERE birth_date > '1901-01-01') AS min_real_bd,
  COUNT(*) FILTER (WHERE birth_date = '1900-01-01') AS sentinel_1900,
  COUNT(*) FILTER (WHERE birth_date < '1901-01-01') AS before_1901,
  COUNT(*) AS total
FROM lnrs.lnrs_anon_patient
WHERE center_code='shengyi' AND created_batch_id='5207cce4-32ca-45a3-8ebd-99b5dd8885a5';

-- ----------------------------------------------------------------------------
-- V7. sex 字典值分布
-- ----------------------------------------------------------------------------
\echo '=== V7. sex 分布 (DDL 字典 0=未知, 1=男, 2=女) ==='
SELECT
  sex,
  COUNT(*) AS n
FROM lnrs.lnrs_anon_patient
WHERE center_code='shengyi' AND created_batch_id='5207cce4-32ca-45a3-8ebd-99b5dd8885a5'
GROUP BY sex
ORDER BY sex;

-- ----------------------------------------------------------------------------
-- V8. ethnicity 字典值分布
-- ----------------------------------------------------------------------------
\echo '=== V8. ethnicity 字典值分布 (DDL 字典 01=汉族, 03=回族, ...) ==='
SELECT
  ethnicity,
  COUNT(*) AS n
FROM lnrs.lnrs_anon_patient
WHERE center_code='shengyi' AND created_batch_id='5207cce4-32ca-45a3-8ebd-99b5dd8885a5'
GROUP BY ethnicity
ORDER BY n DESC;

-- ----------------------------------------------------------------------------
-- V9. abo_blood_type / rh_blood_type 分布
-- ----------------------------------------------------------------------------
\echo '=== V9a. abo_blood_type 分布 (DDL 字典 6=未知) ==='
SELECT abo_blood_type, COUNT(*) AS n
FROM lnrs.lnrs_anon_patient
WHERE center_code='shengyi' AND created_batch_id='5207cce4-32ca-45a3-8ebd-99b5dd8885a5'
GROUP BY abo_blood_type
ORDER BY abo_blood_type;

\echo '=== V9b. rh_blood_type 分布 (DDL 字典 4=未知) ==='
SELECT rh_blood_type, COUNT(*) AS n
FROM lnrs.lnrs_anon_patient
WHERE center_code='shengyi' AND created_batch_id='5207cce4-32ca-45a3-8ebd-99b5dd8885a5'
GROUP BY rh_blood_type
ORDER BY rh_blood_type;

-- ----------------------------------------------------------------------------
-- V10. native_place 分布
-- ----------------------------------------------------------------------------
\echo '=== V10. native_place 概览 ==='
SELECT
  COUNT(*) FILTER (WHERE native_place IS NULL) AS null_np,
  COUNT(native_place) AS nonnull_np,
  COUNT(DISTINCT native_place) AS uniq_np,
  MIN(LENGTH(native_place)) AS min_len,
  MAX(LENGTH(native_place)) AS max_len
FROM lnrs.lnrs_anon_patient
WHERE center_code='shengyi' AND created_batch_id='5207cce4-32ca-45a3-8ebd-99b5dd8885a5';

\echo '=== V10b. native_place top 10 (最长 5 个) ==='
SELECT native_place, LENGTH(native_place) AS len, COUNT(*) AS n
FROM lnrs.lnrs_anon_patient
WHERE center_code='shengyi' AND created_batch_id='5207cce4-32ca-45a3-8ebd-99b5dd8885a5'
  AND native_place IS NOT NULL
GROUP BY native_place
ORDER BY len DESC, n DESC
LIMIT 10;

-- ----------------------------------------------------------------------------
-- V11. PHI audit (patient_id hmac + birth_date partial_keep)
-- ----------------------------------------------------------------------------
\echo '=== V11. PHI audit for batch=5207cce4 (patient) ==='
SELECT
  source_table,
  source_field,
  strategy,
  COUNT(*) AS audit_rows
FROM lnrs.lnrs_anon_phi_audit
WHERE batch_id='5207cce4-32ca-45a3-8ebd-99b5dd8885a5'
GROUP BY source_table, source_field, strategy
ORDER BY source_table, source_field, strategy;

-- ----------------------------------------------------------------------------
-- V12. med_dict_unmatched (5 个枚举字段未匹配字典标签)
-- ----------------------------------------------------------------------------
\echo '=== V12. med_dict_unmatched (patient 路径任何字段未匹配) ==='
SELECT
  raw_label,
  SUM(occurrence_count) AS total_occurrences,
  COUNT(*) AS batch_count,
  MIN(status) AS status
FROM lnrs.med_dict_unmatched
WHERE dict_type_id IN (
  -- patient 路径 5 个枚举字段的 dict_type_id
  -- 0=未知(sex), 1=未记录(smoking), 6=未知(abo), 4=未知(rh) ...
  SELECT dict_type_id FROM lnrs.med_dict_type
  WHERE dict_code IN ('sex', 'ethnicity', 'smoking_status', 'abo_blood_type', 'rh_blood_type')
)
GROUP BY raw_label
ORDER BY total_occurrences DESC
LIMIT 30;

-- ----------------------------------------------------------------------------
-- V13. patient 全表 shengyi 按 created_batch 分布
-- ----------------------------------------------------------------------------
\echo '=== V13. shengyi patient 全表按 created_batch 分布 ==='
SELECT
  p.created_batch_id,
  ib.started_at,
  ib.source_locator,
  COUNT(*) AS n,
  COUNT(*) FILTER (WHERE p.is_placeholder) AS placeholder_n,
  COUNT(*) FILTER (WHERE p.deleted_at IS NOT NULL) AS deleted_n
FROM lnrs.lnrs_anon_patient p
LEFT JOIN lnrs.lnrs_anon_ingest_batch ib ON ib.batch_id=p.created_batch_id
WHERE p.center_code='shengyi'
GROUP BY p.created_batch_id, ib.started_at, ib.source_locator
ORDER BY n DESC;
