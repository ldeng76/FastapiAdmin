Here's my comprehensive review of the `backend/app/plugin/module_medical/hospital/etl1` module:

---

## ETL-1 Module Review: Excel/CSV → Parquet Pipeline

### Architecture Summary

Well-structured, multi-hospital extensible ETL pipeline with clear separation of concerns:

| Module | Responsibility |
|--------|---------------|
| `config.py` | Pydantic schemas + center registry |
| `excel_reader.py` | DuckDB Excel extension wrapper |
| `transforms.py` | Registered column transforms (Python + SQL) |
| `visit_resolver.py` | Cross-table `(patient_id, m) → visit_id` backfill |
| `manifest.py` | `conversion_manifest.json` generation |
| `core.py` | Main loop: single sheet, derived merge, visit resolution |
| `service.py` | FastAPI background task + Redis progress tracking |
| `centers/shengyi.py` | Per-hospital config (~600 lines of field mappings) |

---

### 🔴 Critical Issues

#### 1. **Forked `read_xlsx` views in `core.py` — duplicate reads** (`core.py:236-249`)
`_process_single_sheet` first calls `reader.read_sheet()` at line 236 (which creates a temp view), then immediately creates **another** temp view at lines 243-249 reading the same sheet again. The first view is never used. This doubles I/O for every sheet — on a 200MB file with 26 sheets, that's significant wasted work.

```python
# Line 236: reads and creates a view
rel = reader.read_sheet(spec.sheet_name)
# Lines 237-249: ignores `rel`, creates ANOTHER view from scratch
view_name = f"_v_{spec.target_table}_{abs(hash(spec.sheet_name)) % 100000}"
con.execute(f"CREATE OR REPLACE TEMP VIEW {view_name} AS SELECT * FROM read_xlsx(...)")
```

**Fix:** Either use the relation returned by `reader.read_sheet()` directly, or don't call `read_sheet()` at all in `_process_single_sheet`.

#### 2. **`_PYTHON_ONLY_TRANSFORMS` defined *after* first use** (`core.py:163`)
`_PYTHON_ONLY_TRANSFORMS` is referenced at line 113 inside `_build_select_for_sheet` but defined at line 163. Python executes functions lazily so it works at runtime, but if `_build_select_for_sheet` is ever called before module-level execution reaches line 163 (unlikely but possible with circular imports), it'll raise `NameError`. More importantly, it's a **readability smell** — a constant used in a function appears 50 lines after the function.

#### 3. **`_parse_select_body` is fragile** (`core.py:342-381`)
This hand-rolled SQL parser splits on `, ` and ` AS ` to reconstruct `{tgt: expr}` for derived table column alignment. The docstring even admits the caveat: *"对于 CAST(... AS TYPE) 这种含 AS 的表达式可能出错"*. And indeed, it **does** have a bug: the `" AS "` search at line 374 uses `p[i:i+4] == " AS "` which matches `"CAST"` — the substring `" AS "` appears inside `" AS "` in expressions like `CAST(x AS VARCHAR)`. Actually wait — let me re-read... It tracks parenthesis depth correctly and only matches at `depth == 0`, so it *does* handle `CAST(x AS VARCHAR)` correctly. However, it will break on nested functions or expressions containing `, ` at the top level (e.g., `CONCAT(a, b) AS col`).

**Risk:** If any column expression ever uses a multi-argument SQL function, the parser silently produces wrong output.

---

### 🟡 Medium Issues

#### 4. **Hash collision in view names** (`excel_reader.py:102`, `core.py:243`)
```python
view_name = f"_v_read_{abs(hash(sheet_name)) % 10000000}"
```
`% 10000000` means 10 million buckets — with only 26 sheets this is fine today, but it's a ticking bomb. Two sheets with colliding hashes would silently overwrite each other's view. Use the full hash or sanitize the sheet name directly.

#### 5. **`_process_derived` reads each sheet twice** (`core.py:288-319`)
`_build_select_for_sheet` calls `reader.read_sheet(...).limit(0)` to read headers (line 93), then `_process_derived` calls `con.execute("CREATE OR REPLACE TEMP VIEW ... read_xlsx(...)")` again (line 312). Each source sheet is read from disk at least twice.

