"""lnrs_anon_dicom_series.series_count 实测回归测试（2026-09-17）。

锁定两条契约：
1. ETL _upsert_dicom_byte_size_for_study 调 register_folder 后正确写入 series_count
   （按 SeriesInstanceUID 去重计数，跳过非图像模态）。
2. anon_list_patient_imaging_studies API 返回 series_count 真值（COALESCE 0 兜底）。

无 DB 环境自动跳过（_pg_available 检测，参照 test_anon_patient_placeholder.py）。

测试策略：复用 dev 已有 exam 行（已存在合法 anon_exam_id），本测试只 INSERT batch
+ 写 dicom_series（依赖 anon_exam_id FK + batch_id FK），不动 patient/exam，避免
FK 链复杂度与 placeholder 行为冲突。完成后 DELETE 本测试引入的行。
"""
from __future__ import annotations

import asyncio
import hashlib
import os
from datetime import datetime
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
              modality: str = "CT", sop_class: str = "1.2.840.10008.5.1.4.1.1.2"):
    """生成最小 DICOM 文件（含 Study/Series/SOP UID + 模态 + 必要的文件元）。"""
    from pydicom.dataset import Dataset, FileDataset
    from pydicom.uid import generate_uid

    file_meta = Dataset()
    file_meta.MediaStorageSOPClassUID = sop_class
    file_meta.MediaStorageSOPInstanceUID = sop_uid
    file_meta.TransferSyntaxUID = "1.2.840.10008.1.2"  # Implicit VR Little Endian
    file_meta.ImplementationClassUID = generate_uid()

    ds = FileDataset(str(path), {}, file_meta=file_meta, preamble=b"\0" * 128)
    ds.PatientName = "Test^DicomSeriesCount"
    ds.PatientID = "PT_TEST"
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = series_uid
    ds.SOPInstanceUID = sop_uid
    ds.SOPClassUID = sop_class
    ds.Modality = modality
    ds.is_little_endian = True
    ds.is_implicit_VR = True
    ds.save_as(str(path))


async def _seed_batch(session, batch_id: str, center: str) -> None:
    """准备 ingest_batch（dicom_series.created_batch_id FK）。"""
    await session.execute(
        text(
            "INSERT INTO lnrs.lnrs_anon_ingest_batch "
            "(batch_id, center_code, source_kind, source_locator, "
            " secret_version, key_fingerprint, schema_hash, row_counts, "
            " started_at, status) "
            "VALUES (:b, :c, 'csv_report', 'unit_test', 'v1', '0', '0', "
            " '{}'::jsonb, :sa, 'success')"
        ),
        {"b": batch_id, "c": center, "sa": datetime.utcnow()},
    )


async def _pick_exam(session) -> tuple[str, str] | None:
    """从 dev 已存在的 exam 表取一行 (anon_exam_id, center_code)。
    返回 None 时调用方 pytest.skip。
    """
    result = await session.execute(
        text(
            "SELECT anon_exam_id, center_code "
            "FROM lnrs.lnrs_anon_exam "
            "LIMIT 1"
        )
    )
    return result.fetchone()


async def _cleanup(session, *, study_uid: str | None, batch_id: str) -> None:
    """清理：删 dicom_series（按 study_uid）+ 删 batch（按 batch_id）。"""
    if study_uid:
        await session.execute(
            text("DELETE FROM lnrs.lnrs_anon_dicom_series WHERE dicom_study_uid = :u"),
            {"u": study_uid},
        )
    await session.execute(
        text("DELETE FROM lnrs.lnrs_anon_ingest_batch WHERE batch_id = :b"),
        {"b": batch_id},
    )


