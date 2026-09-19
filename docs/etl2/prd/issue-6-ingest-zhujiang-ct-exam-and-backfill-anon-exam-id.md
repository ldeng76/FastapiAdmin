# Issue 6: 补 zhujiang CT exam 入库 + 回填 `imaging_study.anon_exam_id`

## Parent

[plan-disk1-disk2-disk4-zhujiang-import.md](../plan-disk1-disk2-disk4-zhujiang-import.md)（§7-2）

## What to build

`lnrs_anon_imaging_study.anon_exam_id` 在 zhujiang 的 86,927 行上 **100% NULL**。

`docs/etl2/prd/issue-1-backfill-imaging-study-exam-id.md` 计划用
`backend/etl2/backfill_imaging_study_exam_id.py --apply --center zhujiang` 回填，
但该脚本的关联口径是 **`exam_type='CT'` + `(patient_id, exam_date 距 study_date 最近)`**，
而 zhujiang 的 exam 表**只有 1,091 行、`exam_type` 全是 `gene`**：

| 指标 | 实测值（2026-09-20） |
|---|---:|
| `lnrs_anon_exam` (zhujiang) | 1,091（`exam_type='gene'`，`exam_date` 2016-01-05 ~ 2026-01-06） |
| exam 覆盖患者数 | 1,030 |
| 影像患者数 | 60,385 |
| **两者交集** | **23** |

→ 直接跑 issue-1 覆盖率接近 0。所以本 issue 分两段，端到端目标是
**「zhujiang 的 CT study 挂上真实 CT exam」**：

1. **找 CT exam 数据源并灌库**：在 ETL-1 的 exam 派生表 / parquet 里定位 zhujiang 的 CT exam，
   写入 `lnrs_anon_exam`（+ `lnrs_anon_exam_detail`，若数据齐），`center_code='zhujiang'`。
2. **回填**：跑 `backfill_imaging_study_exam_id.py --apply --center zhujiang`，
   让 `imaging_study.anon_exam_id` 从 100% NULL 变为部分填充。

**若调研结论是「zhujiang 不存在 CT exam 数据源」**：本 issue 降级为「记录结论 + 保持 NULL」，
把根因写进 `plan-disk1-disk2-disk4-zhujiang-import.md` §7-2，并明确后续 issue-3（service 切视图）
在 zhujiang 上会看到什么。**不要**为了凑覆盖率用 gene exam 去关联 CT study。

## Acceptance criteria

- [ ] 调研产出 `docs/etl2/verify_result/zhujiang-exam-source-<date>.md`：列出候选数据源（路径 + 行数 + `exam_type` 分布 + 是否含 CT），并给出「有 / 无 CT exam」的结论
- [ ] （若有源）灌库后断言：`SELECT exam_type, COUNT(*) FROM lnrs_anon_exam WHERE center_code='zhujiang' GROUP BY 1;` 包含 `CT` 行，且行数 ≥ 调研预期
- [ ] （若有源）灌库不破坏既有 1,091 行 gene exam：`SELECT COUNT(*) FROM lnrs_anon_exam WHERE center_code='zhujiang' AND exam_type='gene';` 仍为 1,091
- [ ] `backfill_imaging_study_exam_id.py --dry-run --center zhujiang` 输出的 `matchable` 值记入 commit message
- [ ] `--apply` 后断言：`SELECT COUNT(*) FROM lnrs_anon_imaging_study WHERE center_code='zhujiang' AND anon_exam_id IS NOT NULL;` == dry-run `matchable`（误差 0）
- [ ] 外键完整性断言：`SELECT COUNT(*) FROM lnrs_anon_imaging_study s WHERE s.center_code='zhujiang' AND s.anon_exam_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM lnrs_anon_exam e WHERE e.anon_exam_id = s.anon_exam_id);` 返回 0
- [ ] 抽查 ≥3 条：`anon_exam_id` 指向的 exam 与 study 的 `(patient_id, exam_type='CT', exam_date 最近)` 三列一致
- [ ] 幂等：再跑一次 `--apply`，非 NULL 计数不变（脚本守卫 `WHERE anon_exam_id IS NULL`）
- [ ] 不动 `lnrs_anon_dicom_series`（其 `anon_exam_id` 由 Issue 2 的 ETL-2 upsert `COALESCE` 回填，见 issue-1 的「同时修复 dicom_series.anon_exam_id 全 NULL」小节）
- [ ] 若结论是「无 CT 源」：验收改为「调研报告 + 计划文档更新」，并显式记录「本 issue 不产生数据变更」

## Blocked by

- [Issue 5](./issue-5-extend-path-study-date-zhujiang-prefixes.md) —— `path_study_date` 对 3,710 个 study 返回 NULL，不先修则这些 study 静默不参与关联，覆盖率无法达标。

## Notes for implementer

- 现有 1,091 行 gene exam **不要删**，本 issue 是**追加** CT exam。
- `gene` exam 与 CT study 的关联语义存疑（基因检测日期 ≠ 影像检查日期）——默认**不**用 gene exam 关联 CT study；若产品认为应关联，需在调研报告里显式论证并单独确认。
- 关联脚本：`backend/etl2/backfill_imaging_study_exam_id.py`（骨架已存在，本 issue 主要是**数据源调研 + 执行**）。
- 执行前确认无人在改 `imaging_study`（ETL-2 流水线未跑）。
- 备份建议（不强制）：`CREATE TABLE lnrs_anon_imaging_study_bak_<ts> AS TABLE lnrs.lnrs_anon_imaging_study;`
