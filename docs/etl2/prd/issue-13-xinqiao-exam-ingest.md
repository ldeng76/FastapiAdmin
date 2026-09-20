# Issue 13: 新桥 exam 灌库 + 回填 `lnrs_anon_dicom_series.anon_exam_id`（xinqiao）

## Parent

[plan-xinqiao-disk03-import.md](../plan-xinqiao-disk03-import.md)（§7-4）

## What to build

新桥 33,314 study 全部 `anon_exam_id=NULL`（plan-xinqiao §0.6-5 B 方案）；同 issue-6 的 zhujiang
exam 灌库路径，从新桥 PACS/HIS 拿到 exam 行后灌入 `lnrs_anon_exam`，再回填
`imaging_study` 与 `dicom_series` 的 `anon_exam_id`。

**端到端目标**：xinqiao 的 `lnrs_anon_dicom_series.anon_exam_id` 不再全 NULL（覆盖率 = 实际 match 数）。

## Acceptance criteria

- [x] 明确 xinqiao exam 的输入源（新桥 PACS 导出 / 现有 HIS 表 / 第三方 ETL），写入 issue 评注
  → 新桥 PACS/HIS extracted_tables 导出 `/data/wlx/DATABASE/extracted_tables/xinqiao/ct.parquet`（124,045 CT exam）；
     调研与证据：`docs/etl2/verify_result/xinqiao-exam-source-20260920.md`；实施评注见文末「实施记录」。
- [x] 复用 issue-6 的脚本（`backend/etl2/_issue6_ingest_zhujiang_ct_exam.py`）扩展 `--center xinqiao`；
  关联算法沿用 issue-1（patient_id + study_date 距离最小）
  → `backend/etl2/_issue13_ingest_xinqiao_ct_exam.py`（`--center xinqiao`；复用 issue-6 的
     备份→灌库→dry-run→apply→验收 路径、引擎 `_import_exam_text_table` 直调、0904 适配脚本）。
     study_date 表达式扩展为 `COALESCE(path_study_date(image_path), uid_study_date(dicom_study_uid))`
     （xinqiao image_path 无日期，UID 内嵌时间戳兜底；关联算法本体不变，见调研文档 §3）。
- [x] h196_3 dry-run：报告 matchable 行数（应在数千到数万级别；非零是关键）
  → tier-1 dry-run **matchable=31,098**（no_study_date=2,216，其中 2,012 个患者有 CT exam 走残留兜底）。
- [x] h196_3 --apply：成功跑完且无 ERROR 日志（`/tmp/issue13_run.log`，EXIT=0 见实施记录）。
- [x] SQL 断言 1：`…dicom_series…xinqiao…ds.anon_exam_id IS NOT NULL` **> 0** → **33,110**（V1）。
- [x] SQL 断言 2：外键完整性 → **0**（V2）。
- [x] SQL 断言 3：未漏匹配 → **0**（V3；PRD 原文子查询误用 `lnrs_anon_exam.dicom_study_uid`
  （该列不存在），按意图改写为 EXISTS(patient+CT exam)，见调研文档 §5）。
- [x] 重跑幂等：再执行一次 `--apply --center xinqiao`（`--skip-adapt --skip-ingest` 重跑，
  `/tmp/issue13_rerun.log` EXIT=0）：tier-1 updated=0、residual=0、series=0，
  回填行数保持 33,110 不变（脚本守卫 `WHERE anon_exam_id IS NULL`）。
- [x] 不动 xinqiao 已入库的 patient / imaging_study / dicom_series 的现有数据；不动 zhujiang / shengyi
  → imaging_study 33,314 行全列 diff（除 anon_exam_id/updated_at）**= 0**（对执行前备份表
     `lnrs_anon_imaging_study_bak_20260920_104619`）；dicom_series 全列 checksum（除 anon_exam_id）
     与执行前基线逐字节一致（该表无 updated_at 触发器，UPDATE 仅触碰 anon_exam_id）；
     updated_at 仅在 33,110 个回填行变化。V9：zhujiang 86,927/85,483、shengyi 82,994/0 与执行前基线一致。
- [x] 备份：执行前 `CREATE TABLE lnrs_anon_imaging_study_bak_20260920_104619 AS SELECT * FROM
  lnrs.lnrs_anon_imaging_study WHERE center_code='xinqiao'`（+33,314 行；PRD 原文 `AS TABLE … WHERE`
  非合法 PG 语法，按意图改为 CTAS+SELECT）；另 dicom_series.anon_exam_id 现值入
  `lnrs_tmp_issue13_series_before`（回退用）。

## Blocked by

