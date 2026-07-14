# 医院注册及 Schema 管理 · 技术实现方案

> **日期**：2026-07-07
> **状态**：设计定稿（已修订），待实现
> **前置决策**：ADR 0001, 0002, 0003, 0004, 0005
> **最后更新**：2026-07-07（基于需求变更修订：医疗数据开放访问、当前阶段不脱敏）

---

## 〇、总体架构图

```
┌────────────────────────────────────────────────────────────────────┐
│  平台域（tenant_id=1）                                              │
│  └── 超级管理员  →  注册医院 + 配置映射 + 触发导入                    │
├────────────────────────────────────────────────────────────────────┤
│  医院管理域（med_hospital + med_mapping_rule，平台级元数据）         │
│  ├── med_hospital: {code, name, tenant_id(FK), status, ...}        │
│  ├── med_mapping_rule: {src→tgt 字段映射规则}                       │
│  └── 映射模板 = template_data.py 常量（非数据库表）                  │
│      → 注册医院时按 template_code 复制规则到 med_mapping_rule        │
│      权限：仅超管 + 该医院租户管理员                                 │
├────────────────────────────────────────────────────────────────────┤
│  医疗数据域（共享表，⚠️ 全部用户可读）                                │
│  ├── med_patient (TenantMixin tenant_id 仅作来源标记)              │
│  ├── med_pathology_specimen (同上)                                 │
│  ├── med_surgery_record (同上)                                     │
│  ├── med_genetic_test (同上)                                       │
│  └── 医院独有表: med_nodule_imaging, med_visit_record...           │
│                                                                    │
│  数据流：                                                          │
│  parquet → ETL引擎 → PostgreSQL (写入时带上 tenant_id)             │
│  查询：任何已认证用户 → 可选 tenant_ids 筛选 → 返回全部可见数据      │
├────────────────────────────────────────────────────────────────────┤
│  前端维度                                                          │
│  ├── 顶部医院筛选器（多选，默认全部）                                │
│  └── 医疗数据查询 API：GET /medical/patients?tenant_ids=2,3        │
└────────────────────────────────────────────────────────────────────┘
```

---

## 一、模块结构

```
backend/app/plugin/module_medical/
├── __init__.py              → 路由注册
├── controller.py            → 现有患者/多模态端点（迁移至 PG 后改 repository）
├── repository.py            → 现有 DuckDB 直读（迁移完成后删除或归档）
├── schema.py                → 现有 Pydantic schema
├── service.py               → 现有 service 层（迁移后改调 PG）
├── dicom/                   → DICOM 影像子模块（不变）
└── hospital/                → 新增：医院注册 & Schema 管理
    ├── __init__.py
    ├── model.py             → HospitalModel + MappingRuleModel + HospitalStatusEnum
    ├── schema.py            → Pydantic 入参/出参 schema
    ├── repository.py        → 数据访问层
    ├── service.py           → 业务逻辑层（含状态机、ETL 触发）
    ├── controller.py        → API 端点
    ├── template_data.py     → 预置映射模板（省医 + 珠江-新桥）
    └── etl_engine.py        → 通用 ETL 执行器
```

---

## 二、数据库模型（SQLAlchemy）

### 2.1 医院注册表 `med_hospital`

> **定位**：平台级元数据表。**不继承 `TenantMixin`**（无 `tenant_id` 自动过滤），所有超管可见全部医院记录。`tenant_id` 仅作为指向 `sys_tenant` 的外键（数据来源关联），不参与隔离。
>
> **CRUD 策略**：`__permission_strategy__ = DATA_SCOPE`，但配合权限点 `hospital:query` 限制仅超管 + 关联租户管理员可访问。

```python
# backend/app/plugin/module_medical/hospital/model.py

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base_model import MappedBase, ModelMixin, UserMixin


class HospitalStatus(str, Enum):
    """医院就绪状态"""
    REGISTERED = "registered"               # 已注册
    MAPPING_CONFIGURED = "mapping_configured"  # 映射已配置
    DATA_IMPORTED = "data_imported"         # 数据已导入
    LIVE = "live"                           # 已上线


class HospitalModel(ModelMixin, UserMixin):
    """医院注册表 — 平台级元数据，每家医院对应一个租户。

    不继承 TenantMixin：所有超管/医院管理员可见全部医院记录，
    通过 API 权限点 hospital:query 控制访问，而非 tenant_id 过滤。
    """

    __tablename__ = "med_hospital"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_med_hospital_tenant"),
        {"comment": "医院注册表（平台级元数据）"},
    )

    # 医院基本信息
    code: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, comment="医院编码（shengyi / zhujiang_xinqiao）"
    )
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="医院名称"
    )
    full_name: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="医院全称"
    )

    # 租户关联
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sys_tenant.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
        comment="关联租户ID",
    )

    # 状态
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=HospitalStatus.REGISTERED.value,
        comment="就绪状态",
    )

    # 机构信息
    contact_name: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="联系人")
    contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="联系电话")
    contact_email: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="联系邮箱")
    address: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="机构地址")

    # 数据导入
    last_import_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="最近导入时间"
    )
    last_import_rows: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="最近导入行数"
    )
    import_error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="导入失败时的错误信息"
    )

    # 关联
    tenant: Mapped["TenantModel"] = relationship("TenantModel", lazy="selectin")
    mapping_rules: Mapped[list["MappingRuleModel"]] = relationship(
        "MappingRuleModel", lazy="selectin", back_populates="hospital"
    )
```

