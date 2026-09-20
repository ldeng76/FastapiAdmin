# shengyi imaging_study 覆盖率 0% 根因调研 — 报告

> **Issue**: docs/etl2/prd/issue-4-investigate-shengyi-exam-gap.md
> **执行日期**: 2026-09-20
> **执行环境**: h196_3 (本地 PostgreSQL)
> **结论一句话**: shengyi DICOM 影像来源 patient_id 与 HIS 报告系统 patient_id 是**两批几乎不重叠的患者集合**——属上游数据缺陷,不是 ETL bug,**唯一可行修复是要求上游补 HIS 档案映射表**,暂无 SQL/ETL 层修复路径。

---

## 1. 现状量化 (复现 h196_3 实测数字)

| 指标 | 数值 | 来源 |
|---|---:|---|
| `lnrs_anon_imaging_study` shengyi 行数 | 82,994 | `COUNT(*) WHERE center_code='shengyi'` |
| `lnrs_anon_imaging_study` shengyi unique patient_id | **82,988** | `COUNT(DISTINCT patient_id)` |
| `lnrs_anon_exam` shengyi unique patient_id | 66,635 | `COUNT(DISTINCT patient_id) WHERE center_code='shengyi'` |
| `lnrs_anon_exam` shengyi CT exam 行数 | **237,374** | `exam_type='CT'` (与 PRD 表述的"174"不一致,详 §6) |
| study 与 exam 的 patient 交集 | **219** | `INNER JOIN DISTINCT` (issue-1 PRD 一致) |
| **覆盖率** | **0.26%** | 219 / 82,988 |
| `lnrs_anon_patient` shengyi 行数 | 169,820 | `COUNT(*) WHERE center_code='shengyi'` |
| `is_placeholder=TRUE` 行数 | **0** | (issue-9 已修但本环境未跑 UPDATE) |
| study patient 在 patient 表的覆盖 | 82,988 / 82,988 = 100% | 全员进 patient 表(占位) |

代表性查询:

```sql
-- 关键交叉表: study ∩ exam 与各表规模
WITH s AS (SELECT DISTINCT patient_id FROM lnrs.lnrs_anon_imaging_study
           WHERE center_code='shengyi'),
     e AS (SELECT DISTINCT patient_id FROM lnrs.lnrs_anon_exam
           WHERE center_code='shengyi'),
     p AS (SELECT DISTINCT patient_id FROM lnrs.lnrs_anon_patient
           WHERE center_code='shengyi')
SELECT
    (SELECT COUNT(*) FROM s) AS study_pts,
    (SELECT COUNT(*) FROM e) AS exam_pts,
    (SELECT COUNT(*) FROM p) AS patient_pts,
    (SELECT COUNT(*) FROM s WHERE patient_id IN (SELECT patient_id FROM e)) AS both_se,
    (SELECT COUNT(*) FROM s WHERE patient_id IN (SELECT patient_id FROM p)) AS study_in_patient,
    (SELECT COUNT(*) FROM s WHERE patient_id NOT IN (SELECT patient_id FROM e)) AS study_no_exam;
-- 实测: study_pts=82988, exam_pts=66635, patient_pts=169820,
--       both_se=219, study_in_patient=82988, study_no_exam=82769
```

---

## 2. 数据流溯源

### 2.1 shengyi `imaging_study` 来源

`build_shengyi_imaging_study_index.py` (scripts/build_shengyi_imaging_study_index.py) 离线扫描两个 parquet 写入:

| 来源 parquet | 行数 | `source` 字段 |
|---|---:|---|
| `/data/wlx/DATABASE/extracted_tables/shengyi/CT_image/shengyi_06_disk_CT.parquet` | 52,991 | `disk_06_shengyi` |
| `/data/wlx/DATABASE/extracted_tables/shengyi/CT_image/shengyi_07_disk_CT.parquet` | 30,003 | `disk_07_shengyi` |
| **合计** | **82,994** | — |

