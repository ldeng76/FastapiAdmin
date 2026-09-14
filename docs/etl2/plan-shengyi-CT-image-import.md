# shengyi 中心 CT影像（含报告）离线灌库实施方案

## 0. 结论先行

- **目标**：把 `shengyi_06_disk_CT.parquet` + `shengyi_07_disk_CT.parquet` 共 **82,994 行**（去重后 **82,153 unique record_id**）导入 dev PG `lnrs.lnrs_anon_imaging_study`（center_code='shengyi'）
- **patient 表增量**：补 82,682 个缺失 shengyi patient（FK 强制）
- **路径**：镜像 `scripts/build_imaging_study_index.py`（zhujiang）的新脚本 `scripts/build_shengyi_imaging_study_index.py`
- **匿名化**：HMAC-SHA256(`change-me-in-production-please`, `"shengyi:"+pid`)[:12] → `ANON_<12hex>`，与现有 ETL2 引擎 `anonymize.py:compute_anon_id` 完全同款
- **ETL2 引擎零改动**（`_CENTER_PARQUET_SPECS["shengyi"]` 不动），离线路径与现有 zhujiang 模式保持一致
- **最终状态**：dev `lnrs_anon_patient (shengyi)` 从 87,138 → **169,820**；`lnrs_anon_imaging_study (shengyi)` 从 0 → **82,153**

---

## 1. 问题场景

### 1.1 源数据

| 文件 | 行数 | distinct record_id | 行级重复 | distinct patient_id |
|---|---:|---:|---:|---:|
| `shengyi_06_disk_CT.parquet` | 52,991 | 52,340 | 651 | 52,988 |
| `shengyi_07_disk_CT.parquet` | 30,003 | 29,813 | 190 | 30,000 |
| **合计** | **82,994** | **82,153** | **841** | **82,988** |

两盘 patient_id 完全无重叠（独立采集批次）。

每行字段：
- `record_id`：形如 `shengyi_<盘>_disk_<DICOM_StudyInstanceUID>`（如 `shengyi_06_disk_1.2.840.113564.35201818813822.21168.637093131775193082.30`）
- `patient_id`：院内本地 PID（如 `03373-3`、`11563976`、`12415499`）
- `dir_path`：DICOM Study 根目录绝对路径

### 1.2 PG 现状（dev 库）

| 表 | 行数 | 备注 |
|---|---:|---|
| `lnrs.lnrs_anon_patient (center='shengyi')` | 87,138 | 仅 306 例 anon_id 与本批 parquet 重合（0.37%） |
| `lnrs.lnrs_anon_imaging_study (center='shengyi')` | 0 | 全部 zhujiang 36,356 行 |

### 1.3 缺什么

1. **离线路径不存在**：`scripts/build_imaging_study_index.py` 仅支持 zhujiang
2. **patient FK 缺失**：82,682 名本批患者不在 PG patient 表，FK 会拒掉几乎所有影像行
3. **ETL2 spec 未覆盖**：`_CENTER_PARQUET_SPECS["shengyi"]` 25 项无 CT_image / imaging_study（按本次方案**不**修引擎，走离线路径）

---

## 2. 实施方案

### 2.1 字段映射

| 源列 | 目标列 | 派生规则 |
|---|---|---|
| `record_id` | `dicom_study_uid` | 去掉前缀 `shengyi_<盘>_disk_`（共 19 字符）取后半 |
| `patient_id` | → 离线算 `ANON_<12hex>` → 反查 `lnrs_anon_patient.patient_id` | `HMAC_SHA256(secret, "shengyi:"+pid)[:12]` |
| `dir_path` | `image_path` | 原值 |
| 文件名 | `source` | `shengyi_06_disk_CT.parquet` → `disk_06_shengyi`；`shengyi_07_disk_CT.parquet` → `disk_07_shengyi` |
| — | `modality` | 常量 `'CT'` |
| — | `sop_count` | 0（源数据无 SOP 粒度） |
| — | `center_code` | 常量 `'shengyi'` |
| — | `created_batch_id` | 灌库时生成的 UUID，整批同一值 |
| — | `created_at` / `updated_at` | `CURRENT_TIMESTAMP`（DB 触发器） |

### 2.2 脚本骨架

新文件 `scripts/build_shengyi_imaging_study_index.py`（约 250 行），按 `build_imaging_study_index.py` 风格：

```python
PARQUETS = [
    ('/data/wlx/DATABASE/extracted_tables/shengyi/CT_image/shengyi_06_disk_CT.parquet', 'disk_06_shengyi'),
    ('/data/wlx/DATABASE/extracted_tables/shengyi/CT_image/shengyi_07_disk_CT.parquet', 'disk_07_shengyi'),
]
CENTER = 'shengyi'
RECORD_PREFIX_RE = re.compile(r'^shengyi_\d{2}_disk_(.+)$')
```

