-- =============================================================
-- shengyi 实体肿瘤基因检测报告导入验证 SQL（2026-09-14 实施）
-- 数据库：127.0.0.1:5432/postgres，schema=lnrs
-- 用法：PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres -f verify_shengyi_genetic.sql
-- =============================================================

\set ON_ERROR_STOP on

-- 1. Genetic exam 总数
\echo ''
\echo '=== 1. Genetic exam 总数 ==='
SELECT
  count(*)                                           AS exam_total,
  count(*) FILTER (WHERE patient_id IS NOT NULL)     AS non_null_pid,
  count(*) FILTER (WHERE exam_date IS NOT NULL)      AS non_null_date,
  count(*) FILTER (WHERE source_exam_hash ~ '^SYG-') AS syg_exam,
  count(*) FILTER (WHERE source_exam_hash !~ '^SYG-') AS real_id_exam
FROM lnrs.lnrs_anon_exam
WHERE center_code = 'shengyi' AND exam_type = 'Genetic';

-- 2. 旧 SYG hash 是否清理干净
\echo ''
\echo '=== 2. 旧 SYG hash 是否清理（dirty 数据监测）==='
SELECT
  CASE
    WHEN source_exam_hash ~ '^5b3a9ec3' THEN 'old-SYG-1-dirty'
    WHEN source_exam_hash ~ '^0af0c428' THEN 'old-SYG-2-dirty'
    ELSE 'clean'
  END AS bucket,
  count(*) AS cnt
FROM lnrs.lnrs_anon_exam
WHERE center_code = 'shengyi' AND exam_type = 'Genetic'
GROUP BY 1 ORDER BY cnt DESC;

-- 3. 真单号 hash 抽样
\echo ''
\echo '=== 3. 真单号 hash 抽样（前 5 行）==='
SELECT
  e.source_exam_hash,
  'PG 不存原始 report_id 字面，需 staging 比对脚本验证 SHA256 一致性' AS note
FROM lnrs.lnrs_anon_exam e
WHERE e.center_code = 'shengyi' AND e.exam_type = 'Genetic'
  AND e.source_exam_hash !~ '^5b3a9ec3|^0af0c428'
LIMIT 5;

-- 4. exam_detail 行数 + variants 6 bucket 覆盖率
--    注：detail_json 实际结构为 {"variants": {"snv": [...], "cnv": [...], ...}}
\echo ''
\echo '=== 4. exam_detail 行数 + variants 6 bucket 覆盖率 ==='
SELECT
  count(*)                                                       AS detail_total,
  count(*) FILTER (WHERE d.detail_json->'variants' ? 'snv')      AS has_snv,
  count(*) FILTER (WHERE d.detail_json->'variants' ? 'cnv')      AS has_cnv,
  count(*) FILTER (WHERE d.detail_json->'variants' ? 'indel')    AS has_indel,
  count(*) FILTER (WHERE d.detail_json->'variants' ? 'fusion')   AS has_fusion,
  count(*) FILTER (WHERE d.detail_json->'variants' ? 'other')    AS has_other,
  count(*) FILTER (WHERE d.detail_json->'variants' ? 'drug_ref') AS has_drugref
FROM lnrs.lnrs_anon_exam_detail d
JOIN lnrs.lnrs_anon_exam e ON e.anon_exam_id = d.anon_exam_id
WHERE e.center_code = 'shengyi' AND e.exam_type = 'Genetic';

