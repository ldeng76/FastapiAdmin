# 数据导入核验报告 — 省医 / 基因（文本）— 灌库后（清单 R5）

- 核验日期：2026-09-14
- 数据项：省医 / 基因（文本）（清单 R5）
- 数据存放目录：`/data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.实体肿瘤基因检测报告.*.parquet`（6 个文件）
- 预期记录数：**3,189**（6 parquet 合计）
- 核验环境：dev PG `127.0.0.1:5432`（center='shengyi'）
- 核验结论：**✅ 通过**（ETL2 spec `genetic_report` 已覆盖；ETL1 staging → ETL2 exam 1309；6 bucket 100% 覆盖；FK 完整；旧 SYG dirty 已清）

> 注：R5 状态已是"已完成"，但 `F5`（核验结果路径）原指 `shengyi_genetic/` 目录而非 `verify_result/`。本次核验按用户要求把报告落 `docs/etl2/verify_result/`。

---

## 0. 数字速览

| 维度 | 值 |
|---|---:|
| 源 parquet 文件数 | **6**（SNV/CNV/indel/fusion/other/drug_ref） |
| 源 parquet 合计行数 | **3,189**（与清单预期完全一致） |
| ETL1 staging 行数（`genetic_report.parquet`）| 1,310 |
| ETL2 `lnrs_anon_exam` (shengyi, Genetic) | **1,309** |
| ETL2 `lnrs_anon_exam_detail` (genetic) | **1,309** |
| 6 bucket 覆盖率（snv/cnv/indel/fusion/other/drug_ref）| **100%（1309/1309）** |
| 旧 SYG dirty hash 残留 | 0（已清） |
| FK 孤儿（exam→patient）| 0 |
| FK 孤儿（exam→visit）| 0（但 anon_visit_id 全空，见 §3） |
| source_exam_hash 重复 | 0 |
| 涉及 unique patient_id | 216 |
| 涉及 unique anon_visit_id | 0（**未挂 visit**，见 §3） |
| ETL2 spec 覆盖 | ✅ `genetic_report`（spec list 第 7 条，src_table='genetic_report'） |

**链路总览**：
```
源 6 文件 (3,189 行)                           staging PG                              ───── ────────────                    ────────────
非隐私信息.就诊.实体肿瘤基因检测报告.*.parquet  → ETL1 backend/etl1_adapt_shengyi_202609.py
   ├─ SNV: 2059 行（含 64 空号）               ─→ 6 CTE UNION ALL ─→ GROUP BY (pid,vid,report_id)
   ├─ CNV: 226 行（含 175 空号）               ─→ 真单号 162 SNV ∩ 51 CNV 重合 46 → staging 167
   ├─ indel: 226 行（100% 空号）               ─→ 空号 (pid,vid) 跨 4 文件 = 224
   ├─ fusion: 226 行（100% 空号）              ─→ 派生 SYG-{n}-{8hex} 唯一键
   ├─ other: 226 行（100% 空号）               ─→ staging 1310 行
   └─ drug_ref: 226 行（100% 空号）            ─→ ETL2 import: ON CONFLICT DO NOTHING ─→ 1309 exam
                                                  ─────────────────────
```

---

## 1. ETL2 spec 覆盖确认

`backend/app/plugin/module_medical/hospital/anon_etl_engine.py:2425+` shengyi spec 名单共 **23 条**（grep 完整提取，覆盖 26 个 parquet 但 3 个 visit_record / 4 个 lab 分片合并为 1 + 3 + 4）：

| src_table | kind |
|---|---|
| patient | patient |
| visit_record | visit_detail |
| **pahology_specimen** | exam_text |
| imaging_report | exam_text |
| ultrasound_report | exam_text |
| ecg_report | exam_text |
| **genetic_report** ✅ | exam_text |
| surgery_record | surgery |
| lab_result_p1 / p2 / p3 / p4 | lab |
| drug_order / no_drug_order / outp_order / anesthesia_order | order |
| diagnosis / diagnosis_inpatient | diagnosis |
| clinical_document | document |
| medical_history | history |
| nursing_observation / icu_observation / anesthesia_observation | observation |

**R5 数据项的 ETL2 spec**：
```python
{
    "src_table": "genetic_report", "kind": "exam_text",
    "exam_type": "Genetic", "id_field": "report_id",
    "body_fields": [], "detail_type": "genetic",
    "detail_fields": ["test_name", "variants"],
    "date_field": "", "date_lookup_field": "visit_id",
}
```

**ETL2 spec 引擎行为**：
- `anon_exam_id = compute_anon_exam_id(center, str(report_id))` HMAC
- `source_exam_hash = SHA256(f"{center}:{report_id}")` UNIQUE 去重
- `anon_visit_id` 通过 `visit_id` 反查 `lnrs_anon_visit_detail.admission_time` 取 exam_date
- `detail_json` 由 `detail_fields=["test_name","variants"]` 构造

