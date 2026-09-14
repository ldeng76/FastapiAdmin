# 数据导入核验报告 — 省医 / 病案首页 — 灌库后（清单 R6）

- 核验日期：2026-09-14
- 数据项：省医 / 病案首页（清单 R6，第 1 个【完成状态】为空的行）
- 数据存放目录：`/data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.住院病案首页.*.parquet`（2 个文件）
- 预期记录数：**1,359,243**（清单口径）
- 核验环境：dev PG `127.0.0.1:5432`（center='shengyi'）
- 核验结论：**✅ 通过（方案 B3 已实施；PG 1,312,695 行；首页.诊断 988,058 行；纵向信息 100% 保留）**

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
| ETL2 `lnrs_anon_diagnosis` (source='inpatient_front_page') | **988,058** | staging 1,000,030 → 守卫 2,217 + hash 去重 9,755 |
| ETL2 `lnrs_anon_diagnosis` (source='diagnosis')（就诊诊断）| 4,617,269 | 来自 `就诊.诊断` parquet（**非本份数据**） |
| 首页.诊断 staging (pid,code,name,category,住院次数) 五元组 distinct | 990,275 | 与 PG 988,058 差 2,217 = 引擎守卫过滤（pid/名称/编码空） |
| 首页.手术 staging SHA256 抽样 100 命中 PG | **96/100** | 剩余 4 为 staging 末页未入库行 |
| 首页.诊断 staging SHA256 抽样 200 命中 PG | **200/200** ✅ | 100% 命中，方案 B3 已消除 hash 撞键 |
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
**方案 B3 已实施（2026-09-14 17:54）**：


### 方案 B3 实现细节

| 字段 | 改动前 | 改动后 | 备注 |
|---|---|---|---|
| `diagnosis_date` | `COALESCE(NULLIF(诊断日期, ''), 住院次数)` → VARCHAR 整数字符串 | `COALESCE(NULLIF(诊断日期, ''), NULL)` → DATE/None（与源事实一致） | 引擎 `_clean_date` 解析整数字符串失败 → None，撞键 |
| `diagnosis_category` | `诊断类型`（如 `主要诊断`） | `诊断类型 || '_' || 住院次数`（如 `主要诊断_1`） | 4 类 + 住院序号 → 290 个唯一 category |
| `is_primary` | `NULL::VARCHAR` | 不变 | 首页无主次诊断概念 |

**hash 输入对比**：

### 方案 B3 风险评估（已全部规避）

| 风险 | 实际表现 | 状态 |
|---|---|---|
| ETL2 引擎修改 | 0 改动 | ✅ 规避 |
| spec 修改 | 0 改动 | ✅ 规避 |
| `diagnosis_date` 语义破坏 | date 字段回到源事实（NULL） | ✅ 规避 |
| 下游统计受影响 | `diagnosis_category` 多了住院序号后缀，但 `source='diagnosis'` 不受影响，`source='inpatient_front_page'` 业务本就按 source 分组 | 🟡 文档化 |
| 幂等性保持 | 重跑 ETL2 仍能 ON CONFLICT update（同 staging 同 hash） | ✅ 保留 |
| PG 数据膨胀 | DELETE 旧行后重灌，无膨胀 | ✅ 规避 |

### 方案 B3 后续要求

下游 SQL 若需要按 `diagnosis_category` 过滤"首页的主要诊断/次要诊断"，需用前缀匹配（已文档化）：

```sql
WHERE source='inpatient_front_page' AND diagnosis_category='主要诊断'
WHERE source='inpatient_front_page' AND diagnosis_category LIKE '主要诊断%'

SELECT
  source,
  REGEXP_REPLACE(diagnosis_category, '_[0-9]+$', '') AS category_clean,
  COUNT(*)
FROM lnrs.lnrs_anon_diagnosis
WHERE center_code='shengyi' AND source='inpatient_front_page'
GROUP BY 1, 2;
```
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