-- 5. variants 各 bucket 子项数（null-safe）
SELECT
  round(avg(CASE WHEN jsonb_typeof(d.detail_json->'variants'->'snv') = 'array'
                 THEN jsonb_array_length(d.detail_json->'variants'->'snv') ELSE 0 END), 2) AS avg_snv,
  max(CASE WHEN jsonb_typeof(d.detail_json->'variants'->'snv') = 'array'
            THEN jsonb_array_length(d.detail_json->'variants'->'snv') ELSE 0 END) AS max_snv,
  round(avg(CASE WHEN jsonb_typeof(d.detail_json->'variants'->'cnv') = 'array'
                 THEN jsonb_array_length(d.detail_json->'variants'->'cnv') ELSE 0 END), 2) AS avg_cnv,
  max(CASE WHEN jsonb_typeof(d.detail_json->'variants'->'cnv') = 'array'
            THEN jsonb_array_length(d.detail_json->'variants'->'cnv') ELSE 0 END) AS max_cnv,
  round(avg(CASE WHEN jsonb_typeof(d.detail_json->'variants'->'indel') = 'array'
                 THEN jsonb_array_length(d.detail_json->'variants'->'indel') ELSE 0 END), 2) AS avg_indel,
  max(CASE WHEN jsonb_typeof(d.detail_json->'variants'->'indel') = 'array'
            THEN jsonb_array_length(d.detail_json->'variants'->'indel') ELSE 0 END) AS max_indel,
  round(avg(CASE WHEN jsonb_typeof(d.detail_json->'variants'->'fusion') = 'array'
                 THEN jsonb_array_length(d.detail_json->'variants'->'fusion') ELSE 0 END), 2) AS avg_fusion,
  max(CASE WHEN jsonb_typeof(d.detail_json->'variants'->'fusion') = 'array'
            THEN jsonb_array_length(d.detail_json->'variants'->'fusion') ELSE 0 END) AS max_fusion,
  round(avg(CASE WHEN jsonb_typeof(d.detail_json->'variants'->'other') = 'array'
                 THEN jsonb_array_length(d.detail_json->'variants'->'other') ELSE 0 END), 2) AS avg_other,
  max(CASE WHEN jsonb_typeof(d.detail_json->'variants'->'other') = 'array'
            THEN jsonb_array_length(d.detail_json->'variants'->'other') ELSE 0 END) AS max_other,
  round(avg(CASE WHEN jsonb_typeof(d.detail_json->'variants'->'drug_ref') = 'array'
                 THEN jsonb_array_length(d.detail_json->'variants'->'drug_ref') ELSE 0 END), 2) AS avg_drugref,
  max(CASE WHEN jsonb_typeof(d.detail_json->'variants'->'drug_ref') = 'array'
            THEN jsonb_array_length(d.detail_json->'variants'->'drug_ref') ELSE 0 END) AS max_drugref
FROM lnrs.lnrs_anon_exam_detail d
JOIN lnrs.lnrs_anon_exam e ON e.anon_exam_id = d.anon_exam_id
WHERE e.center_code = 'shengyi' AND e.exam_type = 'Genetic';


-- 6. patient FK 完整性
\echo ''
\echo '=== 6. patient_id FK 完整性 ==='
SELECT
  count(*) FILTER (WHERE NOT EXISTS (
    SELECT 1 FROM lnrs.lnrs_anon_patient p
     WHERE p.patient_id = e.patient_id AND p.center_code = e.center_code
  )) AS orphan_exam,
  count(*) FILTER (WHERE EXISTS (
    SELECT 1 FROM lnrs.lnrs_anon_patient p
     WHERE p.patient_id = e.patient_id AND p.center_code = e.center_code
  )) AS linked_exam
FROM lnrs.lnrs_anon_exam e
WHERE e.center_code = 'shengyi' AND e.exam_type = 'Genetic';

-- 7. anon_visit_id FK 完整性（含空字符串判定）
\echo ''
\echo '=== 7. anon_visit_id FK 完整性（含空字符串判定）==='
SELECT
  count(*) FILTER (WHERE e.anon_visit_id IS NULL OR e.anon_visit_id = '') AS empty_visit,
  count(*) FILTER (WHERE e.anon_visit_id <> '' AND NOT EXISTS (
    SELECT 1 FROM lnrs.lnrs_anon_visit v
     WHERE v.anon_visit_id = e.anon_visit_id AND v.center_code = e.center_code
  )) AS orphan_visit,
  count(*) FILTER (WHERE e.anon_visit_id <> '' AND EXISTS (
    SELECT 1 FROM lnrs.lnrs_anon_visit v
     WHERE v.anon_visit_id = e.anon_visit_id AND v.center_code = e.center_code
  )) AS linked_visit
FROM lnrs.lnrs_anon_exam e
WHERE e.center_code = 'shengyi' AND e.exam_type = 'Genetic';

