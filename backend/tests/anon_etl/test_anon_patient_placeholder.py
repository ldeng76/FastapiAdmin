"""lnrs_anon_patient.is_placeholder 占位标记回归测试。

背景（2026-09-07 根因修复）：患者列表 ~59% 显示「未知的性别」——ETL2 导入
exam/visit/surgery 表时为无档案患者自动发号的占位记录（sex 恒 '0'、无人口学）
被患者列表原样展示（dev 实测 137,490 / 231,352 = 59.4%）。

本文件锁定两条契约（语义按 ADR 0012 数据型口径修订）：
1. upsert 语义：自动发号建档（占位路径）写 is_placeholder=FALSE（名下有
   exam/visit 引用行，非占位）；完整档案到达亦 FALSE + 人口学落库；
   其后占位 upsert 不得覆盖人口学。
2. 列表查询：默认（include_placeholders=False）隐藏占位患者，
   两种模式总数差 == 存活占位行数；出参含 is_placeholder 字段。

无 DB 环境自动跳过（检测同 test_etl_smoke）。
"""

from __future__ import annotations

import asyncio

import pytest

# 库选择与安全闸统一在 tests/anon_etl/_db_guard.py（单一落点）。
# 语义：仅 ENVIRONMENT=test（沙箱库 lnrs_dev）下运行；库名命中真库集合则 fail。
from _db_guard import PG_READY, SKIP_REASON  # noqa: E402


@pytest.mark.skipif(not PG_READY, reason=SKIP_REASON)
class TestUpsertPlaceholderSemantics:
    """upsert 占位/完整档案翻转语义（独立测试中心 + 显式清理）。"""

    def test_placeholder_then_full_record_flips_back(self):
        asyncio.run(self._body())

    @staticmethod
    async def _body():
        import uuid
        from datetime import date, datetime, timedelta

        from sqlalchemy import text

        from app.core.database import async_db_session, async_engine
        from app.plugin.module_medical.hospital import anon_etl_engine
        from app.plugin.module_medical.hospital.anonymize import compute_anon_id

        center = f"ph_test_{uuid.uuid4().hex[:8]}"
        anon_id = compute_anon_id(center, "T1")
        batch_ph = str(uuid.uuid4())
        batch_full = str(uuid.uuid4())
        base_ts = datetime.utcnow()

        try:
            async with async_db_session() as session:
                # 准备 2 个批次行（patient.created_batch_id FK）
                # 注意：PG 的 NOW() 是事务内常量且 INTERVAL 关键字不接受参数，
                # started_at 用 Python 侧时间戳显式区分，避免撞
                # lnrs_anon_uq_batch_center_secret 唯一约束。
                for b, delta in ((batch_ph, timedelta(0)), (batch_full, timedelta(seconds=1))):
                    await session.execute(
                        text(
                            "INSERT INTO lnrs.lnrs_anon_ingest_batch "
                            "(batch_id, center_code, source_kind, source_locator, secret_version, "
                            " key_fingerprint, schema_hash, row_counts, started_at, status) "
                            "VALUES (:b, :c, 'csv_report', 'unit_test', 'v1', '0', '0', '{}'::jsonb, "
                            " :sa, 'success')"
                        ),
                        {"b": b, "c": center, "sa": base_ts + delta},
                    )

                # 1) 占位路径（自动发号）建档 → is_placeholder=FALSE
                #    （数据型语义 ADR 0012：该患者名下有 exam/visit 引用行，
                #    不是占位；is_placeholder=True 参数只控制 ON CONFLICT
                #    不覆盖人口学的行为）
                await anon_etl_engine._batch_upsert_patients(
                    session,
                    center_code=center,
                    patient_records=[
                        {"local_id": "T1", "anon_id": anon_id, "sex": "0", "birth_date": None}
                    ],
                    batch_id=batch_ph,
                    is_placeholder=True,
                )
                row = (
                    await session.execute(
                        text(
                            "SELECT is_placeholder, sex FROM lnrs.lnrs_anon_patient "
                            "WHERE anon_id=:a"
                        ),
                        {"a": anon_id},
                    )
                ).fetchone()
                assert row is not None, "自动发号建档应创建患者行"
                assert row[0] is False, "数据型语义（ADR 0012）：自动建档必须写 is_placeholder=FALSE"
                assert row[1] == "0"

                # 2) 完整档案到达 → 翻回 FALSE + 人口学落库
                await anon_etl_engine._batch_upsert_patients(
                    session,
                    center_code=center,
                    patient_records=[
                        {
                            "local_id": "T1",
                            "anon_id": anon_id,
                            "sex": "1",
                            "birth_date": date(1990, 1, 1),
                        }
                    ],
                    batch_id=batch_full,
                    is_placeholder=False,
                )
                row = (
                    await session.execute(
                        text(
                            "SELECT is_placeholder, sex, birth_date FROM lnrs.lnrs_anon_patient "
                            "WHERE anon_id=:a"
                        ),
                        {"a": anon_id},
                    )
                ).fetchone()
                assert row[0] is False, "完整档案必须把 is_placeholder 翻回 FALSE"
                assert row[1] == "1"
                assert row[2] == date(1990, 1, 1)

                # 3) 其后占位 upsert：不得重新标记、不得覆盖人口学
                await anon_etl_engine._batch_upsert_patients(
                    session,
                    center_code=center,
                    patient_records=[
                        {"local_id": "T1", "anon_id": anon_id, "sex": "0", "birth_date": None}
                    ],
                    batch_id=batch_ph,
                    is_placeholder=True,
                )
                row = (
                    await session.execute(
                        text(
                            "SELECT is_placeholder, sex, birth_date FROM lnrs.lnrs_anon_patient "
                            "WHERE anon_id=:a"
                        ),
                        {"a": anon_id},
                    )
                ).fetchone()
                assert row[0] is False, "占位 upsert 不得把真实患者重新标记为占位"
                assert row[1] == "1", "占位 upsert 不得覆盖人口学（sex）"
                assert row[2] == date(1990, 1, 1), "占位 upsert 不得覆盖人口学（birth_date）"

                # 清理（显式删除，不依赖回滚）
                await session.execute(
                    text("DELETE FROM lnrs.lnrs_anon_patient WHERE anon_id=:a"),
                    {"a": anon_id},
                )
                await session.execute(
                    text(
                        "DELETE FROM lnrs.lnrs_anon_ingest_batch WHERE batch_id IN (:a, :b)"
                    ),
                    {"a": batch_ph, "b": batch_full},
                )
                await session.commit()
        finally:
            # 引擎连接池绑定首个 asyncio.run 的 loop；dispose 后
            # 下一个测试的 asyncio.run 会在自己的 loop 上建连。
            await async_engine.dispose()


