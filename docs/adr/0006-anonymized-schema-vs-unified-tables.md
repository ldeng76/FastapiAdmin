# 脱敏窄表 Schema 与 业务宽表 Schema 的逻辑关系

> 范围：厘清 [ADR-0006 脱敏后落库 Schema](./0006-anonymized-data-schema.md)
> 及其对应 DDL（[0006-anonymized-schema.sql](./0006-anonymized-schema.sql)）
> 与统一业务宽表 [docs/unified_table_schema.md](../unified_table_schema.md)
> 之间的关系、关联键与 ETL 边界。

---

## 1. 一句话结论

**两份 schema 不在同一抽象层，但有明确的上下游 ETL 串联关系：**

- `unified_table_schema.md` = **业务语义层（多中心研究宽表）**
- `0006-anonymized-schema.sql` = **脱敏物理层（跨模态落库窄表）**

ETL 通过"宽表 → 窄表"的导数管线把两者串起来，业务宽表负责"研究问题时如何取数"，脱敏窄表负责"如何合规地保存"。两者**不互相替代**，但通过同一份 ETL 共享一份 `anon_id` ↔ `patient_id`（及 `anon_exam_id` ↔ 检查级业务编号）的映射表。

---

## 2. 设计目标对比

| 维度 | `unified_table_schema.md` | `0006-anonymized-schema.sql` |
|---|---|---|
| **抽象层** | 业务层 / 多中心研究宽表 | 脱敏物理层 / ETL 落地窄表 |
| **实体核心** | 患者、就诊、标本、手术、基因等医疗概念 | 一次检查（`anon_exam`）+ 其报告/发现/DICOM 资产 |
| **去标识化** | 假名化（院内 `patient_id`） | 强去标识化（`anon_id`, `anon_exam_id`） |
| **PHI 处理** | 保留非隐私字段 | 删除原始 ID/姓名；保留正文但经 `clean_method` 审计 |
| **唯一标识** | `patient_id` + `visit_id` + 业务编号 | `anon_id`（人级）+ `anon_exam_id`（检查级桥梁） |
| **跨模态关联** | 通过 `patient_id` / `visit_id` 串接 | 通过 `anon_exam_id` 单点串接（一次检查=一个 ID） |
| **接入来源** | Excel + 多中心结构化数据 | `csv_report` / `dicom_dir` / `dicom_zip` |
| **跨院合并** | 4 张统一表可 `UNION`（核心字段一致） | 通过 `center_code` 跨院，不按业务概念合并 |
| **可逆性** | 可反推（`patient_id` 是院内 ID） | 不可反推（HMAC 截断，无密钥不能还原） |
| **表数量** | 14 张业务表（4 统一 + 10 省医独有，新增 6 张追加表后） | 9 张（核心表 + 视图 + 触发器 + 审计） |
| **核心 join 键** | `patient_id` / `visit_id` | `anon_exam_id`（跨模态唯一桥梁） |

---

## 3. 总体流水线

```text
                ┌──────────────────────────────┐
                │  原始来源                       │
                │  • Excel (省医结构化导出)       │
                │  • DICOM 影像                  │
                │  • 报告文本 (PDF/CSV/JSON)       │
                └──────────────┬────────────────┘
                               │
              ┌────────────────┴────────────────┐
              ▼                                 ▼
    ┌────────────────────┐           ┌─────────────────────────┐
    │  ETL-1 加载宽表      │           │  ETL-2 脱敏落库          │
    │  目标: unified_…    │           │  目标: anonymized-schema │
    │  data/shengyi/*.pq │           │  lnrs_anon_*.sql         │
    └────────┬───────────┘           └────────┬────────────────┘
             │                                │
             │  ETL 同时维护桥接映射表:         │
             │   patient_id  ↔ anon_id         │
             │   visit_id    ↔ anon_exam_id    │
             │   report_id   ↔ anon_exam_id    │
             ▼                                ▼
        研究宽表查询                    合规分析 / 跨模态研究
```

两条管线的产物**互不重叠**：

- 业务宽表保留 `birth_date` 精度、保留多中心并集字段、用于研究查询；
- 脱敏窄表只保留 `birth_year`，删去所有原始 ID，提供 DICOM 与报告的一对一桥梁，支持审计回放。

---

## 4. 表级映射（业务宽表 ↔ 脱敏窄表）

### 4.1 一对一映射