### 2.2 映射规则表 `med_mapping_rule`

```python
class MappingTransform(str, Enum):
    """映射转换类型"""
    RENAME = "rename"           # 字段重命名（源字段名→目标字段名，值不变）
    CONSTANT = "constant"       # 常量填充（目标字段 = 固定值）
    EXPRESSION = "expression"   # 表达式变换（目标字段 = f(源值)）


class MappingRuleModel(ModelMixin, UserMixin):
    """字段映射规则 — (源表, 源字段) → (目标表, 目标字段, 转换)"""

    __tablename__ = "med_mapping_rule"
    __table_args__ = (
        UniqueConstraint(
            "hospital_id", "src_table", "src_field",
            name="uq_med_mapping_rule"
        ),
        {"comment": "字段映射规则表"},
    )

    hospital_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("med_hospital.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属医院",
    )

    # 源
    src_table: Mapped[str] = mapped_column(String(100), nullable=False, comment="源表名")
    src_field: Mapped[str] = mapped_column(String(100), nullable=False, comment="源字段名")

    # 目标
    tgt_table: Mapped[str] = mapped_column(String(100), nullable=False, comment="目标表名")
    tgt_field: Mapped[str] = mapped_column(String(100), nullable=False, comment="目标字段名")

    # 转换
    transform_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=MappingTransform.RENAME.value,
        comment="转换类型",
    )
    transform_value: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="转换值（CONSTANT=常量值 / EXPRESSION=表达式 / RENAME=空）",
    )

    description: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="规则说明"
    )
    sort: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="执行顺序（先核心字段后扩展）"
    )

    # 关联
    hospital: Mapped["HospitalModel"] = relationship(
        "HospitalModel", lazy="selectin", back_populates="mapping_rules"
    )
```

### 2.3 医疗数据统一表（示例 = patient）

所有医疗表继承 `TenantMixin`，获得 `tenant_id` 列（仅作数据来源标记，不做访问隔离，详见 ADR 0005）：

```python
# backend/app/plugin/module_medical/hospital/patient_model.py

from datetime import date

from sqlalchemy import Date, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, TenantMixin, UserMixin


class PatientModel(ModelMixin, TenantMixin, UserMixin):
    """患者基本信息表（统一表）。

    tenant_id 仅作数据来源标记，不做访问隔离（ADR 0005）。
    业务主键 (tenant_id, patient_id) 唯一约束防止重复导入。
    """

    __tablename__ = "med_patient"
    __table_args__ = (
        UniqueConstraint("tenant_id", "patient_id", name="uq_med_patient_tenant_patient"),
        {"comment": "患者基本信息表（统一表）"},
    )

    patient_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="患者编号")
    source_center: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="来源中心（冗余）")
    gender: Mapped[str | None] = mapped_column(String(10), nullable=True, comment="性别")
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="出生日期")
    ethnicity: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="民族")
    native_place: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="籍贯")
    abo_blood_type: Mapped[str | None] = mapped_column(String(10), nullable=True, comment="ABO血型")
    rh_blood_type: Mapped[str | None] = mapped_column(String(10), nullable=True, comment="RH血型")
    smoking_status: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="吸烟状态")
    first_nodule_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="首次发现结节日期")

    # JSON 扩展字段（JSONB，带 GIN 索引）
    visit_counts: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="就诊次数")
    demographics: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="人口学")
    medical_history: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="既往病史")
```

同理：`PathologySpecimenModel`、`SurgeryRecordModel`、`GeneticTestModel`、`NoduleImagingModel`、`IHCResultModel`、`FollowUpModel`、`VisitRecordModel`、`LabResultModel` 等。每张表都必须按其业务粒度加复合唯一约束。

#### 业务主键唯一约束清单

