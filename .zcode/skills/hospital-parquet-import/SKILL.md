---
name: hospital-parquet-import
description: 将医院新批次 parquet 数据（如珠江 zhujiang0814.parquet）按 ETL2 既有流水线脱敏后导入 dev 环境 PostgreSQL 的 lnrs_anon_* 表。使用场景：用户提供新的医院 parquet 文件并要求"按之前的方法处理/导入 dev PG"、重导医院数据、检查导入结果等。
---
<!-- skill 同步副本：.zcode/skills/hospital-parquet-import/ 与 .claude/skills/hospital-parquet-import/ 内容须保持一致（.zcode 被 gitignore，.claude/skills 是 harness 注册位置）；修改任一侧请同步另一侧 -->

# 医院批次 Parquet → ETL2 脱敏 → dev PG 导入

处理医院新批次 parquet 数据的完整流水线。已有成功先例：
- 0723 sample（patient + 影像/病理/基因/IHC）
- 0814 珠江批次（zhujiang0814.parquet 单表 patient，6,714 人，新列名需适配）
- 0719 珠江全量 CT（data/zhujiang/nodule_imaging.parquet，97,039 条 exam，引擎兼容格式直接导入）
- 0825 珠江 extracted_tables 批次（7 表一次导：patient/ct/genetics/ihc/pathology/operation/inpatient；含引擎空正文守卫修复 + zhujiang spec 追加 inpatient(visit_detail) + IHC 日期改用自带列；batch `8aff203f-...`）
- 0825r2 raw_text 补录批次（batch `ce93eaaf-...`：CT/IHC/病理 3 表 detail_json 补 `raw_text` 顶层键，源文件原始报告全文逐字符落库）

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

## Linux 适配（本机实测 2026-08，Ubuntu 22.04 / PostgreSQL 18.4）

正文命令按 Windows（git-bash）编写。核心逻辑（适配脚本 / ETL2 引擎 / 种子 SQL / V1-V10 验证 / 踩坑项）平台无关，命令按此表替换：

| Windows（正文） | Linux（本机） |
|---|---|
| `./.venv/Scripts/python.exe`（Step 1/4/5/6） | `./.venv/bin/python`（或 `uv run python`） |
| `"/c/Program Files/PostgreSQL/18/bin/psql" <args>`（前置条件 3 / Step 3 种子 SQL） | `psql <args>`（/usr/bin/psql，18.4，与正文 PG18 假设一致） |
| V1-V10 编码坑块的 `psql.exe -h 127.0.0.1 -U postgres -d postgres -tAc` | `psql -h 127.0.0.1 -U postgres -d postgres -tAc`（`PGCLIENTENCODING='SQL_ASCII'`、`PGPASSWORD='admin@pwd'` 照旧） |
| `$TEMP/lnrs_backup_...`、`cygpath -m "$TEMP"`（Step 5.5 / 8） | `/tmp/lnrs_backup_...`（无 cygpath 步骤） |
| "工作目录漂移"坑的 `cd /e/mw3/wspy/2026/lnrs` | `cd /home/dzy/wk/lnrs` |

- 前置条件 3 的 psql 检查改为 `psql --version`（本机 18.4；127.0.0.1:5432 `lnrs/lnrs_pwd`→postgres 已验证可连）。
- **`scripts/` 脚本（Step 5.5/8/9 涉及）目前是 Windows（git-bash）版**：`backup_dev_zhujiang_ct.sh`、`rollback_dev_ct0820.sh`、`migrate_dev_to_h59_zhujiang0814.sh` 等均含 `PG_BIN="/c/Program Files/PostgreSQL/18/bin"`（多数可用环境变量 `PG_BIN` 覆盖，`migrate_dev_to_h42.sh` / `migrate_dev_to_h59.sh` 硬编码）、`cygpath -m`、`psql.exe`。Linux 执行前必须改：`PG_BIN` → 本机 pg bin 目录、去掉 `cygpath -m`（直接用 `/tmp` 路径）、`psql.exe` → `psql`，**不要原样执行**。
- ETL2 CLI（Step 4/6）的 `PYTHONPATH="" ENVIRONMENT=dev` 前缀与日志重定向方式在 Linux 上原样可用。

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

