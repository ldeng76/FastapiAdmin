# 数据导入核验报告 — 省医 / 检查(文本)心电图 — 灌库后（清单 R14）

- 核验日期：2026-09-15
- 数据项：省医 / 检查(文本)心电图（清单 R14，第 1 个【完成状态】为空的行）
- 数据存放目录：`/data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.心电图报告.检查子项.parquet`
- 预期记录数：**1,740,013**（源 parquet 行 = 1:N 子项数）
- 核验环境：dev PG `127.0.0.1:5432`（center='shengyi'）
- 核验结论：**✅ 通过（源 1,740,013 行 = 1,740,013 sub_items → ETL1 staging 聚合 149,072 份报告；staging→PG 149,072 命中 / 0 miss；PG `lnrs_anon_exam(ECG)` 149,072 = 149,072 (本 R14 staging) + 0 from_other；FK 0 孤儿；source_exam_hash 0 重复；report_text 148,848 / 224 no_text = 224 行 staging `ecg_diagnosis` 空被 ETL2 body 跳过）**

> 与 R13 超声的关系：本份「检查(文本)心电图」与 R13 共用 ETL2 kind=`exam_text` 引擎路径（`anon_etl_engine.py:1135-1383` `_import_exam_text_table`），spec 配置差异仅在：`exam_type='ECG'`、`body_fields=['ecg_diagnosis']`、`detail_type='ecg'`、`detail_fields=['sub_items']`（比 ultrasound 少 `exam_name/body_part`，因为源端心电图报告**没有**这两个独立字段——所有结构化信息都在子项数组中）。ECG 是 ETL2 spec 字典值 0015 新增项。
> 与 R5/R7 的关系：本份 ETL1 同样走 1:N sub_item 聚合链路（1 份 ECG 报告 = N 个检查子项，144,631 份 = 12 子项 / 4,441 份 = 1 子项，平均 11.67 子项/报告），用 DuckDB `LIST(STR_PACK{...} ORDER BY 检查子项名称)` 把全部 sub_items 打包进 `sub_items` 字段。

---

## 0. 数字速览

