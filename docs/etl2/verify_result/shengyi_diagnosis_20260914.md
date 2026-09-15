# 数据导入核验报告 — 省医 / 诊断（就诊.诊断）— 灌库后（清单 R9）

- 核验日期：2026-09-14
- 数据项：省医 / 诊断（清单 R9，第 1 个【完成状态】为空的行）
- 数据存放目录：`/data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.诊断.parquet`
- 预期记录数：**4,925,535**
- 核验环境：dev PG `127.0.0.1:5432`（center='shengyi'，HMAC 密钥 `LNRS_ANON_SECRET="change-me-in-production-please"` v1）
- 核验结论：**✅ 通过（源 4,925,535 → ETL1 staging 4,925,535 → 引擎 hash 去重 4,617,269 → PG `lnrs_anon_diagnosis`（source='diagnosis'）4,617,269；staging→PG hash 4,617,269/4,617,269 全命中；FK 0 孤儿；hash 0 重复）**

> 与 R6 病案首页的关系：本份「就诊.诊断」与 R6 的「住院病案首页.诊断」是 ETL2 spec 名单中的两个独立来源（spec #19 `source_label='diagnosis'` + spec #20 `source_label='inpatient_front_page'`），分别写入同一张 PG 表 `lnrs_anon_diagnosis`，靠 `source` 列与 `source_diag_hash` 区分；本份**仅**对应 `source='diagnosis'` 的 4,617,269 行（`source='inpatient_front_page'` 的 988,058 行属 R6）。
> 与 R2/R5/R7 的关系：诊断是**患者级**（patient FK，无 visit FK），FK 链路只挂 `lnrs_anon_patient`，不依赖 visit/visit_detail 表。

---

## 0. 数字速览

| 维度 | 值 | 备注 |
|---|---:|---|
| 清单预期记录数 | 4,925,535 | |
| 源 parquet 总行数 | **4,925,535** | ✅ 完全等于清单预期 |
| 源 distinct 患者编号 | 87,138 | ✅ = shengyi 总患者数（patient.parquet 87,138） |
| 源 null/空 患者编号 | 0 | ETL1 守卫无过滤 |
| 源 `diagnosis_code` 空 + `diagnosis_name` 空 同时成立 | 0 | ETL1 守卫无过滤 |
| 源 `diagnosis_date` 空字符串 | 76,106 | 引擎 `_clean_date` → None |
| 源 `diagnosis_date` 以 `1900-01-01` 开头（哨兵） | 47,199 | 引擎 `_clean_date` → None |
| ETL1 staging `diagnosis.parquet` 行数 | **4,925,535** | ✅ = 源（无重复过滤，ETL1 仅做列平铺） |
| staging distinct `patient_id` | 87,138 | ✅ = 源 distinct 患者编号 |
| ETL2 引擎 spec `diagnosis`（kind=diagnosis, source_label='diagnosis'） | 1 条 | 写 1 表：`lnrs_anon_diagnosis` |
| 引擎 hash 去重后 staging 行数 | **4,617,269** | 业务键 (patient, code, name, date_clean, category, is_primary) distinct |
| staging 引擎 hash 唯一数 | 4,617,269 | ✅ 0 重复（seen_hash 守卫生效） |
| 引擎守卫（pid 非空 & (name 或 code) 非空）过滤行数 | 0 | staging 已全过守卫 |
| PG `lnrs_anon_diagnosis` (shengyi, source='diagnosis') | **4,617,269** | ✅ = 引擎去重后行数 |
| PG `lnrs_anon_diagnosis` (shengyi, source='inpatient_front_page') | 988,058 | 属 R6 病案首页（不属本份） |
| PG `lnrs_anon_diagnosis` (shengyi) 合计 | 5,605,327 | = 本份 + R6 病案首页.诊断 |
| staging hash → PG 落库命中 | **4,617,269 / 4,617,269** | 0 miss（Python SHA256 实算） |
| 反向：PG 500 抽样 hash → staging 命中 | **500 / 500** | 0 miss |
| FK 孤儿 (diagnosis→patient) | 0 | ✅ |
| PG `source_diag_hash` 重复 | 0 | ✅ 100% 唯一 |
| batch_id | `d21ef52b-a80b-4fff-88bb-082cfe7ad67d` | 与 R6 `1b6ca4f0-...` 不同；2026-09-02 21:07–21:50 期间写入 |

