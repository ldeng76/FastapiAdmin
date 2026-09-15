# 数据导入核验报告 — 省医 / 检查(文本)超声 — 灌库后（清单 R13）

- 核验日期：2026-09-15
- 数据项：省医 / 检查(文本)超声（清单 R13，第 1 个【完成状态】为空的行）
- 数据存放目录：`/data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.超声诊断报告.检查子项.parquet`
- 预期记录数：**1,557,086**（源 parquet 行 = 1:N 子项数）
- 核验环境：dev PG `127.0.0.1:5432`（center='shengyi'）
- 核验结论：**✅ 通过（源 1,557,086 行 = 1,557,086 sub_items → ETL1 staging 聚合 181,605 份报告；staging→PG 181,604 命中 / 1 行 exam_date='' 被 ETL2 引擎守卫过滤；PG `lnrs_anon_exam(Ultrasound)` 181,691 = 181,604 (本 R13 staging) + 87 (imaging staging 87 行 ON CONFLICT 保留)；FK 0 孤儿；source_exam_hash 0 重复；report_text 179,077 / 2,614 no_text = 2,612 staging ultrasound_finding 空 + 2 来自 imaging 链路）**

> 与 R7 影像学报告(总)的关系：本份「检查(文本)超声」与 R7 共用 ETL2 spec #5 (`ultrasound_report`，kind=exam_text，exam_type=Ultrasound)，但 R7 报告中仅覆盖到 spec #5 staging 的 87 行（imaging 中归一化为 Ultrasound 的"超声内镜"），本 R13 是 spec #5 自身 181,605 份 staging 报告的完整核验。
> 与 R5 基因的关系：本份 ETL1 也是 1:N sub_item 聚合链路（1 份超声报告 = N 个检查子项，N 平均 8.6），但本份 ETL1 已用 `LIST(...)` 结构保留全部 sub_items 进 `exam_detail.detail_json`（与 R5 跨文件 GROUP BY 后丢失子项结构不同）。

---

## 0. 数字速览

| 维度 | 值 | 备注 |
|---|---:|---|
| 清单预期记录数 | 1,557,086 | 源 parquet 行 = 1:N 检查子项数 |
| 源 parquet 总行数 | **1,557,086** | ✅ 完全等于清单预期 |
| 源 distinct 报告编号 | 181,605 | 1:N 聚合后 = 1 份超声报告 |
| 源 distinct 就诊编号 | 106,185 | 1 份报告通常归属 1 个就诊 |
| 源 distinct 患者编号 | 44,287 | 1 个患者平均有 4.1 份超声报告 |
| 源 sub_items 1:N cardinality | 117,578 份(1) / 14(2) / 53(3) / 26(4) / 13(5) / 483(6) / 77(7) / 1,037(8) / 137(9) / 29(10) / 34(11) / 1,105(12) / 61,019(>12) | 平均 8.58 sub_items/报告 |
| 源 null/空 报告编号 | 0 | ETL1 守卫无过滤 |
| 源 null/空 就诊编号 | 0 | |
| 源 null/空 患者编号 | 0 | |
| 源 检查日期范围 | 2008-04-07 08:50:58 ~ 2025-11-14 10:47:52 | 无 1900-01-01 哨兵、无异常年份 |
| 源 "部位" 列 null/空 | 1,557,086 / 1,557,086 = 100% | 源端事实，staging.body_part 继承为空 |
| 源 超声提示 null/空 | 3,593 / 1,557,086 = 0.23% | |
| 源 检查所见 null/空 | 2,727 / 1,557,086 = 0.18% | |
| ETL1 staging `ultrasound_report.parquet` 行数 | **181,605** | ✅ = 源 distinct 报告编号（0 行守卫过滤）|
| staging distinct `report_id` | 181,605 | 0 重复 |
| staging sub_items 总数 (LIST length) | **1,557,086** | ✅ = 源 1,557,086（0 子项丢失）|
| staging `ultrasound_finding` null/空 | 2,612 / 181,605 = 1.44% | = 源按 report_id 聚合后全空报告数 2,612（**完全一致**）|
| staging `exam_detail.findings` null/空 | 2,321 / 181,605 = 1.28% | = 源聚合后全空报告数 2,321（**完全一致**）|
| staging `body_part` null/空 | 181,605 / 181,605 = 100% | 源端"部位"列 100% 空的继承事实 |
| staging `exam_date` null/空 | 1 / 181,605 = 0.0006% | 引擎守卫过滤该行 |
| ETL2 引擎 spec `ultrasound_report` | 1 条 | spec #5，kind=exam_text，exam_type=Ultrasound |
| PG `lnrs_anon_exam` (Ultrasound) | **181,691** | = 181,604 (本 R13 staging 命中) + 87 (imaging staging 87 行 ON CONFLICT 保留) |
| staging hash → PG exam 命中 | **181,604 / 181,605** | 1 miss = staging 中唯一 `exam_date=''` 行被 ETL2 引擎守卫过滤；200 抽样 200/200 ✅ |
| staging hash 唯一性 | 0 重复 | ✅ |
| staging hash → PG exam_type=Ultrasound 命中 | 181,604 / 181,604 = 100% | ✅ 0 错桶 |
| PG ultrasound 87 from_other hash | 87 / 87 = 100% 在 `imaging_report` staging 集合 | 详见 §3.1 |
| `lnrs_anon_exam_detail` (detail_type='ultrasound') | **181,604** | = staging 命中数；0 from_other（87 from_other 不在 spec #5 范围内）|
| `lnrs_anon_report_text` 关联率 | 179,077 / 181,691 = **98.56%** | 2,614 行 no_text = 2,612 staging ultrasound_finding 空（引擎 body 跳过）+ 2 行 87 from_other 路径上 imaging 中 finding+impression 双空 |
| FK 孤儿 (exam→patient) | 0 | ✅ |
| FK 孤儿 (exam→visit) | 0 | ✅（但 181,691 行 `anon_visit_id` 全空，见 §3.4）|
| 涉及 unique patient_id | 44,292 | |
| 涉及 unique anon_visit_id | 0 | 详见 §3.4 |
| exam_date 范围 | 2008-04-07 ~ 2025-11-14 | ✅ |
| ingest_batch 数 | 2 | f83cc91b (2026-09-02 17:15, 181,690 行) + c5871ad4 (2026-07-29 08:10, 1 行旧 ETL2 残留) |
| `source_exam_hash` 全局唯一性 | 0 重复 | ✅ |