@pytest.mark.skipif(not PG_READY, reason=SKIP_REASON)
class TestSeriesCountUpsert:
    """ETL 落库带 series_count：2 series × 3 instance 的 fixture。"""

    def test_upsert_writes_series_count_for_two_series(self, tmp_path: Path):
        asyncio.run(self._body(tmp_path))

    @staticmethod
    async def _body(tmp_path: Path):
        import uuid

        from app.core.database import async_db_session, async_engine
        from app.plugin.module_medical.hospital import anon_etl_engine
        from app.plugin.module_medical.dicom.repository import indexer

        center = f"sc_test_{uuid.uuid4().hex[:8]}"
        batch_id = str(uuid.uuid4())
        study_uid = f"1.2.999.{uuid.uuid4().int}"
        series_a = f"1.2.999.seriesA.{uuid.uuid4().int}"
        series_b = f"1.2.999.seriesB.{uuid.uuid4().int}"

        # 造 2 series × 3 instance = 6 个 DICOM 文件
        for s_uid in (series_a, series_b):
            for i in range(3):
                _make_dcm(
                    tmp_path / f"{s_uid}__{i}.dcm",
                    study_uid=study_uid,
                    series_uid=s_uid,
                    sop_uid=f"{s_uid}.{i}",
                )
        # 加一个 SR 文件：应被 register_folder 跳过（_NON_IMAGE_MODALITIES 含 SR）
        sr_uid = f"1.2.999.sr.{uuid.uuid4().int}"
        _make_dcm(
            tmp_path / f"{sr_uid}.dcm",
            study_uid=study_uid,
            series_uid=sr_uid,
            sop_uid=f"{sr_uid}.0",
            modality="SR",
            sop_class="1.2.840.10008.5.1.4.1.1.88.11",  # Basic Text SR
        )

        try:
            async with async_db_session() as session:
                # 取一个已有 exam 行复用其 anon_exam_id（FK 约束要求 NOT NULL）
                exam_row = await _pick_exam(session)
                if exam_row is None:
                    pytest.skip("dev 环境无 exam 行，无法前置 dicom_series.anon_exam_id FK")
                anon_exam_id, _ = exam_row

                await _seed_batch(session, batch_id, center)
                await session.commit()

                # 调 ETL upsert
                n = await anon_etl_engine._upsert_dicom_byte_size_for_study(
                    session,
                    image_path=str(tmp_path),
                    dicom_study_uid=study_uid,
                    anon_exam_id=anon_exam_id,
                    batch_id=batch_id,
                )
                await session.commit()
                assert n > 0, f"byte_size 应 > 0，实际 {n}"

                # 读回 dicom_series 行
                result = await session.execute(
                    text(
                        "SELECT file_count, byte_size, series_count "
                        "FROM lnrs.lnrs_anon_dicom_series "
                        "WHERE dicom_study_uid = :u"
                    ),
                    {"u": study_uid},
                )
                row = result.fetchone()
                assert row is not None, "dicom_series 行必须被创建"
                file_count, byte_size, series_count = row

                # 断言 1：file_count = 7（2 series × 3 + 1 SR）
                assert file_count == 7, f"file_count 应 = 7，实际 {file_count}"

                # 断言 2：series_count = 2（按 SeriesInstanceUID 去重；SR 跳过模态）
                assert series_count == 2, (
                    f"series_count 应 = 2（series_a + series_b，SR 跳过），"
                    f"实际 {series_count}"
                )

                # 断言 3：byte_size > 0（6 + 1 个 dcm 文件）
                assert byte_size > 0

                # 断言 4：indexer LRU 已清（不留 study_uid 状态）
                assert study_uid not in indexer._studies

            # 重跑验证幂等 + 同字段不变
            async with async_db_session() as session:
                n2 = await anon_etl_engine._upsert_dicom_byte_size_for_study(
                    session,
                    image_path=str(tmp_path),
                    dicom_study_uid=study_uid,
                    anon_exam_id=anon_exam_id,
                    batch_id=batch_id,
                )
                await session.commit()
                assert n2 == n

                result2 = await session.execute(
                    text(
                        "SELECT file_count, series_count "
                        "FROM lnrs.lnrs_anon_dicom_series "
                        "WHERE dicom_study_uid = :u"
                    ),
                    {"u": study_uid},
                )
                row2 = result2.fetchone()
                assert row2[0] == file_count
                assert row2[1] == series_count
        finally:
            # 清理（显式删除，不依赖回滚）
            async with async_db_session() as session:
                await _cleanup(
                    session,
                    study_uid=study_uid,
                    batch_id=batch_id,
                )
                await session.commit()
            await async_engine.dispose()


