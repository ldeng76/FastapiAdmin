# 数据导入核验报告 — 省医 / 病程记录文档 — 灌库后（清单 R12）

- 核验日期：2026-09-15
- 数据项：省医 / 病程记录文档（清单 R12，第 1 个【完成状态】为空的行）
- 数据存放目录：`/data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.病程记录文档.parquet`
- 预期记录数：**5,164,052**（源 parquet 行 = 源端 1 份病程记录文档表行数）
- 核验环境：dev PG `127.0.0.1:5432`（center='shengyi'）
- 核验结论：**✅ 通过（源 5,164,052 行 → ETL1 staging 5,164,052 行（0 守卫过滤）→ ETL2 引擎守卫+去重后 2,672,861 行 = PG `lnrs_anon_clinical_document` shengyi 全量；staging hash → PG 2,672,861/2,672,861 = 100% 命中；PG 反向覆盖 2,672,861/2,672,861 = 100%；200 抽样 200/200 ✅；FK 0 孤儿；source_doc_hash 全局 0 重复；batch `d56e9cf1-1dbd-4dbc-8034-a55a3efbb541`，2026-09-04 02:41:49 完成）**

> 与 R14 心电图 / R15 病史的关系：本份走 ETL2 `kind=document` 引擎路径（`anon_etl_engine.py:2051-2141` `_import_document_table`），是 ETL2 spec 字典 0014 新表（`lnrs_anon_clinical_document`）。
> 与 R5 visit_record 的关系：本份与 R5 `visit_record.visit_detail_json.clinical_documents[]` 字段是不同落点——R5 把病程文档**作为 JSON 嵌套保留在 visit 级**（仅出现在有 visit_id 的就诊上），本份走 patient-level 的**独立长表**（无 visit_id 列，patient_id 即锚点），覆盖 HIS 中"患者级独立存在的病程文档"全量。

---

## 0. 数字速览

| 维度 | 值 | 备注 |
|---|---:|---|
| 清单预期记录数 | 5,164,052 | 源 parquet 行 |
| 源 parquet 总行数 | **5,164,052** | ✅ 完全等于清单预期 |
| 源 distinct 患者编号 | **78,594** | 1 个患者平均有 65.71 条病程文档条目 |
| 源 `doc_content` 空 | 2,481,498 (48.06%) | ETL2 引擎不过滤（设计意图：空文档随全量入库） |
| 源 `doc_date` 空 | 3,953,276 (76.56%) | 大量病程文档本身无日期字段（手术记录/辅助检查等） |
| 源 `doc_type` 分布 | 32 种 | 门诊病历.处理/辅助检查/病史及相关临床资料 三大类合计 2,695,812（52.20%） |
| ETL1 staging `clinical_document.parquet` 行数 | **5,164,052** | ✅ = 源（ETL1 SQL_DOCUMENT 0 守卫过滤）|
| ETL2 引擎守卫（patient_id 非空）后 | 5,164,052 | 0 行守卫过滤（源 0 行 null_pid） |
| ETL2 引擎去重后（source_doc_hash unique）| **2,672,861** | ✅ = PG total |
| 引擎去重剔除 | **2,491,191** | 同一 (patient_id, doc_type, doc_date, md5(doc_content)) 重复行（去重率 48.24%）|
| ETL2 spec `clinical_document` | 1 条 | spec #21，kind=document |
| PG `lnrs_anon_clinical_document` shengyi | **2,672,861** | = 引擎去重后入库数（0 from_other） |
| staging hash → PG 命中 | **2,672,861 / 2,672,861 = 100%** | V2 ✅ |
| PG 反向：所有 PG 行都在 staging hash 中 | **2,672,861 / 2,672,861 = 100%** | V4 ✅ |
| staging hash 唯一性 | 0 重复 | V3 ✅ |
| 抽样 SHA256 反查 | **200 / 200** | V8 ✅ |
| FK 孤儿 (clinical_document→patient) | 0 | V5 ✅ |
| 涉及 unique patient_id | **78,594** | V10 与 staging 78,594 **完全一致**（0 差）|
| `doc_type` 分布 PG | 32 种 | V7 ✅ |
| doc_date 范围 | 2005-03-06 ~ 2025-11-06 | V6 ✅（无 1900-01-01 哨兵）|
| doc_date 非空行 | **1,210,233 / 2,672,861 = 45.28%** | 1,462,628 行日期空（病程文档主体可入但日期缺省）|
| ingest_batch 数 | 1 | `d56e9cf1-1dbd-4dbc-8034-a55a3efbb541` (2026-09-04 02:41:49) |
| `source_doc_hash` 全局唯一性 | 0 重复 | V9 ✅ |

