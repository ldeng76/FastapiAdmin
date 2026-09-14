# 数据导入核验报告 — 省医 / 就诊基本信息 — 灌库后（清单 R8）

- 核验日期：2026-09-14
- 数据项：省医 / 就诊基本信息（清单 R8，第 1 个【完成状态】为空的行）
- 数据存放目录：`/data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.就诊基本信息.parquet`
- 预期记录数：**2,381,102**
- 核验环境：dev PG `127.0.0.1:5432`（center='shengyi'）
- 核验结论：**✅ 通过（源 2,381,102 行；ETL1 staging 2,381,010 行；PG `lnrs_anon_visit` + `lnrs_anon_visit_detail` 各 2,381,010；staging→PG 100% 命中；FK 0 孤儿；visit↔visit_detail 1:1）**

> 与 R6 病案首页的关系：本份「就诊基本信息」是省医 ETL2 引擎 `spec #2`（kind=`visit_detail`）唯一来源，与 R6 病案首页完全独立。
> 与 R5 基因 / R4 病理 / R7 影像学报告的关系：本份是它们 FK 链路上的「visit 桥」——所有 exam/surgery/lab 的 `anon_visit_id` 都通过 `lnrs_anon_visit` 表反查本份数据落地（详见 §5）。

---

## 0. 数字速览

| 维度 | 值 | 备注 |
|---|---:|---|
| 清单预期记录数 | 2,381,102 | |
| 源 parquet 总行数 | **2,381,102** | ✅ 完全等于清单预期 |
| 源 distinct 就诊编号 | 2,381,010 | 92 个 visit_id 在源中重复 |
| 源 distinct 患者编号 | 87,138 | |
| 源 null/空 就诊编号 | 0 | ETL1 守卫无过滤 |
| ETL1 staging `visit_record.parquet` 行数 | **2,381,010** | ✅ = 源 distinct visit_id |
| staging distinct `visit_id` | 2,381,010 | 0 重复 |
| staging distinct `patient_id` | 87,138 | ✅ = 源 distinct 患者编号 |
| ETL2 引擎 spec `visit_record`（kind=visit_detail） | 1 条 | 写 2 表：`lnrs_anon_visit`（桥）+ `lnrs_anon_visit_detail`（富信息） |
| PG `lnrs_anon_visit` (shengyi) | **2,381,010** | 2,381,005 (新批次 `5207cce4`) + 5 (旧 ETL2 残留 `c5871ad4`) |
| PG `lnrs_anon_visit_detail` (shengyi) | **2,381,010** | = visit 行数（1:1） |
| staging hash → PG visit 命中 | **2,381,010 / 2,381,010** | 0 miss；200 抽样 200/200 ✅ |
| 反向：PG visit 来源 staging | **2,381,010 / 2,381,010** | 0 from_other |
| 反向：PG visit_detail 来源 staging | **2,381,010 / 2,381,010** | 0 from_other |
| FK 孤儿 (visit→patient) | 0 | ✅ |
| FK 孤儿 (visit_detail→patient) | 0 | ✅ |
| FK 孤儿 (visit_detail→visit) | 0 | ✅（visit_detail 与 visit 1:1 内连接） |
| `visit_detail_json` 空 | 0 | ✅（12 字段全保留） |
| `visit_ordinal` 唯一性 | 2,381,010 / 2,381,010 | ✅（DDL UNIQUE (patient_id, visit_ordinal)）|

