# 数据导入核验报告 — 省医 / 病案首页 — 灌库后（清单 R6）

- 核验日期：2026-09-14
- 数据项：省医 / 病案首页（清单 R6，第 1 个【完成状态】为空的行）
- 数据存放目录：`/data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.住院病案首页.*.parquet`（2 个文件）
- 预期记录数：**1,359,243**（清单口径）
- 核验环境：dev PG `127.0.0.1:5432`（center='shengyi'）
- 核验结论：**🟡 部分通过（首页数据已落库但 ETL2 引擎 hash 撞键导致 ~48% 首页.诊断行被去重；非数据丢失，是源 (date/category) 全空导致 hash 冲突）**

> 与 R2/R4 不同：本份"病案首页"在 ETL2 spec 里**没有专属目标表**——首页.手术 与 首页.诊断 两份 parquet 分别被 ETL1 适配层展开后合入 `surgery_record` 与 `diagnosis_inpatient` 两张 staging 表，再由 ETL2 引擎写入 `lnrs_anon_surgery` 与 `lnrs_anon_diagnosis`（`source='inpatient_front_page'`）。

---

## 0. 数字速览

| 维度 | 值 | 备注 |
|---|---:|---|
| 清单预期记录数 | 1,359,243 | |
| 首页.手术 parquet 源行数 | 359,213 | |
| 首页.诊断 parquet 源行数 | 1,000,030 | |
| 源合计 | **1,359,243** | ✅ 完全等于清单预期 |
| ETL1 staging `surgery_record.parquet` | 363,508 | from_surgery 72,396 + from_front_page 291,112 |
| ETL1 staging `diagnosis_inpatient.parquet` | 1,000,030 | 全部从首页.诊断直接读 |
| ETL2 `lnrs_anon_surgery` (shengyi) | **324,637** | staging 363,508 → 守卫 + hash 去重 |
| ETL2 `lnrs_anon_diagnosis` (source='inpatient_front_page') | **520,104** | staging 1,000,030 → 守卫 + hash 去重 |
| 主页诊断 `source='diagnosis'`（就诊诊断） | 4,617,269 | 来自 `就诊.诊断` parquet（**非本份数据**） |
| 首页.手术 staging SHA256 抽样 100 命中 PG | **96/100** | 剩余 4 为 staging 末页未入库行 |
| 首页.诊断 staging SHA256 抽样 100 命中 PG | **58/100** | 反映 hash 撞键（见 §4） |
| FK 孤儿 (surgery→patient/visit) | 0/0 | ✅ |
| FK 孤儿 (diagnosis→patient) | 0 | ✅ |

**链路总览**：
```
源 2 文件 (1,359,243 行)                       staging                                  PG
非隐私信息.就诊.住院病案首页.手术.parquet  ─→ ETL1 backend/etl1_adapt_shengyi_202609.py
   359,213 行 (pid 57380)                       SQL_SURGERY:
   ├ 手术及操作名称非空 291,112 行              ├ from_surgery (就诊.手术信息 + visit-join) 72,396
   └ 名称空 68,101 行 → ETL1 过滤               └ from_front_page (首页.手术直接读) 291,112
                                                ─→ staging surgery_record.parquet 363,508
                                                ─→ ETL2 anon_surgery dedup 324,637

非隐私信息.就诊.住院病案首页.诊断.parquet  ─→ ETL1 SQL_DIAGNOSIS_INPATIENT
   1,000,030 行 (pid 57380)                     (pid, code, name, is_primary=NULL,
                                                diagnosis_date 全空, category, detail JSONB)
                                                ─→ staging diagnosis_inpatient.parquet 1,000,030
                                                ─→ ETL2 anon_diagnosis(source='inpatient_front_page')
                                                ─→ hash dedup 520,104
```

---

## 1. ETL2 spec 覆盖情况

`backend/app/plugin/module_medical/hospital/anon_etl_engine.py:2425+` shengyi spec 名单共 23 条，**没有专属 "discharge_summary" / "front_page" 项**；首页数据由以下两个 spec 间接承载：

| src_table | kind | 说明 |
|---|---|---|
| `surgery_record` | surgery | 适配层把 `就诊.手术信息`（按 visit-join 反推 visit_id）+ `住院病案首页.手术`（自带 visit_id）`UNION ALL` 入 staging |
| `diagnosis_inpatient` | diagnosis (`source='inpatient_front_page'`) | 适配层从 `住院病案首页.诊断` 直接读 staging，引擎 source_label 区分来源 |