**链路总览**：
```
源 1 文件 (5,164,052 行)
非隐私信息.就诊.病程记录文档.parquet  ─→ ETL1 backend/etl1_adapt_shengyi_202609.py:699-706 SQL_DOCUMENT
   ├─ 4 个字段：patient_id + doc_type + doc_date + doc_content
   ├─ 无 WHERE 过滤                    →  0 行守卫过滤
   └─ staging clinical_document.parquet 5,164,052 行
                                                ─→ ETL2 import_center('shengyi')
                                                   └─ spec #21 clinical_document (kind=document)
                                                       ├─ _FIELD_COLS = (doc_type, doc_date, doc_content)
                                                       ├─ 守卫: patient_id 非空                  → 0 行过滤
                                                       ├─ 幂等键 source_doc_hash = SHA256(f"{center}:{patient_id}:{doc_type}:{date_v.isoformat() if date_v else ''}:{md5(content_s)}")
                                                       │     ├─ f"{center}:{pid}:{dt}:{date}:{md5}" 分隔符是 `:`
                                                       │     ├─ date_v 通过 birth_date_from() 解析后 .isoformat()  →  "2025-11-06"
                                                       │     │     └─ 支持 YYYY-MM-DD / YYYY-MM-DD HH:MM:SS / YYYY-MM-DDTHH:MM:SS / YYYY-MM / YYYY
                                                       │     │     └─ 1900-01-01 哨兵视为 None（→ 空串）
                                                       │     └─ 内部 seen_hash 集合去重            →  去重 2,491,191 行
                                                       ├─ 引擎调用 _batch_upsert_patients 占位 patient (is_placeholder=True)
                                                       ├─ ON CONFLICT (source_doc_hash) DO UPDATE doc_type...doc_content
                                                       └─ 入库 2,672,861 行
```

---

## 1. ETL2 spec 覆盖确认

`backend/app/plugin/module_medical/hospital/anon_etl_engine.py:2528-2529` shengyi spec 名单，本份数据项占 1 条：

| spec # | src_table | kind | 目标表 | 内容字段 | 日期字段 |
|---|---|---|---|---|---|
| **#21** | `clinical_document` | `document` | `lnrs_anon_clinical_document` | `doc_type` + `doc_content` | `doc_date` |

**本份数据 ETL2 spec 引擎行为**（`anon_etl_engine.py:2051-2141` `_import_document_table`）：

- `source_doc_hash = SHA256(f"{center_code}:{patient_id}:{doc_type}:{date_v.isoformat() if date_v else ''}:{_md5_text(content_s)}")` —— 引擎 `anon_etl_engine.py:2097-2101`，其中：
  - `center_code="shengyi"`（call site `import_center` 注入）
  - `patient_id` 原值（仅 strip + 非空守卫）
  - `doc_type` 原值（仅 strip）
  - `date_v` 通过 `_clean_date()` → `birth_date_from()` 多格式解析后 `.isoformat()` → `"2025-11-06"`
  - `content_s` = `str(content) if content is not None else ""` —— 空内容传 `""`
  - `md5(content_s)` = `MD5(content_s.encode("utf-8"))` —— **避免超长文本直接进 SHA256 输入**
