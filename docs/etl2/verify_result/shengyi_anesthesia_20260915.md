# 数据导入核验报告 — 省医 / 麻醉信息(anesthesia) — 清单 R19

- 核验日期：2026-09-15
- 数据项：省医 / 麻醉信息（清单 R19，第 2 个【完成状态】为空的行）
- 数据存放目录：`/data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.麻醉信息.*.parquet`（glob 通配，对应 2 个文件）
- 预期记录数：**3,326,029**（源 2 个 parquet 行数和 = 子项记录 2,981,080 + 用药记录 344,949）
- 核验环境：dev PG `127.0.0.1:5432`（center='shengyi'）
- 核验结论：**✅ 已完成（2 个 ETL2 spec 完全对账）**
  - `anesthesia_observation`（子项记录）：ETL1 staging 2,981,080 → ETL2 守卫过滤 -4,861（item_name 空）→ ETL2 去重 -18,811 → PG `lnrs_anon_vital_observation(obs_type='anesthesia')` = **2,957,408 行**（= R15 batch.row_counts 完全一致）
  - `anesthesia_order`（用药记录）：ETL1 staging 344,949 → ETL2 守卫过滤 -3,719（PID/order_name 空）→ ETL2 去重 -17,285 → PG `lnrs_anon_order`（R10 内麻醉部分）= **323,945 行**（= R10 batch.row_counts.anesthesia_order 完全一致）
  - 200 抽样 staging→PG：observation 200/200 = 100%；order 200/200 = 100%
  - staging ⊆ PG：observation 2,957,408/2,957,408 = 100%；order 323,945/323,945 = 100%
  - source_obs_hash / source_order_hash 唯一性 100%
  - FK 完整性（patient_id）：0 孤儿 ✅

> 麻醉信息是清单中唯一跨 **两个 ETL2 spec**（observation + order）的复合项，且 R10 batch 同时跑了 anesthesia_order + outp_order，R15 batch 同时跑了 anesthesia_observation + icu_observation。本报告分别独立核验。

---

## 0. 数字速览

### 0.1 anesthesia_observation (子项记录)

| 维度 | 值 | 备注 |
|---|---:|---|
| 清单预期 | (含在 R19 总数 3,326,029) | — |
| 源 parquet 行数 | 2,981,080 | `非隐私信息.就诊.麻醉信息.子项记录.parquet` |
| ETL1 staging `anesthesia_observation.parquet` 行数 | 2,981,080 | ✅ = 源（0 守卫过滤） |
| staging null `patient_id` | 0 | ✅ 0 过滤 |
| staging null/empty `item_name` | 4,861 | ETL2 引擎守卫过滤（**item_name 必填**） |
| ETL2 引擎守卫后行数 | 2,976,219 | 2,981,080 - 4,861 |
| ETL2 引擎 `source_obs_hash` 去重后 | 2,957,408 | -18,811 重复 |
| ETL2 batch `2367dd54-...` `row_counts.anesthesia_observation` | **2,957,408** | ✅ 完全一致 |
| **PG `lnrs_anon_vital_observation` (obs_type=anesthesia, shengyi) 行数** | **2,957,408** | ✅ V1 |
| staging ⊆ PG (hash 集合) | 2,957,408 / 2,957,408 = **100.00%** | ✅ |
| 抽样 SHA256 (200) → PG 命中 | **200 / 200 = 100%** | ✅ |
| source_obs_hash 唯一性 (R15 麻醉) | 2,957,408 = uniq | ✅ V3 |
| `anon_visit_id` 填充 | **0 行 / 2,957,408 = 0%** | staging 中 visit_id 全空，ETL2 走 no-visit 路径，符合预期 |
| `item_name` / `item_result` / `item_result_value` / `obs_time` / `obs_detail_json` nonnull | 2,957,408 (100%) | ✅ V1 |
| `item_unit` nonnull | 2,938,833 (99.36%) | 18,575 行 item_unit 为空（ETL1 source 部分无单位）|
| uniq `patient_id` (R15 麻醉) | **14,580** | 占 shengyi patient 总数 169,820 的 8.6% |
| FK 完整性 (R15 麻醉 ↔ patient) | 0 孤儿 | ✅ V5b |
| obs_time 范围 | 2019-02-19 10:25:00 ~ 2025-10-13 11:35:00 | V1 |
| `obs_detail_json` 顶层键 | 1 个（`detail`）| ETL2 detail_fields=["detail"] 包装 |
| `obs_detail_json->detail` 子键 | 9 个全填充 | 实施手术名称 / 体重(kg) / 麻醉开始时间 / 麻醉结束时间 / 手术开始时间 / 手术结束时间 / 入室时间 / 出室时间 / ASA分级 |

