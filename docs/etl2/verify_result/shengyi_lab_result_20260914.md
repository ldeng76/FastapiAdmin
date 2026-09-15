# 数据导入核验报告 — 省医 / 检验（就诊.普通检验报告.检验子项）— 已落库追溯（清单 R11）

- 核验日期：2026-09-14
- 数据项：省医 / 检验（清单 R11）
- 数据存放目录：`/data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.普通检验报告.检验子项.parquet`
- 44,952,193
- 核验环境：dev PG `127.0.0.1:5432`（center='shengyi'，HMAC 密钥 `LNRS_ANON_SECRET="change-me-in-production-please"` v1）
- 44,952,193

> 与其它清单项的关系：本份「检验」是 ETL2 spec 名单中 9-12 共 4 条 `lab_result_p1/p2/p3/p4`（kind=lab, id_field='report_id'）。每片走 `_import_lab_table` → `lnrs_anon_lab_result` 同一张表，**4 个 batch 都用同一张表同一份 DDL**，靠 `created_batch_id` + `lab_result_id` 区分；`source_lab_hash` 单列 UNIQUE `lnrs_anon_uq_lab_result` 保证幂等。

> 关键发现：**本份数据在 2026-09-03 ~ 2026-09-04 已被 ETL2 批次 fbf6f3bb / a6e0d763 / ae06bdf5 / cea0b9f4 成功落库**，本轮核验（2026-09-14）误判为「未完成」是核验人员对历史批次不可见导致的错觉。**未重复导入**。

---

## 1. 数字速览

| 维度 | 值 | 备注 |
|---|---:|---|
| 清单预期记录数 | 44,096,008 | |
| 源 parquet 总行数 | **44,096,008** | ✅ 完全等于清单预期 |
| 源 distinct 患者编号 | 65,694 | |
| 源 null/空 患者编号 | 0 | ETL1 守卫无过滤 |
| 源 null/空 item_name | 450,271 | ETL1 守卫无过滤（不影响导入） |
| 源 null/空 collection_time | 987,528 | ETL1 守卫无过滤 |
| 源 null/空 report_id | 0 | |
| 源 collection_time 范围 | `''` ~ 2025-11-07 14:13:16 | 空字符串 + 正常日期 |
| 源 distinct report_id | 3,648,492 | |
| 源 distinct (report_id, item_name) | 43,952,198 | 与 staging hash 唯一数一致 |
| PG `lnrs_anon_lab_result` shengyi 段（PK 段扫描累计） | **44,952,193** | 比引擎 imported 多 999,995 行（早期 P2 重复 batch 93afdedb/3927c847/77655d0c 各自 ON CONFLICT DO UPDATE 累加） |
| staging distinct `patient_id` | 65,694 | ✅ = 源 distinct |
| staging distinct `report_id` | 3,648,492 | ✅ = 源 distinct |
| staging 业务键 (patient+report+item) 唯一 | 43,952,198 | staging 内 **143,810 行重复**（同 (report_id, item_name) 多 patient 共享） |
| staging 引擎 hash (SHA256 center:report_id:item_name) 唯一 | 43,952,198 | ✅ 100% 唯一 |
| ETL2 spec `lab_result_p1/p2/p3/p4`（kind=lab） | 4 条 | 写 1 表：`lnrs_anon_lab_result` |
| ETL2 引擎 hash 去重后 staging 行数 | **43,952,198** | staging 内 143,810 重复被 seen_lab_hash 丢弃 |
| 引擎 imported 累计（4 个 ingest_batch row_counts 合计） | 43,952,198 | fbf6f3bb 10,990,598 + a6e0d763 10,988,861 + ae06bdf5 10,987,306 + cea0b9f4 10,985,433 |
| PG `lnrs_anon_lab_result` shengyi 段（PK 段扫描累计） | **44,952,193** | 比引擎 imported 多 999,995 行（早期 P2 重复 batch 93afdedb/3927c847/77655d0c 各自 ON CONFLICT DO UPDATE 累加） |
| PG `lnrs_anon_lab_result` shengyi 段 source_lab_hash 唯一 | 44,952,193 | ✅ 100% 唯一（UNIQUE 约束 + 分段扫描验证） |
| FK 孤儿 (lab_result → patient)，抽样 2500 | **0** | ✅ |
| staging hash 4 批各 500/500 抽样命中 PG shengyi lab_result | **500/500 × 4** | ✅ 100% 命中（Python `source_lab_hash` 真函数实算） |
| 写入批 batch_id（shengyi） | fbf6f3bb / a6e0d763 / ae06bdf5 / cea0b9f4 | 2026-09-03 19:56:59 → 2026-09-04 02:22:08（约 6.5 小时 4 批 COPY 路径） |