| 业务宽表 (`unified_table_schema`) | 对应脱敏窄表 | 关系说明 |
|---|---|---|
| `patient` | `anon_patient` | 同一患者实例；`patient_id` → `anon_id`（HMAC） |
| `imaging_report` / `ultrasound_report` / `ecg_report` 中的"一次影像检查"行 | `anon_exam` | 一次检查 = 一个 `anon_exam_id` |
| 同上的报告正文（CLOB） | `anon_report_text.body_clean` | 报告正文清洗后落库 |
| 同上的结构化发现（直径/密度/分期等） | `anon_exam_finding` | 一行一个发现项 |
| DICOM 物理文件 | `anon_dicom_series` + `anon_dicom_instance` | 仅落元数据 + 文件路径，不保留像素 |

### 4.2 多对一 / 聚合映射

| 业务宽表 | 落到脱敏窄表 | 聚合规则 |
|---|---|---|
| `lab_result`（每条子项） | `anon_exam` + `anon_exam_finding[]` | 同一 `report_id` 聚合为 1 个 `anon_exam_id`；`item_name/value` 转 `finding_type/value_*` |
| `pathology_specimen.pathology_diagnosis` | `anon_report_text.body_clean` | 病案首页诊断通常不含 DICOM，按报告正文清洗入库 |
| `progress_note.content`、`medical_history.present_illness` | `anon_report_text.body_clean` | 新增 `exam_type` 枚举（如 `medical_history` / `progress_note`），见 §7 |
| `diagnosis`（新增表） | `anon_report_text.body_clean` + `anon_exam_finding` | 诊断编码/名称可作为 `finding_type='diagnosis'` 的结构化 finding |

### 4.3 无映射（不在脱敏层关注范围内）

| 业务宽表 | 说明 |
|---|---|
| `genetic_test` | 基因检测通常为 CSV/Excel，不在 anon schema 设计目标内 |
| `drug_order` / `non_drug_order` | 医嘱类非"影像+报告"语义，不入 anon schema |
| `visit_record` | 业务语义概念，不入 anon schema |
| `nursing_observation` / `icu_observation` / `anesthesia_event`（新增 6 张表里的） | 护理/ICU/麻醉的事件流，缺乏与 DICOM/报告的天然一对一对应，需要后续 ADR 扩展 |

---

## 5. 字段级映射示例

下面以 `imaging_report` 为例给出 ETL-1 → ETL-2 的字段映射，其他业务表可类推。

### 5.1 患者级

```text
unified.patient.patient_id        ──► anon_id        (经 HMAC 截断，详见 ADR-0001)
unified.patient.gender            ──► sex            ('男' → 'M', '女' → 'F', null → 'U')
unified.patient.birth_date        ──► birth_year     (仅保留年份，丢弃月日)
unified.patient.source_center     ──► center_code    (取"省医"→'shengyi'，依枚举)
```

### 5.2 检查级（一次影像检查 = 一个 `anon_exam`）

```text
unified.imaging_report.visit_id       ──► anon_exam_id  (经 HMAC 截断)
unified.imaging_report.exam_type      ──► exam_type     (归一化: 'CT', 'MR', 'DR', 'PETCT' …)
unified.imaging_report.exam_date      ──► exam_date
unified.imaging_report.exam_body_part ──► body_part     (通过 dicom_series.body_part 也存一份)
```

### 5.3 报告级

```text
unified.imaging_report.ultrasound_finding
  (或 imaging_report.imaging_finding 文本)
                                   ──► anon_report_text.body_clean
                                       clean_method    = 'regex+llm' | 'regex_only' | 'manual_review'
                                       pii_replaced_count 计数
```

### 5.4 结构化发现级

```text
unified.imaging_report 中"结节长径 12mm"  ──► anon_exam_finding
                                            finding_type    = 'nodule_size_mm'
                                            value_numeric   = 12.0
                                            laterality      = 'R' (若记录)
                                            raw_value_hash  = sha256('12mm' or '12.0')

unified.imaging_report 中"右肺上叶"    ──► anon_exam_finding
                                            finding_type    = 'nodule_location'
                                            value_text      = 'RUL'
                                            laterality      = 'R'
```

---

## 6. ETL 桥接：匿名化映射表

业务宽表与脱敏窄表之间，**必须存在一张 ETL 私有映射表**，以便后续回溯（合规需要 "在数据治理团队用密钥配合下" 才能反解）。

```text
-- 仅 ETL 维护，不属于业务宽表或脱敏窄表：
lnrs_etl_id_map (
    entity           VARCHAR(32),    -- 'patient' | 'visit' | 'report' | 'exam' | …
    center_code      VARCHAR(32),
    business_id      VARCHAR(64),    -- patient_id / visit_id / report_id …
    anon_id          VARCHAR(32),    -- anon_id 或 anon_exam_id
    ingest_batch_id  UUID,
    created_at       TIMESTAMP
)
```

设计哲学与 `anon_dicom_uid_map` 一致：

