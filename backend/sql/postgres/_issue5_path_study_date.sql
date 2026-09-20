-- 一次性脚本: 扩展 lnrs.path_study_date 支持 zhujiang disk1 前缀
-- 见 docs/etl2/prd/issue-5-extend-path-study-date-zhujiang-prefixes.md
CREATE OR REPLACE FUNCTION lnrs.path_study_date(text)
RETURNS date
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE
        WHEN $1 ~ '/(?:yd|new_|new-yd)?([0-9]{4}(0[1-9]|1[0-2])(0[1-9]|[12][0-9]|3[01]))(_\d+)?/[^/]+$'
        THEN lnrs.safe_to_date(
                 (regexp_match($1, '/(?:yd|new_|new-yd)?([0-9]{4}(0[1-9]|1[0-2])(0[1-9]|[12][0-9]|3[01]))(_\d+)?/[^/]+$'))[1],
                 'YYYYMMDD'
             )
        ELSE NULL
    END;
$$;

COMMENT ON FUNCTION lnrs.path_study_date(text) IS
    '从 image_path 提取检查日期（DATE）；正则收紧到月日数值范围，2-29 等
     真实日历异常由 safe_to_date 兜底 → NULL。2026-09-20 (issue-5) 扩展前缀
     (?:yd|new_|new-yd)? 与后缀 (_\d+)?, 兼容 zhujiang disk1 的多种日期形态;
     2026-09-10 视图派生引入';