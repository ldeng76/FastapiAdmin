# ADR 0008: 医疗领域字典与值级映射（多标签归一化）

> 状态：已接受（已修订·2026-07-23）
> 日期：2026-07-23

## 背景

本项目收集多家医院的数据并统一管理。不同医院对同一概念使用不同的标签值：

- 性别字段：省医存"男"/"女"，华山存"Male"/"Female"，有的存"M"/"F"
- 吸烟状态：有的用"是"/"否"，有的用"吸烟"/"不吸烟"，有的用"Current"/"Never"/"Former"

统一表与脱敏库都需要将这些异构值归一化到统一标准，以便跨医院统计与建模。

### 现状（修订重点）

审核发现，**医疗模块（`module_medical`）此前从未使用 `sys_dict_data`/`sys_dict_type`**。`sys_dict` 是 RuoYi 模板遗留的"系统管理字典"，种子数据全是后台运营枚举（`sys_user_sex`、`sys_yes_no`、`sys_notice_type`、`sys_oper_type`、`sys_job_*`……），消费者是前端用户/通知/任务管理页，**没有一条医疗领域字典**。

医疗数据的值归一化目前由**硬编码 Python 函数**承担，典型例子 `anonymize.py:169`：

```python
_SEX_MAP_M = {"男", "男性", "m", "M", "male", "Male"}
_SEX_MAP_F = {"女", "女性", "f", "F", "female", "Female"}
def normalize_sex(raw) -> str: ...   # → 'M' / 'F' / 'U'
```

ADR 0006 的脱敏库 `lnrs_anon_patient.sex` 是 `ENUM('M','F','U')`，因此该函数产出的 **M/F/U** 才是既定的医疗性别标准值，而 `sys_dict_data.sys_user_sex` 的 `"0"/"1"/"2"` 是系统用户管理用的另一套序号约定。

> **范畴澄清**：`sys_user_sex`（系统账号的性别下拉框）与医疗患者的性别是两个同名但无关的概念。拿它去承载医疗数据是范畴错误，就像用"通知类型"去存"病理类型"。

本 ADR 的目标：用**可配置的字典映射**取代/下沉这些硬编码归一化逻辑，让新医院接入时无需改代码。

## 候选方案

### 甲. 复用系统字典（医疗沿用 0/1/2）

医疗数据走 `sys_user_sex`（0/1/2），写入 ENUM 列时再转一次 0→M。

**否决**：要么倒退 ADR 0006 的领域标准（ENUM 改 0/1/2，偏离 HL7/FHIR/DICOM），要么 ETL 多一层无意义的 0↔M 转换；研究员拿到的 0/1/2 也无法直接对接领域标准。

### 乙. 新建医疗字典 + dict_value/存储值分离

在 `sys_dict_data` 新增 `storage_value` 列，`dict_value` 保留为显示码。

**否决**：过度设计。ADR 0006 已用 M/F/U 兼任存储值与语义码，再拆一层无收益，反而引入"哪个列才是真的"的混乱。

### 丙. 新建医疗字典，dict_value 对齐 ADR 0006（采用）

在 `sys_dict_data` 新增 `med_*` 医疗领域字典类型，`dict_value` 直接取 ADR 0006 定义的标准值（M/F/U 等），独立于系统字典。新增映射表 `med_dict_mapping` 承载"医院原始标签 → 标准值"。

## 决策

采用丙。下面分四点展开。

### 决策 1：铁则 —— `dict_value` = DB 列的实际存储值

没有"显示码 vs 存储码"之分。`dict_value` 就是该字段在数据库列里存的值。这条原则作为后续所有医疗字典的设计前提：

- `med_sex` 的 `dict_value` 是 `M`/`F`/`U`（对齐 `lnrs_anon_patient.sex`）
- 任何走字典归一化的列，其存储值 = `dict_value`

由此统一表 `med_patient.gender`（VARCHAR）与脱敏库 `lnrs_anon_patient.sex` 共享同一标准值，天然可 JOIN。

### 决策 2：新建医疗领域字典类型（`med_*`）

首批种子对齐 ADR 0006 已用到的枚举：

| dict_type | dict_name | 取值（dict_value） | 对应存储列 |
|-----------|-----------|-------------------|-----------|
| `med_sex` | 医疗·性别 | `M` / `F` / `U` | `lnrs_anon_patient.sex`、`med_patient.gender` |
| `med_smoking_status` | 医疗·吸烟状态 | 待定 | `med_patient.smoking_status` |
| `med_exam_type` | 医疗·检查类型 | `CT` / `PETCT` / `Pathology` … | `lnrs_anon_exam.exam_type` |
| `med_laterality` | 医疗·侧别 | `L` / `R` / `Bilateral` / `N/A` | `lnrs_anon_exam_finding.laterality` |

**不碰** `sys_user_sex` 等系统字典。

### 决策 3：枚举权威移交 —— ENUM 降级为 VARCHAR+CHECK

ADR 0006 中各 `ENUM(...)` 列（`sex`、`laterality`、`exam_type` 等）改造为 `VARCHAR(10) + CHECK`，**字典成为唯一事实源**。

