# 计划：枚举字段对齐国标 + 归一化下沉 DictMappingService

> **起草日期**: 2026-07-24
> **状态**: 待执行
> **关联 ADR**: ADR-0006（脱敏数据架构）、ADR-0008（医疗字典值级映射）

---

## 决策摘要（已与用户确认）

| 维度 | 决策 |
|---|---|
| **字段编码** | sex=HQMS RC001(0/1/2/9), ethnicity=GB/T3304 数字码(01~56,99), abo=RC030(1~6), rh=RC031(1~3), smoking=自创数字码(1/2/3/9), center=拼音短码 |
| **字典下发** | init_data SQL 脚本（已有库）+ JSON 种子（新库）双写 |
| **CHECK 约束** | 5 个枚举字段全覆盖，统一命名 `lnrs_anon_ck_patient_*` |
| **归一化架构** | 路线 B+：DictMappingService 新增 `load_all_mappings()` 批量预热；anonymize.py 硬编码兜底退役 |
| **数据迁移** | 开发阶段不考虑 |

---

## 背景与动机

### 现状问题
1. `anonymize.py` 中 `_HQMS_TO_MFU` 硬编码换算表存在两层映射叠加的反模式：
   - parquet 原值（0/1/2/9）→ med_dict_mapping 查表得 dict_value（M/F/U）→ 再硬编码换算回 0/1/2/9
   - 注释声称 dict_value 是国标 0/1/2/9，但实际 sys_dict_data.json 里 med_sex 的 dict_value 就是 M/F/U，注释与事实矛盾
2. `normalize_sex` 走"缓存命中后硬编码换算"路径，与 ADR-0008 决策 5 的"normalize_* 退役，下沉到 DictMappingService"方向违背
3. `ethnicity` / `smoking_status` / `abo_blood_type` / `rh_blood_type` 4 个字段**完全没有归一化**，医院给的原值直接入库
4. DDL CHECK 约束命名三处不一致（执行版 DDL / Alembic upgrade / Alembic downgrade 各一套）
5. `docs/adr/0006-anonymized-schema-lnrs.sql` 是过时副本（仍用 ENUM，缺扩展列和 visit/surgery/exam_detail 三表）

### 设计原则（用户拍板）
> `lnrs_anon_*` 表中所有**有限枚举型** VARCHAR 字段的合法取值集合，必须等于 `sys_dict_data` 中对应 `dict_type` 的 `dict_value` 集合。ETL 写入时只通过 `med_dict_mapping` 查表归一化，不在 Python 代码里硬编码换算。

---

## 阶段 1：字典数据（双路径下发）

### 1.1 `backend/app/scripts/data/sys_dict_type.json`（新库种子）
追加 4 个新类型 + 修订 med_sex 描述：

| dict_type | dict_name | 新增/修订 |
|---|---|---|
| `med_sex` | 医疗·性别 | **修订描述**：HQMS RC001 国标 |
| `med_smoking_status` | 医疗·吸烟状态 | 既有类型，补 data |
| `med_ethnicity` | 医疗·民族 | **新建**：GB/T3304 |
| `med_blood_type_abo` | 医疗·ABO血型 | **新建**：HQMS RC030 |
| `med_blood_type_rh` | 医疗·Rh血型 | **新建**：HQMS RC031 |
| `med_center` | 医疗·数据中心 | **新建**：内部拼音短码 |

### 1.2 `backend/app/scripts/data/sys_dict_data.json`（新库种子）

| 字典类型 | 条目数 | 取值（dict_value → dict_label） | 标准来源 |
|---|---|---|---|
| `med_sex`（修订） | 4 | 0=未知, 1=男, 2=女, 9=未说明 | HQMS RC001 / GB/T 2261.1 |
| `med_smoking_status`（补全） | 4 | 1=从不, 2=既往, 3=现在, 9=未知 | 自创数字短码（无国标） |
| `med_ethnicity`（新增） | 57 | 01=汉族, 02=蒙古族, …, 56=基诺族, 99=其他 | GB/T 3304-1991 |
| `med_blood_type_abo`（新增） | 6 | 1=A, 2=B, 3=O, 4=AB, 5=不详, 6=未查 | HQMS RC030 |
| `med_blood_type_rh`（新增） | 3 | 1=阴性, 2=阳性, 3=不详 | HQMS RC031 |
| `med_center`（新增） | 3 | shengyi=省医, xinqiao=新桥, zhujiang=珠江 | 内部编码 |

