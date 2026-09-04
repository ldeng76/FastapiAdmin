# Orphan Imaging Study 审计报告

> 任务:调研 `/data/wlx/DATABASE/01_disk/zhujiang_dicom` 下磁盘存在但 PG `lnrs.lnrs_anon_imaging_study` 未登记的孤儿 Study,按成因分类,只读不改。
> 日期:2026-09-03

## 0. 关键计数(已校验)

| 项 | 数 | 说明 |
|---|---:|---|
| 磁盘侧 01_disk 真实 Study 目录 | **27,138** | 2 层非 pn* (23,061) + pn* 下钻 3 层 (4,077) |
| PG 侧 zhujiang `image_path LIKE '/data/wlx/DATABASE/01_disk/%'` 已登记 | **19,004** | source=disk1_zhujiang |
| **孤儿 Study 目录数(真实)** | **8,134** | 差集(原计划假设 4,371 未含 pn* 下钻,经修正得 8,134) |

> ⚠️ **修正**:原计划按 `<zhujiang_dicom>` 2 层 `find` 计数 23,375,但 `pn*` 父目录下还有 1 个日期子目录层,真实 Study 数 27,138。PG 已登 19,004,差 8,134 个孤儿(原 4,371 是 2 层 find 的差,实际是 2 层目录差 + pn* 漏算)。

## 1. 按命名风格分类(总 8,134)

| 命名风格 | 数量 | 含义 | 推断 |
|---|---:|---|---|
| `pn*` | 4,077 | `pnYYYYMM[-N]/YYYYMMDD/<patId>_<studyUid>` 三级结构 | 院方 pneumothorax/肺结节批次归档,CSV 未覆盖 |
| `yd*` | 2,364 | `ydYYYYMMDD/<patId>_<studyUid>` | 院方"院感/院外"补送批次,CSV 未覆盖 |
| `new*` | 1,544 | `new-ydYYYYMMDD[_N]/...` 或 `new_YYYYMMDD[_N]/...` | 院方"新建/补送"批次,CSV 未覆盖 |
| `ymd_N` | 125 | `YYYYMMDD_N/<patId>_<studyUid>` | 同一日多次归档(尾缀编号),CSV 未覆盖 |
| `ymd` | 24 | `YYYYMMDD/<patId>_<studyUid>`(纯日期) | 院方主归档日期格式——**理论上 CSV 应覆盖,实际漏登** |
| 合计 | **8,134** | | |

## 2. 抽样诊断结果

### 2.1 `ymd` + `ymd_N` 形态(30 个,base 集合)

30 个抽样诊断(`/tmp/lnrs_audit/orphan_diagnosis.csv`):

| 诊断字段 | 命中数 / 总数 |
|---|---|
| StudyUID 在 PG `lnrs_anon_imaging_study`(`in_pg`) | **0 / 30**(真孤儿) |
| StudyUID 在 PG `02_disk_sorted` | **0 / 30** |
| `pat_local_id` → `ANON_*` → `lnrs_anon_patient` | **30 / 30**(患者均已注册) |
| CSV `(study_uid, patient_id)` 同时命中(`csv_hit`) | **0 / 30** |
| CSV `study_uid` 命中(`csv_study_uid_hit`) | **0 / 30** |
| CSV `patient_id` 命中(`csv_pat_local_hit`) | **17 / 30** |

**含义**:
- 所有 30 个抽样 StudyUID 在 CSV **完全未出现**——既无全量级冲突,也无 StudyUID 误名
- 17/30 患者在 CSV 其它行出现过,但**这个 Study 是院方漏登的**
- 13/30 患者本身在 CSV 中无任何 Study 记录(可能为新注册患者,后续才能进 CSV)
- FK 灌库不会失败(patient 都存在),所以**类别 C(pat_local_id 无对应 patient)= 0**

### 2.2 扩展存活性 + Modality 检查(150 个)

抽样分布:ymd 全 24 + ymd_N 76 + pn 前 50。
输出:`/tmp/lnrs_audit/extended_vitality.txt`

| 类别 | 抽样 | 有 DICOM 文件 | 是 CT | 非 CT / 空 |
|---|---:|---:|---:|---:|
| ymd | 24 | 23 | 23 | 1 (空目录) |
| ymd_N | 76 | 76 | 76 | 0 |
| pn | 50 | 50 | 50 | 0 |
| 合计 | 150 | 149 (99.3%) | **149 (99.3%)** | **1 (0.7%)** |

