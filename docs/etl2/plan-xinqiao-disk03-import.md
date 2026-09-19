# 新桥 CT 影像（03_disk/xinqiao）→ h196_3 PG 导入计划

> 状态：**评审修订版（v2）**。v1 的目录模型经实测推翻，见 §2。
> 关联：[plan-disk1-disk2-disk4-zhujiang-import.md](plan-disk1-disk2-disk4-zhujiang-import.md)（珠江模板）、[PRD.md](prd/PRD.md)。

---

## 0. 摘要

### 0.1 关键结论：新桥与珠江的目录语义**不同**

| | 珠江 | 新桥 |
|---|---|---|
| study 目录 | `<PID>_<StudyUID>/`，**目录名 UID == DICOM StudyInstanceUID** | **不存在 study 目录** |
| 目录名 UID 的含义 | StudyInstanceUID | **SeriesInstanceUID**（实测） |
| 目录内内容 | 扁平 DICOM 文件（325 个，无扩展名） | 扁平 `.dcm` 文件（该 series 的图像） |
| 一个 study 的落点 | 单个目录 | 同层多个兄弟目录（每个 series 一个） |

**实测证据**（2026-09-20）：

```
4_tjj/img_00720185_1.2.840.113619.2.359.3.279764300.4.1712546480.961
   → DICOM StudyInstanceUID  = 1.2.840.113619.186.21217482123183196.20240410093458586.740
   → DICOM SeriesInstanceUID = 1.2.840.113619.2.359.3.279764300.4.1712546480.961   ← 等于目录名
4_tjj/img_00720185_1.2.840.113619.2.359.3.279764300.4.1712546480.961.3
   → DICOM StudyInstanceUID  = 1.2.840.113619.186.21217482123183196.20240410093458586.740   ← 同一个 study
   → DICOM SeriesInstanceUID = 1.2.840.113619.2.359.3.279764300.4.1712546480.961.3
```

对照珠江（已验证为 study 级）：

```
01_disk/zhujiang_dicom/20170101/270561_1.2.840.113704.1.111.10996.1483237195.1/
   → 目录名 UID == DICOM StudyInstanceUID  ✓   内含 325 个扁平 DICOM 文件
```

**推论**：v1 把 `img_<PID>_<UID>` 当 study 目录 → 写入的 `dicom_study_uid` 会是 **SeriesInstanceUID**，
且 study 会被拆成多行（每个 series 一行）。v1 的「1,735 study」（4_tjj）实为 **series 目录数**；
按 study 聚合后只有 **412 个 study**。

### 0.2 新桥存在 4 种布局（v1 只描述了 1 种）

| # | 布局 | 出现位置 | PID 来源 | StudyUID 来源 | 是否有 study 根 |
|---|---|---|---|---|---|
| A | `img_<PID>_<SeriesUID>/*.dcm` | 4_tjj 全部；5_yxl 4/9 批次；6_zjj 全部；7_hsy `part1/7`；8_hy 2/4 批次 | 目录名 | DICOM header | 否 |
| B | `img_<PID>_<16hex>/*.dcm` | 5_yxl（1,175 个） | 目录名 | DICOM header | 否 |
| C | `<MD5>/<StudyUID>/<SeriesUID>/*.dcm` | 5_yxl 5/9 批次；8_hy 2/4 批次；7_hsy `part1/{1..6,8}` + `part2` 全部 | DICOM header | 目录名（=header，已验证） | **是**（第 2 层） |
| D | `img_<PID>_<SeriesUID>.<n>/*.dcm` | 与 A 同层的兄弟目录，同属 A 的 study | 目录名 | DICOM header | 否 |

布局 C 的 MD5 目录**恰好 1 个子项**（实测 5_yxl 7,154 / 8_hy 3,977 / 7_hsy 8,601，非单子项 = 0），
故 **MD5 目录数 == study 数**。

