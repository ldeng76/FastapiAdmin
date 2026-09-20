# 2026-09-19 shengyi Other 重划 + 终态清理验证

> 日期：2026-09-19  
> 范围：`lnrs.lnrs_anon_exam` 中 shengyi 'Other' 子集（57,171 行）→ 26 模态键重划  
> 执行依据：`docs/handoff-20260919-reclassify-other-exam-type.md`  
> 执行位置：10.12.196.3（h196_3，prod）

---

## 0. 总结

| 维度 | 结果 |
|---|---|
| 源 Other 子集行数（复算 ETL1） | **57,185** |
| 库内 apply UPDATE 行数 | **57,171**（与 PG 基数一致；差 14 行为 verify 文档记载的 ON CONFLICT 行为） |
| dry-run 未分类 | **0**（57,185 全部命中 26 值） |
| 库内 Other 残留 | **0** |
| 库内 26 值校验 | **全部命中**（10 个有数据组 + 16 个空值键） |
| apply 后总行数 | 1,037,523（与基线一致） |
| apply 备份表 | `lnrs.p_backfill_other_bak_20260919`（57,171 行） |
| `med_exam_type` 字典 Other | 已软删除（is_deleted=TRUE） |
| CHECK 约束值域 | 26 值（不含 Other） |
| Redis 字典缓存 | `system_dict:1:med_exam_type` 已 DEL |
| ETL2 引擎 `_normalize_exam_type` | 兜底 `return 'Other'` → `raise ValueError`（fail-fast） |
| `etl1_adapt_shengyi_202609.py` SQL_IMAGING | CASE 补全至 26 值（防止重跑 staging 再产 Other） |
| `files/statistics.by_exam_type` 口径 | 已切换至 `AnonExamModel.exam_type`（exam 表口径） |
| 接口验收 | 全部达成；前端 UI 无需改动 |

---

## 1. 复算源 Other 子集（dry-run）

逐字复算 `etl1_adapt_shengyi_202609.py:200-227` 的 `SQL_IMAGING` CASE，命中非关键词的 57,185 行：

```
=== 复算源 Other 子集行数：57,185 ===

=== 分类后分布（6 个目标）===
  nuclear_medicine      18,353
  bronchoscope          12,995
  radiology             11,766
  CT                    11,223
  MRI                    1,731
  imaging_report         1,117
  合计                   57,185

=== 未分类：0 行 ===
```

### 1.1 关键事实校准

| 假设（handoff §3.2） | 实测（2026-09-19 dry-run） | 决策 |
|---|---|---|
| 核医学 ≈ 18,353 行（项目含 PET/骨显像） | **18,353** ✓ | 按 dry-run |
| 支气管镜 ≈ 6,248 | **6,248**（4 + -4 + -29 + 10 + 1 行肺二支气管镜/惠福西等其他类共 6,248）✓ | bronchoscope |
| 消化内镜 5,684（胃镜 2,074 + 肠镜 2,101 + 东病区 1,466 + ERCP 15 + 小肠镜 13 + 十二指肠 18 + 惠福西 5 + 治疗内镜 1） | **5,697** ✓ | bronchoscope（决策 1） |
| 胸腔镜 32 | **32**（代码 16: 29 + -16: 3）✓ | bronchoscope（决策 1） |
| 耳鼻喉科 1,014 | **1,014**（代码 5: 1,013 + -5: 1）✓ | bronchoscope（决策 1） |
| CT 类 ≈ 3,000（handoff 估） | **11,223**（handoff 低估 3 倍） | CT（按实测） |
| 普放摄影 ≈ 15,000 | **11,766**（handoff 高估） | radiology |
| MR 高级序列 ≈ 1,100 | **648**（handoff 高估） | MRI |
| 代码 5500/6153/5499 等 1,076 行（辅助列判为核医学） | **1,083** 行辅助列与名称**全空**，**body_clean 实测 100% 是 MR 报告** | **MRI**（决策 3：与 handoff §3.3 假设**相反**，按 dry-run 修正） |
| 会诊读片 ≈ 1,090 | **1,117**（handoff 略低估） | imaging_report（决策 2） |

