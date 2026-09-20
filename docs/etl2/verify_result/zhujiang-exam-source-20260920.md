# zhujiang CT exam 数据源调研

> **Issue**: docs/etl2/prd/issue-6-ingest-zhujiang-ct-exam-and-backfill-anon-exam-id.md
> **调研日期**: 2026-09-20
> **调研人**: 后端自动化 (Claude / lnrs dev session)
> **结论**: **zhujiang 存在 CT exam 数据源** — `data/zhujiang/nodule_imaging.parquet` (97,039 行, 已是 ETL-2 引擎期望格式)。

---

## 1. 起点数据

`lnrs_anon_exam WHERE center_code='zhujiang'` 现状:

| exam_type | 行数 | 覆盖患者数 |
|---|---:|---:|
| gene | 1,091 | 1,030 |
| (其它) | 0 | – |
| **合计** | **1,091** | **1,030** |

`lnrs_anon_imaging_study WHERE center_code='zhujiang'` 现状:

| 指标 | 值 |
|---|---:|
| 总 study 数 | 86,927 |
| `anon_exam_id IS NOT NULL` | 0 |
| `path_study_date IS NULL` (改造前) | 3,710 |

## 2. 数据源扫描结果

### 2.1 NFS 原始提取目录 `/mnt/nfs_d/wlx/DATABASE/extracted_tables/zhujiang/`

| 文件 | 行数 | 列(前 6) | 是否含 CT |
|---|---:|---|---|
| `ct.parquet` | **97,039** | patient_id, exam_id, pat_local_id, exam_date, exam_name, contrast, … | **是** — 列 `exam_name='平扫加增强'` 等 |
| `ct_dicom_map.parquet` | 87,179 | pat_local_id, exam_id, dir, filenames | 路径映射,不直接是 exam 表 |
| `face.parquet` | 9,567 | id, visit_id, 医疗付费方式, 性别, … | 否(住院首页) |
| `genetics.parquet` | 1,091 | patient_id, exam_id, exam_date, sample_source, test_method, panel_size, … | 否(基因检测) |
| `ihc.parquet` | 6,827 | patient_id, exam_id, exam_date, ki67_pct, pdl1_tps_pct, … | 否(免疫组化) |
| `inpatient.parquet` | 9,590 | patient_id, inpatient_id, inpatient_date, … | 否(住院) |
| `operation.parquet` | 18,326 | patient_id, inpatient_id, operation_date, operation_name, … | 否(手术) |
| `pathology.parquet` | n/a | (脚本生成, 非 parquet) | 否 |
| `patient.parquet` | 6,714 | patient_id, source_center, sex, … | 否(patient) |

**关键发现**:`ct.parquet` 共 **97,039 行**, 与 zhujiang `lnrs_anon_imaging_study` 86,927 行(87%)数量级一致 — 显然这张表就是 zhujiang CT 检查的源头数据。`exam_date` 列已是字符串 'YYYY-MM-DD'。

### 2.2 ETL-1 staging 目录 `/home/dzy/wk/lnrs/data/zhujiang/`

| 文件 | 行数 | 是否符合 ETL-2 引擎 spec |
|---|---:|---|
| `patient.parquet` | 66,846 | 是(`_CENTER_PARQUET_SPECS["zhujiang"][0]` kind=patient) |
| `nodule_imaging.parquet` | **97,039** | **是**(specs[1] kind=exam_text, exam_type='CT', id_field='exam_id') |
| `pathology_specimen.parquet` | 12,096 | 是(specs[3] kind=exam_text, exam_type='pathology_text') |

**`nodule_imaging.parquet` 已经是 ETL-2 引擎期望的格式**(列布局完全对齐 `_CENTER_PARQUET_SPECS["zhujiang"][1]`: body_fields=['findings','impression'], detail_fields=[…], ordinal_field='nodule_no')。

数据来源:2026-09-20 ETL-1 适配脚本 `etl1_adapt_zhujiang_ct_pathology.py` 跑出来的(基于 `data/zhujiang/` 已有的 ct0820 → nodule_imaging 链路)。**不是新增的源,而是 ETL-1 → ETL-2 中间产物,从未跑过 ETL-2 灌库步骤**。

### 2.3 其它 staging 目录

| 目录 | 是否含 CT exam 源 |
|---|---|
| `data_zj0825/zhujiang/` | 只有 genetic_test(2026-08-25 批次, 1,091 行, 与 lnrs_anon_exam 现有 1,091 行 gene exam 同源) |
| `data_zj0825raw/zhujiang/` | nodule_imaging 172,305 行(更宽,含 lung_rads),但 staging 列与 ETL-2 spec 略不同;同时数据更全但 ETL-2 引擎消费的就是 `data/zhujiang/nodule_imaging.parquet`,无须更换 |
| `data_zj_face/zhujiang/` | 只有 face_sheet 系列(住院首页),无 exam |

## 3. 结论

| 项 | 结论 |
|---|---|
| zhujiang 是否存在 CT exam 数据源 | **存在** |
| 数据源路径 | `/home/dzy/wk/lnrs/data/zhujiang/nodule_imaging.parquet` |
| 行数 | 97,039(唯一 exam_id 97,039) |
| exam_type | 全部 `'CT'`(已固化) |
| exam_date 范围 | 2016-01-05 ~ 2026-01-06(实测样本) |
| 引擎期望格式 | ✅ 完全对齐 `_CENTER_PARQUET_SPECS["zhujiang"][1]` |
| 灌库动作 | **需要**:通过 ETL-2 引擎 `import_center` 触发 `_import_exam_text_table` 写入 `lnrs_anon_exam`(+ `report_text` + `exam_detail`) |

## 4. 后续动作

1. ✅ Issue 5 已完成(2026-09-20 完成, zhujiang `path_study_date` NULL 计数从 3,710 → 1)
2. **下一步**:跑 ETL-2 把 `nodule_imaging.parquet` 灌库 → 预期 lnrs_anon_exam 新增 97,039 行 `CT` exam
3. 灌库后跑 `backfill_imaging_study_exam_id.py --dry-run --center zhujiang` 取 matchable 期望值
4. 跑 `--apply` 实际回填 `lnrs_anon_imaging_study.anon_exam_id`
5. 验收断言

## 5. 风险

| 风险 | 缓解 |
|---|---|
| 灌库耗时:97,039 行 × 引擎开 batch/BATCH_SIZE=1000 + report_text + exam_detail,总耗时估 5-15 min | 设置 sub-tx 阈值 SUB_TX_ROWS=100000 (env),失败回滚可控 |
| dicom_series 表的 `anon_exam_id` 不由本次回填覆盖 (issue-6 PRD §"不动 dicom_series") | 已记录,需后续 §7-2 工单同步 |
| patient 占位 vs 真实档案: zhujiang 现有 67,114 patient 全为占位, 灌库 exam 后会触发 _batch_upsert_patients 的占位回填路径 | 与 PRD "现有 1,091 行 gene exam 不要删" 不冲突,引擎 idempotent upsert |
| 备份建议: PRD 提到 `CREATE TABLE lnrs_anon_imaging_study_bak_<ts> AS TABLE lnrs.lnrs_anon_imaging_study;` | 本调研不执行,执行前由实施人手工备份 |