## Step 8 —（可选）同步到 h59（192.168.1.59 PG15）

导入 dev 后若需推送 1.59：**不要用全量脚本**（`migrate_dev_to_h59.sh` 会 DROP 整个 schema），用定向增量脚本 `scripts/migrate_dev_to_h59_zhujiang0814.sh`：

- 只搬本次批次足迹（`B1`/`B2` batch id 环境变量可覆盖）：ingest_batch / patient(center) / exam / report_text / exam_detail / phi_audit / med_dict_mapping 七张表
- 全程 ON CONFLICT upsert（phi_audit 先删后插保 audit_id 对齐），不删 h59 任何既有行，幂等可重跑
- 末尾自动 setval 校准 `lnrs_anon_patient_seq` 与 phi_audit 序列（防撞号）
- 验证：两端同过滤条件 count 对比 + 内容 md5 抽查（含 patient_meta.raw_text、detail_json）
- 坑：UNION ALL 验证 SQL 要 `ORDER BY 1`（两端行序不同会误报）；序列只验证 `>= max(PT号)`（dev 端探测性 nextval 有空洞，等值会误报）；`$TEMP` 需 `cygpath -m` 转正斜杠供 psql \copy 使用

## Step 5.5 —（强烈建议）导入前备份 4 张表

> 任何"会覆盖 report_text / exam_detail"的导入前，**先备份**。否则回滚需用 `scripts/migrate_h59_to_dev.sh` 全 schema 重建（破坏其他中心/字典/批次），代价大。

```bash
./scripts/backup_dev_zhujiang_ct.sh zhujiang CT
# 输出末尾打印 BACKUP_DIR 绝对路径（Windows TEMP/lnrs_backup_zhujiang_CT_<TS>/）
# 包含 4 个 CSV: report_text.csv / exam_detail.csv / phi_audit.csv / patient.csv
# + checksums.md5 + phi_audit_backup_batches.txt
```

- **4 张表范围**（`scripts/backup_dev_zhujiang_ct.sh`）：
  - `report_text` + `exam_detail` 按 `exam JOIN (center_code=X, exam_type=Y)` 过滤（不用 batch_id 以避免漏掉 0719 重跑行）
  - `phi_audit` 按 `batch_id IN (center_code=X 全部 batch UUID)` 过滤
  - `patient` 按 `center_code=X` 全量
- 验证：CSV 行数 = 库内 `count(*)`（脚本自动核对） + md5sum
- **不要备份** `lnrs_anon_exam`：导入对 exam 表只 `last_seen/exam_date` 刷新，不重建；FK CASCADE 一旦删 exam 会炸掉 finding/series/uid_map/report/detail

## Step 9 —（条件触发）回滚

导入后立刻跑 V1-V10 验证 SQL（见下面"导入后 10 条验证 SQL"）。任一不通过即触发：

```bash
./scripts/rollback_dev_ct0820.sh "$BACKUP_DIR"
# 单事务 DELETE report_text+exam_detail → \copy 灌回 → count+md5 验证
```

回滚脚本**只回滚 2 张表**（report_text + exam_detail）。`phi_audit` 增量与 `patient` 占位的清理**手动决策**（列在脚本末尾 SQL 模板），避免误删其他批次。

## 导入后 10 条验证 SQL（V1-V10）

