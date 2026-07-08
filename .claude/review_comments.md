# 代码审查意见（请逐条修复）

## [1] HIGH | security
- **文件**: `.gitignore`
- **行号**: 15
- **问题**: Whitelisting `.env.dev` reintroduces the risk of committing sensitive environment variables (DB credentials, API keys, DICOM endpoint tokens, etc.) into the repository. The convention of ignoring all `.env*` files exists precisely to prevent secret leakage. If a development configuration is genuinely needed in-repo, prefer committing a sanitized `.env.dev.example` template (analogous to the existing `.env.example` pattern on the line above) and let developers copy it locally.
- **建议代码**:
```
+# Keep all .env variants ignored; ship sanitized templates instead.
+# !.env.dev
```

## [2] LOW | maintainability
- **文件**: `.gitignore`
- **行号**: 82
- **问题**: The newly added `backend/.run/` rule makes the pre-existing `backend/.run/dev.pid` entry on line 82 redundant (it is already covered by the directory-level pattern). Remove the stale line to keep the file consistent and avoid giving future readers the impression that `dev.pid` requires special handling.
- **建议代码**:
```
frontend/web/.vite/deps/_metadata.json
frontend/web/.vite/deps/package.json
```

## [3] LOW | bug
- **文件**: `backend/app/plugin/module_medical/hospital/controller.py`
- **行号**: 26
- **问题**: Duplicate import of `HospitalService` (imported on both line 27 and line 39). Remove the redundant line 39 import.
- **建议代码**:
```
from .mapping_service import MappingRuleService
from .service import HospitalService
from .schema import (
    HospitalCreate,
    HospitalOut,
    HospitalQueryParam,
    HospitalUpdate,
    MappingRuleBatch,
    MappingRuleOut,
    TemplateOut,
    EtlImportResponse,
    EtlImportStatus,
)
from .etl_service import EtlService
```

## [4] MEDIUM | maintainability
- **文件**: `backend/app/plugin/module_medical/hospital/controller.py`
- **行号**: 191
- **问题**: `get_template_controller` returns `ResponseSchema[dict]`, but the actual payload has a known shape (template metadata + rule list). Define a concrete `MappingTemplateDetailOut` schema for type safety, IDE completion, and OpenAPI documentation accuracy, instead of generic `dict`.

## [5] MEDIUM | maintainability
- **文件**: `backend/app/plugin/module_medical/hospital/controller.py`
- **行号**: 250
- **问题**: `get_data_summary_controller` returns `ResponseSchema[dict]`. The shape is well-known (per-table row counts). Define a concrete `HospitalDataSummaryOut` schema to make the API contract explicit and avoid silent breaking changes.

## [6] LOW | security
- **文件**: `backend/app/plugin/module_medical/hospital/controller.py`
- **行号**: 235
- **问题**: Permission granularity concern: `hospital:query` is used for both the basic hospital detail/list AND the ETL import status / data-summary endpoints. The import status reveals background job execution info and may need a more specific permission (e.g., `hospital:import:query`) to align with least-privilege. Verify against the permission matrix in `hospital_menu.sql`.

## [7] HIGH | performance
- **文件**: `backend/app/plugin/module_medical/hospital/controller.py`
- **行号**: 219
- **问题**: No idempotency / concurrency guard on `POST /hospital/{id}/import`. The `EtlService.trigger_import_service` doesn't appear to check if a `running` job already exists for this hospital; a user could rapidly fire multiple requests, spawning parallel ETL coroutines that race on the same Redis status key and DB rows (the background task overwrites status non-atomically via read-modify-write in `_update_status`). Consider rejecting if a job is already `pending`/`running`.

## [8] MEDIUM | bug
- **文件**: `backend/app/plugin/module_medical/hospital/controller.py`
- **行号**: 72
- **问题**: `get_hospital_page_controller` defaults `order_by` to `[{"id": "asc"}]`, but `page_service` in similar codebases usually expects `order_by` items keyed by DB column names. Using `{"id": ...}` may or may not match the underlying ordering implementation. Worth verifying with the actual `page_service` signature — if it expects column keys (e.g. `"created_time"`), defaulting to `"id"` could cause silent sort errors or be ignored.

## [9] LOW | maintainability
- **文件**: `backend/app/plugin/module_medical/hospital/controller.py`
- **行号**: 75
- **问题**: The `HospitalQueryParam` class uses a constructor with `Query(...)` parameters and a side-effecting `__init__` that only sets attributes when input is truthy. Combined with `search.__dict__ if search and hasattr(search, "__dict__") else {}` in the controller, the resulting search dict will silently miss unset filters but never include explicit `None` values. This makes the search contract implicit. Consider using a Pydantic `BaseModel` with explicit fields for clarity and validation.

## [10] LOW | maintainability
- **文件**: `backend/app/plugin/module_medical/hospital/controller.py`
- **行号**: 91
- **问题**: Path parameter shadowing builtin: the path parameter `id` (e.g. `id: Annotated[int, Path(...)]`) shadows the Python builtin `id()`. While FastAPI doesn't complain, it's a common style/lint warning (e.g., PLW0622, A002). Consider renaming to `hospital_id` for consistency with `etl_service.trigger_import_service(hospital_id=...)` and the path comment style.

## [11] MEDIUM | maintainability
- **文件**: `backend/app/plugin/module_medical/dicom/schema.py`
- **行号**: 14
- **问题**: Dead code: the `StudyOut`, `SeriesOut`, `InstanceOut`, and `DicomStudyDetailOut` Pydantic models are not referenced anywhere — the controller declares `response_model=ResponseSchema[list[dict]]` and the service layer returns `list[dict[str, Any]]`. Either wire them in via `ResponseSchema[list[StudyOut]]` / `list[SeriesOut]` / `list[InstanceOut]` in the controller (which also preserves the rich `description=` for OpenAPI docs), or remove them.

Suggested fix in `dicom/controller.py`:

    response_model=ResponseSchema[list[StudyOut]],        # list_studies
    response_model=ResponseSchema[list[SeriesOut]],       # list_series
    response_model=ResponseSchema[list[InstanceOut]],     # list_instances