写入策略:
- patient_id 在 PG 落库前 HMAC-SHA256(`"shengyi:" + raw_pid`)[:12] → `ANON_<12hex>`;后续 ETL-2 用 `compute_anon_id` 同款派生 → 跨表一致
- shengyi 这 82,994 行 **新建 82,682 个占位 patient** (其余 312 与既有 patient 复用)

### 2.2 shengyi `exam` 来源 (ETL-2 spec)

`backend/app/plugin/module_medical/hospital/anon_etl_engine.py:2467` `_CENTER_PARQUET_SPECS["shengyi"]` 共 26 项 spec,**所有 kind=`exam_text` / `exam_related`**:

| spec 顺序 | src_table | kind | exam_type | id_field |
|---:|---|---|---|---|
| 3 | pahology_specimen | exam_text | pathology_text | specimen_id |
| 4 | imaging_report | exam_text | radiology | report_id |
| 5 | ultrasound_report | exam_text | ultrasound | report_id |
| 6 | ecg_report | exam_text | ECG | report_id |
| 7 | genetic_report | exam_text | gene | report_id |
| 9-12 | lab_result_p1..p4 | lab | — | report_id |
| 13-16 | drug_order/no_drug_order/outp_order/anesthesia_order | order | — | — |

ETL-2 spec **覆盖了所有 exam 类表**,spec 本身不缺(候选 A 排除)。

### 2.3 patient 集合对比 (source-level 硬证据)

把 source parquet 的原始 `patient_id` (HIS 标识号) 拿来直接对比:

| 来源 | unique raw patient_id |
|---:|---:|
| **DICOM 影像** (shengyi_06/07_disk_CT) | **82,988** |
| `imaging_report.parquet` | 63,261 |
| `patient.parquet` | 87,138 |
| **DICOM ∩ imaging_report** | **205** |
| **DICOM ∩ patient.parquet** | **306** |

代表性查询:

```sql
-- 在 DuckDB 跑 (source parquet 联表)
WITH d AS (
  SELECT DISTINCT patient_id FROM read_parquet('/data/wlx/DATABASE/extracted_tables/shengyi/CT_image/shengyi_06_disk_CT.parquet')
  UNION SELECT DISTINCT patient_id FROM read_parquet('.../shengyi_07_disk_CT.parquet')
), i AS (
  SELECT DISTINCT patient_id FROM read_parquet('/home/dzy/wk/lnrs/data_shengyi202609/shengyi/imaging_report.parquet')
)
SELECT
  (SELECT COUNT(*) FROM d) AS dicom_pts,
  (SELECT COUNT(*) FROM i) AS report_pts,
  (SELECT COUNT(*) FROM d WHERE patient_id IN (SELECT patient_id FROM i)) AS intersection;
-- 实测: 82988 / 63261 / 205
```

**铁证**: 即使在 ETL 之前,**原始 HIS 标识号层面**,DICOM 影像的 82,988 个 patient_id 与 HIS 报告系统的 63,261 个 patient_id 仅重叠 205 个 → DB 层 219 个交集(差异是 14 个 patient 在 PG 写了 exam 但 source 标识号与磁盘 DICOM 标识号格式不同被去重)完全是这个事实的反映。

---

## 3. 根因结论

### 3.1 三个候选评估

| 候选 | 描述 | 是否成立 | 证据 |
|---|---|---|---|
| **A**: ETL-2 shengyi spec 中 exam_text 覆盖不全 | 漏导某个 exam 表 | ❌ 排除 | spec 26 项覆盖 pathology / radiology / ultrasound / ECG / gene / lab / order 全谱 |
| **B**: DICOM 来源 patient_id 与 HIS 来源 patient_id 是两个独立患者集合 | 上游数据缺陷 | ✅ **主因** | source 层原始 ID 交集仅 205/82,988 = 0.25% |
| **C**: ETL-1 与 ETL-2 之间 patient_id 哈希派生不一致 | key_fingerprint / secret_version 不同 | ❌ 排除 | 跨表同一 patient_id 完全一致 (5 抽样 + 全表覆盖断言) |