- 将来新增枚举值无需 DDL 变更（加一条 `sys_dict_data` 即可）
- CHECK 取值来自对应 `med_*` 字典的 `dict_value`，提供应用层之外的第二道护栏
- 代价：失去 DB 层 ENUM 的强类型保证（CHECK 可被禁用，ENUM 不能），写入前必须查字典

详见 [ADR 0006 增补节](./0006-anonymized-data-schema.md#枚举列改造2026-07-23-增补)。

### 决策 4：映射表 + 字段路由分工

#### 4.1 值映射表 `med_dict_mapping`

```sql
CREATE TABLE med_dict_mapping (
    id              SERIAL PRIMARY KEY,
    uuid            VARCHAR(64) NOT NULL UNIQUE,
    hospital_id     INTEGER NOT NULL REFERENCES med_hospital(id) ON DELETE CASCADE,
    dict_type_id    INTEGER NOT NULL REFERENCES sys_dict_type(id) ON DELETE CASCADE,
    dict_data_id    INTEGER NOT NULL REFERENCES sys_dict_data(id) ON DELETE CASCADE,
    raw_label       VARCHAR(255) NOT NULL COMMENT '医院原始标签（如"男性"/"Male"/"M"）',
    raw_value       VARCHAR(255) COMMENT '医院原始值（如"M"/"1"）',
    status          VARCHAR(10) NOT NULL DEFAULT '0',
    description     TEXT,
    tenant_id       INTEGER NOT NULL DEFAULT 1 REFERENCES sys_tenant(id),
    created_time    TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_time    TIMESTAMP NOT NULL DEFAULT NOW(),
    is_deleted      BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_time    TIMESTAMP,
    -- 归一化后的唯一约束：入库前 raw_label 须 lower()+trim()
    CONSTRAINT uq_med_dict_mapping UNIQUE (hospital_id, dict_type_id, lower(raw_label))
);
CREATE INDEX ix_med_dict_mapping_lookup ON med_dict_mapping(hospital_id, dict_type_id);
```

**唯一约束说明**：用 `lower(raw_label)` 表达式唯一约束消除大小写/空白差异（`"Male"`≡`"male"`），ETL 写入前再 `trim()`。否则 `"Male"`/`"male"`/`"男性 "` 会被当成三条映射。

**唯一约束粒度**：同一医院同一 dict_type 下，一条原始标签只映射到一个标准值（多对一靠多家医院各自的行实现，不靠单行多值）。

#### 4.2 字段路由 —— 复用 `med_mapping_rule`，新增 transform 类型

"哪张表的哪个字段走哪个 dict_type"由 [ADR 0002](./0002-schema-mapping-management.md) 的 `med_mapping_rule` 承载，新增一种 `transform_type`：

| transform_type | 用途 | transform_value | 适用场景 |
|----------------|------|-----------------|---------|
| `rename` | 字段重命名 | 空 | 字段对齐 |
| `constant` | 常量填充 | 常量值 | 固定值字段 |
| `expression` | 调注册 Python 函数 | 函数 key | **复杂逻辑**（正则、JSON 解析、多字段联动） |
| `dict`（新增） | 应用该院 dict_mapping | dict_type 名（如 `med_sex`） | **需后台 UI 配置的简单枚举映射** |

`expression` 与 `dict` 的分工边界：能枚举的、运营要改的走 `dict`；写死在代码里更稳的复杂变换走 `expression`。`normalize_sex` 退役后，`med_patient.gender` 的映射规则即为 `transform_type='dict', transform_value='med_sex'`。

#### 4.3 未匹配队列表 `med_dict_unmatched`

ETL 遇到无映射的原始标签时记录于此，触发人工干预：

```sql
CREATE TABLE med_dict_unmatched (
    id              SERIAL PRIMARY KEY,
    uuid            VARCHAR(64) NOT NULL UNIQUE,
    hospital_id     INTEGER NOT NULL REFERENCES med_hospital(id) ON DELETE CASCADE,
    dict_type_id    INTEGER NOT NULL REFERENCES sys_dict_type(id) ON DELETE CASCADE,
    raw_label       VARCHAR(255) NOT NULL,
    raw_value       VARCHAR(255),
    occurrence_count INTEGER NOT NULL DEFAULT 1 COMMENT '累计出现次数（按出现频次排优先级）',
    last_seen_at    TIMESTAMP NOT NULL DEFAULT NOW(),
    resolution      VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT 'pending/resolved/ignored',
    resolved_by     INTEGER REFERENCES sys_user(id) ON DELETE SET NULL,
    resolved_at     TIMESTAMP,
    resolved_as_mapping_id INTEGER REFERENCES med_dict_mapping(id) ON DELETE SET NULL,
    tenant_id       INTEGER NOT NULL DEFAULT 1 REFERENCES sys_tenant(id),
    created_time    TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_time    TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_med_dict_unmatched UNIQUE (hospital_id, dict_type_id, raw_label)
);
```

**保留策略**（审核增补）：
- `pending` 记录保留至处理；`resolved`/`ignored` 保留 **90 天**后由定时任务物理删除
- UPSERT 语义：同一 `(hospital_id, dict_type_id, raw_label)` 已存在则 `occurrence_count += 1` 且刷新 `last_seen_at`，不重复插入
- 列默认按 `occurrence_count DESC` 排序，高频未匹配优先暴露给数据管理员

### 决策 5：既有硬编码的迁移路径

`normalize_sex` 等 Python 归一化函数**退役**，但保留薄壳以保证调用点（如 `anon_etl_engine.py:325`）签名不变：

1. 三家既有医院（省医/珠江/新桥）的性别标签映射作为 `med_dict_mapping` 种子一次性灌入
2. `normalize_sex` 改为"查 `med_sex` 字典/缓存 → 返回 dict_value"，逻辑下沉到 `DictMappingService.normalize`
3. 同步新增 `med_smoking_status`、`med_exam_type` 等字典与映射，逐步覆盖其他硬编码归一化

### 决策 6：缓存策略（命名统一）

Redis Hash 缓存，与现有字典缓存前缀对齐（医院=租户，见 [ADR 0001](./0001-hospital-as-tenant.md)）：

```
Key:   system_dict_mapping:{tenant_id}:{dict_type}
Type:  Hash
Field: raw_label（lower+trim 后）
Value: {"dict_value":"M","dict_label":"男","dict_data_id":1}
TTL:   无（手动刷新）
```

- 医院配置映射后调 `cache/refresh` 预热
- 新增/修改映射后自动刷新对应缓存
- 查询 O(1)

### 决策 7：历史数据回填

事后补配置映射时，已入库的 NULL 值回填策略：
- 提供 `DictMappingService.backfill(table, field, dict_type, hospital_id)` 后台接口，重读源 parquet + 重新归一化 + UPDATE
- 对幂等要求高的脱敏库，遵循 ADR 0006 的"重复导入只 UPDATE"语义，回填视为一次重新导入
- 大规模回填走异步任务，避免阻塞

## API 设计

| 接口 | 用途 |
|------|------|
| `GET /medical/dict-mapping/list` | 列出映射（按医院+字典类型筛选） |
| `POST /medical/dict-mapping/create` | 新增单条映射 |
| `PUT /medical/dict-mapping/update/{id}` | 修改映射 |
| `DELETE /medical/dict-mapping/delete` | 删除映射 |
| `POST /medical/dict-mapping/batch` | 批量导入映射 |
| `POST /medical/dict-mapping/normalize` | 单值标准化（HTTP 仅暴露给后台调试；ETL 走内部 `DictMappingService.normalize`） |
| `GET /medical/dict-unmatched/list` | 未匹配队列列表 |
| `POST /medical/dict-unmatched/resolve` | 处理未匹配（建映射并回填） |
| `POST /medical/dict-unmatched/ignore` | 忽略未匹配 |
| `POST /medical/dict-mapping/cache/refresh` | 刷新映射缓存 |
| `POST /medical/dict-mapping/backfill` | 历史数据回填（异步） |

## 后续自动化预留

预留 `suggest_mapping(raw_label, raw_value) → [{dict_data_id, confidence}]`：
- 策略1：`raw_label` 等于某个 `dict_label` → 高置信度
- 策略2：`raw_value` 等于某个 `dict_value` → 高置信度（注意 `raw_value` 经常为 NULL，故不作为唯一依据）
- 策略3：其他医院相同 `raw_label` 的映射 → 参考

当积累足够数据后，可升级为自动映射建议（仍需人工确认）。

## 后果

### 正面
- `dict_value` = 存储值的铁则让统一表与脱敏库天然可 JOIN，单一事实源明确
- 硬编码归一化下沉为可配置映射，新医院接入无需改代码
- 未匹配队列提供数据质量监控，管理员可及时发现映射遗漏
- `med_mapping_rule` 新增 `dict` transform_type，字段路由与值映射统一在同一套规则体系内

### 负面 / 风险
- ETL 性能开销增加（每条记录需查映射缓存）→ Redis Hash 缓解，O(1) 查询
- ENUM 降级为 CHECK 后失去 DB 层强类型护栏 → 写入前必须查字典；CHECK 提供第二道护栏
- `sys_dict_data` 多一批 `med_*` 类型 → 数据量可控，本就该如此
- 未匹配队列需定期清理 → resolved/ignored 保留 90 天后定时物理删

### 与其他 ADR 的关系
- **ADR 0001**（医院=租户）：映射表通过 `hospital_id` 关联；缓存 key 用 `tenant_id`，与现有字典缓存前缀一致
- **ADR 0002**（Schema 映射管理）：`med_mapping_rule` 处理字段路由；新增 `dict` transform_type 与 `expression` 分工——前者承载可配置枚举映射，后者承载复杂逻辑。两者在同一规则体系内互补
- **ADR 0006**（脱敏库 Schema）：枚举权威移交至本 ADR 的 `med_*` 字典；ENUM 列降级为 VARCHAR+CHECK，详见 ADR 0006 增补节
