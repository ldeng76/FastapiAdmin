# Handoff: 医院 parquet 数据导入到 lnrs PG 数据库 经验总结

> 用户明确要求：**只总结"导入 parquet 到 PG"**，不要总结 PG→远程同步的部分（`scripts/migrate_dev_to_h59*` / `scripts/migrate_h59_to_dev*`）。本次总结聚焦 ETL-1 适配 → ETL-2 脱敏落库 → 验证 + 回滚。

## 适用场景

- 接收医院（珠江/省医/新桥 等中心）通过 ETL-1 产出的宽表 parquet
- 通过 ETL-2 引擎批量脱敏写入 `lnrs_anon_patient` / `lnrs_anon_exam` / `lnrs_anon_report_text` / `lnrs_anon_exam_detail` / `lnrs_anon_phi_audit`
- 关键前置：spec 锁定（`_CENTER_PARQUET_SPECS` 写死在 `backend/app/plugin/module_medical/hospital/anon_etl_engine.py:1660-1802`），不重构 ETL-2 引擎

## 推荐新会话加载的 Skill

1. **`hospital-parquet-import`**（仓库内 `.zcode/skills/hospital-parquet-import/SKILL.md`）—— 8 步标准流程的活文档
2. **`lnrs-dev-start`**（仓库内 `.zcode/skills/lnrs-dev-start/SKILL.md`）—— 后端启动 / 连接参数

> **注意**：上述两个 Skill 都**已 commit 到仓库**（见 commit `f3994dce`），新机器 `git clone` 后直接可用——不依赖任何 ZCode 全局 Skill 配置。
> 早期版本里推荐的 `db-reset`（`~/.zcode/skills/db-reset/`）是**全局 Skill**，不在仓库内，**新机器没有**。改用本 handoff 中的"PG 直连 psql 操作"即可完成回退（见下方"如何做库级重置"小节）。

## 如何做库级重置（无需 db-reset Skill）

新机器 agent 无 `db-reset` 时，直接用 psql 操作。**优先用以下顺序**，破坏性递减：

1. **行级回滚**（推荐）：`./scripts/rollback_dev_ct0820.sh "$BACKUP_DIR"` —— 不动 schema，只删 + 灌回 report_text / exam_detail 行
3. **单表 TRUNCATE**（慎用）：
   ```bash
   PGPASSWORD='admin@pwd' PGCLIENTENCODING='SQL_ASCII' \
     /c/Program\ Files/PostgreSQL/18/bin/psql.exe \
     -h 127.0.0.1 -U postgres -d postgres -tAc \
     "TRUNCATE TABLE lnrs.lnrs_anon_report_text CASCADE;"
   ```
   `CASCADE` 会同时清掉依赖 exam_detail 的引用（视 FK 配置）。
3. **整 schema DROP**（兜底）：同 `scripts/migrate_h59_to_dev.sh:96-98`：
   ```bash
   PGPASSWORD='admin@pwd' /c/Program\ Files/PostgreSQL/18/bin/psql.exe \
     -h 127.0.0.1 -U postgres -d postgres -c \
     "DROP SCHEMA IF EXISTS lnrs CASCADE;
      CREATE SCHEMA lnrs AUTHORIZATION postgres;
      GRANT ALL ON SCHEMA lnrs TO lnrs;"
   ```
   之后用 `./scripts/migrate_h59_to_dev.sh` 从 h59 反向恢复（见 `scripts/migrate_h59_to_dev.sh` 的提示用法）。

## 一次性阅读的代码（不要再花时间调研）

| 文件 | 行 | 关键内容 |
|---|---|---|
| `backend/app/plugin/module_medical/hospital/anon_etl_engine.py` | 1660-1802 | `_CENTER_PARQUET_SPECS` 全表（spec 字段定义在 1640-1657 行注释）|
| 同上 | 1848-1854 | `src_table` 拼路径（**改文件名 = 引擎不识别**）|
| 同上 | 401-426 | `_batch_upsert_exams`：ON CONFLICT (center_code, source_exam_hash) 刷 last_seen/exam_date，**不覆盖 exam_type** |
| 同上 | 429-451 | `_batch_upsert_report_text`：ON CONFLICT DO UPDATE body_clean（**真覆盖**）|
| 同上 | 911-1114 | `_import_exam_text_table`：body 拼装 + detail 构造 + seen_exam_anon 跳过（**单 exam 必须 1 行**）|
| 同上 | 243-393 | `_batch_upsert_patients` 三态机：占位 vs 完整记录分支（占位不覆盖人口学）|
| `backend/app/plugin/module_medical/hospital/anon_etl_service.py` | 50-76, 100-172 | batch 创建 / `run_center` / `run_anon_etl` |
| `backend/sql/postgres/0006-anonymized-schema-lnrs.sql` | 178-188 | report_text PK + FK CASCADE |
| 同上 | 332-340 | exam_detail PK = (anon_exam_id, detail_type, detail_ordinal) |
| 同上 | 156-159 | exam → patient FK（CASCADE，删 exam 必炸系列） |
| `backend/app/plugin/module_medical/hospital/anonymize.py` | 全文 | `compute_anon_id` / `compute_anon_exam_id` / `source_exam_hash` / `birth_date_from` / `hash_for_audit` |

