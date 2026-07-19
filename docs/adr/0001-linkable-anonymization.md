# 统一确定性脱敏：跨模态病例数据关联

## Context

多中心肺结节研究系统需要把病例数据（结构化报告 CSV/Parquet + DICOM 影像）导入项目前脱敏。硬约束：脱敏必须去除所有 PHI，**同时**保证同一个真实病人的跨模态数据脱敏后仍归属同一个人——不能因各模态分别脱敏而错配或断链。

源数据核实结论：
- 结构化侧（`CT与病理数据.csv`）的 `PAT_LOCAL_ID` 与 DICOM 目录命名 `<PatientID>_<StudyUID>` 的 PatientID 是同一个值（70/70 命中）。
- `EXAM_NO` 同时出现在 DICOM StudyInstanceUID 末段，是天然的检查级桥梁。
- 不同中心（珠江/新桥/省医）的本地号各自独立编号，会撞号。

## Decision

采用**统一确定性映射**，无映射表：

1. **哈希输入 = `Center + PAT_LOCAL_ID`**（Center 进输入以隔离跨中心同号）。
2. **算法 = HMAC-SHA256 + 项目密钥**，输出 `ANON_<HMAC[:12]>`。确定性保证跨模态关联；密钥抗字典攻击（PAT_LOCAL_ID 仅 6-7 位、搜索空间小，无盐 SHA256 可被离线暴力反算）。
3. **关联粒度 = 病人级 + 检查级**：`PAT_LOCAL_ID → ANON_ID`，`EXAM_NO → ANON_EXAM_ID`。住院级（SICK_ID）清空，不保留。
4. **DICOM UID 确定性重生成**为合法 OID（项目根 + HMAC 填充），不用随机生成——否则检查级关联断链。
5. **检查级桥梁 = DICOM `AccessionNumber` 标签存 EXAM_NO**（标准字段，不依赖 UID 命名规律）。
6. **原地替换、丢弃明文**：原始 PAT_LOCAL_ID / EXAM_NO 不保留在任何列。反查靠持密钥者用 HMAC 重算。
7. **自由文本 PHI（报告正文）= 规则匹配 + 私有化部署 LLM（Qwen3）二次清洗**；数据不出内网。
8. **日期**：检查/就诊日期原值保留；出生日期只保留年份、月日清零（结构化侧与 DICOM 侧规则一致）。

## Considered Options

- **映射表方案**（各模态各自脱敏 + 受保护映射表对应）：被否。映射表是单点失败——一旦泄漏即重识别密钥；且需长期维护。HMAC 的核心价值正是"可彻底丢弃明文、不留映射表，却仍保持关联"。
- **无盐 SHA256**：被否。PAT_LOCAL_ID 空间小（十万级），无盐确定性哈希等同明文可逆，挡不住字典攻击。
- **DICOM UID 随机重生成**（现有 POC 做法）：被否。随机生成会切断检查级关联，与决策 3 冲突。
- **DICOM UID 原值保留**：被否。StudyInstanceUID/SeriesInstanceUID 常含设备序列号、Unix 时间戳、机构 OID，属可识别信息。
- **新增 ANON 列、明文并存**：被否。项目数据里仍存明文病人号，违背"进入项目前必须脱敏"的核心要求。

## Consequences

- **不可逆**：项目密钥丢失则永久无法从 ANON_ID 反推原始号。密钥须有**可恢复备份**，不能只存单机。
- **可复现**：同一密钥下，同一 (Center, PAT_LOCAL_ID) 永远生成同一 ANON_ID——重跑脱敏、增量导入都能对齐，无需持久化任何映射。
- **UID 重生成代价**：PACS 浏览器靠运行时扫描磁盘重建索引（`sop_to_path` / `series_map`），不依赖历史 UID，故 UID 替换后浏览器正常工作——但任何缓存了旧 UID 的外部系统需重新索引。
- **自由文本脱敏非 100%**：规则 + 私有 LLM 仍有漏检可能，需保留人工抽检流程作为兜底。
- **旧 Parquet（8 位 patient_id）不纳入**：那是另一批数据，与本次 DICOM/CSV 不是同一批病人；本方案不解决旧 Parquet 的脱敏。

---

