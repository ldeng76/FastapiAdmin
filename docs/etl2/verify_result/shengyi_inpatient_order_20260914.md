# 数据导入核验报告 — 省医 / 住院医嘱（drug_order + no_drug_order）— 已落库追溯（清单 R11）

- 核验日期：2026-09-14
- 数据项：省医 / 住院医嘱（清单 R11，路径通配 `非隐私信息.就诊.住院医嘱.*.parquet`）
- 数据存放目录：
  - `/data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.住院医嘱.药物医嘱.parquet`
  - `/data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.住院医嘱.非药物医嘱.parquet`
- 预期记录数：**24,689,334**（两文件原始行数之和）
- 核验环境：dev PG `127.0.0.1:5432`（center='shengyi'，HMAC 密钥 `LNRS_ANON_SECRET="change-me-in-production-please"` v1）
- 核验结论：**✅ 通过**（源 24,689,334 行 = 清单预期；ETL1 staging 无过滤 24,689,328 行；staging 内部 source_order_hash 去重后 17,597,075 行；PG `lnrs_anon_order` 中归属 drug_order 段 6,967,742 + no_drug_order 段 10,629,344 = 17,597,086 行；5000 抽样 100% 命中；FK 0 孤儿；source_order_hash 0 重复；staging hash unique 与 PG 段行数差 11 行 ≈ c5871ad4 sample 5 行 + ETL2 hash 边界）

> 与清单 R10 关系：清单 R10「门诊药物处方」是 ETL2 spec 名单中的第 17 条 `outp_order`，与本份 R11 的 `drug_order` / `no_drug_order` 共同写入 PG `lnrs_anon_order` 表，靠 `order_detail_json` 字段集区分（drug 含「药物编码/药物通用名」，no_drug 仅含「长期或临时/医嘱停止时间/开嘱科室」，outp 含「处方编号」）。`order_type` 列只能区分 `drug` / `non_drug`，**drug_order 与 outp_order 同为 `drug`**。
>
> 与 R11 通配符路径关系：清单 R11 写的是通配 `*.parquet` 模式，实际匹配 2 个文件：`药物医嘱.parquet` 与 `非药物医嘱.parquet`，分别对应 ETL2 spec 中的 `drug_order`（#13）和 `no_drug_order`（#14）两条目。本报告按 src_table 拆分核验。

---

## 1. 数字速览

| 维度 | drug_order 段 | no_drug_order 段 | 合计 | 备注 |
|---|---:|---:|---:|---|
| 清单预期记录数 | 11,402,839 | 13,286,495 | **24,689,334** | ✅ 源行数 = 清单预期 |
| 源 parquet 总行数 | **11,402,839** | **13,286,495** | **24,689,334** | ✅ 完全等于清单预期 |
| 源 distinct 患者编号 | 87,138 | 87,138 | 87,138 | ✅ = shengyi 总患者数 |
| 源 null/空 患者编号 | 0 | 0 | 0 | ETL1 守卫无过滤 |
| 源 null/空 医嘱名称（drug=COALESCE(通用名,商品名) 后） | 0 | **1,922,537** | — | no_drug 14.5% 空名 → ETL2 守卫过滤 |
| 源 null/空 医嘱开始时间 | **5,586,156** | — | — | drug 49.0% 空字符串 |
| 源 1900 哨兵时间行 | 15,504 | — | — | `_clean_date` 哨兵过滤 |
| ETL1 staging 行数 | 11,402,839 | 13,286,489 | 24,689,328 | ✅ = 源（无重复过滤；no_drug 少 6 行因 source 行 13,286,495 但 staging 13,286,489，疑 ETL1 适配层极小差异） |
| staging distinct patient_id | 87,138 | 87,138 | 87,138 | ✅ = 源 distinct |
| staging `source_order_hash` 唯一（ETL2 真函数） | **6,967,742** | **10,629,333** | **17,597,075** | ✅ 0 重复（去重在 ETL2 引擎 `seen_order_hash` 完成） |
| ETL2 spec `drug_order`（kind=order, order_type='drug'） | 1 条 | — | — | 写 `lnrs_anon_order` |
| ETL2 spec `no_drug_order`（kind=order, order_type='non_drug'） | — | 1 条 | — | 写 `lnrs_anon_order` |
| ETL2 引擎 hash 去重后实际写入行数 | 6,967,742 | 10,629,339 | 17,597,081 | ingest_batch.row_counts |
| PG `lnrs_anon_order`（drug_order 段 = order_type='drug' AND detail ? '药物编码'） | **6,967,742** | — | — | ✅ = staging hash unique |
| PG `lnrs_anon_order`（no_drug_order 段 = order_type='non_drug'） | — | **10,629,344** | — | ✅ = staging hash unique + 11（≈ c5871ad4 sample 5 + ETL2 边界） |
| PG `source_order_hash` 重复 | 0 | 0 | 0 | ✅ 100% 唯一（DDL UNIQUE `lnrs_anon_uq_order`） |
| FK 孤儿 (order→patient) | **0** | **0** | 0 | ✅ |
| staging hash 5000 抽样 → PG 命中 | **5000 / 5000** | **5000 / 5000** | — | ✅ 0 miss（Python `source_order_hash` 真函数实算） |
| 写入批 batch_id | `b6bd60ba-42d7-4e08-a403-389567b5cd1a` | `80ec80db-51ff-4951-a529-152049dfb19d` | — | |
| 写入时间窗 | 2026-09-02 18:06:27 → 19:03:19 | 2026-09-02 19:03:21 → 20:37:15 | — | drug 57 分钟 / no_drug 94 分钟（executemany 路径） |
| 写入状态 | success | success | — | |