## [12] LOW | maintainability
- **文件**: `backend/app/plugin/module_medical/dicom/schema.py`
- **行号**: 60
- **问题**: Type aliases `InstanceListOut` / `SeriesListOut` / `StudyListOut` are unused (grep shows no caller). They are just aliases for `list[dict[str, Any]]` and add no semantic value — the comment "为 ResponseSchema[...] 给出 dict 友好的容器类型" is misleading because the controller actually uses plain `list[dict]`. Remove them; if a generic list container is genuinely needed in the future, define it once (e.g. `DataList = list[dict[str, Any]]`) instead of three near-identical names.

## [13] LOW | performance
- **文件**: `backend/app/plugin/module_medical/dicom/schema.py`
- **行号**: 60
- **问题**: Indirect maintainability/perf risk: because the controller's `response_model` is `ResponseSchema[list[dict]]`, FastAPI performs no response validation. The repository returns hand-built dicts on every call site; if those dicts drift from the declared `*Out` schemas (e.g. rename a key in the repository), the API contract silently changes and the frontend breaks with no compile-time signal. Tightening the response_model to the typed schemas (see previous comment) would catch that.

## [14] MEDIUM | performance
- **文件**: `backend/app/plugin/module_medical/dicom/service.py`
- **行号**: 24
- **问题**: async method wraps a sync, blocking indexer call (file I/O + pydicom parsing). The first scan on a large dataset runs on the event loop and stalls the worker; concurrent requests serialize behind the per-study RLock. Either drop `async` (FastAPI runs sync callables in a threadpool) or offload with `asyncio.to_thread`.
- **建议代码**:
```
    @classmethod
    def list_studies_service(cls) -> list[dict[str, Any]]:
        """列出所有 Study。"""
        return indexer.list_studies()
```

## [15] MEDIUM | maintainability
- **文件**: `backend/app/plugin/module_medical/dicom/service.py`
- **行号**: 29
- **问题**: Bare `except Exception` swallows the indexer's own `CustomException` (e.g. "非法的 study_id", "Study 不存在", raised with specific status_codes) and rewraps them under a generic 500. Narrow the except and avoid interpolating raw `e!s` into a user-facing message — it can leak filesystem paths or class names. Log the detail, return a generic message.
- **建议代码**:
```
        except CustomException:
            raise
        except OSError as e:
            log.error("扫描 DICOM Study 列表失败: %s", e)
            raise CustomException(msg="读取 DICOM 数据失败")
```

## [16] LOW | bug
- **文件**: `backend/app/plugin/module_medical/dicom/service.py`
- **行号**: 38
- **问题**: Unreachable re-raise: the indexer's `_require_study` already raises `CustomException` before `list_series` would re-raise it. Combined with the broad `except Exception` above, this branch masks the genuine 4xx errors from the indexer by rewrapping them as 500. Remove the re-raise, and instead let `CustomException` propagate cleanly (narrow the outer except).
- **建议代码**:
```
        try:
            return indexer.list_series(study_id)
        except CustomException:
            raise
        except OSError as e:
            log.error("读取 Study %s 序列失败: %s", study_id, e)
            raise CustomException(msg="读取序列失败")
```

## [17] MEDIUM | bug
- **文件**: `backend/app/plugin/module_medical/dicom/service.py`
- **行号**: 56
- **问题**: Wrong HTTP semantics: a missing/empty series is a client-input problem, not an internal error. The default `status_code=500` makes a normal "not found" look like a server failure. Inconsistent with `get_instance_path_service` in this same file (which correctly uses 404) and with peers like `hospital/service.py`. Use `code=404, status_code=404`.
- **建议代码**:
```
        if not instances:
            raise CustomException(
                msg="序列不存在或无可用切片",
                code=status.HTTP_404_NOT_FOUND,
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return instances
```

## [18] MEDIUM | security
- **文件**: `backend/app/plugin/module_medical/dicom/service.py`
- **行号**: 60
- **问题**: Method returns a raw `Path` to the controller; defensive `resolved.is_relative_to(DICOM_DATA_DIR)` is not re-checked at the service boundary. Also no `try/except` for the case where the file is removed between indexer check and `FileResponse` opening it (will surface as raw 500 via the global handler). At minimum, wrap with a `try/except OSError` -> `CustomException(404)`, and prefer a defensive containment check before returning.
- **建议代码**:
```
    @classmethod
    def get_instance_path_service(cls, sop_uid: str) -> Path:
        """按 SOPInstanceUID 取原始 .dcm 文件路径。"""
        path = indexer.get_instance_path(sop_uid)
        if path is None:
            raise CustomException(
                msg="切片不存在或 SOPInstanceUID 无效",
                code=status.HTTP_404_NOT_FOUND,
                status_code=status.HTTP_404_NOT_FOUND,
            )
        # 防御性：即使索引本身已校验过，再确认最终路径仍在数据根目录内。
        try:
            root = Path(settings.DICOM_DATA_DIR).resolve()
            if path.resolve(strict=False).is_relative_to(root) is False:
                raise CustomException(
                    msg="切片路径非法",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
        except OSError as e:
            log.error("解析 DICOM 路径失败: %s", e)
            raise CustomException(
                msg="切片不可访问",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return path
```

## [19] LOW | maintainability
- **文件**: `backend/app/plugin/module_medical/dicom/service.py`
- **行号**: 14
- **问题**: `auth: AuthSchema` is declared on every service method but never read (no DB, no tenant scoping, no audit write). It is dead weight that the controller must fabricate. Remove the parameter from service signatures and from the controllers that call them — `DicomRouter` already enforces `module_medical:dicom:query` permission. Keep it only if a future tenant filter or access log is planned.
- **建议代码**:
```
from app.core.exceptions import CustomException
from app.core.logger import log

from .repository import indexer
```

## [20] CRITICAL | bug
- **文件**: `backend/app/alembic/versions/c3d4e5f6a7b8_add_medical_data_tables.py`
- **行号**: 27
- **问题**: Pervasive `try/except Exception: pass` swallows all errors, including real DB/permission/connectivity failures. This is a major deviation from sibling migrations (a1b2c3d4e5f6, b2c3d4e5f6a7) which raise errors normally. If `op.create_table` fails halfway (e.g., creates 4 of 7 tables), the migration is left in a half-applied state and Alembic will mark it as failed but the silent except here means the operator gets no signal. Remove the try/except wrappers and let Alembic abort on real errors; the only legitimate place for error tolerance would be `op.add_column` for `data_dir` if the migration is meant to be re-runnable — in that case use `op.batch_alter_table` with checks or `op.execute("ALTER TABLE ... ADD COLUMN IF NOT EXISTS ...")`.