- **不进生产库**，落审计物理隔离库；
- **仅做 ETL 审计 / 治理团队回溯**，研究查询绝不直接 JOIN 此表；
- 由于 `anon_id` 由 HMAC 截断生成，单从 `anon_id` 无法反推 `business_id`，需要密钥 + 中心码 + 原 ID 一并出现才能重算（详见 ADR-0001）。

---

## 7. 新增 6 张业务宽表对脱敏窄表的影响

最近追加的 `diagnosis` / `medical_history` / `progress_note` / `nursing_observation` / `icu_observation` / `anesthesia_event` 6 张表，主要为长文本与事件型数据，**全部是就诊（visit）级，而非影像检查（exam）级**。

### 7.1 历史结论（已废弃）

> 本节最初建议"不引入新表，长文本塞 `anon_report_text.body_clean`、结构化塞 `anon_exam_finding`"。该结论在动手写 DDL 时被证伪——见 7.2。

### 7.2 为什么不能复用 anon_exam

`anon_exam` 的语义是"一次影像检查 + 一次报告"，而 6 张业务表与影像**无关**，挂到 exam 上会丢"非影像就诊"的数据：

| 宽表 | 粒度 | 试图塞进 | 问题 |
|------|------|---------|------|
| diagnosis | visit 级 | anon_exam_finding | 没有影像的就诊诊断无处可挂 |
| medical_history | visit 级 | anon_report_text | 6 段长文本 + 1 行/visit，body_clean 装不下结构 |
| progress_note | visit + note 级 | anon_report_text | 单 visit 几十条 note，全塞会爆 |
| nursing_observation | 测量子项级 | — | 无 anon 表能装时序测量 |
| icu_observation | ICU 观察项级 | — | 同上 |
| anesthesia_event | medication + observation 双事件 | — | finding 的 (numeric \| text) 装不下双事件 |

### 7.3 新决策（2026-07-19）：引入第二条桥 `anon_visit`

新增 `lnrs_anon_visit` 作为**第二条桥**，与 `anon_exam` 并列：

```
anon_patient ─┬─ (N) anon_exam    ── 影像/检查 (anon_visit_id 可空)
              │
              └─ (N) anon_visit   ── 就诊 (新增)
                      ├─ (N) anon_diagnosis
                      ├─ (1) anon_medical_history
                      ├─ (N) anon_progress_note
                      ├─ (N) anon_nursing_observation
                      ├─ (N) anon_icu_observation
                      └─ (N) anon_anesthesia_event
```

设计要点：

1. **不破坏 anon_exam 语义** —— 仅 `ALTER TABLE` 给 `anon_exam` 加可空的 `anon_visit_id` 列；ETL 反查 `visit_record` 成功时回填，失败置 null。
2. **anon_visit 主键** —— `anon_visit_id = 'ANON_VIS_' + HMAC(secret, center + PAT_LOCAL_ID + ':' + VISIT_ORDINAL)[:12]`，遵循 ADR-0001 的"统一确定性脱敏"约定。
3. **幂等 UNIQUE** —— 每张业务表都带 `(anon_visit_id, 原始字段哈希)` 形态的 UNIQUE，让重复导入只 UPDATE。
4. **PHI 处理** —— 原始 `patient_id` / `visit_id` / 护士签名 / 医生姓名一律不落库；长文本经 regex+LLM 清洗后落 `body_clean`；结构化字段（如 ICD-10 编码、护理测量值）直接入库。
5. **视图扩展** —— 新增 `v_visit_full`，提供就诊级一站式聚合（各类业务数据的计数）。原 `v_exam_full` 不动。

### 7.4 落地产物

| 文件 | 用途 |
|------|------|
| `0006-anonymized-schema.sql` | 原 9 表基础结构（未改） |
| `0006-anonymized-schema-patch-visit.sql` | **本补丁**：新增 4 枚举 + `anon_visit` + 6 张业务表 + `v_visit_full` + 触发器，并对 `anon_exam` 加 `anon_visit_id` 列 |

执行顺序：先 `0006-anonymized-schema.sql`，再 `0006-anonymized-schema-patch-visit.sql`。补丁用 `BEGIN/COMMIT` 包裹，失败回滚到无变更。

### 7.5 未纳入本补丁的设计点

- **原始 visit_id ↔ anon_visit_id 映射表** —— 与 §6 `lnrs_etl_id_map` 同等隔离要求，由 ETL 桥接表承担，不在本补丁中。
- **跨中心 visit_ordinal 语义** —— 不同医院的 `m/n` 序号语义可能不一致（如门诊次数 vs 住院次数），后续 ETL 时如发现冲突再在 `anon_visit.visit_type` 枚举上区分。
- **`body_clean` 与 exam 级 `anon_report_text.body_clean` 复用 LLM 流水线** —— 实现侧可共用，但库表上保持独立，避免污染。