### 0.2 anesthesia_order (用药记录)

| 维度 | 值 | 备注 |
|---|---:|---|
| 清单预期 | (含在 R19 总数 3,326,029) | — |
| 源 parquet 行数 | 344,949 | `非隐私信息.就诊.麻醉信息.用药记录.parquet` |
| ETL1 staging `anesthesia_order.parquet` 行数 | 344,949 | ✅ = 源（0 守卫过滤） |
| staging null/empty `patient_id` | 0 | ✅ 0 过滤 |
| staging null/empty `order_name` | 3,719 | ETL2 引擎守卫过滤 |
| ETL2 引擎守卫后行数 | 341,230 | 344,949 - 3,719 |
| ETL2 引擎 `source_order_hash` (含 order_hash_extra=True) 去重后 | 323,945 | -17,285 重复 |
| ETL2 batch `56ec3bef-...` `row_counts.anesthesia_order` | **323,945** | ✅ 完全一致 |
| **PG `lnrs_anon_order` (R10 内 anesthesia_order 部分) 行数** | **323,945** | ✅ V2 (R10 全 2,780,474 = outp_order 2,456,529 + anesthesia_order 323,945) |
| staging ⊆ PG (hash 集合) | 323,945 / 323,945 = **100.00%** | ✅ |
| 抽样 SHA256 (200) → PG 命中 | **200 / 200 = 100%** | ✅ |
| source_order_hash 唯一性 (R10 全量) | 2,780,474 = uniq | ✅ V3b |
| R10 order uniq `patient_id` (含麻醉+门诊) | **42,477** | R10 整个 batch（order 共用） |
| uniq `order_name` (R10 全部药物类) | 4,061 | V6 |
| `order_detail_json` 键分布 | 20 个键：10 个麻醉专属键 (323,945) + 10 个门诊专属键 (2,456,529) | V8 |
| `anon_visit_id` 填充 | **0 行 / 2,780,474 = 0%** | R10 全部 order 都未填 visit_id（麻醉与门诊都属此类，源端 visit_id 为空） |

### 0.3 整体对账

| 维度 | 源 | ETL1 staging | ETL2 守卫 | ETL2 去重 | PG 落库 | 与 batch.row_counts 一致 |
|---|---:|---:|---:|---:|---:|:---:|
| anesthesia_observation | 2,981,080 | 2,981,080 | 2,976,219 (-4,861) | 2,957,408 (-18,811) | **2,957,408** | ✅ |
| anesthesia_order | 344,949 | 344,949 | 341,230 (-3,719) | 323,945 (-17,285) | **323,945** | ✅ |
| **合计** | **3,326,029** | **3,326,029** | **3,317,449 (-8,580)** | **3,281,353 (-36,096)** | **3,281,353** | ✅ |
| 清单 R19 预期 | **3,326,029** | — | — | — | 3,281,353 = 源 - 8.1% 守卫/去重过滤 | — |

> 3,326,029 → 3,281,353 共过滤 **44,676 行**（1.34%）：8,580 行守卫过滤（PID/order_name/item_name 空）+ 36,096 行 ETL2 引擎内去重（同 patient 同药同时间的整行重复，源端 ETL1 staging 按就诊展开导致）。

---

## 1. ETL 流程说明

### 1.1 源 → ETL1 staging → ETL2 PG

