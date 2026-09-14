# 省医(shengyi) 实体肿瘤基因检测报告空【检测单号】合成 `report_id` 实施方案

状态：**已完成**（2026-09-12 实施完成；2026-09-14 修复 hash 冲突并最终验证）

## 0. 结论先行

- ETL1 SQL_GENETIC 改写为 6 文件 UNION ALL + 合成 key（`SYG-{n}-{sha256_8hex}`）
- ETL2 spec **零字节改动**（下游契约保持稳定）
- 最终：staging1310 行 → ETL2 入库1309 行（去重后），PG 中 `lnrs_anon_exam` (center='shengyi' AND exam_type='Genetic') 共1309 行
- 备份在 `backend/.backup/shengyi_genetic_exam_pre_20260911_234847.sql`（437MB，含 149 万行 exam）+ `shengyi_genetic_exam_detail_pre_20260911_234847.sql`（2.2GB）

## 1. 问题场景

shengyi 批次里实体肿瘤基因检测报告 6 个 parquet 文件（SNV/CNV/indel/fusion/其他变异/用药参考），**`检测单号` 列存在大量空值**：

| 文件 | total | 空号子项行 | 真单号子项行 |
|---|---:|---:|---:|
| SNV | 2059 | 64 | 1995 |
| CNV | 226 | 175 | 51 |
| indel | 226 | **226** | 0 |
| fusion | 226 | **226** | 0 |
| 其他变异 | 226 | **226** | 0 |
| 用药参考 | 226 | **226** | 0 |

合计 **1143 行空号子项**。原 ETL1 SQL 用 `WHERE 检测单号 IS NOT NULL AND 检测单号 <> ''` 全部丢掉，导致：
- indel/fusion/其他变异/用药参考 4 文件的 224 份原始报告数据**从未入 PG**
- SNV/CNV 的空号行（239 行）也丢失

## 2. 实施步骤（可复用模板）

### 2.1 备份（必做）

```bash
mkdir -p backend/.backup
PGPASSWORD=lnrs_pwd pg_dump -h 127.0.0.1 -U lnrs -d postgres -t lnrs.lnrs_anon_exam \
  --data-only --rows-per-insert=1000 \
  > backend/.backup/shengyi_genetic_exam_pre_$(date +%Y%m%d_%H%M%S).sql
PGPASSWORD=lnrs_pwd pg_dump -h 127.0.0.1 -U lnrs -d postgres -t lnrs.lnrs_anon_exam_detail \
  --data-only --rows-per-insert=1000 \
  > backend/.backup/shengyi_genetic_exam_detail_pre_$(date +%Y%m%d_%H%M%S).sql
```

注：pg_dump 无 `--where`，按全表 dump；或用 `psql -c "COPY ... TO ... WHERE ..."`。

### 2.2 ETL1 SQL_GENETIC 改写

`backend/etl1_adapt_shengyi_202609.py`：

**a. F_FILE / F_COL / SUB 加 4 个空读文件**（indel/fusion/其他/用药）：

```python
F_FILE = {
    ..., "genetic_snv": ..., "genetic_cnv": ...,
    "genetic_indel":    f"{C}.就诊.实体肿瘤基因检测报告.插入缺失突变基因",
    "genetic_fusion":   f"{C}.就诊.实体肿瘤基因检测报告.融合基因",
    "genetic_other":    f"{C}.就诊.实体肿瘤基因检测报告.其他变异基因",
    "genetic_drugref":  f"{C}.就诊.实体肿瘤基因检测报告.用药参考",
}
F_COL.update({
    "genetic_snv": ..., "genetic_cnv": ...,
    "genetic_indel":   f"{C}.就诊.实体肿瘤基因检测报告",
    "genetic_fusion":  f"{C}.就诊.实体肿瘤基因检测报告",
    "genetic_other":   f"{C}.就诊.实体肿瘤基因检测报告",
    "genetic_drugref": f"{C}.就诊.实体肿瘤基因检测报告",
})
SUB = {
    ..., "genetic_snv": "单核苷酸变异基因", "genetic_cnv": "拷贝数变异基因",
    "genetic_indel":   "插入缺失突变基因",
    "genetic_fusion":  "融合基因",
    "genetic_other":   "其他变异基因",
    "genetic_drugref": "用药参考",
}
```

**b. SQL_GENETIC 6 文件 CTE UNION ALL + CASE 合成 key**：

每个 CTE 的 `report_id` 字段：

```sql
CASE
  WHEN <检测单号> IS NOT NULL AND <检测单号> <> ''
  THEN <检测单号>                                          -- 真单号保留原值，hash 不变
  ELSE 'SYG-' || CAST(ROW_NUMBER() OVER (
         PARTITION BY 患者编号, 就诊编号 ORDER BY 子项编号
       ) AS VARCHAR)
       || '-' || SUBSTRING(SHA256('<src>' || '|' ||
         CAST(患者编号 AS VARCHAR) || '|' ||
         CAST(就诊编号 AS VARCHAR) || '|' ||
         COALESCE(CAST(子项编号 AS VARCHAR), ''))::VARCHAR, 1, 8)
END AS report_id
```

