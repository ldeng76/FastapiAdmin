# Issue 14: 调研 — 珠江 `lnrs_anon_imaging_study.dicom_study_uid` ≥100 例 header 对账

## Parent

[plan-xinqiao-disk03-import.md](../plan-xinqiao-disk03-import.md)（§7-6）

## What to build

`lnrs_anon_imaging_study.dicom_study_uid` 在珠江批次的写入策略是「目录名 UID」（参
`scripts/build_zhujiang_imaging_study_index_v2.py`）。新桥调研（plan-xinqiao §0.1）实测发现
「目录名 UID == DICOM SeriesInstanceUID」的情况在 4_tjj 复现 —— 珠江虽以 1 例
`01_disk/zhujiang_dicom/20170101/270561_1.2.840.113704.1.111.10996.1483237195.1/`
验证为 StudyInstanceUID，但 86,927 study 仅抽查 1 例不充分。

**端到端目标**：产出《校验报告》明确「珠江数据可信（≥99% 匹配）」或「需重灌」二选一。
本调研不写任何业务改动，结论决定后续是否开修复工单（issue-15 风格）。

## Acceptance criteria

- [ ] 脚本：从 lnrs_anon_imaging_study 随机抽 **≥100** 条 `center_code='zhujiang'` 的 study；
  对每条取其 `image_path` 目录下首个 DICOM 文件，读 `(0008,0020) StudyInstanceUID`
- [ ] 报告：`docs/etl2/verify_result/zhujiang_study_uid_audit.md` 至少含
  （1）每条 `(patient_id, dicom_study_uid, header_study_uid, match)` 四列；
  （2）汇总匹配率；（3）3 个典型不匹配案例（含完整路径）
- [ ] 决策：若匹配率 **< 100%** 且 ≥3 例不匹配，在 issue 评注开 issue-15 风格的修复工单（暂不实施）
- [ ] 不改任何表数据（纯调研）；不改 CSV 产物
- [ ] 不读 3_cxf_archives（与本调研无关，且无 PHI）

## Blocked by

None - can start immediately.

## Notes for implementer

- 珠江影像根：`/data/wlx/DATABASE/01_disk/zhujiang_dicom/` + `02_disk/` + `04_disk/`（参 `plan-disk1-disk2-disk4-zhujiang-import.md`）
- pydicom 已可用（其它脚本依赖）；header 读 `(0008,0020)` 一行
- 抽样 SQL：`SELECT patient_id, dicom_study_uid, image_path FROM lnrs_anon_imaging_study WHERE center_code='zhujiang' ORDER BY random() LIMIT 100;`
- 若担心抽样被 patient_id 偏倚（同一患者多 study），按 study_uid 去重后再随机
- 报告若发现匹配率 ≈ 0%（即目录名 UID 全是 SeriesInstanceUID），需立即升级到 P0，因为整批数据错误