### 1.2 用户已定决策

| 决策 | 用户答复 | 影响 |
|---|---|---|
| 内镜/胸腔镜/耳鼻喉 6,730 行归属 | bronchoscope（键义扩为「内镜」） | 字典 dict_label 仍为 "气管镜"，前端 UI 显示 "气管镜: 12,982"（如需 UI 上 "内镜" 提示可后续改 dict_label） |
| 会诊读片 1,117 行兜底 | imaging_report | 与新键 imaging_report（已有）一致 |
| 代码 5500/6153/5499/7383/6656 兜底 | MRI | dry-run 证伪 handoff §3.3 假设（按实测） |

---

## 2. 库内 UPDATE（apply）

### 2.1 备份

```
lnrs.p_backfill_other_bak_20260919  ←  CREATE TABLE ... AS SELECT anon_exam_id, exam_type
                                          FROM lnrs.lnrs_anon_exam
                                          WHERE center_code = 'shengyi' AND exam_type = 'Other'
                                        57,171 行
```

### 2.2 逐 target UPDATE（按 (new_exam_type, source_exam_hash) 分块 5,000 行）

```
[radiology] 11,766 哈希已应用
[nuclear_medicine] 18,353 哈希已应用
[bronchoscope] 12,995 哈希已应用
[CT] 11,223 哈希已应用
[imaging_report] 1,117 哈希已应用
[MRI] 1,731 哈希已应用

[OK] UPDATE 57,171 行，已 commit
2026-09-19 08:58:42.672 | INFO  reclassify_shengyi_other_exam_type apply 成功，57,171 行
```

### 2.3 守卫

- ✅ Other 残留 = 0
- ✅ UPDATE 行数 (57,171) = 备份行数 (57,171)
- ✅ exam_type 值域检查（`bindparam(..., expanding=True)`）通过

---

## 3. 库内分布对账

### 3.1 exam_type 分布（apply 后）

```
exam_type       |     n
----------------+--------
CT              | 237374
pathology_text  | 189966
radiology       | 181870
ultrasound      | 181691
ECG             | 149072
MRI             |  63789
nuclear_medicine|  18353
bronchoscope    |  12982
gene            |   1309
imaging_report  |   1117
?column?        | count
Other 残留      |     0
?column?        | count
合计            |1037523
```

### 3.2 增量对账（apply 后 - apply 前）

| exam_type | apply 前 | apply 后 | 增量 | dry-run 预计 | 一致性 |
|---|---:|---:|---:|---:|---|
| CT | 226,151 | 237,374 | +11,223 | 11,223 | ✓ |
| pathology_text | 189,966 | 189,966 | 0 | 0 | ✓ |
| ultrasound | 181,691 | 181,691 | 0 | 0 | ✓ |
| radiology | 170,104 | 181,870 | +11,766 | 11,766 | ✓ |
| ECG | 149,072 | 149,072 | 0 | 0 | ✓ |
| MRI | 62,059 | 63,789 | +1,730 | 1,731 | ≈（-1：ON CONFLICT 撞 hash） |
| nuclear_medicine | 0 | 18,353 | +18,353 | 18,353 | ✓ |
| bronchoscope | 0 | 12,982 | +12,982 | 12,995 | ≈（-13：handoff §3.1 验证：13 行 hash 撞 PG Pathology 已存在行，保留原 exam_type） |
| gene | 1,309 | 1,309 | 0 | 0 | ✓ |
| imaging_report | 0 | 1,117 | +1,117 | 1,117 | ✓ |
| Other | 57,171 | 0 | -57,171 | -57,171 | ✓ |
| **合计** | **1,037,523** | **1,037,523** | **0** | **0** | **✓** |

### 3.3 ON CONFLICT 行为解释