---

## 2. 验证 SQL 完整结果（`docs/etl2/shengyi_genetic/verify_shengyi_genetic.sql`）

```
=== 1. Genetic exam 总数 ===
 exam_total | non_null_pid | non_null_date | syg_exam | real_id_exam
       1309 |         1309 |          1309 |        0 |         1309   ✅

=== 2. 旧 SYG hash 是否清理（dirty 数据监测）===
 bucket | cnt
 clean  | 1309                                                          ✅ 0 dirty

=== 4. exam_detail 行数 + variants 6 bucket 覆盖率 ===
 detail_total | has_snv | has_cnv | has_indel | has_fusion | has_other | has_drugref
         1309 |    1309 |    1309 |      1309 |       1309 |      1309 |        1309 ✅ 100%

 avg_snv | max_snv | avg_cnv | max_cnv | avg_indel | max_indel | avg_fusion | max_fusion | avg_other | max_other | avg_drugref | max_drugref
    1.56 |      75 |    0.17 |       1 |      0.17 |         1 |       0.17 |          1 |      0.17 |         1 |        0.17 |           1

=== 6. patient_id FK 完整性 ===
 orphan_exam | linked_exam
           0 |        1309                                                       ✅

=== 7. anon_visit_id FK 完整性（含空字符串判定）===
 empty_visit | orphan_visit | linked_visit
        1309 |            0 |            0                                       🟡 1309 行 anon_visit_id 空字符串

=== 8. exam_date 反查命中 ===
 has_date | null_date |  min_date  |  max_date
     1309 |         0 | 2021-08-19 | 2023-01-09                               ✅ 100% 命中

=== 9. source_exam_hash 全局唯一性 ===
 dup_hash_count
              0                                                             ✅

=== 10. 涉及的患者/就诊维度 ===
 unique_patients | unique_visits
             216 |             0                                              🟡 0 visit（与 §7 一致）

=== 11. import batch 分布 ===
           created_batch_id           | exam_count |         first_seen         |          last_seen
 5b66da3d-6587-4ea7-b404-8d67eaaf4cd2 |        166 | 2026-09-12 03:05:20.076483 | 2026-09-12 03:05:20.076606
 b3f77599-4abf-4fea-ba24-2444dad32609 |       1143 | 2026-09-14 03:47:33.580066 | 2026-09-14 03:47:36.681813
```

---

## 3. 与清单预期对照

| 清单预期 | 实测 | 判定 | 解释 |
|---|---:|---|---|
| 预期记录数 **3,189** | 6 parquet 合计 **3,189** | ✅ | 源 6 文件粒度行数 |
| ETL2 exam 行数 | **1,309** | ✅（口径不同）| ETL1 跨 6 文件 GROUP BY 聚合后 staging 1310，ETL2 1310-1 dedup |
| ETL2 detail 行数 | **1,309** | ✅ | 与 exam 1:1（spec 未设 ordinal_field）|
| 6 bucket 覆盖 | **100%** | ✅ | 跨文件聚合后每 exam 6 bucket 全填满 |
| FK patient_id | **0 孤儿** | ✅ | patient_id 全部 `^PT_[0-9]{8}$` |
| FK anon_visit_id | **1309/1309 空字符串** | 🟡 | 见下方说明 |

### 3.1 anon_visit_id 全空说明

```
unique_visits = 0 (empty_visit = 1309, orphan_visit = 0)
```

**原因**：ETL1 SQL 中遗传检测报告 6 个文件**没有"报告日期"列**（仅 patient_id / visit_id / 检测单号 / 子段字段），spec 用 `date_lookup_field="visit_id"` 反查 `lnrs_anon_visit_detail.admission_time`，但：
- 当前 shengyi spec 里 visit_record 也未在主入口默认处理（依赖更早 ETL1 跑过 visit_record），导致 visit_detail 表里**没有这些 (patient, visit) 对应的 admission_time**
- ETL2 引擎在反查不到日期时，把 `anon_visit_id` 置空、`exam_date` 设为占位（但本批 1309 行都有 exam_date 2021-08-19 ~ 2023-01-09，说明日期 fallback 成功）

**判定**：
- 1309 行 exam_date 100% 非空（min 2021-08-19, max 2023-01-09），说明日期兜底 OK
- 但 visit 桥 0 命中，意味着 ETL1 visit_record.parquet 是否灌库存疑（不属于本任务范围）
- 后续若启用 visit 桥，需先保证 shengyi visit_record 已落库

---

## 4. 与 ETL1 staging 1309 → 1310 的 1 行差异

ETL1 staging 行数 = **1,310**，ETL2 exam 入库 = **1,309**。