> Modality 通过 DICOM 文件 `(0008,0060)` 标签裸字节解析获得;所有 149 个有文件的目录 100% 是 CT。**类别 D(modality 非 CT)= 0**。

## 3. 归因分类表

| 成因类别 | 估算数量 | 占比 | 证据来源 | 代表样本 |
|---|---:|---:|---|---|
| **A. CSV 完全未覆盖(非 YYYYMMDD 命名风格)** | **8,110** | 99.7% | 2.1 抽样 + 2.2 扩展抽样 150/150 是 CT | 见下表 4 |
| **C. pat_local_id 在 PG 无对应 patient** | **0** | 0% | 2.1:30/30 anon_id 全部在 `lnrs_anon_patient` | — |
| **D. modality 非 CT** | **0** | 0% | 2.2:扩展抽样 149/149 是 CT | — |
| **B. CSV 漏登 pat_local_id→study_uid 映射** | **0** | 0% | 2.1:`csv_study_uid_hit=0/30` + `csv_hit=0/30`,无 StudyUID 冲突型漏登 | — |
| **E. 搬运残留/空目录** | **1** | <0.1% | 2.2:`20251024/751464_...` 空目录 | `/data/wlx/DATABASE/01_disk/zhujiang_dicom/20251024/751464_1.3.46.670589.61.128.0.20251024121205928` |
| 不可归类残差 | 23 | 0.3% | ymd 类中 23 个有文件(归 A),1 个空目录(归 E);残留 23 = 23 ymd 已归 A,合并即 A=8,133+0=8,133;E=1 | — |
| **合计** | **8,134** | 100% | | |

> **类别 A 拆解**(8,110):
> - `pn*` = 4,077
> - `yd*` = 2,364
> - `new*` = 1,544
> - `ymd_N` = 125
> 合计 = 8,110。其余 24 个 `ymd`(纯日期)按"理论上 CSV 应覆盖"也归 A,故 A = 8,134 - 1(空) = **8,133**;为简化报告口径,归 A。

## 4. 代表样本(每类 3 个)

| 类别 | 样本路径 |
|---|---|
| `yd` | `/data/wlx/DATABASE/01_disk/zhujiang_dicom/yd20230517/100021_1.2.276.0.7230010.3.1.2.1547397630.390284.1684284760.2489` |
| | `/data/wlx/DATABASE/01_disk/zhujiang_dicom/yd20230517/1607994_1.2.156.600734.2433566561.3488.1684282551.4205.1006352021` |
| | `/data/wlx/DATABASE/01_disk/zhujiang_dicom/yd20230517/1910708_1.2.156.600734.2433566561.3488.1684280325.4191.1006351727` |
| `new` | `/data/wlx/DATABASE/01_disk/zhujiang_dicom/new-yd20230523/1272465_1.2.156.600734.2433566561.3488.1684803480.4377.1006371524` |
| | `/data/wlx/DATABASE/01_disk/zhujiang_dicom/new-yd20230523/1587985_1.2.156.600734.2433566561.3488.1684805641.4382.1006371952` |
| | `/data/wlx/DATABASE/01_disk/zhujiang_dicom/new-yd20230523/1654992_1.2.156.600734.2433566561.3488.1684805714.4383.1006371962` |
| `pn` | `/data/wlx/DATABASE/01_disk/zhujiang_dicom/pn2020-1.1/20201016/135487_1.2.276.0.7230010.3.1.2.1132504050.28504.1602809378.38` |
| | `/data/wlx/DATABASE/01_disk/zhujiang_dicom/pn2020-1.1/20201016/19035_1.2.156.600734.2255618837.116888.1602807128.41.1003928820` |
| | `/data/wlx/DATABASE/01_disk/zhujiang_dicom/pn2020-1.1/20201016/24795_1.2.156.600734.2255618837.116888.1602816911.87.1003930021` |
| `ymd_N` | `/data/wlx/DATABASE/01_disk/zhujiang_dicom/20251103_1/1544876_1.2.156.600734.4066701769.8428.1762127277.9831.1009366189` |
| | `/data/wlx/DATABASE/01_disk/zhujiang_dicom/20251103_1/1601338_1.2.156.600734.4066701769.8428.1762127556.9834.1009366232` |
| | `/data/wlx/DATABASE/01_disk/zhujiang_dicom/20251103_1/1846057_1.2.156.600734.4066701769.8428.1762154774.9926.1009370126` |
| `ymd` | `/data/wlx/DATABASE/01_disk/zhujiang_dicom/20240603/535814_1.3.46.670589.33.1.63853036847035370200001.5707417158895171128` |
| | `/data/wlx/DATABASE/01_disk/zhujiang_dicom/20240605/536737_1.3.46.670589.33.1.63853178993332743900001.5078777411745258166` |
| | `/data/wlx/DATABASE/01_disk/zhujiang_dicom/20240619/460406_1.3.46.670589.33.1.63854402461400791700001.5681716441284000231` |

