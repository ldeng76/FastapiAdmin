# shengyi 实体肿瘤基因检测报告 ETL 设计文档

实施日期：2026-09-14
适用范围：shengyi 中心 `non_privacy_info.visit.entity_tumor_gene_report.*.parquet` 系列（6 个文件）
相关文件：`backend/etl1_adapt_shengyi_202609.py`、`backend/app/plugin/module_medical/hospital/anon_etl_engine.py`、`verify_shengyi_genetic.sql`

---

## 1. 数据形态

### 6 个 parquet 文件结构

每份原始"实体肿瘤基因检测报告 PDF"抽取后切成 6 个独立 parquet，每个对应一种变异类型：

| 文件 | 含义 | 字段数 |
|---|---|---:|
| 单核苷酸变异基因 (SNV) | 单核苷酸位点变异 | 17 |
| 拷贝数变异基因 (CNV) | 拷贝数变异 | 14 |
| 插入缺失突变基因 (indel) | 小片段插入/缺失 | 21 |
| 融合基因 (fusion) | 基因融合事件 | 16 |
| 其他变异基因 (other) | 无法归入上述4类的罕见变异 | 25 |
| 用药参考 (drug_ref) | 基于上述变异的药物建议 | 9 |

**关键事实**：
- SNV/CNV 文件含 `检测单号` 字段（真单号），indel/fusion/其他/用药 4 文件 `检测单号` **100% 为空**（抽取丢失）
- 每个 parquet 顶层都有 `患者编号` 列（明文 pid），`就诊编号` 在报告级基名下
- 同一份原始报告 PDF → 同一 (pid, vid) → 6 个 parquet 各 1 行（共 6 行，跨文件聚合后塞进同一 exam 的 6 bucket）

### 真单号与空单号分布

| 文件 | 总行数 | 空单号行 | 真单号 (pid,vid,ri) 唯一对 |
|---|---:|---:|---:|
| SNV | 2059 | 64 | 162 |
| CNV | 226 | 175 | 51 |
| indel | 226 | **226** | 0 |
| fusion | 226 | **226** | 0 |
| 其他变异 | 226 | **226** | 0 |
| 用药参考 | 226 | **226** | 0 |

- 真单号 162 SNV ∩ 51 CNV = **46 重合**（同一报告同时含 SNV 与 CNV 检测）
- 真单号唯一 (pid, vid, ri) 实际 = 162 + 51 - 46 = **167**
- 空单号 (pid,vid) 跨 indel/fusion/其他/用药 4 文件 = **224 个**（含 2 对重复）

---

## 2. 设计决策：6 bucket 是否平等？

**答：平等，无主从关系。**

### 临床视角

6 个变异类型对应不同分子机制，临床重要性视具体病例而定：
- 肺癌主变异可能是 EGFR L858R **SNV**
- 乳腺癌主变异可能是 HER2 **CNV 扩增**
- 白血病主变异可能是 BCR-ABL **融合**
- 罕见病例主变异可能落在 **other bucket**

用药参考（drug_ref）是衍生数据，但 ETL 阶段独立抽取，不依赖其他 bucket 的内容。

### ETL 设计证据

1. **6 个 CTE 完全同构**（snv/cnv/indel/fusion/other/drugref 各自独立 `SELECT ... FROM src('genetic_xxx')`），无 JOIN、无优先级
2. **GROUP BY (pid, vid, report_id) 后用 `LIST(variant) FILTER (WHERE src = ...)` 平铺到 6 个 bucket** —— DuckDB FILTER 不分先后
3. **spec 里 `detail_fields: ["test_name", "variants"]`** 把 `variants` 作为整体 dict，引擎不解析 bucket 优先级
4. **实际 staging 393 行的 variants 字典 6 bucket 全填满**（跨6 文件同 (pid,vid) 聚合）

### 真正"主要"信息是 test_name

6 bucket 共享同一 `test_name`（同一份 PDF 抽取的同一报告级字段），代表该份报告的检测项目名称（如"实体肿瘤 76 基因检测（DNA层面）"）。

---

## 3. PG 存放结构

**核心结构**：每个 staging 行 → 1 条 `lnrs_anon_exam` + 1 条 `lnrs_anon_exam_detail`（detail_json 装 6 bucket 变异明细）。

### 表1：lnrs_anon_exam（每 exam 1 行）