### 1.3 `backend/sql/postgres/init_data/050_med_enum_dicts.sql`（NEW，已有库下发）
**命名说明**：前缀 `050_` 确保字典序排在 `hospital_menu.sql`/`medical_menu.sql` 之后、`zzz_hide_irrelevant_menus.sql` 之前。

脚本内容用幂等 `INSERT ... ON CONFLICT DO NOTHING/UPDATE`：
- INSERT sys_dict_type 6 类（ON CONFLICT (tenant_id, dict_type) DO UPDATE SET dict_name）
- INSERT sys_dict_data 全部条目（按 `(dict_type_id, dict_value)` 去重 upsert）
- 重点：med_sex 的旧值 M/F/U 需 UPDATE 改为 1/2/0，并新增 9
- 同时灌入三家医院的 `med_dict_mapping` 种子（医院原始标签 → 标准值）

---

## 阶段 2：DDL 约束

### 2.1 `backend/sql/postgres/0006-anonymized-schema-lnrs.sql`（执行版）
- `:2` 顶部注释追加 Rev `2026-07-24 枚举字段对齐国标 + CHECK 全覆盖`
- `:111` `sex VARCHAR(10) NOT NULL DEFAULT 'U'` → `DEFAULT '0'`
- `:138` CHECK 约束：
  ```sql
  -- 旧：CONSTRAINT lnrs_anon_ck_patient_sex CHECK (sex IN ('M','F','U'))
  CONSTRAINT lnrs_anon_ck_patient_sex CHECK (sex IN ('0','1','2','9'))  -- HQMS RC001
  ```
- 新增 4 个 CHECK（紧跟列定义后或表尾统一加），命名统一 `lnrs_anon_ck_patient_*`：
  ```sql
  CONSTRAINT lnrs_anon_ck_patient_ethnicity CHECK (ethnicity IS NULL OR ethnicity ~ '^[0-9]{2}$'),
  CONSTRAINT lnrs_anon_ck_patient_smoking   CHECK (smoking_status IS NULL OR smoking_status IN ('1','2','3','9')),
  CONSTRAINT lnrs_anon_ck_patient_abo       CHECK (abo_blood_type IS NULL OR abo_blood_type IN ('1','2','3','4','5','6')),
  CONSTRAINT lnrs_anon_ck_patient_rh        CHECK (rh_blood_type IS NULL OR rh_blood_type IN ('1','2','3')),
  CONSTRAINT lnrs_anon_ck_patient_center    CHECK (center_code ~ '^[a-z][a-z0-9_]*$')
  ```
- `exam_type` 维持无 CHECK（理由：字典值会扩展，CHECK 反而束缚；ADR-0006:333 已明示）

### 2.2 `docs/adr/0006-anonymized-schema-lnrs.sql`（镜像同步）
**重大问题**：此文件是过时副本（仍用 ENUM，缺扩展列和 visit/surgery/exam_detail 三表）。
**处置**：本次整改**直接覆盖为执行版的镜像**（从 2.1 复制），消除"双源不一致"历史债。

---

## 阶段 3：DictMappingService 增强（架构核心）

### 3.1 `backend/app/plugin/module_medical/dict_mapping/service.py`
新增 `load_all_mappings` 类方法，复用 `_refresh_cache._do_refresh`（service.py:343-352）的 JOIN 范式：

```python
@classmethod
async def load_all_mappings(
    cls,
    db: AsyncSession,
    dict_type: str,
    hospital_id: int | None = None,
) -> dict[str, str]:
    """批量加载某 dict_type 的全部映射为内存 dict（ETL 场景专用）。

    返回 {raw_label_lower: dict_value}，运行时纯内存查表，零 SQL 往返。
    - hospital_id 指定时：含该院映射 + 平台默认（hospital_id=1）的并集
    - hospital_id 为空时：加载该 dict_type 下全部映射（跨医院并集）

    性能：1 次 JOIN 查询（消除 N+1），适合 10 万级 ETL 批量。
    """
    from app.api.v1.module_system.dict.model import DictDataModel, DictTypeModel

    # 1. 查 dict_type_id（1 SQL）
    dt_result = await db.execute(
        select(DictTypeModel).where(DictTypeModel.dict_type == dict_type)
    )
    dt_obj = dt_result.scalars().first()
    if not dt_obj:
        log.warning("load_all_mappings: dict_type=%s 不存在", dict_type)
        return {}

    # 2. JOIN 批量查映射 + dict_value（1 SQL）
    stmt = (
        select(DictMappingModel.raw_label, DictDataModel.dict_value)
        .join(DictDataModel, DictMappingModel.dict_data_id == DictDataModel.id)
        .where(DictMappingModel.dict_type_id == dt_obj.id)
    )
    if hospital_id is not None:
        stmt = stmt.where(
            DictMappingModel.hospital_id.in_([hospital_id, PLATFORM_TENANT_ID])
        )
    rows = (await db.execute(stmt)).all()

    return {r[0].strip().lower(): r[1] for r in rows if r[1]}
```