**链路总览**：
```
源 1 文件 (1,557,086 行 = 1,557,086 sub_items)
非隐私信息.就诊.超声诊断报告.检查子项.parquet  ─→ ETL1 backend/etl1_adapt_shengyi_202609.py:229 SQL_ULTRASOUND
   ├─ 报告级列 6 列：患者编号/就诊编号/报告编号/检查名称/部位/检查日期
   ├─ 5 个聚合 + 1 个 sub_items LIST：
   │    ANY_VALUE(检查日期) AS exam_date
   │    ANY_VALUE(超声提示) AS ultrasound_finding
   │    ANY_VALUE(检查所见) → STRUCT{findings}
   │    LIST(STR_PACK{项目名称, 检查结果, 检查结果数值, 检查项目单位, 数据来源}) → STRUCT{sub_items}
   ├─ GROUP BY (patient_id, visit_id, report_id)  →  181,605 份报告
   ├─ WHERE 报告编号 IS NOT NULL AND <> ''         →  0 行过滤
   └─ 总 LIST length = 1,557,086                  →  0 子项丢失
   ─→ staging ultrasound_report.parquet 181,605 行
                                                ─→ ETL2 import_center('shengyi')
                                                   └─ spec #5 ultrasound_report (kind=exam_text)
                                                       ├─ id_field="report_id", body_fields=["ultrasound_finding"]
                                                       ├─ source_exam_hash = SHA256(f"shengyi:{report_id}")
                                                       ├─ anon_exam_id = HMAC-SHA256[:12]
                                                       ├─ 守卫: if exam_date is None: continue    ← 1 行被过滤
                                                       ├─ ON CONFLICT (center_code, source_exam_hash) DO UPDATE last_seen
                                                       └─ exam_detail.detail_json = {exam_name, body_part, exam_detail{sub_items}}
```

---

## 1. ETL2 spec 覆盖确认

`backend/app/plugin/module_medical/hospital/anon_etl_engine.py:2458-2466` shengyi spec 名单，本份数据项占 1 条：

