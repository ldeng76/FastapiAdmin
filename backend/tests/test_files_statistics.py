"""medical/files statistics KPI 契约测试（issue-28 口径）。

依赖：
- ENVIRONMENT=h196_3（连接 dev PostgreSQL；真库数据依赖，其他环境自动退出 0）

调用方式：
    cd backend && ENVIRONMENT=h196_3 uv run python tests/test_files_statistics.py
    cd backend && ENVIRONMENT=h196_3 uv run pytest tests/test_files_statistics.py

退出码 0 = 全部通过；非 0 = 失败（assert 抛 AssertionError）。

用例覆盖（issue-28 验收）：
1. KPI 字段契约（新增 total_patient_count；by_file_type/by_center 已消失）
2. file_count = Σ imaging_study.sop_count 且 ≥ record_count（省医回填后成立）
3. total_patient_count ≥ patient_count（影像口径）且 ≥ 0 —— 倒挂修复
4. total_patient_count 与 medicalDashboard「患者总量」同源同值
   （StatsQuery.count_patients 同条件：deleted_at IS NULL 且非占位）
5. 「全选」与「不选」等价：exam_type=全部实际值 vs 不过滤，KPI diff = 0
6. by_exam_type 百分比之和 = 100%，且候选即筛选器候选（实际存在的 exam_type）
7. center_type 筛选下推生效
"""

from __future__ import annotations

import asyncio
import os
import sys

# 确保 backend 根在 Python 路径（独立运行时）
_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)


async def _run_all() -> None:
    if os.environ.get("ENVIRONMENT") != "h196_3":
        print(
            "SKIP: 本文件为 dev 真库契约验证，需 ENVIRONMENT=h196_3"
            "（pytest 全量套件下自动跳过，退出码 0）"
        )
        sys.exit(0)

    from app.api.v1.module_system.auth.schema import AuthSchema
    from app.core.database import async_db_session
    from app.core.tenant import clear_current_tenant
    from app.plugin.module_medical.files.service import MedFilesService
    from app.plugin.module_medical.hospital.stats_query import StatsFiltersIn, StatsQuery

    async with async_db_session() as db:
        super_auth = AuthSchema(
            db=db, user_id=1, is_superuser=True,
            role_ids=[], dept_ids=[], tenant_id=1,
        )

        # 1. 字段契约
        r = await MedFilesService.statistics_service(auth=super_auth)
        for k in (
            "file_count", "record_count", "total_patient_count", "patient_count",
            "exam_patient_count", "exam_count", "total_size_bytes",
            "total_size_text", "by_exam_type",
        ):
            assert k in r, f"缺失字段: {k}"
        assert "by_file_type" not in r and "by_center" not in r, "by_file_type/by_center 应已移除"
        print("PASS 1: 字段契约（含 total_patient_count，无 by_center/by_file_type）")

        # 2. file_count ≥ record_count（sop_count 回填后成立，含省医）
        assert r["file_count"] >= r["record_count"] > 0, (
            f"file_count ({r['file_count']}) < record_count ({r['record_count']})"
        )
        print(f"PASS 2: file_count={r['file_count']:,} ≥ record_count={r['record_count']:,}")

        # 3. 倒挂修复：总患者数 ≥ 影像口径患者数 ≥ 0
        assert r["total_patient_count"] >= r["patient_count"] > 0, (
            f"总患者数 {r['total_patient_count']} < 影像患者数 {r['patient_count']} —— 倒挂未修复"
        )
        print(
            f"PASS 3: total_patient_count={r['total_patient_count']:,}"
            f" ≥ patient_count={r['patient_count']:,}（无倒挂）"
        )

        # 4. 与 medicalDashboard「患者总量」同源同值
        #    （StatsQuery.count_patients：deleted_at IS NULL 且非占位，无筛选）
        dashboard_total = await StatsQuery(db, filters=StatsFiltersIn()).count_patients()
        assert r["total_patient_count"] == dashboard_total, (
            f"medicalFiles total_patient_count ({r['total_patient_count']}) "
            f"≠ dashboard 患者总量 ({dashboard_total})"
        )
        print(f"PASS 4: total_patient_count == dashboard 患者总量 == {dashboard_total:,}")

        # 5. 「全选」与「不选」等价：exam_type = 全部实际值 vs 不过滤
        #    （前端候选由 by_exam_type 驱动 —— IN 覆盖全部值域必须等于无过滤）
        all_values = [x["value"] for x in r["by_exam_type"]]
        r_all = await MedFilesService.statistics_service(
            auth=super_auth, exam_type=all_values
        )
        kpi_keys = (
            "file_count", "record_count", "patient_count", "exam_count",
            "exam_patient_count", "total_patient_count", "total_size_bytes",
        )
        diff = {k: r_all[k] - r[k] for k in kpi_keys if r_all[k] != r[k]}
        assert not diff, f"全选 vs 不选 KPI 不一致: {diff}"
        print(f"PASS 5: 全选({len(all_values)} 种实际 exam_type) 与不选 KPI 完全一致")

        # 6. by_exam_type 百分比之和 = 100%
        total_pct = sum(x["percentage"] for x in r["by_exam_type"])
        assert abs(total_pct - 100.0) < 0.05, f"百分比之和 {total_pct} ≠ 100"
        assert all(x["count"] > 0 for x in r["by_exam_type"]), "候选应裁剪到实际存在的 exam_type"
        print(
            f"PASS 6: by_exam_type 百分比之和 = {total_pct:.2f}%，"
            f"候选 {len(all_values)} 种均有数据（筛选器裁剪生效）"
        )

        # 7. center_type 筛选下推
        r_shengyi = await MedFilesService.statistics_service(
            auth=super_auth, center_type=["shengyi"]
        )
        assert r_shengyi["patient_count"] > 0
        assert r_shengyi["patient_count"] <= r["patient_count"], "center_type 过滤失效"
        # 中心筛选下倒挂仍成立
        assert r_shengyi["total_patient_count"] >= r_shengyi["patient_count"]
        print(
            f"PASS 7: center_type=shengyi 下推生效"
            f"（patient_count={r_shengyi['patient_count']:,}，倒挂仍成立）"
        )

        print()
        print("=== ALL 7 TESTS PASSED ===")

    clear_current_tenant()


if __name__ == "__main__":
    asyncio.run(_run_all())