**注意事项**：
- 加 `strip()` + `lower()`（对齐 ADR-0008 决策 4.1 的 raw_label 规范化约定；现有 `_lookup_cache` 只 lower 不 strip 是已知小瑕疵）
- 用 INNER JOIN：`dict_data_id IS NULL` 的映射会被过滤（符合既有语义）
- 复用 `PLATFORM_TENANT_ID = 1` 常量（service.py 已 import）

**为什么选 B+ 而非直调 normalize_service**：探查发现 `normalize_service` 是为 HTTP 单值调试设计的（每次 3-4 SQL + 独立事务写 unmatched），直调用于 ETL 批量场景会产生 150-200 万次 SQL 往返（10 万患者 × 5 字段，预计 17-50 分钟）。B+ 方案保留"批量预热 + 内存查表"的性能优势，同时真正下沉到 service 层。

---

## 阶段 4：anonymize.py 退役硬编码

### 4.1 `backend/app/plugin/module_medical/hospital/anonymize.py`

**删除**：
- `:37-38` `_SEX_MAP_M` / `_SEX_MAP_F` 硬编码集合
- `:40-42` `_HQMS_TO_MFU` 换算表（国标化后 dict_value 已是 0/1/2/9，无需换算）
- 旧版 `load_sex_mapping`（`:216-260`）的 N+1 实现

**改写 `load_sex_mapping`**（`:216-260`）为薄壳：
```python
async def load_sex_mapping(db: Any, hospital_id: int | None = None) -> None:
    """预热性别映射缓存（ADR-0008 决策5：下沉到 DictMappingService）。

    调用 DictMappingService.load_all_mappings 一次性 JOIN 加载 med_sex 全部映射。
    hospital_id 非空时取该院 + 平台默认的并集。
    """
    global _SEX_MAP_CACHE
    from app.plugin.module_medical.dict_mapping.service import DictMappingService
    try:
        _SEX_MAP_CACHE = await DictMappingService.load_all_mappings(
            db, "med_sex", hospital_id=hospital_id
        )
        log.info(f"ETL2: med_sex 映射缓存加载完成，共 {len(_SEX_MAP_CACHE)} 条")
    except Exception as e:
        log.error(f"ETL2: med_sex 映射加载失败: {e!s}")
        _SEX_MAP_CACHE = {}
```

**改写 `normalize_sex`**（`:263-293`）：
```python
def normalize_sex(raw: Any) -> str:
    """性别归一化 → HQMS RC001 国标码 '0'/'1'/'2'/'9'。

    查 _SEX_MAP_CACHE（由 load_sex_mapping 预热）；未命中返回 '0'（未知）。
    硬编码兜底已退役（ADR-0008 决策5），未配置映射的医院需先在
    med_dict_mapping 表配置种子数据。
    """
    if raw is None:
        return "0"
    s = str(raw).strip()
    if not s:
        return "0"
    if _SEX_MAP_CACHE:
        v = _SEX_MAP_CACHE.get(s.lower())
        if v:
            return v
    return "0"  # 未命中返回未知，不再回退硬编码
```

**新增 4 套对等函数**（同款范式）：
- `load_ethnicity_mapping(db, hospital_id)` + `normalize_ethnicity(raw) -> str | None`（返回 None 表示源为空）
- `load_smoking_status_mapping(db, hospital_id)` + `normalize_smoking_status(raw) -> str | None`
- `load_abo_blood_type_mapping(db, hospital_id)` + `normalize_abo_blood_type(raw) -> str | None`
- `load_rh_blood_type_mapping(db, hospital_id)` + `normalize_rh_blood_type(raw) -> str | None`
- 各自模块级全局缓存 `_ETHNICITY_MAP_CACHE` / `_SMOKING_MAP_CACHE` / `_ABO_MAP_CACHE` / `_RH_MAP_CACHE`