- [Issue 6](./issue-6-ingest-zhujiang-ct-exam-and-backfill-anon-exam-id.md)（同模式，借鉴脚本）
- 与 [Issue 18](./issue-18-xinqiao-cxf-archives-ingest.md) 软联动：若新桥 exam 与 cxf_archives 同源
  （同一 PACS 导出），可一起做

## Notes for implementer

- xinqiao 有 33,314 study / 33,313 PID，规模与 zhujiang 相近；exam 入库量级需先期评估
- 若新桥 PACS 导出文件过大或格式特殊，可能需要新建脚本而非复用 issue-6
- exam 表的 `anon_exam_id` 已 `NOT NULL`；灌库前先确认 DDL 不需新增列
- 与 issue-15（占位真实化）强依赖：本 issue 跑完后才能 issue-15

---

## 实施记录（2026-09-20，h196_3）

### 输入源结论（验收 1）

- xinqiao exam 输入源 = **新桥 PACS/HIS extracted_tables 导出**
  `/data/wlx/DATABASE/extracted_tables/xinqiao/ct.parquet`（124,045 distinct exam_id，
  exam_date 100% 非空）。当前 h196_3 `lnrs_anon_exam` 原本**无 xinqiao 行**
  （0904 批次 `843e8c43-…` 灌的是另一环境），故本次为 h196_3 首次灌入。
- `ct_dicom_map.parquet`（186,678 行 exam→series 目录映射）用作无日期残留 study
  的文件数精确匹配；pathology/genetics 不在本 issue 范围（只灌 CT）。

### 关联算法（验收 2）

- 复用 issue-6 执行路径 + 引擎 `_import_exam_text_table` 直调（不走 ETL2 CLI，
  避免连带触发 xinqiao spec 的 dicom_series 重注册）。
- study_date 扩展：`COALESCE(lnrs.path_study_date(image_path), lnrs.uid_study_date(s.dicom_study_uid))`。
  xinqiao image_path 无日期（path_study_date 100% NULL），**94% 的 StudyInstanceUID
  内嵌检查时间戳**（GE 系），实测 31,097 个有日期 study 中 99.93% 与同患者 CT
  exam_date **同日** → UID 日期即检查日期（`lnrs.uid_study_date` 见
  `backend/sql/postgres/0027-uid-study-date.sql` + alembic `m3n4o5p6q7r8`）。
- 关联本体（patient_id + 日期最近 + anon_exam_id 平局）在
  `backfill_imaging_study_exam_id.py` 中 0 算法变更，仅 study_date 表达式扩展。

### 执行结果（验收 3-9）

| 指标 | 值 |
|---|---:|
| 灌库 CT exam | **124,045**（首跑 batch `4a0e0717-…` + 全量幂等重跑 batch `2f1fa483-…`，均 success；重跑 0 新增行） |
| 患者 upsert | 复用 **33,109**（既有 xinqiao 占位）+ 新增 **16,351**（exam-only 占位，sex='0'，seq 551098..567448） |
| tier-1 matchable（dry-run） | **31,098**（no_study_date=2,216） |
| 残留兜底（2,012） | filecount **1,216** + single **795** + tiebreak **1** |
| imaging_study 回填 | **33,110 / 33,314（99.39%）** |
| dicom_series 回填 | **33,110**（1:1 study） |
| 日期距离（V8） | 0d=31,078 / ≤1d=31,097 / ≤7d=31,098 / 无日期=2,012 |
| 保持 NULL | 204（204 个无 CT exam 的患者，断言 3 不受影响） |

- 验收 SQL：`docs/etl2/verify_xinqiao_exam.sql` V1–V10 全过（V1=33,110>0 / V2=0 / V3=0 /
  V5=0 / V6=0 / V7=124,045；V9 zhujiang 86,927/85,483、shengyi 82,994/0 与执行前一致；
  V10 patient 零漂移：dicom_created=33,313 / exam_new=16,351 / placeholder_sex0=49,664 / soft_deleted=0）。
- 幂等重跑两次：
  - 跳灌库（`--skip-adapt --skip-ingest`，`/tmp/issue13_rerun.log`）：tier-1 updated=0、
    residual=0、series=0，33,110 不变，EXIT=0。
  - 全量（无任何 skip，`/tmp/issue13_rerun2.log`，PRD 字面口径「再执行一次 --apply」）：
    重适配 + 重灌库（124,045 行 upsert，0 新增；患者 49,460 全部复用，0 新增）+
    tier-1 updated=0 + residual=0 + series=0，33,110 不变，零漂移 assert 通过，EXIT=0；
    重跑 batch `2f1fa483-…` 正常关闭 success（验证修复后的关闭路径）。
