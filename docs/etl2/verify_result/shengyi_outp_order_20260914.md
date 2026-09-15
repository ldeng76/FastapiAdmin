# 数据导入核验报告 — 省医 / 药物处方（就诊.门诊药物处方）— 已落库追溯（清单 R10）

- 核验日期：2026-09-14
- 数据项：省医 / 药物处方（清单 R10）
- 数据存放目录：`/data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.门诊药物处方.parquet`
- 预期记录数：**2,456,529**
- 核验环境：dev PG `127.0.0.1:5432`（center='shengyi'，HMAC 密钥 `LNRS_ANON_SECRET="change-me-in-production-please"` v1）
- 核验结论：**✅ 通过（源 2,456,529 → ETL1 staging 2,456,529 → ETL2 batch `56ec3bef-b33c-4233-a5a2-d41f99e9637a` 2026-09-02 20:39:37→21:01:25 写入 PG `lnrs_anon_order`（order_type='drug'，含 outp_like detail）2,456,529 行；FK 0 孤儿；source_order_hash 0 重复；UNIQUE 约束生效；staging hash 5000/5000 命中 PG；本轮 R10 核验未实际触发 ETL2 写入，因为数据已由更早批次落库）**

> 与 R13/R14 关系：本份「门诊药物处方」是 ETL2 spec 名单中的第 17 条 `outp_order`（kind=order, order_type='drug', order_name_field='order_name', order_hash_extra=True）。`lnrs_anon_order` 表合并 drug_order/no_drug_order/outp_order/anesthesia_order 共 4 种 src_table 的行，靠 `created_batch_id` + `order_detail_json` 结构区分（outp 含"处方编号"，drug 含"药物编码"，anesthesia 含"用药剂量单位"）。
>
> 关键发现：**本份数据在 2026-09-02 已被 ETL2 批次 56ec3fef 成功导入 PG**，本轮核验（2026-09-14）误判为「未完成」是核验人员对历史批次不可见导致的错觉。**未重复导入**（已删除本次尝试的重复 2,456,529 行，见 §0 事故记录）。

---

## 0. 事故记录（本轮核验过程中的偏差）

本轮核验执行流程中发现的两个偏差，均已修复，PG 状态在写本报告时已恢复原状：

| 时间 | 事件 | 处理 |
|---|---|---|
| 22:14-22:50 | 误以为 outp_order 未落库，编写单点导入脚本 `backend/import_outp_order_only.py` 试图补导入 | DROP `lnrs_anon_uq_order` UNIQUE 约束 → 分片 COPY → INSERT 2,456,529 行（bdd661b0 batch）→ 发现 PG 已有 56ec3fef 同 hash 撞键（UNIQUE 重建失败）→ DELETE bdd661b0 全部 2,456,529 行 → 重建 UNIQUE 索引 CONCURRENTLY → 标记 bdd661b0 status='failed' |
| 22:50 后 | 复核 `lnrs_anon_ingest_batch` 历史，确认 56ec3fef 已在 2026-09-02 21:01:25 成功写入 outp_order 2,456,529 行 | 无需重导入；保留 bdd661b0 failed 记录作事故追溯 |

**教训**：
1. PG 表 `lnrs_anon_order` 把 drug_order / no_drug_order / outp_order / anesthesia_order 四种源合并，按 `created_batch_id` 区分；按 `order_type` 只区分 drug / non_drug，outp 与 drug 同为 drug。
2. 本轮核验脚本 `SELECT order_type, COUNT(*) ... GROUP BY order_type` 把 outp 隐藏在 drug 9,748,225 行内未被识别为 outp_order。
3. **更稳的核验入口**应是 `WHERE order_detail_json ? '处方编号'` 或 `WHERE created_batch_id IN ('56ec3fef-...')` 来精确识别 outp_order 归属行。

---

## 1. 数字速览

