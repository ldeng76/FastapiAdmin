-- =====================================================================
-- 迁移: lnrs_anon_v_imaging_study_counts 视图（2026-09-15 重构）
--
-- 2026-09-15 改造：dicom_series 重构为 study 级（一行 = 一个 study），
-- 原 series 级 COUNT/SUM 聚合失去意义。视图改为直接 LEFT JOIN 拿
-- byte_size / file_count 字段；series_count 固定为 0（不再拆分 series）。
--
-- 字段语义：
--   * series_count   = 0（study 级聚合已无 series 拆分语义）
--   * instance_count ← dicom_series.file_count（study 目录下文件数）
--   * total_bytes    ← dicom_series.byte_size（study 目录下 .dcm 字节累加）
--
-- 设计要点：
--   * LEFT JOIN imaging_study → dicom_series：dicom_series 未落库的 study
--     三列都返回 0 / NULL；前端 UI 显示「0 文件 / 0 字节」而非 NULL
--   * 无 GROUP BY：原 series 级需要按 study 分组聚合；study 级已是
--     study 维度一对一，无需 GROUP BY
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
    0::INT                                  AS series_count,
    COALESCE(s.file_count, 0)::INT          AS instance_count,
    COALESCE(s.byte_size, 0)::BIGINT        AS total_bytes
FROM lnrs.lnrs_anon_imaging_study ims
LEFT JOIN lnrs.lnrs_anon_dicom_series s
       ON s.dicom_study_uid = ims.dicom_study_uid;

COMMENT ON VIEW lnrs.lnrs_anon_v_imaging_study_counts IS
    'study 维度 series 聚合（series_count / instance_count / total_bytes）；
     series_count 固定为 0（series 级 dicom_series 字段已移除，2026-09-15 重构）；
     instance_count ← dicom_series.file_count（study 目录下文件数）；
     total_bytes ← dicom_series.byte_size。
     重构引入：2026-09-15 ETL-2 dicom_series 重构为 study 级';

COMMIT;

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