Example: this try/except will silently succeed even if `op.create_index` fails due to a permission error or a `psycopg2.OperationalError`, leaving you with tables that lack the indexes you expect.
- **建议代码**:
```
def _audited_columns(prefix: str = "ix_", table: str | None = None) -> None:
    """辅助函数：给一张表添加 ModelMixin/UserMixin 的全部索引。"""
    if table is None:
        return
    indexes = ["id", "uuid", "status", "created_time", "updated_time",
               "is_deleted", "deleted_time", "created_id", "updated_id",
               "deleted_id", "tenant_id"]
    for col in indexes:
        op.create_index(op.f(f"{prefix}{table}_{col}"), table, [col])
```

## [21] CRITICAL | bug
- **文件**: `backend/app/alembic/versions/c3d4e5f6a7b8_add_medical_data_tables.py`
- **行号**: 239
- **问题**: Schema/model mismatch: the model declares `nodule_no: Mapped[str | None] = mapped_column(String(20), nullable=True, ...)` and the comment explicitly says "源数据可能为空", but this migration declares `nodule_no` as `nullable=False`. The migration will reject legitimate rows where source data has no nodule_no. Either change the migration to `nullable=True` to match the model, or backfill the column after creation with a default value, and document the change.
- **建议代码**:
```
        sa.Column("nodule_no", sa.String(length=20), nullable=True, comment="结节编号（源数据可能为空）"),
```

## [22] CRITICAL | bug
- **文件**: `backend/app/alembic/versions/c3d4e5f6a7b8_add_medical_data_tables.py`
- **行号**: 236
- **问题**: Schema/model mismatch: the model declares `exam_id: Mapped[str] = mapped_column(Text, nullable=False, comment="检查唯一号（可能含多个逗号分隔ID）")` but this migration uses `String(length=64)`. The model comment explicitly notes exam_id may contain multiple comma-separated IDs, which can easily exceed 64 chars. Change the migration to `sa.Text()` to match the model, otherwise inserts with long exam_id values will be rejected by PostgreSQL.
- **建议代码**:
```
        sa.Column("exam_id", sa.Text(), nullable=False, comment="检查唯一号（可能含多个逗号分隔ID）"),
```

## [23] MEDIUM | bug
- **文件**: `backend/app/alembic/versions/c3d4e5f6a7b8_add_medical_data_tables.py`
- **行号**: 23
- **问题**: Dead code: `_audited_columns` is defined but never called anywhere in the migration or codebase. It also duplicates the logic of `_create_audit_indexes` (defined below). Remove this function to avoid confusing future maintainers — they will assume it is invoked somewhere and waste time hunting for the call site.
- **建议代码**:
```
# (removed; use _create_audit_indexes directly)
```

## [24] MEDIUM | maintainability
- **文件**: `backend/app/alembic/versions/c3d4e5f6a7b8_add_medical_data_tables.py`
- **行号**: 87
- **问题**: Two-pass server_default approach (create_table then `_set_server_defaults`) is needlessly indirect and inconsistent with the cleaner inline pattern in sibling migrations (a1b2c3d4e5f6 sets `server_default=...` on the sa.Column when needed; e.g., `lifecycle_status` was set inline via alter_column after create_table — this is the established project pattern). More importantly, the helper passes `existing_type`/`existing_nullable=False` which only works if the column was created with nullable=False at create_table time. Apply `server_default` directly on `sa.Column(..., server_default=sa.text("CURRENT_TIMESTAMP"))` etc. inside `_base_columns()` instead of an alter_column pass; this also removes the silent-except around `op.alter_column`.
- **建议代码**:
```
# Inline server_default in sa.Column definitions inside _base_columns() instead.
```

## [25] MEDIUM | performance
- **文件**: `backend/app/alembic/versions/c3d4e5f6a7b8_add_medical_data_tables.py`
- **行号**: 106
- **问题**: Redundant indexes: PostgreSQL automatically creates a unique index for every PRIMARY KEY, and a unique index for every UniqueConstraint. The migration then creates a non-unique `ix_<table>_id` index on the PK column, and a non-unique `ix_<table>_uuid` index overlapping the `uq_<table>_uuid` unique constraint. This wastes storage and slows down inserts. Either drop these manual indexes or drop the corresponding UniqueConstraint — do not have both.
- **建议代码**:
```
    # Skip 'id' (PK auto-indexed) and 'uuid' (uq_<table>_uuid auto-indexed).
    for col in ("status", "created_time", "updated_time",
                "is_deleted", "deleted_time", "created_id", "updated_id",
                "deleted_id", "tenant_id"):
        op.create_index(op.f(f"ix_{table}_{col}"), table, [col])
```

## [26] MEDIUM | performance
- **文件**: `backend/app/alembic/versions/c3d4e5f6a7b8_add_medical_data_tables.py`
- **行号**: 303
- **问题**: Single-column `patient_id` index misses the dominant access pattern. All queries in this schema are tenant-scoped (per the UniqueConstraint `(tenant_id, patient_id)` design and `TenantMixin` semantics), and the unique constraint auto-creates a unique index on `(tenant_id, patient_id)`. Creating an additional single-column `patient_id` index is rarely useful — the `(tenant_id, patient_id)` unique index is already used for tenant-scoped lookups. If single-column `patient_id` lookups are truly needed (e.g., cross-tenant admin queries), keep it; otherwise drop it and rely on the unique index. Note: the unique index is unique, so range scans are still possible.
- **建议代码**:
```
    # The UniqueConstraint (tenant_id, patient_id, ...) already creates
    # a usable index for tenant-scoped lookups; only add this if cross-tenant
    # queries are a real workload, and consider composite (tenant_id, patient_id).
```

