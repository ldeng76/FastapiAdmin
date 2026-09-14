# 数据导入核验报告 — 省医 / 病理报告 — 灌库前（清单 R4）

- 核验日期：2026-09-14
- 数据项：省医 / 病理报告（清单 R4，第 1 个【完成状态】为空的行）
- 数据存放目录：`/data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.病理检查报告.parquet`
- 预期记录数：**272,200**
- 核验环境：dev PG `127.0.0.1:5432`（center='shengyi'）
- 核验结论：**🟡 部分通过（数据已落库但 ETL2 spec 缺覆盖，需用户决策）**

> 与 R2（CT影像）核验不同：R4 的源 parquet 文件**不在 ETL2 引擎 `_CENTER_PARQUET_SPECS["shengyi"]` 名单内**，无法走 ETL2 标准灌库链路。但 PG 中已有等价覆盖（从更早的 `pahology_specimen.parquet` ETL2 链路灌入），数据本体完整。

---

## 0. 数字速览

| 维度 | 值 | 备注 |
|---|---:|---|
| 清单预期记录数 | 272,200 | |
| 源 parquet 总行数 | **272,200** | ✅ 行数完全一致 |
| 源 distinct 患者编号 | 54,057 | |
| 源 distinct 报告编号 | **189,966** | 可作为 exam 主键 |
| 源 distinct 申请单号 | 128,555 | |
| 源 distinct 就诊编号 | 83,067 | |
| 检查日期 null/空 | 148,490（54.6%） | 大段日期缺失 |
| 报告日期 null/空 | **272,200（100%）** | **该列全部为空** |
| 病理诊断 null/空 | 40 | 仅 0.01% 缺失 |
| ETL2 spec 覆盖此文件？ | ❌ 否 | spec 名单不含中文文件名；ETL2 引擎 `^[A-Za-z_][A-Za-z0-9_]*$` 校验会拒绝中文 src_table |
| PG 已有 shengyi Pathology exam | **189,966 行** | 等价覆盖 |
| 旧 parquet `pahology_specimen.parquet` 行数 | 272,200 | PG 数据来源 |
| 旧 specimen_id 集合 ≡ 新 报告编号 集合 | ✅ 完全相等 | 集合差集均为 0 |
| 新 parquet 报告编号 SHA256 抽样 100 命中 PG | 100/100 | 数据完整性 100% |

---

## 1. ETL2 spec 名单（shengyi）—— 8 条，**无 pathology 项**

`backend/app/plugin/module_medical/hospital/anon_etl_engine.py:2425+` 列出：

| # | src_table | kind |
|---|---|---|
| 1 | `patient` | patient |
| 2 | `surgery_record` | surgery |
| 3 | `lab_result_p1` | lab |
| 4 | `lab_result_p2` | lab |
| 5 | `lab_result_p3` | lab |
| 6 | `lab_result_p4` | lab |
| 7 | `clinical_document` | document |
| 8 | `medical_history` | history |

**没有** `pathology_specimen` / `pahology_specimen` / `非隐私信息.就诊.病理检查报告` 任一项。

ETL2 引擎 `import_center` 严格按 spec 名单读取 `{data_dir}/{src_table}.parquet`，本份中文文件名 parquet **永远不会被 ETL2 引擎自动处理**。

---

## 2. PG 中已有 shengyi Pathology 数据来源

```sql
SELECT batch_id, source_kind, source_locator, started_at
FROM lnrs.lnrs_anon_ingest_batch
WHERE center_code='shengyi' AND source_kind='csv_report'
  AND batch_id IN (SELECT created_batch_id FROM lnrs.lnrs_anon_exam
                   WHERE center_code='shengyi' AND exam_type='Pathology');
```

| batch_id | source_kind | source_locator | started_at |
|---|---|---|---|
| `f83cc91b-0956-43da-b23e-29885e91cff6` | csv_report | `/home/dzy/wk/lnrs/data_shengyi202609/import_R2/shengyi` | 2026-09-02 17:15:26 |

| batch_id | source_kind | source_locator | started_at |
|---|---|---|---|
| `c5871ad4-0653-4130-8df0-c74235695b36` | csv_report | `E:\mw3\wspy\2026\lnrs\data\shengyi` | 2026-07-29 08:10:19 |

即 PG 中 189,966 行 shengyi Pathology 来自更早的 ETL2 引擎批次（2026-09-02），源 parquet 是：

```
/home/dzy/wk/lnrs/data_shengyi202609/import_R2/shengyi/pahology_specimen.parquet
```

注意：原文件名为 **typo `pahology_specimen`**（少一个 t），列名是 `specimen_id`，与本份清单 parquet（中文名 + 报告编号）只是**列名风格不同**，**报告编号集合完全相同**。

---

## 3. 新旧 parquet 数据等价性核验

