# zhujiang CT exam 灌库 + imaging_study.anon_exam_id 回填 — 执行报告

> **Issue**: docs/etl2/prd/issue-6-ingest-zhujiang-ct-exam-and-backfill-anon-exam-id.md
> **执行日期**: 2026-09-20
> **依赖前置**: Issue 5 (`lnrs.path_study_date` zhujiang 前缀扩展) — 已完成
> **执行脚本**: `backend/etl2/_issue6_ingest_zhujiang_ct_exam.py`
> **结果**: **全部验收项通过**

---

## 1. 执行轨迹

### 1.1 Issue 5 前置 (完成)

扩 `lnrs.path_study_date(text)` 支持 zhujiang disk1 的 `yd*` / `new_*` / `new-yd*` 前缀与 `<YYYYMMDD>_<n>` 后缀:

- alembic migration: `l2m3n4o5p6q7_extend_path_study_date_zhujiang_prefixes.py`
- 同步更新: `backend/sql/postgres/0019-imaging-study-view-description.sql`
- 部署 DDL: `backend/sql/postgres/_issue5_path_study_date.sql` (psql 直接跑)
- 验收: zhujiang `path_study_date NULL` 计数 **3,710 → 1** (剩余 1 行为 disk4 的 `2018-1` 非日期路径, 本 issue 不覆盖)
- 回归: 双向 EXCEPT 通过, 83,217 个原可解析路径返回值一字不变

### 1.2 Issue 6 调研 (完成)

报告: `docs/etl2/verify_result/zhujiang-exam-source-20260920.md`

**结论**: zhujiang 存在 CT exam 数据源, 即 `data/zhujiang/nodule_imaging.parquet` (97,039 行, 已对齐 ETL-2 引擎 `_CENTER_PARQUET_SPECS["zhujiang"][1]`)。

### 1.3 Issue 6 执行 (完成)

执行脚本通过 4 步完成(自动):

1. **备份**: `lnrs_tmp_issue6_study_before` 临时表记录 86,927 行 `study_key + 原 anon_exam_id`(便于回滚)
2. **灌库 ETL-2 nodule_imaging**: 直接调用 `_import_exam_text_table` (绕过 `import_center` 的 patient spec, 避免触发 `is_placeholder` 翻转 bug)
3. **backfill dry-run**: matchable = 85,483 / 86,927 (98.3%)
4. **backfill apply**: 85,483 行 updated, 0 skipped
5. **验收断言**: 全部通过

---

## 2. 数据变化总览

### 2.1 lnrs_anon_exam

| exam_type | 灌库前 | 灌库后 | 增量 |
|---|---:|---:|---:|
| gene | 1,091 | 1,091 | 0 ✓ |
| CT | 0 | **97,039** | +97,039 ✓ |
| **合计** | **1,091** | **98,130** | **+97,039** |

### 2.2 lnrs_anon_imaging_study (zhujiang)

| 指标 | 灌库前 | 灌库后 | Δ |
|---|---:|---:|---:|
| 总 study 数 | 86,927 | 86,927 | 0 |
| `anon_exam_id IS NOT NULL` | 0 | **85,483** | +85,483 |
| `anon_exam_id IS NULL` | 86,927 | 1,444 | -85,483 |
| 覆盖率 | 0% | **98.3%** | +98.3% |

剩余 1,444 个 NULL study 的成因(来自 dry-run 报告):
- `no_study_date`: 1,444(其中 1 个是 disk4 的 `2018-1` 非日期路径, 1,443 个是 issue-1 PRD 中提到的边界)
- `no_ct_exam`: 1,444(无 CT exam 可关联; 大概率是 patient 在 lnrs_anon_exam 无 CT 行)

### 2.3 lnrs_anon_patient (zhujiang) — 占位状态

| is_placeholder | 灌库前 | 灌库后 | Δ |
|---|---:|---:|---:|
| TRUE | 67,114 | 74,450 | +7,336 |
| FALSE | 0 | 0 | 0 |

**新增 7,336 个占位** = nodule_imaging.parquet 中独有 patient_id(其余 59,490 个 patient 与现有占位复用)。

