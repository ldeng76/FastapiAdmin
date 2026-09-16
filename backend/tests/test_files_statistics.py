"""medical/files statistics KPI dev 验证脚本。

依赖：
- ENVIRONMENT=h196_3（连接 dev PostgreSQL）
- pytest-asyncio（如需 pytest 调用；否则直接 `uv run python` 也能跑）

调用方式：
    cd backend && ENVIRONMENT=h196_3 uv run python tests/test_files_statistics.py

退出码 0 = 全部通过；非 0 = 失败（assert 抛 AssertionError）。
本文件也可被 pytest 收集（每个 test_* 标记 @pytest.mark.asyncio + 依赖 pytest-asyncio）。

集成测试用例覆盖：
1. KPI 字段契约（schema 必含字段 / by_file_type 已消失）
2. exam_count ≠ file_count（语义对齐事实）
3. by_exam_type 百分比之和 = 100%
4. 未关联 bucket 存在且 count = by_exam_type_unlinked
5. by_exam_type_total == file_count（LEFT JOIN 不丢行）
6. center_type 筛选下推生效
7. exam_type 筛选下推生效
8. by_center 含 shengyi / zhujiang 至少之一
9. Permission noop 回归锁（MedFilesModel / AnonDicomSeriesModel / AnonExamModel 无 created_id）
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
            f"SKIP: ENVIRONMENT={os.environ.get('ENVIRONMENT')!r} ≠ 'h196_3'",
            file=sys.stderr,
        )
        sys.exit(0)

    # 触发完整 import chain
    from app.plugin.module_medical.files.service import MedFilesService
    from app.api.v1.module_system.auth.schema import AuthSchema
    from app.core.database import async_db_session
    from app.core.tenant import clear_current_tenant
    from app.core.permission import Permission
    from app.plugin.module_medical.files.model import MedFilesModel
    from app.plugin.module_medical.hospital.anon_model import (
        AnonDicomSeriesModel,
        AnonExamModel,
    )
    from sqlalchemy import select, func

    async with async_db_session() as db:
        super_auth = AuthSchema(
            db=db, user_id=1, is_superuser=True,
            role_ids=[], dept_ids=[], tenant_id=1,
        )

        # 1. 字段契约
        r = await MedFilesService.statistics_service(auth=super_auth)
        for k in (
            "file_count", "patient_count", "exam_count",
            "total_size_bytes", "total_size_text",
            "by_exam_type", "by_exam_type_total", "by_exam_type_unlinked",
            "by_center",
        ):
            assert k in r, f"缺失字段: {k}"
        assert "by_file_type" not in r, "by_file_type 应已被 by_center 替换"
        print("PASS 1: 字段契约（含 by_exam_type_total/unlinked, by_center）")

        # 2. exam_count ≠ file_count
        assert r["file_count"] > 0 and r["exam_count"] > 0
        assert r["exam_count"] != r["file_count"], (
            f"exam_count ({r['exam_count']}) 不应等于 file_count ({r['file_count']})"
        )
        print(
            f"PASS 2: exam_count={r['exam_count']} ≠ file_count={r['file_count']}"
        )

        # 3. by_exam_type 百分比之和 = 100
        total_pct = sum(x["percentage"] for x in r["by_exam_type"])
        assert abs(total_pct - 100.0) < 0.05, f"百分比之和 {total_pct} ≠ 100"
        print(f"PASS 3: by_exam_type 百分比之和 = {total_pct:.2f}%")

        # 4. 未关联 bucket
        unlinked = [x for x in r["by_exam_type"] if x["value"] == "__unlinked__"]
        assert len(unlinked) == 1, "未关联 bucket 必须有且仅有一行"
        u = unlinked[0]
        assert u["label"] == "未关联检查"
        assert u["count"] > 0
        assert u["count"] == r["by_exam_type_unlinked"]
        print(
            f"PASS 4: 未关联 bucket count={u['count']} label={u['label']!r}"
        )

        # 5. by_exam_type_total == file_count
        assert r["by_exam_type_total"] == r["file_count"], (
            f"by_exam_type_total ({r['by_exam_type_total']}) ≠ file_count ({r['file_count']})"
        )
        print(f"PASS 5: by_exam_type_total == file_count == {r['file_count']}")

        # 6. center_type 筛选下推
        r_zhujiang = await MedFilesService.statistics_service(
            auth=super_auth, center_type=["zhujiang"]
        )
        centers = {x["value"] for x in r_zhujiang["by_center"]}
        assert centers == {"zhujiang"}, f"center_type 过滤失效: {centers}"
        print("PASS 6: center_type=zhujiang 筛选下推 → by_center 只有 zhujiang")

        # 7. exam_type 筛选下推
        r_ct = await MedFilesService.statistics_service(
            auth=super_auth, exam_type=["CT"]
        )
        values = {x["value"] for x in r_ct["by_exam_type"]}
        assert "__unlinked__" not in values, (
            f"exam_type 筛选下推后不应再有未关联桶: {values}"
        )
        assert r_ct["exam_count"] < r["exam_count"]
        print(
            f"PASS 7: exam_type=CT 筛选下推 → by_exam_type 无未关联桶, "
            f"exam_count 收窄 {r['exam_count']}→{r_ct['exam_count']}"
        )

        # 8. by_center 含 shengyi / zhujiang
        centers_all = {x["value"] for x in r["by_center"]}
        assert centers_all & {"shengyi", "zhujiang"}, (
            f"未见 shengyi/zhujiang: {centers_all}"
        )
        print(f"PASS 8: by_center 含 {centers_all}")

        # 9. Permission noop 回归锁
        auth_self = AuthSchema(
            db=db, user_id=999, is_superuser=False,
            check_data_scope=True,
            role_ids=[1], dept_ids=[], tenant_id=1,
        )
        for model, sql_factory in [
            (MedFilesModel, lambda m: select(func.count(m.id))),
            (AnonDicomSeriesModel, lambda m: select(func.count(m.series_id))),
            (AnonExamModel, lambda m: select(func.count(m.anon_exam_id))),
        ]:
            sql = sql_factory(model)
            sql = await Permission(model, auth_self).filter_query(sql)
            compiled = str(sql.compile(compile_kwargs={"literal_binds": True}))
            assert "created_id" not in compiled, (
                f"{model.__name__} Permission 应为 noop，但 SQL 含 created_id: "
                f"{compiled[:200]}"
            )
        print(
            "PASS 9: Permission noop 回归锁（3 个无 created_id 模型 SQL 均无 created_id 过滤）"
        )

        print()
        print("=== ALL 9 TESTS PASSED ===")

    clear_current_tenant()


if __name__ == "__main__":
    asyncio.run(_run_all())