布局 A/B 的 DICOM `PatientID` 与目录名 PID 一致；布局 C 的目录名无 PID，但 DICOM header
**有** PatientID（实测 `12001180` / `11641242` / `06281482` / `07425066`）。
**注意前导零**：`06281482` 必须按字符串处理，转 int 会与目录名派生的 PID 失配。

### 0.3 实测规模（2026-09-20）

候选目录（= 布局 A/B/D 的 series 叶目录 + 布局 C 的 study 根）合计 **80,358**，
按 `(patient_id, StudyInstanceUID)` 聚合后的 study 数见下表（**已灌库**）：

| sub | 候选目录 | img_ 布局 | MD5 布局(C) | **study** | PID | 文件数 | 容量 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `4_tjj` | 1,770 | 1,770 | 0 | **412** | 411 | 232,892 | 0.05 TiB |
| `5_yxl` | 13,636 | 6,482 | 7,154 | **8,291** | 8,291 | 4,792,522 | 1.02 TiB |
| `6_zjj` | 39,022 | 39,022 | 0 | **9,108** | 9,107 | | |
| `7_hsy` | 9,199 | 598 | 8,601 | **8,600** | 8,600 | | |
| `8_hy` | 16,717 | 12,744 | 3,977 | **6,903** | 6,902 | | |
| **合计** | **80,358** | 60,612 | 19,732 | **33,314** | **33,313** | 18,664,932 | 3.96 TiB |

**候选目录数 ≠ study 数**：`4_tjj` 1,770 → 412（4.3 个 series / study）；
`5_yxl` 13,636 → 8,291（1.6 个 / study）；`6_zjj` 39,022 → 9,108（4.3 个 / study）。
v1 声称的「67,429 study / 59,445 去重 UID」实为 **series 目录数**，**不成立**（差 2 倍）。

> 注：上表 `8_hy` 的 12,744 个 img_ 目录中，6,903 个 study 里有 3,977 个走布局 C，
> 故 img_ + MD5 的目录数与 study 数不是简单相加关系（同 study 的多个 series 会聚合）。

### 0.4 `3_cxf_archives` 本批**排除**

| 检查 | 结果 |
|---|---|
| 层级语义 | 第 1 层 = **StudyInstanceUID**，第 2 层 = **SeriesInstanceUID**（实测 6 个样本，DICOM header 完全吻合） |
| DICOM `PatientID` | **空** |
| DICOM `PatientName` / `BirthDate` / `Sex` / `Age` / `InstitutionName` / `ReferringPhysicianName` / `StudyDescription` | **全空**（整批去身份导出） |
| 与布局 A/B/D 的 StudyUID 交集 | **0**（7,984 vs 60,620） |
| 与布局 C 的 StudyUID 交集 | **0**（7,984 vs 19,731） |
| 与 PG `imaging_study` / `dicom_series` 交集 | **0 / 0** |

**结论**：`3_cxf_archives` 的 7,984 个 study（1,016 GB / 4.5M 文件）**没有任何患者身份线索**，
无法构造 `patient_id`（`lnrs_anon_imaging_study.patient_id` 是 NOT NULL + FK 到 `lnrs_anon_patient`）。
v1 的「从 DICOM header 反查 PatientID」路径**不可实现**。

本批排除，转入独立工单（§7-1），需新桥 PACS/HIS 提供 `StudyInstanceUID → PatientID` 映射后才能入库。
唯一替代方案是伪造 7,984 个无身份 patient，会把不可对账的假患者写进主表，**不采用**。

> 附：`3_cxf_archives/lists/batch_001..008.txt` 共 **7,984 行**，内容就是第 1 层的 StudyUID 列表
> （与 walk 结果完全一致）→ 一旦拿到外部映射，无需遍历 1,016 GB 即可枚举 study。

### 0.5 其他关键事实

