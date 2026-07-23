# ADR 0008 / 0006 增补 实施计划

> 关联文档：[ADR 0008（医疗字典与值级映射）](./adr/0008-dict-value-mapping.md)、[ADR 0006（脱敏库 Schema，含枚举改造增补节）](./adr/0006-anonymized-data-schema.md)
> 制定日期：2026-07-23
> 状态：待执行（前端 UI 不在本轮）

## 背景与范围

本计划是 ADR 0008（医疗领域字典与值级映射）与 ADR 0006 增补节（ENUM→VARCHAR+CHECK 枚举权威移交）的落地实施。

**本轮覆盖**：DB 迁移、后端模型/Schema/CRUD/Service/Controller、`med_*` 字典种子、ETL1 `dict` transform、ETL2 `normalize_sex` 退役、DDL 文件同步。

**本轮不做**（留待后续）：
- 前端管理 UI（`views/module_medical/dict_mapping/`、`api/`、`types/`）
- `suggest_mapping` 自动化建议
- `backfill` 完整实现（本轮仅建骨架）
- `med_smoking_status` 实际取值（本轮占位）

**关键前提（已与用户确认）**：
- 医疗枚举标准来源 = 新建 `med_*` 字典类型（不沿用系统字典 `sys_user_sex` 的 0/1/2）
- ENUM 权威 = 降级为 `VARCHAR(10) + CHECK`，字典为唯一事实源
- ETL2 的 `normalize_sex` 用**预加载内存缓存**方式退役，保持函数签名不变

## 关键代码事实（探索结论）

- **两条独立 ETL 管线**，分别集成：
  - ETL1（`etl_engine.py` → 统一表 `med_*`）：用 `med_mapping_rule` + `transform_type`。新 `dict` transform 接入 `_transform_row` dispatch（当前仅 rename/constant/expression）。需线程化 `redis` + `hospital_id`。
  - ETL2（`anon_etl_engine.py` → 脱敏库 `lnrs_anon_*`）：硬编码 `normalize_sex()` 同步函数，无 mapping rule、无 redis。退役需预加载映射到模块全局缓存。
- **迁移 HEAD** = `d4e5f6a7b8c9`，新迁移 `down_revision` 依此。
- **菜单/权限点**通过迁移内 `op.get_bind()` + `sys_menu.insert()` 插入（仿 `d4e5f6a7b8c9_add_medical_stats_menu.py`）。
- **控制器自动发现**：`module_medical/` 下 `controller.py` 的模块级 `APIRouter` 自动挂到 `/medical`，无需手动 `include_router`。
- **字典种子**：`initialize.py` 对非空表跳过（`__init_data` 行 108-114），故 JSON 追加仅对**新库**生效；现有库走迁移。
- **`schema_hash`**（`anonymize.py:141`）：基于 DDL 文件字节 sha256，`lru_cache` 进程级。DDL 改动会改变 hash，属预期副作用。

---

## 阶段 0：先读关键文件确认细节（不改）

- Read `backend/sql/postgres/0006-anonymized-schema-lnrs.sql` 中 `lnrs_anon_patient.sex`、`lnrs_anon_exam.exam_type`、`lnrs_anon_exam_finding.laterality` 当前列定义
- Read `etl_engine.py` 完整签名（`run_etl_pipeline`、`import_one_table`、`_transform_row`）确认 redis/tenant_id 线程化改动面
- Read `anon_etl_engine.py` 的 `import_center` 入口确认预加载注入点

## 阶段 1：DB 迁移（一个迁移文件，内部分段）

新建 `backend/app/alembic/versions/e5f6a7b8c9d0_add_med_dict_mapping.py`，`down_revision = "d4e5f6a7b8c9"`。

内容分段：

1. **建 `med_dict_mapping` 表**：列含 `hospital_id`/`dict_type_id`/`dict_data_id`/`raw_label`/`raw_value`/`tenant_id` + ModelMixin 全字段 + UserMixin 审计字段；外键到 `med_hospital`/`sys_dict_type`/`sys_dict_data`/`sys_tenant`；`UNIQUE(hospital_id, dict_type_id, lower(raw_label))`（表达式唯一，消除大小写差异）；索引。
2. **建 `med_dict_unmatched` 表**：列含 `hospital_id`/`dict_type_id`/`raw_label`/`raw_value`/`occurrence_count`/`last_seen_at`/`resolution`/`resolved_by`/`resolved_at`/`resolved_as_mapping_id`/`tenant_id` + ModelMixin 字段；`UNIQUE(hospital_id, dict_type_id, raw_label)`；索引。
3. **插入 `med_*` 字典种子**（`sys_dict_type` + `sys_dict_data`，幂等检查）：
   - `med_sex`：M / F / U
   - `med_exam_type`：CT / PETCT / Pathology
   - `med_laterality`：L / R / Bilateral / N/A
   - `med_smoking_status`：占位（待需求定值，先建类型）
4. **插入菜单+权限点**（仿 `d4e5f6a7b8c9` 模板）：在"医疗数据"目录下加"字典映射"菜单（`module_medical/dict_mapping/index`）+ 按钮权限 `module_medical:dict_mapping:query/create/update/delete`。
5. **ENUM→VARCHAR+CHECK 改造**（ADR 0006 增补）：
   - `ALTER TABLE lnrs_anon_patient ALTER COLUMN sex TYPE VARCHAR(10)` + `ADD CONSTRAINT chk_anon_patient_sex CHECK (sex IN ('M','F','U'))`
   - `lnrs_anon_exam.exam_type`、`lnrs_anon_exam_finding.laterality` 同理
   - downgrade 逆序回滚