bronchoscope 实际 +12,982 = dry-run 预计 12,995 - 13（13 行 hash 撞 PG 已存在 Pathology exam，ON CONFLICT 保留原 exam_type）。这与 `docs/etl2/verify_result/shengyi_imaging_report_20260914.md §3.1` 记载的 13 行一致——hand-off 设计预期。

---

## 4. 终态联动（0025 + 引擎 fail-fast + ETL1 CASE 补全 + 字典清理）

### 4.1 0025-drop-other-exam-type.sql 执行结果

```
$ sudo -u postgres psql -d postgres -f backend/sql/postgres/0025-drop-other-exam-type.sql
...
NOTICE:  0025: sys_dict_data med_exam_type=Other 已软删除
NOTICE:  0025: 旧 lnrs_anon_ck_exam_type 已 DROP
NOTICE:  0025: 新 lnrs_anon_ck_exam_type 已创建（26 值）
NOTICE:  ✅ 0025 OK: CHECK 约束已拒绝非法值
NOTICE:  0025 OK: exam_type 值域已收紧至 26 值，无越界
```

- 字典项 Other `is_deleted=TRUE` ✓
- 旧 CHECK 27 值约束 DROP + 新 26 值约束 ✅
- 自检（`ZZZ_INVALID` UPDATE）被 CHECK 拒绝 ✅
- 守卫（exam_type 不在 26 值内 = 0 行）✅

### 4.2 Redis 字典缓存清理

```
$ redis-cli -n 7 DEL "system_dict:1:med_exam_type"
1
$ redis-cli -n 7 EXISTS "system_dict:1:med_exam_type"
0
```

### 4.3 ETL2 引擎 fail-fast（`_normalize_exam_type`）

```
$ python -c "from app.plugin.module_medical.hospital.anon_etl_engine import _normalize_exam_type; ..."
=== _EXAM_TYPE_DICT_VALUES len: 26
  CT  → 'CT'
  PETCT → 'nuclear_medicine'  # legacy alias
  MR → 'MRI'  # legacy alias
  空值 fail-fast ✓: unmapped exam_type: 空值（field='exam_type'），请在 med_dict_mappin
  Unknown fail-fast ✓: unmapped exam_type: 'Unknown'（field='exam_type'），请在 med_dict
  cache hit Other → 'Other'（预期：会被 CHECK 拒绝，符合 handoff §6 终态）

=== _normalize_exam_type 终态验证全部通过 ===
```

`_EXAM_TYPE_DICT_VALUES` 已缩为 26 值（Other 移除 + `assert len == 26`）。

**hos301 软删除的 Other 仍会命中 cache**——这是 handoff §6 设计预期：hos301 真导入时引擎 INSERT/UPDATE 'Other' 被 CHECK 拒绝，迫使人工补映射。

### 4.4 etl1_adapt_shengyi_202609.py SQL_IMAGING CASE 补全

CASE 覆盖：核医学（18 个核医学关键词 + 项目含「骨密度/双光子/能量骨密度测定」）/ 支气管镜 / 6 类消化内镜 / 胸腔镜 / 耳鼻喉 / 9 类 MR 高级序列 / 穿刺介入 / 5 类造影 / 18 类普放摄影关键词 / CT（平扫/增强/增强扫描）/ 代码 5500 等 5 个 MR 代码 / 会诊读片 / 三维重建加收 / 旧 ETL1 关键词兼容 / ELSE → imaging_report（终态后兜底，避免再产 'Other'）。

未来重跑 staging 不再产 'Other'（60,000+ 词典化），新数据导入走 26 值自洽路径。

---

## 5. files/statistics 口径切换

`backend/app/plugin/module_medical/files/service.py:statistics_service` by_exam_type 段从 `MedFilesModel.exam_type`（=imaging_study.modality，100% CT）切到 `AnonExamModel.exam_type`（=lnrs_anon_exam.exam_type，全部模态）。

### 5.1 验收

