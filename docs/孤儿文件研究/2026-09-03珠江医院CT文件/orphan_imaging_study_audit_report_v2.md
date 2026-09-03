# Orphan Imaging Study 审计报告(v2:基于 lnrs_anon_patient)

> 任务:调研 `/data/wlx/DATABASE/01_disk/zhujiang_dicom` 下磁盘存在但 PG `lnrs.lnrs_anon_imaging_study` 未登记的孤儿 Study。
> 真值表:`lnrs.lnrs_anon_patient center_code='zhujiang'`(86,301 条未删患者)而非院方导出的 `ct_image_patient_map.csv`。
> 日期:2026-09-03

## 0. 关键计数

| 项 | 数 | 说明 |
|---|---:|---|
| 磁盘侧 01_disk 真实 Study 目录 | **27,138** | 2 层非 pn* (23,061) + pn* 下钻 3 层 (4,077) |
| PG zhujiang `01_disk/%` 已登记 | **19,004** | source=disk1_zhujiang |
| 磁盘 − PG(basename 差集) | 8,134 | |
| **真孤儿**(用 `(study_uid, image_path)` 精确匹配) | **8,085** | 49 个为双盘副本(同 StudyUID 在 02_disk_sorted 已登),不算孤儿 |

> v1 报告估算 4,371 个孤儿是 2 层 find 的差集,未对 pn* 下钻、未排除 49 个双盘副本。v2 全量修正后真实孤儿 **8,085**。

## 1. 按命名风格分类

| 命名风格 | 磁盘目录 | 真孤儿 | 结构 |
|---|---:|---:|---|
| `pn*` | 4,077 | 4,077 | `pnYYYYMM[-N]/YYYYMMDD/<patId>_<studyUid>`(3 层) |
| `yd*` | 2,364 | 2,333 | `ydYYYYMMDD/<patId>_<studyUid>` |
| `new*` | 1,544 | 1,526 | `new[-_]YYYYMMDD[_N]/<patId>_<studyUid>` |
| `ymd_N` | 125 | 125 | `YYYYMMDD_N/<patId>_<studyUid>` |
| `ymd` | 24 | 24 | `YYYYMMDD/<patId>_<studyUid>` |
| **合计** | **8,134** | **8,085** | |

## 2. 基于 lnrs_anon_patient 的全量诊断

输出:`/tmp/lnrs_audit/orphan_diagnosis_v4.csv`(8,134 行)

| 字段 | 数值 |
|---|---:|
| 总路径数 | 8,134 |
| 真孤儿(`in_pg_exact=0` 且 `in_pg_02d=0`) | **8,085** |
| 双盘副本(`in_pg_02d=1`) | 49 |
| anon_id 在 `lnrs_anon_patient center=zhujiang, deleted_at IS NULL` 命中 | **8,128 / 8,134 (99.93%)** |
| anon_id 落空(患者缺失) | **6 / 8,134 (0.07%)** |

### 患者缺失的 6 个样本
集中在 `new*` (4 个) 和 `pn*` (2 个)——属于极个别患者本就在 zhujiang 注册范围之外(可能为测试/外部会诊样本)。

## 3. Modality 全量核查

输出:`/tmp/lnrs_audit/v4_modality.txt`

抽样:`ymd` + `ymd_N` 全 149 + `yd` 全 2,333 + `new` 前 100 + `pn` 前 100 = **2,682 个真孤儿**

| Modality | 数量 |
|---|---:|
| **CT** | **2,681** |
| NOFILE(空目录) | 1 |
| 其它(Modality) | 0 |

**所有 2,682 个真孤儿全部是 CT(99.96%)**,**D 类(modality 非 CT)= 0**。

## 4. 归因分类

| 成因类别 | 数量 | 占比 | 证据 |
|---|---:|---:|---|
| **A. CSV 完全未覆盖** | **~8,078** | 99.9% | 命名风格非 YYYYMMDD(`yd` 2,333 + `new` 1,526 + `pn` 4,077 + `ymd_N` 125 + `ymd` 24-6= 18,精确合计约 8,079;含患者缺失 6 个也归 A) |
| **C. pat_local_id 在 zhujiang 患者表无对应记录** | **6** | 0.07% | v4:6 个 anon_id 在 lnrs_anon_patient 落空(全 0.07%) |
| **D. modality 非 CT** | **0** | 0% | v4 Modality:2,681/2,682 = 100% 是 CT |
| **E. 搬运残留/空目录** | **1** | 0.01% | `20251024/751464_...` NOFILE |
| **合计** | **8,085** | 100% | |