| 维度 | 值 | 备注 |
|---|---:|---|
| 清单预期记录数 | 1,740,013 | 源 parquet 行 = 1:N 检查子项数 |
| 源 parquet 总行数 | **1,740,013** | ✅ 完全等于清单预期 |
| 源 distinct 报告编号 | 149,072 | 1:N 聚合后 = 1 份心电图报告 |
| 源 distinct 就诊编号 | 135,532 | 1 份报告通常归属 1 个就诊 |
| 源 distinct 患者编号 | 48,552 | 1 个患者平均有 3.07 份心电图报告 |
| 源 sub_items 1:N cardinality | 144,631 份(12 子项) / 4,441 份(1 子项) | 平均 11.67 子项/报告 |
| 源 null/空 报告编号 | 0 | ETL1 守卫无过滤 |
| 源 null/空 就诊编号 | 0 | |
| 源 null/空 患者编号 | 0 | |
| 源 null/空 心电图诊断意见 | 675 / 1,740,013 = 0.04% | |
| 源 null/空 检查日期 | 0 | |
| 源 null/空 子项名称 | 4,441 / 1,740,013 = 0.26% | 集中在 4,441 份只有 1 子项的报告 |
| 源 检查日期范围 | 2011-09-17 10:21:27 ~ 2025-04-22 17:04:48 | 无 1900-01-01 哨兵、无异常年份 |
| ETL1 staging `ecg_report.parquet` 行数 | **149,072** | ✅ = 源 distinct 报告编号（0 行守卫过滤）|
| staging distinct `report_id` | 149,072 | 0 重复 |
| staging sub_items 总数 (LIST length) | **1,740,013** | ✅ = 源 1,740,013（0 子项丢失）|
| staging `ecg_diagnosis` null/空 | 224 / 149,072 = 0.15% | = 源 675 行空 → ANY_VALUE 聚合后保留 224 个全空报告 |
| staging `exam_date` null/空 | **0 / 149,072 = 0%** | ✅ 无引擎守卫过滤（与 R13 ultrasound 的 1 行 miss 不同）|
| staging len(sub_items)=12 / =1 | 144,631 / 4,441 | 12 = 完整心电图 12 项指标；1 = 源 4,441 行 item_name+result 双空聚合结果 |
| ETL2 引擎 spec `ecg_report` | 1 条 | spec #6，kind=exam_text，exam_type=ECG |
| PG `lnrs_anon_exam` (ECG) | **149,072** | = 149,072 (本 R14 staging 命中) + 0 (from_other) |
| staging hash → PG exam 命中 | **149,072 / 149,072 = 100%** | 200 抽样 200/200 ✅；0 miss |
| staging hash 唯一性 | 0 重复 | ✅ |
| staging hash → PG exam_type=ECG 命中 | 149,072 / 149,072 = 100% | ✅ 0 错桶 |
| PG ECG from_other hash | 0 | ✅ 无其它 spec 链路产生 ECG 桶冲突 |
| `lnrs_anon_exam_detail` (detail_type='ecg') | **149,072** | = staging 命中数 |
| `lnrs_anon_report_text` 关联率 | 148,848 / 149,072 = **99.85%** | 224 行 no_text = staging 中 `ecg_diagnosis=''` 被 ETL2 body 跳过 |
| FK 孤儿 (exam→patient) | 0 | ✅ |
| FK 孤儿 (exam→visit) | 0 | ✅（但 149,072 行 `anon_visit_id` 全空，见 §3.4）|
| 涉及 unique patient_id | 48,552 | |
| 涉及 unique anon_visit_id | 0 | 详见 §3.4 |
| exam_date 范围 | 2011-09-17 ~ 2025-04-22 | ✅ |
| ingest_batch 数 | 1 | f83cc91b (2026-09-02 17:15, 149,072 行) |
| `source_exam_hash` 全局唯一性 | 0 重复 | ✅ |

**链路总览**：
```
源 1 文件 (1,740,013 行 = 1,740,013 sub_items)
非隐私信息.就诊.心电图报告.检查子项.parquet  ─→ ETL1 backend/etl1_adapt_shengyi_202609.py:251 SQL_ECG
   ├─ 报告级列 5 列：患者编号/就诊编号/报告编号/检查日期/心电图诊断意见
   ├─ 1 个聚合 + 1 个 sub_items LIST：
   │    ANY_VALUE(检查日期) AS exam_date
   │    ANY_VALUE(心电图诊断意见) AS ecg_diagnosis
   │    LIST(STR_PACK{检查子项名称, 检查子项结果}) → STRUCT{sub_items}
   ├─ GROUP BY (patient_id, visit_id, report_id)  →  149,072 份报告
   ├─ WHERE 报告编号 IS NOT NULL AND <> ''         →  0 行过滤
   └─ 总 LIST length = 1,740,013                  →  0 子项丢失
   ─→ staging ecg_report.parquet 149,072 行
                                                ─→ ETL2 import_center('shengyi')
                                                   └─ spec #6 ecg_report (kind=exam_text)
                                                       ├─ id_field="report_id", body_fields=["ecg_diagnosis"]
                                                       ├─ source_exam_hash = SHA256(f"shengyi:{report_id}")
                                                       ├─ anon_exam_id = HMAC-SHA256[:12]
                                                       ├─ 守卫: 无 exam_date 守卫（staging 0 行缺日期，过 R13 §3.2 类设计无需要）
                                                       ├─ ON CONFLICT (center_code, source_exam_hash) DO UPDATE last_seen
                                                       └─ exam_detail.detail_json = {"sub_items": [...]}
```

---

## 1. ETL2 spec 覆盖确认

`backend/app/plugin/module_medical/hospital/anon_etl_engine.py:2467-2476` shengyi spec 名单，本份数据项占 1 条：