-- 8. exam_date 反查命中
\echo ''
\echo '=== 8. exam_date 反查命中 ==='
SELECT
  count(*) FILTER (WHERE exam_date IS NOT NULL) AS has_date,
  count(*) FILTER (WHERE exam_date IS NULL)      AS null_date,
  min(exam_date) AS min_date,
  max(exam_date) AS max_date
FROM lnrs.lnrs_anon_exam
WHERE center_code = 'shengyi' AND exam_type = 'Genetic';

-- 9. UNIQUE 约束校验（无重复 hash）
\echo ''
\echo '=== 9. source_exam_hash 全局唯一性 ==='
SELECT count(*) AS dup_hash_count
FROM (
  SELECT source_exam_hash, count(*) c
  FROM lnrs.lnrs_anon_exam
  WHERE center_code = 'shengyi' AND exam_type = 'Genetic'
  GROUP BY 1 HAVING count(*) > 1
) t;

-- 10. 涉及患者数 + 就诊数
\echo ''
\echo '=== 10. 涉及的患者/就诊维度 ==='
SELECT
  count(DISTINCT patient_id)                 AS unique_patients,
  count(DISTINCT NULLIF(anon_visit_id, '')) AS unique_visits
FROM lnrs.lnrs_anon_exam
WHERE center_code = 'shengyi' AND exam_type = 'Genetic';

-- 11. batch 分布
\echo ''
\echo '=== 11. import batch 分布 ==='
SELECT
  created_batch_id,
  count(*) AS exam_count,
  min(created_at) AS first_seen,
  max(created_at) AS last_seen
FROM lnrs.lnrs_anon_exam
WHERE center_code = 'shengyi' AND exam_type = 'Genetic'
GROUP BY 1 ORDER BY first_seen;

-- 12. 真单号 exam 详情样例
\echo ''
\echo '=== 12. 真单号 exam 详情样例（detail_json 截断显示）==='
SELECT
  e.anon_exam_id,
  e.patient_id,
  e.exam_date,
  e.source_exam_hash,
  substr(d.detail_json::text, 1, 500) || '...' AS variants_preview
FROM lnrs.lnrs_anon_exam e
JOIN lnrs.lnrs_anon_exam_detail d ON d.anon_exam_id = e.anon_exam_id
WHERE e.center_code = 'shengyi' AND e.exam_type = 'Genetic'
  AND e.source_exam_hash !~ '^5b3a9ec3|^0af0c428'
LIMIT 1;

-- 13. 跨表 join 抽样
\echo ''
\echo '=== 13. 跨表 join 抽样（exam + patient + visit_detail）==='
SELECT
  e.anon_exam_id,
  e.patient_id,
  p.sex,
  p.birth_date,
  e.anon_visit_id,
  vd.admission_time,
  vd.visit_category,
  e.exam_date,
  e.source_exam_hash
FROM lnrs.lnrs_anon_exam e
JOIN lnrs.lnrs_anon_patient p ON p.patient_id = e.patient_id AND p.center_code = e.center_code
LEFT JOIN lnrs.lnrs_anon_visit_detail vd ON vd.anon_visit_id = e.anon_visit_id AND vd.center_code = e.center_code
WHERE e.center_code = 'shengyi' AND e.exam_type = 'Genetic'
  AND e.source_exam_hash !~ '^5b3a9ec3|^0af0c428'
LIMIT 3;

-- 14. 总览（CSV 友好格式）
\echo ''
\echo '=== 14. 总览（CSV 友好格式）==='
SELECT 'genetic_exam_total'            AS metric, count(*)::text AS value
FROM lnrs.lnrs_anon_exam WHERE center_code='shengyi' AND exam_type='Genetic'
UNION ALL SELECT 'genetic_detail_total', count(*)::text
FROM lnrs.lnrs_anon_exam_detail d JOIN lnrs.lnrs_anon_exam e ON e.anon_exam_id=d.anon_exam_id
WHERE e.center_code='shengyi' AND e.exam_type='Genetic'
UNION ALL SELECT 'old_syg_dirty_count', count(*)::text
FROM lnrs.lnrs_anon_exam
WHERE center_code='shengyi' AND exam_type='Genetic'
  AND (source_exam_hash ~ '^5b3a9ec3' OR source_exam_hash ~ '^0af0c428')