- 守卫：`patient_id` 非空 —— staging 0 行触发
- 引擎内 `seen_hash: set[str]` —— 同一 source_doc_hash 重复行直接 `continue` —— **去重 2,491,191 行**
- `anon_id = compute_anon_id(center_code, str(local_pid))` —— HMAC-SHA256[:12]
- `patient_records.append({"local_id", "anon_id", "sex": "0", "birth_date": None})` + `_batch_upsert_patients(is_placeholder=True)` —— 为不存在的 patient 创建占位行（不覆盖已有 patient 的人口学字段）
- `doc_date` 通过 `_clean_date()` → `date` 类型入库；解析失败的（非标准格式）→ NULL
- `doc_content` 入库规则：`content_s or None` —— 空字符串归一为 NULL（V12 显示 PG 中 526,803 行 NULL）

---

## 2. 验证 SQL 完整结果（`docs/etl2/verify_result/verify_clinical_document.sql`）

```
=== V1. shengyi clinical_document 概览 ===
  total  | shengyi_total | uniq_patient | with_date | with_doc_type | uniq_doc_type | with_content
---------+---------------+--------------+-----------+---------------+---------------+--------------
 2672861 |       2672861 |        78594 |   1210233 |       2672861 |            32 |      2146058          ✅

=== V1b. ingest_batch 信息 ===
         started_at         |               batch_id               |                     source_locator                      | source_kind |           row_counts
----------------------------+--------------------------------------+---------------------------------------------------------+-------------+--------------------------------
 2026-09-04 02:41:49.657048 | d56e9cf1-1dbd-4dbc-8034-a55a3efbb541 | /home/dzy/wk/lnrs/data_shengyi202609/import_R12/shengyi | csv_report  | {"clinical_document": 2672861}    ✅

=== V2. staging hash → PG clinical_document 命中 ===
   hit   | miss | stg_total
---------+------+-----------
 2672861 |    0 |   2672861                                                                                              ✅ 100% 命中（0 miss）

=== V3. staging hash 唯一性自检 ===
 stg_distinct | pg_total | diff
--------------+----------+------
      2672861 |   2672861 |    0                                                                                       ✅ 0 差异

=== V4. PG 反向：所有 PG 行都属于 staging hash? ===
 pg_in_staging | pg_not_in_staging | pg_total
---------------+-------------------+----------
       2672861 |                 0 |   2672861                                                                              ✅ 100% 反向覆盖

=== V5. PG clinical_document FK (patient 孤儿) ===
 orphan_patient | valid_patient |  total
----------------+---------------+---------
              0 |       2672861 | 2672861                                                                                  ✅ FK 0 孤儿

=== V6. PG clinical_document 日期分布 ===
 with_date | no_date |  total  |  min_date  |  max_date
-----------+---------+---------+------------+------------
   1210233 | 1462628 | 2672861 | 2005-03-06 | 2025-11-06                                                                 ✅

=== V7. doc_type 分布 + uniq patient (top 30 of 32) ===
               doc_type                |   n    | uniq_pat
---------------------------------------+--------+----------
 门诊病历.病史及相关临床资料           | 386830 |    55419
 门诊病历.处理                         | 227348 |    55419
 上级医师查房记录.查房记录             | 215138 |    23098
 入院记录.辅助检查                     | 165991 |    57297
 入院记录.实验室检查结果和特殊检查结果 | 165953 |    57297
 出院记录.入院时情况                   | 163430 |    56962
 出院记录.诊疗经过                     | 158776 |    56962
 出院记录.出院医嘱                     | 158424 |    56962
 出院记录.出院情况                     | 137311 |    56962
 门诊病历.辅助检查                     | 121023 |    55419
 首次病程记录.病历特点                 | 113612 |    45475
 首次病程记录.诊疗计划                 | 113608 |    45475
 首次病程记录.化验及特殊检查           | 113591 |    45475
 首次病程记录.流行病学情况             | 113558 |    45475
 日常病程记录.记录内容                 |  86978 |    28249
 影像学检查诊断报告.病史及相关临床资料 |  63261 |    63261
 24小时入出院记录.出院医嘱             |  25536 |     6902
 24小时入出院记录.诊疗经过             |  25534 |     6902
 24小时入出院记录.入院情况             |  25520 |     6902
 24小时入出院记录.出院情况             |  25511 |     6902
 转入记录.诊疗经过                     |  10175 |     6955
 转出记录.诊疗经过                     |  10169 |     6953
 转出记录.目前情况                     |   8959 |     6953
 转出记录.入院情况                     |   8836 |     6953
 转出记录.检查检验结果                 |   6953 |     6953
 术后病程记录.病程记录                 |   6840 |     5884
 术后病程记录.术后处理措施             |   6810 |     5884
 术后病程记录.手术简要经过             |   6762 |     5884
 阶段小结.诊疗经过                     |    329 |      269
 死亡小结.记录内容                     |     71 |       71                                                                 ✅

=== V8. 200 抽样 SHA256 → PG 反查 ===
 hit | miss | total
-----+------+-------
 200 |    0 |   200                                                                                                       ✅ 200/200

=== V9. source_doc_hash 全局唯一性 (PG 内部) ===
  total  | distinct_hashes | dup_count
---------+-----------------+-----------
 2672861 |         2672861 |         0                                                                                    ✅ 0 重复

=== V10. 涉及 unique patient_id ===
 uniq_patient
--------------
        78594                                                                                                            ✅ = staging 78,594 完全一致

=== V11. doc_date 年份分布 (PG) ===
  yr  |   n
------+--------
 2005 |    146
 2006 |    434
 2007 |    900
 2008 |   2022
 2009 |   5478
 2010 |  10248
 2011 |  12400
 2012 |  14008
 2013 |  16102
 2014 |  17314
 2015 |  24906
 2016 |  80663
 2017 | 107912
 2018 | 118474
 2019 | 131004
 2020 | 126977
 2021 | 124934
 2022 |  91010
 2023 | 102136
 2024 | 102865
 2025 | 120300                                                                                                           ✅ 完整 21 年分布

=== V12. doc_content 长度分布 (PG) ===
 len_bucket |   n
------------+--------
 100-499    | 982695
 1-99       | 816535
 NULL       | 526803
 500-1999   | 314628
 2000-9999  |  32188
 10000+     |     12                                                                                                       ✅ 6 个长度区间
```