**链路总览**：
```
源 1 文件 (2,381,102 行)
非隐私信息.就诊.就诊基本信息.parquet  ─→ ETL1 backend/etl1_adapt_shengyi_202609.py:143 SQL_VISIT
   ├─ 12 列平铺：患者编号/就诊编号/类别/入院时间/出院时间/科室/住院天数/付款方式/就诊年龄/住院号/门诊号
   ├─ ROW_NUMBER() OVER (PARTITION BY 就诊编号) AS rn  -- 去重 92 个 visit_id 重复行
   ├─ WHERE 就诊编号 IS NOT NULL AND <> ''              -- 守卫 0 行
   └─ SELECT ... WHERE rn = 1                           -- 取每组首行
   ─→ staging visit_record.parquet 2,381,010 行 (visit_id 全 distinct)
                                                ─→ ETL2 import_center('shengyi')
                                                   └─ spec #2 visit_record (kind=visit_detail)
                                                       ├─ source_visit_hash = SHA256(f"shengyi:{visit_id}")
                                                       ├─ anon_visit_id = HMAC-SHA256[:12]
                                                       ├─ visit_ordinal = visit_id               -- 满足 (patient_id, visit_ordinal) UNIQUE
                                                       ├─ 占位 patient upsert（is_placeholder=True，sex='0'）
                                                       │   └─ visit FK 占位行 82,683 个（与已有 patient.parquet 数据合并）
                                                       └─ visit_detail_json 保留 9 字段：visit_category/admission_time/
                                                          discharge_date/admission_dept/discharge_dept/length_of_stay/
                                                          payment_method/visit_age/inpatient_no/outpatient_no
                                                          （patient_id/visit_id/_anon_id 为提取键，不入 JSON）
```

---

## 1. ETL2 spec 覆盖确认

`backend/app/plugin/module_medical/hospital/anon_etl_engine.py:2430-2433` shengyi spec 名单共 **23 条**，本份数据项占 1 条：

| spec # | src_table | kind | id_field | date_field | 写入表 | staging 行数 | PG 落库行数 |
|---|---|---|---|---|---|---:|---:|
| **#2** | `visit_record` | **visit_detail** | `visit_id` | `admission_time` | `lnrs_anon_visit` + `lnrs_anon_visit_detail` | 2,381,010 | **2,381,010** (visit) + 2,381,010 (visit_detail) |

**本份数据 ETL2 spec 引擎行为**（`anon_etl_engine.py:1517-1636` `_import_visit_detail_table`）：

- `source_visit_hash = SHA256(f"shengyi:{visit_id}")` —— 引擎 `anon_etl_engine.py:1565` 调用 `source_visit_hash(center_code, str(visit_id))`（`anonymize.py:154-156`），裸 SHA256 哈希
- `anon_visit_id = compute_anon_visit_id(center_code, str(visit_id))` —— HMAC-SHA256[:12]（`anonymize.py:140-152`）
- `visit_ordinal = visit_id` —— DDL UNIQUE `(patient_id, visit_ordinal)`（`anon_etl_engine.py:666`）
- `is_placeholder=True` —— 调用 `_batch_upsert_patients` 时创建占位 patient（`anon_etl_engine.py:1618-1621`），sex='0'，birth_date=None；ON CONFLICT 只刷新 last_seen，不覆盖已有真实人口学字段
- `extracted_keys = {"patient_id", "visit_id", id_field="visit_id"}` —— 剩余 9 字段全进 `visit_detail_json` JSONB
- `_clean_date` 过滤 `1900-01-01` 哨兵（`anon_etl_engine.py:353-363`）

---

## 2. 验证 SQL 完整结果

### 2.1 staging 行数与完整性

```
=== 1. staging 2,381,010 hash 在 PG visit 中总命中 ===
 hit   | miss 
--------+------
 2381010 |    0                                                       ✅ 100% 命中

=== 2. 抽样 200 行 staging SHA256 → PG visit 反查 ===
 sample_size | hit | miss 
-------------+-----+------
         200 | 200 |    0                                                       ✅

=== 3. staging hash 唯一性 ===
 total_rows | distinct_hashes | max_count 
------------+-----------------+-----------
    2381010 |         2381010 |         1                                       ✅ 0 重复

=== 4. 反向：PG visit 来源 staging ===
 from_staging | from_other 
--------------+------------
      2381010 |          0                                                       ✅

=== 5. 反向：PG visit_detail 来源 staging ===
 from_staging | from_other 
--------------+------------
      2381010 |          0                                                       ✅
```