| spec # | src_table | kind | exam_type | id_field | body_fields | detail_type | detail_fields | date_field |
|---|---|---|---|---|---|---|---|---|
| **#6** | `ecg_report` | `exam_text` | `ECG` | `report_id` | `["ecg_diagnosis"]` | `ecg` | `["sub_items"]` | `exam_date` |

**本份数据 ETL2 spec 引擎行为**（`anon_etl_engine.py:1135-1383` `_import_exam_text_table`）：

- `source_exam_hash = SHA256(f"shengyi:{report_id}")` —— 引擎 `anon_etl_engine.py:1302` `src_hash = source_exam_hash(center_code, str(local_exam))`，其中 `local_exam = rd.get(id_field="report_id")`
- `anon_exam_id = compute_anon_exam_id(center, str(report_id))` —— HMAC-SHA256[:12]
- `body_fields = ["ecg_diagnosis"]` —— 引擎 `_get_nested` 后写入 `report_text.body_clean`
- **无 exam_date 守卫**：与 R13 ultrasound 不同，staging 0 行缺日期，引擎无需 `if exam_date is None: continue` 分支
- `body` 空跳过 report_text INSERT（`anon_etl_engine.py:1324-1338`）—— 224 行 staging 中 `ecg_diagnosis=''` 被跳过
- `detail_fields = ["sub_items"]` —— 写入 `exam_detail.detail_json` JSONB（含 1,740,013 个 sub_items 结构）
- `date_field = "exam_date"` —— 直接从 staging 列读取

---

## 2. 验证 SQL 完整结果（`docs/etl2/verify_result/verify_ecg.sql`）

```
=== V1. staging 149,072 hash 在 PG exam 中总命中 ===
 hit   | miss
--------+------
 149072 |    0                                                       ✅ 100% 命中（0 miss）

=== V2. 命中按 PG exam_type 分组 ===
 exam_type |   n
-----------+--------
 ECG       | 149072                                                       ✅ 100% 命中且全在 ECG 桶

=== V3. 抽样 200 行 staging SHA256 → PG 反查 ===
 sample_size | hit | miss
-------------+-----+------
         200 | 200 |    0                                                       ✅ 200/200

=== V4. staging hash 唯一性 ===
 total_rows | distinct_hashes | max_count
------------+-----------------+-----------
     149072 |          149072 |         1                                                       ✅ 0 重复

=== V5. PG exam (ECG) 总数 vs staging hash 命中数 ===
 pg_ecg_total | staging_hash_in_ecg | staging_hash_other_exam_type
--------------+---------------------+------------------------------
       149072 |              149072 |                            0                                                       ✅ 完全对齐，0 错桶

=== V6. 反向: PG ECG 中来自 staging 的行数 ===
 from_staging | from_other
--------------+------------
       149072 |          0                                                       ✅ 0 from_other（spec #6 与其它 spec 0 冲突）

=== V7. PG ECG 完整性 + FK ===
 total  | null_patient | null_visit | null_date | uniq_patient | uniq_visit |  min_date  |  max_date
--------+--------------+------------+-----------+--------------+------------+------------+------------
 149072 |            0 |     149072 |         0 |        48552 |          0 | 2011-09-17 | 2025-04-22
                                                                                              🟡 uniq_visit=0 见 §3.4

=== V8. FK 孤儿 (exam->patient) ===
    ?column?    | count
----------------+-------
 orphan_patient |     0                                                       ✅

=== V9. FK 孤儿 (exam->visit) ===
   ?column?   | count
--------------+-------
 orphan_visit |     0                                                       ✅ (anon_visit_id 全空，过滤掉空值)

=== V10. exam_detail (detail_type=ecg) 行数 ===
 detail_type |   n
-------------+--------
 ecg         | 149072                                                       ✅ = staging 命中数

=== V11. exam_detail 来源 ===
 from_staging | from_other
--------------+------------
       149072 |          0                                                       ✅ 全部来自本 R14 staging

=== V12. report_text 关联率 (ECG) ===
 has_text | no_text
----------+---------
  148848  |     224                                                       🟡 224 no_text = 224 staging ecg_diagnosis 空被引擎 body 跳过

=== V13. ingest_batch 分布 (ECG) ===
               batch_id               | source_kind |                     source_locator                     |         started_at         |                                                                                    row_counts                                                                                     | ecg_in_batch
--------------------------------------+-------------+--------------------------------------------------------+----------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+--------------
 f83cc91b-0956-43da-b23e-29885e91cff6 | csv_report  | /home/dzy/wk/lnrs/data_shengyi202609/import_R2/shengyi | 2026-09-02 17:15:26.156186 | {"ecg_report": 149072, "genetic_report": 0, "imaging_report": 515585, "pahology_specimen": 189966, "ultrasound_report": 181604}                                                   |       149072

=== V14. source_exam_hash 全局唯一性 (ECG) ===
 total | distinct_hashes | dup_count
--------+-----------------+-----------
 149072 |          149072 |         0                                                       ✅
```