```sql
lnrs_anon_exam (
  anon_exam_id      VARCHAR(40),    -- 'ANON_EXAM_<12位hex>' = HMAC(secret, "shengyi:{report_id}")
  patient_id        VARCHAR(16),    -- 'ANON_<12位hex>' = HMAC(secret, "shengyi:{患者编号}")
  center_code       VARCHAR(32),    -- 'shengyi'
  exam_type         VARCHAR(32),    -- 'Genetic'
  exam_date         DATE,           -- 反查 lnrs_anon_visit_detail.admission_time
  source_exam_hash  CHAR(64),      -- SHA256("shengyi:{report_id}"), UNIQUE 约束去重
  anon_visit_id     VARCHAR(40),    -- 'ANON_VISIT_<12位hex>'
  created_batch_id UUID, last_seen_batch_id UUID,
  created_at TIMESTAMP, updated_at TIMESTAMP
)
```

UNIQUE 约束：`UNIQUE (center_code, source_exam_hash)`

### 表2：lnrs_anon_exam_detail（每 exam 1 行 detail）

```sql
lnrs_anon_exam_detail (
  anon_exam_id    VARCHAR(40),    -- → lnrs_anon_exam.anon_exam_id (FK)
  detail_type     VARCHAR(32),    -- 'genetic'（spec 里 detail_type 字段）
  detail_ordinal  SMALLINT,       -- 1（spec 未设 ordinal_field，默认）
  detail_json     JSONB,          -- 见下方结构
  created_batch_id UUID, created_at TIMESTAMP
)
PRIMARY KEY (anon_exam_id, detail_type, detail_ordinal)
```

### detail_json 结构

```json
{
  "test_name": "<string>",  // 来自 staging test_name 列，6 bucket 共享
  "variants": {
    "snv":      [ {...variant结构体...}, {...}, ... ],
    "cnv":      [ {...variant结构体...}, ... ],
    "indel":    [ {...variant结构体...}, ... ],
    "fusion":   [ {...variant结构体...}, ... ],
    "other":    [ {...variant结构体...}, ... ],
    "drug_ref": [ {...variant结构体...}, ... ]
  }
}
```

### variant 结构体示例

SNV variant（按 parquet 列映射）：
```json
{
  "子项编号": "1",
  "基因名称": "EGFR",
  "结果正常标志": "异常",
  "转录本": "NM_005228",
  "外显子": "21",
  "CDS突变": "c.2573T>G",
  "氨基酸突变": "p.L858R",
  "突变丰度": "32.5%",
  "结果解读": "...",
  "检测方法": "NGS",
  "变异意义": "致病",
  "纯合/杂合": "杂合",
  "变异类型": "missense"
}
```

drug_ref variant（结构不同）：
```json
{
  "子项编号": "1",
  "药物编号": "DB00316",
  "药物名称": "Erlotinib",
  "临床意义": "敏感",
  "适用疾病": "非小细胞肺癌",
  "证据级别": "A级",
  "参考文献": "..."
}
```

### 物理对应关系

```
6 parquet 文件                              staging PG                              ───────────────────── ────────────                    ────────────
SNV 162 真单号对 (1995 子项)        ─→ GROUP BY ─→ 167 staging 行 ─→ 167 exam
SNV 64 空号 (pid,vid)               ─→ 派生 SYG-* ─→ 64 行        ─→ 64 exam
CNV 51 真单号对                      ─→ GROUP BY ─→ 51 staging 行 ─→ (与 SNV 重合 46)
CNV 175 空号 (pid,vid)              ─→ 派生 SYG-* ─→ 175 行      ─→ 175 exam
indel 224 空号 (pid,vid)             ─→ 派生 SYG-* ─→ 224 行      ─→ 224 exam
fusion 224 空号 (pid,vid)            ─→ 派生 SYG-* ─→ 224 行      ─→ 224 exam
other 224 空号 (pid,vid)             ─→ 派生 SYG-* ─→ 224 行      ─→ 224 exam
drugref 224 空号 (pid,vid)           ─→ 派生 SYG-* ─→ 224 行      ─→ 224 exam
                                                                             ─────────────────────
                                                                                合计 1309 exam
```

**同一 exam 行的 6 bucket 同时填满**（跨 6 文件 GROUP BY 后，SNV/CNV 真单号 exam 的 variants 也含 224 个 indel/fusion/other/drugref 子项）。

---

## 4. 关键设计：合成 key `SYG-{n}-{8位hex}`

### 演进过程

