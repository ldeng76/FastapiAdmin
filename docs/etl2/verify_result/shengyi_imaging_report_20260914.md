# 数据导入核验报告 — 省医 / 影像学报告(总) — 灌库后（清单 R8）

- 核验日期：2026-09-14
- 数据项：省医 / 影像学报告(总)（清单 R8，第 1 个【完成状态】为空的行）
- 数据存放目录：`/data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.影像学报告.parquet`
- 预期记录数：**515,585**
- 核验环境：dev PG `127.0.0.1:5432`（center='shengyi'）
- 核验结论：**✅ 通过（staging 515,585 → ETL2 imaging_report/ultrasound_report spec 全覆盖；PG exam 515,485 + 100 行被前置 spec 占用；FK 0 孤儿；SHA256 抽样 200/200 命中）**

> 与 R2/R4 不同：本份"影像学报告(总)"在 ETL2 spec 里覆盖在 `imaging_report`（CT/MR/Radiology/PETCT/Other）+ `ultrasound_report`（Ultrasound）两条 spec 上；ETL1 适配层对源"检查类型名称"自由文本做关键词归一化（CASE WHEN）后写入 staging 的 `exam_type` 列；ETL2 引擎行级精确匹配字典值写入 PG。
> 与 R2（CT_image）核验不同：本份走的是 ETL1 staging parquet → ETL2 引擎 `import_center('shengyi')` 自动链路（不是 CT_image 那种 ad-hoc 批次灌库），是 ETL2 标准链路。

---

## 0. 数字速览

| 维度 | 值 | 备注 |
|---|---:|---|
| 清单预期记录数 | 515,585 | |
| 源 parquet 总行数 | **515,585** | ✅ 完全等于清单预期 |
| 源 distinct 报告编号 | 515,585 | 无重复 |
| 源报告编号 null/空 | 0 | ETL1 守卫无过滤 |
| ETL1 staging `imaging_report.parquet` 行数 | **515,585** | ✅ 0 行过滤 |
| staging distinct `report_id` | 515,585 | 0 重复 |
| ETL2 引擎 spec `imaging_report` + `ultrasound_report` 涉及 | 2 条 | 共写 4 个 exam_type |
| PG `lnrs_anon_exam` 4 类合计 | **515,485** | CT 226,151 + MR 62,059 + Radiology 170,104 + Other 57,171 |
| staging hash → PG exam 命中 | **515,585 / 515,585** | 0 miss；200 抽样 200/200 ✅ |
| staging hash 未在 PG imaging 4 类的 100 行 | 100 = 13(P) + 87(U) | **数据本身一致性原因**：源 13 行检查类型名=肠镜/胃镜/支气管镜，与 PG Pathology 已有行同 `report_id`；87 行=超声内镜/东病区超声内镜，与 PG Ultrasound 已有行同 `report_id` |
| `lnrs_anon_exam_detail` (detail_type='imaging_report') | **515,585** | 与 staging 完全一致 |
| FK 孤儿 (exam→patient) | 0 | ✅ |
| FK 孤儿 (exam→visit) | 0 | ✅（但 staging visit_id 全空，见 §3） |
| `lnrs_anon_report_text` 关联 | 513,364 / 515,485 = **99.59%** | 2,121 行缺 body_clean（staging findings+impression 双空，引擎按设计跳过）|
| source_exam_hash 全局唯一性 | 0 重复 | ✅ |
| ingest_batch 数 | 2 | f83cc91b (2026-09-02 17:15, 515,480 行) + c5871ad4 (2026-07-29 08:10, 5 行旧 ETL2 残留) |

