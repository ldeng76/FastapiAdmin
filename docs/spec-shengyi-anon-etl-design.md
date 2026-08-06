# 省医 (shengyi) 数据导入 lnrs_anon_* 表 — 技术设计与实现说明

> 状态：**已实现**（代码已落，待执行数据导入）
> 日期：2026-07-29
> 依据：ADR-0006（匿名 schema）/ ADR-0008（字典值映射）/ ADR-0009（多中心配置驱动）/ ADR-0010（珠江字典驱动 ETL 验证）
> 数据源：`docs/demodata/0729_shengyi_sample/`

---

## 1. 背景与目标

将 `docs/demodata/0729_shengyi_sample/` 下的省医样例 Parquet 数据导入 PostgreSQL `lnrs` schema 的 `lnrs_anon_*` 表。流程对标已落地的珠江 (zhujiang) 导入，但因省医数据组织方式与珠江差异显著，不能完全套用。

### 1.1 设计决策（已确认）

| 决策点 | 选择 |
|---|---|
| 无对应目标表的数据（5 类） | **新增专用匿名表**承载，不强行塞进 exam |
| 字段映射风格 | **忠实保留原始结构（JSONB）**，不对齐珠江扁平语义 |
| pathology 无日期 | **反查 visit admission_time**（visit_id join 不上时跳过） |
| no_drug_order 无 visit_id | **anon_visit_id 留空**（退化为只挂 patient） |
| 新表命名 | `lnrs_anon_visit_detail` / `lnrs_anon_lab_result` / `lnrs_anon_order` |
| drug_order + no_drug_order | **合并为 lnrs_anon_order**（order_type 区分） |
| lab/order 关联 | **优先挂 visit，visit 缺失时退化为只挂 patient** |

### 1.2 省医 vs 珠江数据差异概览

| 维度 | 珠江 (`0723_珠江sample_pq`) | 省医 (`0729_shengyi_sample`) |
|---|---|---|
| 文件数 | 6 | 9 |
| 扩展名 | `.pq`（与引擎 `.parquet` 期望不符） | `.parquet`（兼容 ✅） |
| 数据模型 | 肺结节专病结构化 | 病案首页 + 全量电子病历宽表 |
| 嵌套风格 | 深度业务 struct（英文值） | 通用 `*_detail` 包装 struct，值大量为中文 |
| 中心标识 | 数据内有 `source_center` 列 | 数据内无 center 列，靠目录名隐式标识 |
| 空值占位 | NaT / NULL | 大量 `1900-01-01` 作 null 占位 ⚠️ |

省医 9 个文件处理方式：

| 文件 | 行数 | 目标 | 处理 |
|---|---:|---|---|
| `patient.parquet` | 5 | lnrs_anon_patient | 复用 patient kind |
| `visit_record.parquet` | 5 | 🆕 lnrs_anon_visit_detail + 自建 visit 桥 | 新 kind=visit_detail |
| `pahology_specimen.parquet` ⚠️拼写 | 5 | exam(Pathology)+detail | 复用 exam_text，date 反查 visit |
| `imaging_report.parquet` | 5 | exam(Radiology)+detail | 复用 exam_text |
| `ultrasound_report.parquet` | 1 | exam(Ultrasound)+detail | 复用 exam_text |
| `surgery_record.parquet` | 5 | visit + surgery | 复用 surgery（3 空行丢弃） |
| `lab_result.parquet` | 5 | 🆕 lnrs_anon_lab_result | 新 kind=lab |
| `drug_order.parquet` | 10 | 🆕 lnrs_anon_order(drug) | 新 kind=order |
| `no_drug_order.parquet` | 5 | 🆕 lnrs_anon_order(non_drug) | 新 kind=order |

---

## 2. 数据核对关键发现（已实测）

在实现前用 DuckDB 实测了省医数据的 join 可行性，结论：

| 表 | visit_id join visit_record | 日期来源 |
|---|---|---|
| pathology | 3/5 join 上（visit_id `1000837173` 不存在，2 行跳过） | 自身日期全空，反查 visit admission_time |
| imaging | 0/5 join | **自带 exam_date**（2010-01-18 等） |
| ultrasound | 1/1 join | 自带 exam_date |
| lab_result | 5/5 join | collection_time 为 1900-01-01 占位，需清洗 |
| drug_order | 非 NULL 行 join 不上，patient `3175462` 不在 visit_record | 靠 patient 占位兜底 |
| no_drug_order | visit_id 全空 | 退化为只挂 patient |

