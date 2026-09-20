-- =====================================================================
-- 迁移: lnrs_anon_v_imaging_study_counts 加 zero-sop 过滤守卫（2026-09-20 issue-8）
--
-- 背景：
--   zhujiang 中心有 415 个 `imaging_study.sop_count = 0` 的真空 study（issue-8）。
--   调研见 docs/etl2/verify_result/zhujiang_empty_studies_20260920.md：
--     - A 子集（真空，磁盘目录为空，dicom_series 行缺失）：415 行
--     - B 子集（陈旧计数，磁盘已空但 dicom_series 仍 file_count>0）：0 行
--   用户拍板方案 (c)：视图层过滤，不写库、不改 schema。
--
-- 设计要点：
--   * 视图守卫：`WHERE ims.sop_count > 0 OR EXISTS (SELECT 1 FROM lnrs_anon_dicom_series ds
--                                                       WHERE ds.dicom_study_uid = ims.dicom_study_uid
--                                                         AND ds.file_count > 0)`
--     - 排除 sop_count=0 且 dicom_series 行缺失 / file_count=0 的 study
--     - 保留 sop_count>0 的 study（任何 disk1/disk2/disk4 的非空 study）
--     - 保留 sop_count=0 但 dicom_series.file_count>0 的 study（理论存在但当前 zhujiang=0）
--   * CREATE OR REPLACE VIEW：幂等，重复执行安全。
--   * 不动 lnrs_anon_imaging_study / lnrs_anon_dicom_series 表数据。
--   * 不动 lnrs_anon_v_imaging_study / lnrs_anon_v_exam_full 等正交视图。
--
-- 影响：
--   - `study_total`（zhujiang）：从 86,927 降到 86,512（-415）。
--   - `total_size_bytes`：无变化（zero-sop 子集本就不贡献字节）。
--   - `series_count`/`instance_count`/`total_bytes` 分布：不变（zero-sop 行被排除）。
--   - 业务查询（API / 报表）：视图消费者透明。
--
-- 注意：
--   shengyi 中心也存在 82,994 个 sop_count=0 的 study（issue-8 调研 §6 旁路观察），
--   它们无 dicom_series 行，会被本视图守卫一并过滤。这与 zhujiang A 子集处置口径一致，
--   且属于 plan-restore-series-count.md 已认可的「part 离线 → series_count NULL」既有模式。
--   shengyi sop_count=0 根因独立（issue-X 候选），不在本迁移范围。
--
-- 回退：再次运行本文档提供的反向迁移（注释中给出）或手工 CREATE OR REPLACE VIEW
--       lnrs.lnrs_anon_v_imaging_study_counts AS (0020 原版，去掉 WHERE 子句)。
-- =====================================================================

BEGIN;

SET LOCAL search_path = lnrs, public;

CREATE OR REPLACE VIEW lnrs.lnrs_anon_v_imaging_study_counts AS
SELECT
    ims.study_key,
    ims.dicom_study_uid,
    ims.center_code,
    ims.patient_id,
    ims.anon_exam_id,
    COALESCE(s.series_count, 0)::INT        AS series_count,
    COALESCE(s.file_count, 0)::INT          AS instance_count,
    COALESCE(s.byte_size, 0)::BIGINT        AS total_bytes
FROM lnrs.lnrs_anon_imaging_study ims
LEFT JOIN lnrs.lnrs_anon_dicom_series s
       ON s.dicom_study_uid = ims.dicom_study_uid
WHERE
    ims.sop_count > 0
    OR EXISTS (
        SELECT 1
        FROM lnrs.lnrs_anon_dicom_series ds
        WHERE ds.dicom_study_uid = ims.dicom_study_uid
          AND ds.file_count > 0
    );

COMMENT ON VIEW lnrs.lnrs_anon_v_imaging_study_counts IS
    'study 维度 series 聚合（series_count / instance_count / total_bytes）；'
    'series_count ← dicom_series.series_count（NULL 时 COALESCE 0；2026-09-17 引入）；'
    'instance_count ← dicom_series.file_count（study 目录下文件数）；'
    'total_bytes ← dicom_series.byte_size。'
    '重构引入：2026-09-15 ETL-2 dicom_series 重构为 study 级；'
    '2026-09-17 series_count 列上线（实测口径与 DicomViewer.register_folder 一致）；'
    '2026-09-20 issue-8 加 zero-sop 过滤守卫（仅保留 sop_count>0 或 dicom_series.file_count>0 的 study）。';

COMMIT;

-- 验证（事务外，仅输出信息）
DO $$
DECLARE
    view_total       BIGINT;
    view_with_bytes  BIGINT;
    view_zero_bytes  BIGINT;
    ims_total        BIGINT;
    ims_zero_sop     BIGINT;
    filtered_out     BIGINT;
BEGIN
    SELECT count(*),
           count(*) FILTER (WHERE total_bytes > 0),
           count(*) FILTER (WHERE total_bytes = 0)
    INTO view_total, view_with_bytes, view_zero_bytes
    FROM lnrs.lnrs_anon_v_imaging_study_counts;

    SELECT count(*),
           count(*) FILTER (WHERE sop_count = 0)
    INTO ims_total, ims_zero_sop
    FROM lnrs.lnrs_anon_imaging_study;

    filtered_out := ims_total - view_total;

    RAISE NOTICE '视图验证: study 行 % / 有 bytes % / bytes=0 %',
        view_total, view_with_bytes, view_zero_bytes;
    RAISE NOTICE '源表对照: imaging_study 行 % / sop_count=0 行 % / 视图过滤掉 %',
        ims_total, ims_zero_sop, filtered_out;
END $$;

-- 反向回滚（保留在文件底部，方便手动执行；正常流程不会触发）
-- DROP VIEW IF EXISTS lnrs.lnrs_anon_v_imaging_study_counts;
-- 然后重放 0020 原版（无 WHERE 子句）：
--   CREATE OR REPLACE VIEW lnrs.lnrs_anon_v_imaging_study_counts AS
--   SELECT
--       ims.study_key, ims.dicom_study_uid, ims.center_code, ims.patient_id, ims.anon_exam_id,
--       COALESCE(s.series_count, 0)::INT AS series_count,
--       COALESCE(s.file_count, 0)::INT AS instance_count,
--       COALESCE(s.byte_size, 0)::BIGINT AS total_bytes
--   FROM lnrs.lnrs_anon_imaging_study ims
--   LEFT JOIN lnrs.lnrs_anon_dicom_series s
--          ON s.dicom_study_uid = ims.dicom_study_uid;
