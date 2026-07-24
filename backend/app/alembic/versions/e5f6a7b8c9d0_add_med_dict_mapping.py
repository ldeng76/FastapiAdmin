"""add med_dict_mapping + enum-to-varchar migration

Revision ID: e5f6a7b8c9d9
Revises: d4e5f6a7b8c9
Create Date: 2026-07-23

ADR-0008 实施：医疗领域字典与值级映射。
- 新建 med_dict_mapping / med_dict_unmatched 表
- 插入 med_sex / med_exam_type / med_laterality / med_smoking_status 字典种子
- 插入菜单 + 权限点
- ENUM → VARCHAR(10) + CHECK（lnrs_anon_patient.sex, lnrs_anon_exam_finding.laterality）
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. 建 med_dict_mapping 表
    # ------------------------------------------------------------------
    op.create_table(
        "med_dict_mapping",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, comment="主键ID"),
        sa.Column("uuid", sa.String(64), nullable=False, unique=True, comment="UUID全局唯一标识"),
        sa.Column("status", sa.String(10), nullable=False, default="0", comment="状态(0:正常 1:禁用)"),
        sa.Column("description", sa.Text(), nullable=True, comment="备注/描述"),
        sa.Column("created_time", sa.DateTime(), nullable=False, default=sa.func.now(), comment="创建时间"),
        sa.Column("updated_time", sa.DateTime(), nullable=False, default=sa.func.now(), comment="更新时间"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, default=False, comment="是否已删除"),
        sa.Column("deleted_time", sa.DateTime(), nullable=True, comment="删除时间"),
        # 审计字段
        sa.Column(
            "created_id", sa.Integer(),
            sa.ForeignKey("sys_user.id", ondelete="SET NULL", onupdate="CASCADE"),
            nullable=True, comment="创建人ID",
        ),
        sa.Column(
            "updated_id", sa.Integer(),
            sa.ForeignKey("sys_user.id", ondelete="SET NULL", onupdate="CASCADE"),
            nullable=True, comment="更新人ID",
        ),
        sa.Column(
            "deleted_id", sa.Integer(),
            sa.ForeignKey("sys_user.id", ondelete="SET NULL", onupdate="CASCADE"),
            nullable=True, comment="删除人ID",
        ),
        # 业务字段
        sa.Column(
            "tenant_id", sa.Integer(),
            sa.ForeignKey("sys_tenant.id", ondelete="RESTRICT", onupdate="CASCADE"),
            nullable=False, comment="租户ID",
        ),
        sa.Column(
            "hospital_id", sa.Integer(),
            sa.ForeignKey("med_hospital.id", ondelete="CASCADE"),
            nullable=False, index=True, comment="所属医院",
        ),
        sa.Column(
            "dict_type_id", sa.Integer(),
            sa.ForeignKey("sys_dict_type.id", ondelete="CASCADE"),
            nullable=False, index=True, comment="字典类型ID",
        ),
        sa.Column(
            "dict_data_id", sa.Integer(),
            sa.ForeignKey("sys_dict_data.id", ondelete="CASCADE"),
            nullable=True, index=True, comment="映射到的字典数据ID",
        ),
        sa.Column("raw_label", sa.String(200), nullable=False, comment="原始标签（医院上报文本）"),
        sa.Column("raw_value", sa.String(200), nullable=True, comment="原始值（如有）"),
        sa.Index("ix_med_dict_mapping_hospital_type_lower", "hospital_id", "dict_type_id"),
        # 普通列唯一约束（ORM 兼容），表达式唯一约束在下方用原生 SQL 创建
        sa.UniqueConstraint(
            "hospital_id", "dict_type_id", "raw_label",
            name="uq_med_dict_mapping",
        ),
        sa.Index("ix_med_dict_mapping_tenant", "tenant_id"),
        comment="医疗字典值映射表（医院原始标签 → 标准字典值）",
    )

    # 替换为表达式唯一约束：lower(raw_label) 大小写归一
    op.execute("ALTER TABLE med_dict_mapping DROP CONSTRAINT IF EXISTS uq_med_dict_mapping")
    op.execute(
        "CREATE UNIQUE INDEX uq_med_dict_mapping_expr "
        "ON med_dict_mapping (hospital_id, dict_type_id, lower(raw_label))"
    )

    # ------------------------------------------------------------------
    # 2. 建 med_dict_unmatched 表
    # ------------------------------------------------------------------
    op.create_table(
        "med_dict_unmatched",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, comment="主键ID"),
        sa.Column("uuid", sa.String(64), nullable=False, unique=True, comment="UUID全局唯一标识"),
        sa.Column("status", sa.String(10), nullable=False, default="0", comment="状态(0:未处理 1:已忽略 2:已解决)"),
        sa.Column("description", sa.Text(), nullable=True, comment="备注/描述"),
        sa.Column("created_time", sa.DateTime(), nullable=False, default=sa.func.now(), comment="创建时间"),
        sa.Column("updated_time", sa.DateTime(), nullable=False, default=sa.func.now(), comment="更新时间"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, default=False, comment="是否已删除"),
        sa.Column("deleted_time", sa.DateTime(), nullable=True, comment="删除时间"),
        # 业务字段
        sa.Column(
            "tenant_id", sa.Integer(),
            sa.ForeignKey("sys_tenant.id", ondelete="RESTRICT", onupdate="CASCADE"),
            nullable=False, comment="租户ID",
        ),
        sa.Column(
            "hospital_id", sa.Integer(),
            sa.ForeignKey("med_hospital.id", ondelete="CASCADE"),
            nullable=False, index=True, comment="所属医院",
        ),
        sa.Column(
            "dict_type_id", sa.Integer(),
            sa.ForeignKey("sys_dict_type.id", ondelete="CASCADE"),
            nullable=False, index=True, comment="字典类型ID",
        ),
        sa.Column("raw_label", sa.String(200), nullable=False, comment="原始标签"),
        sa.Column("raw_value", sa.String(200), nullable=True, comment="原始值"),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, default=1, comment="出现次数"),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True, comment="最近出现时间"),
        sa.Column("resolution", sa.String(20), nullable=True, comment="处理方式(ignore/resolve)"),
        sa.Column("resolved_by", sa.Integer(), nullable=True, comment="处理人ID"),
        sa.Column("resolved_at", sa.DateTime(), nullable=True, comment="处理时间"),
        sa.Column(
            "resolved_as_mapping_id", sa.Integer(),
            sa.ForeignKey("med_dict_mapping.id", ondelete="SET NULL"),
            nullable=True, comment="解决为的映射ID",
        ),
        sa.UniqueConstraint("hospital_id", "dict_type_id", "raw_label", name="uq_med_dict_unmatched"),
        sa.Index("ix_med_dict_unmatched_tenant", "tenant_id"),
        sa.Index("ix_med_dict_unmatched_status", "status"),
        comment="医疗字典未匹配记录（待人工干预）",
    )

    # ------------------------------------------------------------------
    # 3. 插入 med_* 字典种子
    # ------------------------------------------------------------------
    conn = op.get_bind()

    # sys_dict_type 表引用
    metadata = sa.MetaData()
    dict_type_table = sa.Table(
        "sys_dict_type", metadata,
        sa.Column("id", sa.Integer()),
        sa.Column("dict_name", sa.String()),
        sa.Column("dict_type", sa.String()),
        sa.Column("status", sa.String()),
        sa.Column("description", sa.String()),
    )
    dict_data_table = sa.Table(
        "sys_dict_data", metadata,
        sa.Column("id", sa.Integer()),
        sa.Column("dict_sort", sa.Integer()),
        sa.Column("dict_label", sa.String()),
        sa.Column("dict_value", sa.String()),
        sa.Column("dict_type", sa.String()),
        sa.Column("dict_type_id", sa.Integer()),
        sa.Column("status", sa.String()),
        sa.Column("description", sa.String()),
    )

    def _ensure_dict_type(dict_name: str, dict_type: str, description: str) -> int:
        """幂等插入字典类型，返回 id。"""
        row = conn.execute(
            sa.select(dict_type_table.c.id).where(dict_type_table.c.dict_type == dict_type)
        ).first()
        if row:
            return row[0]
        conn.execute(dict_type_table.insert().values(
            dict_name=dict_name, dict_type=dict_type, status="0",
            description=description,
        ))
        return conn.execute(
            sa.select(dict_type_table.c.id).where(dict_type_table.c.dict_type == dict_type)
        ).first()[0]

    def _ensure_dict_data(dict_type_id: int, dict_type: str, label: str, value: str, sort: int) -> int:
        """幂等插入字典数据，返回 id。"""
        row = conn.execute(
            sa.select(dict_data_table.c.id).where(
                dict_data_table.c.dict_type_id == dict_type_id,
                dict_data_table.c.dict_value == value,
            )
        ).first()
        if row:
            return row[0]
        conn.execute(dict_data_table.insert().values(
            dict_sort=sort, dict_label=label, dict_value=value,
            dict_type=dict_type, dict_type_id=dict_type_id, status="0",
        ))
        return conn.execute(
            sa.select(dict_data_table.c.id).where(
                dict_data_table.c.dict_type_id == dict_type_id,
                dict_data_table.c.dict_value == value,
            )
        ).first()[0]

    # med_sex: M / F / U
    sex_id = _ensure_dict_type("医疗-性别", "med_sex", "医疗领域性别字典（M/F/U）")
    _ensure_dict_data(sex_id, "med_sex", "男", "M", 1)
    _ensure_dict_data(sex_id, "med_sex", "女", "F", 2)
    _ensure_dict_data(sex_id, "med_sex", "未知", "U", 3)

    # med_exam_type: CT / PETCT / Pathology / Genetic / IHC
    exam_id = _ensure_dict_type("医疗-检查类型", "med_exam_type", "医疗领域检查类型字典")
    _ensure_dict_data(exam_id, "med_exam_type", "CT", "CT", 1)
    _ensure_dict_data(exam_id, "med_exam_type", "PET-CT", "PETCT", 2)
    _ensure_dict_data(exam_id, "med_exam_type", "病理", "Pathology", 3)
    _ensure_dict_data(exam_id, "med_exam_type", "基因检测", "Genetic", 4)
    _ensure_dict_data(exam_id, "med_exam_type", "免疫组化", "IHC", 5)

    # med_laterality: L / R / Bilateral / N/A
    lat_id = _ensure_dict_type("医疗-偏侧性", "med_laterality", "医疗领域偏侧性字典")
    _ensure_dict_data(lat_id, "med_laterality", "左", "L", 1)
    _ensure_dict_data(lat_id, "med_laterality", "右", "R", 2)
    _ensure_dict_data(lat_id, "med_laterality", "双侧", "Bilateral", 3)
    _ensure_dict_data(lat_id, "med_laterality", "不适用", "N/A", 4)

    # med_smoking_status: 占位（待需求定值）
    _ensure_dict_type("医疗-吸烟状态", "med_smoking_status", "医疗领域吸烟状态字典（待补充取值）")

    # ------------------------------------------------------------------
    # 4. 插入菜单 + 权限点
    # ------------------------------------------------------------------
    menu_table = sa.Table(
        "sys_menu", metadata,
        sa.Column("id", sa.Integer()),
        sa.Column("parent_id", sa.Integer()),
        sa.Column("name", sa.String()),
        sa.Column("type", sa.Integer()),  # 1=目录 2=菜单 3=按钮
        sa.Column("icon", sa.String()),
        sa.Column("order", sa.Integer()),
        sa.Column("permission", sa.String()),
        sa.Column("route_name", sa.String()),
        sa.Column("route_path", sa.String()),
        sa.Column("component_path", sa.String()),
        sa.Column("status", sa.String()),
        sa.Column("keep_alive", sa.Boolean()),
        sa.Column("hidden", sa.Boolean()),
        sa.Column("always_show", sa.Boolean()),
        sa.Column("title", sa.String()),
        sa.Column("affix", sa.Boolean()),
        sa.Column("redirect", sa.String()),
        sa.Column("description", sa.String()),
    )

    # 查找"医学数据"目录（取最早创建的一条，避免多匹配不确定）
    result = conn.execute(
        sa.select(menu_table.c.id).where(
            menu_table.c.permission.is_(None),
            sa.or_(
                menu_table.c.name.like("%医学%"),
                menu_table.c.name.like("%医疗%"),
                menu_table.c.component_path.like("%module_medical%"),
            ),
        ).order_by(menu_table.c.id).limit(1)
    ).first()
    parent_id = result[0] if result else None

    if parent_id is None:
        raise RuntimeError(
            "无法定位 '字典映射' 的父菜单目录（医疗数据目录）。"
            "请确保医疗数据菜单已初始化后再执行此迁移。"
        )

    # 检查是否已存在（幂等）
    existing = conn.execute(
        sa.select(menu_table.c.id).where(menu_table.c.route_path == "dict-mapping")
    ).first()
    if not existing:
        conn.execute(menu_table.insert().values(
            parent_id=parent_id,
            name="字典映射",
            type=2,
            icon="ri:exchange-line",
            order=1,
            permission="module_medical:dict_mapping:query",
            route_name="DictMapping",
            route_path="dict-mapping",
            component_path="module_medical/dict_mapping/index",
            status="0",
            keep_alive=True,
            hidden=False,
            always_show=False,
            title="字典映射",
            affix=False,
            redirect=None,
            description="医疗领域字典值映射管理（医院原始标签 → 标准字典值）",
        ))

    # 查回菜单项 ID，按钮权限挂到菜单项下（而非目录）
    menu_id_row = conn.execute(
        sa.select(menu_table.c.id).where(menu_table.c.route_path == "dict-mapping")
    ).first()
    menu_id = menu_id_row[0] if menu_id_row else parent_id

    # 按钮权限（parent_id 指向菜单项，不是目录）
    for perm in ["create", "update", "delete"]:
        btn_existing = conn.execute(
            sa.select(menu_table.c.id).where(menu_table.c.permission == f"module_medical:dict_mapping:{perm}")
        ).first()
        if not btn_existing:
            conn.execute(menu_table.insert().values(
                parent_id=menu_id,
                name=f"字典映射-{perm}",
                type=3,
                icon=None,
                order=0,
                permission=f"module_medical:dict_mapping:{perm}",
                route_name=None,
                route_path=None,
                component_path=None,
                status="0",
                keep_alive=False,
                hidden=False,
                always_show=False,
                title=f"字典映射-{perm}",
                affix=False,
                redirect=None,
                description=f"字典映射{perm}权限",
            ))

    # ------------------------------------------------------------------
    # 5. ENUM → VARCHAR(10) + CHECK（ADR-0006 增补）
    # ------------------------------------------------------------------
    # lnrs_anon_patient.sex: lnrs_anon_sex_enum → VARCHAR(10)
    op.execute(
        "ALTER TABLE lnrs.lnrs_anon_patient "
        "ALTER COLUMN sex TYPE VARCHAR(10) "
        "USING sex::text"
    )
    op.create_check_constraint(
        "chk_anon_patient_sex", "lnrs_anon_patient",
        sa.text("sex IN ('M','F','U')"),
        schema="lnrs",
    )

    # lnrs_anon_exam_finding.laterality: lnrs_anon_laterality_enum → VARCHAR(10)
    op.execute(
        "ALTER TABLE lnrs.lnrs_anon_exam_finding "
        "ALTER COLUMN laterality TYPE VARCHAR(10) "
        "USING laterality::text"
    )
    op.create_check_constraint(
        "chk_anon_exam_finding_laterality", "lnrs_anon_exam_finding",
        sa.text("laterality IN ('L','R','Bilateral','N/A')"),
        schema="lnrs",
    )

    # 删除不再使用的 ENUM 类型
    op.execute("DROP TYPE IF EXISTS lnrs.lnrs_anon_sex_enum CASCADE")
    op.execute("DROP TYPE IF EXISTS lnrs.lnrs_anon_laterality_enum CASCADE")


def downgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------------------------
    # 5. 回滚 ENUM 改造
    # ------------------------------------------------------------------
    # 必须先删除 CHECK 约束，否则 ALTER COLUMN TYPE 会失败
    op.drop_constraint(
        "chk_anon_patient_sex", "lnrs_anon_patient",
        schema="lnrs", type_="check",
    )
    op.drop_constraint(
        "chk_anon_finding_laterality", "lnrs_anon_exam_finding",
        schema="lnrs", type_="check",
    )

    # 恢复 lnrs_anon_laterality_enum
    op.execute(
        "CREATE TYPE lnrs.lnrs_anon_laterality_enum AS ENUM ('L','R','Bilateral','N/A')"
    )
    op.execute(
        "ALTER TABLE lnrs.lnrs_anon_exam_finding "
        "ALTER COLUMN laterality TYPE lnrs.lnrs_anon_laterality_enum "
        "USING laterality::lnrs.lnrs_anon_laterality_enum"
    )

    # 恢复 lnrs_anon_sex_enum
    op.execute("CREATE TYPE lnrs.lnrs_anon_sex_enum AS ENUM ('M','F','U')")
    op.execute(
        "ALTER TABLE lnrs.lnrs_anon_patient "
        "ALTER COLUMN sex TYPE lnrs.lnrs_anon_sex_enum "
        "USING sex::lnrs.lnrs_anon_sex_enum"
    )

    # ------------------------------------------------------------------
    # 4. 回滚菜单
    # ------------------------------------------------------------------
    conn.execute(
        sa.text(
            "DELETE FROM sys_menu WHERE permission LIKE 'module_medical:dict_mapping:%'"
        )
    )
    conn.execute(
        sa.text(
            "DELETE FROM sys_menu "
            "WHERE route_path = 'dict-mapping' AND component_path = 'module_medical/dict_mapping/index'"
        )
    )

    # ------------------------------------------------------------------
    # 3. 回滚字典种子（保留数据，不删——可能已被业务引用）
    # ------------------------------------------------------------------
    # 注意：字典种子不删除，避免破坏已有映射的外键引用

    # ------------------------------------------------------------------
    # 2. 删 med_dict_unmatched
    # ------------------------------------------------------------------
    op.drop_table("med_dict_unmatched")

    # ------------------------------------------------------------------
    # 1. 删 med_dict_mapping
    # ------------------------------------------------------------------
    op.drop_table("med_dict_mapping")
