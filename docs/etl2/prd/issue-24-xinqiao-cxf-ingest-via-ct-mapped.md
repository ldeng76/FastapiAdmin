# Issue 24: cxf_archives 7,984 study 入库 — ct_mapped 解锁外部映射阻塞

## Parent

[Issue 18](./issue-18-xinqiao-cxf-archives-ingest.md)（本单实现其目标；18 原文保持不动）。
父文档：[plan-xinqiao-disk03-import.md](../plan-xinqiao-disk03-import.md) §7-1。

## What to build

issue-18 的阻塞点是「需外部提供 `StudyInstanceUID → PatientID` 映射」。
现已解锁：`/data/wlx/DATABASE/extracted_tables/xinqiao/ct_mapped.parquet`
（CT 报告+DICOM 合并导出，与 issue-13 灌库的 ct.parquet 同批数据，对账见
[series-counts-fix 报告](../verify_result/xinqiao-series-counts-fix-20260920.md) §2）中
**exam_id = StudyInstanceUID 的行直接携带 patient_id（院内 PID）+ `path[]` 全量
.dcm 文件路径 + file_count（series 数）+ total_size_bytes**，其中 7,984 行属于
`3_cxf_archives`。入库无需再遍历 1,016 GB 磁盘（`lists/batch_*.txt` 与 path[]
均可枚举，byte_size 直接取导出值，无需 stat）。

端到端行为：7,984 个 cxf study 在库内成为一等公民——patient（占位）/ imaging_study /
dicom_series / exam / report_text / phi_audit / ingest_batch 全链路落库，
`anon_exam_id` 关联到位，页面可查、计数参与统计。

键事实（实测，2026-09-20）：

- cxf 的 7,984 个 StudyUID 与库内 imaging_study / 5 sub 布局的 UID 交集 = 0（§0.4）；
- cxf 的 DICOM header PatientID 全空（§0.4）——patient 归属**以 ct_mapped 报告侧
  patient_id 为准**（院内 PID，字符串处理，注意尾点/前导零形态）；
- path 形态：`…/3_cxf_archives/folders/NNN/<StudyUID>/<SeriesUID>/*.dcm`。

## Acceptance criteria

- [ ] 备份：执行前对将写入的表建 `_bak_<ts>` 快照（imaging_study / dicom_series /
  patient 现有全量），回退可用
- [ ] dry-run：报告将写入行数（patient 新增数、study 7,984、series 7,984、exam 7,984、
  phi_audit、batch），与 ct_mapped cxf 行数逐项对账
- [ ] `--apply` 成功；幂等重跑 0 新增 0 更新
- [ ] SQL 断言：imaging_study `center_code='xinqiao' AND source='xinqiao_3_cxf'` 行数
  = 7,984；`anon_exam_id` 非空率 100%；dicom_series 每行 file_count / byte_size /
  series_count 与 ct_mapped 对应行全等
- [ ] SQL 断言：与既有 33,314 study 的 `dicom_study_uid` 交集 = 0；zhujiang / shengyi
  合计值零漂移
- [ ] 顺带复核项：用 ct_mapped StudyUID 映射复核 issue-13 已回填的 33,110 个
  `anon_exam_id`（imaging_study ↔ ct_mapped StudyUID 行 ↔ exam 三方一致性），
  差异单列报告；不一致不擅自改，开评注
- [ ] 产出验收 SQL `docs/etl2/verify_xinqiao_cxf_ingest.sql`（V1–Vn 模式）+ 调研/
  执行报告入 `docs/etl2/verify_result/`
- [ ] 不动 zhujiang / shengyi；不动既有 xinqiao 33,314 study 及其关联行
- [ ] 执行脚本走 issue-23 的 stage→promote 护栏（若届时已落地）或显式确认闸

## Blocked by

None — 可立即开始（外部映射阻塞已由 ct_mapped 解除）。

## Notes for implementer

- `file_count` 语义 = **series 个数**（不是文件数）；instance 数用 `len(path)`；
  `series_count` 列口径与 2026-09-20 计数校正后的约定一致（PACS 权威值）。
- patient 行按现行占位口径创建（sex='0'、is_placeholder=TRUE）；人口学真实化归
  [Issue 26](./issue-26-xinqiao-placeholder-realization-v2.md)，不要在本单做。
- exam 行的 `exam_date` 直接取 ct_mapped（Accession 行之外 cxf 行 exam_date 实测
  非空；若个别为空，用 StudyUID 内嵌日期兜底（`lnrs.uid_study_date`），兜底比例
  写进报告）。
- ct_mapped 为 PHI 邻接文件：任何 staging 产物含院内 PID 的必须落 gitignore 目录。
