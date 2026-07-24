# ADR 0010: 珠江中心字典驱动 ETL 落地（首例多医院接入）

> 状态：已接受
> 日期：2026-07-24
> 实施：`backend/sql/postgres/0008-zhujiang-dict-seed.sql` + `enum_normalization.py` + `anon_etl_engine.py`

## 背景

ADR 0008 建立了"医疗字典值映射"的框架（`med_dict_mapping` / `med_dict_unmatched` / `sys_dict_data` 数字码），ADR 0006 §343 约定了 `lnrs_anon_*` 表承接 parquet 直入。但框架到首例落地之间还有若干工程缺口：

1. **`med_hospital` 无珠江注册行**——ETL 启动时无法解析 hospital_id。
2. **`med_dict_mapping` 无任何珠江映射规则**——5 个枚举字段全部会落默认值。
3. **`sys_dict_data.med_exam_type` 缺 `Genetic` / `IHC`**——ADR 0006 §343 已约定但种子未灌。
4. **`enum_normalization.py` 未命中时默默返回 None / "0"**——丢失未匹配信号，无法驱动 `med_dict_unmatched` 兜底。
5. **`anon_etl_engine.import_center` 调用 `load_all_enum_mappings(db)` 不传 hospital_id**——多医院 raw_label 互相覆盖。

本 ADR 记录首例珠江中心接入的工程决策与已知遗留问题。

## 决策

### 1. 0008 SQL：前置数据种子（幂等）

新建 `backend/sql/postgres/0008-zhujiang-dict-seed.sql`，包含三部分，全部用 `ON CONFLICT DO NOTHING` / `WHERE NOT EXISTS` 实现幂等：

- **补 `sys_dict_data`**：`med_exam_type` 增加 `Genetic`（基因检测）/ `IHC`（免疫组化），与 ADR 0006 §343 对齐。
- **INSERT `med_hospital`**：`code='zhujiang'`，`tenant_id=1`（PLATFORM_TENANT_ID），`lifecycle_status='mapping_configured'`。
- **INSERT `med_dict_mapping`**：23 行珠江映射规则，通过 `JOIN sys_dict_data` 反查 `dict_data_id`（`med_dict_mapping` 表无 `dict_value` 列，必须反查）。

> **注**：`med_dict_unmatched` 表已由 `initialize.py` 的 `metadata.create_all` 创建，无需在 0008 中重建。

### 2. 默认值矩阵（未命中/空值）

`enum_normalization.py` 为 5 个枚举字段明确默认值，与字典语义对齐：

| 字段 | 默认值 | 含义 | 备注 |
|---|---|---|---|
| `sex` | `'0'` | 未知的性别 | HQMS 0 |
| `ethnicity` | `None` | 不写 | 民族缺失不补默认 |
| `smoking_status` | `'9'` | 未知 | |
| `abo_blood_type` | `'6'` | 未查 | **注意：不是 5=不详** |
| `rh_blood_type` | `'4'` | 未查 | |

> **空值 vs 未命中**：空值（None/空串）视为合法缺失，返回默认值且 `hit=True`（不算未匹配）；未命中返回默认值且 `hit=False`，触发 `med_dict_unmatched` 落库。

### 3. `_with_status` 接口与 unmatched 兜底

新增 `normalize_*_with_status(raw) -> tuple[value, hit]` 五个薄壳，`_import_patient_table` 用此版本攒未匹配标签，导入完成后一次性 `_flush_unmatched`：

- **`_flush_unmatched`** 直接用表级 `pg_insert` + 裸列，绕开 `DictUnmatchedCRUD` 的 auth 依赖；`ON CONFLICT (hospital_id, dict_type_id, raw_label) DO UPDATE` 累加 `occurrence_count`，重置 `status='0'`。

### 4. `_resolve_hospital_id`：不退化策略

`import_center` 启动时调用 `_resolve_hospital_id(db, center_code)`：

- 从 `med_hospital.code` 反查 hospital_id。
- **找不到时抛 `RuntimeError`，不退化到 `PLATFORM_TENANT_ID=1`**——避免误把数据挂到平台租户名下污染其它中心的映射缓存。
- 解析后传给 `load_all_enum_mappings(db, hospital_id=...)`，限定缓存到本中心。

### 5. `_CENTER_PARQUET_SPECS` 扩展注释

在配置字典顶部加注释，明确多医院接入流程与字段含义（src_table / kind / exam_type / id_field / body_fields / detail_type / detail_fields / date_field），新医院只需添加一项配置 + 灌对应 mapping 规则。

## 验证结果（2026-07-24）

珠江 6 个 parquet 导入 `lnrs.lnrs_anon_*`，全部通过：