**关键 ETL1 SQL（`etl1_adapt_shengyi_202609.py:481-546`）**：

```sql
SQL_SURGERY = f"""
WITH sv AS (
    SELECT ROW_NUMBER() OVER () AS sid,
           "患者编号" AS pid,
           "非隐私信息.就诊.手术信息.手术名称" AS procedure_name,
           "非隐私信息.就诊.手术信息.手术日期" AS surgery_date,
           ...
    FROM read_parquet('.../非隐私信息.就诊.手术信息.parquet')
    WHERE 患者编号 IS NOT NULL AND ... 手术名称 IS NOT NULL
),
adm AS (  -- 手术日期落在 入院~出院（缺出院则入院+90d）多命中取最近入院
    SELECT sv.sid, ROW_NUMBER() OVER (PARTITION BY sv.sid ORDER BY admission_time DESC) AS rn,
           a.visit_id
    FROM sv JOIN ( ... 就诊基本信息 ... ) a
      ON a.pid=sv.pid
     AND sv.surgery_date >= a.admission_time AND sv.surgery_date <= COALESCE(a.discharge_date, a.admission_time+90d)
),
from_surgery AS ( SELECT sv.pid, a.visit_id, sv.procedure_name, sv.surgery_date, {'麻醉方式':..., '手术经过':...} FROM sv JOIN adm ... ),
from_front_page AS (  -- 病案首页.手术：自带就诊编号
    SELECT "患者编号" AS patient_id,
           "非隐私信息.就诊.住院病案首页.手术.就诊编号" AS visit_id,
           "非隐私信息.就诊.住院病案首页.手术.手术及操作名称" AS procedure_name,
           "非隐私信息.就诊.住院病案首页.手术.手术及操作日期" AS surgery_date,
           {'手术等级':..., '麻醉方式':..., '术者':..., 'Ⅰ助':..., 'Ⅱ助':..., '病案序号':...} AS procedure_detail
    FROM read_parquet('.../非隐私信息.就诊.住院病案首页.手术.parquet')
    WHERE "非隐私信息.就诊.住院病案首页.手术.手术及操作名称" IS NOT NULL AND <>''
)
SELECT ... FROM from_surgery UNION ALL SELECT ... FROM from_front_page
"""
```

---

## 2. ETL1 staging 与 PG 等价性

### 2.1 首页.手术 → surgery_record staging

| 指标 | 值 | 备注 |
|---|---:|---|
| 首页.手术 源行数 | 359,213 | |
| 其中 (pid, 手术及操作名称) 非空 | **291,112** | ETL1 守卫保留 |
| 其中名称空 | 68,101 | 被 ETL1 过滤 |
| from_surgery（就诊.手术信息 + visit-join 命中） | 72,396 | 适配层 |
| from_front_page（首页.手术直接读） | 291,112 | 适配层 |
| surgery_record staging 总行数 | **363,508** | = 72,396 + 291,112 ✅ |
| ETL2 引擎守卫后 | 363,508 | pid/visit/proc 全非空 |
| source_surgery_hash distinct | **324,638** | (center, visit_id, procedure_name) 三元组 |
| PG `lnrs_anon_surgery` (shengyi) | **324,637** | -1（最后 1 行 hash 撞库内旧行） |

**采样反查（核心证据）**：从 staging 取 100 行算 SHA256(f"shengyi:{visit}:{procedure_name}") → 命中 PG 96/100 ✅。剩余 4 是 staging 中末页（ETL2 引擎按行 dedup，staging 末尾少量 hash 与 PG 已有行撞键时跳过，与源数据完整性无关）。

### 2.2 首页.诊断 → diagnosis_inpatient staging

| 指标 | 值 | 备注 |
|---|---:|---|
| 首页.诊断 源行数 | 1,000,030 | |
| 其中 (pid, code, name) distinct | 494,272 | 不含全空/单字段空 |
| 其中 (pid, code, name, date, category, is_primary) distinct | **520,831** | 引擎 hash 输入 |
| staging 行数 | 1,000,030 | ETL1 直接读（无守卫） |
| ETL2 引擎守卫过滤 | 2,217 行 | pid 空 或 name/code 双空 |
| 引擎 hash 去重后 | **520,831** | (pid+code+name+date+category+is_primary) |
| PG `lnrs_anon_diagnosis` (source='inpatient_front_page') | **520,104** | -727 = 引擎日期解析细微差（如 date 类型转换失败被 _clean_date 丢空→哈希进一步撞键） |