```
源 parquet（清单 R19）：
  /data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/
    非隐私信息.就诊.麻醉信息.子项记录.parquet   2,981,080 行  (清单 glob 第 1 个)
    非隐私信息.就诊.麻醉信息.用药记录.parquet     344,949 行  (清单 glob 第 2 个)
    ─────────────────────────────────────────────────
    小计 (清单 R19 预期 3,326,029)                3,326,029 行  ✅ 完全一致
                ↓ ETL1 SQL_ANESTHESIA + sql_order_anesthesia
ETL1 staging:
  /home/dzy/wk/lnrs/data_shengyi202609/shengyi/
    anesthesia_observation.parquet  2,981,080 行  (8 列: patient_id, visit_id, item_name,
                    item_result, item_result_value, item_unit, obs_time,
                    detail STRUCT(9 键))
    anesthesia_order.parquet          344,949 行  (5 列: patient_id, visit_id, order_name,
                    order_time, order_detail STRUCT(10 键))
                ↓ ETL2 _import_observation_table (kind=observation, obs_type=anesthesia)
                ↓ 守卫: patient_id 非空 AND item_name 非空 (-4,861)
                ↓ 去重: source_observation_hash(center, 'anesthesia', pid, vid, item_name,
                                                result, value, unit, time_iso) (-18,811)
                ↓ 批量 upsert lnrs_anon_vital_observation
                ↓ 同 R15 batch 跑 icu_observation
PG (lnrs.lnrs_anon_vital_observation, obs_type='anesthesia', center='shengyi'):
  2,957,408 行  (= R15 batch.row_counts.anesthesia_observation)

                ↓ ETL2 _import_order_table (kind=order, order_type='drug', order_hash_extra=True)
                ↓ 守卫: patient_id 非空 AND order_name 非空 (-3,719)
                ↓ 去重: source_order_hash(center, time, name, type, patient_id=pid, detail_key) (-17,285)
                ↓ 批量 upsert lnrs_anon_order
                ↓ 同 R10 batch 跑 outp_order
PG (lnrs.lnrs_anon_order, order_type='drug', created_batch_id='56ec3bef...'):
  麻醉部分 323,945 行 + 门诊部分 2,456,529 行 = R10 batch 2,780,474 行
```

### 1.2 关键代码引用

- ETL1 staging SQL:
  - `backend/etl1_adapt_shengyi_202609.py:760-779` `SQL_ANESTHESIA` (子项记录)
  - `backend/etl1_adapt_shengyi_202609.py:636-655` `sql_order_anesthesia()` (用药记录)
- ETL2 spec 配置: `backend/app/plugin/module_medical/hospital/anon_etl_engine.py:2513-2517, 2542-2545`
  - `{"src_table": "anesthesia_order", "kind": "order", "order_type": "drug", "order_name_field": "order_name", "order_hash_extra": True}`
  - `{"src_table": "anesthesia_observation", "kind": "observation", "obs_type": "anesthesia", "detail_fields": ["detail"]}`
- ETL2 engine:
  - `_import_observation_table`: `anon_etl_engine.py:2252-2388`
    - 守卫：`if not local_pid or not item_name: continue`
    - 去重：`source_observation_hash(center, obs_type, pid, vid, item_name, result, value, unit, time_iso)`
    - 截断：`item_name[:255]`, `item_result[:255]`, `item_unit[:64]`
  - `_import_order_table`: `anon_etl_engine.py:1775-1906`
    - 守卫：`if not local_pid or not order_name: continue`
    - 去重：`source_order_hash(center, order_time_str, name, order_type, patient_id=pid, detail_key=json.dumps(order_detail, sort_keys=True))`（因 `order_hash_extra=True`）
    - 截断：`order_name[:200]`
- ETL2 hash:
  - `backend/app/plugin/module_medical/hospital/anonymize.py`:
    - `source_observation_hash` (8 元组 SHA256)
    - `source_order_hash` (6 元组 SHA256，order_hash_extra 时含 patient_id + detail_key)

### 1.3 ingest_batch 时间线

| batch_id | locator | status | row_counts | started_at | finished_at | 麻醉部分 PG |
|---|---|---|---|---|---|---:|
| `56ec3bef-...` | `import_R10/shengyi` | success | `{outp_order: 2,456,529, anesthesia_order: 323,945}` | 2026-09-02 20:37:17 | 2026-09-02 21:04:51 | **323,945** |
| `2367dd54-...` | `import_R15/shengyi` | success | `{icu_observation: 1,679,556, anesthesia_observation: 2,957,408}` | 2026-09-04 05:07:43 | 2026-09-04 05:43:48 | **2,957,408** |