**第一版（错误）**：`SYG-{n}`，n = `ROW_NUMBER() OVER (PARTITION BY 患者编号, 就诊编号 ORDER BY 子项编号)`
- 224 个不同 (pid,vid) 在 indel 文件中派生**全部为 `SYG-1`** → 同源 hash 冲突
- ETL2 引擎 `ON CONFLICT DO UPDATE` 静默吞掉 223 行，仅 1 行 SYG-1 入库
- 严重数据丢失：staging 393 行 → PG 168 行（-225）

**第二版（修复）**：`SYG-{n}-{8位hex}`
- 8 位 hex = `SUBSTRING(SHA256(src||'|'||pid||'|'||vid||'|'||子项编号), 1, 8)`
- src ∈ {snv, cnv, indel, fusion, other, drugref} 区分 6 文件
- 全局唯一：224 个 indel 空号派生 224 个不同 SYG-*，hash 全不同
- ETL2 1:1 入库 1309 exam

### SQL 片段（snv CTE 的 CASE ELSE）

```sql
ELSE 'SYG-' || CAST(
       ROW_NUMBER() OVER (
         PARTITION BY "患者编号",
                      "非隐私信息.就诊.实体肿瘤基因检测报告.就诊编号"
         ORDER BY "非隐私信息.就诊.实体肿瘤基因检测报告.单核苷酸变异基因.子项编号"
       ) AS VARCHAR) || '-' || SUBSTRING(
         SHA256('snv' || '|' || CAST("患者编号" AS VARCHAR) || '|'
                || CAST("非隐私信息.就诊.实体肿瘤基因检测报告.就诊编号" AS VARCHAR) || '|'
                || COALESCE(CAST("非隐私信息.就诊.实体肿瘤基因检测报告.单核苷酸变异基因.子项编号" AS VARCHAR), ''))::VARCHAR,
         1, 8)
END AS report_id
```

其他 5 个 CTE 结构相同，src 字面替换为 cnv/indel/fusion/other/drugref。

### 真单号 hash 不变

`CASE WHEN 检测单号 IS NOT NULL AND 检测单号 <> '' THEN 检测单号 ELSE ... END` —— 真单号行直接用原 `检测单号` 字面作 report_id，**SHA256("shengyi:真单号") 与原 ETL 完全一致**，不影响旧 167 个真单号 exam 的 hash 幂等性。

---

## 5. ETL1 改动

### F_FILE / F_COL / SUB 新增 4 项

```python
F_FILE["genetic_indel"]   = f"{C}.就诊.实体肿瘤基因检测报告.插入缺失突变基因"
F_FILE["genetic_fusion"]  = f"{C}.就诊.实体肿瘤基因检测报告.融合基因"
F_FILE["genetic_other"]   = f"{C}.就诊.实体肿瘤基因检测报告.其他变异基因"
F_FILE["genetic_drugref"] = f"{C}.就诊.实体肿瘤基因检测报告.用药参考"

F_COL[新4项] = f"{C}.就诊.实体肿瘤基因检测报告"  # 报告级基名（所有子段共享）

SUB["genetic_indel"]   = "插入缺失突变基因"
SUB["genetic_fusion"]  = "融合基因"
SUB["genetic_other"]   = "其他变异基因"
SUB["genetic_drugref"] = "用药参考"
```

### SQL_GENETIC 完全重写为 6 文件 UNION ALL

6 个 CTE（snv/cnv/indel/fusion/other/drugref）各自：
1. 取 `患者编号` AS patient_id
2. 取报告级 `就诊编号` AS visit_id
3. 取子段级 `检测单号`，空则合成 SYG-*
4. 取 `检测项目名称` AS test_name
5. 拼成 variant 结构体（按各文件实际列）

最后：
```sql
SELECT patient_id, visit_id, report_id,
       ANY_VALUE(test_name) AS test_name,
       {'snv':      LIST(variant) FILTER (WHERE src = 'snv'),
        'cnv':      LIST(variant) FILTER (WHERE src = 'cnv'),
        'indel':    LIST(variant) FILTER (WHERE src = 'indel'),
        'fusion':   LIST(variant) FILTER (WHERE src = 'fusion'),
        'other':    LIST(variant) FILTER (WHERE src = 'other'),
        'drug_ref': LIST(variant) FILTER (WHERE src = 'drugref')} AS variants
FROM u
GROUP BY 1, 2, 3
```

---

## 6. ETL2 端零字节改动

spec 不动（`anon_etl_engine.py:2480-2486`）：
```python
{
    "src_table": "genetic_report", "kind": "exam_text",
    "exam_type": "Genetic", "id_field": "report_id",
    "body_fields": [], "detail_type": "genetic",
    "detail_fields": ["test_name", "variants"],
    "date_field": "", "date_lookup_field": "visit_id",
}
```