```sql
-- V1: body_clean 非空率（应 100%）
SELECT count(*) FILTER (WHERE body_clean IS NOT NULL AND body_clean != '') AS non_empty,
       count(*) AS total
FROM lnrs.lnrs_anon_report_text rt
WHERE rt.anon_exam_id IN (SELECT anon_exam_id FROM lnrs.lnrs_anon_exam
                          WHERE center_code='zhujiang' AND exam_type='CT');
-- V2: detail_json != '{}' 非空率（应 100%）
SELECT count(*) FILTER (WHERE detail_json != '{}'::jsonb) AS non_empty,
       count(*) AS total
FROM lnrs.lnrs_anon_exam_detail ed
WHERE ed.anon_exam_id IN (SELECT anon_exam_id FROM lnrs.lnrs_anon_exam
                          WHERE center_code='zhujiang' AND exam_type='CT');
-- V3: phi_audit 本次 batch 行数（应 ≈ 29 万 ±5%）
SELECT count(*) FROM lnrs.lnrs_anon_phi_audit WHERE batch_id='<本次>';
-- V4: exam 行数（应不变）
SELECT count(*) FROM lnrs.lnrs_anon_exam
WHERE center_code='zhujiang' AND exam_type='CT';
-- V5: 新占位 patient（应 ≈ 12k ~ 16k ±10%）
SELECT count(*) FROM lnrs.lnrs_anon_patient
WHERE center_code='zhujiang' AND sex='0' AND created_batch_id='<本次>';
-- V6: clean_method 分布（应全 'regex_only'）
SELECT clean_method, count(*) FROM lnrs.lnrs_anon_report_text rt
WHERE rt.anon_exam_id IN (SELECT anon_exam_id FROM lnrs.lnrs_anon_exam
                          WHERE center_code='zhujiang' AND exam_type='CT')
GROUP BY clean_method;
-- V7: review_status 分布（应全 'pending'）
SELECT review_status, count(*) FROM lnrs.lnrs_anon_report_text rt
WHERE rt.anon_exam_id IN (SELECT anon_exam_id FROM lnrs.lnrs_anon_exam
                          WHERE center_code='zhujiang' AND exam_type='CT')
GROUP BY review_status;
-- V8: batch 状态
SELECT status, row_counts::text FROM lnrs.lnrs_anon_ingest_batch
WHERE center_code='zhujiang' AND source_locator LIKE '%ct0820%'
ORDER BY started_at DESC LIMIT 1;
-- V9: 抽样 5 条 body_clean md5（备查）
SELECT md5(body_clean) FROM lnrs.lnrs_anon_report_text rt
WHERE rt.anon_exam_id IN (SELECT anon_exam_id FROM lnrs.lnrs_anon_exam
                          WHERE center_code='zhujiang' AND exam_type='CT')
ORDER BY rt.anon_exam_id LIMIT 5;
-- V10: FK 孤儿检查（应 0）
SELECT 'orphan_rt', count(*) FROM lnrs.lnrs_anon_report_text rt
  LEFT JOIN lnrs.lnrs_anon_exam e ON e.anon_exam_id = rt.anon_exam_id
  WHERE e.anon_exam_id IS NULL
UNION ALL
SELECT 'orphan_ed', count(*) FROM lnrs.lnrs_anon_exam_detail ed
  LEFT JOIN lnrs.lnrs_anon_exam e ON e.anon_exam_id = ed.anon_exam_id
  WHERE e.anon_exam_id IS NULL;
```

> **编码坑**：body_clean 含 GBK 字节时，psql 报"无效的 UTF8 编码字节顺序"。**所有 V1-V10 SQL 必须加 `PGCLIENTENCODING=SQL_ASCII` 环境变量**（`SQL_ASCII` 在 PG18 上强制按字节流通过，不做合法性校验）：

```bash
PGCLIENTENCODING='SQL_ASCII' PGPASSWORD='admin@pwd' \
  /c/Program\ Files/PostgreSQL/18/bin/psql.exe -h 127.0.0.1 -U postgres -d postgres -tAc "<SQL>"
```

## 注意事项（踩过的坑）