> R10 batch 共跑 27 分钟（R10 是 order 大批，包含 2,456,529 门诊用药 + 323,945 麻醉用药），R15 共跑 36 分钟（含 ICU + 麻醉观察 4,636,964 行）。

---

## 2. PG 端概览

### 2.1 V1 vital_observation(obs_type=anesthesia, shengyi)

```
pg_rows            = 2,957,408
nonnull_item       = 2,957,408 (100%)
nonnull_result     = 2,957,408 (100%)
nonnull_value      = 2,957,408 (100%)
nonnull_unit       = 2,938,833 (99.36%)
nonnull_time       = 2,957,408 (100%)
nonnull_detail     = 2,957,408 (100%)
has_visit (anon_visit_id NOT NULL) = 0 (0%)
null_visit                          = 2,957,408 (100%)
obs_time 范围 2019-02-19 10:25:00 ~ 2025-10-13 11:35:00
```

### 2.2 V2 order(R10 batch)

```
R10 总 = 2,780,474 行 (全部 order_type='drug')
其中 outp_order 部分: 2,456,529 行 (10 个门诊专属 JSON 键)
其中 anesthesia_order 部分: 323,945 行 (10 个麻醉专属 JSON 键)
```

### 2.3 V3 hash 唯一性

```
source_obs_hash (R15 麻醉):    2,957,408 / 2,957,408 = 100%
source_order_hash (R10 全量):  2,780,474 / 2,780,474 = 100%
```

### 2.4 V5a/b/c unique patient + FK

```
R15 anesthesia obs uniq_pt       = 14,580
R15 anesthesia obs FK patient    = 0 孤儿 (全部 2,957,408 行都能在 lnrs_anon_patient 找到)
R10 order uniq_pt (含麻醉+门诊)   = 42,477
```

### 2.5 V7/V7b obs_detail_json 键分布

```
顶层键: detail (2,957,408)
detail 子键（9 键，每个都有 2,957,408 行）:
  实施手术名称 / 体重（kg）/ 麻醉开始时间 / 麻醉结束时间 /
  手术开始时间 / 手术结束时间 / 入室时间 / 出室时间 / ASA分级
```

### 2.6 V8 order_detail_json 键分布（R10 batch）

```
10 个麻醉专属键（各 323,945 行）:
  麻醉结束时间 / 体重（kg）/ 麻醉开始时间 / 手术结束时间 /
  术中用药剂量 / ASA分级 / 入室时间 / 出室时间 / 手术开始时间 / 实施手术名称
10 个门诊专属键（各 2,456,529 行）:
  处方编号 / 药品类型 / 开立医生签名 / 处方开立科室名称 / 药物剂型 /
  用药天数 / 药物使用频次 / 药物使用次剂量 / 用药途径名称 / 药物规格
合计 20 个 JSON 键，与 ETL1 SQL_ANESTHESIA(10) + sql_order_outp(10) 完美对应
```

---

## 3. 完整性核验汇总

| 检查项 | anesthesia_observation | anesthesia_order |
|---|---|---|
| ETL1 staging 行数 = 源 | ✅ 2,981,080 = 2,981,080 | ✅ 344,949 = 344,949 |
| ETL2 引擎守卫后行数 | 2,976,219 | 341,230 |
| ETL2 引擎去重后行数 | 2,957,408 | 323,945 |
| PG 落库 = batch.row_counts | ✅ 2,957,408 = 2,957,408 | ✅ 323,945 = 323,945 |
| 源合计 = 清单 R19 预期 | ✅ 3,326,029 = 3,326,029 | |
| hash 唯一性 | ✅ 100% | ✅ 100% |
| staging ⊆ PG (反向覆盖) | ✅ 100.00% | ✅ 100.00% |
| 200 抽样 staging→PG | ✅ 200/200 | ✅ 200/200 |
| FK 完整性 (patient_id) | ✅ 0 孤儿 | (order 表无 FK 约束) |
| 字段填充 | item/result/value/time/detail 100%, unit 99.36% | — |
| `anon_visit_id` 填充 | 0% (符合预期, 源 visit_id 全空) | 0% (符合预期, R10 共用, 源 visit_id 全空) |
| obs_time 范围 | 2019-02-19 ~ 2025-10-13 | — |

---

## 4. 200 抽样核验（Python 端）

