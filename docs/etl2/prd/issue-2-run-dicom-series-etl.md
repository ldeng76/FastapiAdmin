# Issue 2: 跑 ETL-2 dicom_series 阶段（zhujiang → 视图 total_bytes 非零）

## Parent

[PRD: 让 medicalFiles 页面显示真实文件总大小](./PRD.md)

## What to build

执行 `backend/etl2/run_dicom_series_etl.sh --apply --centers zhujiang`，让 ETL-2 dicom_series 阶段扫描 119,350 个 study 中的 zhujiang 36,356 个目录（其中 ~36,342 个 `anon_exam_id` 已回填），解析 series 元数据并 upsert 到 `lnrs_anon_dicom_series`，最终让视图 `lnrs_anon_v_imaging_study_counts.total_bytes` 从 89,180,336（仅 4 行手工验证）变为真实数十~数百 GB。

**端到端可验证**：

- 跑库前后对比 `SELECT count(*), COALESCE(SUM(byte_size), 0) FROM lnrs_anon_dicom_series;`；
- 跑库后查询视图，对 zhujiang study（36,356 行）应绝大多数 `total_bytes > 0`；
- 与 Issue 1 的 dry-run `matchable` 数对齐：成功 upsert 的 series 数应不少于回填成功的 study 数 × 平均 series 数。

**已知预期**：

- 预计耗时 6-12 小时（36,342 study × 22-116MB × `fpath.stat()`）；脚本默认要求 YES 二次确认。
- 引擎内置 `scope='all'`，本 Issue 跑 zhujiang 单中心即可；其他中心（shengyi 0% 覆盖、xinqiao/hos301 体量小）按需追加。
- 幂等：ON CONFLICT (dicom_series_uid) DO UPDATE，重跑安全。

## Acceptance criteria

- [ ] 在 h196_3 环境先执行 `ENVIRONMENT=h196_3 backend/etl2/run_dicom_series_etl.sh --centers zhujiang`（dry-run 模式），确认打印的 dicom_series DB-SCAN 分支存在、其它表状态符合预期（多数 parquet MISSING 不影响 dicom_series）。
- [ ] 在 h196_3 环境执行 `ENVIRONMENT=h196_3 backend/etl2/run_dicom_series_etl.sh --apply --centers zhujiang`，按提示输入 YES；脚本返回 exit code 0。
- [ ] SQL 断言：`SELECT count(*), COALESCE(SUM(byte_size),0) FROM lnrs_anon_dicom_series;` 返回的 `count` ≥ 30,000（保守下限，远低于预期 80,000+ series 行），`sum` ≥ 30 GB。
- [ ] SQL 断言：`SELECT center_code, count(*) FILTER (WHERE total_bytes > 0) AS nonzero, count(*) FILTER (WHERE total_bytes = 0) AS zero FROM lnrs_anon_v_imaging_study_counts GROUP BY center_code;` zhujiang 的 `nonzero` 应 ≥ 30,000（与 `matchable` 对齐）。
- [ ] SQL 断言：`SELECT count(*) FROM lnrs_anon_dicom_series WHERE created_batch_id IS NULL OR created_batch_id NOT IN (SELECT batch_id FROM lnrs_anon_ingest_batch);` 返回 0（每个 series 都归属一个有效 batch）。
- [ ] 日志中无 ERROR 级别记录（WARNING 允许，如目录不存在 / 路径非 DICOM 等）。
- [ ] 不动其它中心（shengyi / xinqiao / hos301）的 imaging_study 与 exam 表；这些中心的 `dicom_series` 增长仅来自本 Issue 跑 zhujiang 之外的扫描，本 Issue 不跑其它中心。
- [ ] shengyi 中心仍 0 覆盖（与 Issue 1 一致；不试图在本 Issue 修复 shengyi exam 缺口，那属于 Issue 4）。

## Blocked by

- Issue 1（回填 zhujiang imaging_study.anon_exam_id）：本 Issue 依赖其结果；未回填则 ETL-2 会 100% skip。

## Notes for implementer

- 脚本骨架在 commit `a9000c56` 中已就绪，本 Issue 主要是**执行**而非新增代码。
- 执行前确认磁盘空间充足（按 6-10 TB 影像 + 索引开销估）。
- 备份建议（不强制）：`CREATE TABLE lnrs_anon_dicom_series_bak_<timestamp> AS TABLE lnrs.lnrs_anon_dicom_series;`
- 执行中可监控进度：`SELECT count(*) FROM lnrs_anon_dicom_series WHERE created_batch_id = (SELECT batch_id FROM lnrs_anon_ingest_batch WHERE center_code='zhujiang' ORDER BY started_at DESC LIMIT 1);`
- 失败 study 不阻断（脚本注释明示），单 study 失败容错好；查看日志末尾的 `ETL2: {center} dicom_series 完成 — scanned=... series_upserted=... skipped_no_exam=... failed_studies=...` 汇总。
- 跑完后**不要**自行启动 Issue 3 —— 等待用户在另一会话根据 PRD 与本 Issue 验收决定 Issue 3 实施时机。

## 验收补充：dicom_series.anon_exam_id 回填

本 Issue 不仅是「让视图 total_bytes 非零」，还顺带完成 `lnrs_anon_dicom_series.anon_exam_id` 从 100% NULL → 全填充的回填（2026-09-19 发现 zhujiang 43,873 / shengyi 82,057 行 NULL；根因见 [Issue 1](./issue-1-backfill-imaging-study-exam-id.md) 的"同时修复 dicom_series.anon_exam_id 全 NULL"小节）。

upsert 路径已就绪（`backend/app/plugin/module_medical/hospital/anon_etl_engine.py:3212-3228`）—— `anon_exam_id` 列使用 `COALESCE(excluded.anon_exam_id, 已存值)`，已为 NULL 的行会被新值覆盖；为非 NULL 的行保持不变；所以本 Issue 的 apply 重跑是**安全的幂等回填**，不需要额外脚本。

shengyi 中心：coverage 0%（[Issue 4](./issue-4-investigate-shengyi-exam-gap.md) 单独调查），dicom_series.anon_exam_id 仍为 NULL 是预期，不需要在本 Issue 修复。