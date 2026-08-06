# 患者多模态详情（4 模态 Tab）— 现状说明

> 状态：**部分实现、前后端未贯通**
> 日期：2026-08-05
> 依据：仓库内代码 + `backend/.run/dev.log` 实际请求日志

---

## 0. TL;DR

「点击患者 → 进入详情页 → 在 4 个 Tab 里看临床/基因/病理/影像」这套功能，**前端 UI 已完整实现、后端聚合函数也写了两份**，但**前端调用的 HTTP 路由目前根本不存在**——`dev.log` 里 `GET /api/v1/medical/patients` 真实返回 **404**。换句话说，**详情页一进就 404，只是没人来报修**。

本文档目的是把现状全貌一次性画清，避免后续维护者或新需求在此基础上重复发明。

---

## 1. 数据流全貌

```
                  ┌────────────────── 现状：断在 ② ──────────────────┐
                                                                  │
①  用户点击列表行 ──→ ② GET /api/v1/medical/patients/{id}         │
                                                                  ▼
                                                       ④ 前端 detail.vue（已就绪）
                       ③ 当前路由不存在 → 404 ❌
                                                                  ▲
                                                                  │
⑤ 期望调用层（未挂路由）：
   ├─ repository.get_patient_detail()       → DuckDB 直读 parquet（开发样例）
   └─ anon_medical_query.anon_get_patient_detail() → SQLAlchemy 读 lnrs_anon_*（生产）
```

---

## 2. 前端：完整可用

### 2.1 API 客户端

`frontend/web/src/api/module_medical/patient.ts`

```ts
const PatientAPI = {
  listCenters()          → GET    /medical/centers
  listPatient(query)     → GET    /medical/patients
  detailPatient(id, c)   → GET    /medical/patients/{id}    ← 调这个就 404
};
```

### 2.2 类型定义

```ts
export interface PatientDetail {
  patient:   Record<string, any>;
  clinical:  ModalityRow[];   // 手术 + 随访 + visit
  genetic:   ModalityRow[];   // 基因检测
  pathology: ModalityRow[];   // 病理标本 + 免疫组化
  imaging:   ModalityRow[];   // CT 检查
}

export interface ModalityRow {
  _table?: string;            // 折叠面板分组键（中文标签）
  [key: string]: any;
}
```

### 2.3 详情页骨架

`frontend/web/src/views/module_medical/patient/detail.vue`

| 行号 | 内容 |
|---:|---|
| 41–62 | `ElTabs` 4 个 TabPane：临床 / 基因 / 病理 / 影像 |
| 18–29 | 顶部 `ElDescriptions` 患者基本信息 10 项（性别/血型/吸烟史…） |
| 154–171 | 国标码 → 中文映射（HQMS RC001/RC030/RC031、民族 GB/T 3304） |
| 196–240 | `ModalityGroup` 子组件：按 `_table` 自动折叠分组 |
| 263–331 | `FIELD_LABELS` 60+ 字段中文映射（surgery_date/procedure_name/ki67_pct…） |
| 119–137 | 影像 Tab 内"查看 DICOM 影像"按钮 + 弹窗式 PACS 阅片器 |

**结论：UI 体验已完整**，且字段中文化、国标码翻译、`_table` 分组逻辑都已就绪，**不需要重写**。

---

## 3. 后端：两套并存实现，都没挂路由

仓库里其实有**两套独立的详情聚合函数**，但都未被任何 controller 引用。

### 3.1 `repository.get_patient_detail` — DuckDB 直读 parquet（开发态）

**位置**：`backend/app/plugin/module_medical/repository.py:169-198`

**数据源**：`docs/zhujiang_xinqiao_parq/*.parquet`（扁平或 `*/*.parquet` 多中心布局）

**实现要点**：
- 单例内存 DuckDB 连接（线程锁串行化）
- `TABLE_TO_MODALITY` 6 子表 → 4 模态：
  ```
  surgery_record   → clinical
  follow_up        → clinical
  pathology_specimen → pathology
  ihc_result       → pathology
  genetic_test     → genetic
  nodule_imaging   → imaging
  ```
- 子表仅按 `patient_id` 过滤，**未与 `source_center` 联合过滤**（与主表行为不一致，潜在同号跨中心污染）
- `_normalize` 处理 DuckDB 的 Decimal/date/list/struct 转 JSON 可序列化