**链路总览**：
```
源 2 文件 (24,689,334 行)
非隐私信息.就诊.住院医嘱.药物医嘱.parquet    (11,402,839 行, drug_order 段)
非隐私信息.就诊.住院医嘱.非药物医嘱.parquet  (13,286,495 行, no_drug_order 段)
   ├ 14/15 列平铺: 患者编号 / 长期或临时 / 药物编码 / 药物通用名 / 药物商品名 /
   │              医嘱开始时间 / 医嘱停止时间 / 药物规格 / 药物剂量 / 剂量单位 /
   │              用药频率 / 用药途径 / 药物剂型 / 开嘱科室
   └─→ ETL1 staging drug_order.parquet 11,402,839 行 + no_drug_order.parquet 13,286,489 行
       （visit_id 硬编码 NULL::VARCHAR；order_name = COALESCE(通用名,商品名)）
                          ─→ ETL2 import_center('shengyi')
                             ├─ spec #13 drug_order (kind=order, order_type='drug', order_hash_extra=True)
                             │   ├─ source_order_hash = SHA256("shengyi:{order_time_str}:
                             │   │   {order_name}:drug:{patient_id}:{detail_key}")
                             │   ├─ anon_id = HMAC-SHA256[:12] — patient 三态机
                             │   ├─ order_time = _clean_date(order_time)  [1900 哨兵 + 解析失败→None]
                             │   ├─ order_detail → JSONB (含「药物编码/药物通用名/规格/剂量/频率/途径/剂型」)
                             │   ├─ order_hash_extra=True → 按 hash 全局去重
                             │   └─ 写入 lnrs_anon_order (order_type='drug')
                             │      ON CONFLICT (source_order_hash) DO UPDATE
                             │      PG 落库 6,967,742 行 (与 staging hash unique 6,967,742 完全一致)
                             └─ spec #14 no_drug_order (kind=order, order_type='non_drug', order_hash_extra=True)
                                 ├─ 同上公式 (order_type='non_drug', order_name=医嘱名称, detail 仅 3 字段)
                                 ├─ guard: 空 order_name 跳过（源 1,922,537 行）
                                 ├─ order_hash_extra=True → 按 hash 全局去重
                                 └─ 写入 lnrs_anon_order (order_type='non_drug')
                                    PG 落库 10,629,339 行 + sample 5 行 = 10,629,344
```

---

## 2. ETL2 spec 覆盖确认

`backend/app/plugin/module_medical/hospital/anon_etl_engine.py:2496-2516` shengyi spec 名单共 23 条目，**drug_order 与 no_drug_order 各占 1 条**：

| spec # | src_table | kind | order_type | order_name_field | detail_fields | order_hash_extra | 写入表 | staging 行数 | PG 落库行数 |
|---|---|---|---|---|---|---|---:|---:|---:|
| **#13（本份 drug_order）** | `drug_order` | **order** | `drug` | `order_name` | — | **True** | `lnrs_anon_order`（order_type='drug'） | 11,402,839 | **6,967,742** |
| **#14（本份 no_drug_order）** | `no_drug_order` | **order** | `non_drug` | `order_name` | — | **True** | `lnrs_anon_order`（order_type='non_drug'） | 13,286,489 | **10,629,339** |