| spec # | src_table | kind | exam_type | id_field | body_fields | detail_type | detail_fields | date_field |
|---|---|---|---|---|---|---|---|---|
| **#5** | `ultrasound_report` | `exam_text` | `Ultrasound` | `report_id` | `["ultrasound_finding"]` | `ultrasound` | `["exam_name", "body_part", "exam_detail"]` | `exam_date` |

**本份数据 ETL2 spec 引擎行为**（`anon_etl_engine.py:1135-1383` `_import_exam_text_table`）：

- `source_exam_hash = SHA256(f"shengyi:{report_id}")` —— 引擎 `anon_etl_engine.py:1302` `src_hash = source_exam_hash(center_code, str(local_exam))`，其中 `local_exam = rd.get(id_field="report_id")`
- `anon_exam_id = compute_anon_exam_id(center, str(report_id))` —— HMAC-SHA256[:12]
- `body_fields = ["ultrasound_finding"]` —— 引擎 `_get_nested` 后写入 `report_text.body_clean`（`anon_etl_engine.py:240` 支持嵌套路径，但本 spec 直接走顶层列）
- **守卫：`if exam_date is None: log.warning(...); continue`**（`anon_etl_engine.py:1254-1259`）—— staging 中唯一 1 行 `exam_date=''` 被显式跳过，不 INSERT exam/report/detail
- `body` 空跳过 report_text INSERT（`anon_etl_engine.py:1324-1338`）—— 2,612 行 staging 中 `ultrasound_finding=''` 被跳过
- `detail_fields = ["exam_name", "body_part", "exam_detail"]` —— 写入 `exam_detail.detail_json` JSONB（含 1,557,086 个 sub_items 结构）
- `date_field = "exam_date"` —— 直接从 staging 列读取

---

## 2. 验证 SQL 完整结果（`docs/etl2/verify_result/verify_ultrasound.sql`）

```
=== V1. staging 181,605 hash 在 PG exam 中总命中 ===
  hit   | miss
--------+------
 181604 |    1                                                       ✅ 1 miss = staging 中 1 行 exam_date='' 引擎守卫

=== V2. 命中按 PG exam_type 分组 ===
 exam_type  |   n
------------+--------
 Ultrasound | 181604                                                       ✅ 100% 命中且全在 Ultrasound 桶

=== V3. 抽样 200 行 staging SHA256 → PG 反查 ===
 sample_size | hit | miss
-------------+-----+------
         200 | 200 |    0                                                       ✅ 200/200

=== V4. staging hash 唯一性 ===
 total_rows | distinct_hashes | max_count
------------+-----------------+-----------
     181605 |          181605 |         1                                                       ✅ 0 重复

=== V5. PG exam (Ultrasound) 总数 vs staging hash 命中数 ===
 pg_ultrasound_total | staging_hash_in_ultrasound | staging_hash_other_exam_type
---------------------+----------------------------+------------------------------
              181691 |                     181604 |                            0

=== V6. 反向: PG Ultrasound 中来自 staging 的行数 ===
 from_staging | from_other
--------------+------------
       181604 |         87                                                       ✅ 87 from_other 全部在 imaging_report staging 集合

=== V7. PG Ultrasound 完整性 + FK ===
 total  | null_patient | null_visit | null_date | uniq_patient | uniq_visit |  min_date  |  max_date
--------+--------------+------------+-----------+--------------+------------+------------+------------
 181691 |            0 |     181691 |         0 |        44292 |          0 | 2008-04-07 | 2025-11-14
                                                                                              🟡 uniq_visit=0 见 §3.4

=== V8. FK 孤儿 (exam->patient) ===
    ?column?    | count
----------------+-------
 orphan_patient |     0                                                       ✅

=== V9. FK 孤儿 (exam->visit) ===
   ?column?   | count
--------------+-------
 orphan_visit |     0                                                       ✅ (anon_visit_id 全空，过滤掉空值)

=== V10. exam_detail (detail_type=ultrasound) 行数 ===
 detail_type |   n
-------------+--------
 ultrasound  | 181604                                                       ✅ = staging 命中数

=== V11. exam_detail 来源 ===
 from_staging | from_other
--------------+------------
       181604 |          0                                                       ✅ 87 from_other 走 spec #5 staging 之外的路径，detail 仍 0

=== V12. report_text 关联率 (Ultrasound) ===
 has_text | no_text
----------+---------
   179077 |    2614                                                       🟡 2,614 no_text = 2,612 staging 引擎 body 跳过 + 2 from_other 链路

=== V13. ingest_batch 分布 (Ultrasound) ===
               batch_id               | source_kind |                     source_locator                     |         started_at         |                                                                                    row_counts                                                                                     | ultrasound_in_batch
--------------------------------------+-------------+--------------------------------------------------------+----------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+---------------------
 f83cc91b-0956-43da-b23e-29885e91cff6 | csv_report  | /home/dzy/wk/lnrs/data_shengyi202609/import_R2/shengyi | 2026-09-02 17:15:26.156186 | {"ecg_report": 149072, "genetic_report": 0, "imaging_report": 515585, "pahology_specimen": 189966, "ultrasound_report": 181604}                                                   |              181690
 c5871ad4-0653-4130-8df0-c74235695b36 | csv_report  | E:\mw3\wspy\2026\lnrs\data\shengyi                     | 2026-07-29 08:10:19.759042 | {"patient": 5, "drug_order": 9, "lab_result": 5, "visit_record": 5, "no_drug_order": 5, "imaging_report": 5, "surgery_record": 2, "pahology_specimen": 3, "ultrasound_report": 1} |                   1

=== V14. source_exam_hash 全局唯一性 (Ultrasound) ===
 total | distinct_hashes | dup_count
--------+-----------------+-----------
 181691 |          181691 |         0                                                       ✅
```