| 表 | 业务粒度 | 唯一约束 |
|----|---------|---------|
| `med_patient` | 每患者一行 | `(tenant_id, patient_id)` |
| `med_pathology_specimen` | 每份病理标本/报告 | `(tenant_id, specimen_id)` |
| `med_surgery_record` | 每次手术 | `(tenant_id, patient_id, surgery_date, procedure_name)` |
| `med_genetic_test` | 每份基因检测报告 | `(tenant_id, test_id)` |
| `med_visit_record` | 每次就诊 | `(tenant_id, patient_id, visit_id)` |
| `med_nodule_imaging` | 一次CT中一个结节 | `(tenant_id, exam_id, nodule_no)` |
| `med_ihc_result` | 每份标本的免疫组化 | `(tenant_id, specimen_id)` |
| `med_follow_up` | 每患者（或每随访周期） | `(tenant_id, patient_id)` |
| `med_lab_result` | 每条检验子项 | `(tenant_id, report_id, item_name)` |

> **作用**：防止 ETL 重复导入产生重复行；同时作为"先 DELETE 再 INSERT"幂等性的补充保险——DELETE WHERE tenant_id 已清除该院数据，但若并发或异常残留，唯一约束确保不会插入重复。

公共 Model Mixin:

```python
class MedicalTableMixin(TenantMixin):
    """医疗表公共 Mixin — 标记此表为'开放访问'。

    继承此类表示 tenant_id 仅作数据来源标记，
    CRUD 查询层不应按 tenant_id 做访问隔离（ADR 0005）。
    """
    __abstract__ = True

    # 标记：CRUDBase.__tenant_condition() 检测此标记跳过过滤
    __medical_open_access__ = True
```

### 2.4 索引策略

| 表 | 索引 | 类型 |
|---|---|---|
| `med_hospital` | `tenant_id` | B-tree（唯一） |
| `med_mapping_rule` | `hospital_id` | B-tree |
| `med_mapping_rule` | `(hospital_id, src_table, src_field)` | 复合唯一 |
| `med_patient` | `tenant_id` | B-tree |
| `med_patient` | `(tenant_id, patient_id)` | 复合 B-tree |
| `med_patient` | `medical_history` | GIN（JSONB @> 查询） |
| `med_genetic_test` | `driver_mutations` | GIN |
| `med_pathology_specimen` | `staging` | GIN |

---

## 三、API 端点设计

### 3.1 医院管理

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| `GET` | `/medical/hospital` | `hospital:query` | 分页列表 |
| `POST` | `/medical/hospital` | `hospital:create` | 注册医院（选模板预填映射） |
| `GET` | `/medical/hospital/{id}` | `hospital:query` | 详情（含当前状态 + 映射规则数） |
| `PUT` | `/medical/hospital/{id}` | `hospital:edit` | 更新医院信息（非 LIVE 状态） |
| `GET` | `/medical/hospital/{id}/template` | `hospital:query` | 查看可用映射模板 |
| `GET` | `/medical/hospital/{id}/mappings` | `hospital:mapping:query` | 映射规则列表 |
| `PUT` | `/medical/hospital/{id}/mappings` | `hospital:mapping:edit` | 批量更新映射规则 |
| `POST` | `/medical/hospital/{id}/import` | `hospital:import` | 触发 ETL 导入 |
| `GET` | `/medical/hospital/{id}/import/status` | `hospital:query` | 查看导入状态/报告 |
| `POST` | `/medical/hospital/{id}/online` | `hospital:online` | 上线发布 |
| `POST` | `/medical/hospital/{id}/offline` | `hospital:offline` | 下线（退回 DATA_IMPORTED） |

> **医院管理权限**：以上所有医院管理 API 仅超管（`is_superuser=1`）可操作。映射查询可额外开放给关联医院的租户管理员。

### 3.2 医疗数据查询（迁移后替代现有 controller）

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| `GET` | `/medical/patients` | `medical:query` | 患者分页（可选 `tenant_ids` 筛选，默认全部） |
| `GET` | `/medical/patients/{pid}` | `medical:query` | 患者多模态详情（可选 `tenant_ids` 消歧同名 patient_id） |

> **注意**：医疗数据查询 API 在根 `/medical/` 下，不需要 `/hospital/{id}` 前缀——因为数据是全部可访问的，医院仅作为筛选维度。
>
> **权限**：`medical:query` 为公共权限，**所有已认证角色默认拥有**——不做医院级隔离。
>
> **筛选参数命名**：直接用 `tenant_ids`（医疗表上的实际列名），不引入 `hospital_ids` 这一冗余概念。`med_hospital.tenant_id` 与医疗表 `tenant_id` 一一对应，前端从医院列表 API 拿到 `tenant_id` 后直接作为筛选值传递。

