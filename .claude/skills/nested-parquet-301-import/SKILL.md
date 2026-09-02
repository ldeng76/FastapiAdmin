---
name: nested-parquet-301-import
description: 解放军总医院（hos301）2026-09 批次嵌套 LIST<STRUCT> parquet（exam/lab/order/record）按 ETL2 引擎期望的平铺 staging schema 适配脱敏落库 dev PG 的端到端流程。使用场景：hos301 数据重导、同类含 LIST<STRUCT> 列的医院新批次、复现 301 导入链路（含 14 种 examClass 归一化、lab NUL 清洗、3.5M lab 大事务 commit 等）。

<!-- skill 同步副本：.zcode/skills/ 与 .claude/skills/ 内容须保持一致（.zcode 被 gitignore，.claude/skills 是 harness 注册位置）；修改任一侧请同步另一侧 -->

# hos301 嵌套 LIST/STRUCT Parquet → ETL2 脱敏 → dev PG 导入
适用于解放军总医院（hos301）2026-09 批次 parquet **含嵌套 LIST<STRUCT>**（每行嵌套多个子项）的场景。
区别于 `hospital-parquet-import`（聚焦平铺 schema + 列名适配），本 skill 重点解决：
- LIST 嵌套展平（每子项一行）
- struct 子字段访问（DuckDB 语法）
- 引擎按行 exam_type 归一化（spec `exam_type_field`）
- 大数据量（3M+ lab）commit 阶段耗时长的应对
- 引擎 spec 透传 `detail_type` 的隐性缺陷
- ETL1 端数据清洗（NUL 字符、NUMERIC 范围）

成功先例：hos301（解放军总医院）2026-09 批次
- exam.parquet (199k) / lab.parquet (285k→3.5M) / order.parquet (8.3k→870k) / record.parquet (18k)
- 导入耗时 ~50 分钟（含单次 3.5M lab 大事务 commit 等待 ~30 分钟）

## 流水线全景

```
医院新 parquet（嵌套 LIST<STRUCT>）
  → ① schema 探查（duckdb DESCRIBE + unnest）    duckdb inline 探查
  → ② ETL1 适配脚本（展平 LIST → 行级 + 清洗）    backend/etl1_adapt_hos301_*.py
       - LATERAL unnest() 展平
       - replace(..., chr(0), '') 清 NUL
       - TRY_CAST + 范围限制 防 NUMERIC 溢出
       - 列名按引擎期望 schema 重映射
  → ③ 独立 staging 目录                            data_hos301/hos301/
  → ④ ETL2 引擎 spec（按中心加新条目）             anon_etl_engine._CENTER_PARQUET_SPECS
       - spec["exam_type_field"]: 按行 exam_type 归一化（修复 301 多 examClass 问题）
       - import_center 必须透传 detail_type（隐藏 bug，见"踩坑项"）
  → ⑤ ETL2 引擎 CLI（HMAC 脱敏 + 幂等 upsert）     anon_etl --centers <center>
  → ⑥ 验证 V1-V10                                 见"验证"
```

核心代码位置：
- `backend/app/plugin/module_medical/hospital/anon_etl_engine.py` — `_CENTER_PARQUET_SPECS` 字典 + 各 `_import_*_table` 函数
- `backend/app/plugin/module_medical/hospital/anon_etl_service.py` — `run_center` 单事务控制
- `backend/app/plugin/module_medical/hospital/anonymize.py` — `compute_anon_id` / `compute_anon_exam_id` / `compute_anon_visit_id`
- `backend/app/plugin/module_medical/hospital/anon_etl/__main__.py` — CLI 入口

## 前置条件

```bash
cd backend
grep -E "DATABASE_HOST|DATABASE_NAME|LNRS_ANON_SECRET|LNRS_DATA_ROOT" env/.env.dev
psql --version   # 18.x
PGPASSWORD='lnrs_pwd' psql -h 127.0.0.1 -U lnrs -d postgres -tAc \
  "SELECT count(*) FROM lnrs.med_hospital WHERE code='hos301'"   # 应存在，未存在需先注册
```

