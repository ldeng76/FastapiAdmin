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