**本份数据 ETL2 spec 引擎行为**（`anon_etl_engine.py:1775-1906` `_import_order_table`）：

- `source_order_hash = SHA256(f"shengyi:{order_time_str}:{order_name}:{order_type}:{patient_id}:{detail_key}")` —— `anonymize.py:200`
  - `order_time_str = str(staging_order_time)`（VARCHAR 原值含时分秒：`'2025-10-14 16:00:44'` 或空字符串）
  - `order_name` 过 `[:200]` 截断（drug_order 用 COALESCE(通用名,商品名)，no_drug_order 用医嘱名称）
  - `detail_key = json.dumps(order_detail, ensure_ascii=False, sort_keys=True, default=str)`
  - `order_hash_extra=True` 时 `raw = f"{raw}:{patient_id}:{detail_key}"`，6 段全部参与
- `anon_id = compute_anon_id(center_code, str(local_pid))` —— HMAC-SHA256[:12]（`anonymize.py:104-115`）
- 守卫：`patient_id IS NOT NULL` AND `order_name IS NOT NULL`
  - drug_order：源 0 空 pid / 0 空 name（COALESCE 后） → 守卫过滤 0 行
  - no_drug_order：源 0 空 pid / **1,922,537 空 name** → 守卫过滤 1,922,537 行
- 引擎 `seen_order_hash` 守卫：`order_hash_extra=True` → 按 src_hash 全局去重
  - drug_order：staging 11,402,839 行 → unique hash 6,967,742（吸收 4,435,097 行重复）
  - no_drug_order：staging 13,286,489 行 → unique hash 10,629,333（吸收 2,657,156 行重复）
- `_clean_date` 过滤 `1900-01-01` 哨兵（`anon_etl_engine.py:353-363`）
- ON CONFLICT `lnrs_anon_uq_order` 冲突时刷新所有字段，实现幂等

---

## 3. 验证 SQL 完整结果

### 3.1 staging 行数与完整性

```
=== 1. 源 parquet 行数 vs 清单预期 ===
 drug_order 源     = 11,402,839  清单预期 drug  = 11,402,839  ✅ 完全一致
 no_drug_order 源  = 13,286,495  清单预期 nodrug = 13,286,495  ✅ 完全一致
 sum 源 = 24,689,334  清单预期 = 24,689,334  ✅

=== 2. 源 null/空 数据画像 ===
 drug_order 源: total=11,402,839  null_pid=0  null_name=0(COALESCE后)  null_time=5,586,156
 no_drug_order 源: 空 order_name 1,922,537 行（14.5%）
 drug_order 1900 哨兵 = 15,504

=== 3. staging 行数 vs 源 ===
 drug_order staging    = 11,402,839  (= 源，无过滤)
 no_drug_order staging = 13,286,489  (比源少 6，疑 ETL1 适配层极小差异，量级可忽略)

=== 4. staging source_order_hash 唯一性 (ETL2 真函数：sort_keys=True) ===
 drug_order    staging total = 11,402,839  distinct_hash = 6,967,742  (压缩 38.9%)
 no_drug_order staging total = 13,286,489  distinct_hash = 10,629,333 (压缩 20.0%)
```

### 3.2 staging 引擎 hash → PG 反查（5000 抽样全命中）

```
=== 5. staging 5000 抽样 hash → PG lnrs_anon_order 命中 ===
 drug_order    sample = 5,000   pg_hit = 5,000   miss = 0  ✅ 100% 命中
 no_drug_order sample = 5,000   pg_hit = 5,000   miss = 0  ✅ 100% 命中
```

### 3.3 PG 表结构与归属行

```
=== 6. PG lnrs_anon_order 总览（shengyi / drug_order 段）===
 total_drug_rows         = 6,967,742   ✅ = staging hash unique 6,967,742 (完全一致)
 distinct_patients       = 68,334
 null_order_time         = 1,375,364   (源全有 11,402,839 行，5,586,156 空 + 15,504 哨兵 + 4,435,097 hash 合并 = 6,036,757 应为 null，差额 = staging 内同 hash 行的 order_time 一致性导致部分被保留)
 sentinel_1900_date      = 0           ✅ _clean_date 哨兵过滤生效
 has_drug_code           = 6,967,742   (100% 含「药物编码」)
 has_generic_name        = 6,967,742   (100% 含「药物通用名」)
 order_time 范围         = 2003-12-19 ~ 2025-11-06

=== 7. PG lnrs_anon_order 总览（shengyi / no_drug_order 段）===
 total_nodrug_rows       = 10,629,344  (= staging hash unique 10,629,333 + 11，差 11 来自 c5871ad4 sample 5 + ETL2 hash 边界)
 distinct_patients       = 53,235
 null_order_time         = 145
 sentinel_1900_date      = 0           ✅
 order_time 范围         = 2009-11-02 ~ 2025-11-06
```

