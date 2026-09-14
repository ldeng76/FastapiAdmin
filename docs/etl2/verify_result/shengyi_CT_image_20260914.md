# 数据导入核验报告 — 省医 CT影像（含报告）

- 核验日期：2026-09-14
- 核验执行：自动化（`docs/etl2/数据导入核验清单.xlsx` 第 2 行）
- 核验结论：**未通过** —— 源数据完整，但 ETL2 spec 与离线灌库脚本均未覆盖；目标库 0 行
- 完成状态：**未完成**（清单中无 ETL2 spec、无 shengyi 离线灌库脚本，需先建 ETL 配置或迁移脚本）
- 核验源数据：清单 `docs/etl2/数据导入核验清单.xlsx` 第 2 行（`医院名称=省医`、`数据项名称=CT影像(含报告)`、`预期记录数=82994`、`完成状态=空`）

---

## 0. 结论速览

| 维度 | 结果 | 期望 | 判定 |
|---|---|---|---|
| 源 parquet 文件数 | 2（`shengyi_06_disk_CT.parquet` + `shengyi_07_disk_CT.parquet`） | 2（清单通配 `*06*.parquet`、`*07*.parquet`） | ✅ 匹配 |
| 源 parquet 行数合计 | **82,994** | 82,994 | ✅ 精确匹配 |
| dir_path 全部存在磁盘 | 82,994 / 82,994（100%） | 100% | ✅ |
| 空 patient_id / 空 dir_path 行 | 0 / 0 | 0 | ✅ |
| record_id 内部嵌入 DICOM StudyUID | 全部含 `1.2.840.…` 形式 | — | ✅ |
| record_id 全局去重后行数 | **82,153**（06 盘 -651 重复 + 07 盘 -190 重复） | — | ⚠️ 源数据有 841 行级重复 |
| PG `lnrs_anon_imaging_study` shengyi 行数 | **0** | 82,994（清单预期） | ❌ **未导入** |
| PG `lnrs_anon_patient` shengyi 行数 | 87,138 | ≥ 82,988 distinct patient | ✅ 已灌，但其中仅 **306 例**（0.37%）与本批 parquet 患者的 anon_id 反查命中 |
| 本批 parquet 患者 anon_id 在 PG 中反查不到 | **82,682 / 82,988（99.63%）** | 0 | ❌ PG patient 表未覆盖本批患者 |
| ETL2 spec 中 shengyi 中心定义 | `_CENTER_PARQUET_SPECS["shengyi"]` 25 项 src_table（patient/visit/…/imaging_report），**无 CT_image / imaging_study 项** | 含 CT_image | ❌ **spec 未配置** |
| 离线灌库脚本（参考 zhujiang） | `scripts/build_imaging_study_index.py` 仅支持 `--center zhujiang` | `--center shengyi` | ⚠️ shengyi 入口未实装 |

**最终判定**：❌ 未通过。清单预期的「82,994 行影像入库」在目标环境（dev PG）实际为 0 行；源数据 parquet 完整且自洽，但 ETL2 侧既无 spec、也无离线灌库脚本落地到 shengyi 中心。

---

## 1. 源数据核验

### 1.1 通配匹配

清单中路径通配：

```
/data/wlx/DATABASE/extracted_tables/shengyi/CT_image/*06*.parquet
/data/wlx/DATABASE/extracted_tables/shengyi/CT_image/*07*.parquet
```

实测目录 `/data/wlx/DATABASE/extracted_tables/shengyi/CT_image/` 命中文件：

| 文件 | 大小 | 总行数 | distinct record_id | 行级重复 | distinct patient_id |
|---|---:|---:|---:|---:|---:|
| `shengyi_06_disk_CT.parquet` | 5.04 MB | **52,991** | 52,340 | 651 | 52,988 |
| `shengyi_07_disk_CT.parquet` | 2.98 MB | **30,003** | 29,813 | 190 | 30,000 |
| **合计** | 8.02 MB | **82,994** | **82,153** | **841** | **82,988** |

✅ 行数 82,994 = 清单预期 82,994（精确一致）。

### 1.2 schema

两文件结构一致：

```
record_id   VARCHAR  # shengyi_<盘号>_disk_<DICOM StudyInstanceUID>
patient_id  VARCHAR  # 院内本地 PID（如 "03373-3"、"11563976"）
dir_path    VARCHAR  # /data/wlx/DATABASE/06_disk/... 或 07_disk/... 绝对路径
```