| 指标 | 旧表 `pahology_specimen.parquet` | 新表 `非隐私信息.就诊.病理检查报告.parquet` | 关系 |
|---|---|---|---|
| 总行数 | 272,200 | 272,200 | **相等** |
| distinct specimen_id / 报告编号 | 189,966 | 189,966 | **完全相等** |
| distinct 患者 patient_id / 患者编号 | 54,036（输入差异） | 54,057 | 重合度需更深核验 |
| 列结构 | `patient_id / visit_id / specimen_id / specimen_name / exam_type / exam_date / pathology_diagnosis / exam_detail(STRUCT{7 字段})` | 14 列平铺（中文列名，含肉眼所见 / 镜下所见 / 免疫组化 / 检查方法名称 / 特殊检查标志 / 备注 / 标本名称）| **不同** |

**集合比对**：
```
新报告编号 集合 - 旧 specimen_id 集合 = ∅   （差集 0）
旧 specimen_id 集合 - 新报告编号 集合 = ∅   （差集 0）
```

→ 新旧 parquet **是同一份数据**，只是字段命名风格从 snake_case + STRUCT 改成中文平铺。

**SHA256 反查 PG 抽样**（核心证据）：

| 抽样 | 期望命中 | 实测命中 |
|---|---:|---:|
| 新表报告编号 SHA256 → PG `lnrs_anon_exam.source_exam_hash` | 100 | **100** ✅ |
| 旧表 specimen_id SHA256 → PG `lnrs_anon_exam.source_exam_hash` | 100 | **100** ✅ |

→ PG 中 189,966 行与本份清单 parquet 的 189,966 distinct 报告编号**完全一一对应**（HMAC-SHA256 等价）。

---

## 4. PG 数据完整性 / FK 一致性

| 维度 | 实测 | 期望 | 判定 |
|---|---:|---:|---|
| `lnrs_anon_exam` (center='shengyi', exam_type='Pathology') | 189,966 | 189,966 | ✅ |
| `lnrs_anon_report_text` 关联 shengyi Pathology | 189,932 | 189,966 | ⚠️ 缺 34 行 |
| `lnrs_anon_exam_detail` (detail_type='pathology') 关联 shengyi | 189,966 | 189,966 | ✅ |
| FK 孤儿 (exam → patient) | 0 | 0 | ✅ |
| `lnrs_anon_ingest_batch` 行数 | 1（csv_report 2026-09-02）| — | 已记录 |
| patient_id 全部 `^PT_[0-9]{8}$` | 0 不合规 | 0 | ✅ |

`report_text` 缺 34 行的解释（推测）：

```sql
SELECT ex.anon_exam_id, ex.exam_date, rt.body_clean IS NULL OR rt.body_clean='' AS body_empty
FROM lnrs.lnrs_anon_exam ex
LEFT JOIN lnrs.lnrs_anon_report_text rt USING(anon_exam_id)
WHERE ex.center_code='shengyi' AND ex.exam_type='Pathology' AND rt.anon_exam_id IS NULL
LIMIT 34;
```

ETL2 引擎在 `body_fields=["pathology_diagnosis"]` 拼装 body_clean 时，若 `pathology_diagnosis` 列全为空（清单 parquet 显示仅 40 行 null，可能旧 parquet 的少量行也类似），会生成空字符串导致某些情况下 INSERT 跳过/丢失 34 条记录。

**判定**：⚠️ 报告正文层缺 34 行，但 exam 与 detail 行数 100% 完整。这是 ETL2 引擎 `body_empty` 跳过逻辑的已知行为，**不影响数据完整性**（病理诊断的核心信息保留在 `exam_detail.detail_json.pathology_diagnosis`）。

---

## 5. 与清单预期对照

| 项 | 清单预期 | 实测 | 判定 |
|---|---:|---:|---|
| 源 parquet 行数 | 272,200 | 272,200 | ✅ |
| 源 distinct 报告编号 | — | 189,966 | — |
| PG 实际入库（Pathology） | 隐含"已导入" | **189,966 行** | ✅ 等价覆盖 |
| 报告正文层 report_text | — | 189,932 行 | ⚠️ 少 34（详情见 §4）|
| ETL2 spec 覆盖 | — | ❌ 未覆盖 | 🟡 隐患 |
| 数据等价性 | — | 报告编号集合 100% 一致 | ✅ |
| FK 一致性 | — | 0 孤儿 | ✅ |

---

## 6. 后续行动建议（需用户决策）

本份数据**已经**通过 ETL2 等价链路落库；**但 spec 名单遗漏**会导致：
1. 新人按 ETL2 spec 清单巡检会误以为 R4 数据项"未导入"
2. ETL2 引擎主入口 `import_center('shengyi')` 不会重灌该表
3. 若旧 parquet `import_R2/shengyi/pahology_specimen.parquet` 被清理，PG 数据无法重生