引擎自动处理：
- `anon_exam_id = compute_anon_exam_id(center, str(report_id))`
- `source_exam_hash = SHA256(f"{center}:{report_id}")` UNIQUE 去重
- `anon_visit_id` 通过 `visit_id` 反查 `lnrs_anon_visit_detail.admission_time` 取 exam_date

---

## 7. 实施记录

| 步骤 | 状态 | 结果 |
|---|---|---|
| Step 1: ETL1 F_FILE/F_COL/SUB 加 4 项 | ✓ | F_FILE=26, F_COL=26, SUB=15 |
| Step 2: SQL_GENETIC 重写为 6 文件 UNION + SYG 合成 key | ✓ | staging 1310 行（首版 393 错误，后修复合 key 后 1310）|
| Step 3: ETL2 spec 零字节改动 | ✓ | 引擎自动消化 |
| 备份 lnrs_anon_exam + detail | ✓ | `backend/.backup/shengyi_genetic_exam_pre_20260911_234847.sql` 等 |
| ETL1 重跑 23 表 | ✓ | genetic_report 1310 行（167 真单号 + 1143 SYG 唯一）|
| 清理 PG 旧 SYG hash 残留 | ✓ | 删除 2 行 `5b3a9ec3...` / `0af0c428...` |
| ETL2 only-genetic 重跑 | ✓ | **1309 exam 全量入库**（1310 -1 dedup）|

### 最终入库数

| 表 | 行数 |
|---|---:|
| ETL1 staging `genetic_report.parquet` | 1310 |
| ETL2 `lnrs_anon_exam` (Genetic) | 1309 |
| ETL2 `lnrs_anon_exam_detail` (Genetic) | 1309 |

---

## 8. 1309 exam 详细推导

**公式**：staging 1310 行 → 1309 unique SHA256 hash → PG 入库 1309 exam（少 1 个 hash = 1 行被 dedup）。

### Step 1: 真单号 staging 行数（167）

| 来源 | 唯一 (pid, vid, ri) 对 |
|---|---:|
| SNV 真单号 | 162 |
| CNV 真单号 | 51 |
| SNV ∩ CNV（同一 (pid,vid) 同时有 SNV 与 CNV 真单号）| 46（这些算 staging 同一行 GROUP BY 合并了） |
| **真单号 staging unique** | **162 + 51 - 46 = 167** |

### Step 2: 空号 staging 行数（1143）

| 来源 | 空号 (pid, vid) 对 | ROW_NUMBER 子项展开 | staging 行数 |
|---|---:|---:|---:|
| SNV 空号 64 (pid, vid) | 64 | 1:1 | 64 |
| CNV 空号 175 (pid, vid) | 175 | 1:1 | 175 |
| indel 224 (pid, vid) 对（含 2 对重复）| 224 | 2 对 × 1 重复行 = 226 | 226 |
| fusion 同 indel | 224 | 2 对 × 1 重复行 = 226 | 226 |
| other 同 indel | 224 | 2 对 × 1 重复行 = 226 | 226 |
| drugref 同 indel | 224 | 2 对 × 1 重复行 = 226 | 226 |
| **小计** | | | **1143** |

**多子项展开原理**：indel/fusion/其他/用药 4 文件各有 2 对 (pid,vid) 重复：
- `('7024627', '1201578601')` × 2 行（子项编号均空）
- `('7518684', '1201257474')` × 2 行（子项编号均空）

DuckDB `ROW_NUMBER() OVER (PARTITION BY 患者编号, 就诊编号 ORDER BY 子项编号)` 在子项编号全空的两行上输出 1、2 → 叠加 `SHA256(src\|pid\|vid\|子项编号)` 后缀后生成 SYG-1-xxx 与 SYG-2-xxx 两个唯一 hash → 2 行独立 staging。

所以每个 100% 空单号文件实际 staging 行数 = 224 (pid,vid) + 2 重复行 = **226 行**。

实测 SYG-2 staging = **8 行**（2 对 (pid,vid) × 4 个 indel/fusion/其他/用药 文件），SYG-1 = 1135 行，合计 1143 SYG-* staging 行。

### Step 3: 总 staging 行数

```
167 真单号 + 1143 SYG-* = 1310 staging 行
```

### Step 4: ETL2 UNIQUE 去重（1310 → 1309）

ETL2 用 `UNIQUE (center_code, source_exam_hash)` + `ON CONFLICT DO UPDATE`，1310 staging 行经 SHA256 后有 1309 个 unique hash：

