# 多模态数据"文件名"命名规则：全局唯一 + 标识模态

## Context

多模态数据页（`frontend/web/src/views/module_medical/files/index.vue`，后端 `/medical/files/list`）的"文件名"列目前恒为空：`MedFilesModel.file_name` 是占位属性，数据库 `lnrs_anon_imaging_study` 无对应列（`backend/app/plugin/module_medical/files/model.py:29-30`，schema 层空串转 None：`files/schema.py:18-22`）。

需求：为每行记录生成一个**全局唯一、能标识模态类型**的文件名，用作页面展示标识，并顺带作为下载/导出时的规范文件名（`files/service.py:444` 已有 `obj.file_name or path.name` 兜底）。

可用素材（均已核实）：

| 素材 | 取值/格式 | 全局唯一性 | 备注 |
|---|---|---|---|
| `patient_id` | `PT_` + 8 位序号 | ✅ 全局序列发号 | 页面已展示 |
| `study_key` | BIGSERIAL 主键 | ✅ | DB 内部号，重建库后会变 |
| `dicom_study_uid` | 原 StudyInstanceUID，≤64 字符 | ✅（明文） | 过长，不宜整体入文件名 |
| `center_code` | hos301 / shengyi / zhujiang / xinqiao | — | 含中心归属，**匿名化要求不进文件名**（见 Decision） |
| `modality` | CT/MR/XR/US/PET/NM/Pathology/Genetic/Other | — | 即需求中的"模态类型" |
| `source` | 盘标识（disk_06_shengyi…），NOT NULL | — | 行级唯一键的组成部分 |
| `anon_exam_id` | `ANON_EXAM_<12hex>` | ✅ | **imaging_study 中可空**，不可依赖 |

关键约束：表上唯一约束是 `(patient_id, dicom_study_uid, source)`（`anon_model.py:936-939`）——**同一 study 跨盘允许重复成多行**。文件名若只锚定 study_uid，跨盘重复行会重名，违背"全局唯一"。

## Decision

### 命名规则

```
{MOD}_{patient_id}_{hash12}.{ext}
```

- **`MOD`**：模态码，由 `imaging_study.modality` 映射（固定表）：`CT→CT, MR→MR, XR→XR, US→US, PET→PET, NM→NM, Pathology→PATH, Genetic→GEN, Other→OTH`。放首段——满足"标识模态类型"，且按文件名排序时同模态自然聚簇。模态是临床属性、非身份标识，可出现。
- **`patient_id`**：`PT_xxxxxxxx` 原值。全局序列发号，跨中心唯一，且编号与来源医院**无任何编码关系**——不泄露中心归属。
- **`hash12`**：`HMAC-SHA256(LNRS_ANON_SECRET, "{patient_id}:{source}:{dicom_study_uid}")[:12]`。**哈希输入 = 该行的自然唯一键三元组**——三元组在表上有 UNIQUE 约束，因此不同行输入必不同，重名只可能来自 48-bit 截断碰撞（概率分析与 ADR-0001 的 ANON_ID 完全同级，当前 12 万行量级期望碰撞 ≈ 2.6e-5，可忽略）。复用 `anonymize.py::_hmac_hex`，与既有脱敏体系同一密钥、同一截断惯例。跨盘重复的同一 study 各行得到不同名字，行级唯一成立。`source`（盘标识）虽字面含中心线索，但只进 HMAC 输入、从不直接出现，HMAC 输出不可反推。
- **`ext`**：数据格式，即页面"数据格式"列的 `file_type`（当前恒 `dcm`；未来 `nii` / `svs`）。文件名扩展名与数据格式列保持一致，两列互为印证。

**不设 center 段（2026-09-22 用户决策）**：文件名是会被导出、截图、传播的载体，"来自哪家医院"本身属敏感信息（尤其小样本中心近乎直接可识别），匿名化要求文件名不携带 `center_code`。库内 `center_code` 列与页面"中心"列/筛选器照常工作——中心维度只在展示层由权限与筛选承担，不进入可外流的标识符。

示例：

```
CT_PT_00565070_9f83aa2b1c7d.dcm
CT_PT_00557189_3d07c5e21a90.dcm
```

命名性质：

- **全局唯一**（见 hash12 论证；兜底见 Consequences）。
- **确定性/幂等**：同一行在任何环境、任何时刻重算同密钥必得同名；ETL 重跑、翻页、重建索引都不漂移。不引入随机数、不依赖发号顺序。
- **跨库重建稳定**：输入全部是内容字段（非 `study_key` 这类库内序号），从零重建库后名字不变——导出数据、论文引用不会失效。
- **字符安全**：仅 `[A-Za-z0-9_.]`，无中文/空格/大小写歧义段，Windows/Linux/S3 object key 通吃；典型长度 ~31 字符，最坏 ~35（模态码最长 PATH=4），远低于 255 文件系统上限。
- **无 PHI**：组成全部是已脱敏标识（PT 号、中心码、HMAC 截断），不含原始院内号。HMAC 而非裸 SHA256，遵守 ADR-0001"小空间标识符必须加盐"的项目铁律。

