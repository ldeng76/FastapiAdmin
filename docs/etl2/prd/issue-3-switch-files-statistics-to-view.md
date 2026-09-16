# Issue 3: service 切视图 + 清理方案 A 临时改动

## Parent

[PRD: 让 medicalFiles 页面显示真实文件总大小](./PRD.md)

## What to build

让 backend 的 `MedFilesService.statistics_service` 不再聚合 `MedFilesModel` (=`lnrs_anon_imaging_study`) 上的 `count(m.id)` + 写死 0，而是聚合 `lnrs_anon_v_imaging_study_counts` 视图的 `total_bytes`。同步：

- 移除 `schema.MedFilesStatisticsOutSchema` 中 `total_size_bytes: int | None` 与 `total_size_text: str | None` 的 `| None` 类型——回到 `int` / `str`。
- 移除前端 `index.vue` 的 `renderTotalSize()` 函数（"—"兜底），恢复直接 `fileSize(statisticsCount.total_size_bytes, true)` 调用。
- 移除前端 `files.ts` 中 catch 兜底里的 `total_size_bytes: undefined`（保留 0 或 undefined 都可，统一即可）。
- 移除 `service.statistics_service` 内 `total_size_bytes = None` 的占位逻辑；改为从视图 SUM。

**端到端可验证**：

- 后端启动后 curl `GET /medical/files/statistics` 返回的 `total_size_bytes` 是数字、且 > 0；
- 前端 `/#/medicalFiles` 顶部「文件大小」显示真实字节数（如 `12.34 GB`），不再是 `—` 或 `0.00 B`；
- 切换筛选条件（模态/中心）后顶部统计仍正确反映筛选（**注意**：视图无 exam_type/file_type 字段，保留原 noop 行为 + 文档明示）。

## Acceptance criteria

- [ ] SQL 前置断言（Issue 2 必须完成）：`SELECT COALESCE(SUM(total_bytes),0) FROM lnrs_anon_v_imaging_study_counts;` 返回 > 0；若返回 0 或 89,180,336（仅 4 行），Issue 3 不应启动，需先回头完成 Issue 2。
- [ ] `backend/app/plugin/module_medical/files/service.py`：移除 `total_size_bytes = None` 占位、聚合源切到视图；保留 `file_count`/`patient_count`/`by_exam_type`/`by_file_type` 计算（**注意**：by_exam_type/by_file_type 在视图下需重新映射字段，参考 PRD §Implementation Decisions 的筛选条件备注）。
- [ ] `backend/app/plugin/module_medical/files/schema.py`：`total_size_bytes: int`、`total_size_text: str`，移除 `int | None` / `str | None` / `default=None`。
- [ ] `frontend/web/src/views/module_medical/files/index.vue`：移除 `renderTotalSize()` 函数、移除 `by_exam_type`/`by_file_type` 等无关重构（仅本 Issue 范围）；表格「文件大小」列 formatter 保留（方案 A 已改成 `typeof === 'number' ? fileSize : '—'`，切视图后会变为真数字，落入 else 分支）。
- [ ] `frontend/web/src/api/module_medical/files.ts`：catch 兜底里 `total_size_bytes` 统一为 `0`（与方案 A 的 `—` 路径不再一致；接口失败时合理显示 0 而非 undefined）。
- [ ] 后端：启动 dev 服务（用技能 lnrs-dev-start 或 `uv run python ...`），curl `GET /medical/files/statistics` 返回 JSON 中 `total_size_bytes` 为正整数、`total_size_text` 为 `X.XX GB`/`X.XX TB` 形式字符串。
- [ ] 前端：vue-tsc --noEmit 退出码 0；pnpm build（或 vite build）成功；浏览器打开 `/#/medicalFiles` 顶部「文件大小」显示非 `—` 非 `0.00 B` 的真实字节数。
- [ ] 集成验收：勾选/取消左侧筛选（模态、中心）后顶部统计实时刷新（仍是真实数字，因为视图 SUM 在筛选下也会变化——但视图无 exam_type 字段，模态筛选事实上 noop，需文档明示）。
- [ ] 不引入新的 ORM 模型、不动 0020 视图本身、不动 ETL-2 引擎。

## Blocked by

- Issue 2（dicom_series 已落库且视图 total_bytes > 0）。

## Notes for implementer

- 方案 A 的临时改动在 commit `722e4f66` 中落地（包含 `int | None` schema / `_human_readable_size(None)` 短路 / `renderTotalSize()` 函数 / catch 兜底 undefined / 表格空值 `—`）。
- 本 Issue 是**反向操作**：还原方案 A 的 UI/接口变更，让真实数字回到页面。
- **不要**直接 git revert 722e4f66——commit 信息会丢、本 Issue 的粒度更细（保留表格 formatter 的 `—` 处理）。
- service 的 `by_exam_type` / `by_file_type` 在视图下需要重新思考：视图有 `series_count` 但 modality 来自 dicom_series（需 LEFT JOIN）；本 Issue 倾向**保持原 noop 行为**（=空列表），等后续单独 issue 重构，理由是混合重构会扩大本 Issue 的爆炸半径。
- 若 service 切视图后 `file_count` / `patient_count` 与原 `MedFilesModel` 不一致，需说明（视图按 study 计数，MedFilesModel 也按 study 计数——当前是一致的，因为 MedFilesModel 的 __table__ 实际是 `lnrs_anon_imaging_study` 而非物理文件表，commit `202fd283` 之前如此；本 Issue 不变更此语义）。
- 部署不在本 Issue 范围：合并到 main 后由用户自行决定部署窗口。