- **raw_text/自由文本含 PHI**（姓名、住址）：入 `patient_meta` 时无 `review_status` 标记，后续清洗/人工抽检计划需覆盖此位置。
- **LNRS_ANON_SECRET 是开发占位密钥**（`change-me-in-production-please`）：dev 可用，生产必须换；换密钥后所有 anon_id 变化 = 全部数据需重导。
- **schema 命名**：查 `med_hospital`/`med_dict_mapping`/`sys_dict_*` 不加前缀；`lnrs_anon_*`/序列加 `lnrs.` 前缀。写错前缀报 UndefinedTable。
- **工作目录漂移**：连续 Bash 调用 cwd 会保持，`cd backend` 后再 `ls data/` 看到的是 backend/data（错误位置）。相对路径执行前先 `cd /e/mw3/wspy/2026/lnrs` 确认。
- **database schema_hash() 有 lru_cache**：改 DDL 后需重启进程才生效。
- **engine 会按目录内容自动连导**：specs 里所有 src_table 只要 parquet 存在就会导入——staging 目录只放本次要导的文件。
- **pathology_specimen 的患者 ID 可能是独立体系**（如珠江 'B1600039'，与 patient 表 '001321' 无交集）：这类患者会被占位发号（sex='0'），属预期行为。
- **同一中心的 sample 与全量文件 schema 可能不同**（0719 全量 CT 实证：sample 有 nodule_* 结构列，全量只有 `findings`/`impression` 文本列）：引擎 `_CENTER_PARQUET_SPECS` 按 sample 写死 `body_fields: []` + detail_fields，导致全量导入后 report_text.body_clean 为空、detail_json 全 `{}`，**报告正文被静默丢弃**。导入 exam 类文件前先 `DESCRIBE` 核对列，与 spec 不符时需调整 spec 或适配文件。
- **同 schema ≠ 同内容**（0825 实证：ct.parquet 与 ct0820 列完全一致，但 97,039 条正文 98.99% md5 不同——旧库正文带 U+3000 全角空格前缀 + 42k 条真实文本更新）：重导前把"适配后 body"与库内 `md5(body_clean)` 全量比对（归一化去空白后再比一次），区分"实质刷新 / 仅表面格式 / 纯 no-op"，决定是否值得走备份+重导。
- **report_text PK=anon_exam_id 跨 exam_type 唯一**（0723 sample 实证：IHC 与病理共享 specimen id，IHC 空 body upsert 把 14 条病理正文覆写为 ""；exam_type 覆盖 bug 2026-07-24 修过但 report_text 漏了）。2026-08-25 引擎已修：`_import_exam_text_table` 正文空则不写 report 行（`if body:`）。共享 id 的 IHC 现在只挂 detail（detail PK 含 detail_type，共存无冲突）。
- **exam 级文件可能一行多标本/多行同 exam**（0825 pathology 实证：15,542 行 / 15,382 唯一 exam，152 个 exam 跨行且各行 specimens[] 是独立标本，另有 75 行空数组 + 49 行 NULL + 数组内部自重复）：适配必须 `unnest` 后按 exam 合并 + struct 去重再落库，标量字段（histology_class/specimen_type/sampling_site）取"首个非空"；完整数组加进 spec detail_fields（如 `"specimens"`）原样落 JSONB。合并前后总数要打印核对。
- **含聚合的 DuckDB 适配默认非确定**（2026-08-26 实证：pathology 适配器 `FIRST()`/`list(ORDER BY 常量)`/`ROW_NUMBER() OVER ()` 依赖扫描序，同一源文件跑 3 次得 3 个不同 staging；staging 被重跑覆盖后重导，静默改写 313 行 body_clean + 1,019 行 detail_json，已从导入前备份恢复）：① 行号必须确定性——`ROW_NUMBER() OVER (ORDER BY md5(to_json(struct_pack(整行所有列))))`；② "首个非空"用 `arg_min(col, src_rn) FILTER (WHERE col IS NOT NULL)`；③ 数组排序键要含行内位置（同行标本共享 src_rn 会并列）——`unnest(range(1, len(arr)+1)) u(i)` + `arr[i]`（DuckDB `range()` 不含尾端、list 下标 1 起），排序键 `MIN(src_rn * 1000000 + spec_pos)`；④ 验证用**内容哈希**连跑 3 次（parquet 文件 md5 不可靠——字节层非确定，内容相同 md5 也可能不同）；⑤ 重导前对比 staging 与库内现状，量化将发生的值漂移。
- **DuckDB 两个语法坑**（0825 适配实测）：① CTE 必须写在 `COPY (WITH ... SELECT ...)` 括号内部，`WITH ... COPY (...)` 报 Parser Error；② `FROM t, unnest(t.col) alias` 的 alias 是**表别名**，`SELECT alias` 得到包装 struct `STRUCT(unnest <实际struct>)` 导致字段查找失败——改用 SELECT 列表内 `unnest(t.col) AS x`。
- **psql 输出经 Python `subprocess` 捕获会丢 `\r`**（2026-08-26 实证：`text=True` 默认通用换行转换把 `\r\n`→`\n`，误判库内 detail_json 丢了 CR，实际数据完好）：捕获 psql 输出必须 `capture_output=True` 字节模式 + `stdout.decode('utf-8')`，再做逐字符比对。
- **DuckDB REGEXP 默认不开 s 标志**：跨多行匹配必须显式 `'s'` flag（如 `regexp_extract(s, 'A\n(.*?)\nB', 1, 's')`），否则 `.` 不匹配换行返回 NULL。
- **DuckDB f-string 内正则/JSON 字面量**：花括号 `{...}` 与 `\r\n` 会被 Python f-string 误解析。复杂正则/字典字面量先在 Python 侧用 raw string 拼好再 `f"..."` 嵌入；或用 `to_json(struct_pack(...))` 替代 `to_json({...})`。
- **ct0820 nodules[] 嵌套 struct**：`nodules` 是 LIST of STRUCT，其中 `nodule_location` 自身是 STRUCT(lobe, segment)。取首结节 lob 需要 `list_extract(nodules, 1).nodule_location.lobe`，不能直接 `.lobe`。
- **psql \copy CSV 行数 ≠ wc -l**：CSV 里 `body_clean` 字段含 `\r\n` 时 `wc -l` 算错行数。用 `\copy` 输出末尾的 `COPY NNNN` 行精确读取，或在 export 时不开 HEADER。备份脚本已统一改用 `psql -tA` + `grep -oE 'COPY [0-9]+'`。
- **psql 输出 CRLF**（Windows 本机 psql）：写入文本文件后用 `tr -d '\r'` 去掉 CR，否则 `IN ('uuid1','uuid2',...)` 解析失败。
- **psql `\copy` 不支持跨行多行字符串**：必须单行调用（参考 0814 同步脚本风格）。多表导出用多次 `psql -c` 而不是 heredoc 文件。
- **ENGINE 配置错读 MySQL**：ETL2 CLI 必须设 `ENVIRONMENT=dev`（否则读不到 .env.dev，连接错驱动）。Command：`ENVIRONMENT=dev PYTHONPATH=. ./.venv/Scripts/python.exe -m app.plugin.module_medical.hospital.anon_etl --centers X --data-root ../data_X`。
- **批次足迹（截至 2026-08-26）**：
  - 0825 批次已导入（batch `8aff203f-424c-40d4-a6d3-c0b887b72913`）：patient 6,714 刷新（=0814 同批人）/ CT 97,039 刷新（文本更新版）/ pathology 15,386 / genetic 1,088 / IHC exam 25（6,698 个共享 id 并入 Pathology exam 行，detail 6,723 条）/ inpatient visit 9,590 / surgery 18,058 / 新占位 patient 12,980。h59 未同步（待确认）。
  - **raw_text 补录（2026-08-26，batch `ce93eaaf-2657-453d-b0d3-39ca4ee16b58`）**：引擎 spec 的 detail_fields 补 `raw_text`（CT/IHC/病理），CT/IHC 适配脚本同步保留该列；staging 独立目录 `data_zj0825raw/` 只放 3 个变更表，引擎按目录内容自动只导这 3 表。各文件 raw_text 最终落点：patient → `patient_meta->raw_text`；genetics → `exam_detail.detail_json->test_meta->raw_text`；inpatient → `visit_detail_json->raw_text`；CT/IHC/病理 → `exam_detail.detail_json->raw_text`（顶层键）；operation 源文件无 raw_text 列（无内容可导）。导入时因 staging 变体漂移误改了 313 body + 1,019 detail，已从备份恢复——**本批对既有数据的唯一足迹是新增 raw_text 键**（+ 簿记字段刷新）。pathology/IHC 适配器已改确定性（3 次内容哈希一致）；下次重导将一次性规范化 ~553 病理 body / 81+12 raw_text / 1,573+ 数组顺序（均为同 exam 合法值，此后不再漂移）。
  - 0723 sample 的 39 条病理中 26 条空正文，其中 14 条系 IHC 空 body 覆盖所致（引擎修复后不再发生；覆盖的正文源文件已删除，无法恢复）。
  - ct0820（2026-08-20）已作为珠江全量 CT 源；0825 的 ct.parquet 是其重抽取版，重导后库内 CT 正文以 0825 为准。

