"""exam_type 值域对齐 all_modalities.json 26 键（+Other = 27 值）

⚠️ 本迁移文件 2026-09-17 状态：与 j0k1l2m3n4o5 同为 **DDL/DML 文档归档**，
**不通过 alembic 推动**（dev_h1963 库无 alembic_version 表，upgrade head 会
从 base 重放全部历史迁移而失败）。

实际应用：
1. 数据与字典变更由 `backend/sql/postgres/0023-exam-type-modalities-dict.sql`
   （幂等，可重复执行）在目标库手工执行；2026-09-17 已在 dev_h1963 应用。
2. `ADD CONSTRAINT lnrs_anon_ck_exam_type` 因 `lnrs_anon_exam` 属主为
   `postgres`（lnrs 角色无 ALTER 权限），由
   `backend/sql/postgres/0022-add-exam-type-check-manual.sql` 以 postgres
   身份手工执行。

---

背景

`docs/all_modalities.json` 是平台 modality 权威定义（26 键），而
`lnrs_anon_exam.exam_type` 的 ETL 词表沿用旧 10 值（CT/Pathology/Genetic/
IHC/PETCT/Radiology/Ultrasound/MR/ECG/Other），两套词表不一致。本迁移把
exam_type 全链路（存量数据、字典、映射、ETL 白名单、ORM 约束）对齐 26 键，
并加 CHECK 约束锁死值域。

值域（27 值 = 26 键 + Other）：

.. code-block:: text

    CT pathology_WSI pathology_text gene medical_record imaging_report
    basic_medical_info diagnosis drug_prescription medical_orders
    medical_testing radiology ultrasound pulmonary_function MRI
    nuclear_medicine bronchoscope ECG case_history progress_note basic_info
    inhospital_record IHC_record operation anesthesia nursing Other

旧值 → 新值改名映射（7 项）：

========  ==================
旧值      新值
========  ==================
Pathology pathology_text
Genetic   gene
IHC       IHC_record
MR        MRI
Radiology radiology
Ultrasound ultrasound
PETCT     nuclear_medicine
========  ==================

CT / ECG / Other 不变。

数据变更（dev_h1963 实测 rowcount，2026-09-17）

- lnrs_anon_exam 改名：Pathology 189,966 / Ultrasound 181,691 /
  Radiology 170,104 / MR 62,059 / Genetic 1,309（IHC、PETCT 无存量），
  共 605,129 行
- sys_dict_data med_exam_type：7 项原地改名（dict_data_id 外键自动跟随，
  med_dict_mapping 无需更新），补齐 17 键；Lab/Order 历史项保留
- med_dict_mapping（301 examClass）升级 6 项重指向新字典行：
  心电图→ECG、放射→radiology、磁共振→MRI、核医学→nuclear_medicine、
  肺功能→pulmonary_function、气管镜→bronchoscope
  （胃肠镜/耳鼻喉/其他/体检/泌外维持 Other）

代码同步

- anon_model.AnonExamModel：CheckConstraint("lnrs_anon_ck_exam_type")
- anon_etl_engine：_EXAM_TYPE_DICT_VALUES 扩为 27 值、新增
  _EXAM_TYPE_LEGACY_ALIASES（7 旧值别名，兼容历史 parquet/适配层输出）、
  _CENTER_PARQUET_SPECS 11 处写死 exam_type 更新
- anon_medical_query.EXAM_TYPE_TO_MODALITY 补新键分组
- app/scripts/data/sys_dict_data.json 种子同步改名

---

由于本文件不通过 alembic 推动，upgrade() / downgrade() 留空实现，
仅保留 revision 元数据以供 alembic heads 报告完整性。
"""

from collections.abc import Sequence

revision: str = "k1l2m3n4o5p6"
down_revision: str | None = "j0k1l2m3n4o5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """DDL/DML 已于 2026-09-17 在 dev_h1963 手工执行（0023 SQL + 一次性脚本）。

    详见模块 docstring 与 backend/sql/postgres/0023-exam-type-modalities-dict.sql、
    0022-add-exam-type-check-manual.sql。
    """
    # noop: not driven by alembic on dev_h1963


def downgrade() -> None:
    """回退路径：0022 SQL 末尾附 DROP CONSTRAINT；改名逆向映射见模块 docstring。

    本文件不通过 alembic 推动，downgrade() 留空实现。
    """
    # noop: not driven by alembic on dev_h1963