| 项 | 结果 |
|---|---|
| `center_code='xinqiao'` 满足 CHECK `^[a-z][a-z0-9_]*$` | ✓ 实测 TRUE |
| `--center xinqiao` 已是 `backfill_dicom_series_count.py` 的合法取值 | ✓（脚本 `choices=["zhujiang","shengyi","xinqiao","hos301"]`） |
| `PatientName` (0010,0010) | 全部为空字符串（所有布局）→ PHI 风险低于珠江 |
| 同人不同 PID 风险 | **0**：33,313 个 PID 与 study 基本 1:1（仅 1 个 PID 有 2 个 study）；无 UID 对应多个 PID |
| 跨布局 UID 重叠 | **0**（img_ 布局 60,612 ∩ MD5 布局 19,732 = 0） |
| PID 形态 | **不止纯数字**：60,612 个目录名为纯数字；另有 **8 个字母前缀**（`img_T04774748_…`）与 **6 个带尾点**（`img_03009286._…`）→ v1「PID 全 8 位数字，无字母前缀」的说法**错误**。DICOM header 的 `PatientID` 是权威值（`03009286.` 连尾点都一致），目录名仅作兜底 |
| 布局 C 的 `PatientID` 前导零 | `05891119` / `06281482` 等；**必须按字符串**处理 |
| `4_tjj/list.csv` | 仅表头一行，无数据（v1 R5 正确） |
| `*.zip_folder` | 是**真实目录**（非压缩包） |

### 0.6 关键决策

1. **中心码** `xinqiao`；**source 标签** `xinqiao_<sub>`（`xinqiao_4_tjj` / `xinqiao_5_yxl` /
   `xinqiao_6_zjj` / `xinqiao_7_hsy` / `xinqiao_8_hy`）。
   *不使用 v1 的 `diskN_xinqiao_*`*：那是自造编号，与实际物理盘/目录无对应（`disk9_..._cxf_archives`
   ↔ 目录 `3_cxf_archives` 已经错位），且 `disk*` 前缀在珠江计划里表示真实物理盘。
2. **study 聚合口径**：`(patient_id, StudyInstanceUID)` 为一行，`dicom_study_uid` 存**真实
   StudyInstanceUID**（从 DICOM header 读）。
3. **`image_path`**：布局 C 用 study 根目录（第 2 层）；布局 A/B/D 无 study 根，取该 study
   字典序最小的 series 目录（CSV `study_root_kind` 列标记来源）。
4. **`dicom_series` 在灌库阶段一并写入**，**不跑 `backfill_dicom_series_count.py`**：
   - 其 bypass 路径用非递归 `path.iterdir()`（`backfill_dicom_series_count.py:324`），
     对新桥这种「目录下是 series 子目录」的结构会算出 `file_count=0 / byte_size=0`；
   - 扫描阶段已算出准确的 `file_count` / `byte_size` / `series_count`；
   - 省掉珠江实测 **3.5 小时** 的 NFS 回填。
5. **exam 关联**：B 方案，`anon_exam_id=NULL`（本批 exam 表无 xinqiao 行）。
6. **`is_placeholder=TRUE`**（与 zhujiang 一致；shengyi 为 FALSE）。
7. **PHI**：CSV `docs/sour/ct_image_patient_map_xinqiao.csv` 含明文院内 PID，走 `.gitignore` + `git rm --cached`。

### 0.7 环境

- 本机即 `h196_3`（10.12.196.3），**不要 ssh**。
- 数据根：`/data/wlx/DATABASE/03_disk/xinqiao/`
- Python：`cd /home/dzy/wk/lnrs/backend && uv run python <script>`
- PG：`PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres`

---

## 1. 磁盘结构（实测）

```
/data/wlx/DATABASE/03_disk/xinqiao/
├── 3_cxf_archives/          1,016 GB；folders/001-008/<StudyUID>/<SeriesUID>/*.dcm   ← 本批排除（§0.4）
├── 4_tjj/                   布局 A 平铺：img_<PID>_<SeriesUID>/*.dcm
├── 5_yxl/                   9 个 *.zip_folder：4 个布局 A + 5 个布局 C
├── 6_zjj/                   10 个 *.zip_folder：全部布局 A
├── 7_hsy/                   part1/{1..8}/<MD5>/<StudyUID>/...（其中 7 为布局 A）
│                            part2/<range>.zip_folder/<MD5>/<StudyUID>/...
├── 8_hy/                    4 个 *.zip_folder：2 个布局 A + 2 个布局 C
└── auto.sh / list.csv 等    非数据文件
```