**新增统一预热入口**：
```python
ENUM_DICT_TYPES = ("med_sex", "med_ethnicity", "med_smoking_status",
                   "med_blood_type_abo", "med_blood_type_rh")

async def load_all_enum_mappings(db: Any, hospital_id: int | None = None) -> None:
    """ETL2 入口统一预热所有枚举字段映射。"""
    await load_sex_mapping(db, hospital_id)
    await load_ethnicity_mapping(db, hospital_id)
    await load_smoking_status_mapping(db, hospital_id)
    await load_abo_blood_type_mapping(db, hospital_id)
    await load_rh_blood_type_mapping(db, hospital_id)
```

---

## 阶段 5：ETL 引擎接入

### 5.1 `backend/app/plugin/module_medical/hospital/anon_etl_engine.py`

**改 `:999-1001` 预热点**：
```python
# 旧：await load_sex_mapping(db)
# 新：
from .anonymize import load_all_enum_mappings
await load_all_enum_mappings(db, hospital_id=current_hospital_id)
```
- 注：`current_hospital_id` 需从 center_code 反查 med_hospital 表得到（或 ETL 入口已传入）。若不便，先用 `hospital_id=None`（加载全平台映射并集）。

**改 `:534, :537-542` 字段填充**：
```python
{
    ...
    "sex": normalize_sex(rd.get("gender")),
    "ethnicity": normalize_ethnicity(rd.get("ethnicity")),
    "smoking_status": normalize_smoking_status(rd.get("smoking_status")),
    "abo_blood_type": normalize_abo_blood_type(rd.get("abo_blood_type")),
    "rh_blood_type": normalize_rh_blood_type(rd.get("rh_blood_type")),
    ...
}
```

**import 语句**（`:44-56`）追加：
```python
from .anonymize import (
    normalize_sex, normalize_ethnicity, normalize_smoking_status,
    normalize_abo_blood_type, normalize_rh_blood_type,
)
```

---

## 阶段 6：测试

### 6.1 `backend/tests/anon_etl/test_anonymize.py`

**修订 `TestNormalizeSex`**（`:110-138`）：
- 旧期望值 M/F/U → 新期望值 1/2/0/9
- 移除对硬编码兜底的隐式依赖（旧测试走硬编码分支，新代码无硬编码，测试需 mock `_SEX_MAP_CACHE`）

**新增测试类**（5 个）：
- `TestNormalizeEthnicity`：mock 缓存为 `{"汉族":"01","ha":"01",...}`，验证 raw_label → dict_value
- `TestNormalizeSmokingStatus`：`{"从不":"1","never":"1",...}`
- `TestNormalizeAboBloodType`、`TestNormalizeRhBloodType`：同款
- `TestLoadAllEnumMappings`：mock db 测预热路径（补上现有 sex 缺失的缓存覆盖）

### 6.2 `backend/tests/test_dict_mapping_service.py`（NEW）
- `TestLoadAllMappings`：JOIN 正确性、hospital_id 过滤、dict_data_id=NULL 过滤

---

## 阶段 7：文档同步

### 7.1 `docs/adr/0008-dict-value-mapping.md`
- **决策 1**（`:55-62`）：修订 med_sex dict_value 取值（M/F/U → 0/1/2/9，注明 HQMS RC001 对齐）
- **决策 2 表格**（`:68-74`）：
  - med_sex：M/F/U → 0/1/2/9（HQMS RC001）
  - med_smoking_status：待定 → 1/2/3/9
  - 新增 4 行：med_ethnicity、med_blood_type_abo、med_blood_type_rh、med_center
- **决策 5**（`:160-167`）：更新现状描述，标注 normalize_* 硬编码兜底已退役，DictMappingService.load_all_mappings 已就位
- **新增决策 7**：HQMS/GB 国标对齐原则，记录各字段的编码来源（RC001/RC030/RC031/GB3304）

### 7.2 `docs/adr/0006-anonymized-data-schema.md`
- **lnrs_anon_patient 字段表**（`:67-80`）：把 sex 的 ENUM('M','F','U') 改为 VARCHAR(10) + CHECK(0/1/2/9)
- **枚举改造增补节**（`:250-284`）：CHECK 约束命名统一为 `lnrs_anon_ck_patient_*`，覆盖范围扩展到 ethnicity/smoking/abo/rh

### 7.3 `docs/spec-medical-wide-table-direct-ingestion-zh.md`
- §3.1 lnrs_anon_patient 扩展表：在"约束"小节补全 5 个新 CHECK
- §4.1 新增 normalize_* 函数签名（5 个新函数）
- §11 决策索引追加 D9：枚举字段对齐国标