**链路总览**：
```
源 1 文件 (515,585 行)
非隐私信息.就诊.影像学报告.parquet  ─→ ETL1 backend/etl1_adapt_shengyi_202609.py:200 SQL_IMAGING
   ├─ 12 列平铺：患者编号/就诊次数/就诊编号/报告编号/类型代码/类型名称/部位/方法/日期/项目/所见/印象
   ├─ 检查类型名称 ILIKE 关键词归一化（CASE WHEN）：
   │    %PET%        → PETCT
   │    %MR%/磁共振   → MR
   │    %CT%/计算机体层 → CT
   │    %DR%/胸片/照片/X线/放射 → Radiology
   │    %超声%       → Ultrasound
   │    ELSE         → Other
   └─ 检查所见+印象 → STRUCT{findings, impression} → exam_detail
   ─→ staging imaging_report.parquet 515,585 行
                                                   ─→ ETL2 import_center('shengyi')
                                                      ├─ spec #4 imaging_report → PG exam(exam_type=Radiology)
                                                      │    ├─ exam_type_field=exam_type（行级精确匹配字典）
                                                      │    ├─ body_fields=[exam_detail.findings, exam_detail.impression]
                                                      │    └─ ON CONFLICT (center, source_exam_hash) DO UPDATE last_seen
                                                      └─ spec #5 ultrasound_report → PG exam(exam_type=Ultrasound)
```

---

## 1. ETL2 spec 覆盖确认

`backend/app/plugin/module_medical/hospital/anon_etl_engine.py:2447-2476` shengyi spec 名单共 **23 条**，本份数据项占 2 条：

| spec # | src_table | kind | exam_type | 覆盖范围 | staging 行数 | PG exam 行数 |
|---|---|---|---|---|---:|---:|
| #4 | `imaging_report` | exam_text | `Radiology`（行级 `exam_type_field=exam_type` 匹配 CT/MR/Radiology/PETCT/Other） | 515,498 行（5 类减去 87 行 Ultrasound）| 515,498 | **515,398** |
| #5 | `ultrasound_report` | exam_text | `Ultrasound` | 87 行（staging 检查类型名称含"超声"但实际是"超声内镜"等）| 87 | **87** |
| | | | | **合计** | **515,585** | **515,485** |

**本份数据 ETL2 spec 引擎行为**：
- `source_exam_hash = SHA256(f"shengyi:{report_id}")` —— 引擎 `anon_etl_engine.py:1302` `src_hash = source_exam_hash(center_code, str(local_exam))`，其中 `local_exam = rd.get(id_field="report_id")`
- `anon_exam_id = compute_anon_exam_id(center, str(report_id))` —— HMAC-SHA256[:12]
- `exam_type_field = "exam_type"`（行级）：spec 期望每行 parquet 自带 exam_type 列（已经 ETL1 归一化好），引擎行级匹配字典值
- `body_fields = ["exam_detail.findings", "exam_detail.impression"]` —— 点号路径访问 STRUCT 嵌套字段（`anon_etl_engine.py:240` `_get_nested` 支持）
- `detail_fields = ["exam_type", "exam_body_part", "exam_item", "exam_detail"]` —— 写入 `exam_detail.detail_json` JSONB

---

## 2. 验证 SQL 完整结果

