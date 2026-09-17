# 方案：series_count 重新落库（lnrs_anon_dicom_series 加列 + ETL 实测 + 存量回填）

> 状态：代码实施完成（2026-09-17）；h196_3 全量回填后台运行中（预计 2.5-3 周）。
> 关联文档：[refactor-impact-dicom-series-study-level.md](refactor-impact-dicom-series-study-level.md)（2026-09-15 study 级重构，本方案是其系列修正）。
> 关联事实：`series_no` 等 series 级字段已随该重构移除（alembic 归档 `j0k1l2m3n4o5`，提交 669db807 / 2dcc0e14）。

## 背景

2026-09-15 将 `lnrs_anon_dicom_series` 从 series 级（一行 = 一个 SeriesInstanceUID）重构为 study 级（一行 = 一个 study）后，ETL 只做 `iterdir + stat`（不解析 DICOM header），导致「一个 Study 下有几个 Series」在系统内无任何数据来源：

- 表 `lnrs_anon_dicom_series` 只有 `file_count`（目录内全部文件数，不过滤模态）与 `byte_size`，无 series 维度（`backend/app/plugin/module_medical/hospital/anon_etl_engine.py:3097-3104`）；
- 视图 `lnrs_anon_v_imaging_study_counts.series_count` 写死 `0::INT`（`backend/sql/postgres/0020-imaging-study-counts-view.sql:41`）；
- API 同样硬编码：`anon_medical_query.py:621` `literal(0).label("series_count")`（`GET /patients/{patient_id}/imaging-studies`）；
- 磁盘上 study 目录内 instance 文件**平铺**（`dicom/repository.py:498-499`），无 Series 子目录可数，series 边界只在每个文件的 DICOM header (0020,000E) 中；
- 现成实测口径：`DicomIndexer.register_folder`（`dicom/repository.py:483`）解析 header 后返回 `series_count = len(idx.series)`（`repository.py:530`），约 10ms/instance。

## 目标与口径

给 `lnrs_anon_dicom_series` 加 `series_count INT NULL` 列（**NULL = 未实测**），使三处产出真实值：

1. ETL 落库时实测；
2. 存量回填脚本扫描在线目录补值；
3. 视图与 API 输出真实值（未实测行 COALESCE 0 兜底）。

**实测口径**：与 DICOMViewer 的 `register_folder` 完全一致——按 SeriesInstanceUID 去重计数，跳过非图像模态（SR/RTPLAN/RTDOSE/RTSTRUCT/ST，`repository.py:129`）与无 UID/解析失败文件。注意与 `file_count`（目录内全部文件数）语义不同。

## 改动范围详细

### Schema 层（DDL + SQL 存档）

- dev_h1963 直接执行（属主修正后 lnrs 角色已有 DDL 权限，2026-09-17 完成）：
  - `ALTER TABLE lnrs.lnrs_anon_dicom_series ADD COLUMN series_count INT;`
  - `ADD CONSTRAINT lnrs_anon_ck_dicom_series_series_count CHECK (series_count IS NULL OR series_count >= 0);`
  - 重建视图：`series_count` 改为 `COALESCE(s.series_count, 0)::INT`；
- 入库存档（项目惯例：手工 SQL 执行 + SQL 文件存档，alembic 不驱动本库）：
  - 新增 `backend/sql/postgres/0023-dicom-series-count.sql`（幂等：ADD COLUMN IF NOT EXISTS + DROP/CREATE VIEW + COMMENT）；
  - 同步 `backend/sql/postgres/0006-anonymized-schema-lnrs.sql` §7（:213-247 列清单加 series_count）；
  - 同步 `backend/sql/postgres/0020-imaging-study-counts-view.sql`（L41 与头部注释「series_count 固定为 0」改写）。

### ORM 层

- `AnonDicomSeriesModel`（`anon_model.py:382-424`）加 `series_count: Mapped[int | None] = mapped_column(Integer, nullable=True)`；
- 类 docstring（:383-397）补：口径定义、NULL 语义（未实测/目录离线）、与 file_count 的区别。

### ETL 引擎层

- `_upsert_dicom_byte_size_for_study`（`anon_etl_engine.py:3085-3160`）：
  - iterdir+stat 之后追加 `indexer.register_folder(path)` 实测 series_count；返回 None（目录在线但无 DICOM 文件）→ series_count=0；目录不存在 → 维持现状不写行；
  - upsert（:3140 `pg_insert ... ON CONFLICT (dicom_study_uid)`）增加 `series_count` 列（INSERT 与 UPDATE set_ 均加）；
  - 测完调用 `indexer.evict_study(...)` 防内存索引泄漏（沿用 `_import_dicom_series_for_center` 现有模式，`anon_etl_engine.py:2988`）；
- docstring 更新：撤销「不调 register_folder」承诺中的 series 部分（byte_size 仍走 stat，不回退）。

### 业务逻辑 / API 层