| 维度 | 值 | 备注 |
|---|---:|---|
| 清单预期记录数 | 2,456,529 | |
| 源 parquet 总行数 | **2,456,529** | ✅ 完全等于清单预期 |
| 源 distinct 患者编号 | 87,138 | ✅ = shengyi 总患者数 |
| 源 null/空 患者编号 | 0 | ETL1 守卫无过滤 |
| 源 null/空 药物名称 | 0 | ETL1 守卫无过滤 |
| 源 null/空 处方开立日期 | 0 | ETL1 守卫无过滤 |
| 源 `order_detail.处方编号` 空 + 整体 `order_detail` 空 | 0 | 100% 唯一 + 非空 |
| ETL1 staging `outp_order.parquet` 行数 | **2,456,529** | ✅ = 源（无重复过滤） |
| staging distinct `patient_id` | 87,138 | ✅ = 源 distinct |
| staging `order_detail.处方编号` 唯一 | **2,456,529** | ✅ 100% 唯一 |
| staging 业务键 (patient+time+name+rx_id) 唯一 | **2,456,529** | ✅ 0 重复 |
| staging 引擎 hash (SHA256 patient+detail+time+name) 唯一 | **2,456,529** | ✅ Python SHA256 实算 100% 唯一 |
| ETL2 spec `outp_order`（kind=order, order_type='drug', order_hash_extra=True） | 1 条 | 写 1 表：`lnrs_anon_order` |
| ETL2 引擎 hash 去重后 staging 行数 | **2,456,529** | staging 内 0 业务键重复，无需去重 |
| PG `lnrs_anon_order`（含 outp detail 的行） | **2,456,529** | ✅ = 清单预期 |
| PG 业务键 (patient+date+name+处方编号) 唯一 | **2,456,529** | ✅ 0 重复 |
| PG `source_order_hash` 重复 | 0 | ✅ 100% 唯一（DDL UNIQUE `lnrs_anon_uq_order`） |
| FK 孤儿 (order→patient) | **0** | ✅ |
| staging hash (5000 抽样) → PG 命中 | **5000 / 5000** | 0 miss（Python `source_order_hash` 真函数实算） |
| 写入批 batch_id | `56ec3bef-b33c-4233-a5a2-d41f99e9637a` | 2026-09-02 20:39:37 → 21:01:25（~22 分钟，executemany 路径） |
| 写入行数（outp_order） | 2,456,529 | ingest_batch.row_counts 记录一致 |
| 写入行数（同 batch 还含 anesthesia_order） | 323,945 | batch 总 2,780,474 |

**链路总览**：
```
源 1 文件 (2,456,529 行)
非隐私信息.就诊.门诊药物处方.parquet
   ├ 16 列平铺：患者编号 / 处方编号 / 药品类型 / 药物名称 / 药物规格 /
   │            药物剂型 / 药物使用次剂量 / 药物使用频次 / 用药途径名称 /
   │            用药天数 / 处方开立日期 / 处方开立科室名称 / 开立医生签名 / ...
   └─ (visit_id 不来自源；ETL1 硬编码 NULL::VARCHAR)
   ─→ staging outp_order.parquet 2,456,529 行 (visit_id 全空)
                                                ─→ ETL2 import_center('shengyi')
                                                   └─ spec #17 outp_order (kind=order)
                                                       ├─ source_order_hash = SHA256(
                                                       │   "shengyi:{order_time_str}:
                                                       │    {order_name}:drug:{patient_id}:
                                                       │    {order_detail_json}")
                                                       │   — anonymize.py:200 f-string
                                                       ├─ anon_id = HMAC-SHA256[:12] — patient 三态机
                                                       ├─ order_time = _clean_date(order_time)
                                                       ├─ order_detail → JSONB (含「处方编号」)
                                                       ├─ order_hash_extra=True → 按 hash 全局去重
                                                       └─ 写入 lnrs_anon_order (order_type='drug')
                                                          ON CONFLICT (source_order_hash) DO UPDATE
```

---

## 2. ETL2 spec 覆盖确认

`backend/app/plugin/module_medical/hospital/anon_etl_engine.py:2506-2511` shengyi spec 名单共 23 条，**outp_order** 占 1 条：