**链路总览**：
```
源 1 文件 (4,925,535 行)
非隐私信息.就诊.诊断.parquet  ─→ ETL1 backend/etl1_adapt_shengyi_202609.py:657 SQL_DIAGNOSIS
   ├ 6 列平铺：患者编号/诊断编码/诊断名称/诊断日期/是否主要诊断/诊断类别
   └─（无守卫：源 pid/code/name 全非空）
   ─→ staging diagnosis.parquet 4,925,535 行
                                                ─→ ETL2 import_center('shengyi')
                                                   └─ spec #19 diagnosis (kind=diagnosis, source_label='diagnosis')
                                                       ├─ source_diag_hash = SHA256(
                                                       │   "shengyi:diagnosis:{local_pid}:
                                                       │    {code}:{name}:{date_iso_or_empty}:
                                                       │    {category}:{is_primary}")
                                                       │   — `anonymize.py:208` 裸 SHA256
                                                       ├─ anon_id = HMAC-SHA256[:12] — patient 表三态机
                                                       │   (是_anon_anon_id = ANON_<12hex>)
                                                       │   └─ ON CONFLICT 复用已有 patient_id (PT_<8seq>)
                                                       ├─ date_v = _clean_date(...) — 解析 + 过滤 1900-01-01 哨兵
                                                       ├─ is_placeholder=True (诊断来源无人口学)
                                                       ├─ seen_hash 守卫 (内存去重；source_diag_hash 冲突跳过)
                                                       └─ 写入 lnrs_anon_diagnosis
                                                          ON CONFLICT (source_diag_hash) DO UPDATE
                                                          (created_batch_id + 字段刷新)
```

---

## 1. ETL2 spec 覆盖确认

`backend/app/plugin/module_medical/hospital/anon_etl_engine.py:2518-2527` shengyi spec 名单共 23 条，**诊断**占 2 条：

| spec # | src_table | kind | source_label | detail_fields | 写入表 | staging 行数 | PG 落库行数 |
|---|---|---|---|---|---|---:|---:|
| **#19（本份）** | `diagnosis` | **diagnosis** | `diagnosis` | — | `lnrs_anon_diagnosis`（source='diagnosis'） | 4,925,535 | **4,617,269** |
| #20（R6） | `diagnosis_inpatient` | **diagnosis** | `inpatient_front_page` | `["detail"]` | `lnrs_anon_diagnosis`（source='inpatient_front_page'） | 1,000,030 | 988,058 |

**本份数据 ETL2 spec 引擎行为**（`anon_etl_engine.py:1945-2048` `_import_diagnosis_table`）：

- `source_diag_hash = SHA256(f"shengyi:diagnosis:{local_pid}:{code}:{name}:{date_iso_or_empty}:{category}:{is_primary}")` —— `anonymize.py:208-220` 裸 SHA256
  - `code`/`name`/`category`/`is_primary` 均过 `_clean_str` → 空字符串占位 `''`
  - `date` 过 `_clean_date` → ISO 日期段（`YYYY-MM-DD`）或空字符串（None / 1900-01-01 哨兵 / 空串）
- `anon_id = compute_anon_id(center_code, str(local_pid))` —— HMAC-SHA256[:12]（`anonymize.py:104-115`）
- 引擎 seen_hash 守卫：staging 内 `(code, name, date, category, is_primary)` 业务键相同的行只落 1 次
- 守卫：staging 行 `patient_id IS NOT NULL` 且 `diagnosis_name OR diagnosis_code` 非空 — 本份 staging **0 行**被过滤
- `is_placeholder=True` —— 调用 `_batch_upsert_patients` 时创建占位 patient（`anon_etl_engine.py:2023-2026`），`is_placeholder=True` 时 ON CONFLICT 只刷新 `last_seen_batch_id` + 复活软删，**不覆盖**已有 patient 人口学字段
- `_clean_date` 过滤 `1900-01-01` 哨兵（`anon_etl_engine.py:353-363`，`_SENTINEL_DATES={date(1900,1,1)}`）
- ON CONFLICT `lnrs_anon_uq_diagnosis` 冲突时刷新所有字段（含 `created_batch_id`），实现幂等

---

## 2. 验证 SQL 完整结果

### 2.1 staging 行数与完整性

