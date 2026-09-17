-- =====================================================================
-- 迁移: lnrs_anon_dicom_series.anon_exam_id 允许 NULL（2026-09-17）
--
-- 背景：
--   0023-dicom-series-count.sql 加了 series_count 列；
--   backfill_dicom_series_count.py（方案 C 实施）走 register_folder 直接
--   INSERT/UPDATE dicom_series.series_count，不依赖 ETL-2 已有 exam 关联。
--
--   原约束：anon_exam_id VARCHAR(40) NOT NULL REFERENCES lnrs_anon_exam。
--   改约束：DROP NOT NULL，保留 FK（NULL 不被 FK 检查）。
--
-- 设计要点：
--   * ALTER COLUMN ... DROP NOT NULL：幂等（重复执行 noop）。
--   * 保留 FK 约束：NULL 值不被 FK 检查；非 NULL 值仍需 exam 存在，
--     ETL-2 主路径（_upsert_dicom_byte_size_for_study 走 exam_id 非空 study）
--     语义不变。
--   * 0006 §7 + 0020 同步更新：移除"NOT NULL"陈述。
--
-- 回退：
--   UPDATE lnrs.lnrs_anon_dicom_series SET anon_exam_id = '<some_existing_exam>'
--   WHERE anon_exam_id IS NULL;  -- 必须先填回，否则 ALTER NOT NULL 会失败
--   ALTER TABLE lnrs.lnrs_anon_dicom_series ALTER COLUMN anon_exam_id SET NOT NULL;
-- =====================================================================

BEGIN;

SET LOCAL search_path = lnrs, public;

ALTER TABLE lnrs.lnrs_anon_dicom_series
    ALTER COLUMN anon_exam_id DROP NOT NULL;

-- 同步 COMMENT（移除 NOT NULL 表述）
COMMENT ON TABLE lnrs.lnrs_anon_dicom_series IS
    '影像研究级元数据（一行 = 一个 study；2026-09-15 重构自 series 级，'
    '2026-09-17 加 series_count，2026-09-17 anon_exam_id 允许 NULL）。'
    'file_count = study 目录下文件数；byte_size = 累加目录下所有 .dcm 的 st_size；'
    'series_count = 实测 SeriesInstanceUID 去重计数（NULL = 未实测）；'
    'anon_exam_id NULL = 无 exam 关联（仅 series_count 落库场景，回填脚本产物），'
    '非 NULL = exam 关联（ETL-2 主路径产物）。';

COMMIT;

-- 验证（事务外）
DO $$
DECLARE
    nullable_info TEXT;
BEGIN
    SELECT is_nullable INTO nullable_info
    FROM information_schema.columns
    WHERE table_schema = 'lnrs'
      AND table_name = 'lnrs_anon_dicom_series'
      AND column_name = 'anon_exam_id';
    RAISE NOTICE 'dicom_series.anon_exam_id is_nullable = %', nullable_info;
END $$;