# Issue 25: 新桥 exam 报告源补全 — Accession 纯报告 + 262 新检查

## Parent

[Issue 13](./issue-13-xinqiao-exam-ingest.md)（其 CT 报告源 ct.parquet 的超集补全）。
父文档：[plan-xinqiao-disk03-import.md](../plan-xinqiao-disk03-import.md) §7-4。

## What to build

`ct_mapped.parquet`（CT 报告+DICOM 合并版，与已灌 ct.parquet 同批数据，见
[series-counts-fix 报告](../verify_result/xinqiao-series-counts-fix-20260920.md) §2）
共 124,308 行，其中两类数据未入库：

1. **83,010 行 `Accession_*` 纯报告**：有完整 raw_text（检查所见/结论 100%）与
   exam_date（100%），盘上无 DICOM 文件。覆盖 29,376 个患者（最多 38 份报告/人）。
2. **262 行 StudyUID 键新检查**：ct.parquet 中不存在的检查（含 262 个新患者），
   有 `path[]` 文件清单但 **exam_date 为 NULL**。

端到端行为：新桥患者的 CT 报告（临床文本）在 `lnrs_anon_exam` /
`lnrs_anon_report_text` / `lnrs_anon_exam_detail` 中完整可查，exam 计数反映
医院真实检查量，而非只有「恰好落盘」的那部分。

**决策门（开单时预置，实施前确认）**：

- **去重口径**：ct_mapped 与已灌 124,045 行 raw_text 全等的部分**只灌增量**——
  按 `(patient_id, exam_date, sha256(raw_text))` 三键幂等跳过已入库内容
  （对账已证两源同批、内容全等）；不得产生重复 exam。
- **双 ID 空间**：新行 `exam_no` 直接用 ct_mapped 的 `exam_id`（`Accession_*` 或
  StudyUID 字符串），`source_exam_hash` / `anon_exam_id` 由引擎
  `compute_anon_exam_id(center, exam_no)` 派生——与旧 124,045 行的 hash 键空间
  天然不相交，并存无冲突，报告中说明即可。
- **262 行 exam_date 为 NULL**：`lnrs_anon_exam.exam_date` NOT NULL。候选口径：
  StudyUID 内嵌时间戳兜底（`lnrs.uid_study_date`，issue-13 已证 GE 系 UID 日期即
  检查日期）→ 兜底成功的灌入、失败的和对应患者保持不入并在报告列明。

## Acceptance criteria

- [ ] 决策门三条均有明确结论并写入实施记录
- [ ] 备份：执行前 exam / report_text / exam_detail / patient 建 `_bak_<ts>` 快照
- [ ] dry-run：报告增量行数（Accession 新 exam、262 新检查、新患者数、跳过的重复数），
  跳过数应与对账预期一致（有日期行中与已灌 raw_text 全等的部分）
- [ ] `--apply` 成功；幂等重跑 0 新增
- [ ] SQL 断言：灌后按 `(patient_id, exam_date, report_text hash)` 口径不存在重复 exam；
  Accession 行 exam_date 非空率 100%
- [ ] SQL 断言：zhujiang / shengyi 的 exam / report_text 行数与合计值零漂移
- [ ] 产出验收 SQL（V1–Vn）+ 报告入 `docs/etl2/verify_result/`
- [ ] 不动 zhujiang / shengyi；不改动既有 xinqiao 124,045 exam 行的任何列
- [ ] staging 产物含院内 PID 的落 gitignore 目录

## Blocked by

None — 可立即开始。与 [Issue 24](./issue-24-xinqiao-cxf-ingest-via-ct-mapped.md)
同源不同切片（24 动 imaging 侧、25 只动 exam 侧），可并行；若 24 先落地，其
exam 灌库路径可复用。

## Notes for implementer

- raw_text 很大（单行可达数十 KB），批量写入注意分块与事务大小。
- 262 个新患者按占位口径创建（sex='0'，is_placeholder=TRUE）；真实化归
  [Issue 26](./issue-26-xinqiao-placeholder-realization-v2.md)。
- 引擎灌库走 `_import_exam_text_table` 直调（不走 ETL2 CLI，避免连带触发
  xinqiao spec 的 dicom_series 重注册，同 issue-13 惯例）；
  `_close_batch` 记得显式 commit（issue-13 遗留缺陷教训）。