@pytest.mark.skipif(not PG_READY, reason=SKIP_REASON)
class TestListPlaceholderFilter:
    """患者列表占位过滤契约（只读）。"""

    def test_hidden_by_default_and_total_diff(self):
        asyncio.run(self._body())

    def test_patient_id_search_includes_placeholder_records(self):
        from app.plugin.module_medical.hospital.stats_query import build_patient_filters
        from app.plugin.module_medical.hospital.stats_schema import StatsFiltersIn

        conditions = build_patient_filters(StatsFiltersIn(patient_id="PT_00039060"))

        assert len(conditions) == 2, (
            "按患者编号搜索时不应额外排除占位患者；"
            "否则占位患者无法通过唯一编号被定位"
        )

    @staticmethod
    async def _body():
        from sqlalchemy import text

        from app.core.database import async_db_session, async_engine
        from app.plugin.module_medical.hospital.anon_medical_query import anon_list_patients
        from app.plugin.module_medical.hospital.stats_schema import StatsFiltersIn

        try:
            async with async_db_session() as session:
                ph_count = (
                    await session.execute(
                        text(
                            "SELECT COUNT(*) FROM lnrs.lnrs_anon_patient "
                            "WHERE deleted_at IS NULL AND is_placeholder"
                        )
                    )
                ).fetchone()[0]

                _, total_all = await anon_list_patients(
                    session, filters=StatsFiltersIn(is_placeholders=True), limit=1
                )
                _, total_hide = await anon_list_patients(
                    session, filters=StatsFiltersIn(is_placeholders=False), limit=1
                )
                assert total_all - total_hide == ph_count, (
                    f"两模式总数差必须等于占位数: {total_all} - {total_hide} != {ph_count}"
                )

                _, total_default = await anon_list_patients(session, limit=1)
                assert total_default == total_hide, "默认必须隐藏占位患者"

                items_hide, _ = await anon_list_patients(
                    session, filters=StatsFiltersIn(is_placeholders=False), limit=100
                )
                assert items_hide, "dev 库应有非占位患者"
                assert all(it["is_placeholder"] is False for it in items_hide), (
                    "隐藏模式下不得出现 is_placeholder=TRUE 行"
                )

                items_all, _ = await anon_list_patients(
                    session, filters=StatsFiltersIn(is_placeholders=True), limit=100
                )
                assert all("is_placeholder" in it for it in items_all), "出参必须含 is_placeholder 字段"
                items_by_id, total_by_id = await anon_list_patients(
                    session,
                    filters=StatsFiltersIn(patient_id="PT_00039060"),
                    limit=10,
                )
                assert total_by_id == 1, "目标患者编号应返回唯一记录"
                assert items_by_id[0]["patient_id"] == "PT_00039060"
                assert items_by_id[0]["is_placeholder"] is True
                await session.rollback()
        finally:
            await async_engine.dispose()