## 历史成功先例

- **0823 0814 patient**：`backend/etl1_adapt_zhujiang0814.py` + `0011-zhujiang-dict-seed-0814.sql`（dict seed） + `data_0814/` staging
- **0823 全量 CT 修复**：`spec.body_fields` 改为 `["findings","impression"]` + 幂等重跑（无 ETL1 适配，原 parquet 直接可用）
- **0820 ct0820 切换**：`backend/etl1_adapt_zhujiang_ct0820.py`（复杂正则 + struct 嵌套） + `data_ct0820/` staging + 备份回滚

## 标准流程（4 步，新机器照抄即可）

### Step 1：源文件分析

```bash
./.venv/Scripts/python.exe -c "
import duckdb
con = duckdb.connect(':memory:')
r = con.execute(\"DESCRIBE SELECT * FROM read_parquet('PATH_TO_FILE')\").fetchall()
for row in r: print(row[0], row[1])
print('row_count:', con.execute(\"SELECT count(*) FROM read_parquet('PATH_TO_FILE')\").fetchone()[0])
"
```

产出：列清单 + 行数 + 关键列示例。**不要相信文件头注释**，DuckDB DESCRIBE 是权威。

### Step 2：列名差异判断

打开 `_CENTER_PARQUET_SPECS["<center>"]` 找到对应 src_table 的 `body_fields` / `detail_fields` / `ordinal_field`：

| 情况 | 动作 |
|---|---|
| 全部 spec 字段在 parquet 中存在 + 顶层 | 直接进入 Step 3（无需适配）|
| spec 字段名不同 / 列在嵌套结构里 | 写 ETL1 适配脚本（参 `etl1_adapt_zhujiang0814.py` 风格）|
| spec 字段在 parquet 中**不存在** | 不动 spec，写适配脚本**补齐该列**（哪怕是空值占位）|

**关键**：
- `body_fields` 缺列 → `report_text.body_clean=""` （**正文静默丢失**——SKILL 已记录多次）
- `detail_fields` 缺列 → `detail_json="{}"` （**详情静默丢失**）
- `ordibody_fields` / `detail_fields` 多了 spec 没有的列 → 无害，spec 多余字段不读
- 顶层 vs 嵌套：spec 字段名可直接用点号路径（`_get_nested(rd, f)` 行 114-120 支持 `exam_detail.findings`）

### Step 3：写 ETL1 适配（如果需要）

参照 `backend/etl1_adapt_zhujiang0814.py`（90 行）：

```python
# 骨架
sql = f"""
    COPY (
        SELECT
            -- 保留 spec 期望的所有列：
            <列名映射>,
            -- 必要时补齐 spec 缺列占位：
            CAST(NULL AS VARCHAR) AS <spec_列名>,
        FROM read_parquet('{src.as_posix()}')
    ) TO '{dst.as_posix()}' (FORMAT PARQUET, OVERWRITE_OR_IGNORE)
"""
con.execute(sql)
```

**DuckDB 适配踩坑**（已实测）：

1. **正则必须显式 `'s' flag`**：`regexp_extract(s, 'A\n(.*?)B', 1, 's')` 让 `.` 匹配换行。默认不开
2. **f-string 内正则/JSON 字面量**：`{...}` 与 `\r\n` 会被 Python f-string 误解析。先在 Python 侧用 raw string 拼好再 `f"..."` 嵌入；或 `to_json(struct_pack(...))` 替代 `to_json({...})`
3. **LIST of STRUCT 取首元素**：`list_extract(arr, 1).field`，但 `field` 自身若是 STRUCT，要 `.field.subfield`
4. **VARCHAR 转 DATE**：`CAST(col AS DATE)` 接受 ISO `YYYY-MM-DD`
5. **空数组取首元素返回 NULL**（不是报错），下游字段自然 NULL