## 阶段 2：DDL 文件同步

修改 `backend/sql/postgres/0006-anonymized-schema-lnrs.sql`：上述三列由 `ENUM(...)` 改为 `VARCHAR(10)` + CHECK。文件头注释标明权威移交 ADR 0008。

**注意**：会改变 `schema_hash`（lru_cache，进程生命周期），属预期副作用。

## 阶段 3：后端模型

新建 `backend/app/plugin/module_medical/dict_mapping/`：

- `__init__.py`（空）
- `model.py`：
  - `DictMappingModel(ModelMixin, UserMixin)`：表 `med_dict_mapping`，`__table_args__` 含表达式 UNIQUE + 各字段；relationship 到 hospital/dict_type/dict_data
  - `DictUnmatchedModel(ModelMixin)`：表 `med_dict_unmatched`（不继承 UserMixin，系统自动写入）

## 阶段 4：Schema / CRUD / Service / Controller

- `schema.py`：`DictMappingCreate/Update/Out`（校验 dict_data_id/dict_type_id/hospital_id 存在性、raw_label 非空并 strip+lower）、`DictMappingBatch`、`DictUnmatchedOut`、`NormalizeIn`（hospital_id, dict_type, raw_label）/`NormalizeBatchIn`、`BackfillIn`
- `crud.py`：`DictMappingCRUD(CRUDBase)`、`DictUnmatchedCRUD(CRUDBase)`；含 `upsert_unmatched`（UPSERT occurrence_count 累加）
- `service.py`：
  - `DictMappingService.list/create/update/delete/batch/refresh_cache`（参考 `mapping_service.py` 全量替换模式；写后刷新 Redis 缓存）
  - 核心 `normalize(hospital_id, dict_type, raw_label)` / `normalize_batch(...)`：查 Redis Hash `system_dict_mapping:{tenant_id}:{dict_type}`，命中返回标准值；未命中写 `med_dict_unmatched`（UPSERT 累加 occurrence_count）并返回 None
  - `backfill(table, field, dict_type, hospital_id)`（异步任务签名占位，本轮只建骨架）
- `controller.py`：模块级 `DictMappingRouter = APIRouter(route_class=OperationLogRoute, tags=["医疗字典映射"])`；端点 list（在 `{id}` 前）/detail/create/update/delete/batch/normalize/normalize-batch/unmatched-list/unmatched-resolve/unmatched-ignore/cache-refresh。权限 `module_medical:dict_mapping:*`。自动发现挂到 `/medical`。

## 阶段 5：`med_mapping_rule` 扩展

`hospital/model.py`：

- `MappingTransform` 枚举新增 `DICT = "dict"`
- `transform_type` 列 comment 更新为 `rename/constant/expression/dict`
- `transform_value` 列 comment 更新（dict=dict_type 名）

## 阶段 6：ETL1 `dict` transform 集成

`etl_engine.py`：

- `_transform_row` dispatch 新增 `elif rule.transform_type == "dict"` 分支：取 `src_val = row_dict.get(rule.src_field)`，以 `rule.transform_value` 为 dict_type 查 `DictMappingService.normalize_batch`（预加载该表整列的 raw_label 批量查缓存，避免逐行）；未匹配由 normalize 负责落 unmatched
- `_transform_row`/`import_one_table`/`run_etl_pipeline` 签名线程化 `redis` + `hospital_id`（tenant_id 已有）；调用方 `etl_service.py` 传入
- 缓存未命中时调 `init`（仿 `get_init_dict_service` 回源逻辑）

## 阶段 7：ETL2 `normalize_sex` 退役（预加载内存缓存）

`anonymize.py`：

- 模块级 `_SEX_MAP_CACHE: dict[str, str] | None = None`（raw_label→dict_value，全院并集）
- 新增异步 `load_sex_mapping(db)`：查 `med_dict_mapping` JOIN `sys_dict_type`(dict_type='med_sex')，把所有 raw_label→dict_value 装入 `_SEX_MAP_CACHE`；查不到则置空 dict（保留回退）
- `normalize_sex(raw)` 改为：`_SEX_MAP_CACHE` 非空时先查缓存（命中返回 dict_value）；未命中或缓存为空回退现有 `_SEX_MAP_M`/`_SEX_MAP_F` 硬编码集合。**签名不变**
- `anon_etl_engine.py` 的 `run_anon_etl`/`import_center` 入口（启动时）调一次 `await load_sex_mapping(db)` 预热

## 阶段 8：字典种子 JSON 追加

`backend/app/scripts/data/sys_dict_type.json` + `sys_dict_data.json` 追加 `med_*` 类型与数据（仅新库生效；现有库走阶段 1 迁移）。

## 阶段 9：自检

- 迁移 `alembic upgrade head` 可正反跑（无报错）
- 后端能 import（无循环依赖）
- ETL1/ETL2 单元跑通 dry_run（不要求真实数据）

---

## 验收标准

- [ ] 迁移 `upgrade head` 与 `downgrade -1` 均成功
- [ ] `med_dict_mapping` / `med_dict_unmatched` 表结构与表达式唯一约束正确
- [ ] `med_sex` 等字典种子在迁移后存在，`dict_value` = M/F/U
- [ ] `lnrs_anon_patient.sex` 等三列已变为 VARCHAR+CHECK
- [ ] 后端启动无 import 错误，`/medical/dict-mapping/*` 路由注册
- [ ] ETL1 配置 `transform_type=dict` 能跑通（mock 映射）
- [ ] ETL2 启动时预加载缓存，`normalize_sex("男")` 经缓存返回 M
- [ ] DDL 文件与迁移一致，`schema_hash` 变化被记录