Linux 适配（与 `hospital-parquet-import` 的 Linux 适配节一致）：
- `./.venv/Scripts/python.exe` → `./.venv/bin/python`
- `/c/Program Files/PostgreSQL/18/bin/psql` → `psql`

## Step 1 — schema 探查（duckdb inline）

```python
import duckdb
con = duckdb.connect()
# schema + 嵌套结构
con.execute("DESCRIBE SELECT * FROM read_parquet('<源 parquet>')").fetchall()
# 嵌套 LIST 展平观察（展平后预估行数）
con.execute("SELECT COUNT(*) FROM read_parquet('<源>'), unnest(<list_col>)").fetchone()
# 嵌套 LIST 子项类型
con.execute("SELECT unnest(<list_col>).a, COUNT(*) FROM read_parquet('<源>') GROUP BY 1").fetchall()
```

## Step 2 — ETL1 适配脚本（核心）

参考 `backend/etl1_adapt_hos301_{exam,lab,order,record}.py`。
关键模式：

### 2.1 LIST 展平 + struct 子字段访问
```python
sql = f"""
    COPY (
        SELECT
            ...,
            unnest.reportItemName AS item_name,    -- 通过 unnest.<field> 访问 struct 子字段
            ...
        FROM read_parquet('{src}'),
             LATERAL unnest(<list_col>) AS unnest
    ) TO '{dst}' (FORMAT PARQUET, OVERWRITE_OR_IGNORE)
"""
```

DuckDB 关键技巧：
- `LATERAL unnest(list) AS unnest` 后，struct 子字段通过 `unnest.<field>` 访问
- `list[1].field` 取 LIST 首元素；空/NULL list 返 NULL（不报错）
- 不要用 `unnest(lst) AS u(a,b)` 命名——只 expose `unnest` 列

### 2.2 NUL 字符清洗（PG VARCHAR 拒绝 \u0000）
```python
def _safe_varchar(expr):
    return f"replace({expr}, chr(0), '')"

# 用法：所有 VARCHAR 列 _safe_varchar("...") 包裹
```

301 lab 有 7 行 `labTestMaster[1].notesForSpcm` 尾部含 `\u0000`；触发
`asyncpg.exceptions.UntranslatableCharacterError: \u0000 cannot be converted to text`。
检查方法：
```python
WHERE position(chr(0) IN labTestMaster[1].notesForSpcm) > 0
```

### 2.3 数值范围限制（防 NUMERIC 溢出）
301 lab 有 4 行 DNA 病毒载量超 NUMERIC(12,4) 上限（99999999.9999），最大 2.1E8：
```python
def _safe_numeric(expr):
    return (
        f"CASE WHEN TRY_CAST({expr} AS DOUBLE) IS NULL THEN NULL "
        f"WHEN TRY_CAST({expr} AS DOUBLE) > 99999999.9999 THEN NULL "
        f"WHEN TRY_CAST({expr} AS DOUBLE) < -99999999.9999 THEN NULL "
        f"ELSE TRY_CAST({expr} AS DOUBLE) END"
    )
```

引擎用 `float(raw_val)` → NUMERIC(12,4)；PG 拒绝单条 → 整批 rollback。
**溢出值置 NULL，原始字符串保留在 lab_detail_json（lab_detail_json 兜底所有非引擎 known 列）。**

### 2.4 列名重命名
301 orderText 在引擎侧期望列名 `task_name`：
```sql
CAST(unnest.orderText AS VARCHAR) AS task_name
```
spec 用 `order_name_field="task_name"` 告诉引擎从 `task_name` 列取值。

### 2.5 顶层无 visit_id
301 lab 顶层无 visit_id → 引擎 `_import_lab_table` 自动退化为"只挂 patient"
（见 `anon_etl_engine.py:1567-1569`：`if vid: visit_id_set.add(...)`，
visit_id 为空时 anon_visit_id=None，patient_id 由 patient 占位生成）。