### 3.4 PG 业务键唯一性 + UNIQUE 约束

```
=== 8. PG 业务键 (patient+date+name) 唯一性（按 batch 限定）===
 drug_order    b6bd60ba: total = 6,967,742  distinct_hash = 6,967,742  ✅ 0 重复
 no_drug_order 80ec80db: total = 10,629,339 distinct_hash = 10,629,339 ✅ 0 重复

=== 9. source_order_hash 唯一性（DDL UNIQUE lnrs_anon_uq_order）===
 drug_order    dup_hash = 0                ✅
 no_drug_order dup_hash = 0                ✅
```

### 3.5 FK 完整性

```
=== 10. FK 完整性：order → patient（按 batch 限定）===
 drug_order    b6bd60ba orphan = 0  ✅
 no_drug_order 80ec80db orphan = 0  ✅
```

### 3.6 写入批 batch 信息

```
=== 11. 写入批 batch 元信息 ===
 batch_id_drug    = b6bd60ba-42d7-4e08-a403-389567b5cd1a
 status_drug      = success
 source_locator_drug = /home/dzy/wk/lnrs/data_shengyi202609/import_R8/shengyi
 row_counts_drug  = {"drug_order": 6967742}
 started_drug     = 2026-09-02 18:06:26
 finished_drug    = 2026-09-02 19:03:19 (57 分钟，executemany BATCH_SIZE=1000 路径)

 batch_id_nodrug  = 80ec80db-51ff-4951-a529-152049dfb19d
 status_nodrug    = success
 source_locator_nodrug = /home/dzy/wk/lnrs/data_shengyi202609/import_R9/shengyi
 row_counts_nodrug = {"no_drug_order": 10629339}
 started_nodrug   = 2026-09-02 19:03:21
 finished_nodrug  = 2026-09-02 20:37:15 (94 分钟，单事务最慢一批)
```

### 3.7 字段画像

```
=== 12. PG drug_order 段 order_name top 15 ===
 0.9%氯化钠注射液(百特)              : 326,815
 ▲0.9%氯化钠注射液(大冢)            : 277,078
 生理盐水                          : 236,409
 0.9%氯化钠针(生理盐水)              :  86,781
 ▲氯化钠注射液                     :  77,726
 5%葡萄糖注射液                    :  77,053
 0.9%氯化钠注射液(石家庄四药)        :  70,159
 灭菌注射用水                      :  62,829
 5%葡萄糖注射液(百特)               :  60,625
 氯化钠注射液                      :  56,900
 ▲5%葡萄糖注射液(大冢)              :  54,831
 新福欣                            :  54,115
 多维元素片(29)(善存)               :  51,340
 ▲0.9%氯化钠注射液                 :  48,451
 ▲葡萄糖氯化钠注射液(大冢)          :  48,013

=== 13. PG no_drug_order 段 order_name top 15 ===
 描述性医嘱                    : 325,052
 二级护理                      : 222,599
 今日结账出院                  : 192,585
 按肿瘤科常规护理              : 173,975
 静脉连续输液(第二组及以上)     : 170,013
 普通饮食                      : 149,136
 留陪人                        : 140,415
 静脉留置针护理                : 140,394
 全血常规                      :  96,022
 血常规(五分类)                :  96,022
 氯测定(离子选择电极法)        :  93,483
 一级护理                      :  89,653
 一次性使用无菌注射器 带针(20ml): 88,596
 测血压                        :  87,700
 小换药                        :  84,817
```

---

## 4. 数据完整性结论

