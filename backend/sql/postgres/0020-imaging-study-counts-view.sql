-- =====================================================================
-- 迁移: lnrs_anon_v_imaging_study_counts 视图（2026-09-15 重构，2026-09-17 加 series_count）
--
-- 2026-09-15 改造：dicom_series 重构为 study 级（一行 = 一个 study），
-- 原 series 级 COUNT/SUM 聚合失去意义。视图改为直接 LEFT JOIN 拿
-- byte_size / file_count 字段；series_count 当时固定为 0。
--
-- 2026-09-17 改造：dicom_series 加 series_count 列（实测 SeriesInstanceUID 去重数），
-- 视图 series_count 改为 COALESCE(s.series_count, 0)::INT；NULL 视为未实测兜底 0。
-- 详见 docs/etl2/prd/plan-restore-series-count.md。
--
-- 字段语义：
--   * series_count   ← dicom_series.series_count（NULL → 0；未实测行兜底 0）
--   * instance_count ← dicom_series.file_count（study 目录下文件数）
--   * total_bytes    ← dicom_series.byte_size（study 目录下 .dcm 字节累加）
--
-- 设计要点：
--   * LEFT JOIN imaging_study → dicom_series：dicom_series 未落库的 study
--     series_count = 0（未实测）；前端 UI 显示「0 序列」而非 NULL
--   * 无 GROUP BY：study 级已是 study 维度一对一，无需 GROUP BY
--   * 幂等：CREATE OR REPLACE VIEW
--   * 与既有 lnrs_anon_v_imaging_study / lnrs_anon_v_exam_full 正交
--   * 不动 lnrs_anon_v_imaging_study 与 lnrs_anon_v_exam_full
--
-- 性能：
--   * 单 patient 路径走 lnrs_anon_ix_imaging_patient；LEFT JOIN 一对一
--     命中 dicom_series（dicom_study_uid UNIQUE）≤ 几十行，毫秒级。
--
-- 回退: DROP VIEW lnrs.lnrs_anon_v_imaging_study_counts
--       然后回放 0020 旧版（series 级 COUNT/SUM 聚合）即可
--       或者：series_count 改回 0::INT、保留 file_count/byte_size 即可
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
       ON s.dicom_study_uid = ims.dicom_study_uid;

COMMENT ON VIEW lnrs.lnrs_anon_v_imaging_study_counts IS
    'study 维度 series 聚合（series_count / instance_count / total_bytes）；'
    'series_count ← dicom_series.series_count（NULL 时 COALESCE 0；2026-09-17 引入）；'
    'instance_count ← dicom_series.file_count（study 目录下文件数）；'
    'total_bytes ← dicom_series.byte_size。'
    '重构引入：2026-09-15 ETL-2 dicom_series 重构为 study 级；'
    '2026-09-17 series_count 列上线（实测口径与 DicomViewer.register_folder 一致）。';

-- 验证（事务外，仅输出信息）
DO $$
DECLARE
    total_rows BIGINT;
    with_bytes BIGINT;
    zero_bytes BIGINT;
BEGIN
    SELECT count(*),
           count(*) FILTER (WHERE total_bytes > 0),
           count(*) FILTER (WHERE total_bytes = 0)
    INTO total_rows, with_bytes, zero_bytes
    FROM lnrs.lnrs_anon_v_imaging_study_counts;

    RAISE NOTICE '视图验证: 总 study 行 % / 有 bytes % / bytes=0 %',
        total_rows, with_bytes, zero_bytes;
END $$;