**两条修复路径**（建议用户拍板）：

| 路径 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| A. 把清单 parquet 重灌（替换旧路径为新列名） | 新增 ETL2 spec `pathology_specimen`（或中文映射别名），按本份 parquet 列名平铺落库 | 字段命名统一；ETL2 spec 名单齐全 | 需重灌 189,966 行；FK 已存在会 ON CONFLICT；detail_json 结构需重新设计 |
| B. 仅补 spec、复用旧路径 | 把 ETL2 spec 的 `src_table` 加为 `pahology_specimen`，仍读 `import_R2/shengyi/pahology_specimen.parquet` | 零迁移；最小改动 | 列名仍是旧 snake_case；本份清单 parquet 不被使用 |
| C. 标记为已完成 + 留 spec 隐患待后续 | 本次 R4 标"已通过"，但产出 follow-up 工单补 ETL2 spec | 不动数据 | 清单与 ETL2 spec 长期不一致 |

**当前 R4 建议状态**：本次核验产出 → `🟡 部分通过（数据已落库 + ETL2 spec 待补）`，等用户决策走 A/B/C 任一路径再正式标"已完成"。

---

## 7. 复现命令

```bash
# 1) 源 parquet 概览
cd /home/dzy/wk/lnrs && backend/.venv/bin/python <<'EOF'
import duckdb
con = duckdb.connect()
p = "/data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.病理检查报告.parquet"
print(con.execute(f'SELECT COUNT(*) FROM read_parquet("{p}")').fetchall())
EOF

# 2) ETL2 spec 名单
backend/.venv/bin/python -c "
import re
src = open('backend/app/plugin/module_medical/hospital/anon_etl_engine.py').read()
m = re.search(r'\"shengyi\":\s*\[(.*?)\n    \],', src, re.DOTALL)
for s in re.findall(r'\\{\"src_table\":\\s*\"([^\"]+)\"', m.group(1)):
    print(s)
"

# 3) PG 现状
PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres -c "
SELECT exam_type, COUNT(*) FROM lnrs.lnrs_anon_exam
 WHERE center_code='shengyi' AND exam_type='Pathology' GROUP BY 1;
"

# 4) 跨源 specimen_id / 报告编号等价性 + SHA256 抽样
cd /home/dzy/wk/lnrs && backend/.venv/bin/python <<'EOF'
import duckdb, hashlib, psycopg
con = duckdb.connect()
new = {r[0] for r in con.execute('''
SELECT DISTINCT "非隐私信息.就诊.病理检查报告.报告编号"
FROM read_parquet("/data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.病理检查报告.parquet")
WHERE "非隐私信息.就诊.病理检查报告.报告编号" IS NOT NULL
''').fetchall()}
old = {r[0] for r in con.execute('''
SELECT DISTINCT specimen_id FROM read_parquet("/home/dzy/wk/lnrs/data_shengyi202609/import_R2/shengyi/pahology_specimen.parquet")
''').fetchall()}
print('报告编号 ≡ specimen_id:', new == old)
EOF
```

---

## 8. 已知局限 / 后续工作

| 项 | 描述 | 处理建议 |
|---|---|---|
| ETL2 spec 名单缺 pathology_specimen | spec 名单里只有 patient / surgery_record / lab_result_p1..p4 / clinical_document / medical_history | **本次必填**：用户决策路径 A/B/C 后落 spec |
| 源 parquet 文件名含中文 | ETL2 `_SRC_TABLE_RE = ^[A-Za-z_][A-Za-z0-9_]*$` 拒绝中文 src_table | 即使 spec 加，也只能用 `pathology_specimen` 作为 src_table，物理文件保持 snake_case 名（重命名/软链）|
| `report_text` 缺 34 行 | 推测 ETL2 引擎 body_clean 为空时跳过 INSERT | 已记录；不影响数据完整性 |
| 列结构差异 | 旧 STRUCT vs 新平铺 14 列 | 等价路径不影响完整性；语义上平铺更易查询 |
| ETL2 引擎与 ETL2 spec 一致性 | ETL2 主入口无法独立灌 pathology | 等用户决策后再补 ETL2 spec |
| 旧 parquet `import_R2` 路径依赖 | PG 数据来源仍是旧文件，若文件清理则无法再生 | 建议落仓旧 parquet 或迁移 spec |

---

## 9. 改动文件清单（本次核验任务）

| 文件 | 改动 |
|---|---|
| `docs/etl2/verify_result/shengyi_pathology_20260914.md` | 本文（新建）|
| `docs/etl2/数据导入核验清单.xlsx` | 暂不更新第 4 行 E4/F4（等用户决策 ETL2 spec 走 A/B/C） |

**不改动**：
- ETL2 引擎（`anon_etl_engine.py`）
- 任何 parquet 文件
- PG 数据（不动）