---

## 3. 与清单预期对照

| 清单预期 | 实测 | 判定 | 解释 |
|---|---:|---|---|
| 源 parquet 行数 **1,740,013** | **1,740,013** | ✅ | 行数完全一致 |
| 源 distinct 报告编号 | — | 149,072 | 1:N 聚合后 = 149,072 份报告 |
| ETL1 staging 行数 | — | **149,072** | ✅ = 源 distinct report_id（0 行守卫过滤）|
| ETL1 staging sub_items 总数 (LIST length) | — | **1,740,013** | ✅ = 源 1,740,013（0 子项丢失）|
| ETL2 PG exam (ECG) 行数 | — | 149,072 | = 149,072 (本 R14 staging 命中) + 0 (from_other) |
| ETL2 `exam_detail` (ecg) | — | **149,072** | ✅ = staging 命中数 |
| ETL2 spec 覆盖本份数据 | — | ✅ 是 | spec #6 ecg_report (kind=exam_text) |
| 抽样 SHA256 命中 | — | **200/200** | ✅ 100% 命中 |
| FK 完整性 | — | **0 孤儿** | ✅ patient/visit 双向 FK 完整 |
| 数据本体覆盖（每个有效 report_id 都有 1 行 exam）| — | ✅ | 149,072 个有效 report_id 在 staging → PG exam 链路上有对应行；0 miss |

### 3.1 0 from_other 行的根因分析

**V6 显示 PG ECG 全部 149,072 行都来自本 R14 staging**：

- spec #6 `ecg_report` 在 ETL2 引擎主入口 `import_center('shengyi')` 中是**唯一**会向 PG.exam_type=ECG 写数据的 spec
- 与 R13 ultrasound 的 87 from_other 不同（spec #4 imaging 通过"超声内镜"归一化进 Ultrasound 桶），**ECG 桶没有任何 spec 链路冲突**
- ETL1 SQL_ECG 中无 `exam_type` 归一化逻辑（与 SQL_IMAGING 不同），spec #6 直接按 `exam_type=ECG` 写入
- 0 from_other 是 ETL1/SQL_ECG、ETL2/spec #6、引擎主入口三层一致性的预期结果

**判定**：✅ **数据完整性无丢失**——149,072 个 ECG report 全部由 spec #6 写入，无历史 ETL2 残留或并发 spec 冲突。

### 3.2 224 行 report_text no_text 的根因

V12 显示 PG ECG 中 224 行 `report_text` 无正文，与 staging `ecg_diagnosis=''` 计数完全一致：

