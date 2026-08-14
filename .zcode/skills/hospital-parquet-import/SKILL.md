---
name: hospital-parquet-import
description: 将医院新批次 parquet 数据（如珠江 zhujiang0814.parquet）按 ETL2 既有流水线脱敏后导入 dev 环境 PostgreSQL 的 lnrs_anon_* 表。使用场景：用户提供新的医院 parquet 文件并要求"按之前的方法处理/导入 dev PG"、重导医院数据、检查导入结果等。
---

# 医院批次 Parquet → ETL2 脱敏 → dev PG 导入

处理医院新批次 parquet 数据的完整流水线。已有成功先例：
- 0723 sample（patient + 影像/病理/基因/IHC）
- 0814 珠江批次（zhujiang0814.parquet 单表 patient，6,714 人，新列名需适配）
- 0719 珠江全量 CT（data/zhujiang/nodule_imaging.parquet，97,039 条 exam，引擎兼容格式直接导入）

## 流水线全景

```
医院新 parquet（单表/新列名）
  → ① 适配脚本（列名/结构 → 引擎期望 schema）      backend/etl1_adapt_*.py
  → ② 独立 staging 目录                            data_<批次>/<center>/patient.parquet
  → ③ 补字典映射种子 SQL（枚举值域缺口）            backend/sql/postgres/00NN-*-dict-seed.sql
  → ④ ETL2 引擎（HMAC 脱敏 + 幂等 upsert）         anon_etl CLI
  → ⑤ 验证（计数/batch/抽样/audit）
```

核心代码位置（`backend/app/plugin/module_medical/hospital/`）：
- `anon_etl_engine.py` — `_CENTER_PARQUET_SPECS` 定义每个中心读取哪些 parquet 及列映射规则；`_import_patient_table` 是 patient 表入口
- `anonymize.py` — `compute_anon_id(center, patient_id)` = HMAC 脱敏；`birth_date_from` 日期解析
- `anon_etl/__main__.py` — CLI；`anon_etl_service.py` — 每中心单事务 + ingest_batch 记录

## 前置条件（每次先确认）

```bash
cd backend
# 1. .env.dev 存在且指向目标 PG（当前 dev = 本机 127.0.0.1:5432, user=lnrs, db=postgres, schema=lnrs）
grep -E "DATABASE_HOST|DATABASE_NAME|LNRS_ANON_SECRET" env/.env.dev
# 2. 中心已在 med_hospital 注册（未注册则引擎直接报错）
#    zhujiang id=1 / shengyi id=3 已注册，新中心需先跑对应种子 SQL
# 3. psql 可用（执行种子 SQL）：
"/c/Program Files/PostgreSQL/18/bin/psql" --version
```

注意：med_* / sys_* 表无 schema 前缀（连接 search_path 已含 lnrs），lnrs_anon_* 表用 `lnrs.` 前缀。

## Step 1 — 分析新文件 schema 与值域

```bash
cd backend && ./.venv/Scripts/python.exe -c "
import duckdb
con = duckdb.connect()
for row in con.execute(\"DESCRIBE SELECT * FROM read_parquet('<新文件绝对路径>')\").fetchall():
    print(row[0], '|', row[1])
# 枚举值域（patient 表关注 sex/ethnicity/smoking/血型 类字段）：
# SELECT <col>, COUNT(*) FROM read_parquet(...) GROUP BY 1 ORDER BY 2 DESC
"
```

对照引擎期望的 patient.parquet 列（`_import_patient_table` 读取）：
`patient_id, source_center, gender, birth_date, ethnicity, native_place, abo_blood_type, rh_blood_type, smoking_status, first_nodule_date, demographics{'bmi'}, medical_history{...}`

## Step 2 — 写适配脚本（列名不一致时）

参考 `backend/etl1_adapt_zhujiang0814.py`（DuckDB COPY + struct_pack，幂等可重跑）。0814 批次的映射先例：

| 新文件列 | 引擎期望 | 备注 |
|---|---|---|
| `sex` | `gender` | 直接别名 |
| `personal_smoking_status` | `smoking_status` | |
| `blood_type_abo` / `blood_type_rh` | `abo_blood_type` / `rh_blood_type` | |
| 标量 `bmi` | `struct_pack(bmi := bmi)` → `demographics` | |
| 病史散列（家族史/既往肿瘤/合并症/包年/发现途径/`raw_text`） | 组装进 `medical_history` struct | 引擎整体序列化进 `patient_meta` JSONB |

关键：**不改引擎代码**，适配在数据侧完成（ETL1 职责）。`raw_text` 等自由文本随 `medical_history` 入 `patient_meta`（含 PHI，见"注意事项"）。

## Step 3 — 枚举映射缺口检查与补种子