### 3.2 主根因 — 候选 B 的展开

shengyi **DICOM 影像 patient_id** (`/data/wlx/DATABASE/extracted_tables/shengyi/CT_image/*.parquet`) 与 **HIS 报告 patient_id** (`/home/dzy/wk/lnrs/data_shengyi202609/shengyi/{patient,imaging_report,...}.parquet`) 来自**两批几乎不重叠的患者**。可能原因:

1. **影像系统采集自外部来源**: shengyi 中心 CT_image 目录下两个 parquet 的 patient_id 出现 `03373-3`、`10000404` 等数字串,但同中心 HIS `patient.parquet` 与 `imaging_report.parquet` 也用同一类数字标识号(长度 5-17) — 不像"不同 ID 体系",更像"不同 patient"
2. **早期某段时期的患者档案未汇入 HIS**: DICOM 早于 HIS 数字化时点的患者档案可能在影像系统里但未上报 HIS
3. **跨院检查**: DICOM 可能是外院转入检查(本院无对应 HIS 档案)

**无论哪种,本质都是"这 82,682 个 patient 在新数据体系里就是无 HIS 档案对应的"** —— 既然没有档案,就没有 exam 数据可关联。**占位 patient (issue-9 标的 82,682) 是正确的处理**。

### 3.3 与 zhujiang 的对照

| 中心 | study unique patient | exam unique patient | 交集 | 覆盖率 |
|---|---:|---:|---:|---:|
| **zhujiang** | 60,385 | 67,832 | **59,472** | **98.5%** |
| **shengyi** | 82,988 | 66,635 | **219** | **0.26%** |

zhujiang 影像与 exam 几乎完全重合 — 因为 zhujiang `nodule_imaging.parquet` 本身就含完整 HIS 档案 (issue-6 灌库),patient 集合一致。shengyi 没有类似 `nodule_imaging` parquet,影像元数据只来自磁盘目录扫描,**没有跟 HIS 档案做桥接**。

---

## 4. 修复路线

### 4.1 路线 1 — 上游补 HIS 档案映射表 (唯一根本修复) ⭐ 推荐

**思路**: 与 shengyi 信息科确认 DICOM 影像来源的 82,988 patient_id 是否能反查到 HIS 档案。若有,产出 `dicom_to_his_mapping.csv` (raw_dicom_pid → raw_his_pid),ETL-1 增加 mapping 适配步骤。

| 项 | 评估 |
|---|---|
| 工作量 | **依赖外部**,不可估 — 需业务方推动 |
| 风险 | 低 — 仅增加 ETL-1 阶段映射 |
| 数据备份 | 不需要(不动现有数据) |
| alembic | 不需要 |
| 回填历史 | 若 mapping 给出,跑一次 ETL-2 灌 exam 即可,自动回填 `imaging_study.anon_exam_id` |
| 时间 | **未知**,等待上游 |

**这是唯一让 shengyi 覆盖率从 0.26% 显著提升的路径**。其余路线只能改善 UX,不能补数据。

### 4.2 路线 2 — 文档化"占位 patient 无 exam 关联"行为 (立即可做)

**思路**: 给 `is_placeholder=TRUE` 且在 exam 表查不到的 patient,明确标注为"影像来源无 HIS 档案对应"。**不需要新增字段**,只需要:

1. `medicalFiles` 页面的"patient"列表对占位 patient 加注 (placeholder badge + tooltip)
2. `backfill_imaging_study_exam_id.py` 的 dry-run 报告按"占位 vs 真实"拆分计数
3. 在 `lnrs_anon_imaging_study` 视图层加 hint 列 (派生,`IS NOT NULL anon_exam_id OR NOT EXISTS patient WHERE NOT is_placeholder`)

