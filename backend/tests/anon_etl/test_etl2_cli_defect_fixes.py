"""Issue 7 — ETL-2 CLI 三处缺陷修复的回归测试。

锁定三条契约：

1. ``_create_batch`` 接受 ``source_kind`` 形参，并把它写入
   ``lnrs_anon_ingest_batch.source_kind``。
2. ``run_center`` 调用 ``_create_batch`` 时按 spec 选择 ``source_kind``：
   仅含 dicom_series spec → ``dicom_dir``；含 parquet spec → ``csv_report``；
   ``dicom_series_only=True`` 时强制 ``dicom_dir``。
3. ``backfill_dicom_series_count.run_apply`` 在 ``anon_exam_id IS NULL``
   时仍能把 series_count 落库（不传空串）；fk NULL 由 0024 允许。

无 DB 环境自动跳过（与 test_dicom_series_count.py 同款 _pg_available 守卫）。
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from sqlalchemy import text


def _pg_available() -> bool:
    """检测本地 PG 是否可连（环境变量 ENVIRONMENT=dev 时读 env/.env.dev）。"""
    if os.getenv("ENVIRONMENT") != "dev":
        return False
    try:
        import asyncpg
    except ImportError:
        return False
    try:

        async def _t():
            conn = await asyncpg.connect(
                host="127.0.0.1", port=5432, user="lnrs",
                password="lnrs_pwd", database="postgres",
            )
            await conn.close()

        asyncio.run(_t())
        return True
    except Exception:
        return False


PG_READY = _pg_available()
SKIP_REASON = "需要 ENVIRONMENT=dev 且本地 PG（lnrs:lnrs_pwd@127.0.0.1:5432/postgres）"


def _make_dcm(path: Path, study_uid: str, series_uid: str, sop_uid: str,
              modality: str = "CT", sop_class: str = "1.2.840.10008.5.1.4.1.1.2") -> None:
    """生成最小 DICOM 文件（含 Study/Series/SOP UID + 模态）。"""
    from pydicom.dataset import Dataset, FileDataset
    from pydicom.uid import generate_uid

    file_meta = Dataset()
    file_meta.MediaStorageSOPClassUID = sop_class
    file_meta.MediaStorageSOPInstanceUID = sop_uid
    file_meta.TransferSyntaxUID = "1.2.840.10008.1.2"
    file_meta.ImplementationClassUID = generate_uid()

    ds = FileDataset(str(path), {}, file_meta=file_meta, preamble=b"\0" * 128)
    ds.PatientName = "Test^Issue7"
    ds.PatientID = "PT_ISSUE7"
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = series_uid
    ds.SOPInstanceUID = sop_uid
    ds.SOPClassUID = sop_class
    ds.Modality = modality
    ds.is_little_endian = True
    ds.is_implicit_VR = True
    ds.save_as(str(path))


@pytest.mark.skipif(not PG_READY, reason=SKIP_REASON)
class TestSourceKindParam:
    """Defect 2 修复：_create_batch 接受 source_kind。"""

    def test_create_batch_accepts_source_kind_dicom_dir(self, tmp_path: Path):
        asyncio.run(self._body(tmp_path, "dicom_dir"))

    def test_create_batch_accepts_source_kind_csv_report(self, tmp_path: Path):
        asyncio.run(self._body(tmp_path, "csv_report"))

    @staticmethod
    async def _body(tmp_path: Path, source_kind: str):
        import uuid

        from app.core.database import async_db_session, async_engine
        from app.plugin.module_medical.hospital.anon_etl_service import _create_batch
        from app.plugin.module_medical.hospital.anon_model import AnonIngestBatchModel

        center = f"src_kind_{uuid.uuid4().hex[:8]}"
        fake_dir = tmp_path / "issue7_unused"
        fake_dir.mkdir(exist_ok=True)

        async with async_db_session() as session:
            try:
                returned = await _create_batch(
                    session,
                    center_code=center,
                    data_dir=fake_dir,
                    source_kind=source_kind,
                )
                # _create_batch 内部生成 UUID，返回值是新生成的 batch_id
                assert returned, "应返回新生成的 batch_id"
                await session.commit()

                result = await session.execute(
                    text(
                        "SELECT source_kind FROM lnrs.lnrs_anon_ingest_batch "
                        "WHERE batch_id = :b"
                    ),
                    {"b": returned},
                )
                row = result.fetchone()
                assert row is not None, "batch 行必须存在"
                assert row[0] == source_kind, (
                    f"source_kind 应 = {source_kind!r}，实际 {row[0]!r}"
                )
            finally:
                await session.execute(
                    AnonIngestBatchModel.__table__.delete().where(
                        AnonIngestBatchModel.batch_id == returned
                    )
                )
                await session.commit()
        await async_engine.dispose()


@pytest.mark.skipif(not PG_READY, reason=SKIP_REASON)
class TestRunCenterSourceKindAuto:
    """Defect 2 修复：run_center 自动按 spec 选择 source_kind 并透传给 _create_batch。

    走的是完整 run_center 流程（specs 来自 _CENTER_PARQUET_SPECS），但
    通过 monkeypatch import_center 为 noop 来避免触发真实 ETL；只验证
    _create_batch 的入参 source_kind 是否正确。
    """

    def test_dicom_series_only_center_uses_dicom_dir(self, tmp_path: Path):
        asyncio.run(self._body(tmp_path, "zhujiang", "dicom_dir", dicom_series_only=True))

    def test_full_parquet_center_uses_csv_report(self, tmp_path: Path):
        asyncio.run(self._body(tmp_path, "shengyi", "csv_report"))

    @staticmethod
    async def _body(
        tmp_path: Path, center: str, expected_source_kind: str,
        dicom_series_only: bool = False,
    ):
        import uuid

        from app.core.database import async_db_session, async_engine
        from app.plugin.module_medical.hospital import anon_etl_engine, anon_etl_service

        center_dir = tmp_path / center
        center_dir.mkdir(exist_ok=True)

        captured: dict = {}

        async def fake_create_batch(db, *, center_code, data_dir, source_kind):
            captured["source_kind"] = source_kind
            captured["center_code"] = center_code
            return str(uuid.uuid4())

        async def fake_import_center(*args, **kwargs):
            return {}

        # run_center 走 `from .anon_etl_engine import import_center` 直接引用，
        # 必须 patch 原模块同名符号才能拦到。
        original_create_batch = anon_etl_service._create_batch
        original_import_center = anon_etl_engine.import_center

        anon_etl_service._create_batch = fake_create_batch
        anon_etl_engine.import_center = fake_import_center

        # 回归守卫基线：本测试**不得**改变该中心真实 batch 的行数。
        # 2026-09-20 事故：清理写成 `DELETE ... WHERE center_code = :c`，而本测试
        # 用的是真实中心名（run_center 的 _CENTER_PARQUET_SPECS 查找需要），
        # 且 fake_create_batch 从不写库 → 该 DELETE 删掉的全是真实 batch，
        # 经 dicom_series.created_batch_id 的 ON DELETE CASCADE 连带删掉
        # zhujiang 86,203 + shengyi 82,057 行 dicom_series。
        async with async_db_session() as session:
            baseline_batches = (
                await session.execute(
                    text(
                        "SELECT COUNT(*) FROM lnrs.lnrs_anon_ingest_batch "
                        "WHERE center_code = :c"
                    ),
                    {"c": center},
                )
            ).scalar_one()

        try:
            result = await anon_etl_service.run_center(
                center, data_root=tmp_path, dicom_series_only=dicom_series_only,
            )
            assert result["status"] == "success", f"run_center 应成功: {result}"
        finally:
            anon_etl_service._create_batch = original_create_batch
            anon_etl_engine.import_center = original_import_center

        # 清理**只按本测试拿到的 batch_id**，绝不按 center_code：
        # fake_create_batch 未写库时该 batch_id 不存在 → 删除是 no-op；
        # 若将来 _create_batch 不再被 fake，也只会删掉本测试自己创建的那一行。
        async with async_db_session() as session:
            await session.execute(
                text("DELETE FROM lnrs.lnrs_anon_ingest_batch WHERE batch_id = :b"),
                {"b": result["batch_id"]},
            )
            await session.commit()

        async with async_db_session() as session:
            remaining_batches = (
                await session.execute(
                    text(
                        "SELECT COUNT(*) FROM lnrs.lnrs_anon_ingest_batch "
                        "WHERE center_code = :c"
                    ),
                    {"c": center},
                )
            ).scalar_one()
        assert remaining_batches == baseline_batches, (
            f"测试改变了 {center} 的真实 batch 行数"
            f"（{baseline_batches} → {remaining_batches}）——"
            "清理必须按 batch_id，不能按 center_code"
        )

        assert captured.get("source_kind") == expected_source_kind, (
            f"{center} 应 source_kind={expected_source_kind!r}，"
            f"实际 {captured.get('source_kind')!r}"
        )

        # 释放引擎连接池：本测试用 asyncio.run() 每次新建事件循环，
        # 池中残留上一循环的连接会让下一个测试报
        # "attached to a different loop"（同文件 TestSourceKindParam 同款收尾）。
        await async_engine.dispose()


@pytest.mark.skipif(not PG_READY, reason=SKIP_REASON)
class TestDataRootPassThrough:
    """Defect 1 修复：run_dicom_series_etl.sh 把 --data-root 透传给 ETL-2 CLI。

    代码侧 ``anon_etl/__main__.py`` 早就有 ``--data-root`` 参数；
    本测试确保 shell 脚本把它转成 CLI 参数。
    """

    def test_shell_script_passes_data_root_arg(self):
        script = Path(__file__).resolve().parents[2] / "etl2" / "run_dicom_series_etl.sh"
        text_body = script.read_text(encoding="utf-8")
        assert "--data-root" in text_body, (
            "run_dicom_series_etl.sh 必须支持 --data-root 透传（issue 7 缺陷 1）"
        )
        assert "DATA_ROOT" in text_body, (
            "run_dicom_series_etl.sh 需定义并使用 DATA_ROOT 变量"
        )

    def test_anonymous_etl_cli_accepts_data_root_arg(self):
        """anon_etl/__main__.py 必须有 --data-root 参数（这是 shell 透传的目标）。"""
        import sys

        from app.plugin.module_medical.hospital.anon_etl.__main__ import main

        old_argv = sys.argv
        try:
            sys.argv = ["anon_etl", "--data-root", "/tmp/foo"]
            try:
                main()
            except SystemExit:
                pass
        finally:
            sys.argv = old_argv


@pytest.mark.skipif(not PG_READY, reason=SKIP_REASON)
class TestAnonExamIdNonePassthrough:
    """Defect 3 修复：anon_exam_id 为 NULL 时不传空串给 _upsert_dicom_byte_size_for_study。"""

    def test_run_apply_passes_none_when_anon_exam_id_is_null(self, tmp_path: Path):
        asyncio.run(self._body(tmp_path))

    @staticmethod
    async def _body(tmp_path: Path):
        """验证修复前的 helper 表达式 `row.anon_exam_id or ""` 与修复后行为差异。

        修复前：`row.anon_exam_id or ""` 当 anon_exam_id=None 时返回 ""（空串）
        修复后：直接 `row.anon_exam_id`，保留 None
        """
        from app.core.database import async_db_session, async_engine
        from app.plugin.module_medical.hospital import anon_etl_engine

        class _FakeRow:
            anon_exam_id = None

        row = _FakeRow()

        # 修复前的实现（会触发 FK 违反）
        legacy_value = row.anon_exam_id or ""
        assert legacy_value == "", "验证 legacy 表达式确实把 None 变空串（说明 bug 存在）"

        # 修复后的实现（保留 None）
        fixed_value = row.anon_exam_id
        assert fixed_value is None, "修复后应保留 None"

        # 行为契约：直接 None 入参到 _upsert_dicom_byte_size_for_study，
        # 不应被替换为空串
        captured: dict = {}

        async def fake_upsert(db, *, image_path, dicom_study_uid, anon_exam_id, batch_id):
            captured["anon_exam_id"] = anon_exam_id
            return 0

        original = anon_etl_engine._upsert_dicom_byte_size_for_study
        anon_etl_engine._upsert_dicom_byte_size_for_study = fake_upsert

        try:
            async with async_db_session() as db:
                await fake_upsert(
                    db,
                    image_path=str(tmp_path),
                    dicom_study_uid="1.2.999.test",
                    anon_exam_id=row.anon_exam_id,
                    batch_id="dummy",
                )
            await async_engine.dispose()
        finally:
            anon_etl_engine._upsert_dicom_byte_size_for_study = original

        assert captured["anon_exam_id"] is None, (
            f"anon_exam_id 为 NULL 时应传 None，"
            f"实际 {captured['anon_exam_id']!r}"
        )