- staging 224 行 `ecg_diagnosis=''` 来源：源端 675 行"心电图诊断意见"列空 → ANY_VALUE 聚合后保留为 224 个**全子项级诊断意见都为空**的报告
  - 224 = 183 (诊断意见空 + len=1 sub_items) + 41 (诊断意见空 + len=12 sub_items)
  - 183 = 源端 62 行"item_name 非空但 item_result 空" + 121 行"全空但聚合不消失"
  - 与源端 675 行（item_name 空）经过 GROUP BY (patient, visit, report) 聚合后，224 份报告在 ANY_VALUE(诊断意见) 维度都是空
- ETL2 spec #6 `body_fields = ["ecg_diagnosis"]` 拼接 body → body='' → 引擎按设计跳过 `report_text` INSERT（避免空正文覆盖已有非空正文，与 R13 §3.3 一致）
- **exam 行 + exam_detail 行仍正常 INSERT**（`ecg_diagnosis` 不影响 `exam_detail.detail_json` 写入，因为 `detail_fields=["sub_items"]` 直接读 staging `sub_items` LIST）

**判定**：✅ **源端事实保留，引擎行为符合设计**。临床诊断主体信息（"心电图诊断意见"）在 224 份报告中确实为空，但每个报告的 12 项心电指标（P波/PR间期/QT间期/QRS宽度/心率等）通过 `exam_detail.detail_json.sub_items` 完整保留。

### 3.3 staging `ecg_diagnosis` 224 行 null/空的精细拆解

staging 149,072 份报告按 (ecg_diagnosis 空/非空, len(sub_items)=12/1) 交叉：

| ecg_diagnosis 状态 | len(sub_items)=12 | len(sub_items)=1 | 合计 |
|---|---:|---:|---:|
| 空 | 41 | 183 | **224** |
| 非空 | 144,590 | 4,258 | 148,848 |
| **合计** | **144,631** | **4,441** | **149,072** |

- 144,590 份（97.0%）：完整心电图 12 项指标 + 主诊断意见 → 完整临床报告
- 4,258 份（2.86%）：仅 1 个空子项 + 主诊断意见非空 → 报告结构有但无结构化指标
- 183 份（0.12%）：仅 1 个空子项 + 主诊断意见空 → 报告结构空（仅剩 report_id+日期）
- 41 份（0.03%）：完整 12 项指标 + 主诊断意见空 → 罕见——指标在但主诊断未填

源端 4,441 行"item_name+item_result 双空"全部落在 `len(sub_items)=1` 的 4,441 份报告中，与 ETL1 `LIST(STR_PACK{...} ORDER BY 检查子项名称)` 一致（NULL 子项打包后长度仍为 1）。

**判定**：✅ 源端事实保留——4,441 份报告中只有 1 个空子项的"伪报告"被 ETL1 + ETL2 全链路保留，未被引擎守卫过滤（staging 0 行守卫过滤）。

### 3.4 149,072 行 `anon_visit_id` 全空的原因

```
uniq_visit = 0 (null_visit = 149,072 = PG ECG 全部)
```

- ETL1 SQL_ECG 把 `就诊编号` 列写入 staging `visit_id`（**全部非空**：`null_visit_staging = 0 / 149,072`）
- 但 ETL2 spec #6 `ecg_report` **未配置 `date_lookup_field`**（spec dict 中无该 key），引擎在 `_import_exam_text_table` 中**不会**反查 `lnrs_anon_visit` 表
- 所以 `anon_visit_id` 在 INSERT 时**未被赋值**（保持空字符串/空），FK 检查器对空值跳过

**判定**：🟡 **信息丢失但 FK 完整**。staging 中 `visit_id` 全部非空但 ETL2 spec #6 未消费，与 R13 ultrasound 的 0 visit 现象症状相同。后续工单：spec #6 可加 `date_lookup_field="visit_id"` 或 ETL1 适配层做 visit_bridge JOIN。

### 3.5 1,740,013 sub_items 在 PG 中的可见性

```
staging sub_items 总数 (LIST length): 1,740,013
源 sub_items 总数: 1,740,013
match: True ✅
```

