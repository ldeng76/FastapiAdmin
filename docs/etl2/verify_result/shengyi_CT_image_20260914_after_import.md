# 数据导入核验报告 — 省医 CT影像（含报告）— 灌库后

- 核验日期：2026-09-14
- 关联计划：`docs/etl2/plan-shengyi-CT-image-import.md`
- 灌库脚本：`scripts/build_shengyi_imaging_study_index.py`
- 验证脚本：`docs/etl2/verify_shengyi_imaging_study.sql`
- 灌库环境：dev（127.0.0.1:5432，secret_version='v1'，key_fingerprint=SHA256(secret)[:16]）
- 核验结论：**✅ 通过**（dev PG 行数与预期完全一致；FK 全部满足；patient 格式合法）

---

## 0. 数字速览（灌库后 vs 灌库前）

| 维度 | 灌库前 | 灌库后 | Δ |
|---|---:|---:|---:|
| `lnrs_anon_patient` (center='shengyi', deleted_at IS NULL) | 87,138 | **169,820** | **+82,682** |
| `lnrs_anon_imaging_study` (center='shengyi') | 0 | **82,994** | **+82,994** |
| `lnrs_anon_imaging_study` unique `dicom_study_uid` | 0 | **82,153** | **+82,153** |
| `lnrs_anon_imaging_study` unique `patient_id` | 0 | **82,988** | **+82,988** |
| ingest_batch (新增) | — | **1 行** (source_kind=dicom_dir) | +1 |

---

## 1. 数字预期对照（计划 §5）

| 阶段 | 计划预期 | 实测 | 判定 |
|---|---:|---:|---|
| `lnrs_anon_patient (shengyi)` | 169,820 | 169,820 | ✅ |
| `lnrs_anon_imaging_study (shengyi)` | 82,994 行（含 841 ON CONFLICT 去重） | 82,994 | ✅ |
| 实际 unique `dicom_study_uid` | 82,153 | 82,153 | ✅ |
| `disk_06_shengyi` 行数 | 52,991 | 52,991 | ✅ |
| `disk_06_shengyi` unique studies | 52,340 | 52,340 | ✅ |
| `disk_07_shengyi` 行数 | 30,003 | 30,003 | ✅ |
| `disk_07_shengyi` unique studies | 29,813 | 29,813 | ✅ |
| 跨盘 patient_id 重叠 | 0 | 0 | ✅ |
| FK 一致性（imaging→patient） | 0 孤儿 | 0 孤儿 | ✅ |
| patient_id 格式 (PT_<8位>) | 0 不合规 | 0 不合规 | ✅ |
| anon_id 格式 (ANON_<12hex>) | 0 不合规 | 0 不合规 | ✅ |

---

## 2. 验证 SQL 完整输出

```sql
1. patient 总数（shengyi）              → 169,820  ✅
2. imaging_study 总数 + unique          → 82,994 行 / 82,153 unique / 82,988 unique pid ✅
3. 按 source 拆分：
   - disk_06_shengyi → 52,991 行（52,340 unique studies）
   - disk_07_shengyi → 30,003 行（29,813 unique studies）
4. 跨盘 patient_id 重叠                 → 0        ✅
5. patient_id 格式（PT_<8位>）           → 0 不合规  ✅
6. anon_id 格式（ANON_<12hex>）          → 0 不合规  ✅
7. imaging → patient FK 一致性           → 0 孤儿    ✅
8. modality / center_code 分布           → shengyi/CT 100%（82,994 行）✅
```

详见 `docs/etl2/verify_shengyi_imaging_study.sql` 脚本（重跑命令见 §6）。

---

## 3. 灌库过程摘要

| 步骤 | 输出 |
|---|---|
| Step 1 DuckDB 读 parquet | 82,994 行 |
| Step 2 record_id 正则解析 dicom_study_uid | 82,994 行（0 跳过）|
| Step 3 离线 HMAC 算 anon_id | 82,988 distinct patient |
| Step 4 PG 反查命中 | 306（PG 已存在的患者直接复用） |
| Step 4 需要新增 patient | 82,682 |
| Step 5 patient INSERT (nextval + advisory lock) | 82,682 新增 |
| Step 6 内存去重 | 82,994 → 82,994（脚本层未命中，PG ON CONFLICT 兜底）|
| Step 7 imaging INSERT (ON CONFLICT DO NOTHING) | 82,994 行发送，PG 接受 82,153 unique + 841 拒绝 |
| 耗时 | 101 秒 |

