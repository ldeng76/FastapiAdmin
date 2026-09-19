# Issue 9: 修复 shengyi 占位漏标（82,682 个患者 `is_placeholder` 应为 TRUE）

## Parent

[plan-disk1-disk2-disk4-zhujiang-import.md](../plan-disk1-disk2-disk4-zhujiang-import.md)（§7-4）

## What to build

`lnrs_anon_patient` 里 shengyi 有 **82,682** 个患者 `is_placeholder = FALSE`，
但人口学**全空**（`sex='0'` 且 8 个人口学列全 NULL）。

根因：`build_shengyi_imaging_study_index.py` 离线脚本**漏写** `is_placeholder` 列，
走 DDL 默认值 `FALSE`。对照：

| 中心 | `is_placeholder` | 行数 | 说明 |
|---|---|---:|---|
| shengyi | `f` | 82,994 | **其中 82,682 应为 TRUE**（人口学全空） |
| zhujiang | `t` | 67,114 | 脚本显式写 TRUE ✓ |
| xinqiao | `t` | 33,313 | 脚本显式写 TRUE ✓ |

`is_placeholder` 的语义（`0018-anon-patient-is-placeholder.sql`）：`TRUE` = 仅有 ID 占位、
人口学待补；后续 ETL-2 patient 批次拿到真实档案时会 upsert 并翻回 `FALSE`。
shengyi 这 82,682 行标成 FALSE 会让「哪些患者人口学待补」这个判断失真。

**端到端交付**：
1. 修 `build_shengyi_imaging_study_index.py`，避免重跑再漏
2. UPDATE 修复存量（规则与 0018 的回填口径一致）

## Acceptance criteria

- [ ] `build_shengyi_imaging_study_index.py` 补上 `is_placeholder = TRUE` 写入（与 zhujiang 的
      `build_zhujiang_imaging_study_index_v2.py` 同款），并在 commit message 说明
- [ ] 存量修复 UPDATE 的 `WHERE` 与 0018 同口径（8 个人口学列全 NULL）：
      `center_code='shengyi' AND sex='0' AND NOT is_placeholder AND birth_date IS NULL AND ethnicity IS NULL AND smoking_status IS NULL AND abo_blood_type IS NULL AND rh_blood_type IS NULL AND native_place IS NULL AND first_nodule_date IS NULL AND bmi IS NULL`
- [ ] 修复前备份：`CREATE TABLE lnrs_anon_patient_bak_shengyi_placeholder_<ts> AS SELECT patient_id, is_placeholder FROM lnrs.lnrs_anon_patient WHERE center_code='shengyi';`
- [ ] 修复前记录基线：`SELECT is_placeholder, COUNT(*) FROM lnrs_anon_patient WHERE center_code='shengyi' GROUP BY 1;`
- [ ] SQL 断言（修复后）：上一条 WHERE 的 `COUNT(*)` 返回 **0**
- [ ] 回归断言：`is_placeholder = FALSE` 的行数**恰好减少 82,682**；`TRUE` 行数恰好增加 82,682；总行数不变
- [ ] 只改 `is_placeholder` 一列 —— 断言 `SELECT COUNT(*) FROM lnrs_anon_patient p JOIN lnrs_anon_patient_bak_shengyi_placeholder_<ts> b USING (patient_id) WHERE p.sex <> '0' OR p.birth_date IS NOT NULL ...` 为 0（其余列未被触碰）
- [ ] 不动 zhujiang / xinqiao 的患者行
- [ ] 收尾：`DROP TABLE lnrs_anon_patient_bak_shengyi_placeholder_<ts>;`（或按团队备份策略保留）

## Blocked by

None - can start immediately.

## Notes for implementer

- 这是**纯数据修正 + 一处脚本补丁**，不改 schema（`is_placeholder` 列由 0018 迁移提供，已存在）。
- 82,682 是 2026-09-20 实测值；执行前**重新跑一遍计数**，因为 shengyi 可能已有新增行（脚本重跑/新批次）。
- 不要把「`sex='0'` 且人口学全空」当成「一定是占位」的唯一判据 —— 本 issue 沿用的是 0018 既定口径，
  若认为口径需调整，先单独提，不要在本 issue 里改判据。
- 同类问题已存在于历史（珠江计划 §7-4 记录为「R16 的存量」），zhujiang/xinqiao 的脚本已避免。
