-- =============================================================================
-- R14 数据导入核验 SQL — 省医 / 检查(文本)心电图 — shengyi
-- 数据存放目录: /data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.心电图报告.检查子项.parquet
-- 预期记录数 (清单): 1,740,013 (源 parquet 行 = 1:N 子项数)
-- ETL1 staging 聚合后: 149,072 份报告 (staging.ecg_report.parquet)
-- ETL2 spec: #6 ecg_report (kind=exam_text, exam_type=ECG)
-- =============================================================================

\echo '=== V1. staging 149,072 hash 在 PG exam 中总命中 ==='
DROP TABLE IF EXISTS verify_ecg_staging_hash;
CREATE TABLE verify_ecg_staging_hash (h TEXT PRIMARY KEY);
\copy verify_ecg_staging_hash(h) FROM '/tmp/ecg_staging_hashes.txt'
SELECT COUNT(*) FILTER (WHERE pg.anon_exam_id IS NOT NULL) AS hit,
       COUNT(*) FILTER (WHERE pg.anon_exam_id IS NULL)     AS miss
FROM verify_ecg_staging_hash s
LEFT JOIN lnrs.lnrs_anon_exam pg
  ON pg.source_exam_hash = s.h AND pg.center_code = 'shengyi';

\echo
\echo '=== V2. 命中按 PG exam_type 分组 ==='
SELECT pg.exam_type, COUNT(*) AS n
FROM verify_ecg_staging_hash s
JOIN lnrs.lnrs_anon_exam pg
  ON pg.source_exam_hash = s.h AND pg.center_code = 'shengyi'
GROUP BY 1 ORDER BY 2 DESC;

\echo
\echo '=== V3. 抽样 200 行 staging SHA256 → PG 反查 ==='
DROP TABLE IF EXISTS verify_ecg_sample;
CREATE TABLE verify_ecg_sample (h TEXT PRIMARY KEY);
\copy verify_ecg_sample(h) FROM '/tmp/ecg_sample_hashes.txt'
SELECT COUNT(*) FILTER (WHERE pg.anon_exam_id IS NOT NULL) AS hit,
       COUNT(*) FILTER (WHERE pg.anon_exam_id IS NULL)     AS miss
FROM verify_ecg_sample s
LEFT JOIN lnrs.lnrs_anon_exam pg
  ON pg.source_exam_hash = s.h AND pg.center_code = 'shengyi';

\echo
\echo '=== V4. staging hash 唯一性 ==='
SELECT COUNT(*) AS total_rows,
       COUNT(DISTINCT h) AS distinct_hashes,
       MAX(c) AS max_count
FROM (
    SELECT h, COUNT(*) AS c
    FROM verify_ecg_staging_hash
    GROUP BY 1
) t;

\echo
\echo '=== V5. PG exam (ECG) 总数 vs staging hash 命中数 ==='
SELECT (SELECT COUNT(*) FROM lnrs.lnrs_anon_exam
         WHERE center_code='shengyi' AND exam_type='ECG') AS pg_ecg_total,
       (SELECT COUNT(*) FROM verify_ecg_staging_hash s
         JOIN lnrs.lnrs_anon_exam pg ON pg.source_exam_hash = s.h
                                      AND pg.center_code='shengyi'
         WHERE pg.exam_type='ECG') AS staging_hash_in_ecg,
       (SELECT COUNT(*) FROM verify_ecg_staging_hash s
         JOIN lnrs.lnrs_anon_exam pg ON pg.source_exam_hash = s.h
                                      AND pg.center_code='shengyi'
         WHERE pg.exam_type<>'ECG') AS staging_hash_other_exam_type;

\echo
\echo '=== V6. 反向: PG ECG 中来自 staging 的行数 ==='
SELECT COUNT(*) FILTER (WHERE pg.center_code='shengyi' AND pg.exam_type='ECG'
                          AND s.h IS NOT NULL) AS from_staging,
       COUNT(*) FILTER (WHERE pg.center_code='shengyi' AND pg.exam_type='ECG'
                          AND s.h IS NULL)     AS from_other
FROM lnrs.lnrs_anon_exam pg
LEFT JOIN verify_ecg_staging_hash s ON s.h = pg.source_exam_hash
WHERE pg.center_code='shengyi' AND pg.exam_type='ECG';

