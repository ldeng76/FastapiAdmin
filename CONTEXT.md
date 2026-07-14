# 病例数据脱敏（Linkable Anonymization）

本上下文定义多中心肺结节研究系统中，病例数据进入项目前的脱敏术语体系。核心约束：脱敏必须去除个人可识别信息（PHI），同时保证同一个真实病人的跨模态数据（结构化报告 + DICOM 影像）脱敏后仍归属同一个人。

## Language

**Patient（病人）**：
一个真实的自然人，本项目所有数据的归属主体。一个 Patient 在结构化侧和 DICOM 侧是同一个人。
_Avoid_: 用户(user)、受试者(subject)——这些词在代码里不指代病人

**Center（中心）**：
一家数据来源医院（珠江 / 新桥 / 省医）。Center 是病人身份的一部分——不同中心的本地号是各自独立编号的，会撞号。
_Avoid_: 医院(hospital)、机构(institution)——这两个词在 DICOM 标签里指代设备/科室，语义不同

**PAT_LOCAL_ID（患者本地号）**：
一家中心内部编号病人的唯一号（如珠江的 `1008201`）。它是**单中心内部**的病人主键，也是跨模态关联的统一确定性哈希输入。
_Avoid_: 门诊号、住院号——这两个是更窄的子概念，见下

**SICK_ID（住院号）**：
病人在某次住院时的号。一个 PAT_LOCAL_ID 可能对应多个 SICK_ID（多次住院）。脱敏时**清空**，不保留住院次级关联。

**EXAM_NO（检查号）**：
一次 CT 检查的唯一号（如 `1006383144`）。它同时在 DICOM 的 `AccessionNumber` 标签中出现，是**检查级**的跨模态桥梁——能精确对应"这张片子是这次检查拍的"。
_Avoid_: 流水号——检查号是业务标识，不是自增序号

**ANON_ID（脱敏病人标识）**：
对 `Center + PAT_LOCAL_ID` 做 HMAC-SHA256 生成的确定性脱敏病人号（形如 `ANON_xxx`）。同一个 (Center, PAT_LOCAL_ID) 永远生成同一个 ANON_ID；跨中心同号生成不同 ANON_ID。替代原始 PAT_LOCAL_ID 写入所有数据，明文 PAT_LOCAL_ID 不保留。

**ANON_EXAM_ID（脱敏检查标识）**：
对 `EXAM_NO` 做 HMAC 生成的确定性脱敏检查号。检查级关联的载体，替代原始 EXAM_NO。

**项目密钥（Project Secret）**：
HMAC 计算所用的对称密钥，存在配置/环境变量、绝不入库。它是反推原始号的**唯一**凭证——丢失则永久不可逆。须有可恢复备份。

**检查级桥梁（Exam-level bridge）**：
DICOM 的 `AccessionNumber` 标签存放原始 EXAM_NO 这一约定。它让 DICOM 侧的 Study 和结构化侧的检查行能跨模态对应，是检查级关联的物理载体。

**重识别（Re-identification）**：
从脱敏数据反推真实病人身份。本方案通过 HMAC 抗字典攻击、确定性哈希防映射表泄漏来抵御。

## Relationships

- 一个 **Patient** 在单中心内由唯一的 **PAT_LOCAL_ID** 标识
- 一个 **Center** 内的 **PAT_LOCAL_ID** 是唯一的；**不同 Center 的相同 PAT_LOCAL_ID 是不同病人**
- 一个 **Patient** 对应 0 或多个 **SICK_ID**（多次住院）
- 一个 **Patient** 对应 1 或多个 **EXAM_NO**（多次检查）
- 一个 **EXAM_NO** 同时存在于结构化数据行 和 对应 DICOM Study 的 `AccessionNumber` 中——这是跨模态桥梁
- 脱敏后：一个 **Patient** → 一个 **ANON_ID**；一个 **EXAM_NO** → 一个 **ANON_EXAM_ID**
- 只有持有 **项目密钥** 的人能从 ANON_ID 反推 PAT_LOCAL_ID（可复现、不可暴力反算）

## Example dialogue

> **Dev:** "珠江的 `1008201` 和省医的 `1008201` 脱敏后会是同一个 ANON_ID 吗？"
> **领域专家:** "不会。ANON_ID 的输入是 Center + PAT_LOCAL_ID，所以这两个不同病人会得到两个不同的 ANON_ID——这正是 Center 进入哈希输入的原因。"

> **Dev:** "为什么不用映射表记录 PAT_LOCAL_ID ↔ ANON_ID 的对应？"
> **领域专家:** "因为映射表一旦泄漏就等于重识别密钥，是单点失败。HMAC 的好处是：可以彻底丢弃明文、不留映射表，却仍保持跨模态关联——确定性保证了'同一输入永远同一输出'。"

## Flagged ambiguities

- "patient_id" 在代码里被用于指代多种东西：旧 Parquet 里的 8 位号、CSV 里的 PAT_LOCAL_ID、DICOM 里的 PatientID——**resolved**: 脱敏语境下，统一指向 PAT_LOCAL_ID 这一层概念；旧 Parquet 是另一批数据、不纳入本方案。
- "ID" 笼统使用时含混——**resolved**: 涉及病人用 PAT_LOCAL_ID / ANON_ID；涉及检查用 EXAM_NO / ANON_EXAM_ID；涉及住院用 SICK_ID（将被清空）。
- "保留日期" 是否包括出生日期——**resolved**: 检查/就诊日期原值保留；出生日期只保留年份、月日清零（两侧规则一致）。