---

## 8. 关键观察

1. **关联路径不同**：
   - 宽表：`patient_id` / `visit_id` → `report_id` → 检查正文与发现
   - 窄表：`anon_id` → `anon_exam_id` → `body_clean` + `finding` + `dicom_series`

2. **id 不可互译**：
   - `patient_id` 不能直接 → `anon_id`（需要密钥 + 中心码 + HMAC）
   - 同样 `anon_id` 也不能反查 `patient_id`
   - 因此 ETL 中应独立维护映射表（§6）以便审计

3. **跨院查询模式不同**：
   - 业务宽表：4 张统一表 `UNION ALL`，按 `patient_id` 拼接
   - 脱敏窄表：所有院数据集中放在一个库，通过 `center_code` 过滤
   - 研究员使用 `data/shengyi/*.parquet` + `data/zhujiang_xinqiao/*.parquet`
   - 工程平台使用 `lnrs_anon_*` 集中表 + 视图 `v_exam_full`

4. **审计与可逆性的强弱差异**：
   - 业务宽表不审计 PH 过 程；
   - 脱敏窄表强制写 `phi_audit` 与 `ingest_batch`，可回放"用什么密钥、什么规则、清洗了什么字段"。

5. **统一表 ≠ 统一脱敏存储**：跨模态（DICOM 像素 + 报告文本）只能在 `anon_exam_id` 维度统一，宽表是按业务概念统一。两者都不可或缺，是同一研究问题的两个不同切面。

---

## 9. 落地清单（ETL 实施时按此推进）

1. **保持统一业务宽表的语义优先** —— `unified_table_schema.md` 是研究侧的真相来源，先固定它。
2. **✅ ETL-1 把宽表写入 Parquet（2026-07-19 已落地）** —— 实现位置：`backend/app/plugin/module_medical/hospital/etl1/`。
   - **入口**：CLI `python -m app.plugin.module_medical.hospital.etl1 --center shengyi --xlsx ...` 或 API `POST /api/v1/medical/hospital/{id}/etl1/run`（FastAPI 后台任务 + Redis 进度）。
   - **架构**：core 引擎 + per-center config（`centers/shengyi.py`）。新增医院只需加一份 config。
   - **Excel 读取**：duckdb `excel` 扩展（`read_xlsx(all_varchar=true, header=true)`），200MB / 1.05M 行单表 28s 完成。
   - **shengyi 已验证**：16 张表共 **3,207,305 行**（4 universal + 9 单 sheet + 3 跨 sheet 合并），全部 visit_id 反查 missed=0，输出到 `data/shengyi/*.parquet`。
   - **关键修正**：每张 sheet 是**单行表头**（行 1），数据从行 2 开始；早先脚本 `analyze_xlsx_raw.py` 的 `header_rows=10` 是误报。
   - **未覆盖**：珠江-新桥 center config（数据是 CSV 不是 xlsx，接入时再加一份）。
3. **ETL-2 把宽表逐行映射到 anon schema** —— `patient` → `anon_patient`、`imaging_report` → `anon_exam`/text/finding、`dicom_*` → `dicom_series`。
   - 已有 `etl_engine.py`（Parquet → PostgreSQL 的 `med_*` 表）。
   - 但 ETL-2 当前不覆盖 `anon_*` 表（脱敏窄表）—— 见 `0006-anonymized-schema-patch-visit.sql` 的 ETL-2 扩展。
4. **桥接映射表单独物理隔离** —— 与 `anon_dicom_uid_map` 同等待遇，避免反推。
5. **每次导入写一个 `ingest_batch` + 多行 `phi_audit`** —— 不留遗漏。
6. **新追加 6 张宽表通过 `anon_visit` 桥落入脱敏库** —— 见 §7 与 `0006-anonymized-schema-patch-visit.sql`。ETL-2 在加载 visit 级宽表时，先建 `anon_visit`，再依次落 6 张业务表。

---

## 10. 关联文档

- [ADR-0001 统一确定性脱敏方案](./0001-linkable-anonymization.md) — `anon_id` / `anon_exam_id` 生成规则
- [ADR-0006 脱敏后落库 Schema (设计稿)](./0006-anonymized-data-schema.md) — DDL 背后的设计与约束
- [0006-anonymized-schema.sql](./0006-anonymized-schema.sql) — 当前生效的 DDL 脚本
- [docs/unified_table_schema.md](../unified_table_schema.md) — 业务宽表定义
