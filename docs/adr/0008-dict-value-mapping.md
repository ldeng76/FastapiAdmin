# ADR 0008: 医院字典值映射（多标签归一化）

> 状态：已接受
> 日期：2026-07-23

## 背景

本项目收集多家医院的数据并统一管理。不同医院对同一概念使用不同的标签值，例如：

- 性别字段：仁济医院存"男性"/"女性"，华山医院存"Male"/"Female"，瑞金医院存"男"/"女"
- 吸烟状态：有的医院用"是"/"否"，有的用"吸烟"/"不吸烟"，有的用"Current"/"Never"/"Former"

统一表需要将这些异构值归一化到标准字典（`sys_dict_data`），以便跨医院统计和建模。

现有体系已具备：
- 标准字典表（`sys_dict_type` / `sys_dict_data`）：平台级枚举定义
- 字段级映射表（`med_mapping_rule`）：解决"哪家医院哪个字段 → 统一表哪个字段"
- 医院注册表（`med_hospital`）：医院元数据

但缺少**值级别**的映射能力——即同一字段内，不同医院的原始标签如何映射到同一个标准 `dict_value`。

## 选项

### 甲. 医院专属字典数据（改原表）

给 `sys_dict_data` 加 `hospital_id` 列，每个医院存自己的 label→value 映射。标准值不统一。

**缺点：**
- 数据膨胀（N 家医院 × M 条字典）
- 标准 `dict_value` 不统一，跨医院查询需额外聚合
- 违反"单一事实源"原则，字典管理混乱

### 乙. 独立映射表（采用）

标准字典保持不变，新增 `med_dict_mapping` 映射表，记录"哪家医院哪个原始标签"对应"哪条标准字典数据"。

**优点：**
- 标准字典干净可复用，保持单一事实源
- 映射关系灵活，支持多对一（多家医院不同标签 → 同一标准值）
- 不影响现有缓存机制
- 可逐步积累映射规则（新医院接入时复用已有映射）

**缺点：**
- 多一张表，ETL 时需额外查询

### 丙. 别名表（JSON 字段）

在 `sys_dict_data` 上加 `aliases` JSON 字段存别名列表。

**缺点：**
- 查询不便（JSON 数组查询无法利用索引）
- 无法追溯"哪个医院的别名"
- 无法处理多家医院别名相同但映射不同的场景

## 决策

采用乙：独立映射表 `med_dict_mapping`。

核心理由：标准字典保持单一事实源，映射关系独立管理，支持医院维度的多对一归一化。

### 表结构

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
    CONSTRAINT uq_med_dict_mapping UNIQUE (hospital_id, dict_type_id, raw_label)
);
```

### 未匹配处理

新增 `med_dict_unmatched` 队列表，记录 ETL 时遇到未映射的原始标签：

```sql
CREATE TABLE med_dict_unmatched (
    id              SERIAL PRIMARY KEY,
    uuid            VARCHAR(64) NOT NULL UNIQUE,
    hospital_id     INTEGER NOT NULL REFERENCES med_hospital(id) ON DELETE CASCADE,
    dict_type_id    INTEGER NOT NULL REFERENCES sys_dict_type(id) ON DELETE CASCADE,
    raw_label       VARCHAR(255) NOT NULL,
    raw_value       VARCHAR(255),
    occurrence_count INTEGER NOT NULL DEFAULT 1 COMMENT '累计出现次数',
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

### 值转换流程

```
ETL2 入库时：
  for each row:
    for each mappable_field:
      raw_label = row[field]
      std = normalize(hospital_id, dict_type, raw_label)
      if std:
        row[field] = std.dict_value
      else:
        record_unmatched(...)
        row[field] = NULL  -- 未匹配，不入库
```

### 缓存策略

```
Key:   dict_map:{hospital_id}:{dict_type}
Type:  Hash
Field: raw_label
Value: {"dict_value": "0", "dict_label": "男", "dict_data_id": 1}
TTL:   无（手动刷新）
```

- 医院接入配置映射后调用 `cache/refresh` 预热
- 新增/修改映射后自动刷新对应缓存
- 查询 O(1) 复杂度

### API 设计

| 接口 | 用途 |
|------|------|
| `GET /medical/dict-mapping/list` | 列出映射（按医院+字典类型筛选） |
| `POST /medical/dict-mapping/create` | 新增单条映射 |
| `PUT /medical/dict-mapping/update/{id}` | 修改映射 |
| `DELETE /medical/dict-mapping/delete` | 删除映射 |
| `POST /medical/dict-mapping/batch` | 批量导入映射 |
| `POST /medical/dict-mapping/normalize` | 单值标准化（ETL 调用） |
| `POST /medical/dict-mapping/normalize-batch` | 批量标准化 |
| `GET /medical/dict-unmatched/list` | 未匹配队列列表 |
| `POST /medical/dict-unmatched/resolve` | 处理未匹配（建映射） |
| `POST /medical/dict-unmatched/ignore` | 忽略未匹配 |
| `POST /medical/dict-mapping/cache/refresh` | 刷新映射缓存 |

### 后续自动化预留

预留 `suggest_mapping(raw_label, raw_value) → [{dict_data_id, confidence}]` 接口：
- 策略1：`raw_value` 等于某个 `dict_value` → 高置信度
- 策略2：`raw_label` 与某个 `dict_label` 模糊匹配 → 中置信度
- 策略3：其他医院相同 `raw_label` 的映射 → 参考

当积累足够数据后，可升级为自动映射建议。

## 后果

### 正面
- 标准字典保持单一事实源，不受医院数据差异影响
- ETL 流水线获得值级归一化能力，入库数据可直接跨医院比较
- 未匹配队列表提供数据质量监控，管理员可及时发现映射遗漏
- 新医院接入时可复用已有映射模板

### 负面 / 风险
- ETL 性能开销增加（每条记录需查映射缓存）→ 通过 Redis Hash 缓解，O(1) 查询
- `med_dict_mapping` 数据量随医院数线性增长 → 数据量可控（每家医院每种字典类型几十条）
- 未匹配队列表需定期清理（已处理的记录）→ 提供 ignore/resolve 状态流转

### 与其他 ADR 的关系
- **ADR 0001**（医院=租户）：映射表通过 `hospital_id` 关联医院
- **ADR 0002**（Schema 映射管理）：`med_mapping_rule` 处理字段路由，本方案处理值转换，两者互补