- `anon_medical_query.py:621` `literal(0).label("series_count")` 改为从 `_DICOM_SERIES_LEFT` 子查询（:602-606）取 `func.coalesce(..., 0)`；`:694-697` 的 int 规整兼容 None；
- 前端零改动：`DicomStudy.series_count` 字段已声明（`frontend/web/src/api/module_medical/dicom.ts:48`），后端出真值即自动生效；
- 视图消费者无需改动：后端代码未直接查询该视图（仅 `stats_query.py:372-386` 已注释的死代码提及）。

### 存量回填脚本（新文件 `backend/etl2/backfill_dicom_series_count.py`）

- 遍历 `lnrs_anon_imaging_study.image_path`（绝对路径，`anon_model.py:909`）逐 study：
  - 目录在线 → `register_folder` 实测 + upsert（只更 `series_count`，不动 `file_count`/`byte_size`）+ `evict_study`；
  - 目录缺失（移动硬盘出库，见 `docs/sour/存储上各Disk存放的数据说明.png`）→ 跳过并计数，series_count 保持 NULL；
- 幂等断点续扫：`WHERE series_count IS NULL`（新列初始全 NULL，天然支持中断重跑）；
- 每 500 study commit（沿用 ETL `BATCH_COMMIT_EVERY=500` 模式，`anon_etl_engine.py:3030`）；参数 `--center / --limit / --dry-run`；日志输出在线率与耗时估算；
- **执行环境约束：必须在服务器上执行**（`/data/wlx/DATABASE` 等路径仅服务器可见；本机 Windows SSH 22 不通、pg_hba 仅放行 lnrs 远程）。先 `--dry-run --limit 200` 估算在线率与总耗时，再全量跑。

### 测试（`backend/tests/anon_etl/`）

- 沿用现有模式：`asyncio.run()` 包裹（项目未启用 pytest-asyncio）、无本地 PG 时自动 skip（`_pg_available()`）；
- 用例：upsert 携带 series_count 的回归；`GET /patients/{id}/imaging-studies` 返回 series_count 非 0 断言（造数验证）。

### 文档

- 本文件即方案文档（`docs/etl2/prd/`）；
- `docs/lnrs_anon_tables.md` dicom_series 小节同步列结构与 series_count 语义。

## 执行顺序

1. 0023 SQL：对 dev_h1963 执行 DDL + 视图重建（幂等文件入库存档）；
2. ORM / ETL / API 代码改动 + 测试；
3. 回填脚本入库；服务器上 dry-run → 全量回填（用户或主会话在服务器 backend venv 下执行）；
4. 终验：抽样 study 比对 `register_folder` 结果、视图/接口输出真实 series_count、NULL 分布报告（在线率）。

## 影响清单（向下）

- `GET /patients/{patient_id}/imaging-studies` 响应中 `series_count` 从恒 0 变为真值（前端字段已就绪）；
- `v_imaging_study_counts.series_count` 从恒 0 变为真值（当前无后端代码消费，报表可用）；
- ETL `dicom_series` 落库步骤耗时回升：每 instance 增加一次 header 轻量解析（`stop_before_pixels + specific_tags`，~10ms），study 级重构的 10x 提速部分回吐——这是本方案已知且被接受的代价。

## 风险与回退

| 风险 | 缓解 |
|---|---|
| 数据盘出库导致大量目录离线，series_count 大面积 NULL | 预期行为；视图/API COALESCE 0 兜底；硬盘回传后重跑回填脚本（幂等续扫）即可 |
| 回填全量耗时不可控（82,994 study × 在线比例 × 文件数） | dry-run 先估；--center/--limit 分批；断点续扫 |
| register_folder 内存索引泄漏 | 每 study 后 evict_study（现有模式） |
| ETL 失败率（坏文件） | register_folder 内部按文件容错计数，不抛断；外层沿用 `failed_studies` 统计 |
| 回退 | DROP COLUMN series_count + 视图还原为 0::INT（0023 文件附反向 SQL）；代码层 series_count 输出改回 literal(0) 即可，无数据损失 |

## 工作量估计

- DDL + SQL 存档：0.5h；ORM + ETL + API：1.5h；测试：1h；回填脚本：1h；文档：0.5h；终验：0.5h。合计约 5h（不含回填脚本在服务器上的实际运行时长）。

## 决策记录

- 2026-09-17 用户在三个统计方案（按需 DicomIndexer / 全库一次性盘点 / 常态化落库）中选定**方案 3：常态化落库**；
- 口径选 `register_folder`（图像模态序列数），不做 `stop_after_tags` 最小 tag 集优化（留作后续性能选项）；
- 未实测行在视图/API 层显示 0（COALESCE），保留列内 NULL 以区分「实测 0」与「未实测」。

## 实施记录（2026-09-17）

### 0024 SQL：dicom_series.anon_exam_id 允许 NULL

h196_3 shengyi 82,994 study 中 `anon_exam_id` 100% NULL，ETL 主路径无法写入 dicom_series。
新增 `backend/sql/postgres/0024-dicom-series-anon-exam-nullable.sql`：
- `ALTER TABLE lnrs_anon_dicom_series ALTER COLUMN anon_exam_id DROP NOT NULL`
- 同步更新 0006 §7 DDL 与 COMMENT
- 保留 FK（NULL 不被 FK 检查；非 NULL 值仍需 exam 存在）

