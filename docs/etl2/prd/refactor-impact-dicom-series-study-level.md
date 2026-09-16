# 影响评估：dicom_series 重构为 study 级 byte_size

> 决策日期：2026-09-15
> 状态：调研完成，待用户决策

## 背景

方案 B 路线在 Issue 2 试跑阶段暴露问题：`_upsert_dicom_series_for_study` 调 `DicomIndexer.register_folder()` 触发 pydicom 解析每个 .dcm header，~10ms/instance。zhujiang 36,342 study × ~30 instance = ~110 万次 pydicom.dcmread ≈ 3-6 小时。

**用户反馈**："我只想要 byte_size，dicom_series 为什么弄得这么复杂？"

## 重构核心：扔掉 series 级拆分

dicom_series 从"每行 = 一个 series"改为"每行 = 一个 study"：

| 当前 | 重构后 |
|---|---|
| 1 行 = 1 series | 1 行 = 1 study |
| 有 series_uid / modality / instance_count / series_no / file_root | 只保留 study_uid + file_count + byte_size |
| 通过 register_folder 解析 DICOM header | 仅 `iterdir + stat`，不调 pydicom |
| 单 study 耗时 ~300ms | 单 study 耗时 ~30ms |
| zhujiang 全量 ~3-6 hr | zhujiang 全量 ~18 min |

## 改动范围详细

### Schema 层（DDL + alembic）

**`backend/sql/postgres/0006-anonymized-schema-lnrs.sql` §7**：

- 删除原 `lnrs_anon_dicom_series` 表（含 DICOM series_uid/modality/body_part/series_no/file_root）；
- 重建为 study 级 schema：
  ```sql
  CREATE TABLE lnrs.lnrs_anon_dicom_series (
      series_id        BIGSERIAL    PRIMARY KEY,
      anon_exam_id     VARCHAR(40)  NOT NULL REFERENCES lnrs.lnrs_anon_exam(anon_exam_id) ON DELETE CASCADE,
      dicom_study_uid  VARCHAR(64)  NOT NULL UNIQUE,
      file_count       INT          NOT NULL CHECK (file_count >= 0),
      byte_size        BIGINT       NOT NULL,
      created_batch_id UUID         NOT NULL REFERENCES lnrs_anon_ingest_batch(batch_id) ON DELETE CASCADE,
      created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
      CONSTRAINT lnrs_anon_uq_series_study_uid UNIQUE (dicom_study_uid)
  );
  ```
- **注**：`series_id` PK 名字保留（避免下游 ORM 大改）。

**alembic 迁移**：

- 新增 `app/alembic/versions/j0k1l2m3n4o5_refactor_dicom_series_study_level.py`：
  - DROP TABLE lnrs_anon_dicom_series CASCADE（含视图依赖）
  - CREATE 新 schema
  - **数据迁移**：现有 4 行（手工验证）按 study_uid 去重后批量 INSERT
  - 备份 SQL：`CREATE TABLE lnrs_anon_dicom_series_bak_<ts> AS TABLE lnrs.lnrs_anon_dicom_series;`

**`backend/sql/postgres/0020-imaging-study-counts-view.sql`**：

```sql
CREATE OR REPLACE VIEW lnrs.lnrs_anon_v_imaging_study_counts AS
SELECT
    ims.study_key,
    ims.dicom_study_uid,
    ims.center_code,
    ims.patient_id,
    ims.anon_exam_id,
    COALESCE(s.byte_size, 0)::BIGINT   AS total_bytes,
    COALESCE(s.file_count, 0)::INT      AS instance_count,
    0::INT                              AS series_count
FROM lnrs.lnrs_anon_imaging_study ims
LEFT JOIN lnrs.lnrs_anon_dicom_series s
       ON s.dicom_study_uid = ims.dicom_study_uid;
```

### ORM 层（SQLAlchemy）

**`backend/app/plugin/module_medical/hospital/anon_model.py` `AnonDicomSeriesModel`**：

- 删除字段：`dicom_series_uid`, `modality`, `body_part`, `series_no`, `file_root`, `file_count_actual`
- 保留字段：`series_id`, `anon_exam_id`, `dicom_study_uid`, `created_batch_id`, `created_at`, `updated_at`
- 新增字段：`file_count: int`, `byte_size: int`
- 删除 `__table_args__` 里的 `instance_count > 0` CHECK（字段没了）
- UNIQUE 约束改为 `(dicom_study_uid)`

### ETL 引擎层（最大改动）

**`backend/app/plugin/module_medical/hospital/anon_etl_engine.py`**：