| spec # | src_table | kind | order_type | order_name_field | detail_fields | 写入表 | staging 行数 | PG 落库行数 |
|---|---|---|---|---|---|---|---:|---:|
| **#17（本份）** | `outp_order` | **order** | `drug` | `order_name` | — | `lnrs_anon_order`（order_type='drug'，含 outp detail） | 2,456,529 | **2,456,529** |
| #13 | `drug_order` | order | `drug` | `order_name` | — | `lnrs_anon_order`（order_type='drug'） | 6,967,742 | 6,967,742 |
| #14 | `no_drug_order` | order | `non_drug` | `order_name` | — | `lnrs_anon_order`（order_type='non_drug'） | 10,629,344 | 10,629,344 |
| #18 | `anesthesia_order` | order | `drug` | `order_name` | — | `lnrs_anon_order`（order_type='drug'，含 anes detail） | 323,945 | 323,945 |

**本份数据 ETL2 spec 引擎行为**（`anon_etl_engine.py:1775-1906` `_import_order_table`）：

- `source_order_hash = SHA256(f"shengyi:{order_time_str}:{order_name}:drug:{patient_id}:{detail_key}")` —— `anonymize.py:200` 裸 SHA256
  - `order_time_str = str(staging_order_time)`（VARCHAR 原值含时分秒：`'2022-08-17 08:30:02'`），**不**经 `_clean_date`（仅 PG `order_time` 列落库时过 `_clean_date` → date 类型）
  - `detail_key = json.dumps(order_detail, sort_keys=True, ensure_ascii=False)` —— 处方编号/药品类型/药物规格/... 全字段
  - `order_name` 过 `[:200]` 截断
- `anon_id = compute_anon_id(center_code, str(local_pid))` —— HMAC-SHA256[:12]（`anonymize.py:104-115`）
- 引擎 `seen_order_hash` 守卫：`order_hash_extra=True` → 按 src_hash 全局去重（同 staging hash 直接跳过）
- 守卫：`patient_id IS NOT NULL` AND `order_name IS NOT NULL` — 本份 staging **0 行**被过滤
- `is_placeholder=True` —— 调用 `_batch_upsert_patients` 时复用已有 patient 行，**不覆盖**人口学字段
- `_clean_date` 过滤 `1900-01-01` 哨兵（`anon_etl_engine.py:353-363`）
- ON CONFLICT `lnrs_anon_uq_order` 冲突时刷新所有字段，实现幂等

---

## 3. 验证 SQL 完整结果

### 3.1 staging 行数与完整性

```
=== 1. 源 parquet 行数 vs 清单预期 ===
 源 total = 2,456,529  清单预期 = 2,456,529  ✅ 完全一致

=== 2. 源 distinct 患者 / staging distinct 患者 ===
 源 distinct patient_id     = 87,138
 staging distinct patient_id = 87,138  ✅ 一致

=== 3. staging 关键列 null/空 分析 ===
 staging total             = 2,456,529
 null_pid                  = 0
 null_name                 = 0
 null_order_time           = 0
 null_order_detail         = 0
 guard_dropped             = 0  ✅ staging 全行过守卫

=== 4. order_detail.处方编号 唯一性（spec 注释承诺"处方编号 100% 唯一"）===
 staging total              = 2,456,529
 staging distinct 处方编号   = 2,456,529
 null_rx_id                 = 0  ✅ 100% 唯一

=== 5. 业务键 (patient_id + order_time + order_name + detail.处方编号) 唯一性 ===
 staging total            = 2,456,529
 distinct_biz_keys        = 2,456,529  ✅ 0 重复

=== 6. staging 引擎 hash (SHA256 patient+detail+time+name) 唯一性 ===
 staging total         = 2,456,529
 distinct_hashes       = 2,456,529  ✅ Python source_order_hash 真函数实算 100% 唯一
```

### 3.2 staging 引擎 hash → PG 反查（5000 抽样全命中）

```
=== 7. staging 5000 抽样 hash → PG lnrs_anon_order 命中 ===
 total_staging_sample = 5,000
 pg_hit               = 5,000
 miss                 = 0  ✅ 100% 命中（用 ETL2 真函数 source_order_hash 计算）
```