**关键约束（来自引擎源码核对）：**
- `lnrs_anon_surgery.anon_visit_id` 是 `NOT NULL`，surgery 3 行无 visit_id 会被守卫静默丢弃，无法补救。
- visit 桥**必须由 visit_detail 自己建立**：surgery 反推覆盖不全，且 visit_record 历史上被引擎显式跳过。
- lab/order 的守卫顺序不能照抄 surgery 三连守卫（`if not pid or not visit_id or not name: continue`），否则 visit_id 为空时连 patient 占位也建不了——须先无条件收集 patient。

---

## 3. 实现交付物

| 文件 | 类型 | 内容 |
|---|---|---|
| `backend/sql/postgres/0009-shengyi-dict-seed.sql` | 新建 | 注册 med_hospital(shengyi) + med_dict_mapping + med_exam_type 新值 |
| `backend/sql/postgres/0010-shengyi-anon-tables.sql` | 新建 | visit_detail / lab_result / order 三张表 DDL |
| `backend/app/plugin/module_medical/hospital/anon_model.py` | 改 | +3 ORM 模型 + 注册 |
| `backend/app/plugin/module_medical/hospital/anonymize.py` | 改 | +source_lab_hash / source_order_hash |
| `backend/app/plugin/module_medical/hospital/anon_etl_engine.py` | 改 | +_clean_date / +3 import / +3 upsert / +3 dispatch / 补 shengyi spec / pathology 反查 |
| `docs/spec-shengyi-anon-etl-design.md` | 新建 | 本文档 |

---

## 4. 新增表设计（仿 lnrs_anon_surgery 模板）

### 4.1 `lnrs_anon_visit_detail`（visit 1:1 富信息）

```sql
CREATE TABLE lnrs.lnrs_anon_visit_detail (
    visit_detail_id     BIGSERIAL    PRIMARY KEY,
    anon_visit_id       VARCHAR(40)  NOT NULL REFERENCES lnrs.lnrs_anon_visit(anon_visit_id) ON DELETE CASCADE,
    patient_id          VARCHAR(16)  NOT NULL REFERENCES lnrs.lnrs_anon_patient(patient_id) ON DELETE CASCADE,
    center_code         VARCHAR(32)  NOT NULL,
    visit_category      VARCHAR(32),                          -- 住院/门诊
    admission_time      DATE,
    discharge_date      DATE,
    admission_dept      VARCHAR(100),
    discharge_dept      VARCHAR(100),
    length_of_stay      INTEGER,
    payment_method      VARCHAR(100),
    visit_age           NUMERIC(5,1),
    visit_detail_json   JSONB        NOT NULL,                -- inpatient_front_page/medical_history/diagnoses[]/clinical_documents[]
    source_visit_hash   CHAR(64)     NOT NULL,
    created_batch_id    UUID         NOT NULL REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id) ON DELETE CASCADE,
    created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT lnrs_anon_uq_visit_detail UNIQUE (anon_visit_id)
);
```

### 4.2 `lnrs_anon_lab_result`（visit 级检验）

- FK `anon_visit_id` **可空**（visit 缺失时退化为只挂 patient）。
- 幂等键 `(anon_visit_id, source_lab_hash)`，NULL 不参与 UNIQUE 冲突。
- `source_lab_hash = SHA256(center:report_id:item_name)`。

### 4.3 `lnrs_anon_order`（visit 级医嘱，drug+non_drug 合并）

- `order_type` VARCHAR(16)：`drug` / `non_drug`。
- FK `anon_visit_id` 可空。
- 幂等键 `(anon_visit_id, source_order_hash)`，`source_order_hash = SHA256(center:order_time:order_name:order_type)`。

---

## 5. 引擎扩展要点

### 5.1 新增 kind（在 `import_center` dispatch）

| kind | 处理函数 | 说明 |
|---|---|---|
| `visit_detail` | `_import_visit_detail_table` | 自建 visit 桥 + 写富信息 |
| `lab` | `_import_lab_table` | 预读 visit 桥，visit_id join，清洗 1900-01-01 |
| `order` | `_import_order_table` | 参数化 order_type / order_name_field |

### 5.2 pathology 日期反查（`date_lookup_field`）

`_import_exam_text_table` 新增 `date_lookup_field` 参数。当 `date_field=""` 且 `date_lookup_field="visit_id"` 时，按本行 visit_id 反查 `lnrs_anon_visit_detail.admission_time` 作为 exam_date。反查不到的行（visit_id 不存在）打 warning 跳过。