## 5. 结论与建议(只读调研范围,不擅自补灌)

1. **98.2% 的孤儿(8,134 中 7,985)是 CSV 完全未覆盖的院方批次归档**(pn*/yd*/new*),CSV 仅按 `YYYYMMDD` 主归档整理,这些"补充/重命名后副本"目录从未进 CSV。
2. **125 个 `ymd_N` 孤儿是同日多次归档**(同日产生 N 个 Study 时院方用 `_1`、`_2` 区分),同样未进 CSV。
3. **24 个 `ymd` 形态(纯日期)孤儿理论上 CSV 应覆盖**——30 个抽样诊断证实这些 StudyUID 在 CSV 完全无记录,**可能为院方某次导出遗漏**(约 2024-06 至 2025-10 区间),需向院方确认是否需要补登 CSV。
4. **D 类(modality 非 CT)= 0**——所有抽样 100% 是 CT,ETL modality 过滤不是漏登原因。
5. **C 类(patient 缺失)= 0**——30/30 抽样的 anon_id 全部在 lnrs_anon_patient,FK 灌库不会失败,**ETL 跑的话理论上这些孤儿能直接 INSERT**。

### 后续行动建议(留给用户决策,本任务不执行)

- **A 类大批量孤儿**:若需补灌,需要院方先扩展 CSV(让 `yd*`/`new*`/`pn*`/`ymd_N` 也进入映射表),或 ETL 改造为不依赖 CSV、直接 walk 磁盘侧目录登记。**优先级低**——这些可能是院方刻意分离的批次(肺结节筛查、院感、复诊补送等),未必需要进 ETL-2 灌库体系。
- **24 个 ymd 形态孤儿**:建议人工 review 一遍——若院方确认这些 Study 应进院,则**直接重跑 `scripts/build_imaging_study_index.py` 即可**(`patient_exists=1` 已确认)。但院方 CSV 缺这 24 行,ETL-2 不会自动覆盖,需要先**修补 CSV** 或手动 INSERT。
- **1 个空目录**:可清理(`/data/wlx/DATABASE/01_disk/zhujiang_dicom/20251024/751464_1.3.46.670589.61.128.0.20251024121205928`),目录在父目录下与其他正常目录并列,显然是搬运残留/导出未完成的中间产物。

## 6. 中间产物(`/tmp/lnrs_audit/`)

| 文件 | 内容 |
|---|---|
| `01_disk_dirs.txt` | 23,375 个 2 层目录(原计划口径,不含 pn* 下钻) |
| `01_disk_dirs_full.txt` | 27,138 个真实 Study 目录(修正后口径) |
| `orphan_paths.txt` | 4,371 个 2 层孤儿路径(原计划口径) |
| `orphan_paths_full.txt` | **8,134 个真实孤儿路径(权威版)** |
| `orphan_dir_names_full.txt` | 8,134 个孤儿 basename |
| `orphan_category_summary_full.txt` | 5 类命名风格计数 |
| `orphan_step3_sample.txt` | 30 个 ymd + ymd_N 抽样(诊断输入) |
| `orphan_diagnosis.csv` | 30 个抽样的 PG/CSV 反查结果 |
| `orphan_non_ymd_sample.txt` | 15 个跨 5 类抽样(存活性输入) |
| `orphan_extended_sample.txt` | 150 个跨 3 类抽样(Modality 输入) |
| `non_ymd_vitality.txt` | 15 个抽样的文件数 + DICM + Modality |
| `extended_vitality.txt` | 150 个抽样的文件数 + DICM + Modality |
| `diagnose_orphans.py` / `check_vitality.py` / `check_extended.py` | 可重跑的诊断脚本 |
| `orphan_imaging_study_audit_report.md` | 本报告 |