### 2.6 顶层全非空但 visit 集合只覆盖部分
301 record.parquet 有 78 行 visit_id 唯一（其余 17919 行 visit_id 重复）→
引擎 `seen_visit_hash` 去重后 visit/visit_detail 入库78 条**visit 级别**。
**这是预期行为：1 个 visit 可能跨多行 visit_record（如多次入院合并去重）。**

### 2.7 examType 按行归一化
301 exam.parquet 含 14 种 examClass（中文：超声/ＣＴ/病理/心电图/放射/磁共振/核医学/胃肠镜/肺功能/耳鼻喉/气管镜/其他/体检/泌外）。引擎 spec.exam_type 是标量字符串，**默认全行同一 exam_type**。修法：
1. ETL1 端 CASE WHEN 把 examClass 归一化为新列 `examType`（映射到 med_dict_mapping 的 dict_value）
2. ETL2 引擎 spec 加 `"exam_type_field": "examType"`，`_import_exam_text_table` 按行 `rd.get(exam_type_field) or exam_type`
3. spec.exam_type 仍需占位（如 `"Other"`）兼容旧逻辑
4. spec.detail_type + detail_fields 落 detail_json（examPara/examItem 等）

## Step 3 — 独立 staging 目录

**务必独立**（与已有 data_<批次>  / 隔离），如 `data_hos301/hos301/`。
`.gitignore` 追加 `/data_hos301/`。

## Step 4 — ETL2 引擎 spec（最小扩展）

```python
# backend/app/plugin/module_medical/hospital/anon_etl_engine.py:_CENTER_PARQUET_SPECS
"hos301": [
    {
        "src_table": "exam", "kind": "exam_text",
        "exam_type": "Other",                       # 占位
        "exam_type_field": "examType",              # 启用按行 exam_type
        "id_field": "exam_id",
        "body_fields": ["impression", "description", "recommendation"],
        "detail_type": "exam_extras",               # 必须显式设置
        "detail_fields": ["examClass", "examPara", "examSubClass",
                          "examItem", "performedBy", "reqDept"],
        "date_field": "examDateTime",
    },
    {
        "src_table": "visit_record", "kind": "visit_detail",
        "id_field": "visit_id", "date_field": "admission_time",
    },
    {"src_table": "lab_result", "kind": "lab", "id_field": "test_id"},
    {
        "src_table": "order", "kind": "order",
        "order_type": "order", "order_name_field": "task_name",
    },
],
```

### 引擎代码修改清单

**重要**：必须确保 `_import_exam_text_table` 接受 `exam_type_field` 且 `import_center` 透传 `detail_type`：

1. `_import_exam_text_table` 签名加 `exam_type_field: str | None = None`
2. 函数体内 `exam_type` 写入改：
   ```python
   "exam_type": (rd.get(exam_type_field) or exam_type) if exam_type_field else exam_type,
   ```
3. **删除 dict 内重复键**（之前是 `"exam_type": exam_type,` 覆盖动态表达式）
4. `import_center` 透传 `detail_type=spec.get("detail_type")`（**之前漏传，导致 exam_detail=0**）

## Step 5 — 跑 ETL

```bash
cd backend
PYTHONPATH="" ENVIRONMENT=dev ./.venv/bin/python -m app.plugin.module_medical.hospital.anon_etl \
  --centers hos301 --data-root ../data_hos301 > /tmp/hos301_run.log 2>&1 &
```

成功标志：日志末尾 `hos301 success rows={...}`。
**大事务（3M+ lab_result）commit 阶段耗时30+ 分钟是正常的**：
- PG 端会话会持续显示 "idle in transaction"
- 客户端进程持续 ~11 GB RSS（所有 lab_rows 在内存）
- 进程状态 Ssl/睡眠 + ep_poll 等待 socket
- **不要 kill**，否则整个事务回滚