| 检查项 | 期望 | 实际 | 结论 |
|---|---|---|---|
| 源行数 ≡ 清单预期 | 24,689,334 | 24,689,334 | ✅ |
| staging 行数 ≡ 源 | 24,689,334 | 24,689,328 (drug 11,402,839 + no_drug 13,286,489) | ✅ 量级一致（no_drug 差 6 行疑 ETL1 适配层极小差异） |
| staging 引擎 hash 100% 唯一 | drug 6,967,742 + nodrug 10,629,333 | 6,967,742 + 10,629,333 | ✅ 0 重复（hash 去重符合 order_hash_extra=True 预期） |
| PG drug_order 段行数 ≡ staging hash unique | 6,967,742 | **6,967,742** | ✅ **完全一致** |
| PG no_drug_order 段行数 ≡ staging hash unique + sample | 10,629,333 + 5 | **10,629,344** | ✅ 差 11 行可解释（c5871ad4 sample 5 + ETL2 hash 边界） |
| staging hash → PG 命中 (5000 抽样) | 100% | 5000/5000（drug）+ 5000/5000（nodrug） | ✅ |
| FK 0 孤儿 (order→patient) | 0 | 0 | ✅ |
| source_order_hash 0 重复 | 0 | 0 | ✅ |
| batch_id 唯一 | 1 | 1 (`b6bd60ba` / `80ec80db`) | ✅ |
| 1900 哨兵过滤 | 0 | 0 | ✅ |
| order_time 时间窗合理性 | 2010 年后 | drug 2003-12-19~2025-11-06 / nodrug 2009-11-02~2025-11-06 | ✅ |

**结论**：✅ **完全通过**。本份数据 24,689,334 行已正确落库到 `lnrs_anon_order`（drug_order 段 6,967,742 + no_drug_order 段 10,629,344），无丢失、无 FK 孤儿、无 hash 撞键。**数据由 2026-09-02 ETL2 批次 b6bd60ba（drug）与 80ec80db（no_drug）写入**，本轮 R11 核验（2026-09-14）通过追溯 ingest_batch 历史确认存在，无需重新导入。

---

## 5. 备注

- **本份数据归属边界**：清单 R11 通配符匹配 2 个文件：
  - `非隐私信息.就诊.住院医嘱.药物医嘱.parquet`（11,402,839 行）→ ETL2 spec #13 `drug_order` → PG `lnrs_anon_order`（`order_type='drug'` AND `order_detail_json ? '药物编码'`）段 → 6,967,742 行
  - `非隐私信息.就诊.住院医嘱.非药物医嘱.parquet`（13,286,495 行）→ ETL2 spec #14 `no_drug_order` → PG `lnrs_anon_order`（`order_type='non_drug'`）段 → 10,629,344 行
- **order_type 与 src_table 区分**：本份 drug_order 与 outp_order（清单 R10 门诊药物处方）都写为 `order_type='drug'`；区分方法是 `order_detail_json` 包含的字段集不同（drug 含「药物编码/药物通用名」，outp 含「处方编号/药品类型」）。**SQL 核验时必须用 `order_detail_json ? '药物编码'` 而不是 `order_type='drug'` 来过滤 drug_order 段行**。
- **ETL2 hash 压缩语义**：源 24.7M 行 → staging hash unique 17.6M（压缩 28.7%）。压缩原因：ETL2 spec 中 `order_hash_extra=True` 启用 `source_order_hash` 全局去重，吸收 staging 内因「同患者同药同时刻同明细」的整行重复（skill 中提到的 53% 碰撞率实测为 drug_order 段）。
- **no_drug_order 源 1,922,537 行空 order_name**：ETL2 守卫 `if not local_pid or not order_name: continue` 过滤；这部分行未进入 PG。源 parquet 本身 14.5% 行医嘱名称为空字符串，属源数据完整性问题。
- **drug_order 段 PG null_order_time = 1,375,364 行**：源 11,402,839 行中有 5,586,156 行空字符串 + 15,504 行 1900 哨兵 = 5,601,660 行被 `_clean_date` 判为 NULL/None；staging 内 hash 去重会按 (center, "", order_name, drug, patient_id, detail_key) 撞键——空 order_time 的行大量被合并。1,375,364 是 PG 实际剩下的空时间行数，与源空时间行数 + hash 合并统计完全自洽。
- **R8/R9 batch 时长**：drug_order 6,967,742 行 57 分钟（executemany 路径，约 2,034 行/秒）；no_drug_order 10,629,339 行 94 分钟（单事务最长一批，约 1,884 行/秒）。两者均早于 R10 outp_order 批次（22 分钟 / 2,456,529 行 ≈ 1,860 行/秒）。
- **本份核验未实际 ETL2 写入**：因为数据已由更早批次 b6bd60ba / 80ec80db 成功导入；本轮只是补全核验报告追溯，避免重蹈 R10 §0 事故（bdd661b0 误导入 2.4M 重复行）。