## 产物清单（历史批次先例，可仿照）

| 产物 | 路径 |
|---|---|
| 适配脚本（0814 patient） | `backend/etl1_adapt_zhujiang0814.py` |
| 适配脚本（0825 genetics） | `backend/etl2/etl1_adapt_zhujiang0825_genetics.py` |
| 适配脚本（0825 pathology，exam 级合并 specimens[]） | `backend/etl2/etl1_adapt_zhujiang0825_pathology.py` |
| 适配脚本（0825 surgery/operation） | `backend/etl2/etl1_adapt_zhujiang0825_surgery.py` |
| 适配脚本（0825 ihc，重复 exam 按非空数取舍） | `backend/etl2/etl1_adapt_zhujiang0825_ihc.py` |
| 适配脚本（ct0820 nodule_imaging） | `backend/etl1_adapt_zhujiang_ct0820.py` |
| 映射种子 SQL（0814） | `backend/sql/postgres/0011-zhujiang-dict-seed-0814.sql` |
| 备份脚本 | `scripts/backup_dev_zhujiang_ct.sh` |
| 备份脚本（Linux 版，0825 批次范围=中心全部 exam_type） | `scripts/backup_dev_zhujiang_0825.sh` |
| 回滚脚本 | `scripts/rollback_dev_ct0820.sh` |
| 同步 h59 脚本（0814+CT） | `scripts/migrate_dev_to_h59_zhujiang0814.sh` |
| 同步 h59 脚本（0814+CT+ct0820） | `scripts/migrate_dev_to_h59_zhujiang_ct0820.sh` |
| staging 0814 patient（gitignore） | `data_0814/zhujiang/patient.parquet` |
| staging 0719 全量 CT（gitignore） | `data_ct/zhujiang/nodule_imaging.parquet` |
| staging ct0820 全量 CT（gitignore） | `data_ct0820/zhujiang/nodule_imaging.parquet` |
| staging 0825 全 7 表（gitignore） | `data_zj0825/zhujiang/{patient,nodule_imaging,genetic_test,ihc_result,pathology_specimen,inpatient,surgery_record}.parquet` |
| staging 0825r2 raw_text 补录 3 表（gitignore） | `data_zj0825raw/zhujiang/{nodule_imaging,ihc_result,pathology_specimen}.parquet` |
| 导入日志 | `/tmp/zhujiang0814_run.log`、`/tmp/zhujiang_ct_run.log`、`/tmp/zhujiang_0825_run.log` |
| 导入前备份（dev） | `$TEMP/lnrs_backup_zhujiang_CT_<TS>/{report_text,exam_detail,phi_audit,patient}.csv` |