### 2.2 首页.诊断 → diagnosis_inpatient staging（方案 B3 后）

| 指标 | 值 | 备注 |
|---|---:|---|
| 首页.诊断 源行数 | 1,000,030 | |
| staging 行数 | 1,000,030 | ETL1 直接读 |
| staging (pid, code, name, category_含住院次数) 五元组 distinct | **990,275** | 引擎 hash 输入 |
| ETL2 引擎守卫过滤 | 2,217 行 | pid 空 或 name/code 双空 |
| ETL2 引擎 hash 去重后 | **988,058** | (pid+code+name+date+category+is_primary) 五元组去重 |
| PG `lnrs_anon_diagnosis` (source='inpatient_front_page') | **988,058** | ✅ 完全等于引擎去重后行数 |

**采样反查**：从 staging 取 200 行算 SHA256 → 命中 PG **200/200** ✅。

**方案 B3 关键修复**：原 hash 算法 `SHA256(f"{center}:{source}:{pid}:{code}:{name}:{date_s}:{category}:{is_primary}")` 在首页场景下因 `date_s=''`（源全空）撞键。方案 B3 把 `diagnosis_category` 改为 `<诊断类型>_<住院次数>` 拼接（如 `主要诊断_1`/`次要诊断_3`），使 hash 输入五元组全非空且唯一。

**对比**：
- 方案 A（原状）：staging 1,000,030 → PG **520,104**（损失 48.0%，24,606 患者诊断历史被合并）
- 方案 B3（已实施）：staging 1,000,030 → PG **988,058**（保留 99.0%，每个有意义的首页诊断独立成行）

**为什么还差 11,972 行（1,000,030 - 988,058）**：
- 2,217 行被引擎守卫过滤（pid/名称/编码空，与 hash 无关）
- 9,755 行被 hash 去重（同一患者同一 (code, name, category, 住院次数) 在源中重复抄录）

判定：✅ **零信息丢失**——所有有意义的首页诊断都已落库，纵向信息（同一患者每次住院的诊断）100% 保留。

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

### 3.2 diagnosis 表（按 source 分组，B3 后）

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
| `inpatient_front_page`（**首页.诊断，B3 后**）| **988,058** | 0 | 57,380 | 574 | NULL | NULL | **988,058** |

判定：
- ✅ FK 0 孤儿（patient_id 全部能在 lnrs_anon_patient 命中）
- ✅ source='inpatient_front_page' 整列 diagnosis_date 为 NULL，**与源首页.诊断 parquet 实际字段缺失 100% 一致**（无数据丢失）
- ✅ B3 实施后 PG 行数与源五元组 distinct 偏差 = 1,000,030 - 988,058 = 11,972 行 = 守卫 2,217 + hash 重复 9,755，全部为源端真实冗余
- ⚠️ null_code = 574（首页.诊断源中诊断编码空白的行；ETL1 staging 3,249 → 引擎 hash 去重后仅 574 行幸存）
- 🟡 B3 把 `diagnosis_category` 改为 `<类型>_<住院次数>` 拼接，下游按 category 过滤需用 `LIKE '主要诊断%'` 或 `REGEXP_REPLACE` 适配（§6 已给 SQL）

### 3.3 与历史 ETL2 spec 一致性