---

## 四、Schema（Pydantic）

```python
# backend/app/plugin/module_medical/hospital/schema.py

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# 医院
# --------------------------------------------------------------------------- #

class HospitalCreate(BaseModel):
    """医院注册入参"""
    code: str = Field(..., description="医院编码")
    name: str = Field(..., description="医院名称")
    full_name: str | None = Field(None, description="医院全称")
    template_code: str | None = Field(None, description="映射模板编码（shengyi / zhujiang_xinqiao）")
    contact_name: str | None = Field(None, description="联系人")
    contact_phone: str | None = None
    contact_email: str | None = None
    address: str | None = None


class HospitalOut(BaseModel):
    """医院出参"""
    id: int
    code: str
    name: str
    full_name: str | None
    tenant_id: int
    status: str
    contact_name: str | None
    contact_phone: str | None
    contact_email: str | None
    address: str | None
    last_import_time: datetime | None
    last_import_rows: int
    mapping_count: int = 0
    created_time: datetime


class HospitalPageOut(BaseModel):
    page_no: int
    page_size: int
    total: int
    has_next: bool
    items: list[HospitalOut]


# --------------------------------------------------------------------------- #
# 映射规则
# --------------------------------------------------------------------------- #

class MappingRuleIn(BaseModel):
    src_table: str
    src_field: str
    tgt_table: str
    tgt_field: str
    transform_type: str = "rename"    # rename / constant / expression
    transform_value: str | None = None
    description: str | None = None
    sort: int = 0


class MappingRuleOut(MappingRuleIn):
    id: int
    hospital_id: int
    created_time: datetime


class MappingRuleBatch(BaseModel):
    """批量更新映射规则 — 全量替换该院映射"""
    rules: list[MappingRuleIn]


# --------------------------------------------------------------------------- #
# ETL
# --------------------------------------------------------------------------- #

class EtlImportResponse(BaseModel):
    task_id: str
    status: str    # pending / running / completed / failed


class EtlImportStatus(BaseModel):
    task_id: str
    status: str
    total_rows: int
    imported_rows: int
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
```

---

## 五、Service 层核心逻辑

### 5.1 医院注册（含状态机 + 租户联动）

```python
# backend/app/plugin/module_medical/hospital/service.py

class HospitalService:

    @classmethod
    async def create_hospital(cls, auth: AuthSchema, data: HospitalCreateSchema) -> dict:
        """
        注册医院：
        1. 调用 TenantService 创建对应租户
        2. 创建 HospitalModel
           - 初始状态：status=registered
           - 若指定 template_code 且模板非空 → 复制模板规则到 med_mapping_rule
             后立即推进状态为 mapping_configured（"用了模板即视为映射已配置"）
           - 若未指定模板或模板为空 → 保持 registered（待手动配置映射后再推进）
        3. 返回 hospital + tenant_id
        """
        ...

    @classmethod
    async def trigger_import(cls, auth: AuthSchema, hospital_id: int) -> str:
        """
        触发 ETL 导入：
        1. 校验状态为 mapping_configured
        2. 创建异步任务（Celery / asyncio.create_task / workflow engine）
        3. 状态推进为 data_imported（导入完成后由回调设置）
        4. 返回 task_id
        """
        ...

    @classmethod
    async def go_online(cls, auth: AuthSchema, hospital_id: int) -> None:
        """
        上线：
        1. 校验状态为 data_imported
        2. 最终数据校验（行数 > 0 / 必要字段非空率检查）
        3. 状态 → live
        4. 日志 + 通知
        """
        ...
```

**初始状态语义澄清**：是否使用模板决定初始状态——用了模板即视为映射已就绪（`mapping_configured`）；空模板/未选模板则停在 `registered`。注册向导里的"确认映射"步骤对应用户对模板预填结果的人工确认/微调，是可选动作，不强制推进状态。

### 5.2 状态机

```python
# 状态流转规则
TRANSITIONS = {
    HospitalStatus.REGISTERED: [HospitalStatus.MAPPING_CONFIGURED],
    HospitalStatus.MAPPING_CONFIGURED: [HospitalStatus.DATA_IMPORTED, HospitalStatus.MAPPING_CONFIGURED],
    #                                                              ↑ 允许重新编辑映射后再次导入
    HospitalStatus.DATA_IMPORTED: [HospitalStatus.LIVE, HospitalStatus.DATA_IMPORTED],
    #                                                  ↑ 允许重新导入
    HospitalStatus.LIVE: [HospitalStatus.DATA_IMPORTED],  # 下线（重新导入也是先下线）
}

# 允许直接编辑映射的状态（LIVE 必须先下线到 DATA_IMPORTED 才能改）
MAPPING_EDITABLE = {HospitalStatus.REGISTERED, HospitalStatus.MAPPING_CONFIGURED, HospitalStatus.DATA_IMPORTED}
```