### 回填脚本新增 `--bypass-exam-fk` 模式

`backfill_dicom_series_count.py` 新增 `run_apply_bypass`：
- 直接 SQL INSERT/UPDATE dicom_series，`anon_exam_id = NULL`
- `created_batch_id` 从 `lnrs_anon_ingest_batch` 取真实 UUID（不再用伪 UUID）
- 绕过 `_upsert_dicom_byte_size_for_study` 的 ORM FK 强校验

### 性能迭代（h196_3 全量回填提速，目标 2-3 study/s）

初版单进程（`backfill_dicom_series_count.py`）实测 ~15-18s/study（0.05-0.1 study/s，
8 分钟仅 48 study），已停止。微基准（`/tmp/perf/bench.py`，part17 382 文件 study）
拆解单 study 耗时：

| 环节 | 耗时 | 占比 |
|---|---|---|
| NFS open+read 16KB | 10.3 ms/file | 77%（I/O bound） |
| pydicom dcmread | 2.8 ms/file | 21%（GIL bound） |
| iterdir+stat | 0.04 ms/file | ~0% |
| SQL upsert+commit | 61 ms/批 | <1% |

迭代过程（`backfill_dicom_series_count_mp.py`）：

| 迭代 | 方案 | 冷数据实测 | 结论 |
|---|---|---|---|
| 1 | ProcessPoolExecutor 12 workers + register_folder 直读 NFS | 1.80 study/s | I/O 等待不占 CPU，多进程有效 |
| 1.5 | 20 workers | 6.58 study/s（热缓存窗口） | 热缓存假象 |
| 2a | 20/30 workers 冷数据 | 0.77 / 0.76 study/s | **NFS 封顶**：加 worker 无效 |
| 2b | 多挂载点（同 export 4 mounts）直读 | 0.79 study/s | 小文件 I/O 不随连接数扩展 |
| 2c | tar 全量→本地盘 staging + register_folder | 1.05-1.1 study/s | 本地 HDD 元数据 IOPS 争用（242MB/s 上限） |
| 2d | tar 全量→/dev/shm tmpfs staging | 1.07 study/s | 瓶颈回到 NFS 本身 |
| 2e | rsize=1MB 挂载 | 被服务端 clamp 到 256KB | 不可行 |
| **3** | **采样快速路径**（见下） | **30-47 study/s** | **达标 10 倍以上** |

NFS 瓶颈定量（`/proc/net/rpc/nfs` + 并发扫描 P=1..32）：
- 服务端每客户端封顶 ~1000-1600 READ RPC/s；rsize=256KB → 聚合带宽 ~250-330MB/s
- 单流「GB/s」读数来自服务端缓存热窗（共享生产存储，随时间波动），不可持续依赖
- 全文件解析 = ~1400 RPC/study（407 文件 × open/read×2/close）→ 0.77-1.1 study/s 封顶

**迭代 3 原理（采样快速路径）**：
- 数据布局实测：`image_path` 恒为「单 series 叶目录」
  （`/06_disk/<part>/<patient>/<study_uid>/<series_uid>/*.*`；3,888 目录样本
  全部 0 子目录 + 数千次 register_folder 全量解析 series_count 均为 0/1）
- 快速路径 ~22-25 RPC/study：scandir 一次 READDIR（READDIRPLUS 属性缓存，
  stat 零 RPC）得 file_count/byte_size；采样前 5 + 后 2 个文件头（16KB/个）
  按 `register_file` 完全相同的跳过规则判定 series_count=1
- 异常兜底（混入第二个 series / 采样全部不可解析）→ `indexer.register_folder`
  全量重解析（与 ETL 零口径偏差）
- 正确性交叉验证：30/30 study 快速路径 vs register_folder 真值完全一致，
  0 次回退

### h196_3 全量回填（最终版）

- 命令：
  ```bash
  ENVIRONMENT=h196_3 uv run python etl2/backfill_dicom_series_count_mp.py \
      --apply --center shengyi --workers 24 \
      --mounts /data,/mnt/nfs_b,/mnt/nfs_c,/mnt/nfs_d
  ```
- 启动时间：2026-09-17 15:44（前序单进程版 14:06 启动的已停止）
- 候选 81,261 study（含 part07-12 ~30k 离线行，主进程预筛过滤）
- 实测速率：**45-47 study/s**（failed=0），ETA ~22 分钟
- 进度查询：`grep "进度" /tmp/backfill_series_count_mp.log | tail -5`
- 落库验证：
  ```sql
  SELECT count(*) FROM lnrs.lnrs_anon_dicom_series WHERE series_count IS NOT NULL;
  ```
- 说明：part07-12（~30,002 study）磁盘目录缺失（离线），`series_count` 保持
  NULL（视图/API COALESCE 显示 0，语义=未实测）；如需补数，待数据恢复后
  重跑同一命令即可（幂等，`WHERE series_count IS NULL` 续扫）