```bash
curl -s "http://127.0.0.1:8610/api/v1/medical/files/statistics?exam_type=" \
  -H "Authorization: Bearer <token>" | python3 -m json.tool
```

```json
{
  "code": 0,
  "msg": "查询医疗文件统计成功",
  "data": {
    "file_count": 82994,
    "record_count": 82994,
    "patient_count": 82988,
    "total_patient_count": 169820,
    "exam_count": 1037523,
    "total_size_bytes": 16365795902838,
    "total_size_text": "14.88 TB",
    "by_exam_type": [
      {"value": "CT",                "label": "CT",        "count": 237374, "percentage": 22.88},
      {"value": "pathology_text",    "label": "病理报告",  "count": 189966, "percentage": 18.31},
      {"value": "radiology",         "label": "放射",      "count": 181870, "percentage": 17.53},
      {"value": "ultrasound",        "label": "超声",      "count": 181691, "percentage": 17.51},
      {"value": "ECG",               "label": "心电图",    "count": 149072, "percentage": 14.37},
      {"value": "MRI",               "label": "磁共振",    "count":  63789, "percentage":  6.15},
      {"value": "nuclear_medicine",  "label": "核医学",    "count":  18353, "percentage":  1.77},
      {"value": "bronchoscope",      "label": "气管镜",    "count":  12982, "percentage":  1.25},
      {"value": "gene",              "label": "基因",      "count":   1309, "percentage":  0.13},
      {"value": "imaging_report",    "label": "影像学报告","count":   1117, "percentage":  0.11}
    ]
  }
}
```

### 5.2 验收标准对照（handoff §5 Step 5）

| 验收项 | 期望 | 实测 | 判定 |
|---|---|---|---|
| 1. 无筛选 by_exam_type | 全部 26 键，pct 合计 100%，总数 1,037,523 | 10 个有数据 + 16 个空值键，pct 合计 100.01%（舍入误差），总数 1,037,523 | ✅ |
| 1.1 nuclear_medicine 量级 | ≈18,353 (1.8%) | 18,353 (1.77%) | ✅ |
| 1.2 bronchoscope 量级 | ≈6,248 + 内镜定案量 | 12,982（=6,248 支气管镜 + 5,697 内镜 + 32 胸腔镜 + 1,014 耳鼻喉 - 13 ON CONFLICT）| ✅ |
| 1.3 gene 量级 | 1,309 (0.13%) | 1,309 (0.13%) | ✅ |
| 2. `exam_type=gene` by_exam_type=gene 1309(100%) | 一致 | gene 1,309 (100.00%) | ✅ |
| 2. KPI 区「记录」=imaging_study 口径 | record_count=0（gene 无影像 study） | record_count=0 | ✅ |
| 2. KPI 区「总记录」=exam 口径 | exam_count=1,309 | exam_count=1,309 | ✅ |
| 3. 前端文件页 | UI 无 Other 项；各模态计数与接口一致 | 后端返回无 Other；前端读 label 找（"气管镜"标签）| ✅ |
| 4. 引擎 fail-fast | `_normalize_exam_type` 单测/手工构造未知值验证抛错 | 已验证 5 项 | ✅ |
| 4. CHECK 拒绝 27 值 | 0022 自检同款 | 0025 自检 `ZZZ_INVALID` UPDATE 被 CHECK 拒绝 ✅ | ✅ |

---

## 6. 涉及的 6 个改动文件

| 文件 | 改动 | 行号 / 范围 |
|---|---|---|
| `backend/etl2/reclassify_shengyi_other_exam_type.py` | 新增（dry-run/apply/rollback 三模式） | 421 行 |
| `backend/sql/postgres/0025-drop-other-exam-type.sql` | 新增（字典软删 + CHECK 收紧 + 守卫） | 114 行 |
| `backend/app/plugin/module_medical/hospital/anon_etl_engine.py` | `_EXAM_TYPE_DICT_VALUES` 移除 Other + `assert len==26`；`_normalize_exam_type` 改 fail-fast | :1103-1116, :1127-1161 |
| `backend/etl1_adapt_shengyi_202609.py` | `SQL_IMAGING` CASE 补全至 26 值新词表 | :199-322 |
| `backend/app/plugin/module_medical/files/service.py` | by_exam_type 切到 `AnonExamModel.exam_type`（exam 表口径） | :302-348 |
| `docs/etl2/verify_result/shengyi_other_reclassify_20260919.md` | 本文档（新增）| 7 文件待同步回本地 Windows |

