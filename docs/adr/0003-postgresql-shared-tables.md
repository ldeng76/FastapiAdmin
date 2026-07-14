# ADR 0003: PostgreSQL 共享表 + TenantMixin 模式

> 状态：已接受
> 日期：2026-07-07

## 背景

数据层从 DuckDB 直读 parquet 迁移到 PostgreSQL 后，需要决定医疗数据的表结构组织方式。统一表（patient、pathology_specimen、surgery_record、genetic_test）和医院独有表都需要在 PostgreSQL 中落地。

## 选项

### 甲. 共享表 + TenantMixin（采用）

一套表结构，所有医院数据通过 `tenant_id` 列区分。统一表加 `TenantMixin`，医院独有表同样加 `TenantMixin`。

**优点：**
- 与 ADR 0001（医院=租户）完全对齐
- 跨院 UNION 查询最简洁
- 现有 RBAC `data_scope` 权限中间件直接生效
- JSONB 扩展字段每家医院独立填充，通过 tenant_id 区分

**缺点：**
- 单表数据量随医院增多而增长（当前量级可接受）

### 乙. 分表（表名带医院后缀）

每家医院独立表（`patient_shengyi`、`patient_zhujiang`）。

**缺点：**
- 跨院 UNION 查询需动态 SQL
- 与"共享表支持跨院 UNION"的核心设计目标矛盾
- 权限过滤需按表名动态路由

### 丙. 分区表

用 `tenant_id` 做 LIST 分区。

**缺点：**
- 当前数据量级不值得引入分区复杂度
- 增加运维负担

## 决策

采用甲：共享表 + TenantMixin。

## 后果

- 所有医疗表继承 `TenantMixin`，自动获得 `tenant_id` 列和外键约束
- 现有 `DATA_SCOPE` 权限策略对医疗数据生效
- 医院独有表（如 `visit_record`）同样加 `tenant_id`，仅一家医院有数据
- 废弃 `module_medical/repository.py` 中的 DuckDB 直读逻辑，改为 SQLAlchemy 查询