**LIVE 状态修改映射的流程**（与"幂等性：重新导入 = 先 DELETE 再 INSERT"对齐）：

```
医院处于 LIVE
   │
   ├── 用户点"修改映射" → 拒绝（提示需先下线）
   │
   └── 用户点"下线" → 状态退回 DATA_IMPORTED → 此时可编辑映射
                                                    │
                                                    └── 编辑后重新触发导入（覆盖原数据）→ 状态推进到 DATA_IMPORTED → 上线
```

**关键规则**：
- LIVE 状态下，映射编辑 API 返回 409（"请先下线"）
- DATA_IMPORTED 状态下编辑映射后，不自动改变状态；只有显式触发"重新导入"才会刷新数据并保持 DATA_IMPORTED
- 重新导入（已存在数据时）必须显式确认覆盖

---

## 六、ETL 引擎

### 6.1 架构

```
parquet 文件
    │
    ▼
┌────────────────────────────────────────────────────┐
│  ETL Engine                                        │
│                                                    │
│  1. 加载 MappingRuleModel → 按 src_table 分组建规则 │
│  2. DuckDB 读取源 parquet                          │
│  3. 对每张源表：                                    │
│     a. 字段映射（rename / constant / expression）  │
│     b. 表级硬编码后处理钩子（行展开/跨表关联）       │
│     c. tenant_id 自动注入（取自 med_hospital.tenant_id）  │
│  4. 写入 PostgreSQL（批量 INSERT）                  │
│     • 冲突处理：ON CONFLICT DO NOTHING              │
└────────────────────────────────────────────────────┘
```

### 6.2 配置驱动 vs 硬编码的边界

**核心原则**：字段级转换走映射表配置，表级结构变换硬编码在 ETL 任务的 per-table handler 中。

| 源表 | 配置驱动（映射表） | 硬编码 handler |
|------|------|---------------|
| `patient` | 全字段 | — |
| `pathology_specimen`（统一表）| 核心字段 + JSON 扩展 | — |
| `genetic_test`（统一表）| 核心字段 | — |
| `surgery_record`（省医）| procedure_detail 等 JSON 字段 | **行展开**：`inpatient_front_page.surgeries[]` 数组拆为多行（unpivot） |
| `surgery_record`（珠江-新桥）| 全字段 | — |
| `ihc_result` | 标志物 JSON | **跨表关联**：通过 `specimen_id` JOIN `med_pathology_specimen` 校验存在性 |
| `nodule_imaging` | 全字段 | — |
| `lab_result`（省医）| 全字段 | — |

**实现机制**：

```python
# etl_engine.py

@dataclass
class TableHandler:
    """每张源表的 ETL 处理器"""
    src_table: str
    tgt_table: str
    # 字段映射（来自 med_mapping_rule）
    field_mappings: list[MappingRuleModel]
    # 可选的表级后处理钩子（行展开、跨表关联等硬编码）
    post_transform: Callable[[list[dict]], list[dict]] | None = None


# 硬编码 handler 注册表（仅结构复杂的表需要）
TABLE_HANDLERS: dict[str, TableHandler] = {
    # 省医手术记录：surgeries[] 行展开
    "shengyi/surgery_record": TableHandler(
        src_table="inpatient_front_page",
        tgt_table="med_surgery_record",
        field_mappings=<从 DB 加载>,
        post_transform=expand_shengyi_surgeries,  # 一行变多行
    ),
    # 其余表无 post_transform，纯字段映射
}


def expand_shengyi_surgeries(rows: list[dict]) -> list[dict]:
    """把 inpatient_front_page.surgeries 数组拆为多行（一行一手术）。"""
    out = []
    for row in rows:
        surgeries = row.get("surgeries") or []
        for surg in surgeries:
            out.append({**row, **surg, "surgeries": None})
    return out
```

**新增医院的处理**：纯字段映射的表无需写代码；只有涉及行展开/跨表关联的表才需要在该医院的 ETL 配置中注册一个 Python handler。

### 6.3 关键设计

