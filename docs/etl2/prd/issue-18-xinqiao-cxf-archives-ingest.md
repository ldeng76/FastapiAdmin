# Issue 18: 新桥 `3_cxf_archives` 入库（阻塞于外部 StudyInstanceUID → PatientID 映射）

## Parent

[plan-xinqiao-disk03-import.md](../plan-xinqiao-disk03-import.md)（§7-1）

## What to build

`/data/wlx/DATABASE/03_disk/xinqiao/3_cxf_archives/` 有 **7,984 个 study / 1,016 GB / 4.5M 文件**，
DICOM header 全部去身份导出（实测 6 个样本）：

| 字段 | 取值 |
|---|---|
| `PatientID` | 空 |
| `PatientName` / `BirthDate` / `Sex` / `Age` / `InstitutionName` / `ReferringPhysicianName` / `StudyDescription` | 全空 |
| `StudyInstanceUID` | 正常（第 1 层目录名 == header，已验证）|
| `SeriesInstanceUID` | 正常（第 2 层目录名 == header，已验证）|

由于 `lnrs_anon_imaging_study.patient_id` 是 **NOT NULL + FK 到 `lnrs_anon_patient`**，无 PID
无法入库。v1 的「从 DICOM header 反查 PatientID」路径**不可实现**（plan-xinqiao §0.4）。

需要新桥 PACS/HIS 提供 `StudyInstanceUID → PatientID` 映射后才能灌库。本 issue 跟踪该映射
的获取与落地。

**端到端目标**：拿到映射后，7,984 study 全部入库，xinqiao patient 池扩到 33,313 + 7,984 - 去重。

## Acceptance criteria

- [ ] **决策门**：用户确认外部映射已拿到 / 何时能拿到（issue 评注里写）。若 6 个月内拿不到，
  本 issue 应显式关闭并写「接受遗留 1,016 GB / 7,984 study 不入影像表」理由
- [ ] 拿到映射后：写入临时表 `<mapping>_cxf.csv`（仅含 `study_instance_uid, patient_id`），
  含 PHI 走 `.gitignore`
- [ ] 复用 plan-xinqiao §0.4 的事实：3_cxf_archives 第 1 层即 StudyInstanceUID；
  `lists/batch_001..008.txt` 共 7,984 行可直接枚举，**不需遍历 1,016 GB**
- [ ] 复用 `scripts/build_xinqiao_imaging_study_index.py`，加 `--layout cxf`，
  layout_C 的 `patient_id` 从外部映射取，study_uid 取第 1 层目录名（已 == header）
- [ ] 灌库脚本：`build_xinqiao_imaging_study_index_v2.py` 加 `--source xinqiao_cxf`，
  `source_kind='cxf_archives'`，`schema_hash` 按 source 派生（参 plan-xinqiao §2 P1-8 处置）
- [ ] 验证 SQL 沿用 `verify_xinqiao_imaging.sql` 风格（V1–V13 的 cxf 子集），
  新增 V14：`SELECT COUNT(*) FROM lnrs_anon_imaging_study WHERE center_code='xinqiao' AND source='xinqiao_cxf';` = 7,984
- [ ] 备份：执行前同 plan-xinqiao §6 R5 的 `/tmp` 备份流程
- [ ] 与 issue-13 的 xinqiao exam 灌库联动：本批进库后 dicom_series.anon_exam_id 走 issue-13 同流程

## Blocked by

None - can start immediately（**但实际被外部 PACS 映射阻塞，无法推进**）。

## Notes for implementer

- 拿映射前**不要做**任何扫描 / 灌库操作（节省 1,016 GB I/O；只需解析 7,984 行 lists）
- 本批进库后 `is_placeholder=TRUE`（与 5 sub 已有口径一致），等 PACS 后续提供人口学再翻 FALSE（参 issue-15）
- `3_cxf_archives/lists/batch_001..008.txt` 已存在并被 walk 结果验证；可直接用作 study UID 枚举
- 若新桥 PACS 同时提供 exam 行，本 issue 可与 issue-13 合并实施
- 跨中心 StudyUID 重叠已实测 0（参 plan-xinqiao §0.5），不必担心与现有 5 sub 撞键