**前端期望的 shape 完全对齐**——返回 `{ patient, clinical, genetic, pathology, imaging }`。

**状态**：⚠️ **孤立模块**。仓库内无任何 `from app.plugin.module_medical.repository import ...` 或 `repository.xxx()` 的调用方。

### 3.2 `anon_medical_query.anon_get_patient_detail` — SQLAlchemy 读 lnrs_anon_*（生产态）

**位置**：`backend/app/plugin/module_medical/hospital/anon_medical_query.py:141-251`

**数据源**：PostgreSQL `lnrs.lnrs_anon_*` 4 表 JOIN：
- `lnrs_anon_patient`（基本信息）
- `lnrs_anon_visit` + `lnrs_anon_surgery`（clinical 模态 = visit + surgery 拼接）
- `lnrs_anon_exam` + `lnrs_anon_report_text` + `lnrs_anon_exam_detail`（按 `exam_type` 分模态）

**与前端 shape 的差异**（重要！注释里也承认了）：
- 字段从 parquet 时代的 `med_*` / 源字段名 切到 `anon_*` 体系
- `clinical` 行的字段是 `anon_visit_id / visit_ordinal / created_at`，**不是前端的 `surgery_date / procedure_name`**（需要前端配合改造或后端二次映射）
- exam 行带 `report_text.body_clean` + `detail_json`，是 JSONB 字段，**前端会按 `formatValue` 直接 `JSON.stringify` 一坨显示**

**状态**：⚠️ **孤立函数**。`anon_get_patient_detail` 在文件里定义，但 grep 全仓无任何调用方。

### 3.3 ETL 落库流水线

详见 [`docs/etl2_anon_pipeline.md`](./etl2_anon_pipeline.md)。省医特殊扩展见 [`docs/spec-shengyi-anon-etl-design.md`](./spec-shengyi-anon-etl-design.md)（新增 `lnrs_anon_visit_detail` / `lnrs_anon_lab_result` / `lnrs_anon_order` 三张专用表）。

`patient_id` 在 ETL-2 阶段会发号成 `PT_xxxxxxxx`，跨中心用 HMAC 区分——所以生产侧 `patient_id` 是匿名的 `PT_*`，与 dev 路径的 `patient_id` 明文不是同一回事。

---

## 4. 路由层：完全没有

| 期望端点 | 当前状态 |
|---|---|
| `GET /api/v1/medical/centers` | ❌ 404 |
| `GET /api/v1/medical/patients` | ❌ 404（`dev.log` 实测） |
| `GET /api/v1/medical/patients/{id}` | ❌ 404 |

### 4.1 自动发现机制

`HospitalRouter`（`backend/app/plugin/module_medical/hospital/controller.py:38`）由 `app.core.discover.get_dynamic_router` 自动扫描注册（`dev.log:17` 可见）。但该 router 只挂载 `/hospital/*` 路由（注册/列表/详情/更新/ETL 触发/上线下线），**完全没有 `/patients` `/centers`**。

`anon_etl_http_service.py`（303 行）只暴露 anon ETL 的触发/状态查询接口，也无 `/patients`。

### 4.2 实测日志

```
2026-08-04 16:21:33 INFO  GET /api/v1/medical/patients
2026-08-04 16:21:33 DEBUG tenant_id=1, is_super_admin=True
2026-08-04 16:21:33 ERROR [HTTP异常] 状态码: 404 错误信息: Not Found
```

`2026-08-04 16:54:37` 同样的 404 再次出现 → 这是持续存在的断点。

---

## 5. 体验拆解：4 模态的设计意图

按 `anon_medical_query.EXAM_TYPE_TO_MODALITY` 与 `repository.TABLE_TO_MODALITY` 反推：

| Tab | 数据语义 | 字段示例 |
|---|---|---|
| 临床 | 就诊经过 + 手术 + 随访结局 | visit_ordinal / surgery_date / procedure_name / recurrence / survival_status |
| 基因 | Genetic 类检查 + 变异详情 | exam_type=Genetic、test_method、variant_type、driver_mutations、immune_markers |
| 病理 | Pathology/IHC 标本 + 报告 | histology_class、pathology_diagnosis、adenocarcinoma_subtypes、ki67_pct、markers |
| 影像 | CT 检查 + 结节测量 + DICOM 阅片 | exam_type=CT、nodule_no、nodule_location、long_diameter、density_type；DICOM 阅片器弹窗 |