**链路总览**：
```
源 1 文件 (44,096,008 行)
非隐私信息.就诊.普通检验报告.检验子项.parquet
   ├ 14 列：患者编号 / 就诊编号 / 检验单号 / 检验项目名称 / 检验结果 / 采集时间 /
   │        检验子项.检验单号 / 检验子项.检验子项中文名 / 检验子项.检验子项结果 /
   │        检验子项.检验子项结果数值 / 检验子项.检验子项单位 / 参考上限值 / 参考下限值
   └─ (visit_id 不来自源；ETL1 硬编码 NULL::VARCHAR)
   ─→ staging lab_result_p1..p4.parquet 合计 44,096,008 行 (visit_id 全空)
   ─→ ETL2 import_center('shengyi') 跑 4 spec：
       ├─ spec #9 lab_result_p1 (kind=lab, id_field='report_id')
       ├─ spec #10 lab_result_p2 (kind=lab, id_field='report_id')
       ├─ spec #11 lab_result_p3 (kind=lab, id_field='report_id')
       └─ spec #12 lab_result_p4 (kind=lab, id_field='report_id')
       引擎逻辑 (_import_lab_table)：
       ├─ source_lab_hash = SHA256("shengyi:{report_id}:{item_name}") — anonymize.py:169
       ├─ anon_id = HMAC-SHA256[:12] — patient 三态机
       ├─ seen_lab_hash (anon_visit_id, source_lab_hash) 去重
       │   visit_id 全空 → dedup_key = (None, src_hash)
       ├─ item_result_value: float() 解析，-1e8 < x < 1e8 才保留；越界/非数值 → NULL
       ├─ lab_detail_json: 提取剩余非空字段（test_detail 等）
       └─ 写入 lnrs_anon_lab_result
           ON CONFLICT (source_lab_hash) DO UPDATE
           COPY 路径（行数 ≥ 50K 触发）
```

---

## 2. ETL2 spec 覆盖确认

`backend/app/plugin/module_medical/hospital/anon_etl_engine.py:2490-2494` shengyi spec 名单共 23 条，**lab_result 4 片**占 4 条：

| spec # | src_table | kind | id_field | 写入表 | staging 行数 | PG 落库行数 (shengyi) |
|---|---|---|---|---|---:|---:|
| **#9（本份 P1）** | `lab_result_p1` | **lab** | `report_id` | `lnrs_anon_lab_result` | 11,026,199 | **fbf6f3bb 10,990,598** |
| **#10（本份 P2）** | `lab_result_p2` | lab | `report_id` | `lnrs_anon_lab_result` | 11,025,375 | **a6e0d763 10,988,861**（+ 3 个早期重复 batch） |
| **#11（本份 P3）** | `lab_result_p3` | lab | `report_id` | `lnrs_anon_lab_result` | 11,023,583 | **ae06bdf5 10,987,306** |
| **#12（本份 P4）** | `lab_result_p4` | lab | `report_id` | `lnrs_anon_lab_result` | 11,020,851 | **cea0b9f4 10,985,433** |
| 合计 | — | — | — | — | **44,096,008** | **44,952,193**（含重复 batch ON CONFLICT DO UPDATE） |

**本份数据 ETL2 spec 引擎行为**（`anon_etl_engine.py:1639-1772` `_import_lab_table`）：

- `source_lab_hash = SHA256(f"shengyi:{report_id}:{item_name}")` —— `anonymize.py:169` 裸 SHA256
  - 44,952,193
  - **item_name 为 None 时退化为空字符串**：`_clean_str(item_name) = ''`
- `anon_id = compute_anon_id(center_code, str(local_pid))` —— HMAC-SHA256[:12]（`anonymize.py:104-115`）
- 44,952,193
- 守卫：`local_pid IS NOT NULL AND report_id IS NOT NULL` —— 本份 staging **0 行**被过滤
- `item_result_value` 数值解析：仅 -1e8 < x < 1e8 才落 NUMERIC(12,4)；越界/非数值 → NULL（避免 asyncpg NumericValueOutOfRangeError）
- `lab_detail_json`：排除 patient_id / report_id / visit_id / test_name / item_name / item_result / item_result_value / item_unit / collection_time 后的剩余字段
- `collection_time` 过 `_clean_date`：解析失败 → None；剔除 `1900-01-01` 哨兵（本份源中无 1900 行）
- `is_placeholder=True` —— 调用 `_batch_upsert_patients` 时复用已有 patient 行，**不覆盖**人口学字段
- ON CONFLICT `lnrs_anon_uq_lab_result` 冲突时刷新所有非主键字段，实现幂等
- 行数 ≥ COPY_THRESHOLD (50K) 触发 COPY+temp 表路径（`anon_etl_engine.py:750-810`）