| 检查项 | 结果 |
|---|---|
| S1: sex CHECK 无字母码 | ✅ `['0','1','2','9']` |
| S2: rh CHECK 含 `'4'` | ✅ |
| patient 行数 | 10（与 parquet 一致） |
| sex / ethnicity / smoking_status | ✅ 全数字码（1/2, 01, 1/2/3） |
| abo / rh（parquet 全 None） | ✅ 默认 `'6'`/`'4'` |
| exam 总数 | 72 = CT(21) + Pathology(25) + Genetic(12) + IHC(14) |
| report_text | 72（与 exam 一致） |
| exam_detail | 72（4 类 detail） |
| visit / surgery | 17 / 47 |
| `med_dict_unmatched` | **0 行**（所有 raw_label 命中映射）✅ |
| patient_meta JSONB | 10/10 行有病史数据 |
| native_place / first_nodule_date / bmi | 10/10 行填充 |

## 已知遗留问题（follow-up）

### IHC 覆盖 Pathology exam_type / detail（✅ 已修复 2026-07-24）

**原现象**：珠江 `ihc_result.parquet` 的 14 个 `specimen_id` 全部在 `pathology_specimen.parquet` 的 39 个中（交集 14/14）。但入库后：

- `lnrs_anon_exam` 中 `exam_type='Pathology'` 只有 25 行（应为 39）
- `lnrs_anon_exam_detail` 中 `detail_type='pathology'` 只有 25 行（应为 39）
- 14 个共享 `specimen_id` 的 exam/detail 全被覆盖成 `IHC`/`ihc`

**原根因**：

1. `_batch_upsert_exams` 的 `ON CONFLICT (center_code, source_exam_hash) DO UPDATE` 会用新值覆盖 `exam_type`——IHC 后处理时把 Pathology 覆盖了。
2. `lnrs_anon_exam_detail` 的 PK 是 `anon_exam_id` 单列（1:1），同一 exam 只能有一个 detail——IHC detail 覆盖了 pathology detail。

**修复（见下方 §"exam_detail 1:N 改造"）**：`lnrs_anon_exam_detail` PK 改为 `(anon_exam_id, detail_type, detail_ordinal)` 实现 1:N；`_batch_upsert_exams` 的 ON CONFLICT 不再覆盖 `exam_type`。修复后 pathology=39 + ihc=14 detail 共存，14 行 ihc detail 全部挂在 Pathology exam 下（符合 ADR-0006 §"IHC 不新增 exam 行"原意）。

### med_hospital 表权限

`med_hospital` 表所有者是 `postgres` 超级用户，`lnrs` 应用账号原仅有 SELECT 权限。本次通过 `GRANT INSERT, UPDATE, DELETE ON lnrs.med_hospital TO lnrs` 解决。生产环境部署时需确保 DDL 脚本执行账号与应用账号的权限授权一致（建议在 initialize.py 流程中统一 GRANT）。

## 实施

- `backend/sql/postgres/0008-zhujiang-dict-seed.sql`（新建）
- `backend/app/plugin/module_medical/hospital/enum_normalization.py`（默认值矩阵 + `_with_status` 接口）
- `backend/app/plugin/module_medical/hospital/anon_etl_engine.py`（`_resolve_hospital_id` + `_flush_unmatched` + `_import_patient_table` 改造 + SPECS 注释）

---

## Rev 2026-07-24（下午）：exam_detail 1:N 改造

### 背景：nodule_no 丢失触发的设计缺陷审视

用户追问"`nodule_imaging.parquet` 中的 `nodule_no` 落在哪张表"，暴露出比 IHC 覆盖 Pathology 更深层的问题：

- `nodule_imaging.parquet` 共 **30 行**，但 distinct `exam_id` 只有 **21 个**——同一 CT exam 下有多个结节（最多 4 个，如 `exam_id=1009188440` 有 n1/n2/n3/n4）。
- 旧 ETL 用 `exam_id` 计算 `anon_exam_id` 后**按 exam 去重**（`seen_exam_anon` 集合），21 个 exam 各写一行 detail，**9 行多结节记录整条丢失**。
- 即使把 `nodule_no` 加进 `detail_fields`，旧 `lnrs_anon_exam_detail` PK 是 `anon_exam_id` 单列（1:1），同一 exam 只能存一个 detail——后写的结节仍会覆盖前一个。

这表明 `lnrs_anon_exam_detail` 的 1:1 PK 设计**同时**导致了三个数据丢失场景：
1. 多结节展开丢失（本节）
2. IHC 覆盖 Pathology（上一节）
3. 任何"同 exam 多结构"场景都受限

### 决策：PK 改为 (anon_exam_id, detail_type, detail_ordinal) 实现 1:N

**DDL 改造**（`0006-anonymized-schema-lnrs.sql` §10d）：

