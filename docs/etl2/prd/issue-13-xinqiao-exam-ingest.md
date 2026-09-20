# Issue 13: 新桥 exam 灌库 + 回填 `lnrs_anon_dicom_series.anon_exam_id`（xinqiao）

## Parent

[plan-xinqiao-disk03-import.md](../plan-xinqiao-disk03-import.md)（§7-4）

## What to build

新桥 33,314 study 全部 `anon_exam_id=NULL`（plan-xinqiao §0.6-5 B 方案）；同 issue-6 的 zhujiang
exam 灌库路径，从新桥 PACS/HIS 拿到 exam 行后灌入 `lnrs_anon_exam`，再回填
`imaging_study` 与 `dicom_series` 的 `anon_exam_id`。

**端到端目标**：xinqiao 的 `lnrs_anon_dicom_series.anon_exam_id` 不再全 NULL（覆盖率 = 实际 match 数）。

## Acceptance criteria

- [ ] 明确 xinqiao exam 的输入源（新桥 PACS 导出 / 现有 HIS 表 / 第三方 ETL），写入 issue 评注
- [ ] 复用 issue-6 的脚本（`backend/etl2/_issue6_ingest_zhujiang_ct_exam.py`）扩展 `--center xinqiao`；
  关联算法沿用 issue-1（patient_id + study_date 距离最小）
- [ ] h196_3 dry-run：报告 matchable 行数（应在数千到数万级别；非零是关键）
- [ ] h196_3 --apply：成功跑完且无 ERROR 日志
- [ ] SQL 断言 1：`SELECT COUNT(*) FROM lnrs_anon_dicom_series ds JOIN lnrs_anon_imaging_study s USING (dicom_study_uid) WHERE s.center_code='xinqiao' AND ds.anon_exam_id IS NOT NULL;` **> 0**（之前全 NULL）
- [ ] SQL 断言 2：`SELECT COUNT(*) FROM lnrs_anon_dicom_series ds WHERE ds.anon_exam_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM lnrs_anon_exam e WHERE e.anon_exam_id = ds.anon_exam_id);` 返回 0（外键完整性）
- [ ] SQL 断言 3：`SELECT COUNT(*) FROM lnrs_anon_imaging_study s WHERE s.center_code='xinqiao' AND s.anon_exam_id IS NULL AND s.dicom_study_uid IN (SELECT DISTINCT dicom_study_uid FROM lnrs_anon_exam e WHERE e.patient_id=s.patient_id);` 返回 0（未漏匹配）
- [ ] 重跑幂等：再执行一次 `--apply --center xinqiao`，回填行数不变（脚本守卫 `WHERE anon_exam_id IS NULL`）
- [ ] 不动 xinqiao 已入库的 patient / imaging_study / dicom_series 的现有数据；不动 zhujiang / shengyi
- [ ] 备份：执行前 `CREATE TABLE lnrs_anon_imaging_study_bak_<ts> AS TABLE lnrs.lnrs_anon_imaging_study WHERE center_code='xinqiao';`

## Blocked by

- [Issue 6](./issue-6-ingest-zhujiang-ct-exam-and-backfill-anon-exam-id.md)（同模式，借鉴脚本）
- 与 [Issue 18](./issue-18-xinqiao-cxf-archives-ingest.md) 软联动：若新桥 exam 与 cxf_archives 同源
  （同一 PACS 导出），可一起做

## Notes for implementer

- xinqiao 有 33,314 study / 33,313 PID，规模与 zhujiang 相近；exam 入库量级需先期评估
- 若新桥 PACS 导出文件过大或格式特殊，可能需要新建脚本而非复用 issue-6
- exam 表的 `anon_exam_id` 已 `NOT NULL`；灌库前先确认 DDL 不需新增列
- 与 issue-15（占位真实化）强依赖：本 issue 跑完后才能 issue-15