### 1.3 dir_path 完整性

- 06 盘：52,991 行 dir_path 全部 `os.path.exists()` 通过（0 个空值、0 个缺失）
- 07 盘：30,003 行 dir_path 全部 `os.path.exists()` 通过（0 个空值、0 个缺失）
- 路径前缀示例：
  - 06：`/data/wlx/DATABASE/06_disk/DCM_part01.zip_folder/03373-3/1.3.12.../1.3.12...`
  - 07：`/data/wlx/DATABASE/07_disk/DCM_part07.zip_folder/11563976/1.2.840.../1.3.46...`

### 1.4 record_id 编码

每行 `record_id` 形如 `shengyi_06_disk_<DICOM_StudyUID>` 或 `shengyi_07_disk_<DICOM_StudyUID>`，可直接解析出 `dicom_study_uid`（去掉前缀 `shengyi_<盘号>_disk_`）。

- 06 盘唯一 record_id：52,340；07 盘：29,813
- 跨盘 record_id 重叠：0（盘号前缀天然分隔）
- 各自盘内重复：06 盘 651 个 record_id 重复 2 次，07 盘 190 个 record_id 重复 2 次
- 重复原因推测：同一 Study 被多 Series / SOP instance 抽取误记录为多行（record_id 缺失 Series/SOP 后缀），源数据层面的去重应由 ETL 层的 `UNIQUE (patient_id, dicom_study_uid, source)` 保证

### 1.5 patient_id 分布

- 06 盘：52,988 distinct patient_id；07 盘：30,000 distinct patient_id
- 跨盘 patient_id 重叠：0（**两盘患者完全无交集** —— 06 盘与 07 盘是 shengyi 中心两个独立采集批次）
- 合计 distinct patient_id：**82,988**（与 82,994 行总数相差 6 行，可推测同一 (patient_id) 在某盘存在 6 次重复，但 record_id 仍唯一）

---

## 2. 目标库核验

### 2.1 PG 连接

- 环境：`backend/env/.env.dev`（`ENVIRONMENT=dev`、`DATABASE_HOST=127.0.0.1`、`DATABASE_NAME=postgres`）
- 密码：`LNRS_ANON_SECRET = "change-me-in-production-please"`（与 `setting.py:defaults` 一致）
- 脱敏算法：`HMAC-SHA256(secret, "shengyi:{patient_local_id}")[:12]` → `ANON_<12hex>`

### 2.2 dev 库 shengyi 行数

| 表 | 行数 |
|---|---:|
| `lnrs.lnrs_anon_patient` WHERE center_code='shengyi' | **87,138** |
| `lnrs.lnrs_anon_imaging_study` WHERE center_code='shengyi' | **0** |
| `lnrs.lnrs_anon_imaging_study`（全库） | 36,356（**全部为 zhujiang**，跨 01_disk/02_disk 两批） |

### 2.3 patient 覆盖率

本批 parquet 82,988 distinct patient_id 离线 HMAC 计算 anon_id 后反查 PG `lnrs_anon_patient`：

| 维度 | 数值 | 占比 |
|---|---:|---:|
| parquet distinct patient_id | 82,988 | 100% |
| anon_id 在 `lnrs_anon_patient (center='shengyi')` 命中 | **306** | **0.37%** |
| anon_id **未**命中（PG 缺失对应 patient） | 82,682 | **99.63%** |

行级（按 parquet 行数）：

| 文件 | 行数 | anon_id 缺失对应 PG patient 的行数 |
|---|---:|---:|
| `shengyi_06_disk_CT.parquet` | 52,991 | 52,705（99.45%） |
| `shengyi_07_disk_CT.parquet` | 30,003 | 29,983（99.93%） |

### 2.5 关键缺口

`lnrs_anon_imaging_study` 存在 FK `patient_id REFERENCES lnrs.lnrs_anon_patient(patient_id) ON DELETE CASCADE`。在 99.63% 的患者不在 PG 的前提下，**即使配置了 ETL2 spec 或离线灌库脚本，绝大部分影像行也会因 FK 违规被拒**。需先补充灌入本批 82,682 名缺失的 shengyi patient。