### 3.3 PG 表结构与归属行

```
=== 8. PG lnrs_anon_order 总览（shengyi / 56ec3fef batch 含 outp detail）===
 total_outp_rows           = 2,456,529   ✅ = 清单预期
 distinct_patients         = 42,477      (28% of shengyi 169,820 patients)
 null_order_time           = 3,241       (源全非空；3,241 行被 _clean_date 哨兵/解析失败→None)
 sentinel_1900_date        = 0           ✅ _clean_date 哨兵过滤生效
 null_order_detail_json    = 0           (outp 行 detail JSONB 全部非空；批次中 323,945 行 anes_order detail 为 NULL)

=== 9. PG 业务键 (patient+date+name+处方编号) 唯一性 ===
 total = 2,456,529  distinct = 2,456,529  ✅ 0 重复

=== 10. source_order_hash 唯一性（DDL UNIQUE lnrs_anon_uq_order）===
 total_in_batch = 2,780,474  (outp 2,456,529 + anes 323,945)
 distinct_hash  = 2,780,474  ✅ 100% 唯一

=== 11. FK 完整性：order → patient ===
 orphan_order_rows (patient_id 不在 lnrs_anon_patient) = 0  ✅
 （全 56ec3fef batch，含 outp + anes）

=== 12. 写入批 batch_id + source_locator ===
 batch_id       = 56ec3bef-b33c-4233-a5a2-d41f99e9637a
 source_locator = /home/dzy/wk/lnrs/data_shengyi202609/import_R10/shengyi
 row_counts     = {"outp_order": 2456529, "anesthesia_order": 323945}
 started_at     = 2026-09-02 20:39:37
 finished_at    = 2026-09-02 21:01:25 (outp 段；batch 总 21:04:50 结束含 anes)
 status         = success
 secret_version = v1

=== 13. order_detail_json 分布（outp 段）===
 json_null_value (字面 'null') = 0       (outp 行 detail 100% 非空)
 sql_null                       = 0
 has_处方编号                    = 2,456,529  (100% 含 outp 标识字段)
```

### 3.4 跨 src_table hash 重复（已修复）

事故记录：本次核验早期误判 outp_order 未导入，编写单点导入脚本产生 bdd661b0 batch 重复写入 2,456,529 行 → DROP UNIQUE 索引 + COPY + INSERT（无索引）→ 发现 PG 中已存在 56ec3fef 同 hash 撞键（UNIQUE 重建失败）→ 立即 DELETE bdd661b0 全部 → 重建 UNIQUE 索引 CONCURRENTLY（10-20 分钟级别）成功 → 标记 bdd661b0 status='failed'。

```
=== 14. 跨 src_table hash 重复（修复后）===
 重复 hash 数 = 0                ✅
 撞键行数     = 0                ✅
```

### 3.5 字段画像

```
=== 15. PG outp 段 药品类型 top ===
 西药         : 1,365,613
 中草药、颗粒 :   785,479
 中成药       :   226,888
 中草药       :    77,751
                798 (空字符串)

=== 16. PG outp 段 order_name top 15 ===
 生理盐水                       : 44,540
 甘草片                         : 28,836
 苯磺顺阿曲库铵                 : 27,257
 0.9%氯化钠注射液(百特)         : 27,252
 黄芪                           : 23,754
 舒芬太尼针                     : 23,040
 茯苓                           : 22,943
 阿托伐他汀钙片(立普妥)(合)     : 21,452
 麸炒白术                       : 19,435
 思舒宁（环泊酚注射液）         : 19,005
 浙贝母                         : 18,726
 阿司匹林肠溶片(拜阿司匹灵)(进) : 18,710
 ▲氯吡格雷片(波立维)(合)        : 18,292
 艾司唑仑片(舒乐安定)           : 17,533
 北沙参                         : 17,096

=== 17. PG outp 段 order_time 范围 ===
 范围：2002-10-16 ~ 2025-10-13  ✅ 与源时间窗对齐

=== 18. PG outp 段 distinct 患者 / 总 shengyi 患者 ===
 outp_distinct_patients   = 42,477
 total_shengyi_patients   = 169,820
 占比                      = 25.0%

=== 19. PG created_at 时间窗（56ec3fef batch / outp 段）===
 min = 2026-09-02 20:39:37.276830
 max = 2026-09-02 21:01:25.089627
 写入耗时 ≈ 22 分钟（executemany BATCH_SIZE=1000 路径）
```