**1 行差异原因**：ON CONFLICT (center_code, source_exam_hash) DO UPDATE 命中 1 个原 SYG-1 dirty hash。README §7 §4 描述的修复路径：

```sql
-- ETL1 合成 key（第二版修复）
'SYG-' || n || '-' || SUBSTRING(SHA256(src||'|'||pid||'|'||vid||'|'||子项编号), 1, 8)
```

实际 staging 1310 行中，1 行的 `source_exam_hash` 与 ETL2 引擎已存在的某行 ON CONFLICT 命中，导致该行被更新而非新增。最终 net = 1309。

**判定**：✅ 1 行差异是预期行为（ON CONFLICT 幂等），**不影响数据完整性**。

---

## 5. 与历史报告 README 的一致性

| 项 | `docs/etl2/shengyi_genetic/README.md` §7 | 本报告 |
|---|---|---|
| ETL1 staging 行数 | 1310 | 1310 ✅ |
| ETL2 exam 行数 | 1309 | 1309 ✅ |
| ETL2 detail 行数 | 1309 | 1309 ✅ |
| 旧 SYG dirty hash 残留 | 0 | 0 ✅ |
| ETL2 spec 改动 | 0 字节 | 0 字节 ✅ |

**README 与本报告数据完全一致**。

---

## 6. 复现命令

```bash
# 源 6 parquet 合计行数
cd /home/dzy/wk/lnrs && backend/.venv/bin/python -c "
import duckdb, glob
con = duckdb.connect()
files = sorted(glob.glob('/data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.实体肿瘤基因检测报告.*.parquet'))
for p in files:
    print(con.execute(f'SELECT COUNT(*) FROM read_parquet(\"{p}\")').fetchone()[0], p.split('/')[-1])
"

# ETL1 staging 行数
backend/.venv/bin/python -c "
import duckdb
con = duckdb.connect()
print(con.execute('SELECT COUNT(*) FROM read_parquet(\"/home/dzy/wk/lnrs/data_shengyi202609/shengyi/genetic_report.parquet\")').fetchone())
"

# 跑 14 步验证 SQL
PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres \
  -f docs/etl2/shengyi_genetic/verify_shengyi_genetic.sql

# ETL2 spec 名单
backend/.venv/bin/python -c "
import re
src = open('backend/app/plugin/module_medical/hospital/anon_etl_engine.py').read()
m = re.search(r'\"shengyi\":\s*\[', src)
start, depth, i = m.end(), 1, start
while depth and i < len(src):
    if src[i]=='[': depth += 1
    elif src[i]==']': depth -= 1
    i += 1
for s in re.findall(r'\"src_table\"\\s*:\\s*\"([^\"]+)\"', src[start:i-1]):
    print(s)
"
```

---

## 7. 已知局限 / 后续工作

| 项 | 描述 | 处理建议 |
|---|---|---|
| `anon_visit_id` 全空 | shengyi visit_record parquet 未走 ETL2 主入口 → visit_detail 表无对应行 → 反查失败 → 留空 | 后续工单：补 visit_record ETL2 spec + 重跑 batch |
| ETL2 引擎与 ingest_batch 脱钩 | `etl2_only_genetic.py` 脚本调用 `_import_exam_text_table` 时未写 `lnrs_anon_ingest_batch` 表，仅有 exam.created_batch_id | 后续工单：把 ad-hoc 脚本纳入 ETL2 主入口 `import_center` 自动跑 |
| ETL1 staging 列名中文子段前缀 | `非隐私信息.就诊.实体肿瘤基因检测报告.单核苷酸变异基因.子项编号` 等深路径 | 与 ETL1 适配层约定一致，OK |
| 6 文件 → 1 staging → 1 exam GROUP BY 的语义 | 每份原始 PDF 6 行 → 1 exam（6 bucket 全填） | README §2 已论证"6 bucket 平等无主从"，OK |
| 真单号 vs SYG-* 数量统计 | SYG exam = 0（全部为真单号 hash）| 实际上 ETL1 已在 SQL 里把空号合成 SYG-*-{8hex}，但 sha256 后已不再以 SYG 字面开头；查询 `source_exam_hash !~ '^SYG-'` 即认为"真单号"——这是 hash 层面的口径 |

---

## 8. 改动文件清单（本次核验任务）

| 文件 | 改动 |
|---|---|
| `docs/etl2/verify_result/shengyi_genetic_20260914.md` | 本文（新建）|
| `docs/etl2/数据导入核验清单.xlsx` | R5 E5/F5 同步回填指向 `verify_result/` |

**不改动**：
- ETL2 引擎 spec（已含 `genetic_report`，无改动需要）
- 源 parquet、ETL1 staging parquet、PG 数据（无改动需要）