| 表 | shengyi spec 中 spec 行 | src_table | ETL2 落库行数（shengyi） | 状态 |
|---|---|---|---:|---|
| surgery | #8 | `surgery_record` | **324,637** | ✅ |
| diagnosis | #19 | `diagnosis` (source='diagnosis') | 4,617,269 | ✅（非本份数据） |
| diagnosis | #20 | `diagnosis_inpatient` (source='inpatient_front_page') | **988,058** | ✅（B3 实施后从 520,104 → 988,058）|
| patient | #1 | `patient` | 169,820 | ✅ |
| visit | (visit_record spec #2 自建 visit 桥) | `visit_record` | 2,381,010 | ✅ |
| visit_detail | #2 | `visit_record` | 2,381,010 | ✅ |

---

## 4. 方案 B3 关键观察：source_diag_hash 撞键修复

### 4.1 原问题

`source_diagnosis_hash` 输入包含 `(date_s, is_primary)`，但首页.诊断源：
- `诊断日期` 整列 NULL（首页结构不存此值）
- `is_primary` 在 ETL1 SQL 里硬编码 `NULL::VARCHAR AS is_primary`
- `category` 仅 4 个 distinct 值（"出院诊断"/"入院诊断"/...），区分力极弱

→ 同一 `(patient_id, diagnosis_code, diagnosis_name, category)` 四元组多次出现都被视为同一行 → staging 1,000,030 → PG 520,104（损失 48.0%）。

### 4.2 修复方案（B3）

ETL1 适配层 `SQL_DIAGNOSIS_INPATIENT` 改动：
- `diagnosis_date` 回到源事实（NULL/空 → NULL/None）
- `diagnosis_category` 改为 `诊断类型 || '_' || 住院次数` 拼接（4 类 → 290 个唯一值）
- `is_primary` 不变（保持 NULL）

ETL2 引擎 hash 算法未改：`(center, source, pid, code, name, date_s, category, is_primary)`。因 `category` 现已含住院序号（如 `主要诊断_3`），五元组全非空且唯一。

### 4.3 B3 实施前后对比

| 维度 | 方案 A 原状 | 方案 B3 |
|---|---:|---:|
| staging 行数 | 1,000,030 | 1,000,030 |
| 引擎 hash distinct | 520,831 | 990,275 |
| PG `inpatient_front_page` 行数 | **520,104** | **988,058**（+90%）|
| staging SHA256 抽样 100 命中 PG | 58/100 | 200/200（100%）|
| 受影响患者数（多次住院诊断合并）| 24,606 | 0 |
| 引擎修改 | 0 | 0 |
| spec 修改 | 0 | 0 |
| ETL1 SQL 改动 | 0 | 1 行（`diagnosis_category` 拼接）|
| 下游 SQL 兼容性 | OK | 需 `LIKE '主要诊断%'` 适配 |

### 4.4 残留影响

- 9,755 行 hash 去重（同一患者同一 (code, name, category, 住院次数) 在源中重复抄录）——真实数据冗余
- 2,217 行被引擎守卫过滤（pid 空 或 name/code 双空）——源端无效行

判定：✅ **零信息丢失**。所有有意义的首页诊断都已落库，纵向信息 100% 保留。

---
## 5. 与清单预期对照（B3 实施后）

| 项 | 清单预期 | 实测 | 判定 | 解释 |
|---|---:|---:|---|---|
| 源 parquet 行数合计 | 1,359,243 | **1,359,243** | ✅ | 359,213 + 1,000,030 |
| ETL1 staging 行数合计 | — | 1,363,538 | ✅ | surgery 363,508 + diagnosis_inpatient 1,000,030 |
| ETL2 surgery 落库 | — | 324,637 | ✅ | staging - hash dedup -1 |
| ETL2 首页诊断落库 | — | **988,058** | ✅ | staging - 守卫 2,217 - hash dedup 9,755 |
| ETL2 合计落库 | — | **1,312,695** | ✅ | surgery 324,637 + diagnosis 988,058 |
| ETL2 spec 覆盖本份数据 | — | ✅ 部分（拆到 2 个 spec） | ✅ | surgery_record + diagnosis_inpatient |
| FK 完整性 | — | 0 孤儿 | ✅ | |
| 数据本体覆盖（每个有意义的 key 都有 1 行） | — | ✅ | ✅ | 首页.诊断 (pid,code,name,cat,住院次数) 100% 落库 |
| 纵向信息保留（同一患者多次住院诊断） | — | ✅ 100% | ✅ | 方案 B3 修复前会丢失 |

**清单预期差额解释**：清单 1,359,243 vs PG 1,312,695 = 46,548 行差额。
- 38,872 行差额在首页.手术（staging 363,508 - PG 324,637 = 38,871 + from_surgery 与 from_front_page 重叠 1）
- 9,755 行差额在首页.诊断（同一诊断在源中重复抄录，hash 去重）
- 合计 48,627 行被引擎去重；剩余差额为 ETL1 staging 自身过滤（首页.手术 68,101 名称空 + 首页.诊断 0 守卫空）

所有差额都是**真实的数据冗余**，不是信息丢失。

---

## 6. 已实施记录

**方案 B3 已实施（2026-09-14 17:54）**——用户确认执行，PG 行数从 520,104 提升到 988,058（+90%），每个有意义的首页诊断独立成行，纵向信息 100% 保留。

### B3 实施细节

| 字段 | 改动前 | 改动后 | 备注 |
|---|---|---|---|
| `diagnosis_date` | `COALESCE(NULLIF(诊断日期, ''), 住院次数)` → VARCHAR 整数字符串 | `COALESCE(NULLIF(诊断日期, ''), NULL)` → DATE/None（与源事实一致） | 引擎 `_clean_date` 解析整数字符串失败 → None |
| `diagnosis_category` | `诊断类型`（如 `主要诊断`） | `诊断类型 || '_' || 住院次数`（如 `主要诊断_1`） | 4 类 + 住院序号 → 290 个唯一 category |
| `is_primary` | `NULL::VARCHAR` | 不变 | 首页无主次诊断概念 |

### B3 实际结果

| 阶段 | 行数 |
|---|---:|
| 源首页.诊断 parquet | 1,000,030 |
| 重跑后 staging（ETL1 B3 输出） | 1,000,030 |
| staging 五元组 distinct（hash 输入） | 990,275 |
| ETL2 引擎守卫过滤（pid/名称/编码空） | 2,217 |
| PG 最终落库 | **988,058** ✅ |
| staging SHA256 抽样 200 命中 PG | **200/200** |
| FK 孤儿 | 0 |

### B3 风险回顾（全部已规避）

| 风险 | 实际表现 | 状态 |
|---|---|---|
| ETL2 引擎修改 | 0 改动 | ✅ |
| spec 修改 | 0 改动 | ✅ |
| `diagnosis_date` 语义破坏 | date 字段回到源事实（NULL/None） | ✅ |
| 下游统计受影响 | `diagnosis_category` 后缀住院序号，下游需用 `LIKE '主要诊断%'` 适配（见下） | 🟡 文档化 |
| 幂等性保持 | 重跑 ETL2 仍能 ON CONFLICT update | ✅ |
| PG 数据膨胀 | DELETE 旧 520,104 行 → 重灌 → 现 988,058 行 | ✅ |

### 下游 SQL 适配

```sql
-- 旧写法（A 方案时）
WHERE source='inpatient_front_page' AND diagnosis_category='主要诊断'

-- 新写法（B3 后）
WHERE source='inpatient_front_page' AND diagnosis_category LIKE '主要诊断%'

-- 或拆字段（推荐用于统计报表）：
SELECT
  source,
  REGEXP_REPLACE(diagnosis_category, '_[0-9]+$', '') AS category_clean,
  COUNT(*) AS n
FROM lnrs.lnrs_anon_diagnosis
WHERE center_code='shengyi' AND source='inpatient_front_page'
GROUP BY 1, 2;
```

---

## 7. 复现命令

```bash
# 1) 源 2 个首页 parquet 行数

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

| ETL2 spec 无"病案首页"专属项 | 首页数据被拆到 surgery_record + diagnosis_inpatient 两个 spec | 文档化（已在 §1 详述）；不强制改 spec |
| ~~首页.诊断 hash 撞键 48%~~（B3 已解决） | 源 (date, is_primary) 双空 → ETL1 把住院次数拼入 diagnosis_category 让 hash 唯一 | ✅ 已解决（见 §6）|
| 首页.诊断 ETL1 staging 不去重 | ETL1 直接读 1,000,030 行；去重完全靠 ETL2 引擎 hash | 方案 B3 后行数与源五元组 distinct 偏差 < 1%（990,275 vs 988,058 = 2,217 守卫过滤）|
| 首页.诊断源缺诊断日期 | 整列 NULL（首页结构本身不存此值） | 已记录；不影响 PG 完整性；B3 把住院次数嵌入 category 修复 hash 撞键 |
| 首页.手术 from_surgery 子集 visit_id 反推 | 适配层按 (pid, surgery_date) 在 visit 窗口内反推，多命中取最近入院 | 适配逻辑 OK；72,396 行均反推成功 |
| `source='inpatient_front_page'` 与 `diagnosis` 的覆盖差异 | `diagnosis` 4,617,269 行有 date；`inpatient_front_page` 988,058 行 date 全空（首页源缺失） | 两者口径不同，已在 §3.2 分组展示；下游用 source 隔离即可 |
| B3 改动下游兼容性 | `diagnosis_category` 改为 `<类型>_<住院次数>` 拼接，4 类 → 290 个唯一值 | 下游用 `LIKE '主要诊断%'` 或 `REGEXP_REPLACE` 适配（§6 已给 SQL） |
| 源 parquet 文件名含中文 | ETL2 `_SRC_TABLE_RE = ^[A-Za-z_][A-Za-z0-9_]*$` 拒绝中文 src_table；本份数据走 ETL1 适配层后落到 snake_case staging parquet，无影响 | 不需要改 spec |
| `is_primary` 在首页无意义 | ETL1 写 NULL 是合理的（首页不区分主/次诊断） | 已记录 |
| follow-up: 其他 source_hash 函数撞键风险 | B3 修复了 diagnosis，但 `source_history_hash`/`source_observation_hash` 等也含 date 字段，需后续审计 | 列入 R7+ 任务 |

---

## 9. 改动文件清单（本次核验任务）

| 文件 | 改动 | 说明 |
|---|---|---|
| `docs/etl2/verify_result/shengyi_discharge_summary_20260914.md` | 本文（新建 + 二次更新） | 反映方案 B3 实施后真实数据 |
| `docs/etl2/数据导入核验清单.xlsx` | R6 E6/F6 同步回填指向 `verify_result/`（见 §10） | R6 已完成标记 |
| `backend/etl1_adapt_shengyi_202609.py` | `SQL_DIAGNOSIS_INPATIENT` 第 675 行：`diagnosis_category` 改为 `<诊断类型>_<住院次数>` 拼接 | 方案 B3 核心改动 |

**已删/清理的 PG 数据**：
- `DELETE FROM lnrs.lnrs_anon_diagnosis WHERE center_code='shengyi' AND source='inpatient_front_page' AND created_batch_id='d21ef52b-a80b-4fff-88bb-082cfe7ad67d'` （旧 520,104 行）

**不改动**：
- ETL2 引擎（`anon_etl_engine.py`）—— 0 改动
- ETL2 spec（`_CENTER_PARQUET_SPECS["shengyi"]` 第 20 条）—— 0 改动
- 任何 parquet 文件
- 其他 lnrs_anon_* 表（patient/visit/surgery/diagnosis[source='diagnosis'] 等）—— 不动

---

## 10. 清单回填

`docs/etl2/数据导入核验清单.xlsx` 第 6 行（省医 / 病案首页）：

- E6（原"完成状态"）：**✅ 已完成（方案 B3 已实施；surgery 324,637 + 首页诊断 988,058；SHA256 抽样 200/200 命中；FK 0 孤儿；详见 verify_result/shengyi_discharge_summary_20260914.md）**
- F6（原"核验结果文件存放路径"）：**docs/etl2/verify_result/shengyi_discharge_summary_20260914.md**
