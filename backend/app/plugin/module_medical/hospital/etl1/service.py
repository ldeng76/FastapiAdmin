"""ETL-1 服务层 — FastAPI 后台任务 + Redis 进度跟踪。

与 etl_service.py (ETL-2) 的对比:

| 维度 | ETL-1 (本文件) | ETL-2 (etl_service.py) |
|------|---------------|----------------------|
| 输入 | Excel 文件路径 | parquet 目录 (hospital.data_dir) |
| 输出 | data/<center>/*.parquet | PostgreSQL med_* 表 |
| 触发条件 | registered (任何状态都可跑) | mapping_configured / data_imported |
| 依赖 mapping rule | 否 (走 center config) | 是 |
| lifecycle 推进 | 不推进 (保持原状态) | → data_imported |
| 调用方式 | asyncio.to_thread (run_etl1 是同步) | 直接 await (run_etl_pipeline 是 async) |
| 进度粒度 | 按表 (tables_done/total) | 按行 (processed/total) |

关键设计:
- run_etl1 是同步函数 (duckdb 阻塞), 用 asyncio.to_thread 包到线程池跑
- 进度回调 on_table_done 通过 asyncio.run_coroutine_threadsafe 跨线程写 Redis
- 临时 Redis 连接 (后台任务无法访问 app.state.redis), 用完关闭
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
from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.logger import log
from app.core.redis_crud import RedisCURD
from app.utils.common_util import uuid4_str

from ..model import HospitalModel
from .config import CenterConfig, get_center_config, list_centers
from .core import run_etl1

# Redis key 前缀和 TTL (与 ETL-2 区分, 避免覆盖)
ETL1_STATUS_KEY_PREFIX = "etl1:status"
ETL1_STATUS_TTL = 3600  # 1 小时


class Etl1Service:
    """ETL-1 (Excel → Parquet) 服务。"""

    @classmethod
    async def trigger_run_service(
        cls,
        auth: AuthSchema,
        hospital_id: int,
        xlsx_path: str,
        center_code: str | None = None,
        only_tables: list[str] | None = None,
        dry_run: bool = False,
        redis: Redis | None = None,
    ) -> dict[str, str]:
        """触发 ETL-1 转换 (异步后台执行)。

        参数:
            auth: 用户上下文 (含 db 会话, 用于校验医院)
            hospital_id: 医院 ID
            xlsx_path: Excel 文件路径 (绝对/相对仓库根)
            center_code: 医院代号; 不传则用 hospital.code
            only_tables: 只处理这些表; None=全部
            dry_run: True 时只校验不写文件
            redis: Redis 连接 (controller 注入); 后台任务会自建独立连接

        返回: {"job_id": "...", "status": "pending", "center_code": "..."}
        """
        # 1. 校验医院
        hospital = await auth.db.get(HospitalModel, hospital_id)
        if not hospital:
            raise CustomException(msg="医院不存在", code=404, status_code=404)

        # center_code 优先级: 参数 > hospital.code
        actual_center = center_code or hospital.code
        try:
            center_cfg = get_center_config(actual_center)
        except KeyError:
            raise CustomException(
                msg=f"未注册的 center_code: {actual_center!r}; 已注册: {list_centers()}",
                code=400, status_code=400,
            )

        # 2. 校验 xlsx 文件
        xlsx = Path(xlsx_path)
        if not xlsx.is_absolute():
            # 相对路径相对仓库根
            from app.config.path_conf import BASE_DIR
            xlsx = (BASE_DIR.parent / xlsx).resolve()
        if not xlsx.exists():
            raise CustomException(
                msg=f"xlsx 文件不存在: {xlsx}", code=400, status_code=400,
            )
        if xlsx.suffix.lower() != ".xlsx":
            raise CustomException(
                msg=f"仅支持 .xlsx, 收到: {xlsx.suffix}", code=400, status_code=400,
            )

        # 3. 校验 only_tables 都在 center_cfg 范围内 (避免拼错)
        if only_tables:
            valid = set(center_cfg.all_target_tables())
            invalid = [t for t in only_tables if t not in valid]
            if invalid:
                raise CustomException(
                    msg=f"only_tables 含未知表: {invalid}; 该 center 支持的: {sorted(valid)}",
                    code=400, status_code=400,
                )

        # 4. 生成 job_id, 写初始状态
        job_id = uuid4_str()
        if redis is not None:
            await cls._write_status(redis, hospital_id, {
                "job_id": job_id,
                "status": "pending",
                "center_code": actual_center,
                "xlsx_path": str(xlsx),
                "tables_total": len(center_cfg.all_target_tables()),
                "tables_done": 0,
                "current_table": "",
                "total_rows": 0,
                "rows_per_table": {},
                "error": None,
                "started_at": datetime.now().isoformat(),
                "completed_at": None,
            })

        # 5. 启动后台协程
        asyncio.create_task(
            cls._run_etl1_background(
                job_id=job_id,
                hospital_id=hospital_id,
                center_cfg=center_cfg,
                xlsx_path=str(xlsx),
                only_tables=only_tables,
                dry_run=dry_run,
            )
        )
        log.info(
            f"ETL1 任务已触发: hospital_id={hospital_id}, center={actual_center}, "
            f"job_id={job_id}, xlsx={xlsx.name}"
        )

        return {"job_id": job_id, "status": "pending", "center_code": actual_center}

    @classmethod
    async def get_run_status_service(
        cls, hospital_id: int, redis: Redis
    ) -> dict[str, Any]:
        """查询 ETL-1 任务状态 (从 Redis 读取)。"""
        key = f"{ETL1_STATUS_KEY_PREFIX}:{hospital_id}"
        raw = await RedisCURD(redis).get(key)
        if not raw:
            return {
                "job_id": "",
                "status": "idle",
                "center_code": "",
                "xlsx_path": "",
                "tables_total": 0,
                "tables_done": 0,
                "current_table": "",
                "total_rows": 0,
                "rows_per_table": {},
                "error": None,
                "started_at": None,
                "completed_at": None,
            }
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return {"status": "unknown", "error": "状态数据损坏"}

    # ============================================================
    # 后台协程
    # ============================================================

    @classmethod
    async def _run_etl1_background(
        cls,
        job_id: str,
        hospital_id: int,
        center_cfg: CenterConfig,
        xlsx_path: str,
        only_tables: list[str] | None,
        dry_run: bool,
    ) -> None:
        """后台执行 ETL-1。

        策略:
        - run_etl1 是同步阻塞函数 (duckdb), 用 asyncio.to_thread 包到线程池
        - 进度回调 on_table_done 是同步函数 (在 worker 线程里被调用),
          通过 asyncio.run_coroutine_threadsafe 把 Redis 写入转发回主事件循环
        - 失败时单独事务更新 hospital.import_error
        """
        from redis.asyncio import Redis as AsyncRedis
        from app.config.setting import settings

        # 2026-07-19 代码评审修复 (Issue #10):
        # 若 AsyncRedis.from_url() 抛错 (Redis 不可达), redis 变量未定义,
        # finally 块的 redis.aclose() 会 UnboundLocalError 掩盖真正错误。
        # 提前初始化为 None, finally 里守卫。
        redis: AsyncRedis | None = None
        try:
            # 后台任务自建 Redis 连接 (无法访问 app.state.redis)
            redis = await AsyncRedis.from_url(
                url=settings.REDIS_URI,
                encoding="utf-8",
                decode_responses=True,
            )
        except Exception as e:
            log.error(f"ETL1: 连接 Redis 失败, 进度将无法上报: {e!s}")
            # 不抛出, 让 ETL 继续跑 (Redis 是软依赖)
            redis = None

        # 主事件循环引用 (供 worker 线程回调跨线程提交协程)
        loop = asyncio.get_running_loop()
        started_at = datetime.now().isoformat()
        tables_done = 0
        total_rows = 0
        rows_per_table: dict[str, int] = {}
        current_table_holder: dict[str, str] = {"name": ""}

        # 写 running 状态
        await cls._write_status(redis, hospital_id, {
            "job_id": job_id,
            "status": "running",
            "center_code": center_cfg.code,
            "xlsx_path": xlsx_path,
            "tables_total": len(center_cfg.all_target_tables()),
            "tables_done": 0,
            "current_table": "",
            "total_rows": 0,
            "rows_per_table": {},
            "error": None,
            "started_at": started_at,
            "completed_at": None,
        })

        # 同步进度回调 (在 worker 线程被 run_etl1 调用)
        def on_table_done(table: str, rows: int) -> None:
            nonlocal tables_done, total_rows
            tables_done += 1
            total_rows += max(rows, 0)
            rows_per_table[table] = rows
            current_table_holder["name"] = table
            # 跨线程提交一个协程到主事件循环 (写 Redis)
            fut = asyncio.run_coroutine_threadsafe(
                cls._update_status(redis, hospital_id, {
                    "tables_done": tables_done,
                    "total_rows": total_rows,
                    "current_table": table,
                    "rows_per_table": dict(rows_per_table),
                }),
                loop,
            )
            try:
                # 阻塞等待完成 (worker 线程可以阻塞); 超时 5s 防死锁
                fut.result(timeout=5)
            except Exception as e:
                log.warning(f"ETL1 进度写入失败 (table={table}): {e!s}")

        try:
            # 在线程池跑同步 run_etl1
            stats = await asyncio.to_thread(
                run_etl1,
                center=center_cfg,
                xlsx_path=xlsx_path,
                only_tables=only_tables,
                dry_run=dry_run,
                on_table_done=on_table_done,
            )

            # dry_run 时 stats 里是 -1, 转成 0 用于显示
            display_stats = {k: max(v, 0) for k, v in stats.items()}

            completed_at = datetime.now().isoformat()
            await cls._write_status(redis, hospital_id, {
                "job_id": job_id,
                "status": "completed",
                "center_code": center_cfg.code,
                "xlsx_path": xlsx_path,
                "tables_total": len(display_stats),
                "tables_done": len(display_stats),
                "current_table": "",
                "total_rows": sum(display_stats.values()),
                "rows_per_table": display_stats,
                "error": None,
                "started_at": started_at,
                "completed_at": completed_at,
            })
            log.info(
                f"ETL1 完成: hospital_id={hospital_id}, center={center_cfg.code}, "
                f"tables={len(display_stats)}, total_rows={sum(display_stats.values())}"
            )

            # 单独事务更新 hospital.last_import_time (不推进 lifecycle_status;
            # ETL-1 产出 parquet, 还需 ETL-2 才进 PG)
            try:
                async with async_db_session() as session:
                    await session.execute(
                        update(HospitalModel)
                        .where(HospitalModel.id == hospital_id)
                        .values(
                            last_import_time=datetime.now(),
                            last_import_rows=sum(display_stats.values()),
                            import_error=None,
                        )
                    )
                    await session.commit()
            except Exception as inner_e:
                log.error(f"ETL1: 更新 hospital.last_import_time 失败: {inner_e!s}")

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e!s}"
            log.error(
                f"ETL1 失败: hospital_id={hospital_id}, center={center_cfg.code}, "
                f"error={error_msg}"
            )
            completed_at = datetime.now().isoformat()
            await cls._write_status(redis, hospital_id, {
                "job_id": job_id,
                "status": "failed",
                "center_code": center_cfg.code,
                "xlsx_path": xlsx_path,
                "tables_total": len(center_cfg.all_target_tables()),
                "tables_done": tables_done,
                "current_table": current_table_holder["name"],
                "total_rows": total_rows,
                "rows_per_table": dict(rows_per_table),
                "error": error_msg,
                "started_at": started_at,
                "completed_at": completed_at,
            })

            # 单独事务更新 hospital.import_error
            try:
                async with async_db_session() as session:
                    await session.execute(
                        update(HospitalModel)
                        .where(HospitalModel.id == hospital_id)
                        .values(import_error=f"[ETL1] {error_msg}"[:1000])
                    )
                    await session.commit()
            except Exception as inner_e:
                log.error(f"ETL1: 写入 import_error 失败: {inner_e!s}")

        finally:
            # redis-py 5.0+: close() 已弃用, 改用 aclose()
            # redis 可能是 None (from_url 抛错时), 守卫一下
            if redis is not None:
                await redis.aclose()

    # ============================================================
    # Redis 状态读写
    # ============================================================

    @classmethod
    async def _write_status(
        cls, redis: Redis | None, hospital_id: int, data: dict[str, Any]
    ) -> None:
        """写入完整状态到 Redis (覆盖式)。

        2026-07-19 修复 (Issue #10): redis 可能为 None (连接失败时),
        此时 noop 让 ETL 继续跑 (Redis 是软依赖)。
        """
        if redis is None:
            return
        key = f"{ETL1_STATUS_KEY_PREFIX}:{hospital_id}"
        await RedisCURD(redis).set(
            key=key,
            value=json.dumps(data, ensure_ascii=False),
            expire=ETL1_STATUS_TTL,
        )

    @classmethod
    async def _update_status(
        cls, redis: Redis | None, hospital_id: int, partial: dict[str, Any]
    ) -> None:
        """增量更新状态 (读后合并再写回)。

        同 _write_status, redis=None 时 noop。
        """
        if redis is None:
            return
        key = f"{ETL1_STATUS_KEY_PREFIX}:{hospital_id}"
        raw = await RedisCURD(redis).get(key)
        if raw:
            try:
                data = json.loads(raw)
                data.update(partial)
            except (ValueError, TypeError):
                data = partial
        else:
            data = partial
        await RedisCURD(redis).set(
            key=key,
            value=json.dumps(data, ensure_ascii=False),
            expire=ETL1_STATUS_TTL,
        )
