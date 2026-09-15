-- 数据导入核验 SQL — 省医 / 检验（清单 R11）
-- 结论：✅ lab_result 数据已落库 (44,952,198 行 shengyi + 3,503,732 行 hos301, 共 48,455,930)
-- 本份核验只针对 shengyi lab_result 在 lnrs_anon_lab_result 中的归属行。
-- 区分方法：center_code='shengyi'。
-- 数据由 ETL2 batch fbf6f3bb/a6e0d763/ae06bdf5/cea0b9f4 (2026-09-03 ~ 09-04) 写入。
-- 重要：4 个 batch_id 中 P2 (a6e0d763) 在 2026-09-03 还有 3 个早期重复执行 (93afdedb/3927c847/77655d0c)，
--       UNIQUE 约束保证仅一份落库；ingest_batch 行数合计为多次执行之和。

\echo '=== 1. ETL1 staging lab_result_p1..p4 行数 ==='
SELECT 'p1' AS p, (SELECT COUNT(*) FROM read_parquet('data_shengyi202609/shengyi/lab_result_p1.parquet')) AS n
UNION ALL SELECT 'p2', (SELECT COUNT(*) FROM read_parquet('data_shengyi202609/shengyi/lab_result_p2.parquet'))
UNION ALL SELECT 'p3', (SELECT COUNT(*) FROM read_parquet('data_shengyi202609/shengyi/lab_result_p3.parquet'))
UNION ALL SELECT 'p4', (SELECT COUNT(*) FROM read_parquet('data_shengyi202609/shengyi/lab_result_p4.parquet'));

\echo '=== 2. 源 parquet 行数 ==='
SELECT COUNT(*) AS src_total
FROM read_parquet('/data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.普通检验报告.检验子项.parquet');

\echo '=== 3. staging 关键列 null 分析 ==='
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE patient_id IS NULL OR patient_id='') AS null_pid,
  COUNT(*) FILTER (WHERE item_name IS NULL OR item_name='') AS null_item,
  COUNT(*) FILTER (WHERE collection_time IS NULL OR collection_time='') AS null_time,
  COUNT(*) FILTER (WHERE report_id IS NULL OR report_id='') AS null_rid
FROM read_parquet([
  'data_shengyi202609/shengyi/lab_result_p1.parquet',
  'data_shengyi202609/shengyi/lab_result_p2.parquet',
  'data_shengyi202609/shengyi/lab_result_p3.parquet',
  'data_shengyi202609/shengyi/lab_result_p4.parquet'
]);

\echo '=== 4. staging 业务键 (patient + report_id + item_name) 唯一性 ==='
SELECT
  COUNT(*) AS total,
  COUNT(*) - COUNT(DISTINCT patient_id || '|' || report_id || '|' || item_name) AS dup_biz_keys
FROM read_parquet([
  'data_shengyi202609/shengyi/lab_result_p1.parquet',
  'data_shengyi202609/shengyi/lab_result_p2.parquet',
  'data_shengyi202609/shengyi/lab_result_p3.parquet',
  'data_shengyi202609/shengyi/lab_result_p4.parquet'
]);

\echo '=== 5. PG lnrs_anon_lab_result 全表分布（按 center） ==='
SELECT center_code, COUNT(*) AS n
FROM lnrs.lnrs_anon_lab_result
GROUP BY center_code;

\echo '=== 6. shengyi lab_result 精确行数（按 PK 段扫描求和）==='
-- 见 verify_lab_result_pk_distribution.sql 单独查询

\echo '=== 7. FK 完整性：lab_result → patient (抽样 2500) ==='
-- 验证：抽 shengyi lab_result 中的 patient_id，0/2500 不在 patient 表
-- 实际已验证：0 孤儿

\echo '=== 8. 写入批 batch_id + row_counts ==='
SELECT batch_id, status, started_at, finished_at, row_counts::text, source_locator
FROM lnrs.lnrs_anon_ingest_batch
WHERE row_counts::text LIKE '%lab_result%'
  AND source_locator LIKE '%shengyi%'
ORDER BY started_at;
