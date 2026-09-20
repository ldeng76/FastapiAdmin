# zhujiang 零文件 study 调研报告（2026-09-20）

> 关联 PRD/Issue: `docs/etl2/prd/issue-8-resolve-zhujiang-empty-studies.md`
> 关联 plan:     `docs/etl2/plan-disk1-disk2-disk4-zhujiang-import.md` §6 R-空 study / §7-5
> 调研日期:       2026-09-20 09:49:31
> 调研环境:       h196_3 (127.0.0.1:5432)
> 数据源:         `lnrs_anon_imaging_study WHERE center_code='zhujiang' AND sop_count=0`
> 完整 inventory: `docs/etl2/verify_result/zhujiang_empty_studies_20260920.csv`

---

## 1. 415 行 source / 日期目录 / path_study_date 分布

DB inventory 总行数: **415**（truncated=False）

### 1.1 source 分布（零 sop study）

| source | 行数 |
|---|---:|
| `disk1_zhujiang` | 268 |
| `disk2_zhujiang_supplement` | 72 |
| `disk4_zhujiang` | 75 |
| **合计** | **415** |

### 1.2 path_study_date 年份分布

| year | 行数 |
|---|---:|
| 2014 | 1 |
| 2015 | 1 |
| 2016 | 2 |
| 2017 | 6 |
| 2018 | 4 |
| 2019 | 1 |
| 2020 | 4 |
| 2021 | 137 |
| 2022 | 47 |
| 2023 | 70 |
| 2024 | 26 |
| 2025 | 116 |
| **合计** | **415** |

## 2. A / B 子集分类（按 issue 定义）

| 子集 | 定义 | 当前行数 |
|---|---|---:|
| **A** | dicom_series 行缺失 **或** `file_count=0 AND byte_size=0` | **415** |
| **B** | dicom_series 行存在且 `file_count>0 OR byte_size>0`（陈旧计数） | **0** |

> ⚠️ **与 PRD 描述的偏差**：PRD 写 A=274 / B=141。当前 DB 状态为 A=全部 / B=0。
> 经核对，B 子集的 141 行陈旧计数 **当前已不存在** —— 可能由后续全量 ETL / DB 重建移除。
> 因此本报告聚焦 A 子集处置决策；B 子集的「陈旧计数修复」自然满足（已为 0）。

## 3. 磁盘状态复核

### 3.1 A 子集磁盘状态分布

| 状态 | 行数 |
|---|---:|
| `empty_dir` | 415 |
| **合计** | **415** |

## 4. 视图 `lnrs_anon_v_imaging_study_counts` 影响评估

| 指标 | 全量 | zero-sop 子集 |
|---|---:|---:|
| `study_total` (zhujiang) | 86927 | 415 |
| `series_count > 0` 行数 | 0 | — |
| `instance_count > 0` 行数 | 0 | — |
| `total_bytes > 0` 行数 | 0 | — |
| `sum_total_bytes` | 0 | — |
| `sum_zero_sop_bytes` (视图) | — | 0 |
| `sum_instance_count` | 0 | — |
| `sum_zero_sop_instances` (视图) | — | 0 |

### 4.1 视图在 zero-sop 子集上的实际行为

- 当前 zero-sop study 在视图中 `series_count=0 / instance_count=0 / total_bytes=0`
  （dicom_series 行缺失 → LEFT JOIN 兜 0）。
- 因此视图 SUM 不被 zero-sop 子集污染：`sum_zero_sop_bytes = 0`。
- 但 **study 行数仍计入分母**：`study_total` 含 415 个 zero-sop 行，
  这对 `total_size_bytes` 总量虽无影响（分子 = 0），但 `study_total` / 平均值 / 统计报表有微妙影响。

## 5. A 子集处置方案对比

PRD 列出 3 套方案。本节评估每套方案对视图与下游 API 的影响。

### 方案 (a)：保留 + 视图/接口标注 `is_empty`

- **改动**：视图 `lnrs_anon_v_imaging_study_counts` 加列 `is_empty BOOL`；API 透出该字段。
- **统计接口影响**：`medicalFiles.total_size_bytes` 保持不变（zero-sop 已 SUM 0，分子无影响）。
- **页面影响**：列表页可显示「空 study」徽标；不影响主统计数字。
- **回退成本**：视图重建；API 字段加/去；前端字段加/去。
- **优点**：保守；不丢数据；业务侧可见。
- **缺点**：视图 schema 变动；前端需适配。