## Revision 2026-07-19: 引入百万级对外 ID `patient_id`，省去物理 `patient_seq`

### 触发原因

业务方反馈："所有患者的 id 以百万级编码"。澄清后确认诉求是**对外暴露的患者 ID 用百万级整数序号表达**，而不是当前 12 位 hex（48 bit）HMAC 字符串。

### 变更要点

| 项 | 旧（Rev 2026-07-14） | 新（Rev 2026-07-19） |
|---|---|---|
| **对外主键** | `ANON_ID = "ANON_" + HMAC[:12]`（16 字符字符串） | **`patient_id = "PT_" + 8位zero-pad`**（10 字符字符串，直接 PK） |
| **物理 PK** | `anon_id` VARCHAR(32) PK | **`patient_id` VARCHAR(16) PK** |
| **HMAC 角色** | 对外可见主键 | **降级为内部反查键**（`anon_id` 列保留 UNIQUE） |
| **物理序号 `patient_seq`** | — | **取消**，不再单独保留 BIGINT 序号列 |
| **`patient_id` 生成** | — | 全局 `SEQUENCE` 自增 + 应用层格式化 `PT_xxxxxxxx` |
| **跨表 FK** | `anon_id VARCHAR(32)` | **`patient_id VARCHAR(16)`**（同时调整 4 张子表 FK） |

### 双 ID 体系详解（patient_seq 已并入 patient_id）

每个病人现在有 **2 个标识符**，**一一对应**：

| 列 | 类型 | 用途 | 出现场景 |
|---|---|---|---|
| `patient_id` | `VARCHAR(16)` **PK** | 对外业务 ID（百万级整数字符串）+ 物理主键 | API 响应、研究员查询、FK 引用 |
| `anon_id`    | `VARCHAR(32)` UNIQUE | 内部不可逆反查密钥 | 数据治理、密钥持有者审计 |

> **为何取消 `patient_seq`**：`patient_id` 已是 zero-pad 后的字符串，本身等价于"百万级整数序号"，单列即可承担"对外展示 + 物理 PK"两职。详见 ADR-0006 §方案对比。

**生成与绑定规则**：

1. 首次导入病人 → 取 `nextval(...)` 得 seq，应用层拼 `patient_id = "PT_" || LPAD(seq::text, 8, '0')` → 写入
2. 同步生成 `anon_id = "ANON_" + HMAC-SHA256(secret, center + PAT_LOCAL_ID)[:12]`
3. 重复导入 → 按 `(center_code, anon_id)` 查得原 `patient_id`，**复用不重新发号**
4. 持密钥者：用 `HMAC-SHA256` 反算 `anon_id` → JOIN 查到 `patient_id`

### 保留的旧决策

- ✅ HMAC-SHA256 + 项目密钥（不变）
- ✅ 哈希输入 = `Center + PAT_LOCAL_ID`（不变）
- ✅ 跨模态关联确定性（同一病人多次导入恒同 ID）
- ✅ UID 重生成（不变，仍是 `dicom_series_uid` 等列）
- ✅ 出生日期仅保留年份（不变）
- ✅ `SICK_ID` 不入库（不变）

### 新增的考量

- **饱和告警**：`patient_id` 上加 `CHECK (patient_id ~ '^PT_[0-9]{8}$')`，DB 层兜底；接近 8000 万时治理层触发"扩位"决策（升级为 9 位 zero-pad）
- **并发性能**：依赖底层 SEQUENCE 的 `CACHE 50`（sequence 单独定义，约束详见 DDL）
- **FK 链重写**：`anon_exam` / `anon_exam_finding` / `dicom_series` 等子表 FK 从 `anon_id VARCHAR(32)` 改为 `patient_id VARCHAR(16)`，单次迁移即可
- **饱和迁移代价**：未来若扩到 9 位 zero-pad（`PT_xxxxxxxxx`），`patient_id` VARCHAR(16) 不够存，需升级到 VARCHAR(17)；同时所有 FK 列也需扩。此为已知代价

### 新增的 Considered Option

- **彻底放弃 HMAC，改用纯 sequence 作为对外 ID**：被否。HMAC 仍有价值：
  1. 持密钥者可"反算 anon_id → 找 patient_id"——保留跨系统对账能力
  2. 未来若要 ID 重新发号（例如合规要求漂移），`anon_id` 不变可作为不变量
  3. 第三方接入数据时，`anon_id` 是与原系统最自然的契约形式