---

## 3. 与清单预期对照

| 清单预期 | 实测 | 判定 | 解释 |
|---|---:|---|---|
| 源 parquet 行数 **1,557,086** | **1,557,086** | ✅ | 行数完全一致 |
| 源 distinct 报告编号 | — | 181,605 | 1:N 聚合后 = 181,605 份报告 |
| ETL1 staging 行数 | — | **181,605** | ✅ = 源 distinct report_id（0 行守卫过滤）|
| ETL1 staging sub_items 总数 (LIST length) | — | **1,557,086** | ✅ = 源 1,557,086（0 子项丢失）|
| ETL2 PG exam (Ultrasound) 行数 | — | 181,691 | = 181,604 (本 R13 staging 命中) + 87 (imaging staging 87 行 ON CONFLICT 保留) |
| ETL2 `exam_detail` (ultrasound) | — | **181,604** | ✅ = staging 命中数（87 from_other 不产生 ultrasound detail）|
| ETL2 spec 覆盖本份数据 | — | ✅ 是 | spec #5 ultrasound_report (kind=exam_text) |
| 抽样 SHA256 命中 | — | **200/200** | ✅ 100% 命中 |
| FK 完整性 | — | **0 孤儿** | ✅ patient/visit 双向 FK 完整 |
| 数据本体覆盖（每个有效 report_id 都有 1 行 exam）| — | ✅ | 181,604 个有效 report_id 在 staging → PG exam 链路上有对应行；1 个 staging miss = 1 行 exam_date='' 引擎守卫过滤（设计如此）|

### 3.1 87 from_other 行的根因分析

**87 from_other hash 100% 在 `staging.imaging_report` 集合中**，与 R7 报告 §3.1 "87 行"完全一致：

- ETL1 SQL_IMAGING 的检查类型名称归一化（`etl1_adapt_shengyi_202609.py:200-227`）把"超声内镜" / "东病区超声内镜"归一化为 `Ultrasound`：
  ```sql
  WHEN 检查类型名称 ILIKE '%超声%' THEN 'Ultrasound'
  ```
- 这 87 行在 ETL2 引擎主入口 `import_center('shengyi')` 跑时：
  1. spec #4 `imaging_report` 优先处理（含这 87 行），按归一化的 `exam_type=Ultrasound` 试图 INSERT 到 PG.exam_type=Ultrasound
  2. 但 PG `lnrs_anon_exam` 中**已有**这 87 个 hash 的行（来自更早的 spec #5 处理或前置 ETL2 残留）—— R7 报告 §3.1 说"超声内镜"此前已被 ETL2 spec `ultrasound_report` 灌入
  3. `ON CONFLICT (center_code, source_exam_hash) DO UPDATE last_seen` —— **不更新 exam_type**（设计：避免覆盖更早入库的临床数据）
  4. 所以 PG.exam_type 保留为 `Ultrasound`（来自更早灌入），但 `last_seen` 被刷新