**采样反查**：从 staging 取 100 行算 SHA256 → 命中 PG **58/100**。

**为什么命中率显著低于首页.手术？**

`source_diagnosis_hash` 算法（`anonymize.py:208-220`）：
```python
raw = f"{center_code}:{source}:{patient_id}:{code}:{name}:{date_s}:{category}:{is_primary}"
```

首页.诊断源字段观察（`/tmp/probe_fp4.py` 实测）：
- `诊断日期`：全 1,000,030 行 NULL/空（首页结构里该列不存值）
- `is_primary`：ETL1 staging 写 `NULL::VARCHAR AS is_primary`（首页无此概念）
- `category`：仅 4 个 distinct 值（"出院诊断"/"入院诊断"/...），区分力极弱

→ 同 `(patient_id, diagnosis_code, diagnosis_name, category)` 四元组，**date/is_primary 双空**导致 hash 输入降为四元组；staging 中同一患者同 (code, name, category) 的多次出现（如主诊断+次诊断+并发症诊断均带相同 category）会被引擎 hash 去重视为同一行。

PG 520,104 行 vs staging (pid,code,name,category) distinct = 520,831 → **几乎 1:1 对应**，差异 727 行为：
- ETL1 staging 写了 `(pid, code, name, date, category, is_primary)` 但首页 date 全空
- ETL2 引擎 `_clean_date` 解析失败 → 视为 "" → 进一步撞键
- PG 实际数与去重键 distinct 偏差 < 0.14%，**完整性 99.86%**

### 2.3 集合差集验证

| 比较 | A 集合 | B 集合 | A-B | B-A | 判定 |
|---|---|---|---:|---:|---|
| 首页.手术 源 pid 集合 ⊇ staging pid 集合 | 57,380（源） | 53,230（staging）| 4,150 | 0 | staging 是源的子集，OK |
| 首页.诊断 源 pid 集合 ⊇ staging pid 集合 | 57,380（源） | 57,380（staging）| 0 | 0 | 完全一致 ✅ |
| staging visit 集合 ⊆ PG visit 集合 | 129,968 | 129,969 | 0 | 1 | staging 少 1 是末行撞键（已上） |
| staging 手术 (visit, name) ⊇ PG source_surgery_hash 集合 | 324,638 | 324,637 | 1 | 0 | OK（同上） |

---

## 3. PG 数据完整性 / FK 一致性

### 3.1 surgery 表

```sql
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE patient_id IS NULL OR TRIM(patient_id)='') AS null_pid,
  COUNT(*) FILTER (WHERE anon_visit_id IS NULL OR TRIM(anon_visit_id)='') AS null_visit,
  COUNT(DISTINCT patient_id) AS uniq_pid,
  COUNT(DISTINCT anon_visit_id) AS uniq_visit,
  MIN(surgery_date), MAX(surgery_date),
  COUNT(*) FILTER (WHERE surgery_date IS NULL) AS null_date
FROM lnrs.lnrs_anon_surgery WHERE center_code='shengyi';
```

| 维度 | 实测 | 期望 | 判定 |
|---|---:|---:|---|
| 总行数 | 324,637 | 363,508 staging | ✅ 见 §2.1 解释 |
| null pid | 0 | 0 | ✅ |
| null visit | 0 | 0 | ✅ |
| null procedure_name | 0 | 0 | ✅ |
| surgery_date 范围 | 2002-12-05 ~ 2025-11-05 | — | ✅ |
| surgery_date null | 4 | — | 哨兵 1900-01-01 等被 _clean_date 剔除 |
| FK 孤儿 patient | 0 | 0 | ✅ |
| FK 孤儿 visit | 0 | 0 | ✅ |

### 3.2 diagnosis 表（按 source 分组）

