-- Issue 25 验收 SQL：xinqiao exam 报告源补全（Accession 纯报告 + 262 新检查）
-- 批次：6bb700b7-a075-4b0c-9e96-d4df4d16af1f（2026-09-21）
-- 执行：PGCLIENTENCODING='SQL_ASCII' psql "postgresql://lnrs:lnrs_pwd@127.0.0.1:5432/postgres" -f docs/etl2/verify_xinqiao_exam_source_completion.sql

-- V1 三键口径不存在重复 exam（应 0）
SELECT 'V1_dup_exam' AS item, COUNT(*) AS n FROM (
  SELECT e.patient_id, e.exam_date, coalesce(md5(rt.body_clean),'') AS k, COUNT(*) AS c
  FROM lnrs.lnrs_anon_exam e
  LEFT JOIN lnrs.lnrs_anon_report_text rt USING (anon_exam_id)
  WHERE e.center_code='xinqiao' AND e.exam_type='CT'
  GROUP BY 1,2,3 HAVING COUNT(*) > 1
) t;

-- V2 本次新增行 exam_date 非空率 100%（Accession/UID 混合键不可反查，以 batch 口径断言；应 0 / 244）
SELECT 'V2_new_null_date' AS item,
       COUNT(*) FILTER (WHERE exam_date IS NULL) AS null_date, COUNT(*) AS total
FROM lnrs.lnrs_anon_exam
WHERE center_code='xinqiao' AND exam_type='CT' AND created_batch_id='6bb700b7-a075-4b0c-9e96-d4df4d16af1f';

-- V3 xinqiao CT exam 总数 = 124,045 + 244 = 124,289
SELECT 'V3_exam_total' AS item, COUNT(*) AS n
FROM lnrs.lnrs_anon_exam WHERE center_code='xinqiao' AND exam_type='CT';

-- V4 幂等：本次 batch 行数 244；重跑后应 0 新增（脚本分类 skip_ingested=244）
SELECT 'V4_batch_rows' AS item,
       (SELECT COUNT(*) FROM lnrs.lnrs_anon_exam WHERE center_code='xinqiao' AND exam_type='CT' AND created_batch_id='6bb700b7-a075-4b0c-9e96-d4df4d16af1f') AS batch_rows,
       0 AS expected_delta_after_rerun;

-- V5 新增 244 exam 的 report_text 覆盖 = 源 raw_text 非空行数
-- （实测 262 新检查行 raw_text 全空 → 引擎守卫不写 report 行，应 0/244/0）
SELECT 'V5_rt_coverage' AS item,
       (SELECT COUNT(*) FROM lnrs.lnrs_anon_report_text
         WHERE anon_exam_id IN (SELECT anon_exam_id FROM lnrs.lnrs_anon_exam
           WHERE center_code='xinqiao' AND exam_type='CT' AND created_batch_id='6bb700b7-a075-4b0c-9e96-d4df4d16af1f')
         AND (body_clean IS NULL OR body_clean='')) AS empty_body,
       (SELECT COUNT(*) FROM lnrs.lnrs_anon_report_text
         WHERE anon_exam_id IN (SELECT anon_exam_id FROM lnrs.lnrs_anon_exam
           WHERE center_code='xinqiao' AND exam_type='CT' AND created_batch_id='6bb700b7-a075-4b0c-9e96-d4df4d16af1f')) AS rt_rows,
       (SELECT COUNT(*) FROM lnrs.lnrs_anon_exam
         WHERE center_code='xinqiao' AND exam_type='CT' AND created_batch_id='6bb700b7-a075-4b0c-9e96-d4df4d16af1f') AS new_exams;

-- V6 FK 孤儿（应全 0）
SELECT 'V6_orphans' AS item, SUM(n) AS n FROM (
  SELECT COUNT(*) AS n FROM lnrs.lnrs_anon_report_text rt
    LEFT JOIN lnrs.lnrs_anon_exam e USING (anon_exam_id) WHERE e.anon_exam_id IS NULL
  UNION ALL
  SELECT COUNT(*) FROM lnrs.lnrs_anon_exam_detail ed
    LEFT JOIN lnrs.lnrs_anon_exam e USING (anon_exam_id) WHERE e.anon_exam_id IS NULL
) t;

-- V7 batch 状态（应 success）
SELECT 'V7_batch' AS item, status, row_counts::text
FROM lnrs.lnrs_anon_ingest_batch WHERE batch_id='6bb700b7-a075-4b0c-9e96-d4df4d16af1f';

-- V8 新占位患者 244（sex='0'，is_placeholder=TRUE）
SELECT 'V8_new_patients' AS item, COUNT(*) AS n
FROM lnrs.lnrs_anon_patient
WHERE center_code='xinqiao' AND created_batch_id='6bb700b7-a075-4b0c-9e96-d4df4d16af1f';

-- V9 zhujiang / shengyi 零漂移基线（执行前后对比：zj exam=98130 sy exam=1037523 / zj rt=97039 sy rt=1031221）
SELECT 'V9_zj_sy_exam' AS item, center_code, COUNT(*) AS n
FROM lnrs.lnrs_anon_exam WHERE center_code IN ('zhujiang','shengyi') GROUP BY 2
UNION ALL
SELECT 'V9_zj_sy_rt', e.center_code, COUNT(*)
FROM lnrs.lnrs_anon_report_text rt JOIN lnrs.lnrs_anon_exam e USING (anon_exam_id)
WHERE e.center_code IN ('zhujiang','shengyi') GROUP BY 2;