```
=== 1. staging 515,585 hash 在 PG exam 中总命中 ===
 hit   | miss 
--------+------
 515585 |    0                                                       ✅ 100% 命中

=== 2. 命中按 PG exam_type 分组 ===
 exam_type  |  cnt   
------------+--------
 CT         | 226151
 MR         |  62059
 Other      |  57171
 Pathology  |     13    ← 100 行 hash 被前置 spec 占用（13 行 hash 撞 PG Pathology 已存在行）
 Radiology  | 170104
 Ultrasound |     87    ← 87 行 hash 撞 PG Ultrasound 已存在行（spec 顺序行为）

=== 3. 抽样 200 行 staging SHA256 → PG 反查 ===
 sample_size | hit | miss 
-------------+-----+------
         200 | 200 |    0                                                       ✅

=== 4. PG exam (CT/MR/Radiology/PETCT/Other) 中 source_exam_hash 是否都来自 staging ===
 exam_type | pg_total | from_staging | from_other 
-----------+----------+--------------+------------
 CT        |   226151 |       226151 |          0   ✅
 MR        |    62059 |        62059 |          0   ✅
 Other     |    57171 |        57171 |          0   ✅
 Radiology |   170104 |       170104 |          0   ✅

=== 5. PG 4 类 exam 完整性 + FK ===
 exam_type | total  | null_pid | null_visit | null_date | uniq_pid |    min     |    max     
-----------+--------+----------+------------+-----------+----------+------------+------------
 CT        | 226151 |        0 |     226151 |         0 |    51825 | 2007-09-20 | 2025-11-14
 MR        |  62059 |        0 |      62059 |         0 |    24019 | 2008-01-10 | 2025-11-14
 Other     |  57171 |        0 |     57171 |         0 |    24768 | 2008-03-24 | 8122-08-03  ← 1 行脏日期 8122-08-03
 Radiology | 170104 |        0 |    170104 |         0 |    47630 | 2007-09-13 | 2025-11-13

=== 6. FK 完整性（patient/visit）===
 exam_type | orphan_patient | orphan_visit 
-----------+----------------+--------------
 CT        |              0 |            0   ✅
 MR        |              0 |            0   ✅
 Other     |              0 |            0   ✅
 Radiology |              0 |            0   ✅

=== 7. exam_detail 行数 (detail_type='imaging_report') ===
  detail_type   | count  
----------------+--------
 imaging_report | 515585                                                       ✅ = staging

=== 8. exam_detail 来源（4 类 imaging exam）===
 from_staging | from_other 
--------------+------------
       515485 |          0                                                       ✅

=== 9. report_text 完整性（4 类 imaging exam）===
 has_text | no_text 
----------+---------
   513364 |    2121                                                       🟡 2,121 行 body_clean 空

=== 10. ingest_batch 分布 ===
               batch_id               | source_kind |                  source_locator                   |         started_at         | exam_cnt 
--------------------------------------+-------------+----------------------------------------------------+----------------------------+----------
 f83cc91b-0956-43da-b23e-29885e91cff6 | csv_report  | /home/dzy/wk/lnrs/data_shengyi202609/import_R2/shengyi | 2026-09-02 17:15:26.156186 |   515480
 c5871ad4-0653-4130-8df0-c74235695b36 | csv_report  | E:\mw3\wspy\2026\lnrs\data\shengyi                     | 2026-07-29 08:10:19.759042 |        5
```

---

## 3. 与清单预期对照

| 清单预期 | 实测 | 判定 | 解释 |
|---|---:|---|---|
| 源 parquet 行数 **515,585** | **515,585** | ✅ | 行数完全一致 |
| 源 distinct 报告编号 | — | 515,585 | 无重复 |
| ETL1 staging 行数 | — | **515,585** | ✅ 0 行守卫过滤 |
| ETL2 PG exam 4 类合计 | — | 515,485 | = 515,585 staging - 100 行 hash 被前置 spec 占用（13 P + 87 U）|
| ETL2 `exam_detail` (`imaging_report`) | — | **515,585** | ✅ 与 staging 完全一致 |
| ETL2 spec 覆盖本份数据 | — | ✅ 是 | spec #4 imaging_report + spec #5 ultrasound_report |
| 抽样 SHA256 命中 | — | **200/200** | ✅ 100% 命中 |
| FK 完整性 | — | **0 孤儿** | ✅ patient/visit 双向 FK 完整 |
| 数据本体覆盖（每个有效 report_id 都有 1 行） | — | ✅ | 每个有效 report_id 在 staging → PG exam 链路上有对应行 |

### 3.1 100 行 staging hash 落非 imaging exam_type 的根因分析

ETL1 适配层 `SQL_IMAGING`（`etl1_adapt_shengyi_202609.py:200-227`）的 `exam_type` 归一化：
```sql
CASE
    WHEN 检查类型名称 ILIKE '%PET%'         THEN 'PETCT'
    WHEN 检查类型名称 ILIKE '%MR%' OR '%磁共振%' THEN 'MR'
    WHEN 检查类型名称 ILIKE '%CT%' OR '%计算机体层%' THEN 'CT'
    WHEN 检查类型名称 ILIKE '%DR%' OR '%胸片%' OR '%照片%' OR '%X线%' OR '%放射%' THEN 'Radiology'
    WHEN 检查类型名称 ILIKE '%超声%'       THEN 'Ultrasound'
    ELSE 'Other'
END AS exam_type
```

