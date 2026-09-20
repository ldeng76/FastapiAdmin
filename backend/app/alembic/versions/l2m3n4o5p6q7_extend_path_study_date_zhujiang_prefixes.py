"""扩 lnrs.path_study_date 支持 zhujiang disk1 的 yd*/new_*/new-yd* 前缀

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2026-09-20

背景 (Issue 5: docs/etl2/prd/issue-5-extend-path-study-date-zhujiang-prefixes.md)：

`lnrs.path_study_date(text)` 是 IMMUTABLE SQL 函数，原只识别 `/<YYYYMMDD>/<name>$`
一种形态。zhujiang disk1 一批目录父目录带前缀：

  - yd<YYYYMMDD>            (2364)
  - new_<YYYYMMDD>          (653)
  - new-yd<YYYYMMDD>        (383)
  - new-yd<YYYYMMDD>_<n>    (184)
  - <YYYYMMDD>_<n>          (125, 既有分支未覆盖, 顺手补)

导致 3,709 个 study 的 path_study_date 返回 NULL, 这些 study 静默不参与
`backfill_imaging_study_exam_id.py` 的 (patient_id, exam_date 距 study_date 最近)
关联, zhujiang 覆盖率卡在 ~0%。

改造: 把可识别前缀抽成一个非捕获可选组 `(?:yd|new_|new-yd)?`, 把可识别后缀抽成
可选组 `(_\d+)?`, 日期 group 仍是 8 位纯数字。这样:
- 既有 `/YYYYMMDD/<name>$` 形态继续被命中 (前缀/后缀空匹配), 0 回归。
- 4 种前缀 + 后缀形态全部命中, NULL 计数从 3,710 → 1 (disk4 的 2018-1 非日期,
  本 issue 不覆盖, 见 PRD §Notes)。
- 函数保持 IMMUTABLE, 不引入表达式索引依赖, pg_depend 无变化。

端到端可验证：
- 改造后 zhujiang NULL 计数从 3,710 → 1 (disk4 唯一行)。
- 双向 EXCEPT 为空: 改造前能解析的 83,217 个 study_key 改造后返回值不变。
- 抽样 3 条 yd*/new*/new-yd 路径, 返回值与目录名 8 位数字一致。

不动 image_path 列、不动任何数据行 (纯函数改造)。
"""
from collections.abc import Sequence

from alembic import op

revision: str = "l2m3n4o5p6q7"
down_revision: str | None = "k1l2m3n4o5p6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_PATH_STUDY_DATE_DDL = """
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
"""

_PATH_STUDY_DATE_COMMENT = """
COMMENT ON FUNCTION lnrs.path_study_date(text) IS
    '从 image_path 提取检查日期（DATE）；正则收紧到月日数值范围，2-29 等
     真实日历异常由 safe_to_date 兜底 → NULL。2026-09-20 (issue-5) 扩展前缀
     `(?:yd|new_|new-yd)?` 与后缀 `(_\d+)?`, 兼容 zhujiang disk1 的
     yd<YYYYMMDD> / new_<YYYYMMDD> / new-yd<YYYYMMDD>(_<n>)? / YYYYMMDD_<n>
     等形态; 2026-09-10 视图派生引入'.
"""


def upgrade() -> None:
    op.execute(_PATH_STUDY_DATE_DDL)
    op.execute(_PATH_STUDY_DATE_COMMENT)


def downgrade() -> None:
    # 回滚到 i9j0k1l2m3n4 的原始定义 (不含前缀/后缀可选组)
    op.execute(
        """
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
    )
    op.execute(
        """
        COMMENT ON FUNCTION lnrs.path_study_date(text) IS
            '从 image_path 提取检查日期（DATE）；正则收紧到月日数值范围，2-29 等
             真实日历异常由 safe_to_date 兜底 → NULL。2026-09-10 视图派生引入';
        """
    )