-- Issue 13 验收 SQL（h196_3）
-- 用法:
--   PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres \
--     -f docs/etl2/verify_xinqiao_exam.sql
-- 预期：V1>0 / V2=0 / V3=0 / V4 覆盖率 99.4%±0.5 / V5=0 / V6=0 / V7=124,045 / V10 零漂移
-- 背景: docs/etl2/prd/issue-13-xinqiao-exam-ingest.md
--       docs/etl2/verify_result/xinqiao-exam-source-20260920.md

-- V1 (PRD 断言 1): xinqiao dicom_series.anon_exam_id 非 NULL 数 > 0（之前全 NULL）
SELECT 'V1_series_with_exam' AS check, COUNT(*) AS n
FROM lnrs.lnrs_anon_dicom_series ds
JOIN lnrs.lnrs_anon_imaging_study s USING (dicom_study_uid)
WHERE s.center_code = 'xinqiao' AND ds.anon_exam_id IS NOT NULL;
-- 预期: 33,110（99.39% of 33,314；执行前预测 33,109，差 1 例为残留兜底多命中）

-- V2 (PRD 断言 2): dicom_series 外键完整性 = 0
SELECT 'V2_series_fk_orphan' AS check, COUNT(*) AS n
FROM lnrs.lnrs_anon_dicom_series ds
WHERE ds.anon_exam_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM lnrs.lnrs_anon_exam e WHERE e.anon_exam_id = ds.anon_exam_id);
-- 预期: 0

-- V3 (PRD 断言 3, 调研文档 §5 可执行口径): 无漏匹配 = 0
-- （PRD 原文子查询误用 lnrs_anon_exam.dicom_study_uid，该列不存在）
SELECT 'V3_study_unmatched_with_exam' AS check, COUNT(*) AS n
FROM lnrs.lnrs_anon_imaging_study s
WHERE s.center_code = 'xinqiao' AND s.anon_exam_id IS NULL
  AND EXISTS (
    SELECT 1 FROM lnrs.lnrs_anon_exam e
    WHERE e.patient_id = s.patient_id AND e.exam_type = 'CT'
  );
-- 预期: 0

-- V4: imaging_study 覆盖率（回填 / 总数）
SELECT 'V4_study_coverage' AS check,
       COUNT(*) AS study_total,
       COUNT(*) FILTER (WHERE anon_exam_id IS NOT NULL) AS with_exam,
       round(100.0 * COUNT(*) FILTER (WHERE anon_exam_id IS NOT NULL) / COUNT(*), 2) AS pct
FROM lnrs.lnrs_anon_imaging_study WHERE center_code = 'xinqiao';
-- 预期: 33,110 / 33,314 / 99.39%

-- V5: imaging_study 侧外键完整 = 0
SELECT 'V5_study_fk_orphan' AS check, COUNT(*) AS n
FROM lnrs.lnrs_anon_imaging_study s
WHERE s.center_code = 'xinqiao' AND s.anon_exam_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM lnrs.lnrs_anon_exam e WHERE e.anon_exam_id = s.anon_exam_id);
-- 预期: 0

-- V6: 抽样患者一致性违例 = 0（exam 必须挂在同 patient 上）
SELECT 'V6_patient_mismatch' AS check, COUNT(*) AS n
FROM lnrs.lnrs_anon_imaging_study s
JOIN lnrs.lnrs_anon_exam e ON e.anon_exam_id = s.anon_exam_id
WHERE s.center_code = 'xinqiao' AND e.patient_id <> s.patient_id;
-- 预期: 0

-- V7: xinqiao CT exam 入库量（= ct.parquet distinct exam_id）
SELECT 'V7_xinqiao_ct_exam' AS check, COUNT(*) AS n
FROM lnrs.lnrs_anon_exam WHERE center_code = 'xinqiao' AND exam_type = 'CT';
-- 预期: 124,045

-- V8: 日期距离分布（回填正确性体检；预期 ~99.9% 落在 0d）
SELECT 'V8_diff_distribution' AS check,
       count(*) FILTER (WHERE diff IS NOT NULL AND diff = 0)  AS d0,
       count(*) FILTER (WHERE diff IS NOT NULL AND diff <= 1) AS d1,
       count(*) FILTER (WHERE diff IS NOT NULL AND diff <= 7) AS d7,
       count(*) FILTER (WHERE diff IS NULL)                   AS no_study_date
FROM (
  SELECT abs(e.exam_date
             - COALESCE(lnrs.path_study_date(s.image_path),
                        lnrs.uid_study_date(s.dicom_study_uid))) AS diff
  FROM lnrs.lnrs_anon_imaging_study s
  JOIN lnrs.lnrs_anon_exam e ON e.anon_exam_id = s.anon_exam_id
  WHERE s.center_code = 'xinqiao'
) t;

-- V9: 跨中心零漂移（zhujiang/shengyi 不应被本 issue 触碰）
SELECT 'V9_other_centers' AS check, center_code,
       COUNT(*) AS study_total,
       COUNT(*) FILTER (WHERE anon_exam_id IS NOT NULL) AS with_exam
FROM lnrs.lnrs_anon_imaging_study
WHERE center_code IN ('zhujiang', 'shengyi')
GROUP BY center_code ORDER BY center_code;
-- 预期: zhujiang 86,927 / 85,483 与 shengyi 82,994 / 0（执行前基线不变）

-- V10: patient 零漂移（「不动既有数据」在 patient 表的口径；验收 5/9 延伸）
--   - 33,313 个 imaging 关联患者均为 DICOM 导入时创建的占位（created_batch_id
--     指向 DICOM 批次）；exam 灌库/重跑只更新 last_seen_batch_id，
--     created_batch_id / is_placeholder / sex 不变
--   - 16,351 个 exam-only 新占位由本 issue 首次灌库批次 4a0e0717 创建
--   - 无软删
SELECT 'V10_patient_drift' AS check,
       (SELECT count(*) FROM lnrs.lnrs_anon_patient
        WHERE center_code = 'xinqiao'
          AND created_batch_id <> '4a0e0717-ebe5-4736-be6a-17675b43cc73') AS dicom_created,
       (SELECT count(*) FROM lnrs.lnrs_anon_patient
        WHERE center_code = 'xinqiao'
          AND created_batch_id = '4a0e0717-ebe5-4736-be6a-17675b43cc73') AS exam_new,
       (SELECT count(*) FROM lnrs.lnrs_anon_patient
        WHERE center_code = 'xinqiao' AND is_placeholder AND sex = '0') AS placeholder_sex0,
       (SELECT count(*) FROM lnrs.lnrs_anon_patient
        WHERE center_code = 'xinqiao'
          AND (deleted_at IS NOT NULL OR deleted_batch_id IS NOT NULL)) AS soft_deleted;
-- 预期: dicom_created=33,313 / exam_new=16,351 / placeholder_sex0=49,664 / soft_deleted=0
