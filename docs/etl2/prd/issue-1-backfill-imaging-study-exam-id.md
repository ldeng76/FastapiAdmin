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

## 同时修复 dicom_series.anon_exam_id 全 NULL

2026-09-19 发现 `lnrs_anon_dicom_series` 表全部 125,930 行 `anon_exam_id` 均为 NULL（zhujiang 43,873 + shengyi 82,057）。根因不是 dicom_series 本身，而是 `lnrs_anon_imaging_study.anon_exam_id` 全 NULL —— dicom_series 是它的下游冗余 FK（`anon_exam_id_fkey ON DELETE CASCADE`）。

本 Issue 完成后会**顺带修复** dicom_series 的 NULL，机制见 Issue 2：`anon_etl_engine.py:3225-3228` 的 ON CONFLICT upsert 写法对 `anon_exam_id` 列使用 `func.coalesce(stmt.excluded.anon_exam_id, 已存值)`，所以等 Issue 2 重跑 dicom_series ETL 时，之前以 NULL 写入的 zhujiang 行会自动被回填成 Issue 1 产出的 anon_exam_id（shengyi 仍为 NULL，因为 shengyi coverage 0% 是已知缺口，见 Issue 4）。

回填 dicom_series 的端到端断言 SQL（Issue 2 跑完后执行）：

```sql
-- zhujiang 的 dicom_series 应全部挂上 exam
SELECT
  b.center_code,
  COUNT(*) AS total_series,
  COUNT(*) FILTER (WHERE s.anon_exam_id IS NULL) AS still_null,
  COUNT(*) FILTER (WHERE s.anon_exam_id IS NOT NULL) AS filled
FROM lnrs.lnrs_anon_dicom_series s
JOIN lnrs.lnrs_anon_ingest_batch b ON s.created_batch_id = b.batch_id
WHERE b.center_code = 'zhujiang'
GROUP BY b.center_code;
-- 期望：still_null = 0，filled = 43873（与 zhujiang 入库 series 行数一致）
```

## Blocked by

None — can start immediately.

## Notes for implementer

- 脚本已在 commit `a9000c56` 中写好骨架，本 Issue 主要是**执行**而非新增代码。
- 若 dry-run 输出与 commit `a9000c56` 的预期（zhujiang 36342 / shengyi 0 / 合计 30.4%）有偏差，先排查：是否有新的 exam 落库、imaging_study 是否新增、函数 `path_study_date` 是否被改。
- 执行前**确认无人在改 imaging_study 表**（即 ETL-2 exam 流水线未跑）。如有，加锁或错峰。
- 备份建议（不强制）：`CREATE TABLE lnrs_anon_imaging_study_bak_<timestamp> AS TABLE lnrs.lnrs_anon_imaging_study;`