- **DuckDB 作为 ETL 读取器保留** — 不用来查询，但用 `read_parquet()` 读取文件然后 `df to 列表 → PostgreSQL` 的管线很高效
- **PostgreSQL 写入用 SQLAlchemy Core** — 不用 ORM（慢），用 `insert().values(rows_batch)`
- **批量大小**：每批 500 行
- **事务**：每张表全量导入在一个事务中（导入失败 = 全表回滚，可重新导入）
- **幂等性**：重新导入 = 先 `DELETE FROM xxx WHERE tenant_id = ?` 再 INSERT（同一医院数据原子更新）；唯一约束（见 2.3 业务主键清单）作为并发残留的兜底
- **任务状态**：用 Redis 跟踪 ETL 任务状态 `etl:status:{hospital_id}` → `{status, processed, total, error}`
- **脱敏/编码**：当前阶段不做（ADR 0005）；完整需求书定义后，在 post_transform 钩子或 Repository 出参层增加

---

## 七、预置映射模板数据

> **定位**：模板是 Python 常量（`template_data.py`），**不是数据库表**。注册医院时按 `template_code` 将模板里的规则批量复制到 `med_mapping_rule`；之后该医院的映射规则可独立编辑，与模板解耦。

```python
# backend/app/plugin/module_medical/hospital/template_data.py

TEMPLATES = {
    "shengyi": {
        "name": "广东省人民医院（省医）完整映射",
        "description": "省医全量表映射，包含统一表 + 医院独有表",
        "rules": [
            # ---- patient 统一表 ----
            {"src_table": "patient", "src_field": "patient_id", "tgt_table": "med_patient", "tgt_field": "patient_id", "transform_type": "rename"},
            {"src_table": "patient", "src_field": "source_center", "tgt_table": "med_patient", "tgt_field": "source_center", "transform_type": "constant", "transform_value": "省医"},
            {"src_table": "patient", "src_field": "gender", "tgt_table": "med_patient", "tgt_field": "gender", "transform_type": "rename"},
            {"src_table": "patient", "src_field": "birth_date", "tgt_table": "med_patient", "tgt_field": "birth_date", "transform_type": "rename"},
            # ... 省略其余字段，均为 rename
            {"src_table": "patient", "src_field": "ethnicity", "tgt_table": "med_patient", "tgt_field": "ethnicity", "transform_type": "rename"},
            {"src_table": "patient", "src_field": "native_place", "tgt_table": "med_patient", "tgt_field": "native_place", "transform_type": "rename"},
            {"src_table": "patient", "src_field": "abo_blood_type", "tgt_table": "med_patient", "tgt_field": "abo_blood_type", "transform_type": "rename"},
            {"src_table": "patient", "src_field": "rh_blood_type", "tgt_table": "med_patient", "tgt_field": "rh_blood_type", "transform_type": "rename"},
            # smoking_status / first_nodule_date 省医原始无 → 目标不填映射，由 ETL 引擎填充 null

            # ---- pathology_specimen 统一表 ----
            {"src_table": "pathology_report", "src_field": "report_id", "tgt_table": "med_pathology_specimen", "tgt_field": "specimen_id", "transform_type": "rename"},
            # ... 其余字段
        ],
    },

    "zhujiang_xinqiao": {
        "name": "珠江-新桥完整映射",
        "description": "珠江-新桥全量表映射",
        "rules": [
            {"src_table": "patient", "src_field": "patient_id", "tgt_table": "med_patient", "tgt_field": "patient_id", "transform_type": "rename"},
            {"src_table": "patient", "src_field": "source_center", "tgt_table": "med_patient", "tgt_field": "source_center", "transform_type": "rename"},
            {"src_table": "patient", "src_field": "birth_year", "tgt_table": "med_patient", "tgt_field": "birth_date", "transform_type": "expression", "transform_value": "year_to_date"},  # 函数名 key，见 6.x TRANSFORM_FUNCTIONS
            # ... 其余字段
        ],
    },
}
```

---

## 八、Alembic 迁移策略

### 8.1 迁移：医院管理表

> **注意**：当前仓库的迁移链 HEAD 是 `0306640395d9`（v3.1.0 插件系统）。新迁移必须 `down_revision = "0306640395d9"`，不能用 `"002"`——`002` 不是链的末端。