\echo
\echo '=== V7. PG ECG 完整性 + FK ==='
SELECT
    COUNT(*)                                                                AS total,
    COUNT(*) FILTER (WHERE patient_id IS NULL)                             AS null_patient,
    COUNT(*) FILTER (WHERE anon_visit_id IS NULL OR anon_visit_id='')      AS null_visit,
    COUNT(*) FILTER (WHERE exam_date IS NULL)                               AS null_date,
    COUNT(DISTINCT patient_id)                                              AS uniq_patient,
    COUNT(DISTINCT anon_visit_id)                                           AS uniq_visit,
    MIN(exam_date)                                                          AS min_date,
    MAX(exam_date)                                                          AS max_date
FROM lnrs.lnrs_anon_exam
WHERE center_code='shengyi' AND exam_type='ECG';

\echo
\echo '=== V8. FK 孤儿 (exam->patient) ==='
SELECT 'orphan_patient', COUNT(*)
FROM lnrs.lnrs_anon_exam e
LEFT JOIN lnrs.lnrs_anon_patient p ON p.patient_id = e.patient_id
WHERE e.center_code='shengyi' AND e.exam_type='ECG' AND p.patient_id IS NULL;

\echo
\echo '=== V9. FK 孤儿 (exam->visit) ==='
SELECT 'orphan_visit', COUNT(*)
FROM lnrs.lnrs_anon_exam e
LEFT JOIN lnrs.lnrs_anon_visit v ON v.anon_visit_id = e.anon_visit_id
WHERE e.center_code='shengyi' AND e.exam_type='ECG'
  AND e.anon_visit_id IS NOT NULL AND e.anon_visit_id <> ''
  AND v.anon_visit_id IS NULL;

\echo
\echo '=== V10. exam_detail (detail_type=ecg) 行数 ==='
SELECT detail_type, COUNT(*) AS n
FROM lnrs.lnrs_anon_exam_detail
WHERE detail_type='ecg'
GROUP BY 1;

\echo
\echo '=== V11. exam_detail 来源 ==='
SELECT COUNT(*) FILTER (WHERE s.h IS NOT NULL) AS from_staging,
       COUNT(*) FILTER (WHERE s.h IS NULL)     AS from_other
FROM lnrs.lnrs_anon_exam_detail ed
JOIN lnrs.lnrs_anon_exam e ON e.anon_exam_id = ed.anon_exam_id
LEFT JOIN verify_ecg_staging_hash s ON s.h = e.source_exam_hash
WHERE e.center_code='shengyi' AND e.exam_type='ECG' AND ed.detail_type='ecg';

\echo
\echo '=== V12. report_text 关联率 (ECG) ==='
SELECT COUNT(*) FILTER (WHERE rt.body_clean IS NOT NULL AND rt.body_clean <> '') AS has_text,
       COUNT(*) FILTER (WHERE rt.body_clean IS NULL OR rt.body_clean = '')        AS no_text
FROM lnrs.lnrs_anon_exam e
LEFT JOIN lnrs.lnrs_anon_report_text rt ON rt.anon_exam_id = e.anon_exam_id
WHERE e.center_code='shengyi' AND e.exam_type='ECG';

\echo
\echo '=== V13. ingest_batch 分布 (ECG) ==='
SELECT ib.batch_id, ib.source_kind, ib.source_locator, ib.started_at, ib.row_counts::text,
       COUNT(*) AS ecg_in_batch
FROM lnrs.lnrs_anon_ingest_batch ib
JOIN lnrs.lnrs_anon_exam e ON e.created_batch_id = ib.batch_id
WHERE e.center_code='shengyi' AND e.exam_type='ECG'
GROUP BY 1,2,3,4,5
ORDER BY ib.started_at DESC;

\echo
\echo '=== V14. source_exam_hash 全局唯一性 (ECG) ==='
SELECT COUNT(*) AS total,
       COUNT(DISTINCT source_exam_hash) AS distinct_hashes,
       COUNT(*) - COUNT(DISTINCT source_exam_hash) AS dup_count
FROM lnrs.lnrs_anon_exam
WHERE center_code='shengyi' AND exam_type='ECG';

\echo
\echo '=== 完毕 ==='