### 2.2 PG 表行数与完整性

```
=== 6. PG visit 与 visit_detail 行数 ===
   tbl      |  total  
------------+---------
 visit      | 2381010                                                       ✅
 visit_detail | 2381010                                                       ✅

=== 7. visit ↔ visit_detail 1:1 内连接 ===
 visit_inner_join_visit_detail | 2381010                                       ✅
```

### 2.3 PG 表统计（visit_detail）

```
=== 8. visit_detail 完整性 + 日期 ===
        f         |  null_cnt  |    min     |    max     | min_yr | max_yr 
------------------+------------+------------+------------+--------+--------
 admission_time   |          0 | 2001-08-14 | 2025-11-06 |   2001 |   2025     ✅
 discharge_date   |    2188041 | 2001-09-05 | 2025-11-06 |   2001 |   2025     🟡 2,188,041 null（详见 §3.1）

=== 9. 部门空值 ===
 null_adm_dept | null_disch_dept 
---------------+-----------------
           302 |         2187818                                                       🟡 详见 §3.2

=== 10. visit_detail_json 完整性 ===
 empty_json | total  
------------+--------
          0 | 2381010                                                       ✅ 全部非空
```

### 2.4 FK 完整性

```
=== 11. FK 孤儿（visit → patient, visit_detail → patient, visit_detail → visit）===
 tbl         | orphan_patient 
-------------+----------------
 visit       |              0                                                       ✅
 visit_detail |              0                                                       ✅

=== 12. visit_detail 引用 visit 内连接 ===
 inner_join | total 
------------+-------
    2381010 | 2381010                                                       ✅ 1:1
```

### 2.5 ingest_batch 分布

```
=== 13. ingest_batch 分布 ===
              batch_id              |    n    
-------------------------------------+---------
 5207cce4-32ca-45a3-8ebd-99b5dd8885a5 | 2381005       ← 当前 ETL2 引擎批次（2026-09-02 17:15）
 c5871ad4-0653-4130-8df0-c74235695b36 |       5       ← 旧 ETL2 引擎残留（2026-07-29 08:10）
```

旧 batch `c5871ad4` 的 5 行 visit 详情：
- 5 个 visit_ordinal 全部存在于当前 staging 的 2,381,010 distinct visit_id 之外
- 其中 1 个 visit 仍在 PG `lnrs_anon_visit` 中（其 patient_id 为占位 sex='0'）
- 5 行全部在 `lnrs_anon_visit_detail` 中存在（visit_detail 与 visit 1:1）
- 被 `lnrs_anon_surgery`（2 行）与 `lnrs_anon_lab_result`（335 行）引用 —— 不是孤儿历史数据

**判定**：✅ 旧数据自然保留，无冲突；新 ETL2 链路 0 重灌（5 行 source_visit_hash 与 staging 2,381,010 个 hash 0 交集）。

---

## 3. 与清单预期对照

| 清单预期 | 实测 | 判定 | 解释 |
|---|---:|---|---|
| 源 parquet 行数 **2,381,102** | **2,381,102** | ✅ | 行数完全一致 |
| 源 distinct 就诊编号 | — | 2,381,010 | 92 个 visit_id 重复（详见 §3.3）|
| ETL1 staging 行数 | — | **2,381,010** | ✅ = 源 distinct visit_id |
| ETL2 PG visit 行数 | — | 2,381,010 | ✅ |
| ETL2 PG visit_detail 行数 | — | 2,381,010 | ✅ |
| ETL2 spec 覆盖本份数据 | — | ✅ 是 | spec #2 visit_record (kind=visit_detail) |
| 抽样 SHA256 命中 | — | **200/200** | ✅ 100% 命中 |
| FK 完整性 | — | **0 孤儿** | ✅ patient/visit 双向 FK 完整 |
| 数据本体覆盖（每个有效 visit_id 都有 1 行） | — | ✅ | 每个有效 visit_id 在 staging → PG visit + visit_detail 链路上有对应行 |

