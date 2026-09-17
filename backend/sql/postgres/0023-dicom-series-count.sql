-- =====================================================================
-- 迁移: lnrs_anon_dicom_series 加 series_count 列（2026-09-17）
--
-- 背景：
--   2026-09-15 将 dicom_series 重构为 study 级（一行 = 一个 study）后，
--   ETL 只做 iterdir + stat（不解析 DICOM header），导致「一个 Study 下
--   有几个 Series」在系统内无任何数据来源。
--   视图 v_imaging_study_counts.series_count 因此被硬编码为 0。
--
--   本迁移为 lnrs_anon_dicom_series 加 series_count INT NULL 列（NULL = 未实测）：
--   1. ETL 落库时实测（register_folder 去重 SeriesInstanceUID，跳过非图像模态）；
--   2. 存量回填脚本扫描在线目录补值；
--   3. 视图与 API 输出真实值（未实测行 COALESCE 0 兜底）。
--
-- 字段语义：
--   * series_count INT NULL
--       NULL = 未实测（目录离线 / ETL 未跑 / 落库早于本迁移）；
--       0   = 已实测，目录在线且无合法 DICOM 图像 / 无图像模态文件；
--       N   = 已实测，去重 SeriesInstanceUID 计数 = N（N >= 1）。
--     注意与 file_count（目录内全部文件数）语义不同。
--
-- 设计要点：
--   * ADD COLUMN IF NOT EXISTS：幂等，重复执行安全。
--   * CHECK：series_count IS NULL OR series_count >= 0（不强制非空，保留 NULL）。
--   * VIEW 重写：series_count 改 COALESCE(s.series_count, 0)::INT。
--   * COMMENT ON VIEW 同步更新：旧"series_count 固定为 0"断言移除。
--   * 不动 lnrs_anon_v_imaging_study / lnrs_anon_v_exam_full 等正交视图。
--
-- 部署：dev_h1963 直接 psql 执行；其他环境按项目惯例手工同步。
--
-- 回退：
--   1) DROP VIEW lnrs.lnrs_anon_v_imaging_study_counts; -- （先恢复视图）
--   2) 重放 0020 旧版（series_count 固定 0::INT）；
--   3) ALTER TABLE lnrs.lnrs_anon_dicom_series DROP COLUMN series_count;
--   4) 代码层 anon_medical_query.py:621 改回 literal(0).label("series_count")。
-- =====================================================================

BEGIN;

SET LOCAL search_path = lnrs, public;

-- 1) 加 series_count 列（NULL = 未实测，CHECK 限制非负整数）
ALTER TABLE lnrs.lnrs_anon_dicom_series
    ADD COLUMN IF NOT EXISTS series_count INT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'lnrs_anon_ck_dicom_series_series_count'
          AND conrelid = 'lnrs.lnrs_anon_dicom_series'::regclass
    ) THEN
        ALTER TABLE lnrs.lnrs_anon_dicom_series
            ADD CONSTRAINT lnrs_anon_ck_dicom_series_series_count
            CHECK (series_count IS NULL OR series_count >= 0);
    END IF;
END $$;

-- 2) 重写视图：series_count 走 dicom_series.series_count（COALESCE 0 兜底）
CREATE OR REPLACE VIEW lnrs.lnrs_anon_v_imaging_study_counts AS
SELECT
    ims.study_key,
    ims.dicom_study_uid,
    ims.center_code,
    ims.patient_id,
    ims.anon_exam_id,
    COALESCE(s.series_count, 0)::INT    AS series_count,
    COALESCE(s.file_count, 0)::INT      AS instance_count,
    COALESCE(s.byte_size, 0)::BIGINT    AS total_bytes
FROM lnrs.lnrs_anon_imaging_study ims
LEFT JOIN lnrs.lnrs_anon_dicom_series s
       ON s.dicom_study_uid = ims.dicom_study_uid;

-- 3) 视图 COMMENT 更新：移除旧"series_count 固定为 0"断言
COMMENT ON VIEW lnrs.lnrs_anon_v_imaging_study_counts IS
    'study 维度 series 聚合（series_count / instance_count / total_bytes）；'
    'series_count ← dicom_series.series_count（2026-09-17 引入，未实测行 COALESCE 0）；'
    'instance_count ← dicom_series.file_count（study 目录下文件数）；'
    'total_bytes ← dicom_series.byte_size。'
    '重构引入：2026-09-15 ETL-2 dicom_series 重构为 study 级；'
    '2026-09-17 series_count 列上线 + 实测口径（register_folder 去重 SeriesInstanceUID）。';

COMMIT;

-- 验证（事务外，仅输出信息）
DO $$
DECLARE
    total_rows     BIGINT;
    with_series    BIGINT;
    null_series    BIGINT;
    view_total     BIGINT;
    view_with_sc   BIGINT;
BEGIN
    SELECT count(*),
           count(*) FILTER (WHERE series_count IS NOT NULL),
           count(*) FILTER (WHERE series_count IS NULL)
    INTO total_rows, with_series, null_series
    FROM lnrs.lnrs_anon_dicom_series;

    SELECT count(*),
           count(*) FILTER (WHERE series_count > 0)
    INTO view_total, view_with_sc
    FROM lnrs.lnrs_anon_v_imaging_study_counts;

    RAISE NOTICE 'dicom_series 列验证: 总 % / 已实测 % / 未实测(NULL) %',
        total_rows, with_series, null_series;
    RAISE NOTICE '视图验证: 总 study 行 % / series_count > 0 的 %',
        view_total, view_with_sc;
END $$;