## [27] MEDIUM | maintainability
- **文件**: `backend/app/alembic/versions/c3d4e5f6a7b8_add_medical_data_tables.py`
- **行号**: 312
- **问题**: `downgrade()` uses `try/except` swallows around `op.drop_table` and `op.drop_column`, mirroring the same anti-pattern as `upgrade()`. If a downgrade fails midway, the schema is left inconsistent and the operator has no signal. More importantly, the explicit `op.drop_index(...)` calls that sibling migrations use to clean up indexes are absent here — `drop_table` will cascade indexes in PostgreSQL, but that means downgrade is not symmetric with upgrade (which used helper-based explicit index creation), making diff review harder. Match the established project style: explicit `op.drop_index` per index, then `op.drop_table`, then `op.drop_column("med_hospital", "data_dir")` — no try/except wrappers.
- **建议代码**:
```
def downgrade() -> None:
    # Drop indexes explicitly (mirror upgrade) then drop tables in reverse order
    for tbl in ("med_follow_up", "med_ihc_result", "med_nodule_imaging",
                "med_genetic_test", "med_surgery_record", "med_pathology_specimen", "med_patient"):
        op.drop_index(op.f(f"ix_{tbl}_patient_id"), table_name=tbl)
        op.drop_table(tbl)
    op.drop_column("med_hospital", "data_dir")
```

## [28] HIGH | security
- **文件**: `backend/app/plugin/module_medical/hospital/etl_engine.py`
- **行号**: 86
- **问题**: Path traversal in DuckDB query: `src_table` originates from `MappingRuleModel` (DB-stored, admin-writable via `replace_service`/`apply_template_service`) and is interpolated directly into the SQL string and the resolved parquet path. A malicious or misconfigured rule such as `src_table='../../etc/passwd'` (or any path outside `data_dir`) lets the engine read arbitrary files accessible to the process. Validate `src_table` against an allow-list (e.g., `TGT_TABLE_MODELS.keys()` mirrored, or a hard-coded set) and verify the resolved `parquet_path` is contained inside `data_dir.resolve()` before opening it. Also avoid f-string SQL — pass the path via a parameterised `read_parquet(?)` to remove the SQL-injection code-smell.
- **建议代码**:
```
    # Validate src_table against allow-list to prevent path traversal
    if not src_table.isidentifier() or "/" in src_table or "\\" in src_table or ".." in src_table:
        raise ValueError(f"非法源表名: {src_table}")
    parquet_path = (data_dir / f"{src_table}.parquet").resolve()
    # Constrain reads to data_dir
    if data_dir.resolve() not in parquet_path.parents:
        raise ValueError(f"源表路径越界: {parquet_path}")
    if not parquet_path.exists():
        raise FileNotFoundError(f"源数据文件不存在: {parquet_path}")

    con = duckdb.connect(database=":memory:")
    try:
        cur = con.execute("SELECT * FROM read_parquet(?)", [parquet_path.as_posix()])
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        return cols, rows
    finally:
        con.close()
```

## [29] HIGH | bug
- **文件**: `backend/app/plugin/module_medical/hospital/etl_engine.py`
- **行号**: 219
- **问题**: Docstring in `run_etl_pipeline` is inconsistent with `etl_service._run_etl_background` and is misleading. The caller wraps `run_etl_pipeline` in a single `async with async_db_session()` and commits once at the end — i.e. one transaction for ALL tables, not per-table. A failure mid-loop rolls back the entire batch (including the DELETE on already-imported tables), which combined with the DELETE-before-INSERT pattern means: an interrupted run leaves ZERO data for that tenant (data loss) even though the docstring claims "单表失败不影响其他表". Either (a) move the commit inside this function to make it truly per-table, or (b) update the docstring and add an `import_run_id`/`batch_id` column to scope the DELETE so partial-import rollback is safe.
- **建议代码**:
```
    """运行完整 ETL 管线：逐表导入，每张表独立提交。

    本函数对每张表独立 `await db.commit()`，单表失败不会污染已导入的表。
    调用方应直接传入一个普通 `AsyncSession`，**不要**再外层 `begin()`，
    也不要自己额外 `commit()`，否则会出现 "回滚语义不一致" 的问题。
```

## [30] MEDIUM | bug
- **文件**: `backend/app/plugin/module_medical/hospital/etl_engine.py`
- **行号**: 150
- **问题**: Silent data loss: `_clean_row` drops any key not present on the target model without raising. If a mapping rule references a renamed/removed column (model schema evolution, stale template), the data simply disappears from the import with no log. At minimum, log a warning when columns are dropped so misconfiguration surfaces. Consider raising on unknown columns when `len(transformed) != len(transformed_rows)`.
- **建议代码**:
```
    """过滤掉目标模型不存在的列，并归一化值类型。

    未知列会被丢弃并打 warning，避免模型字段重命名后旧规则静默丢数据。
    """
    valid_cols = {c.name for c in model.__table__.columns}
    cleaned: dict[str, Any] = {}
    for k, v in row.items():
        if k in valid_cols:
            cleaned[k] = _normalize_value(v)
        else:
            log.warning(f"ETL: 目标表 {model.__tablename__} 不存在列 {k}，已丢弃")
    return cleaned
```

## [31] MEDIUM | bug
- **文件**: `backend/app/plugin/module_medical/hospital/etl_engine.py`
- **行号**: 122
- **问题**: Silent failure on unknown `transform_type`: the `else: continue` branch drops the entire rule with no log. Combined with the schema-level allow-list (`rename`/`constant`/`expression` in `MappingRuleIn._validate_transform_type`), this should never happen at runtime, but a future schema change would silently drop all rows of an affected column. Replace with `log.warning` and a `raise ValueError` so misconfiguration cannot cause silent data loss.
- **建议代码**:
```
        elif rule.transform_type == "expression":
            src_val = row_dict.get(rule.src_field)
            val = apply_expression(rule.transform_value, src_val) if rule.transform_value else None
        else:
            log.error(
                f"ETL: 未知 transform_type={rule.transform_type!r} "
                f"(tgt_field={rule.tgt_field})，已跳过该列"
            )
            continue
```