---

## 3. ETL 侧核验

### 3.1 ETL2 spec 检查

`backend/app/plugin/module_medical/hospital/anon_etl_engine.py:2425` 处的 `_CENTER_PARQUET_SPECS["shengyi"]` 共 25 项 src_table：

```
patient, visit_record, pahology_specimen, imaging_report, ultrasound_report,
ecg_report, genetic_report, surgery_record, lab_result_p1/p2/p3/p4,
drug_order, no_drug_order, outp_order, anesthesia_order,
diagnosis, diagnosis_inpatient, clinical_document, medical_history,
nursing_observation, icu_observation, anesthesia_observation
```

**未见 `disk_ct` / `imaging_study` / `CT_image` / `dicom_study` 等任何与磁盘 DICOM 影像对应的条目**。

`imaging_report`（item 4）是「影像报告文本」（CT/MR/PETCT/Radiology/Ultrasound/Other 的放射诊断报告自由文本），与本任务「CT影像(含报告)」中的 DICOM 影像本体（磁盘路径 → `lnrs_anon_imaging_study`）语义不同。

### 3.2 离线灌库脚本检查

`scripts/build_imaging_study_index.py` 仅硬编码 `DEFAULT_CENTER = "zhujiang"`（脚本 header 注释：「本轮只支撑 CT」/「默认 center_code='zhujiang'」）。脚本解析 `docs/sour/ct_image_patient_map.csv`（36,698 行），没有 shengyi 的 CSV，也没有 `--center shengyi` 路径的实装。

`docs/sour/` 目录内只有 zhujiang 的 `ct_image_patient_map.csv`，未见 `shengyi_*_image_patient_map.csv` 或等价映射。

### 3.3 缺失项清单

为把本批 82,994 行影像落入 `lnrs_anon_imaging_study`，需要补齐：

1. **`docs/sour/` 下新增 shengyi 的 `pid_image_map.csv`**（列：`pat_local_id, dicom_study_uid, image_path`）—— 或由本批 parquet 的 82,994 行直接派生（`record_id` 拆前缀 → `dicom_study_uid`、`patient_id` → `pat_local_id`、`dir_path` → `image_path`）
2. **patient 表增量灌库**：本批 82,682 个未在 PG 的患者需先用 ETL1 / 离线脚本写入 `lnrs_anon_patient`（按 ETL2 引擎同款 patient spec 发号 `PT_<8位>` + `ANON_<12hex>`），保证 FK 满足
3. **ETL2 spec 补 CT_image 条目** 或 **离线灌库脚本 `build_imaging_study_index.py` 支持 `--center shengyi`**：两选一
4. **source 字段定义**：建议 `source = 'disk_06_zhujiang'` → 改为 `'disk_06_shengyi' / 'disk_07_shengyi'` 两源（与 zhujiang `disk1_zhujiang / disk2_zhujiang_supplement` 同语义）
5. **去重策略**：`ON CONFLICT (patient_id, dicom_study_uid, source) DO NOTHING`（参考 `build_imaging_study_index.py:9`），消化源数据的 841 行级重复
6. **orphan 审计**：本批 0 行 `patient_id` 为空、`0 行 dir_path` 缺失、无 `csv_uncovered` 类孤儿，但跨盘 patient_id 完全不重叠（两盘独立批次）值得在 `lnrs_anon_imaging_orphan` 审计中关注

---

## 4. 核验数字汇总（用于清单回填）

| 字段 | 数值 |
|---|---:|
| 源 parquet 文件数 | 2 |
| 源 parquet 行数 | **82,994** |
| 清单预期记录数 | 82,994 |
| 行数匹配 | ✅ 完全一致 |
| dir_path 全部存在磁盘 | ✅ 100% |
| record_id 全部含 DICOM StudyUID | ✅ |
| 源数据 record_id 重复行 | 841（去重后 82,153） |
| PG `lnrs_anon_imaging_study` shengyi 行数 | 0 |
| PG `lnrs_anon_patient` shengyi 行数 | 87,138 |
| 本批 parquet 患者在 PG patient 命中 | 306 / 82,988（0.37%） |
| 本批 parquet 行在 PG patient 命中（行级） | 306 / 82,994（0.37%） |
| ETL2 spec 是否覆盖 shengyi CT_image | ❌ 否 |
| 离线灌库脚本是否覆盖 shengyi | ❌ 否（仅 zhujiang） |
| **核验结论** | **❌ 未通过** |
| **完成状态建议** | **未完成**（待补 spec + 灌库脚本 + patient 表增量） |