```python
"""create hospital management tables + medical data tables (Phase 0)

Revision ID: a1b2c3d4e5f6
Revises: 0306640395d9
Create Date: 2026-07-07
"""

revision = "a1b2c3d4e5f6"
down_revision = "0306640395d9"


def upgrade():
    # 1. med_hospital
    op.create_table("med_hospital", ...)

    # 2. med_mapping_rule
    op.create_table("med_mapping_rule", ...)

    # 3. med_patient（示例）
    op.create_table("med_patient",
        sa.Column("id", Integer, primary_key=True),
        sa.Column("tenant_id", Integer, ForeignKey("sys_tenant.id"), nullable=False),
        sa.Column("patient_id", String(64), nullable=False),
        # ... 核心字段
        sa.Column("medical_history", JSONB, nullable=True),
        sa.Column("visit_counts", JSONB, nullable=True),
        sa.Column("demographics", JSONB, nullable=True),
        # ... ModelMixin 字段
    )
    op.create_index("ix_med_patient_tenant_patient", "med_patient", ["tenant_id", "patient_id"])
    op.create_index("ix_med_patient_medical_history", "med_patient", ["medical_history"],
                    postgresql_using="gin")

    # 4. med_pathology_specimen, med_surgery_record, med_genetic_test, ...
    # 5. med_nodule_imaging, med_ihc_result, med_follow_up（珠江-新桥独有）
    # 6. med_visit_record, med_lab_result, ...（省医独有）


def downgrade():
    # 逆序删除所有 med_* 表
    ...
```

### 8.2 数据迁移（初始导入）

作为 **Alembic 迁移的 after-upgrade hook** 或 **独立脚本**：

- 由省医 + 珠江-新桥的模板中硬编码触发首次导入
- `python -m app.scripts.seed_hospitals --template shengyi --data-dir docs/zhujiang_xinqiao_parq/...`
- 或者：先跑 migration 再通过管理后台"触发导入"按钮手动导入

---

## 九、前端结构建议

```
frontend/web/src/views/module_medical/
├── patient/                   → 现有患者列表/详情
└── hospital/                  → 新增
    ├── index.vue              → 医院列表 + 状态展示
    ├── create.vue             → 注册向导（步骤：基本信息 → 选模板 → 确认映射）
    ├── mapping.vue            → 映射规则编辑器（表格 + 字段下拉）
    ├── import.vue             → 导入管理（触发/进度/错误/重新导入）
    └── components/
        ├── StatusBadge.vue    → 状态徽标
        ├── MappingTable.vue   → 映射规则表格
        └── ImportProgress.vue → 导入进度条
```

---

## 十、医院筛选维度（非隔离）

> **核心原则**：`tenant_id` 仅作为数据来源标记，不作为访问控制边界。所有已认证用户可查看全部医院数据。

前端顶部栏提供**医院多选筛选器**——默认不选（= 看到全部），用户可缩小范围：

```
┌──────────────────────────────────────┐
│  筛选： [🏥 全部医院 ▼]               │
│                                      │
│  弹出面板（多选）：                    │
│  ├── ☑ 广东省人民医院 (tenant_id=2)   │
│  ├── ☐ 珠江-新桥     (tenant_id=3)   │
│  └── ──────                          │
│      ☑ 全选    清除选择              │
└──────────────────────────────────────┘

选择后 → 前端将选中医院的 tenant_id 列表作为参数：
  GET /medical/patients?tenant_ids=2,3
→ 后端 query:
  SELECT * FROM med_patient WHERE tenant_id IN (2, 3)
→ 不选（空列表/缺省）时 → 不加 tenant_id 过滤 → 返回全部
```

**关键实现规则：**

1. 医疗查询 repository 层**不调用 `CRUDBase.__tenant_condition()`**，不使用 `auth.user.tenant_id` 做过滤
2. `tenant_ids` 为可选参数，默认空列表（= 全部）；显式传值才加 WHERE
3. `tenant_ids` 参数严格做类型校验（只允许正整数列表），防止注入
4. **不要引入 `hospital_id` 冗余列**——`med_hospital.tenant_id` 与医疗表 `tenant_id` 已经 1:1 对应，加冗余只会带来不一致风险

**医院列表来源**：前端通过 `GET /medical/hospital` 拿到所有 LIVE 状态的医院，每条返回 `id, name, tenant_id`；多选筛选器直接使用 `tenant_id` 作为提交值。

---

## 十一、实施里程碑

| 阶段 | 内容 | 产出 | 验证方式 |
|------|------|------|---------|
| **M1** | 医院注册 + 租户联动 | `med_hospital` 表 + 注册 API + 列表 API | 注册后查 tenant + hospital 两表都有记录 |
| **M2** | 映射规则管理 | `med_mapping_rule` 表 + CRUD API + 模板数据 | 用模板注册医院后 mappings 列表非空 |
| **M3** | ETL 引擎 + Demo 导入 | etl_engine.py + 珠江-新桥 parquet → PostgreSQL | **导入后立即用 M4 查询验证**：med_patient 行数 == parquet 行数 |
| **M4** | 医疗数据 PG 查询 | patient 列表/详情迁移至 SQLAlchemy + 可选 tenant_ids 筛选（非隔离） | 调 API 验证导入结果，确认无 tenant_id 自动过滤 |
| **M5** | 就绪状态机 + 上下线 | 状态流转 API + 前端状态展示 | 状态机各路径覆盖测试 |
| **M6** | 前端 UI | 列表页 + 注册向导 + 映射编辑器 + 导入管理 | 端到端走通 |