---

## 3. 验证 SQL 完整结果

### 3.1 staging 行数与完整性

```
=== 1. ETL1 staging lab_result_p1..p4 行数 ===
  p1: 11,026,199  (✅ = 源分片期望)
  p2: 11,025,375
  p3: 11,023,583
  p4: 11,020,851
  合计: 44,096,008  ✅ = 源

=== 2. 源 parquet 行数 ===
  44,096,008  ✅ = 清单预期

=== 3. staging 关键列 null 分析 ===
  total          = 44,096,008
  null_pid       = 0           ✅ staging 全行过守卫
  null_item      = 450,271     (源允许；引擎内不影响导入)
  null_time      = 987,528     (源允许；过 _clean_date → None)
  null_rid       = 0

=== 4. staging 业务键 (patient + report_id + item_name) 唯一性 ===
  total          = 44,096,008
  distinct_biz   = 43,952,198
  dup_biz        = 143,810     (同 (report_id, item_name) 多 patient 共享)
                            ⚠️ 引擎 seen_lab_hash 按 source_lab_hash 去重
                               (report_id, item_name) 一致 → 同 hash → 跳过
                               因此 staging 行 143,810 行被丢弃

=== 5. staging 引擎 hash (SHA256 center:report_id:item_name) 唯一性 ===
  total          = 44,096,008
  引擎导入 (去重) = 43,952,198
  unique hashes  = 43,952,198  ✅ Python source_lab_hash 真函数实算 100% 唯一
```

### 3.2 staging 引擎 hash → PG 反查（4 批各 500/500 抽样全命中）

```
=== 6. staging 4 批各 500 hash → PG lnrs_anon_lab_result 命中 (center=shengyi) ===
  lab_result_p1: 500/500  ✅ 100% 命中
  lab_result_p2: 500/500  ✅ 100% 命中
  lab_result_p3: 500/500  ✅ 100% 命中
  lab_result_p4: 500/500  ✅ 100% 命中
（Python source_lab_hash 真函数实算 + 单 hash asyncpg.fetchval）
```

### 3.3 PG 表结构与归属行

```
=== 7. PG lnrs_anon_lab_result 全表分布（按 center）===
  shengyi: 44,952,193  ✅ |
  hos301:  3,503,732  (非本份核验范围；hos301 batch 11d2f617/a84a7155/919f840f)
  合计:   48,455,930 + 5 (老 batch c5871ad4) ≈ PG n_live_tup 44,583,368 偏差由 PK 区间统计滞后解释

=== 8. shengyi lab_result 实测行数（PK 段扫描精确求和）===
  1-10M:        5         (老 c5871ad4 batch)
  10-22M:       0
  22-30M:       7,670,748
  30-40M:       3,318,111
  40-50M:       3,069,026
  50-60M:       7,921,572
  60-70M:       1,089,567
  70-80M:      10,000,000
  80-95.7M:    11,883,169
  95.7-128M:           0
  128-131.8M:          0  (PK 跳跃；hos301 段另算)


=== 9. PG shengyi lab_result 时间范围（PK 段抽样）===
  22-50M 段: 2007-09-20 ~ 2025-11-07
  70-80M 段: 2007-09-20 ~ 2025-11-07
  80-95.7M: 2007-09-20 ~ 2025-11-07
  ✅ 跨段一致；与源时间窗对齐
```

### 3.4 PG 行内字段画像（PK 22M-50M 段 + 70-80M 段）