## [32] MEDIUM | performance
- **文件**: `backend/app/plugin/module_medical/hospital/etl_engine.py`
- **行号**: 140
- **问题**: Precision loss: `_normalize_value` converts `Decimal` → `float`. DuckDB returns DECIMAL columns as `Decimal`; PostgreSQL `NUMERIC` accepts `Decimal` natively. Casting to `float` silently corrupts financial/measurement precision (e.g., 0.1+0.2 territory, large precision specs). Pass `Decimal` through unchanged and only handle the `datetime/date` branch.
- **建议代码**:
```
def _normalize_value(val: Any) -> Any:
    """把 DuckDB 返回的复合类型转为 PG 可接受的 Python 对象。

    注意：Decimal 不要转 float，会丢精度 — PG NUMERIC 原生支持 Decimal。
    """
    if isinstance(val, (datetime, date)):
        return val  # SQLAlchemy 能正确处理
    return val  # Decimal/str/int/float 全部透传
```

## [33] MEDIUM | performance
- **文件**: `backend/app/plugin/module_medical/hospital/etl_engine.py`
- **行号**: 183
- **问题**: Blocking event loop on large parquet: `duckdb.connect(...).execute(...).fetchall()` is fully synchronous and materialises the entire parquet into memory inside the `await import_one_table` coroutine. A large parquet file will block the event loop and risk OOM. Wrap the read+transform in `asyncio.to_thread(...)` and use DuckDB's chunked `fetch_arrow` / `fetchmany` for memory-bounded streaming. At minimum, document the synchronous behaviour and add a row-count guard before reading.
- **建议代码**:
```
    # 1. 读 parquet（同步阻塞操作，放到线程池避免阻塞事件循环）
    cols, raw_rows = await asyncio.to_thread(_read_parquet_rows, data_dir, src_table)
    if not raw_rows:
        log.warning(f"ETL: 源表 {src_table} 无数据，跳过")
        return 0
```

## [34] MEDIUM | maintainability
- **文件**: `backend/app/plugin/module_medical/hospital/etl_engine.py`
- **行号**: 128
- **问题**: JSONB coercion swallows errors silently: `try/except (ValueError, TypeError): pass` keeps a non-JSON string in a JSONB column, which then either gets stored as a raw string (silent corruption) or fails later in the INSERT with a confusing error. If the parquet cell is supposed to be JSON, a parse failure should abort the row (or the whole import) so the schema mismatch is visible. At minimum, log the offending value.
- **建议代码**:
```
        # JSONB 列：JSON 字符串转 dict；解析失败记日志后保持原值让 INSERT 报错
        if rule.tgt_field in jsonb_columns and isinstance(val, str):
            try:
                val = json.loads(val)
            except (ValueError, TypeError) as e:
                log.warning(
                    f"ETL: JSONB 列 {rule.tgt_field} 解析失败: {e!s} "
                    f"(src={rule.src_table}.{rule.src_field})"
                )
```

## [35] HIGH | security
- **文件**: `backend/app/plugin/module_medical/service.py`
- **行号**: 62
- **问题**: The `except Exception` is too broad and forwards the raw exception message to API consumers via `CustomException(msg=f"读取数据失败: {e!s}")`. For a medical-data endpoint this risks leaking internal details (DB error strings, SQL fragments, file paths). Catch only what `get_patient_detail` can legitimately raise (e.g. `SQLAlchemyError` / `asyncpg.PostgresError`) and return a generic message to clients while keeping the full detail in logs via `log.exception` instead of `log.error`.
- **建议代码**:
```
        try:
            detail = await get_patient_detail(db=auth.db, patient_id=patient_id, center=center)
        except SQLAlchemyError:
            log.exception("读取患者多模态数据失败 %s", patient_id)
            raise CustomException(msg="读取患者多模态数据失败")
```

## [36] MEDIUM | bug
- **文件**: `backend/app/plugin/module_medical/service.py`
- **行号**: 67
- **问题**: 404 vs 500 semantics: `get_patient_detail` returns `{}` on a missing patient and the service raises a `CustomException`, but it does not distinguish "no such patient" from "patient exists but has no multimodal rows". For a missing/invalid `patient_id` callers should get a clean 404-style error and not be funneled through the same generic exception path as DB failures. Consider an explicit sentinel or raising a dedicated "not found" exception type from `get_patient_detail` so the service can map it correctly.
- **建议代码**:
```
        if not detail:
            raise CustomException(msg="患者不存在或无多模态数据", code=404)
        return detail
```

## [37] MEDIUM | maintainability
- **文件**: `backend/app/plugin/module_medical/service.py`
- **行号**: 46
- **问题**: `page_service` returns a hand-built `dict[str, Any]` rather than the `PatientListOut`-style typed response already declared in `schema.py`. The controller's `response_model=ResponseSchema[PatientListOut]` is also effectively bypassed here (only the inner items can be coerced). Define a `PatientPageOut` (containing `page_no`, `page_size`, `total`, `has_next`, `items: list[PatientListOut]`) so the service returns a typed model — this gives static checking in OpenAPI clients and matches the controller's `response_model` declaration.
- **建议代码**:
```
        return PatientPageOut(
            page_no=page_no,
            page_size=page_size,
            total=total,
            has_next=(offset + page_size) < total,
            items=[PatientListOut(**item) for item in items],
        )
```

## [38] MEDIUM | maintainability
- **文件**: `backend/app/plugin/module_medical/service.py`
- **行号**: 60
- **问题**: `detail_service` also returns `dict[str, Any]` even though `PatientDetailOut` already exists in `schema.py` and is wired into the controller's `response_model`. Construct and return a `PatientDetailOut` here so the return type is self-documenting and the mapping from query output to API contract is centralized in this layer instead of relying on FastAPI's implicit coercion.
- **建议代码**:
```
    ) -> PatientDetailOut:
        """患者多模态详情。"""
        try:
            detail = await get_patient_detail(db=auth.db, patient_id=patient_id, center=center)
        except SQLAlchemyError:
            log.exception("读取患者多模态数据失败 %s", patient_id)
            raise CustomException(msg="读取患者多模态数据失败")
        if not detail:
            raise CustomException(msg="患者不存在或无多模态数据", code=404)
        return PatientDetailOut(**detail)
```

