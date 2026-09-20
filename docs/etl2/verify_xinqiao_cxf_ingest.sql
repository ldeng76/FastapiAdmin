-- Issue 24 验收 SQL：cxf_archives 7,984 study 入库（ct_mapped 映射）
-- PRD: docs/etl2/prd/issue-24-xinqiao-cxf-ingest-via-ct-mapped.md
-- 执行: PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres -f docs/etl2/verify_xinqiao_cxf_ingest.sql
--
-- 前置: 已运行 backend/etl2/_issue24_ingest_xinqiao_cxf.py（--dry-run / --apply /
--       --verify 任一会重建临时映射表 lnrs.lnrs_tmp_issue24_cxf_map，
--       内容 = ct_mapped 全部 StudyUID 行的 study 侧数值 + 患者 anon 键，无 PHI）。
-- 口径: V13 复核项「只报告不修改」，mismatch > 0 时开评注（PRD 原文）。
-- 基线: zhujiang / shengyi 各计数为 2026-09-21 --apply 执行前实测（零漂移断言）。

\set ON_ERROR_STOP on

-- V1 cxf study 行数 = 7,984
SELECT 'V1' AS chk, COUNT(*) AS cxf_studies,
       CASE WHEN COUNT(*) = 7984 THEN 'PASS' ELSE 'FAIL' END AS verdict
FROM lnrs.lnrs_anon_imaging_study
WHERE center_code = 'xinqiao' AND source = 'xinqiao_3_cxf';

-- V2 cxf anon_exam_id 非空率 100%
SELECT 'V2' AS chk, COUNT(*) AS total,
       COUNT(*) FILTER (WHERE anon_exam_id IS NOT NULL) AS linked,
       CASE WHEN COUNT(*) = COUNT(*) FILTER (WHERE anon_exam_id IS NOT NULL)
            THEN 'PASS' ELSE 'FAIL' END AS verdict
FROM lnrs.lnrs_anon_imaging_study
WHERE center_code = 'xinqiao' AND source = 'xinqiao_3_cxf';

-- V3 cxf study → exam 外键完整（违例 = 0）
SELECT 'V3' AS chk, COUNT(*) AS fk_violations,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS verdict
FROM lnrs.lnrs_anon_imaging_study s
WHERE s.center_code = 'xinqiao' AND s.source = 'xinqiao_3_cxf'
  AND s.anon_exam_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM lnrs.lnrs_anon_exam e
                  WHERE e.anon_exam_id = s.anon_exam_id);

-- V4 dicom_series 与 ct_mapped 对应行 file_count / byte_size / series_count 全等
--    （file_count = len(path[]) 文件数；byte_size = total_size_bytes；
--      series_count = ct_mapped.file_count 的 PACS series 数）
SELECT 'V4' AS chk, COUNT(*) AS cxf_series,
       COUNT(*) FILTER (WHERE ds.file_count   = m.n_files
                         AND ds.byte_size     = m.total_bytes
                         AND ds.series_count  = m.series_cnt) AS all_equal,
       CASE WHEN COUNT(*) = 7984
             AND COUNT(*) FILTER (WHERE ds.file_count   = m.n_files
                                   AND ds.byte_size     = m.total_bytes
                                   AND ds.series_count  = m.series_cnt) = 7984
            THEN 'PASS' ELSE 'FAIL' END AS verdict
FROM lnrs.lnrs_anon_dicom_series ds
JOIN lnrs.lnrs_tmp_issue24_cxf_map m
  ON m.study_uid = ds.dicom_study_uid AND m.is_cxf;

-- V5 cxf StudyUID 与既有 source 的交集 = 0（跨中心重叠实测 0 的库内复核）
SELECT 'V5' AS chk, COUNT(*) AS uid_overlap,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS verdict
FROM lnrs.lnrs_anon_imaging_study a
WHERE a.center_code = 'xinqiao' AND a.source = 'xinqiao_3_cxf'
  AND EXISTS (SELECT 1 FROM lnrs.lnrs_anon_imaging_study b
              WHERE b.dicom_study_uid = a.dicom_study_uid AND b.source <> 'xinqiao_3_cxf');

