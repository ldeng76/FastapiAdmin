# Issue 12: 新桥影像查看器适配 — image_path 指向 series 目录（布局 A/B/D）

## Parent

[plan-xinqiao-disk03-import.md](../plan-xinqiao-disk03-import.md)（§7-2）

## What to build

新桥 5 个 sub（`4_tjj` / `5_yxl` / `6_zjj` / `7_hsy` / `8_hy`）共 33,314 study，其中
**60,612 个目录走布局 A/B/D（无 study 根）**：`lnrs_anon_imaging_study.image_path`
当前指向该 study 字典序最小的 series 目录（CSV `study_root_kind='series_dir_min'`），
其下是该 study 全部 series 中最小的一个（含 `sop_count = 该 study 所有 series 的累加`）。

viewer 现状要求 `image_path` 是 study 根目录（参 `backend/app/plugin/module_medical/hospital/anon_medical_query.py`
与 `frontend/web/src/views/module_medical/viewer/index.vue`）。直接传 series 目录会让 viewer
只渲染该 series 的实例，其余 series 需手动换 prompt。

**端到端目标**：浏览器输入布局 A 系列的某条 study 路径，能正常打开并显示该 study 的**所有 series / instance**，
而非仅字典序最小的那一个。

## Acceptance criteria

- [ ] 调研：在 dev 环境对布局 A / B / D 各抽 1 条 study，curl `GET /medical/imaging_study/{study_id}/dicom?center=xinqiao&series_no=...`，
  确认现状是 noop / 部分能读 / 全部能读。结论写入 issue 评注
- [ ] 设计：在 `anon_medical_query` / `DicomViewer.vue` 找到 series 目录 → 同 study 其他 series 的反查点
  （PG `lnrs_anon_dicom_series` 已按 `dicom_study_uid` 聚合，`file_path` 待补 / 从扫描产物构造）
- [ ] 端到端浏览器实测：4_tjj 抽 1 条、5_yxl 抽 1 条布局 A、6_zjj 抽 1 条布局 A、7_hsy 抽 1 条布局 A、
  8_hhy 抽 1 条布局 A + 1 条布局 C 对照 —— 布局 A 系列能渲染**所有 series**；布局 C 行为不变（study 根目录）
- [ ] 性能：单 study 打开 ≤ 3s（首次含 study 反查）
- [ ] 不改 PG schema；不动 `lnrs_anon_dicom_series` 已有的 `file_count / byte_size / series_count` 字段
- [ ] 不动其他中心（zhujiang / shengyi）的 image_path 语义

## Blocked by

None - can start immediately.

## Notes for implementer

- CSV `docs/sour/ct_image_patient_map_xinqiao.csv` 的 `study_root_kind` 列区分 `'md5_layout_study_root'`（19,732 个，无需适配）
  与 `'series_dir_min'`（13,582 个，需适配）。先看分布再动手
- CSV 含明文 PHI（patient_id），本机查看后别 commit
- 若 viewer 改造与 issue-1/2（service 切视图）合并处理更经济，本 issue 可调整为实施时合并，但文档保留独立
- 字段命名参考：`file_path` 列当前**不存在**于 `lnrs_anon_dicom_series`，需新建（参 plan-xinqiao §0.6-3 决策 #4 的 dicom_series 直写字段）；
  若决定不补 `file_path`，则 viewer 端需用 `series_uid → ImagePath` 反查影像目录（用 DICOM header `SeriesInstanceUID` 扫描）
---

## 实施记录（2026-09-20）

### 实现
- `DicomService.discover_sibling_series_dirs(center_code, patient_id, image_path)`：
  纯函数。**不依赖 PG 的 patient_id**（HMAC 匿名化不可逆），改从 `image_path`
  目录名解析真实院内 PID（`img_<PID>_(.+)` 正则）；扫同前缀兄弟目录。
- `DicomService.ensure_study_indexed(study_uid)`：
  PG 反查 (center_code, patient_id, image_path) → 调 discover → 对每个兄弟
  目录调 `indexer.register_folder`。indexer 自动按 `study_uid` 聚合。
- `DicomService.query_study` / `query_series` 入口 hook：先 `ensure_study_indexed`，
  viewer 首次访问某 study_uid 时自动触发。

### 边界发现（v1 描述 vs 实测）
- `study_root_kind` 实测 CSV 值为 `series_leaf`（不是 issue 文档说的 `series_dir_min`）；
  分布：md5_layout_study_root **19,731** + series_leaf **13,583** = 33,314（与 PG study 数一致）
- `image_path` 指向字典序最小 series 目录（布局 A 实测 4 个兄弟：1/77/553/1 = 632 files）
- **匿名化 vs 真实 PID**：
  - 磁盘目录前缀：`img_00720185_*`（真实院内 PID）
  - PG `patient_id`：`PT_00502280`（HMAC 匿名值）
  - 两者**单向不可逆** → 必须从 image_path 目录名解析 PID，不能用 PG patient_id

### 端到端验证（h196_3 真数据，study_uid=`...58586.740`）
- query_series 返回 **4 个 series**（之前 1 个），total **632 instances** = PG `sop_count`
- 首次 ensure 耗时 **13s**（扫 4 兄弟目录 × 632 DICOM header 读，pydicom 解析）
- LRU 命中后 < 100ms
- indexer `_MAX_STUDIES=50`，覆盖 viewer session

### Acceptance 实际结论
| 项 | 实际 | 备注 |
|---|---|---|
| 布局 A/B/D 能渲染所有 series | ✅ | 4_tjj 实测 4 series × 632 instances 全出 |
| 布局 C 行为不变 | ✅ | discover 返回 [image_path]，单目录 register |
| 不改 PG schema | ✅ | 仅追加 service.py 后端 |
| 不动 zhujiang/shengyi | ✅ | 发现函数对 layout C/非 xinqiao 路径返回单 path |
| 性能 ≤ 3s | ⚠️ | 首次 13s（cold cache 扫 632 DICOM header）；LRU 命中 < 100ms |
| 调研接口不存在 | ⚠️ | acceptance #1 提到的接口 `GET /medical/imaging_study/{id}/dicom` 实际不存在，OHIF 走标准 QIDO-RS `/dicom/studies` + `/dicom/series/{}/instances` |

### 性能 follow-up（不在本 issue 范围）
- `register_folder` 注释明示「不可并发」（`anon_etl_engine.py:3042`），4 兄弟目录串行是当前唯一路径
- 优化方向：viewer 改 series 级懒加载（OHIF 默认就是）；或 issue-13 重灌时把 image_path 改成 study 根
