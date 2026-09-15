# Issue 1: 回填 lnrs_anon_imaging_study.anon_exam_id（zhujiang 全量 + shengyi best-effort）

## Parent

[PRD: 让 medicalFiles 页面显示真实文件总大小](./PRD.md)

## What to build

执行 `backend/etl2/backfill_imaging_study_exam_id.py --apply`，让 `lnrs_anon_imaging_study.anon_exam_id` 从 100% NULL 变为部分填充，为后续 ETL-2 dicom_series 落库解除 NOT NULL 约束阻塞。

**关联逻辑**（脚本内已实现，作为验收口径参考）：

- 关联键：`(imaging_study.patient_id, exam.patient_id)`
- 模态约束：`exam_type='CT'`（h196_3 上 imaging_study.modality 100%='CT'）
- 时间距离：`abs(exam.exam_date - lnrs.path_study_date(image_path))` 最小
- 平局：取 `anon_exam_id` 字典序最小（稳定可复现）

**端到端可验证**：回填后用 SQL 比对 `count(*) FILTER (WHERE anon_exam_id IS NOT NULL)`，应与 dry-run 报告的 `matchable` 一致；该 SQL 输出又作为下游 Issue 2 跑库前的前置断言。

**shengyi best-effort**：dry-run 报告实测 shengyi 覆盖率 0%（仅 219/82,988 patient 在 exam 表有 CT exam）。脚本对该中心行为是 noop，无需专门处理；Issue 4 单独调查根因。

## Acceptance criteria

- [ ] 在 h196_3 环境执行 `ENVIRONMENT=h196_3 uv run python backend/etl2/backfill_imaging_study_exam_id.py --dry-run --center zhujiang`，输出 `matchable` 行与 36342 一致（或更新后的实测值，差异需在 commit message 说明）。
- [ ] 在 h196_3 环境执行 `ENVIRONMENT=h196_3 uv run python backend/etl2/backfill_imaging_study_exam_id.py --apply --center zhujiang`，脚本成功完成且无 ERROR 日志。
- [ ] SQL 断言：`SELECT center_code, count(*) FILTER (WHERE anon_exam_id IS NOT NULL) FROM lnrs_anon_imaging_study WHERE center_code='zhujiang' GROUP BY center_code;` 返回 zhujiang 行数与 dry-run `matchable` 一致（误差 0）。
- [ ] SQL 断言：`SELECT count(*) FROM lnrs_anon_imaging_study WHERE center_code='zhujiang' AND anon_exam_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM lnrs_anon_exam e WHERE e.anon_exam_id = lnrs_anon_imaging_study.anon_exam_id);` 返回 0（外键完整性）。
- [ ] SQL 断言：抽查至少 3 条 imaging_study 行，手动比对 `anon_exam_id` 与 exam 表的 (patient_id, exam_type='CT', exam_date 最近) 三列组合一致。
- [ ] 重跑幂等：再执行一次 `--apply --center zhujiang`，`count(*) FILTER (WHERE anon_exam_id IS NOT NULL)` 不变（脚本守卫 `WHERE anon_exam_id IS NULL`，重复执行 noop）。
- [ ] 决定 shengyi 是否在本次跑：默认 shengyi 是 noop（覆盖率 0%），不需要专门跑——但需在 commit message 写明"shengyi 跳过原因见 Issue 4"。
- [ ] 不动 `lnrs_anon_dicom_series`、不动 `lnrs_anon_exam`、不动任何 parquet/CSV。

## Blocked by

None — can start immediately.

## Notes for implementer

- 脚本已在 commit `a9000c56` 中写好骨架，本 Issue 主要是**执行**而非新增代码。
- 若 dry-run 输出与 commit `a9000c56` 的预期（zhujiang 36342 / shengyi 0 / 合计 30.4%）有偏差，先排查：是否有新的 exam 落库、imaging_study 是否新增、函数 `path_study_date` 是否被改。
- 执行前**确认无人在改 imaging_study 表**（即 ETL-2 exam 流水线未跑）。如有，加锁或错峰。
- 备份建议（不强制）：`CREATE TABLE lnrs_anon_imaging_study_bak_<timestamp> AS TABLE lnrs.lnrs_anon_imaging_study;`