清理失败批（如需重跑）：
```sql
DELETE FROM lnrs.lnrs_anon_phi_audit WHERE batch_id IN
  (SELECT batch_id FROM lnrs.lnrs_anon_ingest_batch WHERE center_code='hos301');
DELETE FROM lnrs.lnrs_anon_ingest_batch WHERE center_code='hos301';
DELETE FROM lnrs.lnrs_anon_report_text WHERE anon_exam_id IN
  (SELECT anon_exam_id FROM lnrs.lnrs_anon_exam WHERE center_code='hos301');
DELETE FROM lnrs.lnrs_anon_exam_detail WHERE anon_exam_id IN
  (SELECT anon_exam_id FROM lnrs.lnrs_anon_exam WHERE center_code='hos301');
DELETE FROM lnrs.lnrs_anon_exam WHERE center_code='hos301';
DELETE FROM lnrs.lnrs_anon_visit_detail WHERE center_code='hos301';
DELETE FROM lnrs.lnrs_anon_visit WHERE center_code='hos301';
DELETE FROM lnrs.lnrs_anon_lab_result WHERE center_code='hos301';
DELETE FROM lnrs.lnrs_anon_order WHERE center_code='hos301';
DELETE FROM lnrs.lnrs_anon_patient WHERE center_code='hos301';
```

## Step 6 — V1-V10 验证

```sql
-- V1: body_clean 非空率（应 100%）
SELECT count(*) FILTER (WHERE body_clean IS NOT NULL AND body_clean != '') AS non_empty,
       count(*) AS total
FROM lnrs.lnrs_anon_report_text rt
JOIN lnrs.lnrs_anon_exam e ON rt.anon_exam_id=e.anon_exam_id WHERE e.center_code='hos301';

-- V2: detail_json != '{}' 非空率（应 100%）
SELECT count(*) FILTER (WHERE detail_json != '{}'::jsonb) AS non_empty,
       count(*) AS total
FROM lnrs.lnrs_anon_exam_detail ed
JOIN lnrs.lnrs_anon_exam e ON ed.anon_exam_id=e.anon_exam_id WHERE e.center_code='hos301';

-- V3-V8: phi_audit / exam / patient / exam_type / lab value / batch
SELECT count(*) FROM lnrs.lnrs_anon_phi_audit pa
  JOIN lnrs.lnrs_anon_ingest_batch ib ON pa.batch_id=ib.batch_id WHERE ib.center_code='hos301';
SELECT center_code, exam_type, count(*) FROM lnrs.lnrs_anon_exam WHERE center_code='hos301' GROUP BY 1,2 ORDER BY 3 DESC;
SELECT count(*) FILTER (WHERE item_result_value IS NULL) AS null_val,
       count(*) FILTER (WHERE item_result_value IS NOT NULL) AS non_null, count(*) AS total
FROM lnrs.lnrs_anon_lab_result WHERE center_code='hos301';
SELECT status, row_counts::text FROM lnrs.lnrs_anon_ingest_batch
  WHERE center_code='hos301' ORDER BY started_at DESC LIMIT 1;

-- V10: FK 孤儿（应 0）
SELECT 'orphan_rt', count(*) FROM lnrs.lnrs_anon_report_text rt
  LEFT JOIN lnrs.lnrs_anon_exam e ON e.anon_exam_id = rt.anon_exam_id
  WHERE rt.anon_exam_id IS NOT NULL AND e.anon_exam_id IS NULL AND e.center_code='hos301'
UNION ALL
SELECT 'orphan_lab', count(*) FROM lnrs.lnrs_anon_lab_result lr
  LEFT JOIN lnrs.lnrs_anon_patient p ON p.patient_id = lr.patient_id
  WHERE lr.center_code='hos301' AND p.patient_id IS NULL;
```

## 踩坑项（必看）

### A. SQL 中 nextval() 在 CTE 多行场景失效

PG 14+ 在 `INSERT ... SELECT FROM (VALUES (...),(...))` 形式下，
同一 CTE 中多次 `nextval(seq)` 被规划为**只调用一次**，
导致多行共享同一 id → `duplicate key`。
修法：**先用 CTE 锁住起点 + ROW_NUMBER() 派生**：
```sql
WITH seq_start AS (SELECT COALESCE(MAX(id), nextval('xxx_id_seq') - 1) AS base FROM xxx)
SELECT s.base + m.rn AS new_id, ...
```

### B. import_center 漏传 detail_type（隐性 bug）