---

## 不修改的文件

- `backend/app/plugin/module_medical/dict_mapping/controller.py`：HTTP 端点不变
- `backend/app/plugin/module_medical/dict_mapping/crud.py`：CRUD 不变
- `backend/app/plugin/module_medical/dict_mapping/model.py`：DictMappingModel 不变
- `etl1/centers/*.py`：ETL1 不动（用户只要求 ETL2）
- `med_exam_type` 字典：已有 CT/PETCT/Pathology/Genetic/IHC，本次不涉及 exam_type 字段
- `med_laterality` 字典：已有 L/R/Bilateral/N/A，本次不涉及 laterality 字段
- `alembic/versions/e5f6a7b8c9d0_*.py`：**既有迁移不改动**（既有 CHECK 命名 bug 留作历史，不回头修迁移脚本，只在执行版 DDL 统一）

---

## 执行顺序

1. **字典数据**（阶段 1.1 / 1.2 / 1.3）：双路径下发
2. **DDL**（阶段 2.1 / 2.2）：CHECK 约束全覆盖
3. **DictMappingService.load_all_mappings**（阶段 3.1）：架构核心
4. **anonymize.py 退役硬编码 + 新增 5 套**（阶段 4.1）
5. **ETL 引擎接入**（阶段 5.1）
6. **测试**（阶段 6.1 / 6.2）
7. **文档同步**（阶段 7.1 / 7.2 / 7.3）
8. **手工验证**：跑现有 ETL smoke 测试（需 PG），确认 dev 库重新导入后 sex 列值为 0/1/2/9

---

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| med_center 字典化后，center_code 值与 ETL 配置（_CENTER_PARQUET_SPECS key）不一致 | 字典 dict_value 用现有 key（shengyi/xinqiao/zhujiang），ETL 配置不改 |
| med_dict_mapping 表当前无种子映射（除 sex 外） | 需在 init_data 脚本里同步灌入三家医院的原始标签→标准值映射种子，否则 normalize_* 全部返回未知值 |
| load_all_mappings 跨医院并集可能冲突（同 raw_label 不同 dict_value） | 当前实现后写覆盖前写；后续可加 hospital_id 优先级排序 |
| schema_hash 变更需重启 | 整改后重启 dev/h42 服务进程 |

---

## 探查发现的关键事实（备查）

### ADR 与代码的偏差
1. **ADR-0008 决策 6 声明的 Redis Hash Value 是 JSON `{dict_value, dict_label, dict_data_id}`，但 service.py:354-356 实际只存裸 dict_value 字符串**（简化实现）
2. **ADR-0008 决策 4.3 的"resolved/ignored 保留 90 天定时清理"未实现**（无定时任务）
3. **ADR-0008 决策 4.3 的"按 occurrence_count DESC 排序"未实现**（list_unmatched_service 无 order_by）
4. **`_lookup_cache` 只 lower 不 trim**，与 ADR-0008 决策 4.1 的"raw_label 须 lower()+trim()"有边缘不一致

### 既有代码的反模式
1. **`_HQMS_TO_MFU` 双层换算**：parquet 0/1/2/9 → dict M/F/U → 换算回 0/1/2/9（本次整改根治）
2. **`load_sex_mapping` 的 N+1 预热**：对每条映射逐条查 DictDataModel（service.py:343-352 的 JOIN 范式更优）
3. **`normalize_batch_service` 是伪批量**：for 循环包装 normalize_service，无真正批量化
4. **`_get_dict_type_id` 无缓存**：每次 normalize 都查一次 sys_dict_type
5. **ETL1 的 `etl_engine._preload_dict_cache` 顶部 import DictMappingService 后未使用**（死代码）——本次整改可统一上移到 service.load_all_mappings

### 国标来源
- **HQMS RC001（性别）**：来源于 GB/T 2261.1-2003《个人基本信息分类与代码》
- **HQMS RC030（ABO 血型）**：来源于卫生行业标准 CV04.50.005
- **HQMS RC031（Rh 血型）**：来源于住院病案首页接口标准
- **GB/T 3304-1991（民族）**：中国各民族名称的罗马字母拼写法和代码
- **官方文档**：[住院病案首页接口标准（卫健委 Excel）](https://www.nhc.gov.cn/cms-search/downFiles/a949da2e4875442eac695ba0ef57fa08.xlsx)