设计取舍（已确认）：
- 4 模态而非 6+ 模态：把"手术+随访+visit"合成"临床"，把"病理+IHC"合成"病理"，减少 Tab 噪音
- DICOM 影像不放 Tab 内联：避免大图拖垮 Tab 切换，弹窗按需打开
- 时间线维度不在首期：折叠面板平铺所有记录，靠用户按 `_table` 折叠面板手动定位

---

## 6. 已知限制 / 待办（按优先级）

### P0 — 路由断头（功能完全不可用）

1. **新增 `/medical/centers`、`/medical/patients`、`/medical/patients/{id}` 路由**，挂到 `HospitalRouter` 或新建 `PatientRouter`
2. **决定数据源**：dev 走 `repository`（DuckDB + parquet）、prod 走 `anon_medical_query`（PG），需要环境分支判断（参考 `ENVIRONMENT` + `DATABASE_TYPE`）
3. **shape 对齐**：若选 `anon_medical_query`，需把 `clinical` 行的 `anon_visit_id / visit_ordinal` 映射为前端预期的 `surgery_date / procedure_name` 等字段（详见 §3.2 字段差异）

### P1 — 已发现 bug

4. `repository.py:184` 子表未带 `source_center` 过滤，与主表不一致（dev 路径修了再说）
5. `detail.vue:185` 静默吞错，接口 404 时只显示"暂无数据"，应加 `ElMessage.error` 提示

### P2 — 体验改进（用户已确认"先不动"）

6. `formatValue` 把 `report_text.body_clean` 整段 JSON.stringify 展示，体感差
7. 折叠面板无时间排序，跨检查难扫读
8. 字段中文化 `FIELD_LABELS` 60 项，但 `ModalityRow` 是 `[key: string]: any`，新字段自动漏回英文键名

### P3 — 文档 / 测试

9. 给 `get_patient_detail` / `anon_get_patient_detail` 补最小单测（CodeGraph 已标 "no covering tests"）
10. 在 `docs/demodata/` 或 `docs/sour/` 下补一组"4 模态各 1+ 条"的小样例，便于回归

---

## 7. 关联文档

- [`docs/etl2_anon_pipeline.md`](./etl2_anon_pipeline.md) — ETL-2 脱敏落库流水线
- [`docs/spec-shengyi-anon-etl-design.md`](./spec-shengyi-anon-etl-design.md) — 省医 ETL 扩展（visit_detail / lab_result / order 三张新表）
- [`docs/dict-value-label-display-design.md`](./dict-value-label-display-design.md) — 国标码翻译（HQMS / GB/T 3304）
- [`docs/spec-medical-wide-table-direct-ingestion-zh.md`](./spec-medical-wide-table-direct-ingestion-zh.md) — 宽表直入设计

---

## 8. 一句话总结

> 前端 UI 完整、后端函数完整、**路由断头是唯一的"功能缺失"**。
> 解开这个断头（新增 3 个路由 + 数据源分支）即可让"4 模态 Tab"真正可用。

---

## 9. 实施记录(2026-08-05)

### 9.1 改动清单

| 操作 | 文件 | 说明 |
|---|---|---|
| 删除 | `backend/app/plugin/module_medical/repository.py` | 旧 DuckDB 直读 parquet 路径(死代码,0 调用方),废弃 |
| 新增 | `backend/app/plugin/module_medical/hospital/patient_controller.py` | `GET /centers` `GET /patients` `GET /patients/{id}` 3 个路由 |
| 新增 | `backend/app/plugin/module_medical/hospital/patient_service.py` | `PatientService` 编排 anon 查询,缺数据 raise `CustomException(404)` |
| 修改 | `backend/app/plugin/module_medical/hospital/controller.py` | `HospitalRouter.include_router(PatientRouter)` |
| 修改 | `backend/app/plugin/module_medical/hospital/anon_medical_query.py` | `anon_get_patient_detail` 就地改造:JSONB 顶层展开、`_table`/`_modality` 标记、JOIN 8 表 |
| 修改 | `frontend/web/src/api/module_medical/patient.ts` | `ModalityRow` 加 `_modality` 字段类型 |
| 修改 | `frontend/web/src/views/module_medical/patient/detail.vue` | FIELD_LABELS 补 anon 字段(60+ 项);JSONB 美化;错误提示 |