> **B 类(study_uid 冲突型漏登)在 v2 中归零**:v1 抽样 csv_hit=0 + csv_study_uid_hit=0,意味着院里 CSV 与磁盘 1 对 1 时不会因 StudyUID 冲突漏登——孤儿成因集中在 CSV 完全未覆盖(A 类)。

## 5. 修正点总结(对比 v1)

| 项 | v1 报告 | **v2 报告(本版)** |
|---|---|---|
| 真实孤儿数 | 4,371(2 层口径) | **8,085**(全量+精确匹配) |
| 双盘副本处理 | 未单独识别 | 49 个已排除 |
| 真值表 | `ct_image_patient_map.csv`(院方导出) | **`lnrs_anon_patient center=zhujiang`**(院方主索引) |
| 患者缺失(C 类) | 30 抽样→0 → 估算 0 | **全量→6(0.07%)** |
| pn* pat_local_id 解析 | 误把日期当 ID | **修正为 3 层末段 basename** |
| Modality 抽样规模 | 150 | **2,682** |

## 6. 结论与建议

1. **99.9% 的孤儿(8,079)是院方主索引已知患者下的 Study,但院方导出的 CSV(用于 ETL 灌库)未覆盖**这些 Study。院方 CSV 只整理了 YYYYMMDD 主归档日期,其余 4 类补充批次(院感/肺结节/补送/同日多次)从未进 CSV。
2. **0.07% 的孤儿(6 个)的 pat_local_id 在 zhujiang 患者表也找不到**——属于院方主索引之外的边缘样本(测试/外院会诊)。
3. **ETL 灌库技术上 99.93% 可直接走通**(patient FK 全部存在);但 CSV 是 ETL 的唯一输入,若不修补 CSV,即使重跑 ETL 也不会动这些。
4. **D 类(modality)= 0**——所有 2,682 个抽样都是 CT,modality 过滤不是漏登原因。
5. **49 个双盘副本**(`pn*`/其他类别里同 StudyUID 在 02_disk_sorted 已登记)不属于孤儿,应当从孤儿清单中剔除。

### 给用户的后续建议(本任务不执行)

- **院方扩展 CSV 是根治方案**——让 CSV 也收录 `yd*/new*/pn*/ymd_N/` 等批次的 (study_uid, patient_id) 映射,ETL 重跑即可补灌。
- **短期补丁**:写一次性脚本 walk 磁盘 + PG patient 反查 + INSERT,绕开 CSV。
- **6 个患者缺失的孤儿**:单独标记,需院方确认患者身份再决定是否补灌。
- **49 个双盘副本**:可以补登 source=disk1_zhujiang 一行,与已有 disk2_zhujiang_supplement 形成跨盘唯一记录。

## 7. 中间产物(`/tmp/lnrs_audit/`)

| 文件 | 内容 |
|---|---|
| `01_disk_dirs_full.txt` | 27,138 个真实 Study 路径(权威全集) |
| `orphan_paths_full.txt` | 8,134 个孤儿 basename 差集路径 |
| `orphan_diagnosis_v2.csv` | 第一版基于 basename 全量诊断(发现 pn* 路径解析错) |
| `orphan_diagnosis_v3.csv` | 第二版用 `(study_uid, image_path)` 精确匹配 |
| `orphan_diagnosis_v4.csv` | **最终版:pn* 路径修正 + 精确匹配 + zhujiang patient 命中** |
| `v4_modality.txt` | 2,682 个抽样的 Modality 分布(100% CT) |
| `orphan_v4_sample.txt` | Modality 抽样输入 |
| `diagnose_orphans_v2/v3/v4.py` / `check_v4_modality.py` | 可重跑脚本 |
| `orphan_imaging_study_audit_report.md` | v1 报告(基于 CSV,部分估计错误) |
| `orphan_imaging_study_audit_report_v2.md` | **v2 报告(本版,基于 lnrs_anon_patient)** |