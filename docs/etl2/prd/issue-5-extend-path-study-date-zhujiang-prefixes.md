# Issue 5: 扩 `lnrs.path_study_date` 支持 zhujiang disk1 的 `yd*` / `new*` / `new-*` 日期前缀

## Parent

[plan-disk1-disk2-disk4-zhujiang-import.md](../plan-disk1-disk2-disk4-zhujiang-import.md)（珠江三盘导入计划 §7-2 的前置）

## What to build

`lnrs.path_study_date(text)` 是 IMMUTABLE SQL 函数，只用一条正则匹配 `/<YYYYMMDD>/<name>$`，
父目录不是纯 8 位日期时返回 NULL：

```sql
-- 现状定义
SELECT CASE
    WHEN $1 ~ '/[0-9]{4}(0[1-9]|1[0-2])(0[1-9]|[12][0-9]|3[01])/[^/]+$'
    THEN lnrs.safe_to_date((regexp_match($1, '/([0-9]{4}(0[1-9]|1[0-2])(0[1-9]|[12][0-9]|3[01]))/[^/]+$'))[1], 'YYYYMMDD')
    ELSE NULL
END;
```

zhujiang disk1 有一批目录的父目录是 `yd<YYYYMMDD>` / `new_<YYYYMMDD>` / `new-yd<YYYYMMDD>`（可带 `_<n>` 后缀），
不是纯 8 位数字 → 函数返回 NULL → 这些 study 无法参与 exam 关联
（`backend/etl2/backfill_imaging_study_exam_id.py` 的关联键依赖 `path_study_date(image_path)`）。

**实测现状（2026-09-20）**：

- `path_study_date(image_path) IS NULL`：disk1 **3,709** + disk4 **1** = **3,710 / 86,927**
- 父目录名形态 top：`new-yd20230708_0`(184) / `yd20230825`(121) / `new_20250902`(119) /
  `new_20230710`(119) / `yd20230809`(113) / `new-yd20230709`(112) / `yd20230818`(108) / …

**要做**：扩展函数识别 `yd<YYYYMMDD>`、`new_<YYYYMMDD>`、`new-yd<YYYYMMDD>`（允许尾部 `_<n>`），
返回对应日期；**不改变**既有 `YYYYMMDD` 分支的行为。这是纯 prefactor——为 Issue 6 让路。

**端到端可验证**：改造后 `path_study_date` 对 zhujiang 的 NULL 计数从 3,710 降到 0，
且改造前能解析的路径返回值**逐一不变**。

## Acceptance criteria

- [ ] `CREATE OR REPLACE FUNCTION lnrs.path_study_date(text)` 部署到 h196_3，保持 `IMMUTABLE` 属性
- [ ] 改造前先落快照：`CREATE TABLE lnrs_tmp_pathdate_before AS SELECT study_key, lnrs.path_study_date(image_path) AS d FROM lnrs.lnrs_anon_imaging_study WHERE center_code='zhujiang';`
- [ ] SQL 断言（改造后）：`SELECT COUNT(*) FROM lnrs_anon_imaging_study WHERE center_code='zhujiang' AND lnrs.path_study_date(image_path) IS NULL;` 返回 **0**
- [ ] 回归断言（双向 EXCEPT 为空）：
      `SELECT study_key, d FROM lnrs_tmp_pathdate_before EXCEPT SELECT study_key, lnrs.path_study_date(image_path) FROM lnrs.lnrs_anon_imaging_study WHERE center_code='zhujiang';`
      及其反向 EXCEPT 均为 0 行 —— 即只新增可解析的路径，不改动任何原本能解析的值
- [ ] 抽样 3 条 `yd*` 路径，人工核对返回日期 == 目录名里的 8 位数字（如 `yd20230825` → `2023-08-25`）
- [ ] 边界断言：`new-yd20230708_0` → `2023-07-08`（尾部 `_0` 不干扰）；非日期目录（如 `zhujiang_dicom`）仍返回 NULL
- [ ] 不动 `image_path` 列、不动任何数据行（纯函数改造）
- [ ] 收尾：`DROP TABLE lnrs_tmp_pathdate_before;`

## Blocked by

None - can start immediately.

## Notes for implementer

- 函数是 `IMMUTABLE`；先 `\d+` 或查 `pg_depend` 确认没有**表达式索引 / 生成列 / 物化视图**依赖它，有则改造后需 `REINDEX`。
- 该函数被 `backfill_imaging_study_exam_id.py` 的 SQL 内联调用（`backend/etl2/backfill_imaging_study_exam_id.py:85,91,119,132`），
  也在 `docs/etl2/prd/issue-1-backfill-imaging-study-exam-id.md` 的关联口径里被引用。
- disk4 那 1 条 NULL 是不同形态，单独看一眼再决定是否一并覆盖（不要为了 1 行把正则改复杂）。
- 建议实现顺序：先把 `yd|new_|new-yd` 三个前缀抽成一个 `CASE` 分支，再跑双向 EXCEPT 回归。
