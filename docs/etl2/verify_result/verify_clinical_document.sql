-- =====================================================================
-- 核验 SQL: 省医 / 临床文档 (clinical_document) 灌库后核验
-- R12 批次 (2026-09-04 02:41:49 batch_id=d56e9cf1-1dbd-4dbc-8034-a55a3efbb541)
-- 源 5,164,052 行 → ETL1 staging 5,164,052 行 → ETL2 引擎守卫+去重 2,672,861 行 = PG total
-- =====================================================================

\echo '=== V1. shengyi clinical_document 概览 ==='
SELECT
  count(*)                                              AS total,
  count(*) FILTER (WHERE center_code='shengyi')         AS shengyi_total,
  count(DISTINCT patient_id)                            AS uniq_patient,
  count(*) FILTER (WHERE doc_date IS NOT NULL)          AS with_date,
  count(*) FILTER (WHERE doc_type IS NOT NULL AND doc_type <> '') AS with_doc_type,
  count(DISTINCT doc_type)                              AS uniq_doc_type,
  count(*) FILTER (WHERE doc_content IS NOT NULL)       AS with_content
FROM lnrs.lnrs_anon_clinical_document;

\echo
\echo '=== V1b. ingest_batch 信息 ==='
SELECT
  started_at,
  batch_id,
  source_locator,
  source_kind,
  row_counts
FROM lnrs.lnrs_anon_ingest_batch
WHERE row_counts::text ILIKE '%clinical_document%'
ORDER BY started_at DESC;

\echo
\echo '=== V2. staging hash → PG clinical_document 命中 ==='
\echo '(生成 staging hash 表)'
DROP TABLE IF EXISTS tmp_stg_hash;
CREATE TEMP TABLE tmp_stg_hash (source_doc_hash CHAR(64));
\copy tmp_stg_hash FROM '/tmp/stg_distinct_hashes.txt' WITH (FORMAT csv);

SELECT
  count(*) FILTER (WHERE pg.source_doc_hash IS NOT NULL) AS hit,
  count(*) FILTER (WHERE pg.source_doc_hash IS NULL)     AS miss,
  (SELECT count(*) FROM tmp_stg_hash)                    AS stg_total
FROM tmp_stg_hash stg
LEFT JOIN lnrs.lnrs_anon_clinical_document pg USING (source_doc_hash);

\echo
\echo '=== V3. staging hash 唯一性自检 ==='
SELECT
  (SELECT count(*) FROM tmp_stg_hash) AS stg_distinct,
  (SELECT count(*) FROM lnrs.lnrs_anon_clinical_document) AS pg_total,
  (SELECT count(*) FROM tmp_stg_hash) - (SELECT count(*) FROM lnrs.lnrs_anon_clinical_document) AS diff;

\echo
\echo '=== V4. PG 反向：所有 PG 行都属于 staging hash? ==='
SELECT
  count(*) FILTER (WHERE stg.source_doc_hash IS NOT NULL) AS pg_in_staging,
  count(*) FILTER (WHERE stg.source_doc_hash IS NULL)     AS pg_not_in_staging,
  (SELECT count(*) FROM lnrs.lnrs_anon_clinical_document) AS pg_total
FROM lnrs.lnrs_anon_clinical_document pg
LEFT JOIN tmp_stg_hash stg USING (source_doc_hash);

\echo
\echo '=== V5. PG clinical_document FK (patient 孤儿) ==='
SELECT
  count(*) FILTER (WHERE pat.patient_id IS NULL) AS orphan_patient,
  count(*) FILTER (WHERE pat.patient_id IS NOT NULL) AS valid_patient,
  (SELECT count(*) FROM lnrs.lnrs_anon_clinical_document) AS total
FROM lnrs.lnrs_anon_clinical_document cd
LEFT JOIN lnrs.lnrs_anon_patient pat
  ON pat.patient_id = cd.patient_id;

\echo
\echo '=== V6. PG clinical_document 日期分布 ==='
SELECT
  count(*) FILTER (WHERE doc_date IS NOT NULL) AS with_date,
  count(*) FILTER (WHERE doc_date IS NULL)     AS no_date,
  count(*) AS total,
  min(doc_date) AS min_date,
  max(doc_date) AS max_date
FROM lnrs.lnrs_anon_clinical_document;

\echo
\echo '=== V7. doc_type 分布 + uniq patient ==='
SELECT
  doc_type,
  count(*) AS n,
  count(DISTINCT patient_id) AS uniq_pat
FROM lnrs.lnrs_anon_clinical_document
GROUP BY 1
ORDER BY 2 DESC
LIMIT 30;

\echo
\echo '=== V8. 200 抽样 SHA256 → PG 反查 ==='
DROP TABLE IF EXISTS tmp_sample;
CREATE TEMP TABLE tmp_sample (source_doc_hash CHAR(64));
\copy tmp_sample FROM '/tmp/sample_200_hashes.txt' WITH (FORMAT csv);

SELECT
  count(*) FILTER (WHERE pg.source_doc_hash IS NOT NULL) AS hit,
  count(*) FILTER (WHERE pg.source_doc_hash IS NULL)     AS miss,
  (SELECT count(*) FROM tmp_sample)                      AS total
FROM tmp_sample s
LEFT JOIN lnrs.lnrs_anon_clinical_document pg USING (source_doc_hash);

\echo
\echo '=== V9. source_doc_hash 全局唯一性 (PG 内部) ==='
SELECT
  count(*) AS total,
  count(DISTINCT source_doc_hash) AS distinct_hashes,
  count(*) - count(DISTINCT source_doc_hash) AS dup_count
FROM lnrs.lnrs_anon_clinical_document;

\echo
\echo '=== V10. 涉及 unique patient_id ==='
SELECT count(DISTINCT patient_id) AS uniq_patient
FROM lnrs.lnrs_anon_clinical_document;

\echo
\echo '=== V11. doc_date 年份分布 (PG) ==='
SELECT
  EXTRACT(year FROM doc_date) AS yr,
  count(*) AS n
FROM lnrs.lnrs_anon_clinical_document
WHERE doc_date IS NOT NULL
GROUP BY 1
ORDER BY 1;

\echo
\echo '=== V12. doc_content 长度分布 (PG) ==='
SELECT
  CASE
    WHEN doc_content IS NULL THEN 'NULL'
    WHEN length(doc_content) = 0 THEN 'empty'
    WHEN length(doc_content) < 100 THEN '1-99'
    WHEN length(doc_content) < 500 THEN '100-499'
    WHEN length(doc_content) < 2000 THEN '500-1999'
    WHEN length(doc_content) < 10000 THEN '2000-9999'
    ELSE '10000+'
  END AS len_bucket,
  count(*) AS n
FROM lnrs.lnrs_anon_clinical_document
GROUP BY 1
ORDER BY 2 DESC;