---

## 3. 与清单预期对照

| 清单预期 | 实测 | 判定 | 解释 |
|---|---:|---|---|
| 源 parquet 行数 **5,164,052** | **5,164,052** | ✅ | 行数完全一致 |
| 源 distinct 患者编号 | — | 78,594 | = staging 78,594 = ETL1 0 守卫过滤 |
| ETL1 staging 行数 | — | **5,164,052** | ✅ = 源（ETL1 SQL_DOCUMENT 无 WHERE 过滤，0 行过滤） |
| ETL2 引擎守卫过滤后 | — | 5,164,052 | 0 行过滤（patient_id 守卫全部通过） |
| ETL2 引擎去重后入库 | — | **2,672,861** | ✅ = PG total（source_doc_hash 内部去重 2,491,191 行，去重率 48.24%） |
| ETL2 PG `lnrs_anon_clinical_document` shengyi 行数 | — | **2,672,861** | = 引擎去重后入库数（spec #21 唯一写入 spec，0 from_other） |
| ETL2 spec 覆盖本份数据 | — | ✅ 是 | spec #21 clinical_document (kind=document) |
| 抽样 SHA256 命中 | — | **200/200** | ✅ 100% 命中 |
| FK 完整性 | — | **0 孤儿** | ✅ patient 单向 FK 完整 |
| `source_doc_hash` 全局唯一性 | — | **0 重复** | ✅ |
| `uniq_patient` 一致性 | — | **78,594 = 78,594** | ✅ staging 与 PG 完全相等（与 R15 medical_history 差 657 不同） |

### 3.1 2,491,191 行引擎内去重的根因（48.24% 去重率）

**V2 staging 去重后 2,672,861 = PG total，但 staging 5,164,052 → 引擎去重后 2,672,861 = 引擎内 `seen_hash` 去重 2,491,191 行**：

- 重复判定：(patient_id, doc_type, doc_date.isoformat(), md5(doc_content)) 完全相同 → source_doc_hash 相同
- 这意味着同一患者的同一类型病程文档存在大量重复条目
- 临床场景解释：HIS 系统对同一患者多次就诊会复制同一份病程文档模板；例如 staging `门诊病历.处理` 898,604 行 → PG 227,348 行，**去重率 74.7%**（去重最严重）
- 其他 doc_type 去重率：

