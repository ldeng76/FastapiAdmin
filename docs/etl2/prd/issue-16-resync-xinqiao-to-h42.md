# Issue 16: h196_3 → 1.59（h42）xinqiao 影像表重同步

## Parent

[plan-xinqiao-disk03-import.md](../plan-xinqiao-disk03-import.md)（§7-5）

## What to build

issue-10 已实现 zhujiang / shengyi / xinqiao 三中心同步；当前 1.59 上的 xinqiao 部分因
`dicom_series.anon_exam_id` 全 NULL（issue-13 前置状态），同步到 1.59 后下游将缺失 exam 关联。

本 issue 在 issue-13 跑完后**重同步一次** xinqiao 三表，让 1.59 拿到带 exam 的最新影像索引。

**端到端目标**：1.59 上 xinqiao 的 `dicom_series.anon_exam_id` 非 NULL 行数与 h196_3 同口径一致。

## Acceptance criteria

- [ ] 复用 issue-10 的 `lnrs-sync-196-to-159` 技能脚本，限定 `--center xinqiao`
- [ ] 同步前 1.59 现状行数记录到 commit message（与 h196_3 对比）
- [ ] 同步前确认 1.59 侧 `/data/lnrs_backup` **可写**（脚本会 DROP 现有目标表并自动备份）—— 先 `touch` 探测
- [ ] 1.59 SQL 断言：`SELECT center_code, COUNT(*) FROM lnrs_anon_imaging_study GROUP BY 1;` 仍覆盖三中心
- [ ] 1.59 SQL 断言：`SELECT COUNT(*) FROM lnrs_anon_dicom_series ds JOIN lnrs_anon_imaging_study s USING (dicom_study_uid) WHERE s.center_code='xinqiao' AND ds.anon_exam_id IS NOT NULL;` **= h196_3 同口径**（之前在 1.59 上是 0）
- [ ] 外键完整性（1.59）：`SELECT COUNT(*) FROM lnrs_anon_imaging_study s WHERE NOT EXISTS (SELECT 1 FROM lnrs_anon_patient p WHERE p.patient_id = s.patient_id);` 返回 0
- [ ] 外键完整性（1.59）：`SELECT COUNT(*) FROM lnrs_anon_dicom_series ds WHERE NOT EXISTS (SELECT 1 FROM lnrs_anon_imaging_study s WHERE s.dicom_study_uid = ds.dicom_study_uid);` 返回 0
- [ ] **单向**：h196_3 行数同步前后**不变**
- [ ] 同步后 1.59 的备份文件路径记入 commit message
- [ ] 不重同步 zhujiang / shengyi（issue-10 已覆盖）；若需重同步全表，独立 issue 处理

## Blocked by

- [Issue 13](./issue-13-xinqiao-exam-ingest.md)

## Notes for implementer

- 同步脚本会自动备份 1.59 旧表到 `/data/lnrs_backup`；若该路径不可写，先 `touch` 探测
- 若用户希望「重同步全三中心」而非只重 xinqiao，把 `--center` 限制取消并把 issue 标题改回 issue-10 风格
- 同步方向是 h196_3 → 1.59；本机即 h196_3（10.12.196.3），**不要 ssh**
- issue-10 已落地，本 issue 主要是**执行**而非新增代码
- 与 issue-15 同源依赖：issue-15 也会改 lnrs_anon_patient，若 1.59 也想看到 sex/birth_date 回填，
  则本 issue 应在 issue-15 之后再跑一次 —— 视用户决策，本 issue 文档默认只重同步 issue-13 的产物