- **保留 `patient_seq` BIGINT 作物理 PK**（双 ID 三列）：被否。`patient_id` 已能直接当 PK，多一列+多一 SEQUENCE 无明显收益；FK join 性能差距（VARCHAR(16) vs BIGINT）在 PostgreSQL 下不明显。

### Schema 落地

详见 [ADR-0006 § lnrs_anon_patient 改造](./0006-anonymized-data-schema.md)。

---

## Revision 2026-07-19 (followup): `lnrs_anon_patient` 软删除 + 复活机制

### 触发原因

业务方反馈："病人在导入数据后被删除，再次导入时 patient_id 会变化"。这违反了"病人一旦分配 ID 就永久不变"的医疗领域常规诉求。

### 核心约束

- `patient_id` 永久不变——同一 `(center_code, PAT_LOCAL_ID)` 多次导入恒得同一 `patient_id`
- `anon_id`（HMAC）天然不变
- 仍允许合规场景**物理清理**——保留批量 PURGE 接口

### 变更要点

| 项 | 旧 | 新 |
|---|---|---|
| 删除语义 | 硬删（CASCADE） | **软删**（`deleted_at` 标记，保留行） |
| 复活机制 | 无 | 同 `(center, anon_id)` 重新导入时，**自动复用原 `patient_id`**，仅清 `deleted_at` |
| 物理清理 | 默认 | 单独 `PURGE` 入口，需 `deleted_at < now() - retention_days` 才删 |
| `lnrs_anon_patient` 新列 | — | `deleted_at`, `deleted_reason`, `deleted_batch_id` |
| 子表 FK | `ON DELETE CASCADE` | **不变**——软删除不触发 CASCADE；硬删除(PURGE)仍 CASCADE |

### 应用层 upsert 逻辑（伪代码）

```python
def upsert_patient(center: str, pat_local_id: str, batch_id: str):
    anon_id = "ANON_" + HMAC_SHA256(secret, center + pat_local_id)[:12]

    # 1. 查活病人 (deleted_at IS NULL) → 复用
    row = SELECT patient_id FROM lnrs_anon_patient
          WHERE anon_id = ? AND deleted_at IS NULL
    if row:
        UPDATE last_seen_batch_id, last_seen_at = NOW() WHERE patient_id = ?
        return row.patient_id

    # 2. 查软删除的 → 复活
    row = SELECT patient_id FROM lnrs_anon_patient
          WHERE anon_id = ? AND deleted_at IS NOT NULL
    if row:
        UPDATE deleted_at = NULL, deleted_reason = NULL, deleted_batch_id = NULL,
               last_seen_batch_id = ?, last_seen_at = NOW()
        WHERE patient_id = ? AND deleted_at IS NOT NULL  -- 防并发
        return row.patient_id

    # 3. 真没有 → 发新号
    seq = nextval('lnrs_anon_patient_seq')
    patient_id = f'PT_{seq:08d}'
    INSERT INTO lnrs_anon_patient (patient_id, anon_id, center_code, ...)
    VALUES (patient_id, anon_id, center_code, ...)
    return patient_id
```

### 物理清理（PURGE）入口

```sql
-- 软删除超过 N 天的行, 真正物理删除 (触发 CASCADE)
DELETE FROM lnrs.lnrs_anon_patient
WHERE deleted_at < NOW() - INTERVAL '90 days'
  AND deleted_at IS NOT NULL;
```

由治理团队手动触发，**不在常规应用层调用**。

### Considered Options

- **B. 独立 history 表映射**：被否。重新引入 ADR-0001 已否决的"映射表方案"，单点失败风险。
- **C. 完全禁硬删**：被否。合规清理（如 GDPR 遗忘权、错误数据下架）需要彻底物理删除手段。
- **方案 A 软删除**：选。**映射就藏在 patient 行自身的 `deleted_at` 字段里**，无独立映射表，且通过 PURGE 保留物理清理能力。

### Schema 落地

详见 [ADR-0006 § lnrs_anon_patient 软删除改造](./0006-anonymized-data-schema.md)。
