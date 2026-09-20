# 新桥 dicom_series 计数校正：series_count / byte_size 以 PACS 导出为准（2026-09-20）

## 1. 背景与结论

用户指出 `ct_mapped.parquet`（CT 报告+DICOM 合并版，与 issue-13 灌库的 ct.parquet
同一批数据，ID 未匿名化仅作参考）中的 `file_count`（= series 数）与
`total_size_bytes` 应取入 `/medicalFiles` 页面的【总文件个数】【总大小】。

排查发现 **xinqiao 33,314 个 study 的 `dicom_series.series_count` 大面积低估**：
19,238 个 study 记 1（磁盘扫描器对新桥 zip_folder / 布局 C 的 series 枚举不全，
抽验 1 例：磁盘实有 11 个 series 子目录 / 11 个 distinct SeriesInstanceUID，
库内记 1，PACS 导出记 12——PACS ≥ 磁盘实测，差额为未落盘文件）。
byte_size 另有 128 行与导出值不一致（同为落盘不全，方向一致）。

**校正**（`backend/etl2/backfill_xinqiao_series_counts_from_pacs.py --apply`）：

| 指标 | 前 | 后 |
|---|---:|---:|
| Σseries_count（页面【总文件个数】基数） | 79,864 | **143,609** |
| Σbyte_size（页面【总大小】） | 4,358,671,594,046 | **4,359,981,928,899**（+1.31 GB） |
| UPDATE 行数 | — | **19,239**（fc 变化 19,238 / sz 变化 128） |

备份：`lnrs.lnrs_anon_dicom_series_bak_20260920_191056`（校正前 33,314 行快照）。

## 2. 对账（ct_mapped ↔ ct.parquet ↔ 库内）

| 项 | 结果 |
|---|---|
| ct.parquet 124,045 行 sha256('xinqiao:'+exam_id) ↔ 库内 source_exam_hash | **124,045/124,045 全命中，0 多余** |
| ct_mapped 有日期行 124,046 ↔ ct.parquet 按 (patient_id, exam_date) | 全配，raw_text **全等 124,046**；108 对「不等」为同患者同日多报告的交叉配对 |
| ct_mapped 41,298 行 exam_id=StudyInstanceUID ↔ imaging_study.dicom_study_uid | **33,314 精确命中**（另 7,984 = cxf_archives 未入库） |
| ct_mapped 无日期行 | 262（ct.parquet 无对应，含 262 新患者；纯报告，未入库，不属本次范围） |
| ct_mapped Accession 纯报告行 | 83,010（无 DICOM 文件，未入库，不动） |

结论：**ct_mapped 与已灌 exam 为同一批数据**，StudyUID 行的 (file_count,
total_size_bytes) 即库内 33,314 study 的 PACS 权威计数值。

## 3. 执行记录

| 步骤 | 结果 |
|---|---|
| TDD seam 测试（`plan_updates` 8 例） | 8/8 passed |
| dry-run | 待更新 19,239；Σseries_count 79,864 → 143,609 |
| apply（19:10:56） | BACKUP +33,314 → STAGE +19,239 → **UPDATE 19,239** → 剩余差异 0 → zj/sy 零漂移 |
| 幂等重跑 | 待更新 0 / UPDATE 0 |
| 验收 SQL `docs/etl2/verify_xinqiao_series_counts.sql` | V1=0 / V2 新值 / V3 旧基线 / V4=19,239 / V5 / V6 / V7=124,045 全过 |

**过程缺陷（已修复）**：首次 apply 的 UPDATE 漏了显式 `commit()`，会话关闭被回滚
（与 issue-13 记录的 `_close_batch` 缺陷同款），且同会话验收读到未提交脏值造成
假阳性。修复：补 commit + 验收改独立连接（`_count_remaining_diff`）。

**异常观测（非本次操作所致，留档）**：19:09-19:11 间观测到 zhujiang
Σbyte_size 一次读数 20,487,298,710,355 → 之后稳定 20,487,229,514,795（差
69,195,560）。本脚本 UPDATE 按 dicom_study_uid（全局 UNIQUE，跨中心重叠实测 0）
限定 xinqiao，物理上不涉及 zhujiang 行；apply 窗口内 zj/sy 基线前后一致，幂等
重跑前后亦一致。变更源不明（本机 dev 后端常驻，无 ETL 进程；2h 内 updated_at
无变化——该表无 updated_at 触发器，裸 SQL 更新不会留痕），待观察。

## 4. 变更文件

| 文件 | 改动 |
|---|---|
| `backend/etl2/backfill_xinqiao_series_counts_from_pacs.py` | 新建：dry-run/apply，备份→临时表→UPDATE→独立连接验收 |
| `backend/tests/anon_etl/test_backfill_xinqiao_series_counts.py` | 新建：`plan_updates` seam 测试（8 例） |
| `docs/etl2/verify_xinqiao_series_counts.sql` | 新建：V1–V7 验收 SQL |
| `docs/etl2/verify_result/xinqiao-series-counts-fix-20260920.md` | 本报告 |

## 5. 后续

- issue-15（新桥占位真实化）仍暂停；其决策门调研结论（exam/ct_mapped 均无
  sex/birth_date；真实人口学源为 `01_disk/_字段与原始数据/2新桥/1_5万例排除术后…`
  46,407 人 100% 覆盖、与影像 PID 交 33,312/33,313、DICOM 年龄交叉验证 12/12）
  待工单重启时并入决策。
- ct_mapped 的 262 个新患者（StudyUID 行无 exam_date）与 7,984 个 cxf study
  的入库，留待后续工单。