-- V6 既有 xinqiao 5-sub 不动 = 33,314
SELECT 'V6' AS chk, COUNT(*) AS xq_5sub,
       CASE WHEN COUNT(*) = 33314 THEN 'PASS' ELSE 'FAIL' END AS verdict
FROM lnrs.lnrs_anon_imaging_study
WHERE center_code = 'xinqiao' AND source <> 'xinqiao_3_cxf';

-- V7 zhujiang / shengyi imaging_study 零漂移（基线 86,927 / 82,994）
SELECT 'V7' AS chk,
       COUNT(*) FILTER (WHERE center_code = 'zhujiang') AS zj,
       COUNT(*) FILTER (WHERE center_code = 'shengyi')  AS sy,
       CASE WHEN COUNT(*) FILTER (WHERE center_code = 'zhujiang') = 86927
             AND COUNT(*) FILTER (WHERE center_code = 'shengyi')  = 82994
            THEN 'PASS' ELSE 'FAIL' END AS verdict
FROM lnrs.lnrs_anon_imaging_study
WHERE center_code IN ('zhujiang', 'shengyi');

-- V8 zhujiang / shengyi exam 零漂移（基线 98,130 / 1,037,523）
SELECT 'V8' AS chk,
       COUNT(*) FILTER (WHERE center_code = 'zhujiang') AS zj,
       COUNT(*) FILTER (WHERE center_code = 'shengyi')  AS sy,
       CASE WHEN COUNT(*) FILTER (WHERE center_code = 'zhujiang') = 98130
             AND COUNT(*) FILTER (WHERE center_code = 'shengyi')  = 1037523
            THEN 'PASS' ELSE 'FAIL' END AS verdict
FROM lnrs.lnrs_anon_exam
WHERE center_code IN ('zhujiang', 'shengyi');

-- V9 zhujiang / shengyi patient 零漂移（基线 74,450 / 169,820）
SELECT 'V9' AS chk,
       COUNT(*) FILTER (WHERE center_code = 'zhujiang') AS zj,
       COUNT(*) FILTER (WHERE center_code = 'shengyi')  AS sy,
       CASE WHEN COUNT(*) FILTER (WHERE center_code = 'zhujiang') = 74450
             AND COUNT(*) FILTER (WHERE center_code = 'shengyi')  = 169820
            THEN 'PASS' ELSE 'FAIL' END AS verdict
FROM lnrs.lnrs_anon_patient
WHERE center_code IN ('zhujiang', 'shengyi');

-- V10 本批新建 patient 占位口径（sex='0' AND is_placeholder=TRUE，0 例外）。
--     注：既有 xinqiao 患者 49,908 人已在 issue-26/27 真实化为 is_placeholder=FALSE，
--     不属本单断言面（issue-24 只约束本批新建行；新建患者真实化归 issue-26）。
SELECT 'V10' AS chk, COUNT(*) AS bad_placeholder,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS verdict
FROM lnrs.lnrs_anon_patient
WHERE created_batch_id = (SELECT batch_id FROM lnrs.lnrs_anon_ingest_batch
                          WHERE source_locator LIKE '%ct_mapped.parquet%xinqiao_3_cxf'
                          ORDER BY started_at LIMIT 1)
  AND (sex <> '0' OR is_placeholder = FALSE);

-- V11 series.anon_exam_id 与 study 完全一致（0 差异）
SELECT 'V11' AS chk, COUNT(*) AS link_mismatch,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS verdict
FROM lnrs.lnrs_anon_dicom_series ds
JOIN lnrs.lnrs_anon_imaging_study s USING (dicom_study_uid)
WHERE s.center_code = 'xinqiao' AND s.source = 'xinqiao_3_cxf'
  AND ds.anon_exam_id IS DISTINCT FROM s.anon_exam_id;

-- V12 本批 ingest_batch 状态与计数（确定性 batch_id，幂等重跑 0 新增行）
SELECT 'V12' AS chk, batch_id, status, row_counts, started_at, finished_at,
       CASE WHEN status = 'success' THEN 'PASS' ELSE 'FAIL' END AS verdict
