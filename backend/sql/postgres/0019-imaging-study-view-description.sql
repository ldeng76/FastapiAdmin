-- =====================================================================
-- 迁移: lnrs_anon_v_imaging_study 视图增补 study_description / study_date
-- 依据: 2026-09-10 前端 study 列表只显示 modality，缺名称 / 日期
--       DicomViewer 已消费 study_description 字段（DicomStudy 类型契约）；
--       后端 IMAGING_STUDY_LIST_COLS 未填 → 字段恒空。
-- 日期: 2026-09-10
-- 目标: PostgreSQL 14+, schema = lnrs
--
-- 派生规则（不落表，保持方案 D「不落表」）：
--   study_date        ← image_path 倒数第二段 YYYYMMDD → DATE
--                       （典型路径：
--                          /data/wlx/DATABASE/01_disk/zhujiang_dicom/
--                          20170101/270561_1.2.840....）
--   study_description ← modality || ' ' || study_date 的可读形式
--                       例: "CT 2017-01-01"
--
-- 设计要点：
--   * 视图派生 → 老数据 0 成本覆盖，无需 ETL 重跑
--   * 路径格式不命中正则 / 非法日历日期（2-29 非闰年等）的行 → 两列返回 NULL
--   * 与 dicom_series 真 DICOM StudyDescription (0008,1030) 正交；
--     将来 ETL-2 落 DICOM 元数据后另起一个真值列，本视图降级为兜底
--   * 撞名（同一 modality + 同日多个 study）按需添加后缀；dev 实测
--     单 patient × 单日撞名 248 / 36100 = 0.69%，暂不加后缀
--
-- 性能：
--   * 单 patient 路径走 lnrs_anon_ix_imaging_patient，视图正则仅扫 ≤ 几十行
--   * 全表视图 ~3.5s（36356 行 + 冷缓存），与原视图同量级；
--     表达式索引收益不抵锁代价，本迁移不引入
--
-- 已知缺口（独立工单，不在本迁移范围）：
--   * study_total_bytes 未实现 — 依赖 lnrs_anon_dicom_series.byte_size 落库，
--     ETL-2 当前未写入该字段，需后续 ETL-2 改造 + 本视图加 SUM 聚合列。
--
-- 幂等: CREATE OR REPLACE VIEW/FUNCTION 多次执行结果一致
--
-- 回退: 还原成 0012 视图定义（12 列无派生列）+ DROP FUNCTION safe_to_date
-- =====================================================================

BEGIN;

SET LOCAL search_path = lnrs, public;

-- ---------- 1. 辅助函数：safe_to_date ----------
-- 包裹 to_date，捕获非法日历值（2-29 非闰年、4-31 等），返回 NULL 而非抛错。
-- 视图层无法 BEGIN/EXCEPTION，必须借助 plpgsql 函数；IMMUTABLE 让 PG 能把
-- 该函数 inline 进查询计划（与裸 to_date 同等优化）。

CREATE OR REPLACE FUNCTION lnrs.safe_to_date(text, text)
RETURNS date
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    result date;
BEGIN
    result := to_date($1, $2);
    RETURN result;
EXCEPTION
    WHEN others THEN
        RETURN NULL;
END;
$$;

COMMENT ON FUNCTION lnrs.safe_to_date(text, text) IS
    '包裹 to_date，非法日历值返回 NULL 不抛错；2026-09-10 视图派生引入';

-- ---------- 2. 辅助函数：path_study_date ----------
-- 把 image_path → DATE 的两步（正则守卫 + substring + safe_to_date）合并
-- 成单参 helper，视图内只用一处表达式，减少 9 份正则字面量漂移。
-- 返回 NULL 当 image_path 不符合 /YYYYMMDD/ 形态或日期非法。

CREATE OR REPLACE FUNCTION lnrs.path_study_date(text)
RETURNS date
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE
        WHEN $1 ~ '/[0-9]{4}(0[1-9]|1[0-2])(0[1-9]|[12][0-9]|3[01])/[^/]+$'
        THEN lnrs.safe_to_date(
                 (regexp_match($1, '/([0-9]{4}(0[1-9]|1[0-2])(0[1-9]|[12][0-9]|3[01]))/[^/]+$'))[1],
                 'YYYYMMDD'
             )
        ELSE NULL
    END;
$$;

COMMENT ON FUNCTION lnrs.path_study_date(text) IS
    '从 image_path 提取检查日期（DATE）；正则收紧到月日数值范围，2-29 等
     真实日历异常由 safe_to_date 兜底 → NULL。2026-09-10 视图派生引入';

-- ---------- 3. 视图：增补 study_date / study_description ----------

CREATE OR REPLACE VIEW lnrs.lnrs_anon_v_imaging_study AS
SELECT
    s.study_key,
    s.patient_id,
    p.anon_id,
    s.center_code,
    s.dicom_study_uid,
    s.modality,
    s.image_path,
    s.sop_count,
    s.source,
    s.anon_exam_id,
    s.created_at,
    s.updated_at,
    lnrs.path_study_date(s.image_path) AS study_date,
    s.modality || ' '
        || to_char(lnrs.path_study_date(s.image_path), 'YYYY-MM-DD')
        AS study_description
FROM lnrs.lnrs_anon_imaging_study s
JOIN lnrs.lnrs_anon_patient p ON p.patient_id = s.patient_id;

COMMENT ON VIEW lnrs.lnrs_anon_v_imaging_study IS
    '影像研究桥接视图（patient_id ↔ 影像绝对路径，仅脱敏 ID）；'
    'study_description / study_date 由 image_path 末两级父目录派生（YYYYMMDD → DATE），'
    '与 dicom_series 真 DICOM StudyDescription 正交，作为兜底；'
    'study_total_bytes 暂未实现（依赖 dicom_series.byte_size 落库）';

COMMIT;

-- 验证（事务外，仅输出信息）
DO $$
DECLARE
    total_rows BIGINT;
    with_desc  BIGINT;
    with_date  BIGINT;
BEGIN
    SELECT count(*),
           count(study_description),
           count(study_date)
    INTO total_rows, with_desc, with_date
    FROM lnrs.lnrs_anon_v_imaging_study;

    RAISE NOTICE '视图验证: 总行 % / 有 study_description % / 有 study_date %',
        total_rows, with_desc, with_date;
END $$;