- 零变更证明：imaging_study 对备份表全列 diff（除 anon_exam_id/updated_at）= 0；
  dicom_series 全列 checksum（除 anon_exam_id）与执行前基线一致；updated_at 仅 33,110 回填行变化；
  patient 零漂移见 V10（引擎占位 upsert 冲突时只刷新 last_seen_batch_id + 复活软删，
  不覆盖人口学/created_batch_id —— `anon_etl_engine._batch_upsert_patients` is_placeholder 分支）。
- 备份：`lnrs.lnrs_anon_imaging_study_bak_20260920_104619`（首跑，33,314 行）+ 重跑新建的
  `…_bak_20260920_113403` 快照 + `lnrs.lnrs_tmp_issue13_series_before`（33,314 行，回退用）。

### 变更文件

| 文件 | 改动 |
|---|---|
| `backend/etl2/_issue13_ingest_xinqiao_ct_exam.py` | 新建：备份→适配→灌库→tier-1→残留兜底→series→验收（`pick_residual_exam` 为可测纯函数） |
| `backend/etl2/backfill_imaging_study_exam_id.py` | study_date 表达式扩展（COALESCE uid 日期）+ `coverage_report_sql()` helper + `run_dry_run` 返回报告行；关联算法不变 |
| `backend/sql/postgres/0027-uid-study-date.sql` | 新建：`lnrs.uid_study_date(text)`（plpgsql IMMUTABLE） |
| `backend/app/alembic/versions/m3n4o5p6q7r8_add_uid_study_date.py` | 新建：alembic 版本（同函数） |
| `backend/tests/anon_etl/test_issue13_xinqiao_exam_backfill.py` | 新建：`pick_residual_exam` seam 测试（8 例） |
| `docs/etl2/verify_xinqiao_exam.sql` | 新建：V1–V10 验收 SQL |
| `docs/etl2/verify_result/xinqiao-exam-source-20260920.md` | 新建：输入源调研 + 关联可行性实测（含执行前预测 vs 实际对照） |
| `.gitignore` | + `/data_xq0913/` 行已在工作区；因该文件 diff 混入无关 WIP（见「遗留/发现」），**本提交不含 .gitignore** |

### 遗留 / 发现

- **代码评审发现并已修复的缺陷**：首跑 batch `4a0e0717` 在脚本退出后仍停 `running`
  （row_counts={} / finished_at NULL）—— `ingest_ct_exam` 的 `_close_batch` UPDATE
  无 `commit()`，会话结束被回滚（batch INSERT 在独立事务已提交，故只剩关闭丢失）。
  修复：success/failed 两处均加显式 commit（与 `run_center` 失败路径惯例一致）。
  `4a0e0717` 已手动关闭为 success（row_counts={"nodule_imaging": 124045}）；
  全量重跑（batch `2f1fa483-…`）端到端验证修复后的关闭路径 = success。
- **issue-6 遗留缺陷（未修，超出本 issue 范围）**：`lnrs_anon_ingest_batch` 中 zhujiang
  两个 batch（`58966961-…`、`708381a5-…`）status 停在 `running` 且 row_counts 为空
  —— issue-6 脚本直调 `_import_exam_text_table` 后未 `_close_batch`。zhujiang 两行
  属历史数据，未动（「不动 zhujiang」约束）；如需修正请单独处理。
- **.gitignore 未随本提交入库**：工作区中该文件已混入无关 WIP 改动（删
  `/data_hos301/`、增 `/data_zj_face/`、` /data_xq0904/`/` /.workbuddy/` 行首空格
  致锚定失效）；本 issue 仅新增 `/data_xq0913/` 一行，与上述 WIP 无法按 hunk 拆分，
  故整体移出本提交，待原作者合并时一并入库。
- shengyi 有 45 个 study 的 path_study_date 为 NULL 但 UID 含日期：COALESCE 扩展使
  它们**在未来**不限中心的 backfill 运行中可被匹配（本次 `--center xinqiao` 未触碰
  shengyi 任何行，V9 已证）。属严格改进（同一 issue-1 语义），非回归。
- 残留 tiebreak 1 例（患者多 CT、文件数无匹配）：按 anon_exam_id 字典序最小兜底，
  语义为「同患者 CT exam」，满足断言 3；如需更高精度可后续用 ct_dicom_map 的
  StudyUID（布局 C）做精确 join 复核。
- 本 issue 完成后解锁 [Issue 15](./issue-15-xinqiao-placeholder-realization.md)（占位真实化）。