FROM lnrs.lnrs_anon_ingest_batch
WHERE batch_id = (SELECT batch_id FROM lnrs.lnrs_anon_ingest_batch
                  WHERE source_locator LIKE '%ct_mapped.parquet%xinqiao_3_cxf'
                  ORDER BY started_at LIMIT 1);

-- V13 【复核项】issue-13 已回填的 anon_exam_id 三方一致性（imaging_study ↔
--     ct_mapped StudyUID 行 ↔ exam）。mismatch 应为 0；> 0 时只列报告开评注，
--     不擅自改（PRD 原文）。明细 CSV:
--     docs/etl2/verify_result/xinqiao-cxf-exam-link-audit-20260921.csv
SELECT 'V13' AS chk,
       (SELECT COUNT(*) FROM lnrs.lnrs_anon_imaging_study s
        WHERE s.center_code = 'xinqiao' AND s.source <> 'xinqiao_3_cxf'
          AND s.anon_exam_id IS NOT NULL
          AND EXISTS (SELECT 1 FROM lnrs.lnrs_tmp_issue24_cxf_map m
                      WHERE m.study_uid = s.dicom_study_uid)) AS linked_checked,
       (SELECT COUNT(*) FROM lnrs.lnrs_anon_imaging_study s
        JOIN lnrs.lnrs_anon_patient p ON p.patient_id = s.patient_id
        LEFT JOIN lnrs.lnrs_anon_exam e ON e.anon_exam_id = s.anon_exam_id
        JOIN lnrs.lnrs_tmp_issue24_cxf_map m ON m.study_uid = s.dicom_study_uid
        WHERE s.center_code = 'xinqiao' AND s.source <> 'xinqiao_3_cxf'
          AND s.anon_exam_id IS NOT NULL
          AND (p.anon_id IS DISTINCT FROM m.patient_anon
               OR e.exam_date IS DISTINCT FROM m.exam_date)) AS mismatch,
       CASE WHEN (SELECT COUNT(*) FROM lnrs.lnrs_anon_imaging_study s
                  JOIN lnrs.lnrs_anon_patient p ON p.patient_id = s.patient_id
                  LEFT JOIN lnrs.lnrs_anon_exam e ON e.anon_exam_id = s.anon_exam_id
                  JOIN lnrs.lnrs_tmp_issue24_cxf_map m ON m.study_uid = s.dicom_study_uid
                  WHERE s.center_code = 'xinqiao' AND s.source <> 'xinqiao_3_cxf'
                    AND s.anon_exam_id IS NOT NULL
                    AND (p.anon_id IS DISTINCT FROM m.patient_anon
                         OR e.exam_date IS DISTINCT FROM m.exam_date)) = 0
            THEN 'PASS' ELSE 'REVIEW（开评注，不擅改）' END AS verdict;

-- V14 报告文本面：cxf 关联到既有 exam 的行，其报告已在库（issue-13 灌 ct.parquet）；
--     本批新建 exam（无日期兜底行）raw_text 本为空，report_text 0 行属预期
SELECT 'V14' AS chk,
       COUNT(*) FILTER (WHERE r.anon_exam_id IS NOT NULL) AS with_report,
       COUNT(*) FILTER (WHERE r.anon_exam_id IS NULL) AS without_report
FROM lnrs.lnrs_anon_imaging_study s
JOIN lnrs.lnrs_anon_exam e ON e.anon_exam_id = s.anon_exam_id
LEFT JOIN lnrs.lnrs_anon_report_text r ON r.anon_exam_id = e.anon_exam_id
WHERE s.center_code = 'xinqiao' AND s.source = 'xinqiao_3_cxf';

-- V15 全局合计（信息性，对照报告）
SELECT 'V15' AS chk,
       (SELECT COUNT(*) FROM lnrs.lnrs_anon_imaging_study
        WHERE center_code = 'xinqiao') AS xq_imaging_total,
       (SELECT COUNT(*) FROM lnrs.lnrs_anon_dicom_series) AS series_total_all,
       (SELECT COUNT(*) FROM lnrs.lnrs_anon_patient
        WHERE center_code = 'xinqiao') AS xq_patient_total;