6 个 CTE 各对应 src 标签：`'snv' / 'cnv' / 'indel' / 'fusion' / 'other' / 'drugref'`。

最外层 GROUP BY 仍按 `(pid, vid, report_id)`，variants dict 含 6 个 bucket：

```sql
{u AS (SELECT * FROM snv UNION ALL SELECT * FROM cnv ... UNION ALL SELECT * FROM drugref)}
SELECT patient_id, visit_id, report_id,
       ANY_VALUE(test_name) AS test_name,
       {'snv':      LIST(variant) FILTER (WHERE src = 'snv'),
        'cnv':      LIST(variant) FILTER (WHERE src = 'cnv'),
        'indel':    LIST(variant) FILTER (WHERE src = 'indel'),
        'fusion':   LIST(variant) FILTER (WHERE src = 'fusion'),
        'other':    LIST(variant) FILTER (WHERE src = 'other'),
        'drug_ref': LIST(variant) FILTER (WHERE src = 'drugref')} AS variants
FROM u GROUP BY 1, 2, 3
```

### 2.3 ETL2 spec 不动

`backend/app/plugin/module_medical/hospital/anon_etl_engine.py` 的 shengyi `genetic_report` 条目：

```python
{"src_table": "genetic_report", "kind": "exam_text",
 "exam_type": "Genetic", "id_field": "report_id",
 "body_fields": [], "detail_type": "genetic",
 "detail_fields": ["test_name", "variants"],
 "date_field": "", "date_lookup_field": "visit_id"},
```

引擎自动消化新 report_id 形态（`SYG-{n}-{hash}` 字符串），按 `report_id` 计算 `anon_exam_id` + `source_exam_hash`。

### 2.4 ETL2 单独跑 genetic_report（避全表超时）

全表 ETL2 处理 shengyi 23 表耗时 30+ 分钟，Bash 1800s 超时。**单独跑 genetic_report**：

```python
# backend/.backup/etl2_only_genetic.py
import asyncio, sys, uuid
from pathlib import Path
sys.path.insert(0, "/home/dzy/wk/lnrs/backend")
from app.config.setting import settings
from app.core.logger import log
from app.plugin.module_medical.hospital.anon_etl_engine import (
    _import_exam_text_table, _resolve_hospital_id,
)
from app.plugin.module_medical.hospital.enum_normalization import load_all_enum_mappings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

PARQUET = Path("/home/dzy/wk/lnrs/data_shengyi202609/shengyi/genetic_report.parquet")
CENTER = "shengyi"
BATCH_ID = str(uuid.uuid4())

async def main():
    engine = create_async_engine(settings.ASYNC_DB_URI, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as db:
        hospital_id = await _resolve_hospital_id(db, CENTER)
        await load_all_enum_mappings(db, hospital_id=hospital_id)
        n = await _import_exam_text_table(
            db,
            center_code=CENTER,
            parquet_path=PARQUET,
            src_table="genetic_report",
            exam_type="Genetic",
            exam_type_field=None,
            hospital_id=hospital_id,
            id_field="report_id",
            body_fields=[],
            detail_type="genetic",
            detail_fields=["test_name", "variants"],
            date_field="",
            date_lookup_field="visit_id",
            batch_id=BATCH_ID,
        )
        await db.commit()
        log.info(f"genetic_report imported: {n}")
    await engine.dispose()

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

执行：`ENVIRONMENT=dev ./.venv/bin/python backend/.backup/etl2_only_genetic.py`

## 3. **关键陷阱：合成 key 必须全局唯一**

### 3.1 第一版设计（失败）

合成 key 形如 `'SYG-1'`、`'SYG-2'`，用 `ROW_NUMBER() OVER (PARTITION BY pid, vid ORDER BY 子项编号)` 派生。

**症状**：staging 393 行 → ETL2 入库仅 168 行 → **缺失 225 行**。

**根因**：
```sql
source_exam_hash = SHA256("shengyi:SYG-1")  -- 全局唯一哈希值
```
UNIQUE 约束 `(center_code, source_exam_hash)`。ETL2 用 `ON CONFLICT DO UPDATE` 模式：**所有 224 行 SYG-1 派生同一 hash → 后续 223 行触发 ON CONFLICT，UPDATE 覆盖 patient_id/anon_visit_id → 静默吞掉 223 行数据**。

### 3.2 修复方案

合成 key 必须让 `SHA256("center:" + report_id)` 也全局唯一。**嵌入 `(src|pid|vid|子项编号)` 的 SHA256 摘要**：

```sql
ELSE 'SYG-' || CAST(ROW_NUMBER() OVER (...) AS VARCHAR)
       || '-' || SUBSTRING(SHA256('<src>' || '|' || pid || '|' || vid || '|' || 子项编号)::VARCHAR, 1, 8)