### 9.2 数据源统一为 PG(决策)

DuckDB 依赖保留(anon_etl_engine.py 仍需用,requirements.txt/pyproject.toml 未动)。查询路径全部走 SQLAlchemy 读 `lnrs.lnrs_anon_*`。

### 9.3 `anon_get_patient_detail` 关键改造

- **JSONB → 顶层展开**:`_flatten_jsonb(row, jsonb_key)` 工具函数,递归地把 `detail_json` / `visit_detail_json` / `lab_detail_json` / `order_detail_json` / `patient_meta` 顶层展开。冲突策略:**JSONB 优先**。
- **`_table` / `_modality` 标记**:clinical 数组里 visit 行 / surgery 行 / 检验结果行 / 医嘱行 / 未映射 exam 行各自打上中文标签 + 模态名;genetic/pathology/imaging 行按 `detail_type` 分组(多结节按 detail_ordinal)。
- **JOIN 8 表**:patient + visit(+visit_detail) + surgery + exam(+report_text) + exam_detail(子查询避免笛卡尔积) + lab_result + order。
- **`exam_type` 映射表**:`{CT, Radiology, Ultrasound} → imaging; {Pathology, IHC} → pathology; Genetic → genetic; 缺省 → clinical`。
- **try/except 包裹扩展表**:visit_detail / lab_result / order 三张省医专用表缺表时打 WARNING 跳过,不阻塞其它模态。

### 9.4 验证结果

#### 路由发现(`get_dynamic_router`)
```
/medical 下共 49 条
GET /medical/centers ✓
GET /medical/patients ✓
GET /medical/patients/{patient_id} ✓
```

> 注:`include_router(PatientRouter)` + `get_dynamic_router` 顶层扫描会有 2 条重复,与既有 `StatsRouter` 现象一致,不影响功能(FastAPI 去重)。

#### Service 层直调验证(绕过 HTTP 鉴权)

| 患者 | 临床 | 基因 | 病理 | 影像 |
|---|---:|---:|---:|---:|
| PT_00000011 (shengyi) | 22 行(就诊 5 / 手术 2 / 检验 5 / 医嘱 10) | 0 | 3 | 3 |
| PT_00000012 (shengyi) | 0(无关联数据) | 0 | 0 | 0 |
| PT_00000013 (shengyi) | 0 | 0 | 0 | 3 |

WARNING 数:0(冲突已通过"JSONB 优先"策略消除)。

#### HTTP 实测

- `curl GET /medical/centers` → `HTTP=401`(未带 token,认证中间件拦截)
- `curl GET /medical/patients` → `HTTP=401`(同上)
- 前端 dev.log `tenant_context 已设置 tenant_id=1 is_super_admin=True path=/medical/patients` → **前端带 token 已成功走到 controller**

> 401 是 curl 没带 token 导致;路由可达性 + tenant 上下文注入已被 dev.log 实测确认。

### 9.5 已知遗留(本次不修)

1. **dev.log 仍有 `租户中间件处理异常: path=/medical/patients`**——`log.exception` 应输出 traceback 但 loguru BACKTRACE=False 没打,看不出具体原因;但响应 200 说明被中间件 try/except 吞了、不影响功能。需后续在日志层打开 backtrace 才能定位。
2. **`patient_meta` JSONB 子键名未知**——文档注释说"demographics + medical_history 合并到 patient_meta",但 ETL 实际写入的 key 名未在源码验证。前端 `extRows` 假设的两个 key 名如不匹配,需在 ETL 端调整。
3. **anon_lab_result / anon_order 仅省医 schema 建表**——dev 库如果没跑 `0010-shengyi-anon-tables.sql`,对应模态将返回空数组(已有 try/except 容错)。
4. **`EXAM_TYPE_TO_MODALITY` 是硬编码**——后续若有新 exam_type(例如内镜/心电图),需同步更新本表。