各 sub 根目录均有 `auto.sh`（导出脚本残留）；`3_cxf_archives` 另有 `run_*.ps1` / `logs/` / `state.json`。

---

## 2. v1 评审发现（P0 / P1 / P2）

### P0 —— 阻断执行或产出错误数据

| # | 问题 | 证据 | 处置 |
|---|---|---|---|
| P0-1 | **目录层级语义写反**：v1 §1.1/§1.2/§2.1/§4.1/§6-R2 称 `img_<PID>_<StudyUID>`、`3_cxf_archives` 为 `<series>/<study>`；实测**都是反的** | 4_tjj 目录名 == DICOM **SeriesInstanceUID**；cxf 第 1 层 == DICOM **StudyInstanceUID** | 已改为 header 驱动聚合（§0.6-2） |
| P0-2 | **`img_` 目录不是 study 而是 series** → 写入的 `dicom_study_uid` 会是 series UID，study 被拆行 | 同一 StudyUID `...58586.740` 下有两个目录 `...961` / `...961.3` | 同上；4_tjj 1,770→412 study |
| P0-3 | **`3_cxf_archives` 无任何身份信息**，v1 的核心路径「从 DICOM header 反查 PatientID」不可实现 | 6 个样本的 `PatientID`/`PatientName`/`BirthDate`/`Sex`/`Age` 全空 | 本批排除，转 §7-1 |
| P0-4 | **布局覆盖不全**：v1 只描述 `img_<PID>_<UID>`，漏掉布局 C（19,732 个 study 所在）与 B（1,175 个） | 5_yxl 5/9 批次、8_hy 2/4 批次、7_hsy 几乎全部是 `<MD5>/<StudyUID>/` | 扫描器实现 4 种布局 |
| P0-5 | **规模数字错误**：v1「67,429 study / 59,445 去重 UID」= series 目录数，非 study 数 | 4_tjj：1,735 → 412 | 以扫描产物为准 |

### P1 —— 会导致数据错误或运行期失败

| # | 问题 | 证据 | 处置 |
|---|---|---|---|
| P1-1 | v1 用 `backfill_dicom_series_count.py` 写 `dicom_series`；其 bypass 路径非递归 `iterdir()`，对「目录下是 series 子目录」的新桥结构会写 `file_count=0 / byte_size=0` | `backfill_dicom_series_count.py:324` `files=[p for p in path.iterdir() if p.is_file()]` | 改为灌库阶段直接写入（§0.6-4） |
| P1-2 | v1 §2.5 只列 `ingest_batch` 的 3 个字段，漏掉 NOT NULL 的 `row_counts` / `key_fingerprint` / `schema_hash` / `secret_version` → INSERT 必失败 | `information_schema.columns` 实测 | v2 脚本按 shengyi/zhujiang 同款写法填全 |
| P1-3 | `sop_count` 定义「study 目录下文件数 `os.scandir`」对新桥无意义（study 无目录） | 同上 | 改为「该 study 所有 series 目录的递归文件数」 |
| P1-4 | v1 §3.3 命令文件名拼错 `build_xinqiang_...`（第 284 行）→ 跑不起来 | v1 原文 | 修正为 `build_xinqiao_...` |
| P1-5 | v1 验证 SQL V8/V9 是 `FROM ...` 字面占位，不可执行 | v1 原文第 367/370 行 | v2 重写为 13 条可执行 SQL |
| P1-6 | PID 前导零风险：布局 C 的 `PatientID` 如 `06281482`，若转数值会与目录名 PID 失配 | DICOM header 实测 | 全程按字符串处理 |
| P1-7 | **PID 形态假设过窄**：v1 §9 称「PID 全 8 位数字，无字母前缀」；实测有 **8 个字母前缀**目录（`img_T04774748_…`）+ **6 个带尾点**目录（`img_03009286._…`）。扫描器首版正则 `^img_(\d+)_(.+)$` 漏掉这 14 个目录 | 全量目录名普查（`纯数字 60,612 / 字母前缀 8 / 不匹配 6`） | 正则放宽为 `^img_([A-Za-z0-9.]{1,16})_(.+)$`，且 **PID 一律以 DICOM header 为准**，目录名仅兜底；重扫后 33,311 → 33,314 study |
| P1-8 | `ingest_batch` 有 `UNIQUE(center_code, secret_version, key_fingerprint, schema_hash, started_at)`，同一事务内 `CURRENT_TIMESTAMP` 相同 → 5 个 batch 撞唯一键 | 首次 dry-run 报 `UniqueViolation: lnrs_anon_uq_batch_center_secret` | `schema_hash` 改为按 source 派生（`sha256("xinqiao_disk_image_index_20260920:"+source)`） |