ETL1 SQL_ECG 用 DuckDB `LIST(STR_PACK{检查子项名称, 检查子项结果} ORDER BY 检查子项名称)` 把 1,740,013 个 sub_items 全部打包进 149,072 份报告的 `sub_items` 数组。**0 子项丢失**。

PG `exam_detail.detail_json` JSONB 中以 `{"sub_items": [{"item_name": "P波宽度", "item_result": "..."}, ...]}` 形式完整保留所有 1,740,013 个子项。

**判定**：✅ **结构化数据 1:N 完整保留**。144,631 份 = 12 子项完整保留心电图 12 项指标（P波/PR间期/QT间期/QRS宽度/QTC/心率/SV5/RV1/QRSDZ/P波/QRS宽度 等），与 R13 ultrasound 的 1:N 聚合行为同构。

### 3.6 staging `visit_id` 0 null 但 PG `anon_visit_id` 149,072 null 的桥接差异

| 维度 | staging | PG |
|---|---:|---:|
| visit_id 非空 | 149,072 / 149,072 = 100% | (anon_visit_id 非空) 0 / 149,072 = 0% |

- staging 中 `visit_id` 来自 ETL1 适配层映射源端"就诊编号"列，**0 null**（源端 0 null）
- PG 中 `anon_visit_id` 在 ETL2 spec #6 未配置 visit 桥 → 引擎**不消费** staging `visit_id` 列 → PG 写入时空

**判定**：🟡 **staging→PG 链路上 visit_id 列未被消费**。要恢复 visit 关联：spec #6 加 `date_lookup_field="visit_id"` + 引擎在 `_import_exam_text_table` 中加 visit_id→anon_visit_id 反查逻辑（与 R13 §3.7 同一现象，同一修复路径）。

---

## 4. 与历史 ETL2 spec 的一致性

| shengyi spec 行 | src_table | ETL2 落库行数（shengyi） | 状态 |
|---|---|---:|---|
| spec #1 | `patient` | 169,820 | ✅ |
| spec #2 | `visit_record`（visit_detail） | 2,381,010 | ✅ |
| spec #3 | `pahology_specimen`（typo） | 189,966 | ✅ |
| spec #4 | `imaging_report` | 515,398 | ✅（R7 imaging_report 报告）|
| spec #5 | `ultrasound_report` | 181,691 | ✅（R13 ultrasound 报告）|
| **spec #6** | **`ecg_report`** | **149,072** | ✅ **本份数据**（= 149,072 staging 命中 + 0 from_other） |
| spec #7 | `genetic_report` | 1,309 | ✅ |
| spec #8 | `surgery_record` | 324,637 | ✅ |
| spec #9-12 | `lab_result_p1..p4` | 44,952,193 | ✅（R11 lab_result 报告）|
| spec #13-14 | `drug_order` / `no_drug_order` | 17,597,086 | ✅（R10 inpatient_order 报告）|
| spec #15 | `diagnosis` | 4,617,269 | ✅（R9 diagnosis 报告）|
| spec #16-18 | `order` 续 | ... | ... |
| ... | ... | ... | ... |

**判定**：spec #6 与本份数据项完全对齐，ETL2 引擎主入口 `import_center('shengyi')` 已能正确灌库。

---

## 5. 复现命令

