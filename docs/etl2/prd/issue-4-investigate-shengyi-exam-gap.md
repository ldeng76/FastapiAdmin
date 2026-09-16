# Issue 4: 调查 shengyi imaging_study 覆盖率 0% 的根因

## Parent

[PRD: 让 medicalFiles 页面显示真实文件总大小](./PRD.md)

## What to build

**调查产出**：一份 markdown 报告（`docs/etl2/findings/shengyi-exam-gap-<date>.md`），回答以下问题，并给出**根因 + 修复路线**（不实施修复）：

1. shengyi `lnrs_anon_imaging_study` 82,994 行 = 82,988 patient，其中仅 219 patient（0.26%）在 `lnrs_anon_exam` 表有任意 exam、174 patient 有 CT exam。为什么？
2. 是 ETL-1 shengyi parquet 适配只导了影像 metadata 但没导对应 exam？还是 ETL-2 引擎的 exam 写入路径在 shengyi spec 里没启用？还是 exam 表 shengyi 部分被某次 ETL 重置覆盖？
3. 修复方案预计工作量（SQL 行数 + ETL 改写范围）——是否能与其它 ETL-2 工作合批做、还是需要独立排期。

**端到端可验证**：报告可被一个不在本会话的工程师用作修复实施输入。

## Acceptance criteria

- [ ] 报告第一部分"现状量化"：复现 h196_3 上的关键数字——`shengyi imaging_study: 82994 行 / 82988 patient`，`patient 有 exam: 219 (0.26%)`，`patient 有 CT exam: 174`；这些数字与 commit `a9000c56` README / dry-run 一致。
- [ ] 报告第二部分"数据流溯源"：
  - shengyi imaging_study 来源：`disk_06_shengyi / disk_07_shengyi`（commit message 与 imaging_study.source 字段），共 4 个 parquet 文件路径。
  - shengyi exam 表来源：找到 ETL-2 shengyi spec 中导 exam 的 spec 条目，列出导入了哪些 parquet、写入多少行；与 imaging_study 中 patient 集合做 LEFT JOIN 比较，找"应到未到"的 patient。
- [ ] 报告第三部分"根因结论"：从候选根因里选定一个（可能多个），并给出支持证据。例如：
  - 候选 A：ETL-2 shengyi spec 中 `exam_text` kind 覆盖不全——部分 exam 来源未注册，导致 imaging_study 来源的 patient 在对应 exam 没入库。
  - 候选 B：shengyi imaging_study 来源（磁盘 DICOM 目录）来自另一批 patient，patient 表里没他们——这部分影像关联不上任何 exam 是正确的（脱敏后无 anchor）。
  - 候选 C：ETL-1 staging 与 ETL-2 exam 写入之间 patient_id 哈希派生版本不一致（key_fingerprint / secret_version 不同）。
- [ ] 报告第四部分"修复路线"：基于根因，给出 1-3 个修复路径，每个含工作量估计（小时/天）、风险等级、所需数据备份、是否需要新 alembic 迁移、是否需要回填历史 exam 行。
- [ ] 报告不超过 5 页 markdown；技术细节用 SQL 输出佐证（贴 1-2 段代表性查询）。
- [ ] 不修改任何代码、不修改任何数据；本 Issue 仅为调研。

## Blocked by

None — can start immediately.

## Notes for implementer

- 这是**纯调研** Issue，不需要写 ETL 代码、不需要 alembic 迁移、不需要 UPDATE/INSERT。
- 关键 SQL 模板（可在 dev DB 直接跑）：
  ```sql
  -- shengyi imaging_study patient 与 shengyi exam patient 集合对比
  SELECT
    (SELECT count(DISTINCT patient_id) FROM lnrs_anon_imaging_study WHERE center_code='shengyi') AS study_patients,
    (SELECT count(DISTINCT patient_id) FROM lnrs_anon_exam WHERE center_code='shengyi') AS exam_patients,
    (SELECT count(DISTINCT s.patient_id)
     FROM lnrs_anon_imaging_study s
     WHERE s.center_code='shengyi'
       AND NOT EXISTS (SELECT 1 FROM lnrs_anon_exam e WHERE e.patient_id = s.patient_id)) AS study_only;
  ```
- shengyi ETL-2 spec 在 `backend/app/plugin/module_medical/hospital/anon_etl_engine.py:_CENTER_PARQUET_SPECS['shengyi']`；阅读它确认导了哪些 src_table。
- 若根因是"磁盘影像来自不同 patient 集合"，结论可能是"无需修复"——shengyi 这 82,994 study 在新数据体系里就是无 exam 关联的。这要写清楚，不能糊弄。
- 参考文档：`/home/dzy/wk/lnrs/docs/etl2/数据导入核验清单.xlsx` 第 7 行"基础信息 🟡 部分通过（87,132 行 PG，但 staging 后期追加 6 个 patient_id ETL2 patient 路径未再重跑）"——可能与本 Issue 根因相关。