```python
# 新文件值域（Step 1） vs 库内映射，缺口 = 值域 - 已映射 raw_label：
SELECT dt.dict_type, dm.raw_label, sd.dict_value
FROM med_dict_mapping dm
JOIN sys_dict_type dt ON dt.id = dm.dict_type_id
JOIN sys_dict_data sd ON sd.id = dm.dict_data_id
WHERE dm.hospital_id = <id>;   -- zhujiang=1
# 标准字典可用值（映射目标必须存在于 sys_dict_data）：
SELECT dt.dict_type, sd.dict_value, sd.dict_label
FROM sys_dict_data sd JOIN sys_dict_type dt ON dt.id = sd.dict_type_id
WHERE dt.dict_type LIKE 'med_%';
```

缺口 → 写幂等种子 SQL（参考 `backend/sql/postgres/0011-zhujiang-dict-seed-0814.sql`，模式：`WITH hosp AS (...) INSERT ... ON CONFLICT (hospital_id, dict_type_id, raw_label) DO NOTHING`），然后：

```bash
"/c/Program Files/PostgreSQL/18/bin/psql" "postgresql://lnrs:lnrs_pwd@127.0.0.1:5432/postgres" \
  -v ON_ERROR_STOP=1 -f "<种子SQL路径>"
```

不补映射不会失败（未命中落 NULL + `med_dict_unmatched` 待处理表），但枚举信息丢失。

## Step 4 — 独立 staging + dry-run

**务必用独立 staging 目录**（如 `data_0814/`、`data_ct/`），不要直接用 `data/<center>/`——后者可能残留旧批次的其他 parquet（nodule_imaging 等），引擎会按 specs 连带导入。两种方式：

```bash
cd backend
# 方式 A：新文件需列名适配（经适配脚本生成）
./.venv/Scripts/python.exe etl1_adapt_<批次>.py --out-dir ../data_<批次>/<center>
# 方式 B：文件本就是引擎兼容格式（specs 已覆盖的表，如 data/zhujiang/ 下的全量
#         nodule_imaging.parquet），复制单文件到独立 staging 即可，无需适配
mkdir -p ../data_ct/zhujiang && cp ../data/zhujiang/nodule_imaging.parquet ../data_ct/zhujiang/
# dry-run：确认"将处理 N 个源表"只含本次目标表
PYTHONPATH="" ENVIRONMENT=dev ./.venv/Scripts/python.exe -m app.plugin.module_medical.hospital.anon_etl \
  --dry-run --centers <center> --data-root ../data_<批次>
```

staging 目录加入 `.gitignore`（已有 `/data/` 规则，需为 `data_<批次>/` 追加）。

## Step 5 — 重复/覆盖检测（回答"数据有重复先删旧的" / "这文件是否已导入"）

**patient 表**：按 anon_id（HMAC，需 LNRS_ANON_SECRET）比对：

```bash
cd backend && PYTHONPATH=. ENVIRONMENT=dev ./.venv/Scripts/python.exe -c "
import asyncio, duckdb
from sqlalchemy import text
from app.core.database import async_engine
from app.plugin.module_medical.hospital.anonymize import compute_anon_id
con = duckdb.connect()
pids = [r[0] for r in con.execute(\"SELECT patient_id FROM read_parquet('<staging>/patient.parquet')\").fetchall()]
anon_ids = [compute_anon_id('<center>', str(p)) for p in pids]
async def main():
    async with async_engine.connect() as conn:
        existing = set()
        for i in range(0, len(anon_ids), 4000):
            r = await conn.execute(text(\"SELECT anon_id FROM lnrs.lnrs_anon_patient WHERE center_code='<center>' AND anon_id = ANY(:ids)\"), {'ids': anon_ids[i:i+4000]})
            existing.update(x[0] for x in r.fetchall())
        print(f'重复 {len(existing)} / 新增 {len(set(anon_ids))-len(existing)}')
    await async_engine.dispose()
asyncio.run(main())
"
```

**exam 类表**（nodule_imaging / pathology_specimen 等）：按 `source_exam_hash`（裸 SHA256，无需密钥）比对文件的 id_field 与库内：

```python
# sha256(f"{center}:{exam_id}")，分块查 lnrs_anon_exam.source_exam_hash = ANY(...)
# 先例：0719 全量 CT 97,039 条 vs 库内仅命中 21 条（0723 sample 子集）→ 99.98% 未入库
```

结论解读：引擎按幂等键（patient: `center_code+anon_id`；exam: `center_code+source_exam_hash`）upsert，**重复 = 原位刷新（等效于删旧插新），无需也不应物理 DELETE**——patient 行被 exam 表 FK 引用，硬删会断引用且重发 PT_ 号。0 重复则纯新增。

## Step 6 — 正式导入

```bash
cd backend
PYTHONPATH="" ENVIRONMENT=dev ./.venv/Scripts/python.exe -m app.plugin.module_medical.hospital.anon_etl \
  --centers <center> --data-root ../data_<批次> > /tmp/<center>_<批次>_run.log 2>&1
echo "EXIT=$?"; grep -v WARNING /tmp/<center>_<批次>_run.log | tail -25
```

成功标志：`EXIT=0`、汇总区 `success`、日志出现"病人 upsert ... 新增 N"与"未匹配标签 X 条"（X 应为 0）。