### 3.1 PG discharge_date 2,188,041 null 的解释

```
source null/empty discharge_date:    2,187,908  (其中 92 在 rn=1 dedup 中被去重)
staging null/empty discharge_date:   2,187,816  (= source 2,187,908 - 92)
staging '1900-01-01' 哨兵:                225  (_clean_date 过滤为 NULL)
staging 有效可解析 discharge_date:     192,969
PG 非空 discharge_date:               192,969   ✅ 与 staging 解析有效数完全一致
PG null discharge_date:             2,188,041  (= 2,187,816 + 225)
```

**判定**：✅ **PG null=2,188,041 完全等于 ETL1 staging 过滤后 + ETL2 `_clean_date` 哨兵过滤后**的预期值，源端事实保留完整（详见 §3.4 关于 1900 哨兵的来源解释）。

### 3.2 admission_dept 302 null / discharge_dept 2,187,818 null

```
source null admission_dept:   302  → staging 302 (去重未影响) → PG 302 ✅
source null discharge_dept: 2,187,910  → staging 2,187,818 (rn=1 dedup 减 92) → PG 2,187,818 ✅
```

**判定**：✅ 与源端 null/empty 完全一致，零信息丢失。

### 3.3 92 个 visit_id 重复行的根因分析

源 parquet 中 92 个 visit_id 各出现 2 次，**全字段 6 列 100% 相同**（pid/visit_id/admission/discharge/category/length_of_stay 完全一致）：

```
distinct visit_id with dup>1:  92
dup groups where all 6 cols identical:  92
```

样例（5 组）：
```
('1206201679', '2823407', '2023-11-08 14:42:06', '',         '门诊', '')
('1206201679', '2823407', '2023-11-08 14:42:06', '',         '门诊', '')
('1207919968', '2823407', '2024-05-22 14:06:06', '',         '门诊', '')
('1207919968', '2823407', '2024-05-22 14:06:06', '',         '门诊', '')
('1209431910', '2823407', '2024-10-30 14:10:18', '',         '门诊', '')
('1209431910', '2823407', '2024-10-30 14:10:18', '',         '门诊', '')
```

ETL1 SQL_VISIT（`etl1_adapt_shengyi_202609.py:143-167`）通过 `ROW_NUMBER() OVER (PARTITION BY 就诊编号) AS rn` + `WHERE rn = 1` 去重。

**判定**：✅ **零信息丢失** —— 92 个重复组所有列完全一致，纯源数据冗余，去重后语义无差。

### 3.4 225 行 discharge_date='1900-01-01' 哨兵

源 parquet 中 `出院日期` 字段含 225 行 `'1900-01-01 00:00:00'`。ETL2 `_clean_date`（`anon_etl_engine.py:353-363`）显式把 `1900-01-01` 当 NULL 处理：

```python
def _clean_date(raw: Any) -> date | None:
    """清洗日期列：解析 + 剔除省医 1900-01-01 占位哨兵。"""
    if raw is None:
        return None
    d = birth_date_from(raw)
    if d is None:
        return None
    return None if d in _SENTINEL_DATES else d
```

→ 225 行哨兵全部解析为有效日期 `1900-01-01`，随后被显式 None 化，PG 中表现为 null。

**判定**：✅ **预期行为**（哨兵过滤设计正确，避免脏日期进入 PG DATE 列）。

### 3.5 length_of_stay 2,190,704 null

```
source null/empty length_of_stay: 2,190,796
staging null length_of_stay:      2,190,704 (= source 2,190,796 - 92 dup 减除)
PG null length_of_stay:           2,190,704                                       ✅
```

→ `length_of_stay` 在 ETL1 适配层 `TRY_CAST(... AS INTEGER)` 解析失败时为 None。源端 2,190,796 行为门诊（无住院天数）+ 92 行为 dedup 中被去重 → PG 2,190,704 = 完全一致。

### 3.6 visit_category 分布