```sql
CREATE TABLE lnrs.lnrs_anon_exam_detail (
    anon_exam_id     VARCHAR(40)  NOT NULL REFERENCES lnrs.lnrs_anon_exam(anon_exam_id) ON DELETE CASCADE,
    detail_type      VARCHAR(32)  NOT NULL,
    detail_ordinal   SMALLINT     NOT NULL DEFAULT 1,   -- 同类型多实例序号
    detail_json      JSONB        NOT NULL,
    created_batch_id UUID         NOT NULL REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id) ON DELETE CASCADE,
    created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT lnrs_anon_pk_exam_detail PRIMARY KEY (anon_exam_id, detail_type, detail_ordinal)
);
```

- `detail_ordinal` 默认 1：无多实例的 detail（pathology/genetic/ihc）单行，向后兼容。
- 同 exam 不同 detail_type 各自独立成行（pathology + ihc 共存）。
- 同 exam 同 detail_type 多实例按 ordinal 区分（n1/n2/n3/n4 → ordinal 1/2/3/4）。

**ORM 改造**（`anon_model.py`）：`AnonExamDetailModel` 加 `detail_ordinal: Mapped[int]`（SmallInteger，复合 PK 第三列）。

**ETL 改造**（`anon_etl_engine.py`）：

1. `_batch_upsert_exams`：ON CONFLICT 不再覆盖 `exam_type`（仅刷新 `last_seen_batch_id` + `exam_date`）——修 IHC 覆盖 Pathology。
2. `_batch_upsert_exam_detail`：ON CONFLICT 改用复合 PK `lnrs_anon_pk_exam_detail`，更新 `detail_json` + `created_batch_id`。
3. `_import_exam_text_table` 新增 `ordinal_field` 参数：
   - 设置后（如 `nodule_imaging` 的 `nodule_no`），**detail 构造移到 `seen_exam_anon` 去重之前**，每行 parquet 生成一条 detail（1:N 展开），`detail_ordinal` 从字段值解析数字（`_parse_ordinal('n1')→1, '结节4'→4`）。
   - 不设置时保持旧行为：同 anon_exam_id 只生成一条 detail（`detail_ordinal=1`）。
4. `_CENTER_PARQUET_SPECS["zhujiang"]["nodule_imaging"]` 配置更新：
   - 加 `ordinal_field: "nodule_no"`
   - `detail_fields` 补 4 个原丢失的标量字段：`nodule_no, nodule_location, long_diameter, density_type`

### 验证结果（改造后）

| 检查项 | 改造前 | 改造后 | parquet 原始 |
|---|---|---|---|
| nodule_imaging detail 行数 | 21（9 行丢失） | **30** ✅ | 30 |
| nodule_imaging max_ordinal | 1 | **4**（n4） ✅ | 4 |
| Pathology detail 行数 | 25（14 行被覆盖） | **39** ✅ | 39 |
| IHC detail 行数 | 14（覆盖了 Pathology） | **14**（与 Pathology 共存） ✅ | 14 |
| Pathology exam 行数 | 25（被 IHC 覆盖） | **39** ✅ | 39 |
| exam 表总数 | 72（含 14 IHC） | **72**（21 CT + 39 Path + 12 Gen） ✅ | — |
| nodule_no 字段落库 | ❌ 丢失 | ✅ 21/21 | — |
| nodule_location 字段落库 | ❌ 丢失 | ✅ 21/21 | — |
| long_diameter 字段落库 | ❌ 丢失 | ✅ 10/21 | — |
| density_type 字段落库 | ❌ 丢失 | ✅ 13/21 | — |

**IHC 挂载正确性**：14 行 ihc detail 全部挂在 Pathology exam 下（共享 specimen_id），符合 ADR-0006 §"IHC 不新增 exam 行（与 pathology 共享 anon_exam_id）"原意。

### 多结节展开样例

`exam_id=1009188440`（珠江某 CT exam）有 4 个结节，改造后展开为 4 行 detail：

```
ANON_EXAM_9f0337959df2  ord=1  nodule_no='n1'  location='右肺下叶背段'
ANON_EXAM_9f0337959df2  ord=2  nodule_no='n2'  location='右肺下叶前基底段'
ANON_EXAM_9f0337959df2  ord=3  nodule_no='n3'  location='左肺上叶尖后段'
ANON_EXAM_9f0337959df2  ord=4  nodule_no='n4'  location='左肺下叶外基底段胸膜下'
```

每行 detail_json 还携带各自的 `nodule_morphology`/`nodule_quantitative`/`follow_up_comparison` 结构。

### 影响

- **DDL 不向后兼容**：`lnrs_anon_exam_detail` PK 变更，需重跑 0006 SQL（DROP+CREATE）。生产升级时需清空该表或写迁移脚本。
- **查询接口需适配**：原本 `JOIN exam_detail ON exam.anon_exam_id = detail.anon_exam_id` 会返回多行，前端/查询需按 `detail_type` + `detail_ordinal` 分组展示。
- **幂等性保持**：ETL 可重复执行，ON CONFLICT 按 (anon_exam_id, detail_type, detail_ordinal) 幂等更新。