## [39] MEDIUM | bug
- **文件**: `backend/app/plugin/module_medical/service.py`
- **行号**: 28
- **问题**: Input validation is absent at the service boundary. `page_no <= 0` yields a negative `offset` (PostgreSQL will reject it), `page_size` is unbounded (memory/DoS risk on huge pages), and `keyword`/`center` flow straight into `ilike`/`==`. The controller only relies on `PaginationQueryParam` defaults — please clamp/validate `page_no >= 1`, `1 <= page_size <= MAX_PAGE_SIZE`, and reject empty-string `keyword` here as well, so callers reaching this service via non-HTTP paths are also protected.
- **建议代码**:
```
    @classmethod
    async def page_service(
        cls,
        auth: AuthSchema,
        page_no: int = 1,
        page_size: int = 10,
        center: str | None = None,
        keyword: str | None = None,
    ) -> PatientPageOut:
        """患者分页列表。"""
        if page_no < 1 or page_size < 1:
            raise CustomException(msg="page_no 和 page_size 必须为正整数")
        page_size = min(page_size, MAX_PAGE_SIZE)
        keyword = keyword.strip() or None
        center = center.strip() or None
        offset = (page_no - 1) * page_size
```

## [40] LOW | maintainability
- **文件**: `frontend/web/src/types/module_medical/hospital.ts`
- **行号**: 77
- **问题**: The inline rule shape inside `MappingTemplateDetail.rules` duplicates `MappingRuleRow` fields and weakens `transform_type` from `MappingTransformType` to plain `string`. Consider using `Array<Omit<MappingRuleRow, "id" | "hospital_id" | "created_time">>` to keep both type definitions in sync and preserve type safety.
- **建议代码**:
```
rules: Array<Omit<MappingRuleRow, "id" | "hospital_id" | "created_time">>;
```

## [41] LOW | maintainability
- **文件**: `frontend/web/src/types/module_medical/hospital.ts`
- **行号**: 90
- **问题**: `EtlImportStatusValue` defines `"idle"` and `"unknown"` states that aren't represented anywhere else (e.g., `LIFECYCLE_STATUS_META` covers only the four lifecycle values). Confirm these values are actually returned by the backend ETL job; if not, drop them to avoid misleading consumers.

## [42] HIGH | security
- **文件**: `frontend/web/src/views/module_medical/hospital/components/DataOverviewPanel.vue`
- **行号**: 50
- **问题**: Missing permission check for online/offline actions. The parent list page wraps these actions with `hasAuth("module_medical:hospital:online")` / `hasAuth("module_medical:hospital:offline")`, but this dialog exposes the same endpoints without any permission guard, allowing unauthorized users to trigger state transitions through the data overview panel.
- **建议代码**:
```
<ElButton
        v-if="canGoOnline"
        type="success"
        @click="handleGoOnline"
      >
        上线
      </ElButton>
      <ElButton
        v-if="canGoOffline"
        type="warning"
        @click="handleGoOffline"
      >
        下线
      </ElButton>
```

## [43] MEDIUM | bug
- **文件**: `frontend/web/src/views/module_medical/hospital/components/DataOverviewPanel.vue`
- **行号**: 116
- **问题**: Race condition in `loadData()`: when the dialog is opened and closed rapidly, an in-flight request may resolve after a newer request, overwriting the latest summary with stale data. Track the request with an abort signal or a request id and ignore stale responses.
- **建议代码**:
```
let loadSeq = 0;
async function loadData() {
  const seq = ++loadSeq;
  loading.value = true;
  try {
    const res = await HospitalAPI.getDataSummary(props.hospitalId);
    if (seq !== loadSeq) return; // stale response, ignore
    summary.value = res.data?.data || null;
  } finally {
    if (seq === loadSeq) loading.value = false;
  }
}
```

## [44] MEDIUM | bug
- **文件**: `frontend/web/src/views/module_medical/hospital/components/DataOverviewPanel.vue`
- **行号**: 152
- **问题**: Watcher does not refetch when `hospitalId` changes while dialog is already open. If the parent reuses this panel with a different hospital id (e.g. navigating between rows), the stale `summary` will be shown until reopened. Watch `props.hospitalId` as well, or reset `summary` when `hospitalId` changes.
- **建议代码**:
```
watch(
  [visible, () => props.hospitalId],
  ([val]) => {
    if (val) {
      loadData();
    } else {
      summary.value = null;
    }
  },
);
```

## [45] LOW | maintainability
- **文件**: `frontend/web/src/views/module_medical/hospital/components/DataOverviewPanel.vue`
- **行号**: 88
- **问题**: `TABLE_LABELS` duplicates the schema information already encoded in `HospitalDataSummary.tables`. If the backend adds a new table, this hardcoded map silently falls back to showing the raw key. Consider either deriving labels from a shared source-of-truth, or at minimum adding a TODO / runtime warning when an unknown key is encountered.
- **建议代码**:
```
// NOTE: keep in sync with backend HospitalDataSummary.tables
const TABLE_LABELS: Record<keyof HospitalDataSummary["tables"], string> = {
  patient: "患者基本信息",
  pathology_specimen: "病理标本",
  surgery_record: "手术记录",
  genetic_test: "基因检测",
  nodule_imaging: "结节影像",
  ihc_result: "免疫组化",
  follow_up: "随访结局",
};
```

## [46] LOW | bug
- **文件**: `frontend/web/src/views/module_medical/hospital/components/DataOverviewPanel.vue`
- **行号**: 22
- **问题**: `totalRowsFormatted` is computed before checking whether `summary` is loaded. While `loading=true`, the dialog header shows `0` for 总行数 and `已注册` for 状态, which can be misleading and look like an empty hospital. Consider showing `-` or a skeleton placeholder while `summary` is null.
- **建议代码**:
```
<ElDescriptionsItem label="总行数">
            <strong>{{ summary ? totalRowsFormatted : "-" }}</strong>
          </ElDescriptionsItem>
```

## [47] HIGH | bug
- **文件**: `frontend/web/src/views/module_medical/hospital/components/HospitalCreateDialog.vue`
- **行号**: 185
- **问题**: The `handleSubmit` function does not check the API response status before showing the success message. If `HospitalAPI.createHospital` returns a business error or the request fails, the dialog will still close and a success alert will be shown, leaving the user with an incorrect state. Wrap the call with error handling (e.g., check `res.data?.code` or rely on a unified axios interceptor for rejections) and only show the success message when the call truly succeeded.
- **建议代码**:
```
async function handleSubmit() {
  submitLoading.value = true;
  try {
    const res = await HospitalAPI.createHospital(formData.value);
    if (!res) return;
    ElMessageBox.alert("注册成功！请在后端日志中查看初始管理员用户名和临时密码。", "提示", {
      type: "success",
      confirmButtonText: "确定",
    });
    visible.value = false;
    currentStep.value = 0;
    formData.value = { ...initialFormData };
    emit("success");
  } catch (err) {
    // request interceptor typically surfaces the error via message; keep dialog open so user can retry
    console.error("注册医院失败", err);
  } finally {
    submitLoading.value = false;
  }
}
```