### P2 —— 表述/口径问题

| # | 问题 | 处置 |
|---|---|---|
| P2-1 | 标题「六盘」错误：是 **1 块盘（03_disk）下的 6 个 sub 目录** | 已改标题 |
| P2-2 | v1 第 21 行「早期估 68,944（zhujiang）口径」来源不明（珠江基线是 87,595） | 删除 |
| P2-3 | v1 §1.3 称「抽 4 个 study」但只列 2 行；且其自身数据已显示目录名 UID ≠ header StudyUID，却仍断言「UID 与目录名一致（无错配）」（第 99 行） | 已用实测表替换 |
| P2-4 | v1 §4.2 讨论 `exam_date` / `exam_date_source`：`lnrs_anon_imaging_study` **没有这两列**（DDL 0012:37-56），它们只存在于 CSV 侧，且 v2 灌库不使用 | 已注明 |
| P2-5 | v1 第 30 行「< 2 min」与第 214 行「~3-5 min」自相矛盾 | 已删（cxf 排除） |
| P2-6 | v1 第 34 行 `STUDENT_RE` 拼写 | 已修正 |
| P2-7 | v1 §6 R2 正文 `fold ers` 空格错字，且「第一层是 series UID」说法与实测相反 | 已重写风险表 |
| P2-8 | v1 把备份放 `/tmp` 未说明风险 | 已在 §6 R5 注明 |
| P2-9 | `anon_id` 有 `UNIQUE(center_code, anon_id)` + `CHECK ^ANON_[0-9a-f]{12}$`（48 bit）；14k 行碰撞概率极低但非零，撞了会整批 abort | 已在 §6 R6 注明 |

### 评审通过的部分（保留）

- 复用 `backfill_dicom_series_count.py` 的 `--center` 取值已含 `xinqiao`（脚本已预留）。
- `center_code='xinqiao'` 合法；`source` VARCHAR(64) 容量足够；`image_path` 为 TEXT 无长度风险。
- `is_placeholder=TRUE` 与 zhujiang 口径一致。
- PHI 处理方案（`.gitignore` + `git rm --cached`）沿用珠江。
- 同人不同 PID 风险 = 0 的结论成立（实测 1:1）。
- 复用 `build_zhujiang_imaging_study_index_v2.py` 的 patient FK 反查 / advisory lock / phi_audit 写法。

---

## 3. 字段映射

### 3.1 `lnrs_anon_imaging_study`

| 字段 | 来源 |
|---|---|
| `patient_id` | 布局 A/B/D：目录名 PID；布局 C：DICOM header `PatientID`（字符串） |
| `center_code` | `'xinqiao'` |
| `dicom_study_uid` | DICOM header `StudyInstanceUID`（布局 C 可与目录名校验一致） |
| `modality` | DICOM header `Modality`（实测全为 `CT`） |
| `image_path` | 布局 C：study 根；A/B/D：字典序最小的 series 目录 |
| `sop_count` | 该 study 全部 series 目录的递归文件数 |
| `source` | `xinqiao_<sub>` |
| `anon_exam_id` | `NULL` |
| `created_batch_id` | 该 source 的 batch |