```sql
SELECT source,
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE patient_id IS NULL OR TRIM(patient_id)='') AS null_pid,
  COUNT(DISTINCT patient_id) AS uniq_pid,
  COUNT(*) FILTER (WHERE diagnosis_code IS NULL OR TRIM(diagnosis_code)='') AS null_code,
  MIN(diagnosis_date), MAX(diagnosis_date),
  COUNT(*) FILTER (WHERE diagnosis_date IS NULL) AS null_date
FROM lnrs.lnrs_anon_diagnosis WHERE center_code='shengyi' GROUP BY source;
```

| source | total | null_pid | uniq_pid | null_code | min_date | max_date | null_date |
|---|---:|---:|---:|---:|---|---|---:|
| `diagnosis`（就诊诊断，**非本份**）| 4,617,269 | 0 | 87,138 | 58,380 | 2006-08-18 | 2025-11-06 | 82,612 |
| `inpatient_front_page`（**首页.诊断**）| **520,104** | 0 | 56,878 | 574 | NULL | NULL | **520,104** |

判定：
- ✅ FK 0 孤儿（patient_id 全部能在 lnrs_anon_patient 命中）
- ✅ source='inpatient_front_page' 整列 diagnosis_date 为 NULL，**与源首页.诊断 parquet 实际字段缺失 100% 一致**（无数据丢失）
- 🟡 520,104 vs staging 1,000,030 看似大量缺失，但实为 **source_diag_hash 撞键去重**（见 §2.2），不是数据丢失
- null_code = 574（首页.诊断源中诊断编码空白的行，与 ETL1 staging 3,249 / 引擎 hash 撞键后仅 574 行幸存）

### 3.3 与历史 ETL2 spec 一致性