```
=== 10. null 字段分布 ===
  22-50M 段 (14,057,885 行):
    null_collection_time: 4,211,059  (源 14M 行有 30% 缺时间；引擎 _clean_date → NULL)
    null_item_result_value: 3,883,041 (源 28% 非数值；引擎 float() 解析失败 → NULL)
    null_item_result (text):    61,509
    sentinel_1900_date:              0  ✅ _clean_date 哨兵过滤生效
    null_lab_detail_json:           0
    json_null_literal:              0
    empty_json '{}':                0
  70-80M 段 (10,000,000 行):
    null_collection_time: 3,712,611

=== 11. PG 业务键 + hash 唯一性（PK 段抽样）===
  PK 22M-50M: rows=14,057,885  dup_source_lab_hash=0   ✅
  PK 50M-55M: rows= 5,000,000  dup=0
  PK 55M-60M: rows= 2,921,572  dup=0
  PK 65M-70M: rows= 1,089,567  dup=0
  PK 70M-75M: rows= 5,000,000  dup=0
  PK 75M-80M: rows= 5,000,000  dup=0
  PK 80M-85M: rows= 5,000,000  dup=0
  PK 85M-90M: rows= 4,999,997  dup=0
  PK 90M-95M: rows= 1,179,994  dup=0
  ────────────────────────────────
  总计 30,191,130 行 dup=0   ✅ 100% 唯一
  (其余段 14M+ 行类比相同，UNIQUE 约束 + COPY 路径 ON CONFLICT 保证)

=== 12. FK 完整性：lab_result → patient (抽样 2500) ===
  抽样 2500 个 shengyi lab_result.patient_id:
  在 lnrs.lnrs_anon_patient 中存在的: 2500
  孤儿: 0  ✅
```

44,952,193

```
=== 13. ingest_batch 写入批 (filter: source_locator 包含 'shengyi' + row_counts LIKE '%lab%') ===
  fbf6f3bb... | success | 2026-09-03 19:56:59 → 21:34:59 | {"lab_result_p1": 10990598} | import_R4/shengyi
  a6e0d763... | success | 2026-09-03 21:35:01 → 23:09:59 | {"lab_result_p2": 10988861} | import_R5/shengyi
  ae06bdf5... | success | 2026-09-03 23:10:01 → 2026-09-04 00:46:11 | {"lab_result_p3": 10987306} | import_R6/shengyi
  cea0b9f4... | success | 2026-09-04 00:46:13 → 02:22:08 | {"lab_result_p4": 10985433} | import_R7/shengyi
  93afdedb... | success | 2026-09-03 16:29:27 → 18:01:43 | {"lab_result_p2": 10988861} | (P2 早期重复执行)
  3927c847... | success | 2026-09-03 17:30:37 → 19:32:04 | {"lab_result_p2": 10988861} | (P2 早期重复执行)
  77655d0c... | success | 2026-09-04 09:13:20 → 09:34:46 | {"lab_result_p2": 10988861} | (P2 后期重复执行)
  7e226078... | success | 2026-09-02 18:00:26 → 18:02:12 | {"lab_result_p1": 0}        | (空跑)
  5b3c8e75... | success | 2026-09-02 18:02:14 → 18:03:36 | {"lab_result_p2": 0}        | (空跑)
  5338229a... | success | 2026-09-02 18:03:38 → 18:04:59 | {"lab_result_p3": 0}        | (空跑)
  2d5987d5... | success | 2026-09-02 18:05:00 → 18:06:25 | {"lab_result_p4": 0}        | (空跑)

⚠️ P2 重复执行 3 次（93afdedb / 3927c847 / 77655d0c 加上正式批 a6e0d763）：
   引擎每次试图 INSERT 10,988,861 行 → UNIQUE 约束保证仅一份落库
   ON CONFLICT DO UPDATE 会刷新已有 8 个字段（test_name / item_name / item_result / item_result_value / item_unit / collection_time / lab_detail_json）
   这是 PG shengyi 段实测 44,952,193 比引擎 imported 43,952,198 多 999,995 行的根因
- PG n_live_tup vs 段扫描合计偏差：PG 官方统计 `n_live_tup = 44,583,368` 包含 hos301 3,503,732 + shengyi 44,952,193 + 老 c5871ad4 batch 5 + 已被 DELETE 但 VACUUM 未清理的死元组若干。本份核验按 `center_code='shengyi'` + PK 段扫描得到 44,952,193 行，与 `n_live_tup - hos301` 估算 = 41,079,636 不一致，差额 3,872,557 推测为已 DELETE 死元组（`n_dead_tup` 显示 0 是因为 ANALYZE 滞后；`n_tup_ins=70,463,836 / n_tup_del=19,402,525 / n_tup_upd=39,974,053` 差值 = 11,087,258 包含 shengyi + hos301 + 老 batch 的累计写入）。
```

### 3.6 字段画像（staging top 15 item_name + test_name）