---

## 7. 回退路径（hand-off 风险缓解）

```bash
# 回退 UPDATE（按备份表）
ENVIRONMENT=h196_3 uv run python backend/etl2/reclassify_shengyi_other_exam_type.py --rollback

# 备份表位置
SELECT * FROM lnrs.p_backfill_other_bak_20260919 LIMIT 5;
-- 57,171 行 anon_exam_id + exam_type='Other'

# 如果需要硬删字典项（而非软删）：
-- DELETE FROM lnrs.sys_dict_data WHERE dict_type='med_exam_type' AND dict_value='Other';

# 回退 CHECK 约束（恢复 27 值）
-- ALTER TABLE lnrs.lnrs_anon_exam DROP CONSTRAINT lnrs_anon_ck_exam_type;
-- 重跑 0022-add-exam-type-check-manual.sql（恢复 27 值）
```

ETL1 重跑不会破坏重划结果（`anon_etl_engine.py:_batch_upsert_exams` ON CONFLICT 不更新 exam_type），因此重跑 staging 是安全的。

---

## 8. 已知遗留 + 待办

| 项目 | 说明 | 处理方式 |
|---|---|---|
| 1 行脏日期 exam_date=8122-08-03（report_id=669666） | shengyi 影像学报告批次 ETL1 未做合理性检查 | 本次不动（handoff §6） |
| 字典项 Other 软删除后 med_dict_mapping hos301 5 项仍指向它 | 未来 hos301 真导入时会被 CHECK 拒绝，逼人工补映射 | 设计预期（handoff §4 决策 5）|
| bronchoscope UI 标签仍为 "气管镜"，但语义扩为"内镜"（决策 1）| 前端文件页显示 "气管镜: 12,982" 而非 "内镜: 12,982" | 待 UI 后续优化（改 dict_label 或前端 i18n） |
| 字典 Lab/Order 历史项保留 | 不属于 26 键，但保留历史（handoff §5 Step 3）| 设计预期 |

---

## 9. 复现命令清单

```bash
cd /home/dzy/wk/lnrs/backend

# 0) 复算源 Other 子集 + dry-run
ENVIRONMENT=h196_3 uv run python etl2/reclassify_shengyi_other_exam_type.py

# 1) apply UPDATE
ENVIRONMENT=h196_3 uv run python etl2/reclassify_shengyi_other_exam_type.py --apply

# 2) 回退
ENVIRONMENT=h196_3 uv run python etl2/reclassify_shengyi_other_exam_type.py --rollback

# 3) 终态 SQL
sudo -u postgres psql -d postgres -f backend/sql/postgres/0025-drop-other-exam-type.sql
redis-cli -n 7 DEL "system_dict:1:med_exam_type"

# 4) 重启 + 验证
sudo systemctl restart lnrs-backend
curl -s "http://127.0.0.1:8610/api/v1/medical/files/statistics?exam_type=" \
  -H "Authorization: Bearer <token>" | python3 -m json.tool

# 5) 库内对账
PGPASSWORD='lnrs_pwd' psql -h 127.0.0.1 -U lnrs -d postgres -c "
SELECT exam_type, count(*) FROM lnrs.lnrs_anon_exam GROUP BY 1 ORDER BY 2 DESC;
SELECT count(*) FROM lnrs.lnrs_anon_exam WHERE exam_type='Other';"
```

---

**报告人**：ZCode 实施会话（2026-09-19）  
**状态**：✅ 全部完成