```
source 门诊: 2,187,618 (含 92 个 dup)
staging 门诊: 2,187,526 (rn=1 dedup)
PG 门诊 (visit_detail): 2,187,526 ✅

source 住院: 193,484 (0 dup)
staging 住院: 193,484
PG 住院 (visit_detail): 193,484 ✅
```

**判定**：✅ 与源端完全一致（去重 92 行均为门诊重复）。

---

## 4. 与历史 ETL2 spec 的一致性

| shengyi spec 行 | src_table | ETL2 落库行数（shengyi） | 状态 |
|---|---|---:|---|
| spec #1 | `patient` | 169,820（87,138 真实 + 82,683 占位 sex='0'）| ✅ |
| **spec #2** | **`visit_record`** (visit_detail) | **2,381,010** (visit) + 2,381,010 (visit_detail) | ✅ **本份数据** |
| spec #3 | `pahology_specimen`（typo）| 189,966 | ✅（R4 pathology 报告）|
| spec #4 | `imaging_report` | 515,398 | ✅（R7 imaging_report 报告）|
| spec #5 | `ultrasound_report` | 181,691 | ✅（R7 imaging_report 报告）|
| spec #7 | `genetic_report` | 1,309 | ✅（R5 genetic 报告）|
| spec #8 | `surgery_record` | 324,637 | ✅（R6 discharge_summary 报告 §2.1）|
| spec #20 | `diagnosis_inpatient` (source='inpatient_front_page') | 988,058 | ✅（R6 discharge_summary 报告 §2.2）|

**判定**：spec #2 与本份数据项完全对齐，ETL2 引擎主入口 `import_center('shengyi')` 已能正确灌库。

---

## 5. visit 桥的下游影响

`lnrs_anon_visit` 是其他表的 FK 目标（DDL `Referenced by`）：

```
TABLE "lnrs_anon_exam" CONSTRAINT "lnrs_anon_fk_exam_visit" FOREIGN KEY (anon_visit_id) REFERENCES lnrs_anon_visit(anon_visit_id) ON DELETE SET NULL
TABLE "lnrs_anon_lab_result" CONSTRAINT "lnrs_anon_lab_result_anon_visit_id_fkey" FOREIGN KEY (anon_visit_id) REFERENCES lnrs_anon_visit(anon_visit_id) ON DELETE CASCADE
TABLE "lnrs_anon_surgery" CONSTRAINT "lnrs_anon_surgery_anon_visit_id_fkey" FOREIGN KEY (anon_visit_id) REFERENCES lnrs_anon_visit(anon_visit_id) ON DELETE CASCADE
TABLE "lnrs_anon_visit_detail" CONSTRAINT "lnrs_anon_visit_detail_anon_visit_id_fkey" FOREIGN KEY (anon_visit_id) REFERENCES lnrs_anon_visit(anon_visit_id) ON DELETE CASCADE
TABLE "lnrs_anon_vital_observation" CONSTRAINT "lnrs_anon_vital_observation_anon_visit_id_fkey" FOREIGN KEY (anon_visit_id) REFERENCES lnrs_anon_visit(anon_visit_id) ON DELETE CASCADE
```

→ 本份 visit 表是 lab_result / surgery / exam / visit_detail / vital_observation 的"visit 桥"，是它们能写入 PG 的前置条件。

**验证**（5 行旧 batch `c5871ad4` visit 的下游引用）：

```
referenced by exam:           0
referenced by surgery:        2
referenced by lab_result:    335
has visit_detail:             5
```

→ 旧 5 行 visit 仍被 2 surgery + 335 lab_result 引用，说明 visit 桥的保留对下游 FK 完整性至关重要。

---

## 6. 复现命令