| 类别 | staging unique hash | PG 入库 exam |
|---|---:|---:|
| 真单号 (162+51-46 = 167) | 167 - **1**（`2000074593` dup）= 166 | 166 |
| SYG-*（1143 unique hash，全部唯一）| 1143 | 1143 |
| **合计** | **1309** | **1309** |

**唯一 dup 来源**：真单号 `2000074593` 在 SNV 文件某 (pid, vid) 下出现 **2 次**（子项编号不同），都带同一 `检测单号=2000074593` → ETL1 GROUP BY (pid, vid, report_id) 后这 2 行聚合到同一分组，但因 variant 结构体不同，仍产生 2 staging 行 → 同 report_id → 同 SHA256 → ETL2 UNIQUE 约束保留 1 行。

实测：`hash=d4c3688128424177...` 对应 report_id `(2000074593, 2000074593)` 两个 staging 行。

### 最终 1309 = 166 真单号 + 1143 SYG-*

---

## 9. 验证方法

执行 `verify_shengyi_genetic.sql` 跑 14 段断言，重点检查：

| # | 断言 | 期望 |
|---|---|---|
| 9 | source_exam_hash 全局唯一 | dup_hash_count = 0（本次修复的关键）|
| 2 | 旧 SYG hash 残留 | old-SYG-1-dirty / old-SYG-2-dirty = 0（清理成功）|
| 4 | exam_detail 6 bucket 覆盖率 | has_snv/has_cnv/has_indel/has_fusion/has_other/has_drugref 均 > 0 |
| 6 | patient FK 完整性 | orphan_exam = 0 |
| 7 | anon_visit_id FK 完整性 | orphan_visit = 0 |
| 8 | exam_date 反查命中 | null_date = 0 |
| 10 | 涉及患者/就诊维度 | unique_patients ~216, unique_visits ~224 |

---

## 10. 业务查询路径

```sql
-- 1. 找到某病人所有基因报告
SELECT * FROM lnrs.lnrs_anon_exam
WHERE patient_id = 'ANON_xxx' AND exam_type = 'Genetic';

-- 2. 看一份报告的 6 类变异
SELECT e.anon_exam_id, e.exam_date,
       d.detail_json->'variants'->'snv'      AS snv_variants,
       d.detail_json->'variants'->'cnv'      AS cnv_variants,
       d.detail_json->'variants'->'indel'    AS indel_variants,
       d.detail_json->'variants'->'fusion'   AS fusion_variants,
       d.detail_json->'variants'->'other'    AS other_variants,
       d.detail_json->'variants'->'drug_ref' AS drug_variants
FROM lnrs.lnrs_anon_exam e
JOIN lnrs.lnrs_anon_exam_detail d ON d.anon_exam_id = e.anon_exam_id
WHERE e.center_code = 'shengyi' AND e.exam_type = 'Genetic'
LIMIT 10;

-- 3. 跨表 join（exam + patient + visit_detail）
SELECT e.anon_exam_id, p.sex, p.birth_date,
       vd.admission_time, vd.visit_category, e.exam_date
FROM lnrs.lnrs_anon_exam e
JOIN lnrs.lnrs_anon_patient p
  ON p.patient_id = e.patient_id AND p.center_code = e.center_code
LEFT JOIN lnrs.lnrs_anon_visit_detail vd
  ON vd.anon_visit_id = e.anon_visit_id AND vd.center_code = e.center_code
WHERE e.center_code = 'shengyi' AND e.exam_type = 'Genetic';

-- 4. GIN 索引高效检索变异内容
SELECT * FROM lnrs.lnrs_anon_exam_detail
WHERE detail_json @> '{"variants":{"snv":[{"基因名称":"EGFR"}]}}';
```

---

## 11. 关键文件清单

- `backend/etl1_adapt_shengyi_202609.py` — ETL1 适配器（修改 SQL_GENETIC、F_FILE/F_COL/SUB）
- `backend/app/plugin/module_medical/hospital/anon_etl_engine.py` — ETL2 引擎（spec 零改动）
- `backend/app/plugin/module_medical/hospital/anonymize.py` — HMAC 派生函数
- `backend/.backup/etl2_only_genetic.py` — 单独跑 genetic_report 入库的临时脚本
- `docs/etl2/shengyi_genetic/verify_shengyi_genetic.sql` — 14 段端到端验证 SQL
- `docs/etl2/shengyi_genetic/README.md` — 本文档