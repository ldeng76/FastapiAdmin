-- 一次性脚本: 新增 lnrs.uid_study_date(text) — 从 DICOM StudyInstanceUID 提取内嵌检查日期
-- 见 docs/etl2/prd/issue-13-xinqiao-exam-ingest.md 与
--     docs/etl2/verify_result/xinqiao-exam-source-20260920.md §3
--
-- 背景:
--   xinqiao (03_disk) 的 image_path 形态 (img_<PID>_<SeriesUID> / <MD5>/<StudyUID>/…)
--   不含日期, lnrs.path_study_date(image_path) 对其 100% 返回 NULL。
--   但 94% 的 StudyInstanceUID (GE 等厂商) 内嵌 YYYYMMDDHHMMSSmmm 时间戳,
--   实测 31,097 个有日期 study 中 99.93% 与同患者 CT exam_date 同日 → UID 日期即检查日期。
--
-- 语义 (与调研脚本逐字一致):
--   1. 按最大连续 8+ 位数字串 (\d{8,}) 从左到右扫描;
--   2. 取该串前 8 位, lnrs.safe_to_date 严格日历校验 (2-29 非闰年等 → NULL);
--   3. 年份限定 1990..2030 (排除 UID 里 17 位设备编号等假日期,
--      如 1.2.840.113619.186.21217482123183196.20240312180240611.103 中的设备段);
--   4. 返回第一个合法日期; 全不合法 → NULL (Siemens 系 UID 无内嵌日期)。
--
-- 回归安全: 纯新增函数, 不触碰 path_study_date / safe_to_date / 视图 / 数据行。
CREATE OR REPLACE FUNCTION lnrs.uid_study_date(p_uid text)
RETURNS date
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    run text;
    d   date;
BEGIN
    IF p_uid IS NULL THEN
        RETURN NULL;
    END IF;
    FOR run IN
        SELECT t[1] AS run FROM regexp_matches(p_uid, '\d{8,}', 'g') AS t(t)
    LOOP
        d := lnrs.safe_to_date(left(run, 8), 'YYYYMMDD');
        IF d IS NOT NULL AND extract(year FROM d) BETWEEN 1990 AND 2030 THEN
            RETURN d;
        END IF;
    END LOOP;
    RETURN NULL;
END;
$$;

COMMENT ON FUNCTION lnrs.uid_study_date(text) IS
    '从 DICOM StudyInstanceUID 提取内嵌检查日期 (DATE); 取 UID 中第一个可被
     safe_to_date 严格校验且年份 1990..2030 的最大 8+ 位数字串前 8 位;
     无内嵌日期的 UID (Siemens 系) 返回 NULL。2026-09-20 (issue-13)
     为 xinqiao backfill 引入; 与 lnrs.path_study_date 配合
     (COALESCE(path_study_date(image_path), uid_study_date(dicom_study_uid)))';