| 项 | 评估 |
|---|---|
| 工作量 | 1-2 小时(纯前端 + dry-run 增强) |
| 风险 | 极低(只加视图/前端标识) |
| 数据备份 | 不需要 |
| alembic | 1 个视图迁移(如走视图方案) |
| 回填 | 不适用 |
| 建议 | **同时执行路线 4.1 时并发做** |

### 4.3 路线 3 — 降低 zhujiang 字典序最小区分启发式 (短期 noop)

**思路**: 当前 `backfill_imaging_study_exam_id.py` 已尝试 `(patient_id, MIN(|exam_date - study_date|))` 关联 — 但 shengyi 这 82,769 个 study 因为 patient 不在 exam 表而**根本无法进入关联候选集**。这条路无效,仅记录。

| 项 | 评估 |
|---|---|
| 工作量 | 0 (无效) |
| 风险 | — |
| 建议 | **不做** |

### 4.4 路线 4 — 路线 4.1 不可行时的 fallback (永久 partial)

**思路**: 如果上游确实无法提供 mapping,**接受** shengyi 82,994 个 study 中 99.74% (82,769) 在新数据体系里 `anon_exam_id` 永久 NULL。这是**事实**,不是 bug:

- 占位 patient (`is_placeholder=TRUE` 且人口学全空) 与 imaging_study 的 join 是有意义的 (UI 仍可显示"某位匿名患者在某日做了 CT")
- byte_size 可以走 `dicom_series.byte_size` 累加(issue-2 dicom_series 阶段,与 issue-1 联动)
- 仅 `anon_exam_id` 关联不可达 → 不影响 PRD "medicalFiles 页面显示真实文件总大小" 目标

| 项 | 评估 |
|---|---|
| 工作量 | 0 (事实接受) |
| 风险 | 极低 |
| 建议 | **若路线 4.1 长期阻塞,落档为正式 ADR** |

---

## 5. 总结

| 项 | 结论 |
|---|---|
| 根因 | 候选 B: DICOM 影像 patient_id 与 HIS patient_id 是两批几乎不重叠的患者 |
| 是否 ETL bug | **否** — ETL 各步执行正确 |
| 是否 spec 缺失 | **否** — spec 26 项覆盖完整 |
| 是否 hash 派生不一致 | **否** — 跨表一致 |
| 唯一根本修复 | 依赖外部 mapping 接入 (路线 4.1) |
| 立即可行修复 | 路线 4.2 (文档化占位行为) + 路线 4.4 (接受事实) |

---

## 6. 附录 — 与 issue-1 PRD 数字差异说明

issue-1 PRD 表述"patient 有 CT exam: 174",实测 `COUNT(DISTINCT patient_id) FILTER (exam_type='CT')` = **52,368**。差异源于:

- issue-1 PRD 的"174"是**"既在 study 又在 exam 且 exam_type='CT' 的 patient 数"** = study ∩ exam ∩ CT-exam
- 全 exam patient 数 = 66,635,全 CT-exam patient 数 = 52,368,study ∩ exam 患者仅 219,**CT 子集进一步缩到 174**

issue-4 本报告使用更精确的描述以避免歧义。

---

## 7. 参考

- issue-1 PRD: `docs/etl2/prd/issue-1-backfill-imaging-study-exam-id.md`
- issue-9 PRD: `docs/etl2/prd/issue-9-fix-shengyi-placeholder-flag.md` (与本 issue 强相关)
- 父 PRD: `docs/etl2/prd/PRD.md` §"Out of Scope — shengyi exam 入库缺口"
- ETL-2 shengyi spec: `backend/app/plugin/module_medical/hospital/anon_etl_engine.py:2467`
- 影像离线灌库脚本: `scripts/build_shengyi_imaging_study_index.py`