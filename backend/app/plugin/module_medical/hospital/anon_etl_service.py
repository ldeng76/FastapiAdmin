"""ETL-2 编排服务 — 遍历多中心 parquet → 脱敏 → 入库。

职责：
1. 为每个中心创建一个 lnrs_anon_ingest_batch 行（记录密钥指纹/schema 哈希/行数）
2. 调 anon_etl_engine.import_center 完成实际导入
3. 成功 → 关 batch (status=success + row_counts)；失败 → 关 batch (status=failed + error)

事务模型：
- 每中心一个独立事务（async_db_session）—— 一中心失败不影响其他中心
- ingest_batch 在同事务内创建并关闭，确保原子性

CLI 入口见 anon_etl/__main__.py。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.setting import settings
from app.core.database import async_db_session
from app.core.logger import log

from .anon_etl_engine import import_center
from .anon_model import AnonIngestBatchModel
from .anonymize import key_fingerprint, schema_hash, secret_version

# 已知的中心清单（与 data/ 子目录、etl1/centers/ 注册保持一致）
KNOWN_CENTERS = ("shengyi", "xinqiao", "zhujiang")


def _read_source_sha256(data_dir: Path) -> str | None:
    """从 _meta/conversion_manifest.json 读 source_sha256（ETL-1 已写入）。"""
    manifest = data_dir / "_meta" / "conversion_manifest.json"
    if not manifest.exists():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        return data.get("source_sha256") or data.get("sha256")
    except (json.JSONDecodeError, OSError) as e:
        log.warning(f"读取 manifest 失败: {manifest}: {e}")
        return None


async def _create_batch(
    db: AsyncSession,
    *,
    center_code: str,
    data_dir: Path,
    source_kind: str = "csv_report",
) -> str:
    """创建一个 running 状态的 ingest_batch，返回 batch_id。

    source_kind（Issue 7 修复）：
    - ``"csv_report"``：ETL-1 产出 parquet（默认；与历史行为一致）
    - ``"dicom_dir"``：磁盘 DICOM 目录（如 dicom_series spec 单独跑）
    - ``"dicom_zip"``：DICOM zip 压缩包（预留）
    由 ``run_center`` 根据 spec 自动决定，调用方一般无需显式传入。
    """
    batch_id = str(uuid.uuid4())
    source_sha256 = _read_source_sha256(data_dir)
    await db.execute(
        AnonIngestBatchModel.__table__.insert().values(
            batch_id=batch_id,
            center_code=center_code,
            source_kind=source_kind,
            source_locator=str(data_dir),
            source_sha256=source_sha256,
            secret_version=secret_version(),
            key_fingerprint=key_fingerprint(),
            schema_hash=schema_hash(),
            row_counts={},
            started_at=datetime.utcnow(),
            finished_at=None,
            status="running",
            error=None,
        )
    )
    return batch_id


async def _close_batch(
    db: AsyncSession,
    *,
    batch_id: str,
    status: str,
    row_counts: dict[str, int],
    error: str | None = None,
) -> None:
    """关闭 batch（写 finished_at/status/error/row_counts）。"""
    await db.execute(
        AnonIngestBatchModel.__table__.update()
        .where(AnonIngestBatchModel.batch_id == batch_id)
        .values(
            finished_at=datetime.utcnow(),
            status=status,
            error=(error[:2000] if error else None),
            row_counts=row_counts,
        )
    )


async def run_center(
    center_code: str,
    data_root: Path | None = None,
    dicom_series_only: bool = False,
) -> dict[str, Any]:
    """运行单中心的 ETL-2，返回汇总。

    data_root: ETL-1 产出物根目录，默认 settings.LNRS_DATA_ROOT
    dicom_series_only: True 时仅跑 dicom_series spec（Issue 7 修复）；
        同时 batch.source_kind 标记为 'dicom_dir'。适用于
        run_dicom_series_etl.sh 包装的 dicom_series 灌库。
    返回: {"center": str, "status": "success"|"failed", "rows": {...}, "batch_id": str}

    source_kind 自动推导（Issue 7 修复 Defect 2）：
    - 仅 dicom_series spec → "dicom_dir"（磁盘 DICOM 目录扫描）
    - 含 parquet spec → "csv_report"（ETL-1 产出 parquet）
    与 shengyi / xinqiao / zhujiang 三中心的实际用法一致：
    - shengyi 全量 spec 含 patient/exam_text/... → csv_report
    - 单独跑 dicom_series spec → dicom_dir
    """
    # 延迟导入：避免循环（anon_etl_engine 反向引用本模块的场景）
    from .anon_etl_engine import _CENTER_PARQUET_SPECS

    root = Path(data_root) if data_root else Path(settings.LNRS_DATA_ROOT)
    root = root.resolve()
    data_dir = root / center_code

    if not data_dir.exists():
        msg = f"中心数据目录不存在: {data_dir}"
        log.error(f"ETL2: {msg}")
        return {"center": center_code, "status": "failed", "error": msg, "rows": {}}

    log.info(
        f"ETL2: 开始处理中心 {center_code} (data_dir={data_dir}) "
        f"dicom_series_only={dicom_series_only}"
    )

    # source_kind 推导（Issue 7 修复 Defect 2）：
    # - dicom_series_only=True → 强制 "dicom_dir"
    # - 否则：spec 列表只含 dicom_series → "dicom_dir"；
    #         含 parquet spec → "csv_report"
    if dicom_series_only:
        source_kind = "dicom_dir"
    else:
        specs = _CENTER_PARQUET_SPECS.get(center_code, [])
        only_dicom = bool(specs) and all(s.get("kind") == "dicom_series" for s in specs)
        source_kind = "dicom_dir" if only_dicom else "csv_report"

    # 1. 用独立事务创建 batch 行并提交——确保即使导入失败回滚，batch 记录仍保留，
    #    便于回溯"哪次尝试用了什么密钥/schema"。失败时后续 _close_batch 才能 UPDATE 到。
    async with async_db_session() as batch_session:
        batch_id = await _create_batch(
            batch_session,
            center_code=center_code,
            data_dir=data_dir,
            source_kind=source_kind,
        )
        await batch_session.commit()
    log.info(
        f"ETL2: 创建 batch {batch_id} center={center_code} source_kind={source_kind}"
    )

    # 2. 导入数据（独立事务，失败不影响 batch 记录）
    try:
        async with async_db_session() as session:
            result = await import_center(
                db=session,
                center_code=center_code,
                data_dir=data_dir,
                batch_id=batch_id,
                dicom_series_only=dicom_series_only,
            )
            await session.commit()
        log.info(f"ETL2: 中心 {center_code} 完成: {result}")
        return {
            "center": center_code,
            "status": "success",
            "rows": result,
            "batch_id": batch_id,
        }
    except Exception as e:
        # 导入失败：数据事务已由 async with 自动回滚；
        # batch 记录因已单独提交而保留，这里用独立事务置 failed。
        error_msg = f"{type(e).__name__}: {e!s}"
        log.error(f"ETL2: 中心 {center_code} 失败: {error_msg}")
        try:
            async with async_db_session() as close_session:
                await _close_batch(
                    close_session,
                    batch_id=batch_id,
                    status="failed",
                    row_counts={},
                    error=error_msg,
                )
                await close_session.commit()
        except Exception as inner_e:
            log.error(f"ETL2: 关 batch 失败: {inner_e!s}")
        return {
            "center": center_code,
            "status": "failed",
            "error": error_msg,
            "rows": {},
            "batch_id": batch_id,
        }


async def run_anon_etl(
    centers: list[str] | None = None,
    data_root: Path | None = None,
    dicom_series_only: bool = False,
) -> list[dict[str, Any]]:
    """运行多中心 ETL-2。一中心失败不影响其他。

    centers: None 则处理全部 KNOWN_CENTERS
    dicom_series_only: True 时仅跑 dicom_series spec（Issue 7 修复）；
        同时 batch.source_kind 标记为 'dicom_dir'。
    返回: 每中心的汇总 dict 列表
    """
    todo = centers or list(KNOWN_CENTERS)
    unknown = [c for c in todo if c not in KNOWN_CENTERS]
    if unknown:
        log.warning(f"ETL2: 未知中心 {unknown}（已知: {KNOWN_CENTERS}），仍尝试处理")

    results = []
    for center in todo:
        r = await run_center(center, data_root=data_root, dicom_series_only=dicom_series_only)
        results.append(r)
    return results