## [48] MEDIUM | maintainability
- **文件**: `frontend/web/src/views/module_medical/hospital/components/HospitalCreateDialog.vue`
- **行号**: 144
- **问题**: The `request` utility likely returns `undefined` or rejects on HTTP errors; `loadTemplates` does not handle failure. If the templates request fails, the user silently sees an empty list and may believe no templates are available. Add error handling and (optionally) surface a message so the issue is visible.
- **建议代码**:
```
async function loadTemplates() {
  templateLoading.value = true;
  try {
    const res = await HospitalAPI.listTemplates();
    templateOptions.value = res?.data?.data || [];
  } catch (err) {
    templateOptions.value = [];
    console.error("加载映射模板失败", err);
  } finally {
    templateLoading.value = false;
  }
}
```

## [49] MEDIUM | maintainability
- **文件**: `frontend/web/src/views/module_medical/hospital/components/HospitalCreateDialog.vue`
- **行号**: 3
- **问题**: The dialog passes both `:confirm-loading="submitLoading"` and an explicit `#footer` slot, which on most Element Plus–style wrappers (including `FaDialog`) makes the default footer (with built-in confirm/cancel) still render. The result is a duplicated "取消" button next to the wizard's own one, and the built-in confirm/cancel likely no-op (since handlers `@cancel`/`@confirm` are wired). Either remove the `confirm-loading`/`@cancel`/`@confirm` bindings or override the entire footer (no default). As-is this creates confusing UX.
- **建议代码**:
```
  <FaDialog
    v-model="visible"
    title="注册医院"
    width="720px"
    dialog-class="crud-embed-dialog"
    modal-class="crud-embed-dialog"
  >
```

## [50] MEDIUM | bug
- **文件**: `frontend/web/src/views/module_medical/hospital/components/HospitalCreateDialog.vue`
- **行号**: 177
- **问题**: The `template_code` field is not included in `basicFormItems`, but the ElSteps render independently for steps 0/1/2 and the form is unmounted when step !== 0. As a consequence `formData.value.template_code` entered in step 2 (via direct v-model) survives, but if the user clicks "Back" to step 0 the template choice is preserved only by virtue of being a shared ref — that's actually fine. However, there is no form-level `rules` for `template_code` and it's optional on the type, so it's not validated. More importantly, if the user is *required* (per the placeholder "请选择..." hint suggesting it's expected) it's silently optional. Either make it required with a validation message in step 2, or document explicitly that it's optional.
- **建议代码**:
```
async function handleNext() {
  if (currentStep.value === 0) {
    const valid = await basicFormRef.value?.validate().catch(() => false);
    if (!valid) return;
  }
  if (currentStep.value === 1 && !formData.value.template_code) {
    ElMessageBox.alert("请选择一个映射模板（或在确认页继续选择）", "提示", { type: "warning" });
    return;
  }
  currentStep.value++;
}
```

## [51] LOW | maintainability
- **文件**: `frontend/web/src/views/module_medical/hospital/components/HospitalCreateDialog.vue`
- **行号**: 88
- **问题**: The `SearchFormItem` import is brought in via a relative path `@/components/forms/fa-search-bar/index.vue` which is unusual and likely incorrect: this component renders an internal `FaForm`, not a search bar. The intended type for `basicFormItems` is the form-item type from `FaForm`. Verify and replace with the proper type import (e.g. `FaFormItem` from `@/components/forms/fa-form`).
- **建议代码**:
```
// Replace with the actual form-item type used by FaForm, e.g.
// import type { FaFormItem } from "@/components/forms/fa-form";
```

## [52] LOW | maintainability
- **文件**: `frontend/web/src/views/module_medical/hospital/components/HospitalCreateDialog.vue`
- **行号**: 154
- **问题**: The `onTemplateChange` handler is a no-op placeholder and its parameter is prefixed with `_`. Either implement the preview extension now (or remove the listener) to keep the code intentional.
- **建议代码**:
```
// 预留：可扩展预览模板详情（目前模板摘要已在 ElAlert 中展示）
```

## [53] HIGH | bug
- **文件**: `frontend/web/src/views/module_medical/patient/components/DicomViewer.vue`
- **行号**: 450
- **问题**: In `setActiveTool`, the previous tool's Primary mouse binding is not deactivated. Once a tool is bound to Primary, it stays bound. Each subsequent call to `setActiveTool` adds another Primary-bound tool, so multiple tools will respond to left-click simultaneously. Use `setToolPassive(name)` (or `setToolDisabled(name)`) for the previously active tool before binding the new one, or use `toolGroup.setToolActive(newTool, { bindings: [{ mouseButton: MouseBindings.Primary }] })` together with `setToolPassive` on the previous one.
- **建议代码**:
```
function setActiveTool(toolName: string) {
  if (!toolGroup) return;
  // 1) 把所有非固定工具先置为 passive，避免同时响应左键
  ["WindowLevel", "Zoom", "Pan", "Length", "Angle", "Probe", "RectangleROI"].forEach(
    (name) => {
      if (name !== toolName) toolGroup!.setToolPassive(name);
    },
  );
  activeTool.value = toolName;
  toolGroup.setToolActive(toolName, {
    bindings: [{ mouseButton: MouseBindings.Primary }],
  });
}
```

## [54] MEDIUM | bug
- **文件**: `frontend/web/src/views/module_medical/patient/components/DicomViewer.vue`
- **行号**: 201
- **问题**: `probeValue` ref is declared and rendered in the overlay (`<div v-if="probeValue != null">HU: {{ probeValue }}</div>`), but it is never assigned anywhere. The `onProbeMove` handler is empty. Either implement real-time probe value retrieval (e.g., via viewport canvas coords → `viewport.getProperties()` / pixel data lookup) or remove the dead state and its UI binding.
- **建议代码**:
```
// 如果暂不实现，先移除 ref 与模板中 v-if="probeValue != null" 的分支，避免误导。
```

