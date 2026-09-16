"""重构 lnrs_anon_dicom_series 为 study 级 byte_size（DDL 文档归档）

⚠️ 本迁移文件 2026-09-15 状态：仅作为 DDL 文档归档，**不通过 alembic 推动**。

原因：
- h196_3 / dev 库从未跑过 alembic（alembic_version 表不存在）
- 现有 lnrs schema 表是 SQL 脚本（backend/sql/postgres/*.sql）创建的，72 张表
  不在 alembic 版本控制下
- 若 alembic upgrade head 跑本迁移，会触发 base → j0k1l2m3n4o5 全部 12 个
  历史迁移重新执行，每个 CREATE 已存在的对象必失败

实际应用：本迁移对应 DDL 已于 2026-09-15 在 h196_3 库手工执行（用 postgres
superuser；详见 docs/etl2/prd/refactor-impact-dicom-series-study-level.md
的 Step 1a）。SQL 内容一致：DROP VIEW → 备份老表 → DROP TABLE CASCADE →
CREATE 新表（study 级）→ 数据迁移（按 study_uid 去重聚合）→ 重置序列 →
重建视图（study 级 LEFT JOIN）。

未来 dev 库 init 时按 backend/sql/postgres/0006-anonymized-schema-lnrs.sql §7
（已同步改写为 study 级）+ §8（FK 已移除）执行；0020 视图按
backend/sql/postgres/0020-imaging-study-counts-view.sql（同步改写为 study 级
LEFT JOIN）执行。

---

背景

原 dicom_series 表是 series 级（一行 = 一个 DICOM SeriesInstanceUID），ETL-2 阶段
通过 DicomIndexer.register_folder + pydicom.dcmread 解析每个 .dcm header 拿
series_uid/modality/instance_count/file_root/series_no，再累加 byte_size。

zhujiang 全量落库测算：~30 instance × ~10ms pydicom = 300ms / study；36,342 study
× 300ms = ~3 小时磁盘 I/O + CPU bound。

重构后：dicom_series 表改为 study 级（一行 = 一个 study），仅保留 study_uid +
file_count + byte_size + anon_exam_id + batch 字段。ETL 阶段仅 iterdir + stat，
不再调 register_folder、不再调 pydicom、不再保留 series_uid/modality/body_part。
zhujiang 全量预计 ~18 分钟（10x 加速）。

设计决策（详见 docs/etl2/prd/refactor-impact-dicom-series-study-level.md）：

- dicom_series.dicom_series_uid 字段删除：原来 UNIQUE 键改为 dicom_study_uid UNIQUE
- dicom_series.modality / body_part / series_no / file_root / file_count_actual
  字段删除：DICOMweb 实时接口仍走 DicomIndexer（路径不变）
- instance_count 改名 file_count：原 register_folder 过滤非图像模态（SR/SEG/PR/...），
  新设计不过滤；file_count = study 目录下文件数，可能略大于真实 image instance 数
- v_imaging_study_counts 视图重写：series_count → 0（不再有意义），
  instance_count → file_count，total_bytes → byte_size（语义保持）

数据迁移

原 4 行（commit f8dd292e 手工验证）按 dicom_study_uid 去重：

- 4 行同属 1 个 study (dicom_study_uid=1.2.840.113704.1.111.10996.1483237195.1)
- byte_size 累加：89,180,336（保持）
- file_count：当时 register_folder 解析的 4 个 series 各自 instance_count 之和
  = 3 + 55 + 266 + 1 = 325（即原 instance_count）

视图重写

.. code-block:: sql

    DROP VIEW lnrs.lnrs_anon_v_imaging_study_counts;
    CREATE VIEW lnrs.lnrs_anon_v_imaging_study_counts AS
    SELECT ims.study_key, ims.dicom_study_uid, ims.center_code, ims.patient_id,
           ims.anon_exam_id,
           0::INT                              AS series_count,
           COALESCE(s.file_count, 0)::INT     AS instance_count,
           COALESCE(s.byte_size, 0)::BIGINT   AS total_bytes
    FROM lnrs_anon_imaging_study ims
    LEFT JOIN lnrs_anon_dicom_series s ON s.dicom_study_uid = ims.dicom_study_uid;

验证：dev (h196_3) lnrs_anon_imaging_study 119,350 行；现有 dicom_series 4 行；
迁移后 dicom_series 1 行（按 study_uid 去重）；视图 v_imaging_study_counts
series_count=0/instance_count=325/total_bytes=89,180,336（语义保持）。

---

由于本文件不通过 alembic 推动，upgrade() / downgrade() 函数留空实现，
仅保留 revision 元数据以供 alembic heads 报告完整性。
"""

from collections.abc import Sequence

from alembic import op

revision: str = "j0k1l2m3n4o5"
down_revision: str | None = "i9j0k1l2m3n4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """DDL 已于 2026-09-15 在 h196_3 手工执行，本文件仅为归档。

    详见模块 docstring 与 docs/etl2/prd/refactor-impact-dicom-series-study-level.md。
    """
    # noop: DDL not driven by alembic on h196_3


def downgrade() -> None:
    """DDL 回退路径见 docs/etl2/prd/refactor-impact-dicom-series-study-level.md。

    本文件不通过 alembic 推动，downgrade() 留空实现。
    若需回退，请参考决策文档 Step 1a 的反向 SQL（含 lnrs._migration_old_dicom_series
    临时备份表数据还原）。
    """
    # noop: DDL not driven by alembic on h196_3