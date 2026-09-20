# Issue 19: prefactor — 把 `_copy_then_merge` 抽成 promote 可复用的共用函数

## Parent

[事故复盘：测试清理按 center_code 级联删除 168,260 行 dicom_series](../findings/incident-20260920-test-cascade-delete.md)（§10 隔离落地记录 → 「先暂存再上」后续）

## What to build

**这是「先暂存再上」系列的 prefactor，本身不改任何行为。** 先做它，后面每一片都变薄。

`backend/app/plugin/module_medical/hospital/anon_etl_engine.py:162` 已有一个
`_copy_then_merge`：单事务内 `CREATE TEMP TABLE (LIKE target INCLUDING DEFAULTS)` →
`copy_records_to_table` → `INSERT INTO target SELECT ... FROM tmp ON CONFLICT ... DO UPDATE`。
**这正是 promote 需要的机制**（先暂存、再幂等上），只是现在它埋在 ETL 引擎里、只有一个调用点
（同文件 :789），外部拿不到。

本 issue 把它挪到 promote 与主 ETL **都能 import 的位置**，签名与行为保持不变。

**为什么先做**：否则 promote 会另写一套 upsert，两套逻辑各自演化 —— 而这正是本仓已经
吃过的亏（`_pg_available()` 被逐文件复制，最终没有单一落点，见复盘 §4.3）。

**端到端可验证**：主 ETL 现有测试全绿（行为未变），且 promote 命令能 import 该函数。

## Acceptance criteria

- [ ] `_copy_then_merge` 移到一个 `anon_etl_engine` 与 promote 命令**都能 import** 的位置
- [ ] **不产生循环依赖**（promote 侧 import 时 `anon_etl_engine` 不被反向拉起；若必须，说明取舍）
- [ ] 函数签名与语义不变：`CREATE TEMP TABLE ... LIKE ... INCLUDING DEFAULTS` → COPY → `ON CONFLICT ON CONSTRAINT ... DO UPDATE`
- [ ] `anon_etl_engine` 的调用点行为等价（`backend/app/plugin/module_medical/hospital/anon_etl_engine.py:789`）
- [ ] 现有 ETL 相关测试全绿（`tests/anon_etl/`），且**不新增**失败
- [ ] 在测试沙箱上可独立调用该函数完成一次 upsert（`ENVIRONMENT=test`，见 `backend/env/.env.test`）
- [ ] 不引入新的第三方依赖

## Blocked by

None - can start immediately.

## Notes for implementer

- 该函数当前是模块级 `async def`，所以「抽出」主要是在**放哪儿**：`anon_etl_engine` 与 promote
  之间谁 import 谁，决定了会不会成环。先读 `anon_etl_engine` 的 import 图再定位置。
- 别顺手改 `update_set` / `column_order` 的语义 —— 本 issue 是纯搬家。
- 沙箱用法：`cd backend && ENVIRONMENT=test uv run pytest tests/anon_etl/`；
  重建沙箱：`bash scripts/provision_lnrs_dev_sandbox.sh`。