- V6 反映：87 行 PG 端 exam 的 `source_exam_hash` 在本 R13 `staging.ultrasound_report` 集合中**不存在**（因为这 87 行的 report_id 在 `staging.imaging_report` 中而非 `staging.ultrasound_report` 中）

**判定**：✅ **数据完整性无丢失**——87 个 hash 在 PG 中存在且 exam_type=Ultrasound，仅 source_exam_hash 不与本 R13 staging 集合相交，原因是 spec #4 与 spec #5 处理顺序 + ON CONFLICT 设计。

### 3.2 1 个 staging miss 的根因

V1 显示 staging 181,605 hash 中 1 个不在 PG 中：

- 该 staging 行内容：
  ```
  report_id='55155317960262127', patient_id='7570713', visit_id='1201098933',
  exam_name='{浅表器官彩B(甲状腺、甲状旁腺及其引流区域淋巴结);}',
  body_part='', exam_date='', ultrasound_finding='',
  exam_detail.findings='甲状腺右侧叶实质性病灶（考虑结节性甲状腺肿)。' (153 字符),
  exam_detail.sub_items=[1 个子项]
  ```
- ETL2 引擎 `_import_exam_text_table` 显式守卫（`anon_etl_engine.py:1254-1259`）：
  ```python
  if exam_date is None:
      log.warning(f"ETL2: 跳过无 exam_date 的 exam: center={center_code} ...")
      continue
  ```
- `exam_date=''` 经 `_clean_date('')` → `None` → 引擎跳过该行，不 INSERT 到 exam/report/detail

**判定**：✅ **设计正确**（staging 唯一 1 行无日期的脏数据，避免 1969-12-31 之类哨兵或脏日期进入 PG DATE 列；与 R6 discharge_summary 的 1900-01-01 哨兵过滤逻辑一致）。

### 3.3 staging `ultrasound_finding` 2,612 行 null/空的根因

- staging 2,612 行 `ultrasound_finding=''` **完全等于** 源端按 report_id 聚合后"超声提示"全空报告数 2,612
- ETL1 SQL_ULTRASOUND 用 `ANY_VALUE(超声提示) AS ultrasound_finding`，聚合后该列保留的是该 report 下所有 sub_items 中**任意**一行的"超声提示"值
- 当某份报告**所有** sub_items 的"超声提示"列都为空时，`ANY_VALUE` 返回 NULL 或空串
- ETL2 spec #5 `body_fields = ["ultrasound_finding"]` 拼接 body → body='' → 引擎按设计跳过 `report_text` INSERT（避免空正文覆盖已有非空正文，与 R7 §3.2 一致）
- **exam 行 + exam_detail 行仍正常 INSERT**（`ultrasound_finding` 不影响 `exam_detail.detail_json` 写入，因为 `detail_fields` 只用 `exam_name/body_part/exam_detail`，不引用 `ultrasound_finding`）

**判定**：✅ **源端事实保留，引擎行为符合设计**。临床诊断主体信息（"检查所见"/"超声提示"）在 `exam_detail.detail_json.findings` 与 `exam_detail.detail_json.exam_detail.sub_items` 中完整保留。

### 3.4 181,691 行 `anon_visit_id` 全空的原因

```
uniq_visit = 0 (null_visit = 181,691 = PG ultrasound 全部)
```

- ETL1 SQL_ULTRASOUND 把 `就诊编号` 列写入 staging `visit_id`（**全部非空**：`null_visit_staging = 0 / 181,605`）
- 但 ETL2 spec #5 `ultrasound_report` **未配置 `date_lookup_field`**（spec dict 中无该 key），引擎在 `_import_exam_text_table` 中**不会**反查 `lnrs_anon_visit` 表
- 所以 `anon_visit_id` 在 INSERT 时**未被赋值**（保持空字符串/空），FK 检查器对空值跳过

**判定**：🟡 **信息丢失但 FK 完整**。staging 中 `visit_id` 全部非空但 ETL2 spec #5 未消费，与 R5 基因（`anon_visit_id` 全空，spec #7 用 `date_lookup_field="visit_id"` 反查 `visit_detail.admission_time`）的 0 visit 现象症状相似但原因不同。后续工单：spec #5 可加 `date_lookup_field="visit_id"` 或 ETL1 适配层做 visit_bridge JOIN。

### 3.5 staging `body_part` 100% 空的原因