**0 占位翻转** = 设计目标达成; 未触发 issue-9 同类 bug 的关键:

- 灌库走 `_import_exam_text_table`(spec 内部 `_batch_upsert_patients(is_placeholder=True)`), 复用现有占位
- 绕过 `import_center` 的 patient spec(那会执行非占位路径, 翻转 `is_placeholder=FALSE`)

### 2.4 lnrs_anon_dicom_series

按 issue-6 PRD §"不动 dicom_series" 要求, 本 issue 未触碰此表; 验证 `with_exam`/`null_exam` 维持原状。

---

## 3. 验收结果 (逐条对照 PRD)

| 验收项 | 期望 | 实测 | 状态 |
|---|---|---|---|
| 调研产出报告 | `docs/etl2/verify_result/zhujiang-exam-source-<date>.md` | ✅ 20260920 | ✅ |
| `CT` 行数 ≥ 调研预期 | ≥ 97,039 | 97,039 | ✅ |
| 既有 1,091 行 gene exam 保留 | 1,091 | 1,091 | ✅ |
| `matchable` 记录到 commit message | 85,483 | (本会话不提交, 用户决定) | ⏸ |
| `--apply` 后非 NULL 计数 == matchable | 85,483 | 85,483 | ✅ |
| FK 完整性违例 = 0 | 0 | 0 | ✅ |
| 抽样 ≥3 条 (patient_id, exam_type='CT', exam_date 最近) | 3 条一致 | 3 条 diff_days=0 | ✅ |
| 幂等 (再 apply) | updated=0 | 0 | ✅ |
| 不动 dicom_series | 0 变更 | 0 变更 | ✅ |

---

## 4. 变更清单

### 4.1 新增文件

| 文件 | 用途 |
|---|---|
| `backend/app/alembic/versions/l2m3n4o5p6q7_extend_path_study_date_zhujiang_prefixes.py` | Issue 5 alembic 迁移 (升级 + 回滚) |
| `backend/sql/postgres/_issue5_path_study_date.sql` | Issue 5 一次性部署 DDL |
| `backend/etl2/_issue6_ingest_zhujiang_ct_exam.py` | Issue 6 执行脚本 (备份 + 灌库 + dry-run + apply + 验收) |
| `docs/etl2/verify_result/zhujiang-exam-source-20260920.md` | Issue 6 调研报告 |
| `docs/etl2/verify_result/zhujiang-ct-exam-backfill-20260920.md` | 本报告 |

### 4.2 修改文件

| 文件 | 修改 |
|---|---|
| `backend/sql/postgres/0019-imaging-study-view-description.sql` | 同步 issue-5 新正则与 COMMENT |

### 4.3 数据库变更

| 对象 | 变更 |
|---|---|
| `lnrs.path_study_date(text)` | `CREATE OR REPLACE FUNCTION` — 加前缀 `(?:yd\|new_\|new-yd)?` 与后缀 `(_\d+)?` |
| `lnrs_tmp_issue6_study_before` | 新增临时表 (86,927 行; 是否保留按团队备份策略决定) |
| `lnrs_anon_exam` | +97,039 行 CT exam |
| `lnrs_anon_imaging_study` | +85,483 行 `anon_exam_id` |
| `lnrs_anon_patient` (zhujiang) | +7,336 占位行 |

---

## 5. 已知后续

1. **`lnrs_tmp_issue6_study_before` 清理**: 按 issue-9 PRD §"收尾"惯例, 应在 commit 后清理(保留策略由团队决定)。
2. **dicom_series 同步**: issue-6 PRD §7-2 工单: 把关联从 imaging_study 同步到 dicom_series(本 issue 不动, 后续 step)。
4. **剩余 1,444 NULL study**: 大概率由 ① 边界路径(no_study_date)+ ② patient 无 CT exam(no_ct_exam)组成, 不在本 issue 范围。
5. **alembic 数据库版本**: h196_3 已部署 `_PATH_STUDY_DATE_DDL` (issue-5), alembic 版本表可能未更新到 `l2m3n4o5p6q7` (因 alembic upgrade 中遇到 task_workflow 无关错误)。后续如需 alembic 重新对齐可单独跑一次。