### 生成位置（两阶段）

**Phase 1（推荐立即做）：查询时计算，不动库。**

- 共享工具函数（放 `anonymize.py` 或 `files/naming.py`）：

  ```python
  _MODALITY_CODE = {"CT": "CT", "MR": "MR", "XR": "XR", "US": "US",
                    "PET": "PET", "NM": "NM", "Pathology": "PATH",
                    "Genetic": "GEN", "Other": "OTH"}

  def build_file_name(*, patient_id, modality,
                      dicom_study_uid, source, study_key, file_type="dcm") -> str:
      anchor = (f"{patient_id}:{source}:{dicom_study_uid}"
                if dicom_study_uid else f"study_key:{study_key}")
      code = _MODALITY_CODE.get(modality, "OTH")
      return f"{code}_{patient_id}_{_hmac_hex(anchor)}.{file_type}"
  ```

- `MedFilesModel.file_name` 从 `str = ""` 占位改为 `@property`，内部调用上述函数（需在 model 上补映射物理列 `source`）；pydantic `from_attributes` 走 getattr，`/files/list`、下载兜底（`service.py:444`）自动生效，**零迁移、零回填、零 ETL 写路径改动**。
- 排序无回归：`service.py::_resolve_order_columns` 对无 `__clause_element__` 的属性本就静默跳过、回退 `id desc`——文件名列的排序头目前就是空操作；如需排序体验，可把 `file_name` 排序映射到 `(modality, patient_id, id)` 表达式（前缀序，等价观感），属可选增强。

**Phase 2（仅当出现外部契约需求时）：持久化列。**

若未来要把文件名写进导出包、对外 API 合同或对象存储 key，再迁移加列 `file_name VARCHAR(64)`，用同一函数回填，加 UNIQUE 索引（冲突行把截断延长到 16 hex 消解）。规则本身不变，Phase 1 → Phase 2 无缝升级。当前阶段没有任何消费方需要落库名字，先落列只会增加 5+ 个灌库脚本的写路径负担。

## Considered Options

- **文件名含 `center_code` 段**（初版方案 `CT_hos301_PT_xxx_<hash>.dcm`）：被否（2026-09-22 用户决策）。中心归属本身是敏感信息——多中心研究里"来自哪家医院"可大幅缩小重识别面（小样本中心近乎直接可识别），文件名作为可导出/可传播的标识载体不得携带；HMAC 输入里的 `source` 同理只进哈希不外显。
- **文件名嵌完整 `dicom_study_uid`**：被否。UID 最长 64 字符，整名逼近 90+ 字符且暴露 UID 全文（设备序列号/机构 OID 结构可见，ADR-0001 决策 4 的同类顾虑）。
- **锚定 `study_key`（如 `CT_hos301_PT_xxx_00012345.dcm`）**：被否。库内自增号随重建漂移，导出引用会失效；且从名字看不出与 study 的内容关联。
- **锚定 `anon_exam_id`**：被否。imaging_study 中可空（离线灌库行未回填），无法全覆盖；且一次 exam 理论可对应多 study。
- **随机 UUID 文件名**：被否。非确定性——每次查询/重跑都变，违背幂等；也无法从行数据重算。
- **裸 SHA256（无盐）截断**：被否。StudyInstanceUID 虽熵较高，但项目惯例（ADR-0001）是凡源自原始标识符的派生一律 HMAC，统一口径避免例外。
- **不区分 source（哈希输入仅 `center:study_uid`）**：被否。唯一约束明确允许跨盘重复行，重复行会重名，违背全局唯一。

## Consequences

- **可读性权衡**：从文件名不再能直读中心归属——这是匿名化的代价也是目的。中心维度由页面"中心"列/筛选器承担（库内 `center_code` 列不动）；跨中心核对同一患者时以 `patient_id` 为准（患者本就跨中心唯一）。
- **碰撞残留**：48-bit 截断在当前 12 万行量级可忽略；若未来到千万行且已 Phase 2，靠 UNIQUE + 16-hex 延长消解。未落库阶段两行碰撞仅是显示重名，行仍以 `study_key` 区分，无功能影响。
- **`Pathology/Genetic` 未来行**：命名规则天然覆盖（PATH_/GEN_ 前缀 + 对应 ext），病理 WSI（svs）、报告类文档入库后无需改规则，仅扩 `file_type` 取值。
- **hos301 现状兼容**：当前 301 行是纯元数据行（文件数/大小均为 0、无物理目录），文件名作为逻辑标识照常生成，不依赖物理文件存在；"查看文件"的存在性校验逻辑不受影响。
- **下载行为不变**：study 目录下载现被 400 拦截（提示走 DICOMweb）；单文件下载经 `obj.file_name or path.name` 后将自动使用规范名。若未来开放目录打包下载，包名 = `{file_name}.zip`。
- **字典翻译不受影响**："模态类型"列继续走 `med_modality` 字典显示中文 label；文件名中的 `MOD` 码是面向文件系统/接口的英文码，两者职责不同、并存。
