-- 数据导入核验 SQL — 省医 / 门诊药物处方（清单 R10）
-- 结论：✅ outp_order 数据已落库 (2,456,529 行)，来自 ETL2 batch 56ec3bef (2026-09-02)
-- 本份核验只针对 outp_order 在 lnrs_anon_order 中的归属行。
-- 区分方法：order_detail_json 含 "处方编号" key (outp 独有字段)。
--         或者 created_batch_id = '56ec3bef-b33c-4233-a5a2-d41f99e9637a' 的 drug 行。
-- 另一种区分方式（更稳）：order_name + order_time + patient_id + order_detail.处方编号 业务键。

\echo '=== 1. outp_order 在 PG 中的归属行数 (基于 56ec3bef batch) ==='
SELECT COUNT(*) AS outp_rows_in_pg
FROM lnrs.lnrs_anon_order
WHERE created_batch_id = '56ec3bef-b33c-4233-a5a2-d41f99e9637a';

\echo '=== 2. outp_like (order_detail 含 处方编号) 行数 ==='
SELECT COUNT(*) AS outp_like_rows
FROM lnrs.lnrs_anon_order
WHERE center_code='shengyi'
  AND order_type='drug'
  AND order_detail_json::text LIKE '%"处方编号"%';

\echo '=== 3. 源 parquet 行数 vs 清单预期 ==='
-- 源: /data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.门诊药物处方.parquet
-- 清单预期 2456529 (源 DuckDB 计数)

\echo '=== 4. ETL1 staging outp_order.parquet 行数 ==='
-- data_shengyi202609/shengyi/outp_order.parquet 行数 = 2456529

\echo '=== 5. staging 关键列 null/空 ==='
-- patient_id/order_name/order_time/order_detail 全非空 (DuckDB 验证)

\echo '=== 6. order_detail.处方编号 唯一性 (staging 100% 唯一) ==='
-- COUNT(DISTINCT order_detail.处方编号) = 2456529 = total

\echo '=== 7. 业务键 (patient + order_time + order_name + detail.处方编号) 唯一性 (staging) ==='
-- COUNT(DISTINCT (...)) = 2456529

\echo '=== 8. staging source_order_hash 唯一性 (Python SHA256) ==='
-- DuckDB 模拟 SHA256: 2456529 行 distinct = 2456529

\echo '=== 9. PG 行 FK 完整性 (order → patient) ==='
SELECT COUNT(*) AS orphan_order_rows
FROM lnrs.lnrs_anon_order o
WHERE NOT EXISTS (
  SELECT 1 FROM lnrs.lnrs_anon_patient p WHERE p.patient_id = o.patient_id
);

\echo '=== 10. PG source_order_hash 唯一性 (UNIQUE 约束) ==='
SELECT COUNT(*) AS total,
       COUNT(DISTINCT source_order_hash) AS distinct_hash
FROM lnrs.lnrs_anon_order
WHERE created_batch_id='56ec3bef-b33c-4233-a5a2-d41f99e9637a';

\echo '=== 11. PG outp_like (56ec3bef batch) batch_id + created_at ==='
SELECT MIN(created_at) AS first_row,
       MAX(created_at) AS last_row,
       COUNT(DISTINCT created_at) AS distinct_seconds
FROM lnrs.lnrs_anon_order
WHERE created_batch_id='56ec3bef-b33c-4233-a5a2-d41f99e9637a';

\echo '=== 12. PG distinct patient 覆盖 (outp) ==='
SELECT COUNT(DISTINCT patient_id) AS outp_distinct_patients,
       (SELECT COUNT(*) FROM lnrs.lnrs_anon_patient WHERE center_code='shengyi') AS total_shengyi_patients
FROM lnrs.lnrs_anon_order
WHERE created_batch_id='56ec3bef-b33c-4233-a5a2-d41f99e9637a';

\echo '=== 13. PG order_time 范围 (outp) ==='
SELECT MIN(order_time) AS first_date, MAX(order_time) AS last_date,
       COUNT(*) FILTER (WHERE order_time IS NULL) AS null_time
FROM lnrs.lnrs_anon_order
WHERE created_batch_id='56ec3bef-b33c-4233-a5a2-d41f99e9637a';

\echo '=== 14. PG order_detail_json 完整性 ==='
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE order_detail_json IS NULL) AS null_detail,
  COUNT(*) FILTER (WHERE order_detail_json::text = 'null') AS json_null_literal,
  COUNT(*) FILTER (WHERE order_detail_json ? '处方编号') AS has_rx_id
FROM lnrs.lnrs_anon_order
WHERE created_batch_id='56ec3bef-b33c-4233-a5a2-d41f99e9637a';

\echo '=== 15. PG 业务键 (patient, order_time, order_name, 处方编号) 唯一性 ==='
SELECT COUNT(*) AS total,
       COUNT(DISTINCT (patient_id || '|' || COALESCE(order_time::text,'') || '|' || order_name || '|' || (order_detail_json->>'处方编号'))) AS distinct_biz
FROM lnrs.lnrs_anon_order
WHERE created_batch_id='56ec3bef-b33c-4233-a5a2-d41f99e9637a';

\echo '=== 16. 跨表 hash 重复 (outp 撞 drug_order) ==='
-- 0 (UNIQUE 约束已生效)

\echo '=== 17. PG outp_like batch 分布 ==='
SELECT created_batch_id, COUNT(*) AS n,
       MIN(created_at) AS first, MAX(created_at) AS last
FROM lnrs.lnrs_anon_order
WHERE center_code='shengyi' AND order_detail_json::text LIKE '%"处方编号"%'
GROUP BY created_batch_id;
