"""新增 lnrs.uid_study_date(text) — 从 DICOM StudyInstanceUID 提取内嵌检查日期

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-09-20

背景 (Issue 13: docs/etl2/prd/issue-13-xinqiao-exam-ingest.md)：

xinqiao (03_disk) 的 image_path 不含日期，`lnrs.path_study_date(image_path)`
对其 100% 返回 NULL，`backfill_imaging_study_exam_id.py` 的
(patient_id, |exam_date - study_date| 最近) 关联对 xinqiao 无法生效。
94% 的 StudyInstanceUID 内嵌 YYYYMMDDHHMMSSmmm 时间戳（GE 等厂商），
实测 31,097 个有日期 study 中 99.93% 与同患者 CT exam_date 同日
（见 docs/etl2/verify_result/xinqiao-exam-source-20260920.md §3）。

改造：新增纯函数 `lnrs.uid_study_date(text)`（plpgsql IMMUTABLE）：
  1. 按最大连续 8+ 位数字串从左到右扫描；
  2. 取前 8 位经 lnrs.safe_to_date 严格日历校验；
  3. 年份限定 1990..2030（排除 UID 设备编号段的假日期）；
  4. 返回第一个合法日期，否则 NULL（Siemens 系 UID 无内嵌日期）。

backfill 脚本的 study 日期表达式改为
`COALESCE(lnrs.path_study_date(image_path), lnrs.uid_study_date(dicom_study_uid))`：
zhujiang/shengyi 路径日期已覆盖（且其 UID 无内嵌日期）→ 行为 0 回归。

不动 path_study_date / safe_to_date / 视图 / 任何数据行（纯新增函数）。
"""
from collections.abc import Sequence

from alembic import op

revision: str = "m3n4o5p6q7r8"
down_revision: str | None = "l2m3n4o5p6q7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_UID_STUDY_DATE_DDL = """
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
        SELECT t[1] AS run FROM regexp_matches(p_uid, '\\d{8,}', 'g') AS t(t)
    LOOP
        d := lnrs.safe_to_date(left(run, 8), 'YYYYMMDD');
        IF d IS NOT NULL AND extract(year FROM d) BETWEEN 1990 AND 2030 THEN
            RETURN d;
        END IF;
    END LOOP;
    RETURN NULL;
END;
$$;
"""

_UID_STUDY_DATE_COMMENT = """
COMMENT ON FUNCTION lnrs.uid_study_date(text) IS
    '从 DICOM StudyInstanceUID 提取内嵌检查日期 (DATE); 取 UID 中第一个可被
     safe_to_date 严格校验且年份 1990..2030 的最大 8+ 位数字串前 8 位;
     无内嵌日期的 UID (Siemens 系) 返回 NULL。2026-09-20 (issue-13)
     为 xinqiao backfill 引入; 与 lnrs.path_study_date 配合
     (COALESCE(path_study_date(image_path), uid_study_date(dicom_study_uid)))';
"""


def upgrade() -> None:
    op.execute(_UID_STUDY_DATE_DDL)
    op.execute(_UID_STUDY_DATE_COMMENT)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS lnrs.uid_study_date(text);")