UNION ALL SELECT 'detail_has_snv_bucket', count(*)::text
FROM lnrs.lnrs_anon_exam_detail d JOIN lnrs.lnrs_anon_exam e ON e.anon_exam_id=d.anon_exam_id
WHERE e.center_code='shengyi' AND e.exam_type='Genetic'
  AND d.detail_json->'variants' ? 'snv'
UNION ALL SELECT 'detail_has_cnv_bucket', count(*)::text
FROM lnrs.lnrs_anon_exam_detail d JOIN lnrs.lnrs_anon_exam e ON e.anon_exam_id=d.anon_exam_id
WHERE e.center_code='shengyi' AND e.exam_type='Genetic'
  AND d.detail_json->'variants' ? 'cnv'
UNION ALL SELECT 'detail_has_indel_bucket', count(*)::text
FROM lnrs.lnrs_anon_exam_detail d JOIN lnrs.lnrs_anon_exam e ON e.anon_exam_id=d.anon_exam_id
WHERE e.center_code='shengyi' AND e.exam_type='Genetic'
  AND d.detail_json->'variants' ? 'indel'
UNION ALL SELECT 'detail_has_fusion_bucket', count(*)::text
FROM lnrs.lnrs_anon_exam_detail d JOIN lnrs.lnrs_anon_exam e ON e.anon_exam_id=d.anon_exam_id
WHERE e.center_code='shengyi' AND e.exam_type='Genetic'
  AND d.detail_json->'variants' ? 'fusion'
UNION ALL SELECT 'detail_has_other_bucket', count(*)::text
FROM lnrs.lnrs_anon_exam_detail d JOIN lnrs.lnrs_anon_exam e ON e.anon_exam_id=d.anon_exam_id
WHERE e.center_code='shengyi' AND e.exam_type='Genetic'
  AND d.detail_json->'variants' ? 'other'
UNION ALL SELECT 'detail_has_drugref_bucket', count(*)::text
FROM lnrs.lnrs_anon_exam_detail d JOIN lnrs.lnrs_anon_exam e ON e.anon_exam_id=d.anon_exam_id
WHERE e.center_code='shengyi' AND e.exam_type='Genetic'
  AND d.detail_json->'variants' ? 'drug_ref'
UNION ALL SELECT 'orphan_exam_pid', count(*)::text
FROM lnrs.lnrs_anon_exam e WHERE e.center_code='shengyi' AND e.exam_type='Genetic'
  AND NOT EXISTS (SELECT 1 FROM lnrs.lnrs_anon_patient p WHERE p.patient_id=e.patient_id AND p.center_code=e.center_code)
UNION ALL SELECT 'empty_anon_visit_id', count(*)::text
FROM lnrs.lnrs_anon_exam e WHERE e.center_code='shengyi' AND e.exam_type='Genetic'
  AND (e.anon_visit_id IS NULL OR e.anon_visit_id = '')
UNION ALL SELECT 'null_exam_date', count(*)::text
FROM lnrs.lnrs_anon_exam WHERE center_code='shengyi' AND exam_type='Genetic' AND exam_date IS NULL
UNION ALL SELECT 'unique_patients', count(DISTINCT patient_id)::text
FROM lnrs.lnrs_anon_exam WHERE center_code='shengyi' AND exam_type='Genetic'
UNION ALL SELECT 'unique_visits', count(DISTINCT NULLIF(anon_visit_id, ''))::text
FROM lnrs.lnrs_anon_exam WHERE center_code='shengyi' AND exam_type='Genetic'
UNION ALL SELECT 'dup_hash_count', count(*)::text
FROM (SELECT source_exam_hash FROM lnrs.lnrs_anon_exam
       WHERE center_code='shengyi' AND exam_type='Genetic'
       GROUP BY 1 HAVING count(*) > 1) t
ORDER BY 1;

\echo ''
\echo '=== 验证完成 ==='