### 2.3 处理流程

```
Step 1: DuckDB 读两 parquet → (record_id, patient_id, dir_path, source) 列表
Step 2: record_id 正则解析 dicom_study_uid；空 patient_id / 解析失败 → WARNING 跳过
Step 3: 离线 HMAC 算 anon_id（82,988 distinct → 82,988 个 ANON_*）
Step 4: PG 反查 anon_id → patient_id（chunk=5000）
        命中 → 标记 reused_patients += 1
        未命中 → 进入 Step 5 patient 增量
Step 5: patient 增量发号（pg_advisory_xact_lock + MAX(patient_id)+1 续号）
        INSERT INTO lnrs.lnrs_anon_patient (patient_id, anon_id, center_code, ...)
        同时记录到 added_pids[]
Step 6: 内存去重（patient_id, dicom_study_uid, source）
        82,994 行 → 82,153 unique（消 841 行级重复）
Step 7: INSERT INTO lnrs.lnrs_anon_imaging_study
        ON CONFLICT (patient_id, dicom_study_uid, source) DO NOTHING
        批大小 2000
Step 8: 输出 patient_added 列表到 docs/sour/shengyi_imaging_study_patient_added.txt
```

### 2.4 patient 增量发号细节

避免与现有 ETL2 patient kind 并发抢号：

```sql
-- 拿 advisory lock（事务结束自动释放）
SELECT pg_advisory_xact_lock(hashtext('shengyi_patient_seq'));

-- 取当前最大 patient_id，续号
SELECT patient_id FROM lnrs.lnrs_anon_patient
 WHERE center_code='shengyi' AND patient_id ~ '^PT_[0-9]{8}$'
 ORDER BY patient_id DESC LIMIT 1;
-- max_pt_id = 'PT_008001' → 下个号 = 'PT_008002'（按 SUBSTR + 1 算）
```

patient 表新增字段：
```sql
INSERT INTO lnrs.lnrs_anon_patient
  (patient_id, anon_id, center_code, source_system, source_patient_id,
   created_batch_id, last_seen_batch_id, created_at, updated_at)
VALUES (%s, %s, 'shengyi', 'disk_image_index', %s, %s, %s, now(), now())
ON CONFLICT (anon_id) DO NOTHING  -- 双保险：万一 advisory lock 失效
```

实际 INSERT 字段集需查 `lnrs_anon_patient` 表真实 schema（DDL 在 `0006-anonymized-schema-lnrs.sql`）。

### 2.5 ETL 引擎改动

**零改动**。`_CENTER_PARQUET_SPECS["shengyi"]` 不动；离线路径与 ETL2 引擎并行存在（zhujiang 也是这样）。

---

## 3. 关键决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| patient 缺口策略 | 灌库脚本内同步发号 | FK 强制 + 与现有 ETL2 patient kind 同款 |
| source 命名 | `disk_06_shengyi` / `disk_07_shengyi` | 与 zhujiang `disk1_zhujiang` 模式一致 |
| dicom_study_uid 解析 | record_id 去前缀 | record_id 已天然嵌入 DICOM StudyInstanceUID |
| 落库环境 | dev 本机 | 与本批核验用同一库 + secret 一致 |
| sop_count | 默认 0 | 源数据无 SOP 粒度 |
| patient_added 输出 | `docs/sour/shengyi_imaging_study_patient_added.txt` | 落仓便于审计 |
| 去重策略 | 内存 dedup + `ON CONFLICT DO NOTHING` | 双重保护 |
| ETL2 引擎改动 | 零 | 离线路径与 zhujiang 模式一致 |

---

## 4. 实施步骤

### Step 1：备份（必做）

```bash
mkdir -p backend/.backup
PGPASSWORD=lnrs_pwd pg_dump -h 127.0.0.1 -U lnrs -d postgres \
  -t lnrs.lnrs_anon_patient -t lnrs.lnrs_anon_imaging_study \
  --data-only --rows-per-insert=1000 \
  > backend/.backup/pre_shengyi_imaging_$(date +%Y%m%d_%H%M%S).sql
```

### Step 2：建脚本

- `scripts/build_shengyi_imaging_study_index.py`
- `docs/etl2/verify_shengyi_imaging_study.sql`

### Step 3：dry-run

```bash
cd /home/dzy/wk/lnrs
ENVIRONMENT=dev backend/.venv/bin/python scripts/build_shengyi_imaging_study_index.py --dry-run
```

期望输出：
- parquet rows: 82,994
- distinct record_id: 82,153
- distinct patient_id: 82,988
- reused_patients (anon_id 命中): 306
- patient_to_add: 82,682
- imaging_rows_after_dedup: 82,153
- 预估耗时：~30 秒

### Step 4：正式跑