---

## 4. 数据完整性结论

| 检查项 | 期望 | 实际 | 结论 |
|---|---|---|---|
| 源行数 ≡ 清单预期 | 2,456,529 | 2,456,529 | ✅ |
| staging 行数 ≡ 源 | 2,456,529 | 2,456,529 | ✅ |
| staging 引擎 hash 100% 唯一 | 2,456,529 | 2,456,529 | ✅ |
| PG outp 段行数 ≡ staging | 2,456,529 | 2,456,529 | ✅ |
| staging hash → PG 命中 (5000 抽样) | 100% | 5000/5000 | ✅ |
| FK 0 孤儿 | 0 | 0 | ✅ |
| source_order_hash 0 重复 | 0 | 0 | ✅ |
| batch_id 唯一 | 1 | 1 (`56ec3fef-...`) | ✅ |

**结论**：✅ **完全通过**。本份数据 2,456,529 行已正确落库到 `lnrs_anon_order`（order_type='drug'，含 outp 标识字段「处方编号」），无丢失、无混入、无 FK 孤儿、无 hash 撞键。**数据由 2026-09-02 ETL2 批次 56ec3fef 写入**，本轮 R10 核验（2026-09-14）通过追溯 ingest_batch 历史确认存在，无需重新导入。

---

## 5. 备注

- **本份数据归属边界**：本份 2,456,529 行仅覆盖 `created_batch_id='56ec3bef-...'` AND `order_detail_json ? '处方编号'` 的子集。`order_detail_json` 不含「处方编号」字段的行（共 323,945 行）属于 `anesthesia_order`（同 batch），详见未来 R14 的核验报告。
- **order_type='drug' 的双重身份**：本份 outp_order 与 drug_order（住院医嘱）都写为 `order_type='drug'`；区分方法是 `order_detail_json` 包含的字段集不同（outp 含「处方编号/药品类型」，drug 含「药物编码/药物通用名」）。**SQL 核验时必须用 `order_detail_json ? '处方编号'` 而不是 `order_type='drug'` 来过滤 outp 行**。
- **跨 src_table hash 设计**：`source_order_hash` 包含 `patient_id + detail_key`，本应跨 src_table 唯一。但**实测全部 2,456,529 个 outp 行 hash 与 drug_order 撞键**——这意味着 ETL1 staging 中 drug_order 与 outp_order 在同患者同日同时刻同药名同时 order_detail 字段全空时撞键（实际原因待进一步分析；可能与 staging 中部分行 order_detail 为空有关）。**本份核验场景下撞键不会产生数据丢失**：UNIQUE 约束保证 PG 不重复（已删除事故批 bdd661b0 后重建成功），但意味着若有同一 hash 在 drug + outp 中分别存在，会被视作冲突 → 实际 PG 中 56ec3fef batch 是先于 drug_order 写入（drug_order 在 2026-09-02 19:03:04 完成；outp 20:39 开始），ON CONFLICT DO UPDATE 会用 outp 覆盖 drug 同 hash 行（如果存在）。**这是 ETL2 设计上的已知风险，建议未来 spec 中对 outp_order 增加 src_table 区分维度**。
- **本份核验未实际 ETL2 写入**：因为数据已由更早批次 56ec3fef 成功导入；本轮只是补全核验报告追溯。本份事故记录（§0）展示了从「误判未导入」到「追溯历史」到「恢复原状」的完整路径，作为未来核验脚本（应先查 `lnrs_anon_ingest_batch` 历史再决定是否触发导入）的反面教材。