### 3.2 `lnrs_anon_dicom_series`（灌库阶段直写）

| 字段 | 来源 |
|---|---|
| `dicom_study_uid` | 同上 |
| `file_count` | = `sop_count` |
| `byte_size` | 该 study 全部文件的 `st_size` 累加 |
| `series_count` | 该 study 去重 `SeriesInstanceUID` 数（扫描阶段已得） |
| `anon_exam_id` | `NULL` |

### 3.3 `lnrs_anon_patient` / `phi_audit` / `ingest_batch`

- patient：`PT_` + `LPAD(nextval('lnrs.lnrs_anon_patient_seq'),8,'0')`；`anon_id = ANON_` +
  `HMAC-SHA256(secret, 'xinqiao:'+pid)[:12]`；`is_placeholder=TRUE`；`sex='0'`。
- phi_audit：每 imaging_study 一条，`source_hash=sha256(patient_id)`，`strategy='hmac'`，
  应用层按 `(batch_id, source_table, source_field, source_hash)` 去重。
- ingest_batch：**每个 source 一个 batch**，`source_kind='dicom_dir'`，
  `source_locator='<csv>#<source>'`，`row_counts` 记录该 batch 的 imaging/series 行数。

### 3.4 CSV 列（`docs/sour/ct_image_patient_map_xinqiao.csv`）

`patient_id, center_code, dicom_study_uid, modality, image_path, sop_count, series_count,
file_count, byte_size, source, exam_date, exam_date_source, study_root_kind`

> `exam_date` / `exam_date_source` 仅 CSV 侧留存（供后续 exam 关联用），**不写入 PG**。

---

## 4. 步骤

### Step 0 环境前置（已实测）

- [x] `lnrs_anon_imaging_study` 无 `center_code='xinqiao'` 行
- [x] `lnrs_anon_patient` 无 `center_code='xinqiao'` 行
- [x] `xinqiao` 满足 `center_code` CHECK
- [x] `patient_seq.last_value` 已记录（发号起点）
- [x] `--center xinqiao` 合法

### Step 1 备份

```bash
BACKUP=/tmp/lnrs_backup/20260920_xinqiao_pre
mkdir -p "$BACKUP"
for t in lnrs_anon_patient lnrs_anon_imaging_study lnrs_anon_dicom_series lnrs_anon_phi_audit lnrs_anon_ingest_batch; do
  pg_dump -h 127.0.0.1 -U lnrs -d postgres -n lnrs -t "lnrs.$t" -Fc -f "$BACKUP/$t.dump"
  pg_dump -h 127.0.0.1 -U lnrs -d postgres -n lnrs -t "lnrs.$t" --data-only --inserts -f "$BACKUP/$t.sql"
done
```

> `/data/lnrs_backup` 在本机不可写（珠江时已确认），故用 `/tmp`。见 §6 R5。

### Step 2 扫描 → CSV

```bash
cd /home/dzy/wk/lnrs/backend
uv run python ../scripts/build_xinqiao_imaging_study_index.py --workers 16
# 产物：docs/sour/ct_image_patient_map_xinqiao.csv
#       docs/sour/scan_skipped_dirs_xinqiao.txt
```

脚本行为：单进程 walk 发现候选（4 种布局）→ 16 进程读 DICOM header + 统计文件/字节 →
按 `(PID, StudyInstanceUID, source)` 聚合 → 写 CSV。

**校验点**：
- 候选目录总数 == 80,358（§0.3 实测）
- `scan_skipped_dirs_xinqiao.txt` 为空或全部有合理解释
- 4_tjj 子集应复现 412 study / 411 PID / 232,892 文件

### Step 3 灌库

```bash
cd /home/dzy/wk/lnrs/backend
ENVIRONMENT=h196_3 uv run python ../scripts/build_xinqiao_imaging_study_index_v2.py --dry-run
ENVIRONMENT=h196_3 uv run python ../scripts/build_xinqiao_imaging_study_index_v2.py
```

