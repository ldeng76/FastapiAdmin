# 珠江医院 CT 孤儿影像研究审计产物

> 任务:只读调研 `/data/wlx/DATABASE/01_disk/zhujiang_dicom` 下磁盘存在但 PG `lnrs_anon_imaging_study` 未登记的孤儿 Study。
> 真值表:`lnrs_anon_patient center_code='zhujiang'`(86301 条未删患者)。
> 日期:2026-09-03
> **未修改 PG、未修改磁盘、未修改任何源码**。

## 一、报告(从这开始看)

| 文件 | 说明 |
|---|---|
| `orphan_imaging_study_audit_report_v2.md` | **最终报告**(基于 lnrs_anon_patient,推荐) |
| `orphan_imaging_study_audit_report.md` | v1 报告(基于 CSV,部分估计被 v2 修正) |

## 二、核心结论速览

- **磁盘侧 01_disk 真实 Study 目录:27,138**(2 层 23,061 + pn* 3 层 4,077)
- **PG zhujiang 已登记:19,004**
- **真孤儿:8,085 个**(8,134 个 basename 差集 − 49 个双盘副本)
- **99.93% 患者的 anon_id 在 zhujiang 患者表命中**(C 类仅 6 个 = 0.07%)
- **100% 抽样都是 CT**(D 类 = 0)
- **唯一主因:院方导出的 `ct_image_patient_map.csv` 仅覆盖 YYYYMMDD 主归档日期,4 类补充批次(院感 `yd*` / 肺结节 `pn*` / 补送 `new*` / 同日多份 `ymd_N`)从未进 CSV**。

## 三、文件分组

### 1. 全量基础集合(步骤 1 产物)

| 文件 | 行数 | 含义 |
|---|---:|---|
| `01_disk_dirs.txt` | 23,375 | 2 层 find 末级目录(原计划口径,**不含 pn* 下钻**) |
| `01_disk_dirs_full.txt` | 27,138 | 真实 Study 目录(2 层非 pn* + pn* 3 层) |
| `01_disk_dirs_full_raw.txt` | 27,138 | 同上,带尾斜杠的原始输出 |
| `01_disk_dir_names.txt` | 23,375 | `01_disk_dirs.txt` 的 basename |
| `01_disk_dir_names_full.txt` | 27,138 | 全量 Study 的 basename |
| `01_disk_pg_dirs.txt` | 19,004 | PG 中 zhujiang 01_disk 已登记的 basename |
| `01_disk_pg_dirs_sorted.txt` | 19,004 | 同上,排序后 |
| `pn_studies.txt` | 4,077 | pn* 3 级下钻的真实 Study 路径 |

### 2. 孤儿清单(步骤 1 差集)

| 文件 | 行数 | 含义 |
|---|---:|---|
| `orphan_dir_names.txt` | 4,371 | 2 层 find 差集(v1 口径,少算 pn*) |
| `orphan_dir_names_full.txt` | 8,134 | 全量差集(权威版) |
| `orphan_paths.txt` | 4,371 | 同上,完整路径 |
| `orphan_paths_full.txt` | 8,134 | **权威孤儿路径清单**(后续补灌可直接消费) |

### 3. 命名风格分类(步骤 2 产物)

| 文件 | 行数 | 含义 |
|---|---:|---|
| `orphan_by_date_prefix.txt` | 104 | 每个日期前缀下的孤儿数 |
| `orphan_category_summary.txt` | — | v1 口径5 类归并 |
| `orphan_category_summary_full.txt` | 5 | **权威5 类归并**:pn 4077 + yd 2364 + new 1544 + ymd_N 125 + ymd 24 |

### 4. 诊断 CSV(步骤 3 + 步骤 4 全量)

| 文件 | 行数 | 含义 |
|---|---:|---|
| `orphan_diagnosis.csv` | 30 | v1 抽样诊断(基于 CSV) |
| `orphan_diagnosis_v2.csv` | 8,134 | v2 全量诊断(basename 比对,**发现 pn* 解析错**) |
| `orphan_diagnosis_v3.csv` | 8,134 | v3 全量诊断(精确路径匹配) |
| **`orphan_diagnosis_v4.csv`** | **8,134** | **最终全量诊断**:pn* 路径修正 + 精确匹配 + zhujiang patient 命中 |

### 5. Modality / 存活性(步骤 4 产物)

| 文件 | 行数 | 含义 |
|---|---:|---|
| `non_ymd_vitality.txt` | 15 | v1 15 个抽样的文件数+DICM+Modality |
| `extended_vitality.txt` | 150 | v1 150 个抽样的扩展检查 |
| **`v4_modality.txt`** | **2,682** | **最终全量 Modality 分布**:2,681 CT + 1 NOFILE |
| `orphan_v4_sample.txt` | 2,682 | Modality 抽样的输入路径 |

### 6. 抽样输入

| 文件 | 行数 | 含义 |
|---|---:|---|
| `orphan_step3_sample.txt` | 30 | v1 步骤 3 抽样(ymd+ymd_N) |
| `orphan_ymd_only.txt` | 24 | 纯 ymd 形态 |
| `orphan_ymd_N_sample.txt` | 6 | ymd_N 每组前 3 |
| `orphan_non_ymd_sample.txt` | 15 | v1 步骤 4 5 类各前 3 |
| `orphan_extended_sample.txt` | 150 | v1 步骤 4 扩展(ymd 24 + ymd_N 76 + pn 50) |

### 7. 可重跑脚本

| 文件 | 说明 |
|---|---|
| `diagnose_orphans.py` | v1 步骤 3 抽样诊断(基于 CSV) |
| `diagnose_orphans_v2.py` | v2 全量诊断(basename) |
| `diagnose_orphans_v3.py` | v3 全量诊断(精确路径) |
| **`diagnose_orphans_v4.py`** | **最终全量诊断脚本**(推荐) |
| `check_vitality.py` | v1 步骤 4 存活性检查(15 个) |
| `check_vitality2.py` | 同上的 exec hack 版(可忽略) |
| `check_extended.py` | v1 步骤 4 扩展检查(150 个) |
| **`check_v4_modality.py`** | **最终 Modality 检查脚本**(2,682 个) |

## 四、复用建议

若后续做"自动补灌孤儿 Study"脚本:

```python
# 消费 orphan_diagnosis_v4.csv:
#   - in_pg_exact=0 且 in_pg_02d=0 → 真孤儿,INSERT 到 PG
#   - in_pg_02d=1 → 双盘副本,跳过(或补 source=disk1_zhujiang 一行)
#   - patient_in_zhujiang=0 → 跳过(6 个,需院方确认)
#   - anon_id 字段已算好,直接用作 FK

import csv
real_orphans = [r for r in csv.DictReader(open('orphan_diagnosis_v4.csv'))
                if r['in_pg_exact']=='0' and r['in_pg_02d']=='0'
                and r['patient_in_zhujiang']=='1']
print(f"可补灌: {len(real_orphans)} 行")
```

## 五、原始位置

所有中间文件原始位于 `/tmp/lnrs_audit/`,本目录为归档副本。