## [55] LOW | bug
- **文件**: `frontend/web/src/views/module_medical/patient/components/DicomViewer.vue`
- **行号**: 388
- **问题**: `onProbeMove` is registered as a global `MOUSE_MOVE` listener on every `renderStack`, but the body is empty (placeholder comment). This adds unnecessary global event dispatch overhead on every mouse move. Remove the listener registration and the unused handler until real probe logic is implemented.
- **建议代码**:
```
// 探针工具激活时由 cornerstone 自动在标注里展示 HU，
  // 实时鼠标移动展示留待后续迭代。如无需该事件，删除此行与对应 handler。
```

## [56] HIGH | bug
- **文件**: `frontend/web/src/views/module_medical/patient/components/DicomViewer.vue`
- **行号**: 495
- **问题**: `clearMeasurements` calls `toolsAnnotation.state.getAllAnnotations()` which returns annotations across ALL cornerstone annotation managers globally, not only for this viewport/element. If two DicomViewer instances coexist, calling "清除标注" on one will wipe annotations on the other. Filter by `metadata.element` (the viewport container) or by toolName/elementUID before removing.
- **建议代码**:
```
function clearMeasurements() {
  const element = viewportRef.value;
  const annots = toolsAnnotation.state.getAllAnnotations?.() || [];
  annots
    .filter((a: any) => !element || a.metadata?.element === element)
    .forEach((a: any) => {
      toolsAnnotation.state.removeAnnotation?.(a.annotationUID);
    });
  renderingEngine?.renderViewports([VIEWPORT_ID]);
}
```

## [57] LOW | bug
- **文件**: `frontend/web/src/views/module_medical/patient/components/DicomViewer.vue`
- **行号**: 320
- **问题**: `selectSeries` early-returns when the same series UID is clicked AND instances are already loaded. If the underlying instance list changes (e.g., new DICOM files added server-side) the viewer will not refresh. Either drop the optimization or invalidate when a refresh trigger fires.
- **建议代码**:
```
async function selectSeries(seriesUid: string, force = false) {
  if (!force && seriesUid === activeSeriesUid.value && instanceList.value.length) return;
  activeSeriesUid.value = seriesUid;
```

## [58] MEDIUM | performance
- **文件**: `frontend/web/src/views/module_medical/patient/components/DicomViewer.vue`
- **行号**: 298
- **问题**: `loadStudy` fetches ALL studies via `listStudies()` and filters client-side by `study_id`. With a non-trivial DICOM archive (hundreds/thousands of studies), this transfers the whole list every time the viewer opens. Use a server-side `GET /studies/{studyId}` endpoint or pass `studyId` as a query param to filter at the source.
- **建议代码**:
```
const seriesRes = await DicomAPI.listSeries(props.studyId);
    // 后端新增 GET /medical/dicom/studies/{studyId} 时改用单点查询：
    // studyInfo.value = (await DicomAPI.getStudy(props.studyId)).data?.data || null;
```

## [59] LOW | performance
- **文件**: `frontend/web/src/views/module_medical/patient/components/DicomViewer.vue`
- **行号**: 421
- **问题**: `prefetchNeighbors` uses `import("@cornerstonejs/core")` inside a loop. The dynamic import resolves to the same module every iteration, triggering duplicate promise resolutions and module cache lookups. Hoist the import to the top of the file (or capture `imageLoader` once at mount) and call `imageLoader.loadImage(id)` directly in the loop.
- **建议代码**:
```
try {
      const { imageLoader } = await import("@cornerstonejs/core");
      imageLoader.loadImage(id).catch(() => {});
    } catch {
      /* ignore */
    }
```

## [60] MEDIUM | maintainability
- **文件**: `frontend/web/src/views/module_medical/patient/components/DicomViewer.vue`
- **行号**: 286
- **问题**: `buildImageId` hardcodes `/api/v1/medical/dicom/instances` with `window.location.origin`. This couples viewer to (a) a specific URL prefix and (b) same-origin proxy. In deployments where the API lives at a different origin/reverse-proxy path, the loader will 404. Move the base path to a configurable constant (e.g., read from `import.meta.env.VITE_DICOM_API_BASE` or a shared `dicom` config module) and document the proxy contract.
- **建议代码**:
```
// 改为从运行时配置读取，便于在不同部署/反代路径下调整
const DICOM_API_BASE =
  (import.meta.env.VITE_DICOM_API_BASE as string) ||
  `${window.location.origin}/api/v1/medical/dicom/instances`;

function buildImageId(sopUid: string): string {
  return `wadouri:${DICOM_API_BASE}/${encodeURIComponent(sopUid)}`;
}
```

## [61] LOW | bug
- **文件**: `frontend/web/src/views/module_medical/patient/components/DicomViewer.vue`
- **行号**: 286
- **问题**: `buildImageId` interpolates `sopUid` directly into the URL. DICOM SOP Instance UIDs are not strictly URL-safe (may contain `.` and other reserved chars). Use `encodeURIComponent` to be safe against malformed UIDs triggering wadouri parsing errors or unintended path traversal.
- **建议代码**:
```
function buildImageId(sopUid: string): string {
  const base = `${window.location.origin}/api/v1/medical/dicom/instances`;
  return `wadouri:${base}/${encodeURIComponent(sopUid)}`;
}
```

## [62] LOW | maintainability
- **文件**: `frontend/web/src/views/module_medical/patient/components/DicomViewer.vue`
- **行号**: 167
- **问题**: `IToolGroup = any` discards all type safety on the cornerstone ToolGroup. The diff already notes this is to "evade type export differences", but the rest of the file is type-strict. Consider declaring a minimal local interface with only the methods used (`addTool`, `addViewport`, `setToolActive`, `setToolPassive`, `destroy`, etc.) so future refactors don't silently break the API contract.
- **建议代码**:
```
// 最小 ToolGroup 接口（仅声明用到的方法），避免全 any 丢失类型保护
interface IToolGroup {
  addTool: (name: string) => void;
  addToolInstance: (name: string, instanceId: string) => void;
  addViewport: (viewportId: string, engineId: string) => void;
  setToolActive: (name: string, opts?: any) => void;
  setToolPassive: (name: string) => void;
  destroy: () => void;
}
```