END
```

8 字符 hex 摘要足以保证全局唯一（生日碰撞概率可忽略）。

### 3.3 验证方法

```bash
# staging unique hash 应等于 PG exam 行数
python3 -c "
import duckdb, hashlib, subprocess, os
con = duckdb.connect()
df = con.execute(\"SELECT patient_id, visit_id, report_id FROM '/path/genetic_report.parquet'\").fetchall()
expected_h = {hashlib.sha256(f'shengyi:{r}'.encode()).hexdigest() for _,_,r in df}
pg = subprocess.check_output(['psql','-h','127.0.0.1','-U','lnrs','-d','postgres','-t','-c',
    \"SELECT source_exam_hash FROM lnrs.lnrs_anon_exam WHERE center_code='shengyi' AND exam_type='Genetic';\"],
    env={**os.environ,'PGPASSWORD':'lnrs_pwd'}).decode().splitlines()
pg_h = {x.strip() for x in pg if x.strip()}
print('staging unique:', len(expected_h), 'PG count:', len(pg_h))
print('1:1 match:', expected_h == pg_h)
"
```

**期望**：staging unique hash == PG exam 行数 == staging 总行数（或 staging-1 因 GROUP BY 去重）。

## 4. 数字预期对照表（用于其他中心类似场景预判）

| 字段 | 数字 |
|---|---|
| staging 行数 | 唯一 (pid, vid, report_id) 对数；不展开子项为独立 row |
| 真单号行数 | SNV 真单号 (pid, vid, ri) 唯一数 + CNV 唯一数 - 跨文件重合 |
| SYG-* 行数 | 唯一空号 (pid, vid, src, 子项编号) 派生 SHA256 数 |
| ETL2 入库 exam | staging unique hash 数（= staging unique report_id 数） |
| exam_detail 行 | 与 exam 同（spec 设 detail_ordinal=1） |

**关键误解**：原规划写"3189 行 / 1143 行"——把子项级行数当 staging 行数。**staging 是 GROUP BY (pid, vid, report_id) 后的报告级聚合**（与原 SNV 真单号 162 行 staging 语义一致）。

## 5. 后续操作清单

1. ETL1 重跑：`cd backend && ./.venv/bin/python etl1_adapt_shengyi_202609.py`
   - 期望 stdout 含 `genetic_report: 1310 行`（具体数随数据变）
2. ETL2 单独跑：`ENVIRONMENT=dev ./.venv/bin/python backend/.backup/etl2_only_genetic.py`
3. 验证脚本（同 §3.3）
4. **清理旧脏数据**（若有前次失败的 SYG-* 行残留）：

```sql
DELETE FROM lnrs.lnrs_anon_exam_detail d
 WHERE d.anon_exam_id IN (
   SELECT anon_exam_id FROM lnrs.lnrs_anon_exam
    WHERE center_code='shengyi' AND exam_type='Genetic'
      AND source_exam_hash IN ('<旧SYG-1 hash>', '<旧SYG-2 hash>'));
DELETE FROM lnrs.lnrs_anon_exam
 WHERE center_code='shengyi' AND exam_type='Genetic'
   AND source_exam_hash IN ('<旧SYG-1 hash>', '<旧SYG-2 hash>');
```

旧 SYG hash 形式（无 SHA256 后缀版）：
- `'5b3a9ec3e8aaf28c4e184837030f01536cdbc967861d876dda0442e44f3a59f9'`（SYG-1）
- `'0af0c4283ade544248fb982eb5934dfa29ad851fc8330d5447fab0fde10a8709'`（SYG-2）

## 6. 适用场景扩展

本方案适用于任何 ETL1 适配层遇"唯一键字段（report_id / exam_id / 等）部分为空"的场景：

1. ETL1 在 SELECT 时对空值派生确定性合成 key
2. **合成 key 必须让派生 hash 也全局唯一**（避免 ON CONFLICT DO UPDATE 静默吞数据）
3. ETL2 引擎无需改动；spec 也不动
4. 验证：staging unique hash 数 == PG 入库 exam 数

**通用合成 key 模板**：

```sql
CASE
  WHEN <unique_field> IS NOT NULL AND <unique_field> <> ''
  THEN <unique_field>
  ELSE '<prefix>-' || CAST(<row_number_expr> AS VARCHAR)
       || '-' || SUBSTRING(SHA256('<src_label>' || '|' || <其他唯一性字段...>)::VARCHAR, 1, 8)
END AS <id_field>
```

`<src_label>` 必须包含**文件/数据源标识**，保证跨文件也不同 hash。`<其他唯一性字段...>` 至少包含至少一个业务唯一键（pid/visit 等），保证跨 (pid, vid) 不同。

## 7. 变更文件清单

| 文件 | 改动 |
|---|---|
| `backend/etl1_adapt_shengyi_202609.py` | F_FILE / F_COL / SUB 加 4 项；SQL_GENETIC 完全重写 |
| `backend/app/plugin/module_medical/hospital/anon_etl_engine.py` | **未改动**（spec 已支持） |
| `backend/.backup/shengyi_genetic_exam_pre_*.sql` | 新增备份（437MB） |
| `backend/.backup/shengyi_genetic_exam_detail_pre_*.sql` | 新增备份（2.2GB） |
| `backend/.backup/etl2_only_genetic.py` | 新增脚本（单独跑 ETL2 genetic_report） |
| `docs/etl2/plan-shengyi-genetic-empty-report-id.md` | 本文档 |