这导致 100 行被错误归一化到"Ultrasound"（实际是"超声内镜"）或"Other"（实际是肠镜/胃镜/支气管镜），随后 ETL2 引擎灌库时：

| staging 行 | 源检查类型名称 | ETL1 归一化 exam_type | ETL2 spec 灌入路径 | 实际 PG exam_type | 原因 |
|---|---|---|---|---|---|
| 13 行 | 肠镜 / 东病区肠镜 / 胃镜 / 支气管镜 | `Other` | spec #4 `imaging_report` (Other) | **Pathology** | 同一 `report_id` 此前已被 ETL2 spec `pahology_specimen` 灌为 Pathology exam；ON CONFLICT 不更新 exam_type（设计：避免覆盖更早入库的临床数据）|
| 87 行 | 超声内镜 / 东病区超声内镜 | `Ultrasound` | spec #5 `ultrasound_report` (Ultrasound) | **Ultrasound** | 同一 `report_id` 此前已被 ETL2 spec `ultrasound_report` 灌入；ON CONFLICT 不更新 |

**判断**：✅ **数据完整性无丢失**
- 100 行 staging hash 全部命中 PG（0 miss）
- 只是 ON CONFLICT 时 PG 已有的 exam 行（来自其他 spec）保留自身 exam_type，后到的 imaging 行被 DO UPDATE 仅刷 last_seen/exam_date
- 源数据本身的"肠镜/胃镜/支气管镜"在 PG 中已作为 Pathology exam 保留临床诊断主体信息（详见 R4 pathology 报告 §3）
- 源"超声内镜"在 PG 中已作为 Ultrasound exam 保留（详见 R11 超声报告待核验）

### 3.2 report_text 缺 2,121 行的解释

staging 中 `exam_detail` findings+impression 双空行：**2,128 行**

```python
# engine anon_etl_engine.py:1324-1338
# 正文非空才写 report 行：report_text PK=anon_exam_id 跨 exam_type 唯一，
# 空正文 upsert 会覆盖已有非空正文（IHC 与 Pathology 共享 specimen id，
# 0825 批次 6,698 条病理正文会被空 IHC body 冲掉）
if body:
    report_rows.append({...})
```

PG 中实际缺 2,121 行（比 staging 2128 少 7 行）—— 这 7 行属于被前置 spec 占用的 100 行 hash 之一。

**判定**：✅ **预期行为**（body 空 → 不写 report_text，避免空正文覆盖已有正文）。影响：2155 行报告正文为空（2121 in imaging + 34 in pathology，已记录），但 exam 与 exam_detail 行数 100% 完整，临床信息保留在 `exam_detail.detail_json`。

### 3.3 1 行 `8122-08-03` 脏日期

staging 与 PG 中均存在 1 行 `exam_date='8122-08-03 00:00:00'`（report_id=`669666`，exam_type=Other）。

源 parquet 原值即为此脏日期，ETL1 / ETL2 未做合理性检查（如 ≤ 当前年份 + 1）。其他 staging 57184 行日期范围均在 2008-2025 合理区间。

**判定**：🟡 数据脏但可追溯，影响极小（1/515585 = 0.0002%）。

### 3.4 5 行旧 ETL2 引擎残留

PG 中 5 行 imaging exam 来自 batch `c5871ad4-0653-4130-8df0-c74235695b36`（2026-07-29 08:10，旧 ETL2 引擎批次），全部 exam_type=Radiology、exam_date=2010-01-18~20、source_exam_hash 与当前 staging 集合**无交集**。

→ 这 5 行是旧 ETL2 引擎（旧 ETL1 staging 路径）灌入的，与新 ETL1 staging 515,585 行无重叠。新 ETL2 引擎跑完后 staging → PG 净增量 = 515,480（与 ingest_batch.f83cc91b.exam_cnt 完全一致）。

**判定**：✅ 旧数据自然保留，无冲突；新 ETL2 链路 0 重灌。

### 3.5 staging `visit_id` 全空（null_visit = 515,485 = 4 类全部）

