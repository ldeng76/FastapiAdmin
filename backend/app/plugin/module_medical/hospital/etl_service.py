"""ETL 导入服务 — asyncio 后台执行 + Redis 进度跟踪 + 状态机推进。

触发流程（trigger_import_service）：
1. 校验医院 + lifecycle_status
2. 校验 data_dir 存在
3. 加载映射规则
4. 生成 job_id，asyncio.create_task 启动后台协程
5. 立即返回 job_id

后台协程（_run_etl_background）：
1. 独立 DB 会话（async_db_session，非请求会话）
2. Redis 写初始进度
3. 调 etl_engine.run_etl_pipeline
4. 成功 → 更新医院 lifecycle_status=data_imported + last_import_time/rows
5. 失败 → Redis 写 error + 医院写 import_error
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from redis.asyncio.client import Redis
from sqlalchemy import select, update

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.logger import log
from app.core.redis_crud import RedisCURD
from app.utils.common_util import uuid4_str

from .etl_engine import resolve_data_dir, run_etl_pipeline
from .model import HospitalModel, HospitalStatus, MappingRuleModel

# ETL 状态 Redis key 前缀和 TTL
ETL_STATUS_KEY_PREFIX = "etl:status"
ETL_STATUS_TTL = 3600  # 1 小时

# 允许触发导入的状态（mapping_configured: 首次导入; data_imported: 重新导入）
IMPORTABLE_STATUSES = {HospitalStatus.MAPPING_CONFIGURED.value, HospitalStatus.DATA_IMPORTED.value}


class EtlService:
    """ETL 导入服务"""

    @classmethod
    async def trigger_import_service(
        cls, auth: AuthSchema, hospital_id: int, redis: Redis
    ) -> dict[str, str]:
        """触发 ETL 导入（异步后台执行）。

        返回: {"job_id": "...", "status": "pending"}
        """
        # 1. 校验医院
        hospital = await auth.db.get(HospitalModel, hospital_id)
        if not hospital:
            raise CustomException(msg="医院不存在", code=404, status_code=404)

        if hospital.lifecycle_status not in IMPORTABLE_STATUSES:
            raise CustomException(
                msg=f"当前状态[{hospital.lifecycle_status}]不允许导入，需先配置映射",
                code=400, status_code=400,
            )

        # 2. 校验 data_dir
        if not hospital.data_dir:
            raise CustomException(msg="医院未配置 data_dir，无法导入", code=400, status_code=400)
        data_dir = resolve_data_dir(hospital.data_dir)
        if not data_dir.exists():
            raise CustomException(
                msg=f"data_dir 不存在: {data_dir}", code=400, status_code=400
            )

        # 3. 加载映射规则
        stmt = select(MappingRuleModel).where(
            MappingRuleModel.hospital_id == hospital_id,
            MappingRuleModel.is_deleted == False,  # noqa: E712
        )
        result = await auth.db.execute(stmt)
        rules = result.scalars().all()
        if not rules:
            raise CustomException(
                msg="医院未配置任何映射规则，无法导入", code=400, status_code=400
            )

        # 4. 生成 job_id，写初始状态
        job_id = uuid4_str()
        await cls._write_status(redis, job_id, {
            "status": "pending",
            "total": 0,
            "processed": 0,
            "error": "",
            "started_at": datetime.now().isoformat(),
            "completed_at": "",
        })

        # 5. 启动后台协程（独立会话，不复用 auth.db）
        asyncio.create_task(
            cls._run_etl_background(
                job_id=job_id,
                hospital_id=hospital_id,
                tenant_id=hospital.tenant_id,
                data_dir=str(data_dir),
                rules=list(rules),
            )
        )
        log.info(f"ETL 任务已触发: hospital_id={hospital_id}, job_id={job_id}")

        return {"job_id": job_id, "status": "pending"}

    @classmethod
    async def get_import_status_service(
        cls, hospital_id: int, redis: Redis
    ) -> dict[str, Any]:
        """查询导入状态（从 Redis 读取）。"""
        # job_id 通过 hospital.last_import_time 关联不够精确，
        # 这里用约定：每个医院最近一次 job_id 存在 hospital.import_error 旁边
        # 简化：扫描 etl:status:{hospital_id}:* —— 但 UUID 不可预测
        # 更简单：状态 key 直接用 hospital_id（只跟踪最近一次）
        key = f"{ETL_STATUS_KEY_PREFIX}:{hospital_id}"
        raw = await RedisCURD(redis).get(key)
        if not raw:
            return {
                "job_id": "",
                "status": "idle",
                "total": 0,
                "processed": 0,
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
    async def _run_etl_background(
        cls,
        job_id: str,
        hospital_id: int,
        tenant_id: int,
        data_dir: str,
        rules: list[MappingRuleModel],
    ) -> None:
        """后台执行 ETL（独立 DB 会话 + Redis 进度）。

        注意：此方法在 asyncio.create_task 中运行，不持有请求上下文。
        所有 DB 操作用独立会话（async_db_session）。
        Redis 连接临时创建（用完关闭），因后台任务无法访问 app.state.redis。

        事务模型：
        - async_db_session() 自动开启事务（SQLAlchemy 2.0 默认）
        - ETL 在事务内运行；on_table_done 和 status 更新通过 await 同步
        - 成功：调用 session.commit() 提交
        - 失败：session 自动 rollback（async with 退出时）
        - import_one_table 内 ON CONFLICT DO NOTHING 跳过单条重复键
        - 整段 ETL 在同一事务里，任一张表 import_one_table 抛错则全部回滚
        """
        from pathlib import Path

        from redis.asyncio import Redis

        from app.config.setting import settings

        # 临时创建 Redis 连接（后台任务无法访问 app.state.redis）
        redis = await Redis.from_url(
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
            "error": "",
            "started_at": started_at,
            "completed_at": "",
        })

        total_rows = 0
        try:
            async with async_db_session() as session:
                # async_db_session 自动 begin() — 直接在事务内运行 ETL
                # 进度回调
                async def on_table_done(src_table: str, rows: int) -> None:
                    nonlocal total_rows
                    total_rows += rows
                    await cls._update_status(redis, hospital_id, {
                        "total": total_rows,
                        "processed": total_rows,
                    })

                result = await run_etl_pipeline(
                    db=session,
                    data_dir=Path(data_dir),
                    tenant_id=tenant_id,
                    mapping_rules=rules,
                    on_table_done=on_table_done,
                )

                # 推进医院状态（同一事务）
                await session.execute(
                    update(HospitalModel)
                    .where(HospitalModel.id == hospital_id)
                    .values(
                        lifecycle_status=HospitalStatus.DATA_IMPORTED.value,
                        last_import_time=datetime.now(),
                        last_import_rows=sum(result.values()),
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
                "error": "",
                "started_at": started_at,
                "completed_at": completed_at,
            })
            log.info(f"ETL 完成: hospital_id={hospital_id}, total_rows={total_rows}")

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e!s}"
            log.error(f"ETL 失败: hospital_id={hospital_id}, error={error_msg}")

            # 写失败状态
            completed_at = datetime.now().isoformat()
            await cls._write_status(redis, hospital_id, {
                "job_id": job_id,
                "status": "failed",
                "total": total_rows,
                "processed": total_rows,
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
        key = f"{ETL_STATUS_KEY_PREFIX}:{hospital_id}"
        await RedisCURD(redis).set(key=key, value=json.dumps(data, ensure_ascii=False), expire=ETL_STATUS_TTL)

    @classmethod
    async def _update_status(
        cls, redis: Redis, hospital_id: int, partial: dict[str, Any]
    ) -> None:
        """增量更新状态（读取后合并再写回）。"""
        key = f"{ETL_STATUS_KEY_PREFIX}:{hospital_id}"
        raw = await RedisCURD(redis).get(key)
        if raw:
            try:
                data = json.loads(raw)
                data.update(partial)
            except (ValueError, TypeError):
                data = partial
        else:
            data = partial
        await RedisCURD(redis).set(key=key, value=json.dumps(data, ensure_ascii=False), expire=ETL_STATUS_TTL)
