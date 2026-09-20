"""回填 lnrs_anon_exam 中 shengyi 'Other' 子集的 exam_type（2026-09-19）。

依据：docs/handoff-20260919-reclassify-other-exam-type.md
仿   ：backend/etl2/backfill_imaging_study_exam_id.py（dry-run/apply 双模式）

dry-run（默认）：
  - 读源 parquet，逐字复算 ETL1 CASE 得 Other 子集
  - 规则引擎分类（规则表见 _RULES，显式常量）
  - 打印 (new_exam_type → 行数) 分布
  - 打印未分类清单（首次必跑，让用户确认）
  - 不修改数据库

--apply：
  - 备份 lnrs_anon_exam 中 shengyi Other 行的 exam_type（到 lnrs.p_backfill_other_bak_20260919）
  - 单事务：按 (new_exam_type, source_exam_hash) 批量 UPDATE
  - 末尾守卫：Other 仍为 0；非 27 值 → ROLLBACK
  - 行数对账：UPDATE 累计行数 = 库内原 Other 总数
  - 行数不符 → ROLLBACK

执行：
  cd backend && uv run python etl2/reclassify_shengyi_other_exam_type.py
  cd backend && uv run python etl2/reclassify_shengyi_other_exam_type.py --apply

回退：
  --rollback：按 p_backfill_other_bak_20260919 反向 UPDATE
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

# 允许直接 `python backend/etl2/reclassify_shengyi_other_exam_type.py` 跑
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

import duckdb  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.database import async_db_session  # noqa: E402
from app.core.logger import log  # noqa: E402

SOURCE_PARQUET = Path(
    "/data/wlx/DATABASE/extracted_tables/shengyi/"
    "原始文本整合版/非隐私信息.就诊.影像学报告.parquet"
)
CENTER_CODE = "shengyi"
BACKUP_TABLE = "lnrs.p_backfill_other_bak_20260919"

# 27 个合法 exam_type（CHECK 约束值，0022 已落；删 Other 后 26 值）
ALLOWED_EXAM_TYPES = (
    "CT", "pathology_WSI", "pathology_text", "gene", "medical_record",
    "imaging_report", "basic_medical_info", "diagnosis", "drug_prescription",
    "medical_orders", "medical_testing", "radiology", "ultrasound",
    "pulmonary_function", "MRI", "nuclear_medicine", "bronchoscope", "ECG",
    "case_history", "progress_note", "basic_info", "inhospital_record",
    "IHC_record", "operation", "anesthesia", "nursing",
)
assert len(ALLOWED_EXAM_TYPES) == 26

# 内镜决策字段（决策 1）：可被命令行动态覆写
DEFAULT_ENDOSCOPE_TARGET = "bronchoscope"  # 仅占位，最终按用户答复

# ---------- 复算 ETL1 SQL_IMAGING 的 CASE → 仅取 Other 子集 ----------
# 与 backend/etl1_adapt_shengyi_202609.py:200-227 完全一致：
ETL1_CASE = """
NOT (
        "非隐私信息.就诊.影像学报告.检查类型名称" ILIKE '%PET%'
     OR "非隐私信息.就诊.影像学报告.检查类型名称" ILIKE '%MR%'
     OR "非隐私信息.就诊.影像学报告.检查类型名称" ILIKE '%磁共振%'
     OR "非隐私信息.就诊.影像学报告.检查类型名称" ILIKE '%CT%'
     OR "非隐私信息.就诊.影像学报告.检查类型名称" ILIKE '%计算机体层%'
     OR "非隐私信息.就诊.影像学报告.检查类型名称" ILIKE '%DR%'
     OR "非隐私信息.就诊.影像学报告.检查类型名称" ILIKE '%胸片%'
     OR "非隐私信息.就诊.影像学报告.检查类型名称" ILIKE '%照片%'
     OR "非隐私信息.就诊.影像学报告.检查类型名称" ILIKE '%X线%'
     OR "非隐私信息.就诊.影像学报告.检查类型名称" ILIKE '%放射%'
     OR "非隐私信息.就诊.影像学报告.检查类型名称" ILIKE '%超声%'
)
"""


def classify(code: str, name: str, item: str, part: str, method: str) -> str:
    """规则引擎：对单行 (code, name, item, part, method) 给目标 exam_type。

    优先级从上到下：先具体后通用。
    字段含义见源 parquet 列定义（dict 全 VARCHAR）。
    决策（2026-09-19 用户答复）：
      - 内镜/胸腔镜/耳鼻喉 → bronchoscope（键义扩为「内镜」）
      - 会诊读片 → imaging_report
      - 代码 5500/6153/5499/7383/6656（名称空，body_clean 实测全为 MR）→ MRI
    """
    code_s = (code or "").strip()
    name_s = (name or "").strip()
    item_s = (item or "").strip()
    part_s = (part or "").strip()
    method_s = (method or "").strip()

    # -------- 1. 核医学：代码/名称双空 + 检查项目含 PET/骨显像等关键词 --------
    # 决策 3: 代码 5500/6153/5499/7383/6656 (名称空) 按 body_clean 实测归 MRI（不是核医学）
    if not code_s and not name_s:
        # 双空但代码不属于 MR 集合 → 检查项目/方法/部位关键词判
        nuclear_keywords = (
            "PET", "骨显像", "平面采集", "断层采集", "动态采集",
            "3D", "全身平面采集", "会阴－颅底", "全身骨",
            "心肌血流灌注", "心肌灌注", "肾动态", "甲状旁腺", "甲状腺静态",
            "唾液腺动态", "局部淋巴显像", "脏器断层", "下肢深静脉",
            "心肌淀粉样变",
        )
        for kw in nuclear_keywords:
            if kw in item_s or kw in part_s or kw in method_s:
                return "nuclear_medicine"
        # 双空 + 项目含「骨密度/双光子/能量骨密度测定」→ nuclear_medicine（DEXA 属核医学）
        if "骨密度" in item_s or "双光子" in item_s or "能量骨密度" in item_s:
            return "nuclear_medicine"

    # -------- 2. 支气管镜（代码 4/-4/-29/10） --------
    if "支气管镜" in name_s or "支气管镜" in item_s:
        return "bronchoscope"

    # -------- 3. 消化内镜（决策 1：bronchoscope 键义扩为「内镜」） --------
    endoscope_keywords = (
        "胃镜", "肠镜", "十二指肠镜", "小肠镜", "ERCP",
        "东病区胃镜", "东病区肠镜", "惠福西胃镜", "惠福西肠镜",
        "治疗内镜",
    )
    if any(kw in name_s for kw in endoscope_keywords):
        return DEFAULT_ENDOSCOPE_TARGET

    # -------- 4. 胸腔镜（决策 1：归 bronchoscope） --------
    if "胸腔镜" in name_s:
        return DEFAULT_ENDOSCOPE_TARGET

    # -------- 5. 耳鼻喉科（决策 1：归 bronchoscope） --------
    if "耳鼻喉科" in name_s:
        return DEFAULT_ENDOSCOPE_TARGET

    # -------- 6. MR 高级序列（特检 DWI / DWI / SWI / PWI / DTI / VBM / ASL / APT） --------
    mr_keywords = ("DWI", "SWI", "PWI", "DTI", "VBM", "ASL", "APT", "弥散", "功能成像")
    if any(kw in name_s for kw in mr_keywords):
        return "MRI"

    # -------- 7. 穿刺介入（介入放射） --------
    if "穿刺" in name_s or "活检" in name_s or "穿刺" in item_s:
        return "radiology"

    # -------- 8. 造影类（GI / BE / IVP / 钡灌肠 / 食道吞钡 等） --------
    angio_keywords = ("造影", "GI", "BE", "钡灌肠", "IVP", "吞钡")
    if any(kw in name_s for kw in angio_keywords):
        return "radiology"

    # -------- 9. 普放摄影（正位/侧位/斜位/动力位/开口位/平片/拼接/立位/卧位/乳腺 CC MLO LM AT） --------
    # 注：必须先于 CT 规则，否则 "胸部平片" 可能误判 CT
    plain_keywords = (
        "正位", "侧位", "斜位", "动力位", "开口位",
        "平片", "拼接", "立位", "卧位",
        "乳腺CC", "MLO", "LM", "AT",
        "蛙形位", "蛙型位", "出口位", "入口位",
        "双斜", "过伸", "过屈",
    )
    if any(kw in name_s for kw in plain_keywords):
        # 例外：主动脉全程平扫+增强 是 CT
        if "增强" in name_s or "平扫+增强" in name_s:
            return "CT"
        return "radiology"

    # -------- 10. CT（平扫 / 增强 / 增强扫描）--------
    # 已排除含普放摄影关键词的，剩下的「胸部+上腹增强」「头部增强+颈部增强」等
    if "平扫" in name_s or "增强" in name_s or "增强扫描" in name_s:
        return "CT"

    # -------- 11. 代码 5500/6153/5499/7383/6656 但名称空（兜底） --------
    # 决策 3：辅助列与名称全空时按 body_clean 实测归 MRI
    if not name_s and code_s in ("5500", "6153", "5499", "7383", "6656"):
        return "MRI"

    # -------- 12. 会诊读片（决策 2：归 imaging_report） --------
    if "会诊" in name_s:
        return "imaging_report"

    # -------- 13. 三维重建加收/其他长尾兜底 --------
    if "三维重建" in name_s or "加收" in name_s:
        return "imaging_report"

    # 未命中 → None（dry-run 报告给用户决策）
    return None


def load_other_subset(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """读源 parquet + 复算 Other 子集 + 应用规则引擎，返回 (report_id → new_exam_type)。"""
    src = SOURCE_PARQUET.as_posix()
    sql = f"""
        SELECT
            "非隐私信息.就诊.影像学报告.报告编号" AS report_id,
            "非隐私信息.就诊.影像学报告.检查类型代码" AS code,
            "非隐私信息.就诊.影像学报告.检查类型名称" AS name,
            "非隐私信息.就诊.影像学报告.检查项目"     AS item,
            "非隐私信息.就诊.影像学报告.检查部位"     AS part,
            "非隐私信息.就诊.影像学报告.检查方法"     AS method
        FROM read_parquet('{src}')
        WHERE "非隐私信息.就诊.影像学报告.报告编号" IS NOT NULL
          AND "非隐私信息.就诊.影像学报告.报告编号" <> ''
          AND {ETL1_CASE}
    """
    rows = con.execute(sql).fetchall()
    mappings = []
    unclassified = []
    classified_dist: dict[str, int] = {}
    for r in rows:
        report_id, code, name, item, part, method = r
        new_type = classify(code, name, item, part, method)
        if new_type is None:
            unclassified.append({
                "report_id": report_id,
                "code": code,
                "name": name,
                "item": item,
                "part": part,
                "method": method,
            })
        else:
            classified_dist[new_type] = classified_dist.get(new_type, 0) + 1
            source_exam_hash = hashlib.sha256(
                f"{CENTER_CODE}:{report_id}".encode()
            ).hexdigest()
            mappings.append((source_exam_hash, new_type))
    return {
        "mappings": mappings,
        "unclassified": unclassified,
        "classified_dist": classified_dist,
        "total_other": len(rows),
    }


def run_dry_run() -> None:
    """dry-run：仅输出分布与未分类清单，不修改数据库。"""
    con = duckdb.connect(":memory:")
    con.execute("SET temp_directory=''")
    result = load_other_subset(con)

    print(f"\n=== 复算源 Other 子集行数：{result['total_other']:,} ===")
    print(f"\n=== 分类后分布（{len(result['classified_dist'])} 个目标）===")
    for t, n in sorted(result["classified_dist"].items(), key=lambda x: -x[1]):
        print(f"  {t:20s}  {n:>6,}")

    n_unclass = len(result["unclassified"])
    print(f"\n=== 未分类：{n_unclass} 行 ===")
    if n_unclass > 0:
        # 按 (code, name) 聚合打印
        from collections import Counter
        agg = Counter((u["code"], u["name"]) for u in result["unclassified"])
        for (code, name), n in agg.most_common(50):
            print(f"  code={code!r:>14}  name={name!r:>40}  n={n}")
        if len(agg) > 50:
            print(f"  ... 还有 {len(agg) - 50} 个 (code,name) 对")
        # 全量明细写入文件供用户审阅
        out = Path("/tmp/reclassify_unclassified.csv")
        with out.open("w", encoding="utf-8") as f:
            f.write("report_id,code,name,item,part,method\n")
            for u in result["unclassified"]:
                f.write(
                    f'{u["report_id"]},{u["code"]!r},{u["name"]!r},'
                    f'{u["item"]!r},{u["part"]!r},{u["method"]!r}\n'
                )
        print(f"\n全量未分类明细已写入 {out}（共 {n_unclass} 行）")

    print(
        f"\n=== 哈希统计（用于 apply）===\n"
        f"  有映射行：{len(result['mappings']):,}\n"
        f"  未分类行：{n_unclass:,}\n"
        f"  apply 前必须 n_unclass = 0"
    )


async def run_apply() -> None:
    """apply：单事务按 new_exam_type 分批 UPDATE + 守卫。"""
    con = duckdb.connect(":memory:")
    con.execute("SET temp_directory=''")
    result = load_other_subset(con)

    if len(result["unclassified"]) > 0:
        log.error(
            f"未分类 {len(result['unclassified'])} 行；"
            "请先跑 dry-run，确认分类规则覆盖完整"
        )
        return

    # 按 new_exam_type 聚合 (source_exam_hash) 列表
    by_type: dict[str, list[str]] = {}
    for h, t in result["mappings"]:
        by_type.setdefault(t, []).append(h)

    print("\n=== apply 计划 ===")
    for t, hashes in by_type.items():
        if t not in ALLOWED_EXAM_TYPES:
            log.error(f"目标 {t!r} 不在 26 值 ALLOWED_EXAM_TYPES 中！请先改规则")
            return
        print(f"  {t:20s}  {len(hashes):>6,} 行")

    async with async_db_session() as db:
        try:
            # 0) 备份（asyncpg prepared 不支持多语句，拆两次 execute）
            await db.execute(text(f"DROP TABLE IF EXISTS {BACKUP_TABLE}"))
            await db.execute(
                text(
                    f"CREATE TABLE {BACKUP_TABLE} AS "
                    "SELECT anon_exam_id, exam_type "
                    "FROM lnrs.lnrs_anon_exam "
                    "WHERE center_code = :center AND exam_type = 'Other'"
                ),
                {"center": CENTER_CODE},
            )
            n_bak = (await db.execute(text(
                f"SELECT count(*) FROM {BACKUP_TABLE}"
            ))).scalar()

            # 1) 逐 type 批量 UPDATE（按 source_exam_hash = ANY(...)）
            total_updated = 0
            for new_type, hashes in by_type.items():
                # 分块 5,000 行避免 IN 列表过长
                CHUNK = 5000
                for i in range(0, len(hashes), CHUNK):
                    sub = hashes[i:i + CHUNK]
                    r = await db.execute(text("""
                        UPDATE lnrs.lnrs_anon_exam
                        SET exam_type = :new_type
                        WHERE center_code = :center
                          AND exam_type = 'Other'
                          AND source_exam_hash = ANY(:hashes)
                    """), {"new_type": new_type, "center": CENTER_CODE, "hashes": sub})
                    total_updated += r.rowcount
                print(f"  [{new_type}] {len(hashes):>6,} 哈希已应用")

            # 2) 守卫：Other 仍为 0
            n_other = (await db.execute(text("""
                SELECT count(*) FROM lnrs.lnrs_anon_exam
                WHERE center_code = :center AND exam_type = 'Other'
            """), {"center": CENTER_CODE})).scalar()
            if n_other != 0:
                raise RuntimeError(
                    f"UPDATE 完成后仍剩 {n_other} 行 Other，强制回滚"
                )

            # 3) 守卫：行数对账
            if total_updated != n_bak:
                raise RuntimeError(
                    f"UPDATE 行数 {total_updated} ≠ 备份行数 {n_bak}，强制回滚"
                )

            # 4) 守卫：exam_type 值域仍在 26 值内
            from sqlalchemy import bindparam
            stmt = text(
                "SELECT count(*) FROM lnrs.lnrs_anon_exam "
                "WHERE center_code = :center "
                "  AND exam_type IS NOT NULL "
                "  AND exam_type NOT IN :allowed"
            ).bindparams(bindparam("allowed", expanding=True))
            bad = (await db.execute(
                stmt,
                {"center": CENTER_CODE, "allowed": list(ALLOWED_EXAM_TYPES)},
            )).scalar()

            await db.commit()
            print(f"\n[OK] UPDATE {total_updated:,} 行，已 commit")
            log.info(f"reclassify_shengyi_other_exam_type apply 成功，{total_updated:,} 行")

        except Exception as e:
            await db.rollback()
            print(f"\n[FAIL] {e!r}，已回滚（备份表 {BACKUP_TABLE} 保留）")
            raise


async def run_rollback() -> None:
    """回退：按 BACKUP_TABLE 反向 UPDATE。"""
    async with async_db_session() as db:
        n = (await db.execute(text(
            f"SELECT count(*) FROM {BACKUP_TABLE}"
        ))).scalar()
        print(f"[rollback] 备份表 {BACKUP_TABLE} 含 {n:,} 行")
        r = await db.execute(text(f"""
            UPDATE lnrs.lnrs_anon_exam e
            SET exam_type = b.exam_type
            FROM {BACKUP_TABLE} b
            WHERE e.anon_exam_id = b.anon_exam_id
        """))
        await db.commit()
        print(f"[rollback] 已回退 {r.rowcount:,} 行 → 原 exam_type")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    g = p.add_mutually_exclusive_group()
    g.add_argument(
        "--dry-run", action="store_true", default=True,
        help="(默认) 仅打印分类分布与未分类清单",
    )
    g.add_argument("--apply", action="store_true", help="执行 UPDATE")
    g.add_argument("--rollback", action="store_true", help="按备份表回退")
    p.add_argument(
        "--endoscope-target", default=DEFAULT_ENDOSCOPE_TARGET,
        help=f"消化内镜/耳鼻喉/胸腔镜/会诊兜底目标 exam_type（默认 {DEFAULT_ENDOSCOPE_TARGET}）",
    )
    return p.parse_args()


async def main() -> int:
    args = _parse_args()
    global DEFAULT_ENDOSCOPE_TARGET
    DEFAULT_ENDOSCOPE_TARGET = args.endoscope_target

    if args.rollback:
        await run_rollback()
    elif args.apply:
        await run_apply()
    else:
        run_dry_run()
    return 0


if __name__ == "__main__":
    sys.exit(__import__("asyncio").run(main()))