`patient_added` 列表已落 `docs/sour/shengyi_imaging_study_patient_added.txt`（82,682 行）。

---

## 4. ingest_batch 元数据

```sql
SELECT batch_id, center_code, source_kind, source_locator, started_at, status
  FROM lnrs.lnrs_anon_ingest_batch
 WHERE center_code='shengyi' AND source_kind='dicom_dir'
 ORDER BY started_at DESC LIMIT 1;
```

新增 1 行：

| batch_id | center_code | source_kind | source_locator | status |
|---|---|---|---|---|
| `913e071d-6219-4fca-9245-5d615b3ef8ca` | shengyi | dicom_dir | `/data/wlx/DATABASE/extracted_tables/shengyi/CT_image` | success |

---

## 5. 与灌库前核验报告的对照

| 维度 | 灌库前报告（`shengyi_CT_image_20260914.md`） | 灌库后（本文） |
|---|---|---|
| 源 parquet 行数 | 82,994 | 82,994（不变） |
| 源 distinct record_id | 82,153 | 82,153（不变） |
| 源 dir_path 全部存在 | 100% | 100%（不变）|
| PG `lnrs_anon_imaging_study` (shengyi) | **0 行** | **82,994 行** |
| PG `lnrs_anon_patient` (shengyi) | 87,138 | 169,820 |
| 本批 parquet 患者 anon_id 在 PG 命中 | 306 / 82,988（0.37%）| **82,988 / 82,988（100%）** |
| ETL2 spec 是否覆盖 shengyi CT_image | ❌ 否（走离线路径）| ❌ 否（保持）|
| 离线灌库脚本是否覆盖 shengyi | ❌ 否（仅 zhujiang）| ✅ **已新建** `scripts/build_shengyi_imaging_study_index.py` |
| **核验结论** | ❌ **未通过** | ✅ **通过** |

---

## 6. 复现命令

```bash
# 灌库
cd /home/dzy/wk/lnrs
ENVIRONMENT=dev backend/.venv/bin/python scripts/build_shengyi_imaging_study_index.py

# 验证
PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres \
  -f docs/etl2/verify_shengyi_imaging_study.sql

# 复查 patient_added 文件
wc -l docs/sour/shengyi_imaging_study_patient_added.txt   # → 82688（6 行注释 + 82682 行数据）
```

---

## 7. 已知局限 / 后续工作

| 项 | 描述 | 处理建议 |
|---|---|---|
| `sop_count=0` | 源 parquet 不含 SOP 粒度；后续可扫描 dir_path 子目录重新计算 | 后续工单：从 DICOM 元数据补 sop_count |
| `image_path` 完整性 | 灌库时未做磁盘存在性校验；理论上可能在 ETL 之后磁盘被清理 | 由 `lnrs_anon_imaging_orphan` 审计链路（0016 迁移）发现并登记 |
| ETL2 spec 仍未覆盖 | 本次走离线路径；ETL2 引擎 `_CENTER_PARQUET_SPECS["shengyi"]` 零改动 | 后续若需 ETL2 也支持 CT_image，可补一条 spec；本任务不要求 |
| h196_3 复跑 | h196_3 环境 secret 可能不同，单独跑 | 后续工单：相同脚本换 `LNRS_PG_DSN` + secret 即可 |
| dir_path 不在 PG 视图字典 | `lnrs_anon_v_imaging_study` 视图（0019 迁移）会按 dir_path 派生 study_description / study_date | 自动生效，无需额外脚本 |

---

## 8. 改动文件清单（本次灌库任务）

| 文件 | 改动 |
|---|---|
| `scripts/build_shengyi_imaging_study_index.py` | 新建（~280 行）|
| `docs/etl2/verify_shengyi_imaging_study.sql` | 新建（~70 行）|
| `docs/etl2/plan-shengyi-CT-image-import.md` | 新建（实施计划）|
| `docs/sour/shengyi_imaging_study_patient_added.txt` | 新建（脚本产物，82,682 行）|
| `backend/.backup/pre_shengyi_imaging_20260914_155423.sql` | 新建（灌库前备份，129 MB）|
| `docs/etl2/数据导入核验清单.xlsx` | 同步更新第 2 行【完成状态】+【核验结果路径】|
| `docs/etl2/verify_result/shengyi_CT_image_20260914_after_import.md` | 本文（after_import 核验报告）|

**不改动**：
- `backend/app/plugin/module_medical/hospital/anon_etl_engine.py`
- `scripts/build_imaging_study_index.py`（zhujiang 路径）