```bash
cd /home/dzy/wk/lnrs
ENVIRONMENT=dev backend/.venv/bin/python scripts/build_shengyi_imaging_study_index.py
```

期望输出：
- patient_inserted: 82,682（新增 0 跳过）
- imaging_inserted: 82,153（首次跑 ON CONFLICT 0 跳过）
- patient_added 列表写到 `docs/sour/shengyi_imaging_study_patient_added.txt`
- 耗时 < 60 秒

### Step 5：验证

```bash
PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres \
  -f docs/etl2/verify_shengyi_imaging_study.sql
```

期望：
```
shengyi_patients | shengyi_imaging | unique_studies | disk_06_rows | disk_07_rows
       169,820   |        82,153   |        82,153 |       52,340 |       29,813
```

### Step 6：回填核验清单

更新 `docs/etl2/数据导入核验清单.xlsx` 第 2 行：
- E2（完成状态）：`已完成（影像 +82,153 行落 PG；patient +82,682；详见 verify_result/shengyi_CT_image_20260914_after_import.md）`
- F2（核验结果文件路径）：`docs/etl2/verify_result/shengyi_CT_image_20260914_after_import.md`

### Step 7：commit + push

只提交本次新增/修改（用户先前的工作不动）：
- 新增 `scripts/build_shengyi_imaging_study_index.py`
- 新增 `docs/etl2/verify_shengyi_imaging_study.sql`
- 新增 `docs/etl2/plan-shengyi-CT-image-import.md`
- 新增 `docs/sour/shengyi_imaging_study_patient_added.txt`（脚本产物）
- 新增 `docs/etl2/verify_result/shengyi_CT_image_20260914_after_import.md`
- 更新 `docs/etl2/数据导入核验清单.xlsx`

---

## 5. 数字预期对照表

| 阶段 | lnrs_anon_patient (shengyi) | lnrs_anon_imaging_study (shengyi) |
|---|---:|---:|
| 灌库前 | 87,138 | 0 |
| Step 4 后（patient_inserted=82,682 + imaging_inserted=82,153） | **169,820** | **82,153** |
| 重跑（ON CONFLICT DO NOTHING） | 169,820（不变） | 82,153（不变） |

按 source 拆分：

| source | 预期 unique rows |
|---|---:|
| `disk_06_shengyi` | 52,340 |
| `disk_07_shengyi` | 29,813 |
| **合计** | **82,153** |

按 modality 拆分：本批全 `'CT'`，预期 82,153 行 `modality='CT'`。

---

## 6. 风险与缓解

| 风险 | 缓解 |
|---|---|
| patient 续号与 ETL2 引擎并发产生同号 | `pg_advisory_xact_lock` 事务级串行化 + INSERT `ON CONFLICT (anon_id) DO NOTHING` 双保险 |
| dir_path 不存在磁盘但仍 INSERT | 接受；后续由 `lnrs_anon_imaging_orphan` 审计链路捕获（0016 迁移已就绪） |
| record_id 解析不出 DICOM UID | WARNING + skip，已在脚本逻辑中 |
| parquet 物理消失 / 路径移动 | dry-run 前先做文件系统 stat 校验 |
| 重跑产生新批次脏数据 | imaging_study 用 `ON CONFLICT DO NOTHING`；patient 已存在 anon_id 跳过；幂等 |

---

## 7. 后续操作清单

1. ✅ ETL2 spec 不动（本次只走离线路径）
2. ✅ `build_imaging_study_index.py` 不动（zhujiang 路径不受影响）
3. 🆕 新建 `build_shengyi_imaging_study_index.py`
4. 🆕 新建 `verify_shengyi_imaging_study.sql`
5. 🆕 dry-run → 正式跑 → 验证 SQL → 出 after_import 报告
6. 🆕 回填核验清单 + commit + push
7. 📋 后续工单（不在本批次）：h196_3 环境复跑（h196_3 secret 可能不同，单独 secret 取自 `env/.env.h196_3`）

---

## 8. 变更文件清单

| 文件 | 改动 |
|---|---|
| `scripts/build_shengyi_imaging_study_index.py` | 新建（~250 行） |
| `docs/etl2/verify_shengyi_imaging_study.sql` | 新建（~50 行） |
| `docs/etl2/plan-shengyi-CT-image-import.md` | 新建（本文档） |
| `docs/sour/shengyi_imaging_study_patient_added.txt` | 新建（脚本产物，~82k 行） |
| `docs/etl2/verify_result/shengyi_CT_image_20260914_after_import.md` | 新建（核验报告） |
| `docs/etl2/数据导入核验清单.xlsx` | 更新第 2 行 E2/F2 |

**不改动**：
- `backend/app/plugin/module_medical/hospital/anon_etl_engine.py`（_CENTER_PARQUET_SPECS["shengyi"]）
- `scripts/build_imaging_study_index.py`（zhujiang 路径）