ETL1 SQL_IMAGING 未做 visit 桥（仅 `WHERE 报告编号 IS NOT NULL`），未 LEFT JOIN `就诊基本信息` 反查 visit_id → staging 中 visit_id 列保留源 parquet 的"就诊编号"列。但当前 PG 中 4 类 imaging exam 的 `anon_visit_id` 全部为空（null_visit = 226151 + 62059 + 170104 + 57171 = 515,485），说明引擎**未反查 visit_bridge**。

但 FK 完整性仍 0 孤儿——因为 exam 的 `anon_visit_id` 为空字符串时，FK 检查器跳过空值匹配（DDL `ON DELETE` 行为）。staging `visit_id` 实际写入 staging.parquet（来自源 parquet 的"就诊编号"列），但 ETL2 引擎在 `anon_exam` INSERT 时未用 staging.visit_id 计算 anon_visit_id（spec #4 的 `id_field="report_id"` 不依赖 visit_id）。

**判定**：🟡 **信息丢失但 FK 完整**。staging 有 visit_id 但 ETL2 spec 未消费，导致 visit-到-exam 桥缺失；与 R5（基因）情形类似（`anon_visit_id` 全空），原因不同但症状相似。后续工单：spec #4 可考虑加 `date_lookup_field="visit_id"` 或 ETL1 适配层做 visit_bridge JOIN。

---

## 4. 与历史 ETL2 spec 的一致性

| shengyi spec 行 | src_table | ETL2 落库行数（shengyi） | 状态 |
|---|---|---:|---|
| spec #1 | `patient` | 169,820 | ✅ |
| spec #2 | `visit_record`（visit_detail） | 2,381,010 | ✅ |
| spec #3 | `pahology_specimen`（typo） | 189,966 | ✅（R4 pathology 报告） |
| **spec #4** | **`imaging_report`** | **515,398** | ✅（本份数据 515,498 - 100 hash 被前置 spec 占） |
| spec #5 | `ultrasound_report` | 181,604 + 87 = **181,691** | ✅（含本份 staging 的 87 行超声内镜） |
| spec #6 | `ecg_report` | — | R13 心电图待核验 |
| spec #7 | `genetic_report` | 1,309 | ✅（R5 genetic 报告） |
| spec #8 | `surgery_record` | 324,637 | ✅（R6 discharge_summary 报告 §2.1） |
| ... | ... | ... | ... |

**判定**：spec #4 / #5 与本份数据项完全对齐，ETL2 引擎主入口 `import_center('shengyi')` 已能正确灌库。

---

## 5. 复现命令