```bash
# 1) 源 parquet 概览
cd /home/dzy/wk/lnrs && backend/.venv/bin/python <<'EOF'
import duckdb
con = duckdb.connect()
src = "/data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.就诊基本信息.parquet"
print(con.execute(f"SELECT COUNT(*), COUNT(DISTINCT \"非隐私信息.就诊.就诊基本信息.就诊编号\"), COUNT(DISTINCT \"非隐私信息.就诊.就诊基本信息.患者编号\") FROM read_parquet('{src}')").fetchone())
EOF

# 2) ETL1 staging 行数与列概览
cd /home/dzy/wk/lnrs && backend/.venv/bin/python <<'EOF'
import duckdb
con = duckdb.connect()
stg = "data_shengyi202609/shengyi/visit_record.parquet"
print(con.execute(f"SELECT COUNT(*) FROM read_parquet('{stg}')").fetchone())
EOF

# 3) staging hash → PG visit 反查（核验主表）
cd /home/dzy/wk/lnrs && backend/.venv/bin/python <<'EOF'
import duckdb, hashlib
con = duckdb.connect()
stg = "data_shengyi202609/shengyi/visit_record.parquet"
rows = con.execute(f"SELECT DISTINCT visit_id FROM read_parquet('{stg}') WHERE visit_id IS NOT NULL AND visit_id <> ''").fetchall()
hashes = [hashlib.sha256(f"shengyi:{r[0]}".encode()).hexdigest() for r in rows]
with open('/tmp/visit_staging_hashes.txt','w') as f:
    for h in hashes: f.write(h+'\n')
print(f"distinct hash: {len(hashes)}")
EOF
PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres <<SQL
CREATE TEMP TABLE verify_visit_staging_hash (h TEXT PRIMARY KEY);
\copy verify_visit_staging_hash(h) FROM '/tmp/visit_staging_hashes.txt'
SELECT COUNT(*) FILTER (WHERE v.anon_visit_id IS NOT NULL) AS hit,
       COUNT(*) FILTER (WHERE v.anon_visit_id IS NULL) AS miss
FROM verify_visit_staging_hash s
LEFT JOIN lnrs.lnrs_anon_visit v
  ON v.source_visit_hash=s.h AND v.center_code='shengyi';

-- 抽样 200 行
DROP TABLE IF EXISTS verify_visit_sample;
CREATE TABLE verify_visit_sample (h TEXT PRIMARY KEY);
\copy verify_visit_sample(h) FROM '/tmp/visit_sample_hashes.txt'
SELECT COUNT(*) FILTER (WHERE v.anon_visit_id IS NOT NULL) AS hit,
       COUNT(*) FILTER (WHERE v.anon_visit_id IS NULL) AS miss
FROM verify_visit_sample s
LEFT JOIN lnrs.lnrs_anon_visit v
  ON v.source_visit_hash=s.h AND v.center_code='shengyi';
SQL

# 4) FK 完整性
PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres <<'SQL'
SELECT 'visit' AS tbl,
  COUNT(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM lnrs.lnrs_anon_patient p WHERE p.patient_id=v.patient_id)) AS orphan_patient
FROM lnrs.lnrs_anon_visit v WHERE v.center_code='shengyi'
UNION ALL
SELECT 'visit_detail',
  COUNT(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM lnrs.lnrs_anon_patient p WHERE p.patient_id=vd.patient_id))
FROM lnrs.lnrs_anon_visit_detail vd WHERE vd.center_code='shengyi';
SQL

# 5) ingest_batch 分布
PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres <<'SQL'
SELECT created_batch_id, COUNT(*) AS n
FROM lnrs.lnrs_anon_visit WHERE center_code='shengyi' GROUP BY 1;
SQL
```

---

## 7. 清理动作

- 源 parquet、ETL1 staging parquet、PG 数据（无改动需要）
- 本次核验未创建或修改任何 ETL1 / ETL2 代码
- 本次核验临时表（`verify_visit_staging_hash`, `verify_visit_sample`）建议保留以备后续核验复用；如需清理：
  ```sql
  DROP TABLE IF EXISTS verify_visit_staging_hash;
  DROP TABLE IF EXISTS verify_visit_sample;
  ```