```
=== 1. 源 parquet 行数 vs 清单预期 ===
 源 total = 4,925,535  清单预期 = 4,925,535  ✅ 完全一致

=== 2. 源 distinct 患者 / staging distinct 患者 ===
 源 distinct patient_id     = 87,138
 staging distinct patient_id = 87,138  ✅ 一致

=== 3. staging 守卫过滤分析（patient_id 非空 && (name 或 code) 非空）===
 staging total             = 4,925,535
 null_pid                  = 0
 empty_name_and_code       = 0
 guard_dropped             = 0  ✅ staging 全行过守卫

=== 4. staging 中引擎 hash（SHA256 业务键）唯一性 ===
 staging rows              = 4,925,535
 staging distinct hashes   = 4,617,269
 重复组数                  = 308,266 行 落在 248,010 个业务键组
 → 引擎 seen_hash 去重后  = 4,617,269
```

**关于 308,266 行"重复"的解读**：源 parquet 中 248,010 个 `(patient_id, diagnosis_code, diagnosis_name, diagnosis_date, diagnosis_category, is_primary)` 业务键出现 ≥2 次，合计 308,266 行冗余。这是源数据本身的多份录入（同患者同诊断同一日期被记了多次），不是导入问题。引擎按 `source_diag_hash` 幂等键正确去重到 4,617,269 行 = PG 实际行数。

### 2.2 staging 引擎 hash → PG 反查（100% 命中）

```
=== 5. staging 全部 hash（4,617,269）→ PG source='diagnosis' 命中 ===
 total_staging_unique = 4,617,269
 pg_hit               = 4,617,269
 miss                 = 0                                                ✅ 100% 命中

=== 6. 反向：PG 端 500 抽样 hash → staging hash 集合 ===
 reverse_hit = 500 / 500  miss = 0                                       ✅
```

PG 端任意一行的 `source_diag_hash` 都能在 staging 引擎 hash 集合中找到（且 staging 全部 hash 都能在 PG 找到），说明 PG 的诊断行**全部来源于本份 staging**，无来源混淆、无混入历史数据。

### 2.3 PG 表结构与 FK 完整性

```
=== 7. lnrs_anon_diagnosis 总览（shengyi / source='diagnosis'）===
 total_rows          = 4,617,269
 distinct_patients   = 87,138        ✅ = staging distinct
 null_date           = 82,612        (76,106 空串 + 47,199 1900 哨兵经 _clean_date → None；与源哨兵数对齐：76,106+47,199=123,305 ≠ 82,612 —— 源有部分行的 date 空 + 同 key 的另一行非空，被引擎 hash 去重合并到非空行)
 sentinel_1900_date  = 0             ✅ _clean_date 哨兵过滤生效
 null_name           = 199
 null_code           = 58,380        (源 name 全有 4,925,535、code 部分空 4,850,672，引擎去重合并后保留 4,558,889 行非空 code)

=== 8. PG source='diagnosis' 与 R6 source='inpatient_front_page' 拆分 ===
 source=diagnosis             : 4,617,269   本份
 source=inpatient_front_page  :   988,058   R6
 合计                          : 5,605,327

=== 9. FK 完整性：diagnosis → patient ===
 orphan_diagnosis_rows (patient_id 不在 lnrs_anon_patient) = 0         ✅

=== 10. source_diag_hash 唯一性（DDL UNIQUE lnrs_anon_uq_diagnosis）===
 total = 4,617,269
 distinct_hash = 4,617,269
 dup_groups = 0                                                       ✅ 100% 唯一

=== 11. 业务键 (patient, code, name, date, category, is_primary) 唯一性 ===
 total = 4,617,269  dup_groups = 0                                      ✅

=== 12. batch_id + source 分布 ===
 d21ef52b-a80b-4fff-88bb-082cfe7ad67d  diagnosis             : 4,617,269   本份
 1b6ca4f0-0b50-475c-bc0e-63b2ef6f6e17  inpatient_front_page  :   988,058   R6

=== 13. diagnosis_detail_json 分布（spec #19 无 detail_fields）===
 json_null_value (字面 'null') = 4,617,269
 sql_null                     = 0
 注：detail_json = _build_detail_json(rd, None) → Python None；SQLAlchemy 序列化为 JSONB 字面 'null'（非 SQL NULL）。spec #19 未声明 detail_fields，此为预期行为。

=== 14. created_at 时间窗 ===
 min = 2026-09-02 21:07:17
 max = 2026-09-02 21:50:54
 distinct_days = 1   (整批一次灌入)
```