### 5.3 `_clean_date` 通用工具

省医数据用 `1900-01-01` 作时间占位哨兵，`_clean_date()` 将其清洗为 NULL（复用 `birth_date_from` 的多格式解析）。

### 5.4 shengyi spec 处理顺序

```
patient → visit_detail(建桥) → pathology(反查 visit) → imaging(自带日期)
→ ultrasound → surgery → lab → drug_order → no_drug_order
```

visit_detail 先于 pathology/surgery，保证 visit 桥存在。

---

## 6. 执行步骤

### 6.1 前置（一次性）
```bash
cd backend
alembic upgrade head                      # 基础 schema
psql ... -f sql/postgres/0006-anonymized-schema-lnrs.sql   # 匿名表（若未执行）
psql ... -f sql/postgres/0009-shengyi-dict-seed.sql        # 省医医院+字典+枚举
psql ... -f sql/postgres/0010-shengyi-anon-tables.sql      # 省医三张新表
```

### 6.2 数据布局
样例数据放到 `{LNRS_DATA_ROOT}/shengyi/`（当前 `data/shengyi/` 已有旧数据，需用 7-29 新样例覆盖或临时指向 sample 目录）。

### 6.3 验证与导入
```bash
# dry-run 核对文件清单（sample 目录名需为 shengyi）
python -m app.plugin.module_medical.hospital.anon_etl --centers shengyi --data-root <父目录> --dry-run

# 真实导入
python -m app.plugin.module_medical.hospital.anon_etl --centers shengyi
# 或 HTTP 联调
uv run python scripts/anon_e2e_smoke.py --hospital-id <shengyi_id> --data-dir ../docs/demodata/0729_shengyi_sample --centers shengyi --skip-probe
```

### 6.4 行数校验（预期）

| 表 | 预期行数 | 说明 |
|---|---:|---|
| patient | 5 | 5 个 patient_id |
| visit（桥）| 5 | visit_record 5 个 visit_id |
| visit_detail | 5 | 1:1 |
| exam(Pathology) | 3 | 5 行中 2 行 visit_id join 不上被跳过 |
| exam(Radiology) | 5 | imaging_report |
| exam(Ultrasound) | 1 | |
| surgery | 2 | 3 行无 visit_id 被丢弃 |
| lab_result | 5 | |
| order(drug) | 5 | drug_order 10 行中 5 行有 order_name |
| order(non_drug) | 5 | |
| med_dict_unmatched | 0 | 性别/民族全命中 |

> 注：order(drug) 实际行数取决于 `drug_generic_name` 非空行数（10 行中部分可能无名称被跳过）。

---

## 7. 风险与限制

| 项 | 说明 |
|---|---|
| surgery 3 空行丢失 | DDL `lnrs_anon_surgery.anon_visit_id NOT NULL`，visit_id 缺失行无法入库 |
| pathology 2 行跳过 | visit_id `1000837173` 在 visit_record 不存在，反查不到日期 |
| PHI 清洗未真正执行 | body_clean 仅 regex_only 占位（与珠江一致），生产前需人工抽检 |
| 新 kind 偏离纯配置驱动 | lab/order/visit_detail 引入省医专用代码路径，已注释标注，不影响 zhujiang 链路 |
| 1900-01-01 哨兵 | lab.collection_time / order.order_stop_time 已由 _clean_date 清洗 |

---

## 8. 关键设计取舍说明

1. **为什么 visit_detail 自建桥而非依赖 surgery？**
   surgery 反推的 visit 集合是 visit_record 的子集（很多就诊无手术），且 visit_record 历史上被引擎显式跳过。若 visit_detail 依赖 surgery 建桥，则"有就诊无手术"的 visit 会因 FK 缺失写失败。visit_detail 自建桥后，surgery 后跑时 `_batch_upsert_visits` 幂等（冲突只刷 last_seen），不冲突。

2. **为什么 lab/order 的 anon_visit_id 可空？**
   实测 no_drug_order.visit_id 全空、drug_order 半数空且 join 不上 visit_record。若强制 NOT NULL，这些医嘱全部丢失。可空 + 退化为只挂 patient 是数据完整性与 FK 严格性的折中。PG 中 NULL 不参与 UNIQUE 冲突，同 patient 下多条无 visit 的 order 各自独立入库。

3. **为什么 drug_order + no_drug_order 合并一表？**
   两者语义同质（医嘱），字段结构相近，合并后用 order_type 区分可避免重复建表、重复 upsert 逻辑，查询也更统一（如"该患者所有医嘱"）。