### 方案 (b)：软删（`deleted_at` 类字段）

- **改动**：给 `lnrs_anon_imaging_study` 加 `deleted_at TIMESTAMP NULL`；UPDATE zero-sop 子集；视图加 `WHERE deleted_at IS NULL` 守卫（与 `lnrs_anon_patient.deleted_at` 口径一致）。
- **统计接口影响**：`total_size_bytes` 不变（zero-sop 本就 SUM 0），但 `study_total` 减少 415 行。
- **页面影响**：列表行数减少 415；medicalFiles 顶部「记录」统计 -415。
- **回退成本**：`deleted_at` 清空即可；视图 WHERE 子句拆除。
- **优点**：与 patient 表口径一致；语义清晰（数据已不可用）。
- **缺点**：schema 变动（DDL）；违反「保留空 study」既有口径（PRD Notes §1）。

### 方案 (c)：视图层过滤（不写库）

- **改动**：视图 `lnrs_anon_v_imaging_study_counts` 加守卫 `s.sop_count > 0 OR EXISTS (SELECT 1 FROM lnrs_anon_dicom_series ds WHERE ds.dicom_study_uid = s.dicom_study_uid AND ds.file_count > 0)`；API 不变。
- **统计接口影响**：`total_size_bytes` 不变；`study_total` 减少 415 行（视图层面）。
- **页面影响**：列表行数减少 415（视图层）；medicalFiles 顶部「记录」统计 -415。
- **回退成本**：视图 WHERE 子句拆除。
- **优点**：零 schema 变动；零数据修改；纯逻辑过滤。
- **缺点**：与既有口径偏离；下游若直接查 `imaging_study` 仍能看到 zero-sop 行。

## 6. 旁路观察：shengyi 的同名异常（out-of-scope）

调研中顺手发现：`shengyi` 中心有 **82,994** 个 `sop_count=0` 的 study，
**全部** 无对应 `dicom_series` 行（按 `dicom_study_uid` LEFT JOIN 全部 NULL）。

抽样 5 个 study 路径，**磁盘目录实际文件数**：

| image_path | 目录内文件数 |
|---|---:|
| `/data/wlx/DATABASE/06_disk/DCM_part01.zip_folder/01010_P980295/1.3.46.670589.50.2.12512907832493497412.21716784194060679662/1.3.46.670589.50.2.1522009751889913676.24887599591830659057` | 330 |
| `/data/wlx/DATABASE/06_disk/DCM_part01.zip_folder/02379-3/1.3.6.1.4.1.19899.2.220527.303430.023793/1.2.156.112605.159303470218600.220527003826.3.31696.141142` | 660 |
| `/data/wlx/DATABASE/06_disk/DCM_part01.zip_folder/03373-3/1.3.12.2.1107.5.1.4.48611.30000020091423035571800000020/1.3.12.2.1107.5.1.4.48611.30000020091500262687500016381` | 343 |
| `/data/wlx/DATABASE/06_disk/DCM_part01.zip_folder/03772-3/1.3.6.1.4.1.19899.2.241101.324221.037723/1.2.156.112605.159303470218600.241101014849.3.10224.77806` | 653 |
| `/data/wlx/DATABASE/06_disk/DCM_part01.zip_folder/05304-14/1.3.6.1.4.1.19899.2.260416.164021.0530414/1.2.156.112605.159303470218600.260416003002.3.9512.131562` | 653 |

**与 zhujiang 的零文件 study 性质不同**：

- zhujiang：磁盘无数据 + `sop_count=0` → **一致**（真空 study）。
- shengyi：磁盘有数据（DICOM 文件齐全）+ `sop_count=0` → **不一致**（计数漂移）。

shengyi 异常根因在 `sop_count` 离线统计口径，与本 issue 的零文件 study 处置决策正交，
**不在本 issue 范围**。建议作为独立 issue 处理。

## 7. 建议

倾向 **(c) 视图层过滤**（最小侵入，不写库、不改 schema），若需要列表页可见 zero-sop 行则改 **(a)**。
不推荐 **(b)** —— 与既有「保留空 study」口径冲突，且需 DDL。

---

## 附：执行命令

```bash
# 本报告生成
cd /home/dzy/wk/lnrs/backend
ENVIRONMENT=h196_3 uv run python etl2/investigate_zhujiang_empty_studies.py \
    --out-csv /home/dzy/wk/lnrs/docs/etl2/verify_result/zhujiang_empty_studies_20260920.csv
```