---

## 5. 建议落地路径（不在本次核验范围，仅供后续工单参考）

按 zhujiang 现有模式（`scripts/build_imaging_study_index.py` + `docs/sour/ct_image_patient_map.csv`）镜像移植：

1. 派生 `docs/sour/shengyi_image_patient_map.csv`：82,994 行，列 `pat_local_id, dicom_study_uid, image_path`（来自本批两文件，`record_id` 去前缀即得 `dicom_study_uid`，`dir_path` 即 `image_path`，`patient_id` 即 `pat_local_id`）
2. 补 patient：82,682 名新增 patient 按 ETL2 patient spec（`backend/anon_etl_engine.py` patient kind）发号 `PT_<8位>` + `ANON_<12hex>`，FK 安全
3. 改 `scripts/build_imaging_study_index.py` 加 `--center shengyi` 路径（或新建 `scripts/build_shengyi_imaging_study_index.py`），`source` 取 `disk_06_shengyi` / `disk_07_shengyi`
4. ETL2 spec `_CENTER_PARQUET_SPECS["shengyi"]` 视情况补 `imaging_study`（kind 需新增，目前无现成 kind 可用；建议优先走离线灌库路径）
5. 跑完回看本报告 §2.2 / §4 各数；预期 `lnrs_anon_imaging_study (center='shengyi')` 应为 82,153 行（去重后）

---

## 附：核验执行命令（可复现）

```bash
# 源数据行数 / schema / record_id / dir_path 检查
backend/.venv/bin/python <<'EOF'
import duckdb, os, concurrent.futures
con = duckdb.connect()
files = [
    '/data/wlx/DATABASE/extracted_tables/shengyi/CT_image/shengyi_06_disk_CT.parquet',
    '/data/wlx/DATABASE/extracted_tables/shengyi/CT_image/shengyi_07_disk_CT.parquet',
]
for f in files:
    n = con.execute(f"SELECT COUNT(*) FROM read_parquet('{f}')").fetchone()[0]
    nd = con.execute(f"SELECT COUNT(DISTINCT record_id) FROM read_parquet('{f}')").fetchone()[0]
    print(f, n, 'distinct=', nd, 'dup=', n-nd)
    paths = [r[0] for r in con.execute(f"SELECT dir_path FROM read_parquet('{f}')").fetchall()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as ex:
        exists = sum(1 for h in ex.map(os.path.exists, paths) if h)
    print('  exist=', exists, '/', len(paths))
EOF

# PG 行数
PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres -c "
SELECT
  (SELECT COUNT(*) FROM lnrs.lnrs_anon_patient WHERE center_code='shengyi') AS shengyi_patients,
  (SELECT COUNT(*) FROM lnrs.lnrs_anon_imaging_study WHERE center_code='shengyi') AS shengyi_imaging_studies;
"

# patient 反查
backend/.venv/bin/python <<'EOF'
import duckdb, os, hmac, hashlib, psycopg
con = duckdb.connect()
pats = set()
for f in ['/data/wlx/DATABASE/extracted_tables/shengyi/CT_image/shengyi_06_disk_CT.parquet',
          '/data/wlx/DATABASE/extracted_tables/shengyi/CT_image/shengyi_07_disk_CT.parquet']:
    pats |= {r[0] for r in con.execute(f"SELECT DISTINCT patient_id FROM read_parquet('{f}')").fetchall()}
secret = b"change-me-in-production-please"
anon = {p: "ANON_" + hmac.new(secret, f"shengyi:{p}".encode(), hashlib.sha256).hexdigest()[:12] for p in pats}
with psycopg.connect("host=127.0.0.1 user=lnrs password=lnrs_pwd dbname=postgres") as c:
    a2p = dict(c.execute("SELECT anon_id, patient_id FROM lnrs.lnrs_anon_patient WHERE center_code='shengyi'").fetchall())
hit = sum(1 for a in anon.values() if a in a2p)
print(f"hit={hit} / {len(anon)}  ({hit/len(anon)*100:.2f}%)")
EOF
```