> **M3 和 M4 强耦合**：ETL 导入后必须有 PG 查询接口验证导入正确性。建议 M3 完成时同步交付一个最小可用的 M4 查询端点（即使只是 `SELECT count(*)`），不要等 M4 阶段才开始验证。

---

## 十二、风险与注意事项

1. **JSONB 表达式安全性** — `transform_type=expression` 的 `transform_value` 严禁直接 `eval()`/`exec()`，存在任意代码执行风险。`ast.literal_eval()` 也无法执行表达式（只能解析字面量），不适用。

   **采用方案：预定义转换函数字典 + 函数名注册**

   ```python
   # etl_engine.py

   # 预定义的表达式函数（仅支持已知转换，不可任意扩展）
   TRANSFORM_FUNCTIONS: dict[str, Callable[[Any], Any]] = {
       # 珠江-新桥 birth_year (int) → birth_date (str YYYY-01-01)
       "year_to_date": lambda val: f"{int(val)}-01-01" if val else None,
       # 大小写标准化
       "upper": lambda val: val.upper() if val else None,
       "lower": lambda val: val.lower() if val else None,
   }

   def apply_expression(func_key: str, value: Any) -> Any:
       """安全求值：仅允许 TRANSFORM_FUNCTIONS 字典里已注册的函数。"""
       fn = TRANSFORM_FUNCTIONS.get(func_key)
       if fn is None:
           raise ValueError(f"未注册的转换函数: {func_key}")
       return fn(value)
   ```

   - `med_mapping_rule.transform_value` 存储**函数名 key**（如 `"year_to_date"`），而非任意表达式字符串
   - 新增转换需开发注册函数并在 dict 中加 key（受控扩展，非任意执行）
   - 前端映射编辑器从 `TRANSFORM_FUNCTIONS` 的可用函数列表中下拉选择

2. **大文件 ETL 超时** — parquet 文件如果 > 1GB，`asyncio.create_task` 中的 DuckDB 读取 + PG 写入可能超时。
   - ✅ 措施：用系统已有 `module_task` 工作流引擎编排 ETL 为正式任务节点，支持进度追踪

   > **当前阶段不涉及**：脱敏规则（由完整需求书定义）、patient_id 重编码（同上）

3. **JSONB 索引膨胀** — 大体积 JSONB 的 GIN 索引可能膨胀。
   - ✅ 措施：GIN 索引仅建在需要查询的 JSONB 列上（`medical_history`、`driver_mutations`、`staging`），不盲目标记所有 JSONB 列

4. **多模态接口的向前兼容** — `module_medical/controller.py` 现有端点不变，仅迁移 `repository.py` 从 DuckDB → SQLAlchemy。
   - ✅ 前端无需修改（API response 结构不变）
   - ⚠️ `source_center` 字段的显示从 FK 关联变为原始字符串；如需友好显示需前端做映射表

5. **租户过滤绕过方案 — 关键实现细节** — 现有 `CRUDBase.__tenant_condition()` 会对含 `tenant_id` 列的表按 `auth.user.tenant_id` 自动过滤。医疗表继承 `TenantMixin` 后也会被这套逻辑影响，必须显式绕过。
   - ✅ 方案 A（推荐）：医疗表查询使用**独立 Repository 类**（不继承 CRUDBase），自行编写 SQLAlchemy 查询，物理隔离不依赖自动过滤
   - ✅ 方案 B：继承 CRUDBase 但在 `__tenant_condition()` 检查 `__medical_open_access__` 标记返回 `[]`（已在 MedicalTableMixin 2.3 定义此标记）
   - **推荐方案 A** — 最清晰，与平台系统表的权限体系完全解耦；医疗数据有自己的查询路径

6. **未来发展预留** — 完整需求书定义脱敏规则后：
   - ETL 引擎增加脱敏转换层（`TRANSFORM_FUNCTIONS` 加 `desensitize_id` / `encode_patient_id` 等注册函数）
   - 或更推荐：**在 Repository 出参层统一做脱敏**（而不改写入数据），保持原始数据完整性
   - 此变更对当前设计无结构冲击——因为 Repository 已是独立层