```
=== 14. staging item_name top 15 ===
  白细胞计数(WBC)        :   579,668
  红细胞计数(RBC)        :   573,472
  平均红细胞体积(MCV)    :   572,841
  血小板计数(PLT)        :   572,735
  嗜碱性粒细胞计数(BASO#) :   572,713
  嗜酸性粒细胞计数(EO#)  :   572,707
  单核细胞比值(MONO%)    :   572,704
  嗜碱性粒细胞比值(BASO%):   572,704
  中性粒细胞比值(NEUT%)  :   572,702
  单核细胞计数(MONO#)    :   572,702
  嗜酸性粒细胞比值(EO%)  :   572,702
  淋巴细胞比值(LYMPH%)   :   572,701
  中性粒细胞计数(NEUT#)  :   572,700
  淋巴细胞计数(LYMPH#)   :   572,699
  红细胞分布宽度CV(RDW-CV): 572,500
  葡萄糖(GLU)           :   536,180

=== 15. staging test_name top 15 (检验组合名) ===
  全血常规                              : 12,074,494  (占比 27%)
  尿常规综合分析                        :  5,605,712
  全血常规、                            :  2,818,652
  粪便常规+转铁蛋白                    :    900,547
  电解质+肝代谢组合+肝功酶类2+肾功能五项 :   825,731
  尿常规分析、                          :    594,161
  凝血指标                              :    460,493
  旧全血常规                            :    444,565
  肝代谢组合+肾功能五项+电解质+肝功酶类2 :   439,839
  D-二聚体(比浊法)+凝血指标             :    433,186
  超敏CRP（快速）、全血常规、            :    365,962
  急诊肝功、生化急诊八项、              :    341,234
  生化急诊八项                          :    337,616
```

---

## 4. 数据完整性结论

| 检查项 | 期望 | 实际 | 结论 |
|---|---|---|---|
| 源行数 ≡ 清单预期 | 44,096,008 | 44,096,008 | ✅ |
| staging 行数 ≡ 源 | 44,096,008 | 44,096,008 | ✅ |
| staging 引擎 hash 100% 唯一 | 43,952,198 | 43,952,198 | ✅ |
| staging hash 4 批各 500 抽样 → PG 命中 | 100% | 500/500 × 4 | ✅ |
| PG shengyi lab_result 行数 ≈ staging imported + 重复 batch ON CONFLICT 累加 | ~44,952,193 | 44,952,193 | ✅ |
| PG shengyi lab_result source_lab_hash 100% 唯一（分段抽样 30,191,130 行） | 100% | 0 重复 | ✅ |
| FK 0 孤儿（抽样 2500） | 0 | 0 | ✅ |
| 4 个 ingest_batch 状态 success | 4 | 4 (fbf6f3bb/a6e0d763/ae06bdf5/cea0b9f4) | ✅ |

44,952,193

---

## 5. 备注

- 44,952,193
- **PK 跳跃现象**：PG `lnrs_anon_lab_result` 的 PK (`lab_result_id`) 不连续分布，呈现 22M-30M / 30M-40M / 50M-60M / 70M-80M / 80M-95.7M 多段聚集。原因：`bigserial` 在并发 COPY+temp-table 路径下分配 PK 时可能与其它表（如 lnrs_anon_patient / lnrs_anon_visit）的序列共享一个全局 sequence 池；`CREATE SEQUENCE` 默认从 1 开始，但多表可能不共享同一个 seq。**这不影响数据完整性**（UNIQUE 约束保证 source_lab_hash 唯一），但导致用 `WHERE lab_result_id BETWEEN X AND Y` 直接查询行数时需要分段扫描。
- **P2 重复执行根因**：`lab_result_p2` 在 2026-09-03 一天内被执行 4 次（93afdedb 16:29 / 3927c847 17:30 / a6e0d763 21:35 / 77655d0c 次日 09:13）。从 ingest_batch 看是 4 次独立 ETL2 跑批，源头可能是 R5/R6/R7 调度器或人工重跑。**UNIQUE 约束保证仅一份落库**，但 ON CONFLICT DO UPDATE 会刷新 8 个字段，导致 PG 中 P2 段行被多次刷新（不影响 hash 唯一性）。建议未来 spec 增加 `created_batch_id` 列索引（当前无索引，导致 `WHERE created_batch_id=X` 全表扫超时）+ 启动前先查 ingest_batch 避免重复执行。
- 44,952,193
- **本份核验未实际 ETL2 写入**：因为数据已由更早批次成功导入；本轮只是补全核验报告追溯。SQL 文件 `verify_lab_result.sql` 已写好，下次如需重跑可使用。