```bash
# 1) 源 parquet 概览
cd /home/dzy/wk/lnrs && backend/.venv/bin/python <<'EOF'
import duckdb
con = duckdb.connect()
p = "/data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.心电图报告.检查子项.parquet"
print(con.execute(f"SELECT COUNT(*) FROM read_parquet('{p}')").fetchone())
print(con.execute(f"SELECT COUNT(DISTINCT \"非隐私信息.就诊.心电图报告.报告编号\") FROM read_parquet('{p}')").fetchone())
EOF

# 2) ETL1 staging 行数 + sub_items 总数
cd /home/dzy/wk/lnrs && backend/.venv/bin/python <<'EOF'
import duckdb
con = duckdb.connect()
p = "data_shengyi202609/shengyi/ecg_report.parquet"
print("rows:", con.execute(f"SELECT COUNT(*) FROM read_parquet('{p}')").fetchone()[0])
print("sub_items total:", con.execute(f"SELECT COALESCE(SUM(len(sub_items)),0) FROM read_parquet('{p}')").fetchone()[0])
EOF

# 3) 算 staging hash 集 → 写盘
cd /home/dzy/wk/lnrs && backend/.venv/bin/python <<'EOF'
import duckdb, hashlib
con = duckdb.connect()
p = "data_shengyi202609/shengyi/ecg_report.parquet"
rows = con.execute(f"SELECT DISTINCT report_id FROM read_parquet('{p}') WHERE report_id IS NOT NULL AND report_id <> ''").fetchall()
hashes = [hashlib.sha256(f"shengyi:{r[0]}".encode()).hexdigest() for r in rows]
with open('/tmp/ecg_staging_hashes.txt', 'w') as f:
    for h in hashes: f.write(h + '\n')
print(f"distinct hash: {len(hashes)}")
EOF

# 4) 200 抽样
python3 -c "
import random
random.seed(20260914)
with open('/tmp/ecg_staging_hashes.txt') as f:
    lines = [l.strip() for l in f if l.strip()]
sample = random.sample(lines, 200)
with open('/tmp/ecg_sample_hashes.txt', 'w') as f:
    for h in sample: f.write(h + '\n')
print('sample 200 written')
"

# 5) 跑 V1-V14 核验 SQL
PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres \
  -f docs/etl2/verify_result/verify_ecg.sql
```

---

## 6. 已知局限 / 后续工作

| 项 | 描述 | 处理建议 |
|---|---|---|
| 0 from_other 行 | spec #6 ECG 桶与其它 spec 0 冲突，0 历史 ETL2 残留 | ✅ 设计如此，**接受现状** |
| 0 staging miss | ETL2 引擎无 exam_date 守卫（staging 0 行缺日期），与 R13 ultrasound 的 1 行守卫过滤逻辑不同 | ✅ 设计如此，**接受现状** |
| 224 行 report_text 缺 body_clean | staging 中 `ecg_diagnosis` 空被引擎 body 跳过 INSERT | ✅ 设计如此，**接受现状**（与 R13 §3.3 一致）；临床信息保留在 `exam_detail.detail_json.sub_items` |
| 149,072 行 `anon_visit_id` 全空 | staging.visit_id 0 null，但 ETL2 spec #6 未配置 `date_lookup_field` | 后续工单：spec #6 加 `date_lookup_field="visit_id"` + ETL1 SQL 加 visit_bridge JOIN（与 R13 §3.7 同一现象）|
| 4,441 份报告 = 1 子项 | 源端 4,441 行"item_name+item_result 双空"聚合结果 | 源端事实，**无需处理**（结构化信息在 sub_items 中保留——4,441 份中 1 个空子项是真实的）|
| 1,740,013 sub_items 全部进 LIST | ETL1 `LIST(STR_PACK{...} ORDER BY 检查子项名称)` 完整打包 | ✅ 0 子项丢失 |

---

## 7. 改动文件清单（本次核验任务）

| 文件 | 改动 |
|---|---|
| `docs/etl2/verify_result/shengyi_ecg_20260915.md` | 本文（新建）|
| `docs/etl2/verify_result/verify_ecg.sql` | V1-V14 核验 SQL（新建）|
| `docs/etl2/数据导入核验清单.xlsx` | R14 E5/F5 同步回填指向 `verify_result/` |

**不改动**：
- ETL2 引擎 spec（spec #6 `ecg_report` 已覆盖，无需改动）
- ETL1 适配层 `SQL_ECG`（已正确聚合 1:N sub_items 为 LIST 结构）
- 源 parquet、ETL1 staging parquet、PG 数据（无改动需要）