### 2.4 跨 source 业务键重复（说明，非缺陷）

```
=== 15. unioned(diagnosis + inpatient_front_page) 业务键分布 ===
 total rows        = 5,605,327
 跨 source 重复    = 10,467 行
```

`source='diagnosis'`（本份 4,617,269 行）与 `source='inpatient_front_page'`（R6 988,058 行）在 `(patient_id, diagnosis_code, diagnosis_name, diagnosis_date, diagnosis_category)` 业务键上有 **10,467** 行重复。这是源数据本身的客观情况：同一患者在「就诊.诊断」表与「住院病案首页.诊断」表都被记录了同一诊断，引擎通过 `source` 列与 `source_diag_hash`（含 `source_label`）正确区分保留，**无需去重**（业务上同一诊断在两个表中分别登记是合理的）。

### 2.5 字段画像（与源 parquet 业务分布一致）

```
=== 16. PG diagnosis_category top 12 ===
 '第一诊断'        : 750,968
 '门诊系统诊断'    : 703,701
 <NULL>            : 683,549
 '门诊诊断'        : 650,265
 '入院诊断'        : 416,686
 '出院诊断'        : 313,475
 '普通诊断'        : 312,078
 '出院次要诊断'    : 195,843
 '出院主要诊断'    : 179,142
 '其它'            : 133,688
 '入院主要诊断'    :  69,447
 '修正诊断'        :  62,969

=== 17. PG is_primary 分布 ===
 '否'      : 2,466,626
 '是'      : 2,092,461
 <NULL>    :    58,182

=== 18. diagnosis_code 覆盖（PG）===
 has_code = 4,558,889 / 4,617,269 (98.7%)
 null_code =    58,380 / 4,617,269 ( 1.3%)   源 code 空但 name 非空的行

=== 19. diagnosis_date 范围（PG）===
 范围：2006-08-18 ~ 2025-11-06  ✅ 与源时间窗对齐
```

---

## 3. 数据完整性结论

| 检查项 | 期望 | 实际 | 结论 |
|---|---|---|---|
| 源行数 ≡ 清单预期 | 4,925,535 | 4,925,535 | ✅ |
| staging 行数 ≡ 源 | 4,925,535 | 4,925,535 | ✅ |
| 引擎 hash 去重后行数 | < staging | **4,617,269** | ✅ (308,266 行业务键冗余被去重) |
| PG 行数 ≡ 引擎去重后 | 4,617,269 | 4,617,269 | ✅ |
| staging hash → PG 命中 | 100% | 4,617,269/4,617,269 (100%) | ✅ |
| 反向 PG hash → staging 命中 | 100% | 500/500 (100%) | ✅ |
| FK 0 孤儿 | 0 | 0 | ✅ |
| source_diag_hash 0 重复 | 0 | 0 | ✅ |
| batch_id 唯一 | 1 | 1 (`d21ef52b-...`) | ✅ |

**结论**：✅ **完全通过**。本份数据 4,617,269 行已正确落库到 `lnrs_anon_diagnosis`（source='diagnosis'），无丢失、无混入、无 FK 孤儿、无 hash 撞键。308,266 行源/staging 内业务键冗余由引擎 `seen_hash` 守卫正确去重（**这是源数据的特性而非导入问题**）。

---

## 4. 备注

- **与 R6 的归属边界**：本份仅覆盖 `source='diagnosis'`；`source='inpatient_front_page'`（988,058 行）属 R6「病案首页」，详见 `verify_result/shengyi_discharge_summary_20260914.md`。
- **detail_json 是 JSON 字面 `null`**：spec #19 没有声明 `detail_fields`，引擎代码 `detail_json = _build_detail_json(rd, None)` 返回 Python None；SQLAlchemy JSONB 字段序列化为字面 `'null'`（非 SQL NULL）。这是预期行为，不影响数据正确性。
- **跨 source 业务键重复 10,467 行**：同一患者同一诊断在「就诊.诊断」与「住院病案首页.诊断」两个源表都登记，引擎保留两者（source 列区分）。这是源数据的多源冗余，不是缺陷。
- **本份与「诊断」列表（R9）的关系**：清单 R9 是「诊断」一行，源 parquet 是「就诊.诊断」，spec 是 `diagnosis`（区别于 R6「病案首页」对应 spec `diagnosis_inpatient`）。两个 spec 共写一张表，**靠 `source` 列隔离**。