要点：`PYTHONPATH=""` 必设（防 PATH 污染）；日志重定向到文件再看（不要 grep 管道，会与进度输出冲突）；单中心约 30 秒/7 千行量级。

## Step 7 — 验证

```python
# 建议写成临时 py 文件执行（bash 内联 $ /引号转义易错），核心查询：
SELECT center_code, COUNT(*) FROM lnrs.lnrs_anon_patient GROUP BY 1;               -- 分布
SELECT status, row_counts, source_locator FROM lnrs.lnrs_anon_ingest_batch
  ORDER BY started_at DESC LIMIT 1;                                                  -- 本次 batch
SELECT COUNT(*) FROM lnrs.lnrs_anon_phi_audit;                                       -- 审计增量 ≈ 行数×2(patient_id+birth_date)
-- 抽样：sex/ethnicity/血型应是归一化码（'1'/'01'/'6'...），patient_meta ? 'raw_text' 应为 true
SELECT patient_id, sex, ethnicity, abo_blood_type, bmi, first_nodule_date,
       patient_meta ? 'raw_text' FROM lnrs.lnrs_anon_patient
WHERE created_batch_id = '<本次batch_id>' ORDER BY patient_id LIMIT 5;
```

核对项：库内增量 = 导入行数；枚举码非原始中文标签；`first_nodule_date`/`bmi`/`patient_meta` 覆盖数与源文件一致。

**exam 类表导入的额外核对项**（0719 全量 CT 先例）：

```sql
-- 1. exam 分布：目标表行数应等于文件去重 exam_id 数（97,039 = 97,039 ✓）
SELECT center_code, exam_type, COUNT(*) FROM lnrs.lnrs_anon_exam GROUP BY 1,2;
-- 2. exam_detail：spec 配了 detail_fields/ordinal_field 时每行一条 JSONB
SELECT detail_type, COUNT(*) FROM lnrs.lnrs_anon_exam_detail
WHERE created_batch_id = '<batch_id>' GROUP BY 1;
-- 3. 占位患者语义：exam 涉及但 patient 表没有的患者自动占位发号（sex='0'），
--    已有患者（如 0814 批次真实档案）则复用且不覆盖人口学——抽样验证跨批次 FK 关联：
SELECT e.patient_id, p.sex FROM lnrs.lnrs_anon_exam e
JOIN lnrs.lnrs_anon_patient p ON p.patient_id = e.patient_id
WHERE e.created_batch_id = '<batch_id>' AND p.sex <> '0' LIMIT 3;
-- 4. phi_audit：每 exam 1 条 id HMAC（body_fields 为空时无正文审计）
```

耗时参考：97k exam + 66.6k 占位患者约 1.5 分钟。

## 注意事项（踩过的坑）

- **raw_text/自由文本含 PHI**（姓名、住址）：入 `patient_meta` 时无 `review_status` 标记，后续清洗/人工抽检计划需覆盖此位置。
- **LNRS_ANON_SECRET 是开发占位密钥**（`change-me-in-production-please`）：dev 可用，生产必须换；换密钥后所有 anon_id 变化 = 全部数据需重导。
- **schema 命名**：查 `med_hospital`/`med_dict_mapping`/`sys_dict_*` 不加前缀；`lnrs_anon_*`/序列加 `lnrs.` 前缀。写错前缀报 UndefinedTable。
- **工作目录漂移**：连续 Bash 调用 cwd 会保持，`cd backend` 后再 `ls data/` 看到的是 backend/data（错误位置）。相对路径执行前先 `cd /e/mw3/wspy/2026/lnrs` 确认。
- **database schema_hash() 有 lru_cache**：改 DDL 后需重启进程才生效。
- **engine 会按目录内容自动连导**：specs 里所有 src_table 只要 parquet 存在就会导入——staging 目录只放本次要导的文件。
- **pathology_specimen 的患者 ID 可能是独立体系**（如珠江 'B1600039'，与 patient 表 '001321' 无交集）：这类患者会被占位发号（sex='0'），属预期行为。
- **未完事项（截至 2026-08-14）**：`data/zhujiang/pathology_specimen.parquet`（12,093 行全量病理，B 编号体系、0 患者交集）仍未导入，库内 Pathology 仅 39 条 sample；导入方式同全量 CT（复制单文件到独立 staging）。

## 产物清单（历史批次先例，可仿照）

| 产物 | 路径 |
|---|---|
| 适配脚本（0814 patient） | `backend/etl1_adapt_zhujiang0814.py` |
| 映射种子 SQL（0814） | `backend/sql/postgres/0011-zhujiang-dict-seed-0814.sql` |
| staging 0814 patient（gitignore） | `data_0814/zhujiang/patient.parquet` |
| staging 0719 全量 CT（gitignore） | `data_ct/zhujiang/nodule_imaging.parquet` |
| 导入日志 | `/tmp/zhujiang0814_run.log`、`/tmp/zhujiang_ct_run.log` |
