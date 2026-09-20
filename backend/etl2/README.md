# backend/etl2 — ETL-1 适配 + 方案 B 后续脚本

本目录存放 ETL-1 适配脚本与方案 B（dicom_series 落库）的回填 / 跑库脚本。

## 文件清单

| 文件 | 用途 |
|---|---|
| `etl1_adapt_*.py` | ETL-1 适配：把各中心原始 parquet 转为 ETL-2 引擎期望的 parquet 布局 |
| `backfill_imaging_study_exam_id.py` | 方案 B 步骤 1：回填 `lnrs_anon_imaging_study.anon_exam_id`（dry-run + apply） |
| `run_dicom_series_etl.sh` | 方案 B 步骤 2：一键跑 ETL-2 dicom_series 阶段的包装脚本 |

## 方案 B 完整执行步骤

### 步骤 0：环境准备

```bash
cd /home/dzy/wk/lnrs/backend
ENVIRONMENT=h196_3 uv run python ../backend/etl2/backfill_imaging_study_exam_id.py --dry-run
```

预期（h196_3 实测 2026-09-15）：

```
center          total  matchable     <=1d     <=7d  no_study_date  no_ct_exam
------------ -------- ---------- -------- -------- -------------- -----------
shengyi         82994          0        0        0          82994       82994
zhujiang        36356      36342    36337    36342             14          14
合计: 36342/119350 study 可回填 (30.4%)
```

**重要发现**：

- zhujiang 覆盖率 100%；
- shengyi 覆盖率 0%——**shengyi 大部分 patient 在 exam 表里没有任何 exam 行**（219/82,988 = 0.26%），需另案补 shengyi exam 入库；
- 全量上限 30.4%（36,342 study）。

### 步骤 1：回填 imaging_study.anon_exam_id

```bash
# 仅 zhujiang（推荐首跑：风险可控、100% 覆盖）
ENVIRONMENT=h196_3 uv run python ../backend/etl2/backfill_imaging_study_exam_id.py --apply --center zhujiang

# 全量（含 shengyi 0 覆盖，对 shengyi study 是 noop）
ENVIRONMENT=h196_3 uv run python ../backend/etl2/backfill_imaging_study_exam_id.py --apply
```

幂等：UPDATE 含 `WHERE anon_exam_id IS NULL` 守卫，重复执行 noop。

### 步骤 2：跑 ETL-2 dicom_series 阶段

```bash
# dry-run（不修改数据，仅打印 ETL-2 处理计划）
ENVIRONMENT=h196_3 backend/etl2/run_dicom_series_etl.sh

# 实际跑全量
ENVIRONMENT=h196_3 backend/etl2/run_dicom_series_etl.sh --apply

# 仅 zhujiang
ENVIRONMENT=h196_3 backend/etl2/run_dicom_series_etl.sh --apply --centers zhujiang
```

预计耗时：

- zhujiang：6-12 小时（36,356 study × 22-116MB × `fpath.stat()`）
- shengyi：< 1 小时（82,994 study 中 99.7% 仍 anon_exam_id NULL → 全部 skip）
- xinqiao / hos301：< 30 分钟

### 步骤 3：切 service 到视图（待用户单独决策）

详见 `local://plan_b_evidence.md` §三。

## 数据现状（h196_3，2026-09-15）

```
lnrs_anon_imaging_study        119,350 行（anon_exam_id 全 NULL）
lnrs_anon_dicom_series             4 行（commit f8dd292e 手工验证）
lnrs_anon_v_imaging_study_counts   视图（SUM byte_size → total_bytes）
```

## 回退

| 阶段 | 回退命令 |
|---|---|
| 步骤 1 回填 | `UPDATE lnrs.lnrs_anon_imaging_study SET anon_exam_id = NULL;`（仅步骤 1 内生效；若步骤 2 已跑 dicom_series，需先回滚步骤 2） |
| 步骤 2 落库 | `DELETE FROM lnrs.lnrs_anon_dicom_series WHERE created_batch_id = '<batch>';` |
| 完整回退 | `DROP TABLE lnrs.lnrs_anon_dicom_series;` + 重跑 `0006-anonymized-schema-lnrs.sql §7` |

> ⚠ **回退前必读**：`lnrs_anon_dicom_series` 是 `ingest_batch` 的 CASCADE 子表 ——
> `DELETE FROM lnrs_anon_ingest_batch WHERE ...` 会连带删除对应 `dicom_series` 行
> （2026-09-20 事故：一条按 `center_code` 的测试清理删掉 168,260 行）。
> 完整复盘见 [`docs/etl2/findings/incident-20260920-test-cascade-delete.md`](../../docs/etl2/findings/incident-20260920-test-cascade-delete.md)。
> 另注：该文档 §3.1 记录了 **DDL 文件与 live schema 的 FK 已分叉** ——
> 判断级联范围请查 live `pg_constraint`，不要读 DDL。

## 与既有核验的关系

`/home/dzy/wk/lnrs/docs/etl2/数据导入核验清单.xlsx`（2026-09-14 收口）覆盖 shengyi 的 23 张 parquet 派生表。本目录的两个脚本对应**核验清单之外的 dicom_series 落库**——数据源是磁盘 DICOM 目录（不在 parquet 体系内），从未进入核验清单。