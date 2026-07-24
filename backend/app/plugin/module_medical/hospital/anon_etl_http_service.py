"""anon ETL HTTP 服务 — 异步后台执行 + Redis 进度跟踪 + 状态机推进。

仿 EtlService（etl_service.py）模式，但落库到 lnrs_anon_* 表（不经 med_* 中间层）。

触发流程（trigger_import_service）：
1. 校验 hospital + 中心列表（KNOWN_CENTERS）
2. 校验 data_dir 存在（来自 hospital.data_dir 或请求参数）
3. 生成 job_id，asyncio.create_task 启动后台协程
4. 立即返回 job_id

后台协程（_run_anon_etl_background）：
1. 独立 DB 会话（async_db_session，非请求会话）
2. Redis 写 running 状态
3. 调 anon_etl_service.run_anon_etl(centers=center_codes)
4. 成功 → 更新医院 lifecycle_status=DATA_IMPORTED + last_import_time/rows
5. 失败 → Redis 写 error + 医院写 import_error

与 EtlService 的区别：
- 不依赖 med_mapping_rule（anon 链路用 _CENTER_PARQUET_SPECS 硬编码）
- 不依赖 tenant_id 过滤（anon 表无 tenant_id 列）
- data_dir 可来自 hospital.data_dir 或请求覆盖
- 中心列表是请求参数，不由 hospital 推导（hospital↔center 映射暂不实现）
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from redis.asyncio.client import Redis
from sqlalchemy import update

from app.api.v1.module_system.auth.schema import AuthSchema
from app.config.setting import settings
from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.logger import log
from app.core.redis_crud import RedisCURD
from app.utils.common_util import uuid4_str

from .anon_etl_service import KNOWN_CENTERS, run_anon_etl
from .model import HospitalModel, HospitalStatus

# anon ETL 状态 Redis key 前缀（与旧 ETL 区分）
ANON_ETL_STATUS_KEY_PREFIX = "anon_etl:status"
ANON_ETL_STATUS_TTL = 3600  # 1 小时

# 允许触发 anon 导入的状态（与旧 ETL 一致）
IMPORTABLE_STATUSES = {
    HospitalStatus.MAPPING_CONFIGURED.value,
    HospitalStatus.DATA_IMPORTED.value,
}


class AnonEtlService:
    """anon ETL 导入服务（落库到 lnrs_anon_* 表）"""

    @classmethod
    async def trigger_import_service(
        cls,
        auth: AuthSchema,
        hospital_id: int,
        redis: Redis,
        center_codes: list[str] | None = None,
        data_dir_override: str | None = None,
    ) -> dict[str, str]:
        """触发 anon ETL 导入（异步后台执行）。

        Args:
            auth: 请求认证上下文（含 db 会话）。
            hospital_id: 触发医院 ID（用于 lifecycle_status 推进和 Redis key）。
            redis: Redis 连接（请求内）。
            center_codes: 要导入的中心列表；None=处理全部 KNOWN_CENTERS。
                必须在 KNOWN_CENTERS 内。
            data_dir_override: 覆盖 hospital.data_dir（用于临时指定 parquet 路径）。

        Returns:
            {"job_id": "...", "status": "pending"}
        """
        # 1. 校验医院
        hospital = await auth.db.get(HospitalModel, hospital_id)
        if not hospital:
            raise CustomException(msg="医院不存在", code=404, status_code=404)

        if hospital.lifecycle_status not in IMPORTABLE_STATUSES:
            raise CustomException(
                msg=f"当前状态[{hospital.lifecycle_status}]不允许导入，需先配置映射",
                code=400,
                status_code=400,
            )

        # 2. 决定中心列表
        todo_centers = center_codes or list(KNOWN_CENTERS)
        unknown = [c for c in todo_centers if c not in KNOWN_CENTERS]
        if unknown:
            raise CustomException(
                msg=f"未知中心 {unknown}（已知: {KNOWN_CENTERS}）",
                code=400,
                status_code=400,
            )

        # 3. 决定 data_dir
        if data_dir_override:
            data_dir = Path(data_dir_override)
        elif hospital.data_dir:
            data_dir = Path(hospital.data_dir)
        else:
            raise CustomException(
                msg="医院未配置 data_dir，且请求未指定 data_dir_override，无法导入",
                code=400,
                status_code=400,
            )
        data_dir = data_dir.resolve()
        if not data_dir.exists():
            raise CustomException(
                msg=f"data_dir 不存在: {data_dir}",
                code=400,
                status_code=400,
            )

        # 4. 生成 job_id，写初始状态
        job_id = uuid4_str()
        await cls._write_status(redis, hospital_id, {
            "job_id": job_id,
            "status": "pending",
            "total": 0,
            "processed": 0,
            "centers": todo_centers,
            "error": "",
            "started_at": datetime.now().isoformat(),
            "completed_at": "",
        })

        # 5. 启动后台协程（独立会话，不复用 auth.db）
        asyncio.create_task(
            cls._run_anon_etl_background(
                job_id=job_id,
                hospital_id=hospital_id,
                center_codes=todo_centers,
                data_dir=str(data_dir),
            )
        )
        log.info(
            f"anon ETL 任务已触发: hospital_id={hospital_id}, "
            f"job_id={job_id}, centers={todo_centers}, data_dir={data_dir}"
        )

        return {"job_id": job_id, "status": "pending"}

    @classmethod
    async def get_import_status_service(
        cls,
        hospital_id: int,
        redis: Redis,
    ) -> dict[str, Any]:
        """查询 anon ETL 导入状态（从 Redis 读取最近一次任务）。"""
        key = f"{ANON_ETL_STATUS_KEY_PREFIX}:{hospital_id}"
        raw = await RedisCURD(redis).get(key)
        if not raw:
            return {
                "job_id": "",
                "status": "idle",
                "total": 0,
                "processed": 0,
                "centers": [],
                "error": None,
                "started_at": None,
                "completed_at": None,
            }
        try:
            data = json.loads(raw)
            return data
        except (ValueError, TypeError):
            return {"status": "unknown", "error": "状态数据损坏"}

    @classmethod
    async def _run_anon_etl_background(
        cls,
        job_id: str,
        hospital_id: int,
        center_codes: list[str],
        data_dir: str,
    ) -> None:
        """后台执行 anon ETL（独立 DB 会话 + Redis 进度）。

        与 EtlService._run_etl_background 结构相同，区别：
        - 不传 tenant_id（anon 体系无此概念）
        - 用 run_anon_etl 替代 run_etl_pipeline
        - lifecycle_status 推进后 last_import_rows 取本次 row 总和
        """
        from redis.asyncio import Redis as RedisClient

        # 临时创建 Redis 连接（后台任务无法访问 app.state.redis）
        redis = await RedisClient.from_url(
            url=settings.REDIS_URI,
            encoding="utf-8",
            decode_responses=True,
        )

        started_at = datetime.now().isoformat()

        # 写 running 状态
        await cls._write_status(redis, hospital_id, {
            "job_id": job_id,
            "status": "running",
            "total": 0,
            "processed": 0,
            "centers": center_codes,
            "error": "",
            "started_at": started_at,
            "completed_at": "",
        })

        total_rows = 0
        try:
            # 调 run_anon_etl 跑全部中心（run_anon_etl 内部按中心独立事务）
            results = await run_anon_etl(
                centers=center_codes,
                data_root=Path(data_dir),
            )

            # 累加成功中心的行数
            for r in results:
                if r.get("status") == "success":
                    rows = r.get("rows") or {}
                    total_rows += sum(rows.values())

            # 推进医院状态
            async with async_db_session() as session:
                await session.execute(
                    update(HospitalModel)
                    .where(HospitalModel.id == hospital_id)
                    .values(
                        lifecycle_status=HospitalStatus.DATA_IMPORTED.value,
                        last_import_time=datetime.now(),
                        last_import_rows=total_rows,
                        import_error=None,
                    )
                )
                await session.commit()

            # 写完成状态
            completed_at = datetime.now().isoformat()
            await cls._write_status(redis, hospital_id, {
                "job_id": job_id,
                "status": "completed",
                "total": total_rows,
                "processed": total_rows,
                "centers": center_codes,
                "error": "",
                "started_at": started_at,
                "completed_at": completed_at,
                "results": results,
            })
            log.info(
                f"anon ETL 完成: hospital_id={hospital_id}, total_rows={total_rows}, "
                f"centers={center_codes}"
            )

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e!s}"
            log.error(f"anon ETL 失败: hospital_id={hospital_id}, error={error_msg}")

            completed_at = datetime.now().isoformat()
            await cls._write_status(redis, hospital_id, {
                "job_id": job_id,
                "status": "failed",
                "total": total_rows,
                "processed": total_rows,
                "centers": center_codes,
                "error": error_msg,
                "started_at": started_at,
                "completed_at": completed_at,
            })

            # 单独事务里更新医院 import_error
            try:
                async with async_db_session() as session:
                    await session.execute(
                        update(HospitalModel)
                        .where(HospitalModel.id == hospital_id)
                        .values(import_error=error_msg[:1000])
                    )
                    await session.commit()
            except Exception as inner_e:
                log.error(f"写入 import_error 失败: {inner_e!s}")
        finally:
            await redis.close()

    @classmethod
    async def _write_status(
        cls, redis: Redis, hospital_id: int, data: dict[str, Any]
    ) -> None:
        """写入完整状态到 Redis（覆盖式）。"""
        key = f"{ANON_ETL_STATUS_KEY_PREFIX}:{hospital_id}"
        await RedisCURD(redis).set(
            key=key,
            value=json.dumps(data, ensure_ascii=False),
            expire=ANON_ETL_STATUS_TTL,
        )