```python
random.seed(20260915)

# anesthesia_observation: 从 staging 2,976,219 守卫通过集合抽 200
sample_obs = random.sample(staging_guard_pass_obs, 200)
# 计算 source_observation_hash, 在 PG R15 batch 2,957,408 hash 中查
hit_obs = 200 / 200 = 100%  ✅

# anesthesia_order: 从 staging 341,230 守卫通过集合抽 200
sample_order = random.sample(staging_guard_pass_order, 200)
# 计算 source_order_hash(extra=True), 在 PG R10 batch 2,780,474 hash 中查
hit_order = 200 / 200 = 100%  ✅
```

---

## 5. 结论与建议

### 5.1 通过项 ✅

- ETL2 引擎已成功落库 **3,281,353 行**（2,957,408 obs + 323,945 order），与 `ingest_batch.row_counts` 报告值**完全一致**
- 源 3,326,029 行 = 清单 R19 预期 3,326,029 ✅ **完全一致**
- ETL1 staging 行数 = 源 parquet 行数（0 守卫过滤）✅
- ETL2 引擎守卫过滤 + 去重后行数 = batch.row_counts ✅
- 200 抽样 100% 命中 (observation + order 两个 spec 都 100%) ✅
- staging ⊆ PG = 100.00%（observation + order 两个 spec 都 100%）✅
- source_obs_hash / source_order_hash 唯一性 100% ✅
- FK 完整性（patient_id）0 孤儿（observation 部分用 PG JOIN 验证）✅
- 字段填充率（item/result/value/time/detail）100% ✅
- obs_detail_json 与 order_detail_json 完整保留源端 detail struct 所有键 ✅

### 5.2 通过项但需注意 ⚠️

- **filter 行数（44,676 行 / 1.34%）来源**：
  - 守卫过滤 8,580 行（item_name 空 4,861 + order_name 空 3,719）— 这些是 staging 中真实无效行，引擎按 spec 跳过，符合预期
  - 去重过滤 36,096 行 — 同一 (patient, time, drug) 整行重复（staging 按就诊展开导致），ETL2 引擎通过 `source_order_hash` (含 patient_id + detail_key) 精准去重，无副作用
- **`anon_visit_id` 100% 为空**：源 staging 中 visit_id 全空（清单 R19 注释也未要求），ETL2 引擎走 no-visit 路径，符合 spec
- **`item_unit` 99.36% 填充**：18,575 行 unit 为空，源端未提供单位

### 5.3 建议

1. **【清单完善】R19 可考虑改为两行**：当前 R19 把"麻醉信息"作为一行（glob 路径 + 总行数 3,326,029），但 ETL2 实际是两个独立 spec（observation + order），PG 落点也不同（vital_observation vs order）。建议拆为"R19a 麻醉子项记录"和"R19b 麻醉用药记录"两行分别跟踪。
2. **【源端优化】visit_id 全空**：源 staging 中麻醉子项 / 用药记录的 visit_id 全空，ETL2 引擎无法关联 visit。若需后续按 visit 维度分析（如按 visit 聚合麻醉事件），建议 ETL1 阶段尝试从 visit.parquet 反查（参考 `etl1_adapt_shengyi_202609.py:481-546` `SQL_SURGERY` 中 `from_surgery` 的 join 模式）。

### 5.4 最终结论

> ✅ **已完成**
>
> 麻醉信息数据（清单 R19）跨 2 个 ETL2 spec 全部完美对账：
> - `anesthesia_observation` → 2,957,408 行（= 清单子项记录 2,981,080 经 4,861 守卫 + 18,811 去重过滤）
> - `anesthesia_order` → 323,945 行（= 清单用药记录 344,949 经 3,719 守卫 + 17,285 去重过滤）
> - 合计 3,281,353 行 = 源 3,326,029 行 - 44,676 行 ETL2 引擎守卫/去重过滤
>
> 200 抽样 100% 命中，staging ⊆ PG 100%，hash 唯一性 100%，FK 完整性 0 孤儿。所有核验维度均通过。

---

## 6. 核验 SQL 与脚本

- SQL: `docs/etl2/verify_result/verify_anesthesia.sql`
- Python 抽样验证：内嵌于本报告 §4（Python + duckdb + psycopg 直连 dev PG）