`anon_etl_engine.py:2047` 之前**只透传 `detail_fields` 而不传 `detail_type`**，
导致 `if detail_rows` 实际 `_build_detail_json` 不执行。
**修复**：
```python
detail_type=spec.get("detail_type"),
detail_fields=spec.get("detail_fields"),
```

### C. dict 重复键覆盖

写 dict literal 时 `{"a": 1, "a": 2}` Python 取后者。
我的 `exam_type` 修复时写了
```python
"exam_type": (rd.get(exam_type_field) or exam_type) if exam_type_field else exam_type,
"exam_type": exam_type,    # ← 这一行覆盖上面动态表达式
```
导致 spec 全部变成 `"Other"` 占位。修：**删重复键**。

### D. pg_restore 与 psql -f 失败但报告成功

详见 `hospital-parquet-import` skill "踩坑项"——`INSERT 0 14` 等输
出 + psql 退出码 0 不代表事务提交。**最后一行 COMMIT 才决定**。
检查文件结尾是否有 `COMMIT;` 行（**之前我 edit 漏删了 COMMIT 导致
事务整段被回滚，所有 INSERT 看似成功实际 0 行落库**）。

### E. 大事务 commit 阶段加速

3.5M lab 单事务 INSERT（即使分批 BATCH_SIZE=1000）仍在单事务内，
commit 阶段需刷脏页到磁盘，耗时30+ 分钟。PG 端 `idle in transaction`、
进程状态 Ssl/睡眠 + ep_poll 是正常状态。
**绝对不要** SIGKILL，否则整事务回滚 + 重新跑又30 分钟。

**修复方案（已落地于 `anon_etl_engine.py:import_center`）**：事务内
`SET LOCAL synchronous_commit = off`——commit 不再等 fsync，事务内
批量 INSERT 阶段耗时不变，**commit 阶段从 ~30 分钟降到秒级**。

落地位置（`backend/app/plugin/module_medical/hospital/anon_etl_engine.py`
`import_center` 入口，docstring 闭合后、`if not data_dir.exists()` 之前）：
```python
import os
fsync_off = os.environ.get("LNRS_ETL_FSYNC", "0") != "1"
if fsync_off:
    try:
        await db.execute(text("SET LOCAL synchronous_commit = off"))
        log.info(f"ETL2: {center_code} 事务内 synchronous_commit=off "
                 f"（commit 不等 fsync；崩溃丢失风险由重跑幂等吸收）")
    except Exception as e:
        # PG 版本不支持或权限不足 → 回退到 on（保持原行为，不阻断导入）
        log.warning(f"ETL2: {center_code} 关闭 synchronous_commit 失败，回退默认: {e}")
```

**关键属性**：
- `SET LOCAL` 作用域限定到当前事务，commit/rollback 后自动复原——
  **不会**污染同一连接上的查询 API 调用。
- **不会**影响 INSERT 阶段耗时（与每批 WAL 写入有关，与 fsync 无关）；
  **仅** commit 阶段从 fsync 等待 30+ 分钟降到秒级。
- 代价：DB crash 时本事务已 ACK 但未刷盘的最后 WAL 段会丢失 →
  ETL 重跑幂等即可吸收（`ON CONFLICT DO UPDATE` + patient 三态机）。

**环境变量逃生口**：
- 默认 `LNRS_ETL_FSYNC=0` → 关闭 fsync（**当前默认**）
- `LNRS_ETL_FSYNC=1` → 恢复同步落盘（用于对比 commit 耗时或复现 on 行为）

**配套调优**（PG 端 `postgresql.conf` / `ALTER SYSTEM`，需 reload）：
```sql
ALTER SYSTEM SET wal_compression = on;            -- 减小 WAL 体积
ALTER SYSTEM SET max_wal_size = '4GB';            -- 减少 checkpoint 触发频率
ALTER SYSTEM SET maintenance_work_mem = '1GB';    -- index build 阶段
```
这些 **不会**影响 commit fsync 等待本身，但能降低 checkpoint 期间的 stall。

### F. lab 无 visit_id → 引擎退化为只挂 patient