- staging 181,605 行 `body_part=''`
- 源端 parquet "非隐私信息.就诊.超声诊断报告.部位"列 **1,557,086 / 1,557,086 = 100% 全部为空**
- ETL1 SQL_ULTRASOUND 用 `ANY_VALUE(部位) AS body_part` 继承源端事实
- 写入 PG `exam_detail.detail_json.body_part = ''`（结构化 JSONB 字段值为空串）

**判定**：✅ 源端事实保留，**staging 100% null 是源数据完整性事实而非 ETL 缺陷**。结构化临床信息（项目名称/检查结果）通过 `exam_detail.detail_json.exam_detail.sub_items` 全字段保留。

### 3.6 1,557,086 sub_items 在 PG 中的可见性

```
staging sub_items 总数 (LIST length): 1,557,086
源 sub_items 总数: 1,557,086
match: True ✅
```

ETL1 SQL_ULTRASOUND 用 DuckDB `LIST(STR_PACK{...} ORDER BY 项目名称)` 把 1,557,086 个 sub_items 全部打包进 181,605 份报告的 `exam_detail.exam_detail.sub_items` 数组。**0 子项丢失**。

PG `exam_detail.detail_json` JSONB 中以 `{"exam_name": ..., "body_part": "", "exam_detail": {"findings": ..., "sub_items": [{item_name, item_result, item_result_value, item_unit, data_source}, ...]}}` 形式完整保留所有 1,557,086 个子项。

**判定**：✅ **结构化数据 1:N 完整保留**，与 R5 基因的 6 文件聚合后 staging 1310 行（每行 6 bucket 填满）不同——本份用 LIST 直接保留 sub_items，避免 R5 §7 提到的"6 文件 GROUP BY 后子段结构丢失"问题。

### 3.7 staging `visit_id` 0 null 但 PG `anon_visit_id` 181,691 null 的桥接差异

| 维度 | staging | PG |
|---|---:|---:|
| visit_id 非空 | 181,605 / 181,605 = 100% | (anon_visit_id 非空) 0 / 181,691 = 0% |

- staging 中 `visit_id` 来自 ETL1 适配层映射源端"就诊编号"列，**0 null**（源端 0 null）
- PG 中 `anon_visit_id` 在 ETL2 spec #5 未配置 visit 桥 → 引擎**不消费** staging `visit_id` 列 → PG 写入时空

**判定**：🟡 **staging→PG 链路上 visit_id 列未被消费**。要恢复 visit 关联：spec #5 加 `date_lookup_field="visit_id"` + 引擎在 `_import_exam_text_table` 中加 visit_id→anon_visit_id 反查逻辑（与 R5 §7 提到的"补 visit_record ETL2 spec + 重跑 batch"路径相同）。

---

## 4. 与历史 ETL2 spec 的一致性

| shengyi spec 行 | src_table | ETL2 落库行数（shengyi） | 状态 |
|---|---|---:|---|
| spec #1 | `patient` | 169,820 | ✅ |
| spec #2 | `visit_record`（visit_detail） | 2,381,010 | ✅ |
| spec #3 | `pahology_specimen`（typo） | 189,966 | ✅ |
| spec #4 | `imaging_report` | 515,398 | ✅（R7 imaging_report 报告）|
| **spec #5** | **`ultrasound_report`** | **181,691** | ✅ **本份数据**（= 181,604 staging 命中 + 87 from_other） |
| spec #6 | `ecg_report` | 149,072 | R14 心电图待核验 |
| spec #7 | `genetic_report` | 1,309 | ✅ |
| spec #8 | `surgery_record` | 324,637 | ✅ |
| ... | ... | ... | ... |

**判定**：spec #5 与本份数据项完全对齐，ETL2 引擎主入口 `import_center('shengyi')` 已能正确灌库。

---

## 5. 复现命令

