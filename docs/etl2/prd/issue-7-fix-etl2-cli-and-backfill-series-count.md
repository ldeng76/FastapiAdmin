# Issue 7: 修 ETL-2 CLI 三处缺陷 + `dicom_series.series_count` 全量回填

## Parent

[PRD: 让 medicalFiles 页面显示真实文件总大小](./PRD.md)（视图字段 `series_count`）+ [plan-disk1-disk2-disk4-zhujiang-import.md](../plan-disk1-disk2-disk4-zhujiang-import.md)（§7-1）

## What to build

zhujiang 的 `lnrs_anon_dicom_series` 有 **86,203 行**，其中 `series_count` **100% NULL**
（DDL 允许 NULL = 未实测，但它是 PRD 视图 `lnrs_anon_v_imaging_study_counts` 的字段之一）。
这批行是走 `backfill_dicom_series_count.py --apply --bypass-exam-fk` 的 **bypass 路径**写入的，
该路径**刻意跳过** `register_folder`，所以 `file_count` / `byte_size` 有值而 `series_count` 全空。

同时 ETL-2 CLI 有三处缺陷，会让 main path 根本跑不起来（issue-2 的 acceptance 第 1 条只说
「dry-run 跑 centern」，没说要先修这些）：

| # | 位置 | 缺陷 | 后果 |
|---|---|---|---|
| 1 | `backend/env/.env.h196_3:64` | `LNRS_DATA_ROOT = "/home/dzy/wk/lnrs_dats"`，该目录**不存在** | `run_center` 直接 failed（计划 R14） |
| 2 | `backend/app/plugin/module_medical/hospital/anon_etl_service.py:63` | `_create_batch` 硬编码 `source_kind="csv_report"` | `dicom_dir` 批次标签错 |
| 3 | `backend/etl2/backfill_dicom_series_count.py:218` | `anon_exam_id=row.anon_exam_id or ""` | NULL 传空串 → FK 违反 |

**端到端目标**：三处修好 → 用 `register_folder` 路径（真实 DICOM 解析）把 86,203 行的
`series_count` 从 NULL 填成实测值 → 视图 `series_count` 可用于 PRD 后续步骤。

## Acceptance criteria

- [ ] 缺陷 1 修复：`/home/dzy/wk/lnrs_dats` 目录创建 **或** 放宽 `run_center` 守卫 **或** 给 `run_dicom_series_etl.sh` 加 `--data-root` 透传（三选一，在 commit message 说明选择理由）。验证：`run_dicom_series_etl.sh --centers zhujiang`（dry-run）能进到 DB-SCAN 分支
- [ ] 缺陷 2 修复：`_create_batch` 按调用方传参。验证：新建的 batch `SELECT source_kind FROM lnrs_anon_ingest_batch WHERE batch_id=<new>` 返回 `dicom_dir`
- [ ] 缺陷 3 修复：`anon_exam_id` 为 NULL 时不传空串。验证：`--apply` 全程无 FK 违反错误
- [ ] SQL 断言（核心）：`SELECT COUNT(*) FROM lnrs_anon_dicom_series ds WHERE ds.dicom_study_uid IN (SELECT dicom_study_uid FROM lnrs_anon_imaging_study WHERE center_code='zhujiang') AND ds.series_count IS NULL;` 返回 **0**
- [ ] 抽查 3 个 study：`series_count` == 该 study 目录下去重 `SeriesInstanceUID` 数（用 pydicom/dcmtk 人工数一遍比对）
- [ ] 幂等断言：重跑不改变已填值（`series_count` 非 NULL 的行数不变、值不变）
- [ ] 不破坏既有值：`file_count` / `byte_size` 在跑完后与跑前一致（除非确认新值更准并说明）
- [ ] 实测吞吐（study/s）记入 commit message，并与 `plan-restore-series-count.md` 的预期对比（shengyi iter3 快速路径 30-47 study/s；zhujiang 实测 **1.51 study/s**，NFS 冷数据封顶）
- [ ] 先跑 200 条 canary 估算总耗时，再决定全量机制；总耗时 >6h 时在 commit message 写明并确认可接受
- [ ] 不动其它中心（shengyi / xinqiao / hos301）的 `dicom_series` 行

## Blocked by

None - can start immediately.

## Notes for implementer

- **与 Issue 2 的边界**：Issue 2 走 `run_dicom_series_etl.sh --apply --centers zhujiang`（ETL-2 main path），
  它 upsert **新行**时会带 `series_count`，但**不会**覆盖已存在的 86,203 行（除非 ON CONFLICT 子句显式回填）。
  本 issue 负责把**已有行**补齐。两者都扫同一批目录 —— 幂等但重复劳动，跑之前先确认谁先跑、能否合并成一次。
- **两条机制，先实测再选**：
  - `backend/etl2/backfill_dicom_series_count_mp.py --workers N`（iter3 采样快速路径，单目录只读头 5 + 尾 2 个文件的 16KB）
  - 单进程 patched bypass（跳过 `register_folder`，`series_count` 留 NULL —— **不能用于本 issue**，因为本 issue 的目标正是 `series_count`）
  - zhujiang 实测：`_mp` 快速路径仅 **1.51 study/s**（NFS 封顶），单进程 `register_folder` 更慢（0.05-0.1 study/s）。
    本 issue **必须**拿到真实 `series_count`，所以不能用 bypass；在 1.51 study/s 下 86,203 study ≈ **16 小时** —— 排期前务必先 canary 实测。
- 现有 `series_count` 语义（DDL 注释）：实测口径 = `DicomIndexer.register_folder` 去重 `SeriesInstanceUID` 计数，
  跳过非图像模态（SR/RTPLAN/RTDOSE/RTSTRUCT/ST）。`0` = 实测无合法 DICOM 图像；`NULL` = 未实测。
- 监控进度：`SELECT COUNT(*) FROM lnrs_anon_dicom_series ds WHERE ds.dicom_study_uid IN (SELECT dicom_study_uid FROM lnrs_anon_imaging_study WHERE center_code='zhujiang') AND ds.series_count IS NOT NULL;`