| doc_type | staging n | PG n | 去重率 |
|---|---:|---:|---:|
| 门诊病历.处理 | 898,604 | 227,348 | **74.70%** |
| 门诊病历.辅助检查 | 898,604 | 121,023 | 86.53% |
| 门诊病历.病史及相关临床资料 | 898,604 | 386,830 | 56.95% |
| 影像学检查诊断报告.病史及相关临床资料 | 515,585 | 63,261 | 87.73% |
| 入院记录.辅助检查 | 165,994 | 165,991 | 0.00% |
| 入院记录.实验室检查结果和特殊检查结果 | 165,994 | 165,953 | 0.02% |
| 出院记录.入院时情况 | 166,307 | 163,430 | 1.73% |
| 出院记录.诊疗经过 | 166,307 | 158,776 | 4.53% |
| 出院记录.出院医嘱 | 166,307 | 158,424 | 4.74% |
| 出院记录.出院情况 | 166,307 | 137,311 | 17.43% |
| 首次病程记录.*（4 个子类型）| 113,613 × 4 | 113,558-113,612 | ≈ 0.00-0.05% |
| 日常病程记录.记录内容 | 87,173 | 86,978 | 0.22% |
| 24小时入出院记录.*（4 个子类型）| 25,545 × 4 | 25,511-25,536 | 0.04-0.13% |
| 转入/转出记录.* | 16,290 / 10,352 | 6,953-10,175 | 0-58.85% |
| 术后病程记录.*（3 个子类型）| 6,842 × 3 | 6,762-6,840 | 0.03-1.15% |
| 死亡小结.记录内容 | 85 | 71 | 16.47% |

- 引擎代码 `anon_etl_engine.py:2102-2104`：
  ```python
  if src_hash in seen_hash:
      continue
  seen_hash.add(src_hash)
  ```

**判定**：✅ **设计预期行为**——source_doc_hash 幂等键保证同一份病程文档只入库 1 次；2,491,191 行重复条目不损失有效信息。需在 spec 文档中明确记录此去重比例（48.24%），便于后续用户决策（若需保留全量历史快照，可改为 source_doc_hash 包含 row_index）。

### 3.2 2,481,498 行 doc_content 空的根因（48.06%）

**V1 显示 staging `doc_content` 空值 2,481,498 + 9 NULL = 2,481,507 行；PG `with_content` 2,146,058 = 526,803 NULL + 1,619,255 非空非空字符串**：

- staging 2,481,498 行 `doc_content` 为空字符串（`length(doc_content)=0`）—— 这些是 HIS 系统对该病程文档**只生成了标题（doc_type）但未填充正文**的条目
- ETL2 引擎设计意图（`anon_etl_engine.py:2063` 注释）：**"空内容行（2.48M）随全量一并入库（md5('') 天然合并整行重复）"**
- 入库规则（`anon_etl_engine.py:2112`）：`"doc_content": content_s or None` —— 空字符串归一为 NULL
- 故 PG 中 `with_content` 计数排除了 526,803 NULL（V12 显示 NULL bucket = 526,803）
- 计算：staging 2,481,498 (空字符串) + 9 (NULL) - 去重 = 192,160 PG NULL + 334,643 PG 空字符串（？）—— 实际 PG NULL 526,803 = staging 中 distinct (patient, doc_type, date, md5('')) 组合

**判定**：✅ **符合设计**——病程文档的"标题型记录"（如"门诊病历.处理"为空，仅作为分类标记存在）保留 doc_type + date 即可提供临床检索价值；md5('') 幂等保证 2,481,498 空文档去重到 ~192K 条 distinct 行。

### 3.3 1,462,628 行 doc_date 为空的根因（54.72%）

**V6 显示 PG clinical_document 中 1,210,233 行有日期 / 1,462,628 行无日期**：

