"""ad-hoc 执行脚本安全闸：写非沙箱库必须显式声明目标（issue-21）。

背景
----
2026-09-20 事故复盘（docs/etl2/findings/incident-20260920-test-cascade-delete.md
§7.4 / §10）结论：「隔离要么靠机制、要么靠纪律，而纪律会失效」（本仓已有两例
清理泄漏实证）。测试沙箱（lnrs_dev + tests/anon_etl/_db_guard.py）解决的是
「测试」这一类；本闸解决另一类：`backend/etl2/` 下的一次性/执行型脚本
（backfill_dicom_series_count.py、_issue13_ingest_xinqiao_ct_exam.py、
_issue6_ingest_zhujiang_ct_exam.py 等）——带着 --apply 就能直接改生产库，
没有任何「你确定要写生产吗」的闸。

行为式闸，不是静态门
--------------------
「正则检查 SQL 里有没有 DELETE」这类静态门挡不住同类变体（UPDATE /
WHERE patient_id IN (...) / f-string 拼语句），且产生「规则通过」的错觉
（复盘 §7.3）。本闸只看两个事实：

1. 当前目标库是谁（settings.DATABASE_NAME，跟随 env，不硬编码库名）；
2. 调用者是否显式声明了目标（`--target`）。

规则
----
| 当前库 | 声明 | 行为 |
|---|---|---|
| 沙箱 lnrs_dev | 不要求 | 放行，仍打印目标库名 |
| 非沙箱（生产） | `--target production` 或 `--target <当前库名>` | 放行，打印目标 banner |
| 非沙箱（生产） | 未声明 / 声明库名与当前库不符 | **拒绝，退出码 2**，stderr 说明如何声明 |

启动时**总是**打印 banner：目标库名 + 目标 schema + 将写入的表 + 预计影响行数
（`estimated_rows=None` → 打印「未知」而不是假装知道；预计行数尽量取自脚本
自身的 --dry-run 口径）。

豁免面
------
ETL 主路径（`anon_etl_engine` / `anon_etl_service` 被 API 调用）**不经过本闸**：
它们是线上流程的入口，不是一次性执行脚本——给主路径加闸会打断线上流程。
豁免仅限该主路径；`backend/etl2/` 下新增的执行型脚本必须接入本闸。

与 tests/anon_etl/_db_guard.py 的关系
------------------------------------
那个模块是 pytest 写库测试的闸（ENVIRONMENT=test → lnrs_dev），面向测试；
本模块面向脚本。两者独立，本模块**不改动**它的既有语义。

用法
----
    from _script_guard import add_target_argument, gate

    add_target_argument(parser)      # 给脚本 argparse 加 --target 参数
    ...
    gate(schema="lnrs",
         tables=["lnrs.lnrs_anon_dicom_series"],
         declared=args.target,       # None = 未声明
         estimated_rows=n_or_None,   # 预计影响行数（来自 --dry-run 口径）
         action="write")             # 只读调用传 "read"（永不拒绝）
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

#: 沙箱库名 —— DATABASE_NAME 命中该值时免显式声明（沙箱本身就是安全的）
SANDBOX_DB_NAME = "lnrs_dev"

#: 可用作声明的别名（等价于「确认我要写生产」）
PRODUCTION_ALIAS = "production"

#: 拒绝执行时的退出码（非 0）
REFUSED_EXIT_CODE = 2

#: exam_text 灌库（anon_etl_engine._import_exam_text_table）写入的表——
#: issue-6 / issue-13 类执行脚本 banner 的共享清单；各脚本的 backfill/备份表在其上追加
EXAM_TEXT_INGEST_TABLES = (
    "lnrs.lnrs_anon_patient",
    "lnrs.lnrs_anon_exam",
    "lnrs.lnrs_anon_report_text",
    "lnrs.lnrs_anon_exam_detail",
    "lnrs.lnrs_anon_ingest_batch",
    "lnrs.lnrs_anon_phi_audit",
)

_TAG = "[WRITE-GATE]"


def current_db_name() -> str:
    """当前目标库名（跟随 settings.DATABASE_NAME，不硬编码库名）。"""
    from app.config.setting import settings

    return settings.DATABASE_NAME


def is_sandbox() -> bool:
    """当前目标是否沙箱库 lnrs_dev。"""
    return current_db_name() == SANDBOX_DB_NAME


def add_target_argument(parser: argparse.ArgumentParser) -> None:
    """给脚本的 argparse 加 --target 显式声明参数。"""
    parser.add_argument(
        "--target",
        default=None,
        help=(
            "显式声明写入目标：'production' 或当前库名（如 postgres / lnrs）；"
            f"沙箱库（{SANDBOX_DB_NAME}）免声明"
        ),
    )


def _declared_matches(declared: str | None, db_name: str) -> bool:
    """声明有效 = 'production' 别名，或声明值与当前库名一致（大小写不敏感）。"""
    if not declared:
        return False
    d = declared.strip().lower()
    return d == PRODUCTION_ALIAS or d == db_name.strip().lower()


def gate(
    *,
    schema: str,
    tables: Sequence[str],
    declared: str | None = None,
    estimated_rows: int | None = None,
    action: str = "write",
) -> str:
    """安全闸入口，在脚本启动时、任何写库动作之前调用。返回当前库名。

    - 总是打印目标 banner（库名 / schema / 将写入的表 / 预计影响行数）；
    - ``action="read"``（只读调用，如 --dry-run）→ 永不拒绝；
    - ``action="write"`` 且非沙箱库且未有效声明 → ``SystemExit(REFUSED_EXIT_CODE)``。

    注意：banner 与拒绝判断在连接数据库**之前**完成——闸本身不依赖 DB 可达。
    """
    if action not in ("read", "write"):
        raise ValueError(f"action 必须是 'read' 或 'write'，收到 {action!r}")

    db_name = current_db_name()
    env_label = "沙箱" if is_sandbox() else "生产"
    est = "未知" if estimated_rows is None else f"{estimated_rows} 行"
    tables_str = ", ".join(tables)
    print(f"{_TAG} 目标库    : {db_name}（{env_label}）")
    print(f"{_TAG} 目标 schema: {schema}")
    print(f"{_TAG} 将写入的表: {tables_str}")
    print(f"{_TAG} 预计影响行数: {est}")

    if action == "read":
        return db_name

    if is_sandbox():
        print(f"{_TAG} 沙箱库 → 免显式声明，放行")
        return db_name

    if _declared_matches(declared, db_name):
        print(f"{_TAG} 生产库 → 已显式声明 --target {declared}，放行")
        return db_name

    if declared:
        reason = f"声明的目标 {declared!r} 与当前库 {db_name!r} 不符"
    else:
        reason = "未显式声明写入目标"
    print(
        f"{_TAG} 拒绝执行：当前目标库为 {db_name!r}（生产），且{reason}。\n"
        f"{_TAG} 继续执行请改用：--target production "
        f"（或 --target {db_name}，即显式确认当前库名）。\n"
        f"{_TAG} 背景：docs/etl2/prd/issue-21-adhoc-script-write-guard.md "
        f"（2026-09-20 事故复盘 §7.4/§10）",
        file=sys.stderr,
    )
    raise SystemExit(REFUSED_EXIT_CODE)


def count_parquet_rows(path: Path) -> int | None:
    """parquet 文件行数（供闸 banner 的「预计影响行数」）。

    文件不存在或读取失败返回 None（banner 打印「未知」而不是假装知道）。
    只读文件元数据，不连接数据库。
    """
    p = Path(path)
    if not p.exists():
        return None
    try:
        import duckdb

        con = duckdb.connect()
        try:
            n = con.execute("SELECT count(*) FROM read_parquet(?)", [str(p)]).fetchone()[0]
        finally:
            con.close()
    except Exception:
        return None
    return int(n)