### Step 4：staging + 隔离

```bash
mkdir -p data_<批次>/zhujiang/   # 新建独立 staging 目录
cp data_ct0820/zhujiang/nodule_imaging.parquet data_<批次>/zhujiang/  # 复制过去
```

**重要**：
- staging 目录加入 `.gitignore`（一行 `/data_<批次>/`）
- staging 只放本次要导的文件 —— engine 会按 specs 自动连导，多放就多导
- 不要写到仓库默认 `data/<center>/` —— 那里有别的 parquet，staging 失效

### Step 5：dry-run

```bash
cd backend
ENVIRONMENT=dev PYTHONPATH=. ./.venv/Scripts/python.exe \
  -m app.plugin.module_medical.hospital.anon_etl \
  --dry-run --centers <center> --data-root ../data_<批次>
```

预期输出形如：
```
[DRY-RUN]    - patient                [MISSING] kind=patient
[DRY-RUN]    - nodule_imaging         [28139627 bytes] kind=exam_text
[DRY-RUN]    - pathology_specimen     [MISSING] kind=exam_text
...
```

**仅本次目标表 EXISTS + 其他 MISSING = 隔离正确**。否则检查 staging 目录。

### Step 6：（强烈建议）导入前备份

> 任何会覆盖 report_text / exam_detail 的导入前都要做。详见 `scripts/backup_dev_zhujiang_ct.sh`（已 commit，2f5e131c 等）。

**范围**：`report_text` + `exam_detail` + `phi_audit` + `patient` 4 张表，按 `center_code='X' AND exam_type='Y'` 过滤。

**不要备份** `lnrs_anon_exam` —— FK CASCADE 会炸 finding/series/uid_map/report/detail。

### Step 7：正式导入

```bash
cd backend
ENVIRONMENT=dev PYTHONPATH=. ./.venv/Scripts/python.exe \
  -m app.plugin.module_medical.hospital.anon_etl \
  --centers <center> --data-root ../data_<批次>
```

注意 `ENVIRONMENT=dev` 必须显式设（否则 settings 加载 .env 失败，连错驱动）。

耗时：97k exam + 66.6k 占位患者约 1.5 分钟。

### Step 8：10 条验证 SQL（V1-V10）

详见 `.zcode/skills/hospital-parquet-import/SKILL.md` 的"导入后 10 条验证 SQL（V1-V10）"小节。任一不通过即触发 `scripts/rollback_dev_ct0820.sh`。

## 关键陷阱（一次性吸收，不走弯路）

### 编码与字符集

- `body_clean` 字段含 GBK 字节时 psql 报"无效 UTF8 编码"。**所有 psql 查询加 `PGCLIENTENCODING=SQL_ASCII`**：
  ```bash
  PGCLIENTENCODING='SQL_ASCII' PGPASSWORD='admin@pwd' \
    /c/Program\ Files/PostgreSQL/18/bin/psql.exe -h 127.0.0.1 -U postgres -d postgres -tAc "<SQL>"
  ```

### CSV 与备份

- **psql `\copy` 不支持跨行多行字符串**：必须单行调用。多表导出用多次 `psql -c` 而不是 heredoc 文件。
- **psql Windows 客户端输出 CRLF**：写入文本文件后用 `tr -d '\r'` 去 CR，否则 `IN ('uuid1',...)` 解析失败（CRLF 会让 UUID 后跟 `\r`）。
- **`wc -l` 对 CSV 不准**（CSV 字段含换行符）：用 `\copy` 输出末尾的 `COPY NNNN` 行精确读取，或在 export 时不开 HEADER。`backup_dev_zhujiang_ct.sh` 已统一用 `psql -tA | grep -oE 'COPY [0-9]+'`。

### ETL-2 引擎行为

- `engine 会按目录内容自动连导`：specs 里所有 src_table 只要 parquet 存在就会导入，staging 目录只放本次要导的文件。
- 引擎对同 source exam_id 用 `seen_exam_anon` 跳过（行 1054-1056）—— **同一 exam_id 在单 batch 内只能产生一行**。如果源文件 1 个 exam 对应多行（如 nodules 展开），**必须聚合到 1 行**（如把 nodules[] 序列化为 detail_json 字段），否则后导入的 detail 行被跳过。
- exam upsert **不覆盖** `exam_type` / `created_batch_id`（修 IHC 覆盖 Pathology bug 后行为）。
- report_text upsert **真覆盖** `body_clean` + `clean_method`，`review_status` 强制 `pending`。
- patient 占位 upsert **不覆盖**人口学（避免占位值冲掉真实数据）。