写入：`ingest_batch`(+5) / `patient` / `imaging_study` / `dicom_series` / `phi_audit`。

### Step 4 验证

```bash
PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres \
  -f /home/dzy/wk/lnrs/docs/etl2/verify_xinqiao_imaging.sql
```

V1–V13 全部对照预期；重点 V4（`dicom_series` 覆盖 == `imaging_study` 去重 UID）、
V5（`file_count/byte_size/series_count` 全为正）、V12（`image_path` 前缀正确）。

### Step 5 提交

见 §8。

---

## 5. 实际规模与耗时（已执行）

| 表 | 增量 |
|---|---|
| `lnrs_anon_ingest_batch` | +5（每 source 一个，status=success） |
| `lnrs_anon_patient` | **+33,313** |
| `lnrs_anon_imaging_study` | **+33,314** |
| `lnrs_anon_dicom_series` | **+33,314** |
| `lnrs_anon_phi_audit` | **+33,313**（1 个 PID 有 2 个 study → 去重后少 1） |

耗时：扫描 **1,259 s**（80,358 次 DICOM header 读 + 18.66M 文件 stat，16 进程）；
灌库 **62.6 s**；**无 backfill 阶段**（相比珠江方案省 3.5 h）。

全局回归：`shengyi 82,994` / `zhujiang 86,927` 未变；`patient_seq` 502,197 → 535,547（含 CACHE 50 的块尾）。

---

## 6. 风险

| # | 风险 | 缓解 |
|---|---|---|
| R1 | 布局 A 的 series 目录可能被误判为独立 study | 已用 DICOM `StudyInstanceUID` 聚合，不依赖目录名 |
| R2 | 同一 study 在布局 C 下有多个 study 根（如同时出现在 `part1/1` 与 `part2`）→ `file_count` 重复累加、`image_path` 取后者 | 扫描后核对 `study_root_kind='md5_layout_study_root'` 行的重复 UID；必要时按目录去重 |
| R3 | 布局 B 的 16-hex 被写成非法 `SeriesInstanceUID`（VR UI 告警） | 只用 `StudyInstanceUID` 作键，告警已静音 |
| R4 | 布局 C 的 DICOM `PatientID` 前导零 | 全程字符串；灌库校验正则 `^[A-Za-z0-9.]{1,16}$` |
| R5 | 备份放 `/tmp`，可能被清理 | 执行后尽快转存；`/tmp` 至少保留到 Step 4 通过 |
| R6 | `anon_id` 48 bit 碰撞（`UNIQUE(center_code, anon_id)`） | 概率 ~1e-7；`ON CONFLICT (anon_id) DO NOTHING` 已兜底，撞了该 patient 缺行会体现在 `imaging_study` 行数差 |
| R7 | NFS 慢（珠江实测 1.51 study/s 的 _mp 路径） | 扫描用 16 进程读 header，单目录只读 1 个文件；不跑全量 register_folder |
| R8 | 中文目录名（`张家俊_Batch*.zip_folder` / `胸外科导出*`） | 用 `os.scandir`/`os.walk` 处理 bytes→utf-8，不依赖 shell 编码；实测可正常遍历 |
| R9 | `image_path` 对布局 A/B/D 指向 series 目录（非 study 根）→ 查看器可能只看到该 series | 已用 `study_root_kind` 列标记；后续工单 §7-2 评估查看器适配 |
| R10 | `3_cxf_archives` 7,984 study 未入库，业务侧若按「全部新桥影像」统计会缺失 | §7-1 明确列为待办并说明原因 |
| R11 | `is_placeholder=TRUE` 标在真实影像患者上，语义上是「待补人口学」而非「占位」 | 与 zhujiang 口径一致；后续 §7-3 回填后改 FALSE |

---

## 7. 后续工单