@pytest.mark.skipif(not PG_READY, reason=SKIP_REASON)
class TestSeriesCountEmptyDir:
    """空目录 / 离线目录的兜底行为。"""

    def test_empty_dir_returns_zero(self, tmp_path: Path):
        """空目录：函数路径里 files=[]，早 return；不写 dicom_series。"""
        asyncio.run(self._body(tmp_path))

    @staticmethod
    async def _body(tmp_path: Path):
        import uuid

        from app.core.database import async_db_session, async_engine
        from app.plugin.module_medical.hospital import anon_etl_engine

        # 在 tmp_path 下建一个空子目录
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        center = f"sc_empty_{uuid.uuid4().hex[:8]}"
        batch_id = str(uuid.uuid4())
        study_uid = f"1.2.999.empty.{uuid.uuid4().int}"

        async with async_db_session() as session:
            exam_row = await _pick_exam(session)
            if exam_row is None:
                pytest.skip("dev 环境无 exam 行")
            anon_exam_id, _ = exam_row

            await _seed_batch(session, batch_id, center)
            await session.commit()

            try:
                # 空目录：早 return 0，不写 dicom_series
                n = await anon_etl_engine._upsert_dicom_byte_size_for_study(
                    session,
                    image_path=str(empty_dir),
                    dicom_study_uid=study_uid,
                    anon_exam_id=anon_exam_id,
                    batch_id=batch_id,
                )
                await session.commit()
                assert n == 0, "空目录应早 return 0"

                result = await session.execute(
                    text(
                        "SELECT count(*) FROM lnrs.lnrs_anon_dicom_series "
                        "WHERE dicom_study_uid = :u"
                    ),
                    {"u": study_uid},
                )
                row = result.scalar()
                assert row == 0, "空目录不应写 dicom_series"
            finally:
                await _cleanup(
                    session,
                    study_uid=None,  # 空目录未创建 dicom_series 行
                    batch_id=batch_id,
                )
                await session.commit()
        await async_engine.dispose()


@pytest.mark.skipif(not PG_READY, reason=SKIP_REASON)
class TestAPIImagingStudiesSeriesCount:
    """GET /patients/{id}/imaging-studies series_count 返回真值（COALESCE 0）。"""

    def test_api_returns_series_count_for_known_study(self):
        asyncio.run(self._body())

    @staticmethod
    async def _body():
        # 仅验证 API 层 SQL 渲染：调 anon_list_patient_imaging_studies，
        # 断言返回项含 series_count 字段且为非负整数。
        from app.core.database import async_db_session, async_engine
        from app.plugin.module_medical.hospital.anon_medical_query import (
            anon_list_patient_imaging_studies,
        )

        async with async_db_session() as session:
            result = await session.execute(
                text(
                    "SELECT DISTINCT s.patient_id "
                    "FROM lnrs.lnrs_anon_imaging_study s "
                    "WHERE s.patient_id IS NOT NULL "
                    "LIMIT 1"
                )
            )
            row = result.fetchone()
            if row is None:
                pytest.skip("dev 环境无 imaging_study 行")

            items = await anon_list_patient_imaging_studies(
                session, patient_id=row[0], center="shengyi"
            )
            assert isinstance(items, list)
            assert len(items) > 0, "API 至少应返回一项"
            for it in items:
                assert "series_count" in it, f"每项必须有 series_count: {it}"
                assert isinstance(it["series_count"], int)
                assert it["series_count"] >= 0
                # file_count / byte_size 一并存在
                assert "file_count" in it
                assert "byte_size" in it

        await async_engine.dispose()