#### 6. **`resolve_visits` stats query is wrong** (`visit_resolver.py:145-152`)
The matched/missed count queries the **temp parquet** file which already has `visit_id` baked in, then does a **second LEFT JOIN** against `_visit_dict`. This counts matches against the *already-merged* file, not the *before state*. The log comment acknowledges this: *"含已存在 visit_id 的近似统计"*. The numbers are misleading for troubleshooting.

#### 7. **Race condition on Redis status key** (`service.py:363-381`)
`_update_status` does a read-modify-write on Redis without locking. If two tables complete nearly simultaneously (possible with fast sheets), concurrent calls could lose each other's updates. Not critical since `on_table_done` runs single-threaded in the worker, but the design doesn't enforce that guarantee.

#### 8. **`_MATCH_STRIP` is a module-level mutable toggle** (`excel_reader.py:27`)
```python
_MATCH_STRIP = True
```
This is a global flag that changes `normalize_header()` behavior. If someone sets it to `False` for testing, it affects all callers. Either remove the toggle or make it a parameter.

---

### 🟢 Minor Issues / Nits

#### 9. **`_common_keys()` in shengyi.py returns `visit_ordinal` with wrong source** (`shengyi.py:69-73`)
```python
def _common_keys() -> list[ColumnSpec]:
    return [
        _str("患者编号", "patient_id", required=True),
        _str("当前命中就诊次数/命中就诊总次数", "visit_ordinal"),
    ]
```
This is used via `*_common_keys()` in many specs. But column matching in `build_column_map` does strip-based matching — `"患者编号"` matches the standalone column A (always present). However, some sheets have the **fully qualified** header `"非隐私信息.患者基本信息.患者编号"` instead of just `"患者编号"`. If the Excel header is the dotted form, `_common_keys()` won't match it. The code happens to work for shengyi because column A is always just `"患者编号"`, but it's fragile for other hospitals.

#### 10. **Missing `close()` on Redis in error path** (`service.py:308-344`)
The `finally` block at line 342 does `await redis.aclose()`, but if `_run_etl1_background` itself raises during `AsyncRedis.from_url()` (line 204), `redis` is never defined and the `finally` block raises `UnboundLocalError`. Add a `redis = None` guard before the try.

#### 11. **`_NULL_SENTINELS` includes `"nan"` case-sensitively** (`transforms.py:34`)
```python
_NULL_SENTINELS = {"", "null", "None", "NULL", "nan", "NaN"}
```
Missing `"NAN"`, `"nAn"`, etc. Excel sometimes produces `"NAN"` (uppercase). Consider `.lower()` comparison or add more variants.

#### 12. **No test files found**
The directory has zero test files. For an ETL pipeline processing 200MB medical files, this is risky. At minimum: unit tests for `transforms.py`, `build_column_map`, and `_parse_select_body`.

#### 13. **`genetic_test` silently skipped** (`shengyi.py:572-577`)
The genetic_test universal table is not registered because all 6 sheets are header-only. The comment says downstream ETL-2 skips on absence. But there's no explicit test/guard for this contract — if ETL-2 changes to *require* the file, it silently breaks.

---

### ✅ What's Done Well

1. **Pydantic config schema** with frozen models, field validators, and cross-module constraints (`_SRC_TABLE_RE`) — excellent defense-in-depth.
2. **Registry pattern** for hospitals — adding a new hospital is just one Python file + one import.
3. **SQL-layer processing** for heavy lifting (column selection, type casting, dedup via `DISTINCT ON`) with Python UDFs only where necessary — smart performance strategy.
4. **Security** — target table whitelist, path traversal checks, sheet name sanitization.
5. **Lazy duckdb relations** with `COPY ... TO parquet` avoiding Python-side materialization of large datasets.
6. **`visit_resolver`** using `os.replace()` for atomic file swaps — correct pattern.
7. **Service layer** with proper cross-thread coroutine scheduling (`run_coroutine_threadsafe`) and independent DB sessions for error handling.