- **7-1** `3_cxf_archives`（7,984 study / 1,016 GB / 4.5M 文件）入库：**阻塞于外部映射**
  （需新桥 PACS/HIS 提供 `StudyInstanceUID → PatientID`）。映射到手后：第 1 层即 study UID，
  `lists/batch_*.txt` 可直接枚举，无需遍历 1,016 GB。
- **7-2** 影像查看器对「`image_path` = series 目录」的适配评估（布局 A/B/D）。
- **7-3** 占位真实化：关联 exam 后回填人口学并把 `is_placeholder` 置 FALSE。
- **7-4** 新桥 exam 灌库 + `dicom_series.anon_exam_id` 回填。
- **7-5** h196_3 → 1.59（h42）同步（`lnrs-sync-196-to-159`）。
- **7-6** **反查珠江已导入数据是否同病**：珠江目录名确认为 `StudyInstanceUID`（已验证 1 例），
  但建议抽样 ≥100 例确认 `lnrs_anon_imaging_study.dicom_study_uid` 与 DICOM header 一致。
- **7-7** git 历史 PHI 清除（filter-repo/BFG，破坏性）。

---

## 8. 变更文件

| 文件 | 改动 |
|---|---|
| `scripts/build_xinqiao_imaging_study_index.py` | 新建：4 布局扫描 + DICOM header 解析 + 聚合 → CSV |
| `scripts/build_xinqiao_imaging_study_index_v2.py` | 新建：5 batch + patient + imaging_study + dicom_series + phi_audit |
| `docs/etl2/verify_xinqiao_imaging.sql` | 新建：V1–V13 |
| `docs/etl2/plan-xinqiao-disk03-import.md` | 本文件（v2 评审修订版） |
| `.gitignore` | + `docs/sour/ct_image_patient_map_xinqiao.csv` / `docs/sour/xinqiao_imaging_study_patient_added.txt` |
| `docs/sour/ct_image_patient_map_xinqiao.csv` | 产物，**新建即被 `.gitignore` 忽略**（含明文 PID），无需 `git rm --cached` |

---

## 9. 执行记录

| 时间 | 步骤 | 结果 |
|---|---|---|
| 2026-09-20 00:47 | 扫描 v1 启动 | 候选 80,344 |
| 2026-09-20 00:48 | 4_tjj 单 sub 验证 | 1,770 series → 412 study / 411 PID / 232,892 文件 / 0.05 TiB |
| 2026-09-20 01:17 | 扫描 v1 完成 | 33,311 study（**0 跳过**）；发现 7,154 个布局 C 目录被 `no_file` 误跳 → 修复 |
| 2026-09-20 00:59 | Step 1 备份 | `/tmp/lnrs_backup/20260920_xinqiao_pre`（1.3 GB）；`patient_seq=502,197` |
| 2026-09-20 01:22 | 目录名 PID 普查 | 纯数字 60,612 / 字母前缀 8 / 带尾点 6 → 修正则 + 改 header 优先 |
| 2026-09-20 01:32 | 扫描 v2 启动（修复后） | 候选 80,358 |
| 2026-09-20 01:53 | 扫描 v2 完成 | **33,314 study / 33,313 PID / 18,664,932 文件 / 3.96 TiB / 0 跳过** |
| 2026-09-20 01:54 | Step 3 dry-run | 33,314 行 0 丢弃；修 batch 唯一键冲突（P1-8） |
| 2026-09-20 01:56 | Step 3 灌库 | 62.6 s；patient 33,313 / imaging 33,314 / series 33,314 / phi 33,313 |
| 2026-09-20 01:58 | Step 4 验证 SQL | **V1–V13 全过**；V5 `file_count/byte_size/series_count` 33,314/33,314/33,314 全为正 |
| 2026-09-20 01:59 | 独立冒烟 | 随机 5 行回读磁盘 DICOM：`dicom_study_uid` == header `StudyInstanceUID` **5/5** |
| 2026-09-20 02:0x | Step 5 提交 | 本地 `3ef6acce`（5 文件）；**push 失败**：`gz.proxy.git.sz` 502（与珠江 `ce038e91` 同一代理故障，待网络恢复 `git push`） |