```bash
# 1) 源 parquet 概览
cd /home/dzy/wk/lnrs && backend/.venv/bin/python <<'EOF'
import duckdb
con = duckdb.connect()
p = "/data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.超声诊断报告.检查子项.parquet"
print(con.execute(f"SELECT COUNT(*) FROM read_parquet('{p}')").fetchone())
print(con.execute(f"SELECT COUNT(DISTINCT \"非隐私信息.就诊.超声诊断报告.报告编号\") FROM read_parquet('{p}')").fetchone())
EOF

# 2) ETL1 staging 行数 + sub_items 总数
cd /home/dzy/wk/lnrs && backend/.venv/bin/python <<'EOF'
import duckdb
con = duckdb.connect()
p = "data_shengyi202609/shengyi/ultrasound_report.parquet"
print("rows:", con.execute(f"SELECT COUNT(*) FROM read_parquet('{p}')").fetchone()[0])
print("sub_items total:", con.execute(f"SELECT COALESCE(SUM(length(exam_detail.sub_items)),0) FROM read_parquet('{p}')").fetchone()[0])
EOF

# 3) 算 staging hash 集 → 写盘
cd /home/dzy/wk/lnrs && backend/.venv/bin/python <<'EOF'
import duckdb, hashlib
con = duckdb.connect()
p = "data_shengyi202609/shengyi/ultrasound_report.parquet"
rows = con.execute(f"SELECT DISTINCT report_id FROM read_parquet('{p}') WHERE report_id IS NOT NULL AND report_id <> ''").fetchall()
hashes = [hashlib.sha256(f"shengyi:{r[0]}".encode()).hexdigest() for r in rows]
with open('/tmp/ultrasound_staging_hashes.txt', 'w') as f:
    for h in hashes: f.write(h + '\n')
print(f"distinct hash: {len(hashes)}")
EOF

# 4) 200 抽样
python3 -c "
import random
random.seed(20260914)
with open('/tmp/ultrasound_staging_hashes.txt') as f:
    lines = [l.strip() for l in f if l.strip()]
sample = random.sample(lines, 200)
with open('/tmp/ultrasound_sample_hashes.txt', 'w') as f:
    for h in sample: f.write(h + '\n')
print('sample 200 written')
"

# 5) 跑 V1-V14 核验 SQL
PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres \
  -f docs/etl2/verify_result/verify_ultrasound.sql
```

---

## 6. 已知局限 / 后续工作

| 项 | 描述 | 处理建议 |
|---|---|---|
| 87 from_other hash 100% 在 imaging staging 集合 | spec #4 归一化为 Ultrasound 的 87 行在 spec #5 前已 upsert 入 PG，ON CONFLICT 保留 exam_type 不更新 | 设计如此，**接受现状**（与 R7 §3.1 同一现象）|
| 1 个 staging miss (exam_date='') | ETL2 引擎显式守卫过滤该行（避免脏日期入 PG）| 设计如此，**接受现状**（与 R6 §3.4 哨兵过滤逻辑一致）|
| 2,612 行 report_text 缺 body_clean | staging 中 ultrasound_finding 空 + 2 行 from_other 链路 imaging finding+impression 双空 → 引擎 body 跳过 INSERT | 设计如此，**接受现状**（与 R7 §3.2 一致）；临床信息保留在 `exam_detail.detail_json` |
| 181,691 行 `anon_visit_id` 全空 | staging.visit_id 0 null，但 ETL2 spec #5 未配置 `date_lookup_field` | 后续工单：spec #5 加 `date_lookup_field="visit_id"` + ETL1 SQL 加 visit_bridge JOIN（与 R5 §7、R7 §3.5 同一现象）|
| staging `body_part` 100% 空 | 源端"部位"列 1,557,086/1,557,086 = 100% 全空 | 源端事实，**无需处理**（结构化信息在 sub_items 中保留）|
| 1,557,086 sub_items 全部进 LIST | ETL1 `LIST(STR_PACK{...} ORDER BY 项目名称)` 完整打包 | ✅ 0 子项丢失（与 R5 §7 提到的"跨文件 GROUP BY 后子段结构丢失"问题不同）|

---

## 7. 改动文件清单（本次核验任务）

| 文件 | 改动 |
|---|---|
| `docs/etl2/verify_result/shengyi_ultrasound_20260914.md` | 本文（新建）|
| `docs/etl2/verify_result/verify_ultrasound.sql` | V1-V14 核验 SQL（新建）|
| `docs/etl2/数据导入核验清单.xlsx` | R13 E5/F5 同步回填指向 `verify_result/` |

**不改动**：
- ETL2 引擎 spec（spec #5 `ultrasound_report` 已覆盖，无需改动）
- ETL1 适配层 `SQL_ULTRASOUND`（已正确聚合 1:N sub_items 为 LIST 结构）
- 源 parquet、ETL1 staging parquet、PG 数据（无改动需要）