1. 删除 `_upsert_dicom_series_for_study`（series 级实现）
2. 新增 `_upsert_dicom_byte_size_for_study`：
   ```python
   async def _upsert_dicom_byte_size_for_study(
       db, *, image_path, dicom_study_uid, anon_exam_id, batch_id,
   ) -> int:
       path = Path(image_path)
       if not path.is_dir():
           log.warning(f"ETL2: dicom_series 跳过（目录不存在）study={dicom_study_uid}")
           return 0
       files = [p for p in path.iterdir() if p.is_file()]
       if not files:
           log.warning(f"ETL2: dicom_series 跳过（目录无文件）study={dicom_study_uid}")
           return 0
       file_count = len(files)
       byte_size = sum(p.stat().st_size for p in files)
       
       stmt = pg_insert(AnonDicomSeriesModel.__table__).values(
           anon_exam_id=anon_exam_id,
           dicom_study_uid=dicom_study_uid,
           file_count=file_count,
           byte_size=byte_size,
           created_batch_id=batch_id,
       )
       stmt = stmt.on_conflict_do_update(
           index_elements=[AnonDicomSeriesModel.__table__.c.dicom_study_uid],
           set_={
               "anon_exam_id": stmt.excluded.anon_exam_id,
               "file_count": stmt.excluded.file_count,
               "byte_size": stmt.excluded.byte_size,
           },
       )
       await db.execute(stmt)
       return byte_size
   ```

3. 修改 `_import_dicom_series_for_center` 调用新函数

### DicomIndexer 使用范围收缩

`DicomIndexer.register_folder` **不再被 ETL-2 dicom_series 阶段使用**——但仍是：
- OHIF viewer 实时预览 DICOM 的核心组件
- DICOMweb 接口的内存索引
- DicomViewer / DicomStudy 实时交互的依赖

**修改范围限定在 ETL-2，不动 DicomIndexer 本身**。

### 业务逻辑层

**`backend/app/plugin/module_medical/hospital/anon_medical_query.py`**：

- 移除 `_SERIES_COUNT_SUBQ` 子查询（line 565-568）：原 `series_count` 字段不再落库（改为视图 0）
- `anon_list_patient_imaging_studies` 返回的 `series_count` 字段：从"聚合 dicom_series" 改为"视图 v_imaging_study_counts.series_count"（永远是 0）

**`backend/app/plugin/module_medical/hospital/stats_query.py`**：

- 删除 `query_series_counts_by_modality`（依赖 modality 聚合，series_uid 没了无法用）
- 或改为 `query_byte_size_by_center`（study 级总字节）

### 前端

**`frontend/web/src/views/module_medical/dicom/`（DicomViewer）**：

- 顶部「序列数 / 切片总数」computed（commit f8dd292e 引入）：移除 series_count 部分；保留 instance_count（仍由 dicom_instance 接口实时给）
- 实际影响：原"序列数 X"显示从 dicom_series 表读取改为**前端拿不到稳定数字**——可选修复：调 `/dicomweb/studies/{study}/series` 实时接口，但增加页面渲染时间

**`frontend/web/src/views/module_medical/patients/index.vue`**：

- `series_count` 列：移除或显示 "—"
- 注：核验清单并未要求 `series_count` 必须展示

### 不动的部分

- DICOMweb 实时接口（`/dicomweb/studies/...`）不动——仍走 `DicomIndexer`
- `lnrs_anon_imaging_study` 表不动
- 0020 视图的结构（仅 GROUP BY 改 LEFT JOIN）
- 服务端 service.py / schema.py：原 PRD 已切到视图，**重构后视图依然有 `total_bytes`，无需再改 service**

## 影响清单（向下）

| 维度 | 影响 |
|---|---|
| 数据库迁移 | DROP TABLE + CREATE，新 alembic 迁移文件 |
| 现有数据 | 现有 4 行（commit f8dd292e 手工）按 study_uid 去重后保留 |
| ETL-2 引擎 | 函数重写，预计 80 行变化 |
| DICOM Viewer | 顶部"序列数"不再稳定显示 |
| 患者列表 | `series_count` 列无数据 |
| 仪表板 | `query_series_counts_by_modality` 删除；改为 study 级字节数聚合 |
| 视图 | 0020 视图重写 |
| 业务接口 | `statistics` 接口（PRD Issue 3）：输出仍正确（视图 total_bytes 一致） |

## 风险与回退