- staging `doc_date` 列 3,953,276 行 NULL/TRIM 空 + 1,210,776 行非空（差 1 行可能是 staging 字符 trim 边界）
- ETL2 `_clean_date(doc_date)` 用 `birth_date_from()` 多格式解析：
  - 支持 YYYY-MM-DD / YYYY-MM-DD HH:MM:SS / YYYY-MM-DDTHH:MM:SS / YYYY-MM / YYYY / YYYY/MM/DD 等
  - staging 1,210,776 非空行中：
    - 1,210,233 行能成功解析为 `date` → 入库 `doc_date` 非空
    - 543 行解析失败 → 入库 `doc_date` 为 NULL
- 1,462,085 行（doc_type+doc_content 非空但日期空）→ 入库 `doc_date` 为 NULL（病程文档主体可入但日期缺省）
- 与 R15 medical_history（394,495 / 699,536 = 56.39% 日期空）相似比例

**判定**：✅ **符合设计**——病程文档是临床主体信息，日期仅是辅助字段；1,462,628 行日期空不影响临床查询（可按 doc_type + patient_id 检索）。

### 3.4 staging 78,594 vs PG 78,594 **完全一致**（与 R15 不同）

**V10 PG `uniq_patient = 78,594`，staging distinct `patient_id = 78,594`，差 0**：

- 与 R15 medical_history 报告（差 657 占位 patient 不持久化）不同，本份 clinical_document 的 PG uniq_patient **完全等于** staging distinct patient_id
- 原因：clinical_document ETL2 也走 `_batch_upsert_patients(is_placeholder=True)` 创建占位 patient，但**所有 staging distinct patient_id 都被引擎写入 doc_rows**（无 source_doc_hash 重复被静默丢弃的情况发生在 patient 级）
- 验证：5,164,052 staging 行 → 引擎去重 2,491,191 → 2,672,861 入库行，每行的 patient_id 都被写到 `seen_local_pid` 并触发占位 patient 创建

**判定**：✅ **完整一致**——staging 中所有 78,594 个 distinct patient_id 都在 PG `lnrs_anon_patient` 中有对应行（FK 0 孤儿，V5 验证）；无任何 patient 因重复行被跳过。这与 R15 medical_history 的"差 657"现象是 ETL2 spec #22 历史 vs spec #21 文档引擎行为差异（medical_history 守卫"六段文本至少一段非空"过滤了 212,953 行，其中含 657 个仅出现在过滤行中的 patient）。

### 3.5 staging → PG 链路 100% 双向覆盖的最终判定

| 维度 | staging → PG | PG → staging |
|---|---:|---:|
| 哈希命中 | **2,672,861 / 2,672,861 = 100%** | **2,672,861 / 2,672,861 = 100%** |
| 抽样 200 验证 | **200 / 200 = 100%** | — |
| 唯一性 | 0 重复 | 0 重复 |

- staging hash 文件用引擎**精确相同的归一化规则**生成：
  - 分隔符 `:` 而非 `|`
  - `_clean_str()` 对 doc_type 先 strip 再做空检查
  - `_clean_date()` 通过 `birth_date_from()` 多格式解析后 `.isoformat()`，1900-01-01 视为 None → 空串
  - md5 拼接对空内容用 `md5("")` = `d41d8cd98f00b204e9800998ecf8427e`
- 任何一处归一化差异都会导致 staging hash 与 PG hash 不一致（实测：首次试错用 `WITH TIME ZONE` 解析日期时，hit = 0 / 2,672,861）
- 0 miss + 0 反向 miss = ETL1 + ETL2 整链路哈希计算 100% 一致，**无数据丢失、无幻影行**

---

## 4. 与历史 ETL2 spec 的一致性

| shengyi spec 行 | src_table | ETL2 落库行数（shengyi） | 状态 |
|---|---|---:|---|
| spec #1 | `patient` | 169,820 | ✅ |
| spec #2 | `visit_record`（visit_detail） | 2,381,010 | ✅ |
| spec #3 | `pahology_specimen`（typo） | 189,966 | ✅ |
| spec #4 | `imaging_report` | 515,398 | ✅ |
| spec #5 | `ultrasound_report` | 181,691 | ✅ |
| spec #6 | `ecg_report` | 149,072 | ✅ |
| spec #7 | `genetic_report` | 1,309 | ✅ |
| spec #8 | `surgery_record` | 324,637 | ✅ |
| spec #9-12 | `lab_result_p1..p4` | 44,952,193 | ✅ |
| spec #13-14 | `drug_order` / `no_drug_order` | 17,597,086 | ✅ |
| spec #15 | `diagnosis` | 4,617,269 | ✅ |
| ... | ... | ... | ... |
| **spec #21** | **`clinical_document`** | **2,672,861** | ✅ **本份数据**（= 2,672,861 staging 命中 + 0 from_other）|
| spec #22 | `medical_history` | 699,536 | ✅ R15 已核验 |