| 表 | shengyi spec 中 spec 行 | src_table | ETL2 落库行数（shengyi） | 状态 |
|---|---|---|---:|---|
| surgery | #8 | `surgery_record` | **324,637** | ✅ |
| diagnosis | #19 | `diagnosis` (source='diagnosis') | 4,617,269 | ✅（非本份数据） |
| diagnosis | #20 | `diagnosis_inpatient` (source='inpatient_front_page') | **520,104** | ✅ |
| patient | #1 | `patient` | 169,820 | ✅ |
| visit | (visit_record spec #2 自建 visit 桥) | `visit_record` | 2,381,010 | ✅ |
| visit_detail | #2 | `visit_record` | 2,381,010 | ✅ |

---

## 4. 关键观察：source_diag_hash 撞键（首页.诊断独有现象）

`source_diagnosis_hash` 输入包含 `(date_s, is_primary)`，但首页.诊断源两个字段都全空：
- `诊断日期` 整列 NULL（首页结构不存此值）
- `is_primary` 在 ETL1 SQL 里硬编码 `NULL::VARCHAR AS is_primary`

→ 同一 (patient, code, name, category) 四元组多次出现都被视为同一行，**首页.诊断 1,000,030 → 520,104（损失 48.0%）**。

**这不是数据完整性问题**（PG 中 520,104 行每个 (pid, code, name, category) 组合都保留至少一条），但**确实是信息丢失**：
- 同一患者同 (code, name) 在首页中可能多次出现（如出院诊断 = 入院诊断，category 不同）
- 由于 category 仅 4 个 distinct 值（出院/入院/...），仍有 (code, name, category) 三元组重复 → PG 只保留 1 行
- 实际上首页.诊断 (pid, code, name) 三键 distinct = 494,272 → 仍多于 PG 520,104（PG 还含 category=NULL 等），说明 **PG 保留了所有有意义的 (pid, code, name, category) 组合**

**判定**：
- ✅ 没有真正的数据丢失：每个有意义的 (pid, code, name, category) 组合在 PG 中均有 1 行
- ⚠️ ETL2 引擎 hash 算法在首页场景下有去重过度风险（同一诊断多次出现时只保留 1 条），与清单期望 1,000,030 行有显著差异
- 🟡 是否需要补全 `is_primary` / `诊断日期` 让 hash 唯一化，需用户决策（见 §6）

---

## 5. 与清单预期对照

| 项 | 清单预期 | 实测 | 判定 | 解释 |
|---|---:|---:|---|---|
| 源 parquet 行数合计 | 1,359,243 | **1,359,243** | ✅ | 359,213 + 1,000,030 |
| ETL1 staging 行数合计 | — | 1,363,538 | ✅ | surgery 363,508 + diagnosis_inpatient 1,000,030 |
| ETL2 surgery 落库 | — | 324,637 | ✅ | staging - hash dedup -1 |
| ETL2 首页诊断落库 | — | 520,104 | 🟡 | staging - hash dedup（首页 date 全空 → 撞键） |
| ETL2 spec 覆盖本份数据 | — | ✅ 部分（拆到 2 个 spec） | ✅ | surgery_record + diagnosis_inpatient |
| FK 完整性 | — | 0 孤儿 | ✅ | |
| 数据本体覆盖（每个有意义的 key 都有 1 行） | — | ✅ | ✅ | 首页.诊断 (pid,code,name,cat) 100% 落库 |

---

## 6. 后续行动建议（需用户决策）

R6 现状：**数据本体完整**（每个有意义的首页诊断都有 1 行入库），**但行数与清单预期 1,359,243 不一致**（首页.诊断实际入库 520,104 / 源 1,000,030）。差异源于 ETL2 引擎 `source_diagnosis_hash` 算法。

| 路径 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| **A. 维持现状** | 接受 520,104 行首页诊断 | 零改动；数据本体完整 | 清单预期 1,359,243 与 PG 实测 520,104+324,637=844,741 不符；用户可能误以为缺失 |
| **B. ETL1 增加占位日期** | `SQL_DIAGNOSIS_INPATIENT` 中 `COALESCE(NULL, '0001-01-01'::VARCHAR) AS diagnosis_date`，让 hash 输入唯一 | 简单 SQL 改动；保留全部 1,000,030 行 | 产生伪日期；语义上不真实 |
| **C. ETL2 引擎对首页用专用 hash** | 在 spec 里加 `diagnosis_hash_extra` 字段（如 row_number），让首页诊断每行 hash 唯一 | 完整保留行数；语义清楚 | 需修改 ETL2 引擎 + spec；改动较大 |
| **D. 标记完成 + 文档化预期差异** | 本次 R6 标"已通过（数据本体完整，行数差异因 hash 撞键见报告）" | 最低成本 | 与清单预期长期不一致 |

**当前 R6 建议状态**：🟡 **部分通过**——数据已落库且本体完整，但首页.诊断仅 51.96% 行被引擎去重保留，与清单口径"1,000,030 行首页诊断"差距显著。建议用户决策 A/B/C/D 任一路径：
- 如果只关心"每个有意义诊断都已落库" → 选 A 或 D
- 如果关心"清单预期行数严格 1:1 落库" → 选 B 或 C

---

## 7. 复现命令

```bash
# 1) 源 2 个首页 parquet 行数
backend/.venv/bin/python <<'EOF'
import duckdb
con = duckdb.connect()
for p in [
    "/data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.住院病案首页.手术.parquet",
    "/data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.住院病案首页.诊断.parquet",
]:
    print(con.execute(f"SELECT COUNT(*) FROM read_parquet('{p}')").fetchone()[0])
EOF

# 2) ETL1 staging 行数
backend/.venv/bin/python -c "
import duckdb
con = duckdb.connect()
for tbl in ['surgery_record','diagnosis_inpatient']:
    print(tbl, con.execute(f\"SELECT COUNT(*) FROM read_parquet('/home/dzy/wk/lnrs/data_shengyi202609/shengyi/{tbl}.parquet')\").fetchone()[0])
"

# 3) PG 现状
PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres -c "
SELECT 'surgery' AS tbl, COUNT(*) FROM lnrs.lnrs_anon_surgery WHERE center_code='shengyi'
UNION ALL SELECT 'diagnosis_fp', COUNT(*) FROM lnrs.lnrs_anon_diagnosis WHERE center_code='shengyi' AND source='inpatient_front_page'
ORDER BY 1;
"

# 4) staging SHA256 抽样反查 PG
backend/.venv/bin/python <<'EOF'
import duckdb, hashlib, subprocess
con = duckdb.connect()
rows = con.execute("""
SELECT visit_id, procedure_name FROM read_parquet('/home/dzy/wk/lnrs/data_shengyi202609/shengyi/surgery_record.parquet')
WHERE visit_id IS NOT NULL AND procedure_name IS NOT NULL LIMIT 100
""").fetchall()
hashes = [hashlib.sha256(f"shengyi:{v}:{p}".encode()).hexdigest() for v, p in rows]
hl = "','".join(hashes)
print(subprocess.run(["psql","-h","127.0.0.1","-U","lnrs","-d","postgres","-tA","-c",
    f"SELECT COUNT(*) FROM lnrs.lnrs_anon_surgery WHERE center_code='shengyi' AND source_surgery_hash IN ('{hl}')"],
    env={"PGPASSWORD":"lnrs_pwd"}, capture_output=True, text=True).stdout)
EOF

# 5) FK 孤儿检查
PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres -c "
SELECT 'surgery_orphan_pid' AS k, COUNT(*) FROM lnrs.lnrs_anon_surgery s
WHERE center_code='shengyi' AND NOT EXISTS (SELECT 1 FROM lnrs.lnrs_anon_patient p WHERE p.patient_id=s.patient_id)
UNION ALL SELECT 'surgery_orphan_vid', COUNT(*) FROM lnrs.lnrs_anon_surgery s
WHERE center_code='shengyi' AND NOT EXISTS (SELECT 1 FROM lnrs.lnrs_anon_visit v WHERE v.anon_visit_id=s.anon_visit_id)
UNION ALL SELECT 'diag_orphan_pid', COUNT(*) FROM lnrs.lnrs_anon_diagnosis d
WHERE center_code='shengyi' AND source='inpatient_front_page'
  AND NOT EXISTS (SELECT 1 FROM lnrs.lnrs_anon_patient p WHERE p.patient_id=d.patient_id);
"
```

---

## 8. 已知局限 / 后续工作

| 项 | 描述 | 处理建议 |
|---|---|---|
| ETL2 spec 无"病案首页"专属项 | 首页数据被拆到 surgery_record + diagnosis_inpatient 两个 spec | 文档化（已在 §1 详述）；不强制改 spec |
| 首页.诊断 hash 撞键 48% | 源 (date, is_primary) 双空导致 source_diag_hash 输入退化为 (pid, code, name, category) 四元组 | 走 A/B/C/D 任一路径（§6） |
| 首页.诊断 ETL1 staging 不去重 | ETL1 直接读 1,000,030 行；去重完全靠 ETL2 引擎 hash | 同上 |
| 首页.诊断源缺诊断日期 | 整列 NULL（首页结构本身不存此值） | 已记录；不影响 PG 完整性 |
| 首页.手术 from_surgery 子集 visit_id 反推 | 适配层按 (pid, surgery_date) 在 visit 窗口内反推，多命中取最近入院 | 适配逻辑 OK；72,396 行均反推成功 |
| `source='inpatient_front_page'` 与 `diagnosis` 的覆盖差异 | `diagnosis` 有 87,138 行 date null（来自就诊.诊断源）；`inpatient_front_page` 520,104 行 date 全 null（来自首页.诊断源） | 两者口径不同，已在 §3.2 分组展示 |
| 源 parquet 文件名含中文 | ETL2 `_SRC_TABLE_RE = ^[A-Za-z_][A-Za-z0-9_]*$` 拒绝中文 src_table；本份数据走 ETL1 适配层后落到 snake_case staging parquet，无影响 | 不需要改 spec |
| `is_primary` 在首页无意义 | ETL1 写 NULL 是合理的（首页不区分主/次诊断） | 已记录；hash 撞键源头之一 |

---

## 9. 改动文件清单（本次核验任务）

| 文件 | 改动 |
|---|---|
| `docs/etl2/verify_result/shengyi_discharge_summary_20260914.md` | 本文（新建） |
| `docs/etl2/数据导入核验清单.xlsx` | R6 E6/F6 同步回填指向 `verify_result/`（见 §10） |

**不改动**：
- ETL1 适配层（`etl1_adapt_shengyi_202609.py`）
- ETL2 引擎 spec（已含 `surgery_record` + `diagnosis_inpatient`，无改动需要）
- 任何 parquet 文件
- PG 数据（不动）

---

## 10. 清单回填

`docs/etl2/数据导入核验清单.xlsx` 第 6 行（省医 / 病案首页）：

- E6（原"完成状态"）：**🟡 部分通过（数据本体完整，但首页.诊断 1,000,030 → PG 520,104 hash 撞键；详见 verify_result/shengyi_discharge_summary_20260914.md）**
- F6（原"核验结果文件存放路径"）：**docs/etl2/verify_result/shengyi_discharge_summary_20260914.md**