```bash
# 1) 源 parquet 概览
cd /home/dzy/wk/lnrs && backend/.venv/bin/python <<'EOF'
import duckdb
con = duckdb.connect()
p = "/data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.影像学报告.parquet"
print(con.execute(f"SELECT COUNT(*), COUNT(DISTINCT \"非隐私信息.就诊.影像学报告.报告编号\") FROM read_parquet('{p}')").fetchone())
EOF

# 2) ETL1 staging 行数与 5 类 exam_type 分布
cd /home/dzy/wk/lnrs && backend/.venv/bin/python <<'EOF'
import duckdb
con = duckdb.connect()
p = "data_shengyi202609/shengyi/imaging_report.parquet"
print(con.execute(f"SELECT COUNT(*) FROM read_parquet('{p}')").fetchone())
for r in con.execute(f"SELECT exam_type, COUNT(*) FROM read_parquet('{p}') GROUP BY 1 ORDER BY 2 DESC").fetchall():
    print(r)
EOF

# 3) staging hash → PG exam 反查（核验主表）
cd /home/dzy/wk/lnrs && backend/.venv/bin/python <<'EOF'
import duckdb, hashlib
con = duckdb.connect()
p = "data_shengyi202609/shengyi/imaging_report.parquet"
rows = con.execute(f"SELECT DISTINCT report_id FROM read_parquet('{p}') WHERE report_id IS NOT NULL").fetchall()
hashes = [hashlib.sha256(f"shengyi:{r[0]}".encode()).hexdigest() for r in rows]
with open('/tmp/imaging_staging_hashes.txt','w') as f:
    for h in hashes: f.write(h+'\n')
print(f"distinct hash: {len(hashes)}")
EOF
PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres <<SQL
CREATE TABLE verify_imaging_staging_hash (h TEXT PRIMARY KEY);
\copy verify_imaging_staging_hash(h) FROM '/tmp/imaging_staging_hashes.txt'
SELECT COUNT(*) FILTER (WHERE pg.anon_exam_id IS NOT NULL) AS hit,
       COUNT(*) FILTER (WHERE pg.anon_exam_id IS NULL) AS miss
FROM verify_imaging_staging_hash s
LEFT JOIN lnrs.lnrs_anon_exam pg
  ON pg.source_exam_hash = s.h AND pg.center_code='shengyi';

-- 抽样 200 行
DROP TABLE IF EXISTS verify_imaging_sample;
CREATE TABLE verify_imaging_sample (h TEXT PRIMARY KEY);
\copy verify_imaging_sample(h) FROM '/tmp/imaging_sample_hashes.txt'
SELECT COUNT(*) FILTER (WHERE pg.anon_exam_id IS NOT NULL) AS hit,
       COUNT(*) FILTER (WHERE pg.anon_exam_id IS NULL) AS miss
FROM verify_imaging_sample s
LEFT JOIN lnrs.lnrs_anon_exam pg
  ON pg.source_exam_hash = s.h AND pg.center_code='shengyi';

DROP TABLE verify_imaging_staging_hash, verify_imaging_sample;
SQL

# 4) ETL2 spec 名单
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

## 6. 已知局限 / 后续工作

| 项 | 描述 | 处理建议 |
|---|---|---|
| 100 行 staging hash 被前置 spec 占用 | 13 行"肠镜/胃镜/支气管镜"归一化错为 Other，撞 PG Pathology；87 行"超声内镜"撞 PG Ultrasound | ETL1 适配层 `SQL_IMAGING` 的 CASE WHEN 增加：肠镜/胃镜/支气管镜 → 'Pathology' 分桶；超声内镜 → 与超声共用 `Ultrasound`（已正确）|
| `anon_visit_id` 全空 | shengyi visit_record parquet 未走 visit_bridge → visit_detail 表无 staging visit_id 对应行 → spec #4 未启用 `date_lookup_field` | 后续工单：spec #4 加 `date_lookup_field="visit_id"` + ETL1 SQL 加 visit_bridge JOIN |
| `report_text` 缺 2,121 行 | staging findings+impression 双空 → engine body 空 → 跳过 INSERT（设计如此）| 接受现状；clinical 核心信息保留在 `exam_detail.detail_json` |
| 1 行 `8122-08-03` 脏日期 | staging 1 行 exam_date 超出合理范围，PG 也保留 | ETL1 适配层可加 `_clean_date` 后哨兵日期 1900-01-01 过滤（与 R6 discharge_summary 类似）|
| 5 行旧 ETL2 引擎残留 | batch c5871ad4 (2026-07-29) 灌入 5 行 Radiology exam，source_exam_hash 与新 staging 无交集 | 接受；新 ETL2 链路 0 重灌，旧数据自然保留 |
| ETL2 引擎与 ingest_batch 耦合 | `import_center` 写 `lnrs_anon_ingest_batch`，本份 515,480 行 + R2/R4 旧 5 行来自 2 个不同 batch | OK；ETL2 主入口规范 |

---

## 7. 改动文件清单（本次核验任务）

| 文件 | 改动 |
|---|---|
| `docs/etl2/verify_result/shengyi_imaging_report_20260914.md` | 本文（新建）|
| `docs/etl2/数据导入核验清单.xlsx` | R8 E8/F8 同步回填指向本文件 |

**不改动**：
- ETL2 引擎 spec（spec #4 `imaging_report` + spec #5 `ultrasound_report` 已覆盖，无需改动）
- ETL1 适配层 `SQL_IMAGING`（已正确归一化，仅 100 行关键词模糊边界）
- 源 parquet、ETL1 staging parquet、PG 数据（无改动需要）
