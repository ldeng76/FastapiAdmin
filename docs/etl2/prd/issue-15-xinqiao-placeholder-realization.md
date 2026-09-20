# Issue 15: 新桥占位真实化 — 关联 exam 后回填人口学 + `is_placeholder=FALSE`

## Parent

[plan-xinqiao-disk03-import.md](../plan-xinqiao-disk03-import.md)（§7-3）

## What to build

新桥 33,313 patient 当前 `is_placeholder=TRUE`（plan-xinqiao §0.6-6，与 zhujiang 同口径）。

issue-13 exam 灌库后，从 exam 行拿 `sex` / `birth_date`（与 zhujiang 一致考虑是否纳入 `patient_name`）
回填 `lnrs_anon_patient`，再把 `is_placeholder` 置 FALSE。

**端到端目标**：xinqiao 的 patient 表不再全 `is_placeholder=TRUE`。

## Acceptance criteria

- [ ] **决策门**：与 issue-9（zhujiang 占位漏标修复）口径对齐 —— 哪些字段必填才算「真实化」？
  写在 issue 评注（参考 issue-9 当时的决策：`sex` + `birth_date` 有其一即可）
- [ ] 脚本：构造 UPDATE 用 `exam JOIN imaging_study` 反查 patient，把 patient 行更新：
  `UPDATE lnrs_anon_patient p SET is_placeholder=FALSE, sex=COALESCE(p.sex, e.sex), birth_date=COALESCE(p.birth_date, e.birth_date) FROM lnrs_anon_exam e JOIN lnrs_anon_imaging_study s ON s.anon_exam_id=e.anon_exam_id WHERE p.patient_id=s.patient_id AND p.center_code='xinqiao' AND p.is_placeholder=TRUE`
  （具体 JOIN 去重逻辑以 issue-13 落地后实测为准）
- [ ] dry-run 报告受影响行数；--apply 成功
- [ ] SQL 断言 1：`SELECT is_placeholder, COUNT(*) FROM lnrs_anon_patient WHERE center_code='xinqiao' GROUP BY is_placeholder;` 中 `FALSE` 行数 > 0 且与 dry-run 一致
- [ ] SQL 断言 2：`SELECT COUNT(*) FROM lnrs_anon_patient p WHERE p.center_code='xinqiao' AND p.is_placeholder=FALSE AND p.sex='0' AND p.birth_date IS NULL;` 返回 0
  （真实化要求至少 sex 或 birth_date 之一被填）
- [ ] 备份：执行前 `CREATE TABLE lnrs_anon_patient_bak_<ts> AS TABLE lnrs.lnrs_anon_patient WHERE center_code='xinqiao';`
- [ ] 不动 zhujiang / shengyi
- [ ] 不动 `lnrs_anon_imaging_study` / `lnrs_anon_dicom_series` / `lnrs_anon_exam`

## Blocked by

- [Issue 13](./issue-13-xinqiao-exam-ingest.md)（必须先有 exam 行）

## Notes for implementer

- 同样适用于 cxf_archives 那 7,984 study 假以时日入了库后的批量真实化；本 issue 仅覆盖现有 5 sub
- 与 issue-9 同结构，可参照其脚本（`backend/etl2/backfill_shengyi_patient_placeholder.py` 的反向用法）
- 「sex='0'」是新桥当前的占位默认值（plan-xinqiao §0.3）；真实化后应被 exam 的 sex 覆盖
- 若 exam 表的 sex 也大量为占位（部分医院不送），则 `is_placeholder=FALSE` 实际意义不大；
  决策门需评估这种情况是否要改用其他字段判定