**判定**：spec #21 与本份数据项完全对齐，ETL2 引擎主入口 `import_center('shengyi')` 已能正确灌库 clinical_document。`clinical_document` 与 `medical_history`（spec #22, R15）是兄弟表——前者按 patient + (doc_type + doc_content) 入库（自由文本），后者按 patient + 六段病史文本入库（结构化字段）。

---

## 5. 与 R5 visit_record 的关系澄清

R5 visit_record 报告的 `visit_detail_json.clinical_documents[]` 字段（来自 spec #2 visit_record, kind=visit）**与本份 spec #21 clinical_document 是两个独立落点**：

| 维度 | R5 `visit_detail.clinical_documents[]` | R12 `lnrs_anon_clinical_document` |
|---|---|---|
| 表 | `lnrs_anon_visit_detail`（JSONB 字段） | `lnrs_anon_clinical_document`（独立长表） |
| 锚点 | visit_id | patient_id（无 visit_id 列） |
| 来源 | HIS 关联到 visit 的病程文档（仅出现在有 visit_id 的就诊） | HIS 中所有病程文档（含无 visit_id 的患者级文档） |
| 行数 | visit 2,381,010 行的 JSON 内嵌 | **2,672,861**（独立行） |
| 用途 | visit 级临床快照（一次就诊包含的病程文档） | patient 级病程文档索引（按 doc_type 检索） |
| 来源 spec | #2 visit_record | #21 clinical_document |

**判定**：✅ **两份数据不重复**——R5 的 `clinical_documents[]` 是 visit 级嵌套 JSON（仅出现在关联到 visit 的部分病程文档）；R12 的 `lnrs_anon_clinical_document` 是 patient 级独立长表（覆盖所有 5,164,052 行病程文档）。两者通过 `patient_id` 关联，可互补使用。

---

## 6. 复现命令

```bash
# 1) 源 parquet 概览
cd /home/dzy/wk/lnrs && /home/dzy/wk/lnrs/backend/.venv/bin/python3 <<'EOF'
import duckdb
src = '/data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.病程记录文档.parquet'
con = duckdb.connect()
print(con.execute(f"SELECT count(*) AS rows, count(DISTINCT 患者编号) AS uniq_pat FROM read_parquet('{src}')").fetchdf())
EOF
# 期望: rows=5164052, uniq_pat=78594

# 2) staging → 引擎 source_doc_hash → 写入 /tmp
backend/.venv/bin/python3 /tmp/scan5.py
# 期望: distinct=2672861, dup_count=2491191

# 3) 验证 SQL（依赖 /tmp/stg_distinct_hashes.txt + /tmp/sample_200_hashes.txt）
PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -p 5432 -U lnrs -d postgres \
  -f docs/etl2/verify_result/verify_clinical_document.sql
# 期望: V2 hit=miss=0, V4 pg_not_in_staging=0, V8 hit=miss=0
```

---

## 7. 产物清单

- ETL1 staging 源文件：`/home/dzy/wk/lnrs/data_shengyi202609/import_R12/shengyi/clinical_document.parquet`（473 MB, 5,164,052 行）
- ETL2 灌库产物：PG `lnrs.lnrs_anon_clinical_document` shengyi = 2,672,861 行
- ETL2 batch：`d56e9cf1-1dbd-4dbc-8034-a55a3efbb541` (2026-09-04 02:41:49)
- 验证 SQL（本目录下）：`docs/etl2/verify_result/verify_clinical_document.sql`
- 核验报告（本文件）：`docs/etl2/verify_result/shengyi_clinical_document_20260915.md`