`_import_lab_table` (`anon_etl_engine.py:1525-1531`) 在 `vid` 为空时不
预读 visit 桥、`anon_visit_id=None`、lab_rows 的 patient_id 由 patient
占位填充。无需 ETL1 端做特殊处理。

### G. record.parquet Doc[] HTML 文档大、入库成本高

301 record.parquet 的 `Doc[]` 是 XML/HTML 体（XMLNS+HTML+注释），清洗
成本高；本次**不导入 Doc 数据**——只入顶层 visit 信息。
`Doc` 列保留为 LIST 字段整体进入 `visit_detail_json`（引擎剩余字段自动
进 JSONB 兜底），后续若要解析 Doc 可在 ETL1 端展开为 exam_text
(ClinicalNote 类型) 走 exam_detail。

### H. KNOWLEDGE_CENTERS 与 `--centers` 关系

`anon_etl_service.KNOWN_CENTERS = ("shengyi", "xinqiao", "zhujiang")` 是
CLI 默认处理列表。新中心可**不改 KNOWN_CENTERS**，只要 `--centers <center>`
显式传入；引擎会 warning "未知中心" 但仍尝试处理。

## 与已有 skill 的区别

| 维度 | hospital-parquet-import | nested-parquet-hospital-import（本 skill） |
|---|---|---|
| 源 parquet schema | 平铺 schema（每行=一个实体） | 嵌套 LIST<STRUCT>（每行=多个子项） |
| 适配脚本工作 | 列名重映射 + struct 整体引用 | **LIST 展平 + struct 子字段访问** + 数据清洗 |
| 引擎改动 | 无需改引擎 spec（spec 已覆盖） | 需加 spec 条目；`exam_type_field`/`detail_type` 透传 |
| 数据量 | 万级 | 百万~千万级（大事务 commit 30+ 分钟） |
| 数据问题 | 无明显脏数据 | NUL 字符 / NUMERIC 溢出 / examClass 多值 |
| Commit 加速 | 不需要（万级） | `SET LOCAL synchronous_commit=off`（commit 30 分钟 → 秒级） |

## 适配脚本模板参考

```python
"""ETL-1 适配: 中心 X 的 <file>.parquet → ETL-2 <target>.parquet 布局。

源文件: <源路径> (N 行)
  关键列: <schema 描述，含 LIST<STRUCT> 嵌套>

ETL2 spec: src_table='<X>', kind='<kind>', id_field='<Y>'

DuckDB 关键技巧:
  - LATERAL unnest(<list>) AS unnest → 通过 unnest.<field> 访问 struct 子字段
  - replace(<expr>, chr(0), '') 清洗 NUL（PG VARCHAR 拒绝 \\u0000）
  - TRY_CAST + 范围限制 防 NUMERIC 溢出
  - list[1].field 取 LIST 首元素；空/NULL list 返 NULL（不报错）
| 维度 | hospital-parquet-import | nested-parquet-301-import（本 skill，301 2026-09 批次先例） |
幂等: COPY OVERWRITE_OR_IGNORE。
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path
import duckdb

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default=None)
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()
    backend_dir = Path(__file__).resolve().parent
    src = Path(args.src).resolve() if args.src else \
          Path("<源路径>").resolve()
    out_dir = Path(args.out_dir).resolve() if args.out_dir else \
              (backend_dir.parent / "data_<批次>" / "<center>").resolve()
    if not src.exists():
        print(f"[ERR] 源文件不存在: {src}", file=sys.stderr)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / "<file>.parquet"
    con = duckdb.connect(":memory:")
    sql = f"""
        COPY (
            SELECT
                replace(CAST(<col> AS VARCHAR), chr(0), '') AS <col>,
                ...
            FROM read_parquet('{src.as_posix()}'),
                 LATERAL unnest(<list_col>) AS unnest
        ) TO '{dst.as_posix()}' (FORMAT PARQUET, OVERWRITE_OR_IGNORE)
    """
    con.execute(sql)
    n = con.execute("SELECT COUNT(*) FROM read_parquet(?)", [dst.as_posix()]).fetchone()[0]
    print(f"[OK] {dst} 已生成: {n} 行")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```