### ETL1 适配输出规范

- 输出列名必须与 spec 期望**完全一致**（引擎 `_get_nested(rd, f)` 缺列返回 None）。
- `OVERWRITE_OR_IGNORE` 保证幂等。
- 适配后用 DuckDB 自身查一遍统计（行数、关键字段非空数），不要相信 ETL2 引擎会报错。

### 工作流陷阱

- **工作目录漂移**：连续 Bash 调用 cwd 会保持，`cd backend` 后再 `ls data/` 看到的是 `backend/data`。相对路径执行前先 `cd /e/mw3/wspy/2026/lnrs` 确认。
- **`database schema_hash() 有 lru_cache`**：改 DDL 后需重启进程才生效（一般 ETL1 适配脚本不涉及，但调试 ETL2 引擎时要注意）。
- **schema 命名**：查 `med_hospital`/`med_dict_mapping`/`sys_dict_*` 不加前缀；`lnrs_anon_*`/序列加 `lnrs.` 前缀。写错前缀报 UndefinedTable。
- **占位 patient 是预期行为**：exam 涉及的 patient 表里没有的，自动占位发号（sex='0'），已有患者复用且不覆盖人口学。
- **重跑会产生新 batch**：每次 `run_center` 创建新 `batch_id = uuid4()`，与 source_sha256 是否相同无关。同步脚本（如 `migrate_dev_to_h59_zhujiang0814.sh`）的 `BATCH_IDS` 必须包含全部相关 batch。

## 已 commit 的产物（直接复用）

| 文件 | 作用 |
|---|---|
| `backend/etl1_adapt_zhujiang0814.py` | 0814 patient 宽表适配参考（简单：列名重命名 + struct_pack）|
| `backend/etl1_adapt_zhujiang_ct0820.py` | ct0820 nodule_imaging 适配参考（复杂：正则解析 + struct 嵌套）|
| `backend/sql/postgres/0011-zhujiang-dict-seed-0814.sql` | 0814 dict 种子（29 行 mapping），可改中心复用 |
| `scripts/backup_dev_zhujiang_ct.sh` | 4 表备份（已 commit 03663ef8）|
| `scripts/rollback_dev_ct0820.sh` | 单事务回滚（已 commit 03663ef8）|
| `data_0814/`、`data_ct/`、`data_ct0820/` | staging 目录（gitignore 已配）|

## 已知未做（用户未要求）

- `data/zhujiang/pathology_specimen.parquet`（12,093 行全量病理，B 编号体系）—— 路径同 ct0820：写 ETL1 适配 + 独立 staging + 导入前备份。`spec` 已有配置（`anon_etl_engine.py:1755-1770`）。
- `docs/zhujiang_xinqiao_parq/nodule_imaging.parquet`（212,453 行跨中心多类型，30.9% exam_id 与 ct0820 跨文件 patient_id 不一致）—— 当前 97,039 行 ct0820 已覆盖，剩余 115,414 行独有数据**未导入**。如需：把 nodule_imaging.parquet 拆分为 ct0820 重合部分（已导入）+ 独有部分（写 ETL1 适配 + 单独 staging）。

## 完整流程串联（一行版）

```bash
cd /e/mw3/wspy/2026/lnrs && \
# 1. 适配（如果源文件 schema 与 spec 不匹配）
PYTHONPATH=. ./.venv/Scripts/python.exe etl1_adapt_zhujiang_ct0820.py && \
# 2. dry-run 确认隔离
cd backend && ENVIRONMENT=dev PYTHONPATH=. ./.venv/Scripts/python.exe \
  -m app.plugin.module_medical.hospital.anon_etl \
  --dry-run --centers zhujiang --data-root ../data_ct0820 && \
# 3. 备份（4 张表）
bash scripts/backup_dev_zhujiang_ct.sh && \
# 4. 正式导入
ENVIRONMENT=dev PYTHONPATH=. ./.venv/Scripts/python.exe \
  -m app.plugin.module_medical.hospital.anon_etl \
  --centers zhujiang --data-root ../data_ct0820 && \
# 5. 验证 V1-V10（见 SKILL.md）
# 6. 如失败回滚
bash scripts/rollback_dev_ct0820.sh "$BACKUP_DIR"
```