| 风险 | 缓解 |
|---|---|
| DDL DROP CASCADE 误删依赖 | 备份表 `lnrs_anon_dicom_series_bak_<ts>` |
| alembic 迁移失败回滚 | 迁移自带 down_revision；失败 DOWN 后保留 bak 表还原 |
| series_count 字段消失 | 前端 `—` 兜底；DICOMweb 实时接口仍可用 |
| 文件实际大小与 DICOM 标准大小不一致 | DICOM 文件 = 整个 .dcm 字节数；OS stat 准确 |
| 单 study 文件数与 DICOM instance 数不一致 | 假设 study 目录下"所有 .dcm 都是 image instance"——register_folder 当前也是这么处理的；非图像模态会被 register_folder skip，但 stat 全部计入。新设计不区分。**影响**：file_count 数字会略大于真实的 image instance 数。 |

**关于 file_count 与真实 instance 数偏差**：现状 register_folder 用 `_NON_IMAGE_MODALITIES = {'SR', 'SEG', 'PR', 'KO', 'AU_AS', 'OT'}` 过滤非图像模态；新设计不过滤。

**对策**：在 docstring 与 PR 描述中明示——`file_count` 是"study 目录下文件数"，**不是**"image instance 数"。如果将来需要严格 instance 数，再调 register_folder 仅过滤计数。

## 验证清单

- [ ] alembic 升级：dev 库 `alembic upgrade head` 成功
- [ ] DDL：备份表行数 = 4（原 dicom_series 行数）
- [ ] 迁移后：新 dicom_series 行数 = 4（按 study_uid 去重）；byte_size 与原 4 行合计一致
- [ ] 视图：v_imaging_study_counts 返回 total_bytes 字段不变（仍为 89,180,336 for study 1）
- [ ] 单 study 跑 `_upsert_dicom_byte_size_for_study` 验证（用 /tmp/test_issue2_one_study.py 改版）
- [ ] 全量 zhujiang：预计 ~18 分钟（vs 原 3-6 hr）
- [ ] DICOM Viewer：移除 series_count 列后页面无错
- [ ] /medical/files/statistics 接口：返回 total_size_bytes 仍为正数

## 工作量估计

| 任务 | 行数 / 时长 |
|---|---|
| alembic 迁移 + DDL 改写 | ~50 行 / 1-2 hr |
| ORM 模型改写 | ~30 行 / 30 min |
| ETL 引擎重写 | ~80 行 / 1 hr |
| 视图重写 | ~20 行 / 15 min |
| 前端 DicomViewer 调整 | ~30 行 / 30 min |
| 移除 query_series_counts_by_modality | ~50 行 / 30 min |
| 测试 + 验证 | 1-2 hr |
| **合计** | **~6-8 hr** |

## 决策

| 选项 | 推荐度 | 备注 |
|---|---|---|
| 接受重构 | ⭐⭐⭐ | zhujiang 全量从 3-6 hr → ~18 min；代价是 DICOM Viewer 序列数消失 |
| 加 byte_size_only 快速路径 | ⭐⭐ | 保留 series_uid，加快速路径；改 dicom_series schema 不动（系列信息改走 register_folder）；复杂度高 |
| 不重构 | ⭐ | 接受 3-6 hr 全量；DICOM Viewer 保留序列数 |
| 暂停本会话 | — | 决策材料已交付；下会话决定 |

## 与 PRD/Issue 拆分的关系

| 原条目 | 影响 |
|---|---|
| `docs/etl2/prd/PRD.md` | 更新 §Implementation Decisions（"DICOM series 拆分" 改为 "study 级 byte_size"） |
| `issue-2-run-dicom-series-etl.md` | 改为 `issue-2-run-dicom-byte-size-etl.md`；范围扩展为 alembic 迁移 + 重构 |
| `issue-3-switch-files-statistics-to-view.md` | 不变（视图仍提供 total_bytes） |
| `issue-4-investigate-shengyi-exam-gap.md` | 不变（独立调研） |

## 决策材料位置

本文件：`docs/etl2/prd/refactor-impact-dicom-series-study-level.md`
上游决策材料：`local://plan_b_evidence.md`
原 PRD：`docs/etl2/prd/PRD.md`
相关 commit：`a9000c56`（脚本骨架，仍适用）

## 验证：本会话试跑结果（不变，重构后这些数字仍正确）

- Issue 1 zhujiang 全量回填：36,342 / 36,356 = 99.96%
- Issue 2 单 study 试跑：4 series_uid，total_bytes=89,180,336
- 重构后：`v_imaging_study_counts.total_bytes` 仍为 89,180,336（语义一致）