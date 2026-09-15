"""lnrs_anon_v_imaging_study 视图增补 study_description / study_date

Revision ID: i9j0k1l2m3n4
Revises: h8c9d0e1f2a3
Create Date: 2026-09-10

背景：前端 DicomViewer 已消费 DicomStudy.study_description 字段；
后端 IMAGING_STUDY_LIST_COLS（原列表）未带该列，前端 study 列表只显示
modality，缺名称 / 日期。

本迁移：
1. CREATE OR REPLACE FUNCTION lnrs.safe_to_date(text, text) — 包裹 to_date，
   非法日历值（2-29 非闰年、4-31 等）返回 NULL 而非抛错。视图层无
   BEGIN/EXCEPTION，必须借助 plpgsql 函数；IMMUTABLE 让 PG 能 inline 进查询计划。
2. CREATE OR REPLACE FUNCTION lnrs.path_study_date(text) — 把 image_path →
   DATE 的两步（正则守卫 + substring + safe_to_date）合并为单参 helper，
   视图内每条派生列只调用一次，减少正则字面量漂移。
3. CREATE OR REPLACE VIEW lnrs.lnrs_anon_v_imaging_study 在原 12 列基础上
   增补 study_date (DATE) 与 study_description (TEXT)，由 image_path
   末两级父目录派生。
4. 不落表（保持方案 D「不落表」），不写 lnrs_anon_imaging_study 表。
5. 不引入表达式索引（dev 实测收益 15% buffer reads，不抵 ACCESS EXCLUSIVE
   锁代价，单 patient 路径走 lnrs_anon_ix_imaging_patient 已足够）。

验证：dev (h196_3) lnrs_anon_imaging_study 36356 行，路径正则命中率 100%；
单 patient × 单日撞名 248 / 36100 = 0.69%，未引入后缀。

已知缺口（独立工单）：
* study_total_bytes 未实现 — 依赖 lnrs_anon_dicom_series.byte_size 落库，
  ETL-2 当前未写入；本视图后续加 SUM(byte_size) 列即可。
"""

from collections.abc import Sequence

from alembic import op

revision: str = "i9j0k1l2m3n4"
down_revision: str | None = "h8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_SAFE_TO_DATE_DDL = """
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
"""

_PATH_STUDY_DATE_DDL = """
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
"""

_VIEW_DDL = """
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
"""

_VIEW_DDL_DOWNGRADE = """
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
    s.updated_at
FROM lnrs.lnrs_anon_imaging_study s
JOIN lnrs.lnrs_anon_patient p ON p.patient_id = s.patient_id;
"""

_DROP_FUNCTIONS = """
DROP FUNCTION IF EXISTS lnrs.path_study_date(text);
DROP FUNCTION IF EXISTS lnrs.safe_to_date(text, text);
"""


def upgrade() -> None:
    op.execute(_SAFE_TO_DATE_DDL)
    op.execute(_PATH_STUDY_DATE_DDL)
    op.execute(_VIEW_DDL)


def downgrade() -> None:
    op.execute(_VIEW_DDL_DOWNGRADE)
    op.execute(_DROP_FUNCTIONS)
