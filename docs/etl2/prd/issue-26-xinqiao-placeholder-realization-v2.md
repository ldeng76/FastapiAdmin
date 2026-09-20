> **⚠ 总方向由 issue-27 确认（ADR 0012，2026-09-20）**：`is_placeholder` 已统一为
> 数据型语义；xinqiao 影像 stub 已因「名下有真实影像数据」统一翻 FALSE。
> 本 issue 的「回填 sex/birth_date」仍可执行（数据质量增强），但**不再是占位
> 翻转步骤**——回填后无标志翻转诉求；其两个决策门（数据源 / 范围）仍按本文件
> 流程走用户确认。见
> [issue-27](./issue-27-unify-placeholder-semantics.md) /
> [ADR 0012](../../adr/0012-is-placeholder-data-typed-semantics.md)。

# Issue 26: 新桥占位真实化 v2 — 5万例人口学源回填 sex/birth_date + `is_placeholder=FALSE`

## Parent

[Issue 15](./issue-15-xinqiao-placeholder-realization.md)（本单承接其目标；15 原文
保持不动，其「从 exam 行取 sex/birth_date」机制经实测**作废**——exam 表无人口学列，
ct_mapped 亦无）。父文档：[plan-xinqiao-disk03-import.md](../plan-xinqiao-disk03-import.md) §7-3。

## What to build

新桥 49,664 个 patient 全部 `is_placeholder=TRUE`（sex='0'、birth_date 全 NULL），
前端默认隐藏占位患者、KPI 默认排除——整个新桥在医学页面不可见。
真实人口学源已定位并验证（2026-09-20 调研，暂停前完成）：

`/data/wlx/DATABASE/01_disk/_字段与原始数据/2新桥/1_5万例排除术后_单一影像号_已处理/`
（gb18030，6 个 CSV，46,407 患者，**sex + 出生日期 100% 覆盖**，patients 与
检查报告双字段 0 矛盾；姓名/身份证已打码）。

端到端行为：按院内 PID → HMAC → `anon_id` 直接 join `lnrs_anon_patient`，
回填 `sex`（男→'1' / 女→'2'）与 `birth_date`（解析两种导出格式
`YYYY/M/D H:MM` / `YYYY-M-D HH:MM:SS`），并将有人口学的行 `is_placeholder=FALSE`。
不经 exam JOIN（人口学不在 exam 里）。

调研证据（已实测，实施前可抽查复验）：

| 项 | 结果 |
|---|---|
| 与 33,313 影像 PID 交集（归一 = 去尾部 `.`） | 33,312（仅 `10638055` 无源，保持占位） |
| 与 16,351 exam-only PID 交集 | 13,016 |
| 加 `2_5万例时序影像_带病理_新`（utf-8，49,753 人）后并集覆盖 | **49,662 / 49,664**，两队列 0 真实冲突（仅日期格式差异） |
| DICOM StudyDate + PatientAge 交叉验证 CSV 出生日期 | 12/12 通过 |

**决策门（实施前与用户确认，写入实施记录）**：

1. **数据源**：仅 c1（排除术后已处理队列，46,327 人可回填）vs
   c1∪c2 并集（49,662 人；推荐——0 冲突已验证，c1 优先、c2 补缺）。
2. **范围**：仅影像患者（33,312，issue-15 原字面 JOIN 路径）vs
   所有源中有人口学的占位患者（≈49,662；推荐——与引擎「档案到达：占位翻转为真实」
   的既有语义一致）。

## Acceptance criteria

- [ ] 决策门两条结论写入实施记录；PID 归一规则（尾部 `.`）与 sex/日期映射写明
- [ ] 备份：`CREATE TABLE lnrs.lnrs_anon_patient_bak_<ts> AS SELECT * FROM
  lnrs.lnrs_anon_patient WHERE center_code='xinqiao'`（PRD 原文 `AS TABLE … WHERE`
  非合法 PG，用 CTAS+SELECT）
- [ ] dry-run：报告回填行数（sex 变化 / birth_date 变化 / flip FALSE 数）及前后
  `is_placeholder` 分布
- [ ] `--apply` 成功；幂等重跑 0 行
- [ ] SQL 断言 1（承 issue-15）：`SELECT is_placeholder, COUNT(*) FROM
  lnrs.lnrs_anon_patient WHERE center_code='xinqiao' GROUP BY 1` 中 FALSE 行数 > 0
  且与 dry-run 一致
- [ ] SQL 断言 2（承 issue-15）：`is_placeholder=FALSE AND sex='0' AND
  birth_date IS NULL` 的 xinqiao 行数 = 0（真实化要求 sex/birth_date 至少其一为真值；
  本源两者都有，断言应自然满足）
- [ ] SQL 断言：`sex` 值域仅 {0,1,2}（0 = 未回填的占位残留）；zhujiang / shengyi
  patient 行数与人口学合计零漂移
- [ ] 产出验收 SQL（V1–Vn）+ 报告入 `docs/etl2/verify_result/`
- [ ] 不动 zhujiang / shengyi；不动 `lnrs_anon_exam` / `lnrs_anon_imaging_study` /
  `lnrs_anon_dicom_series`
- [ ] staging 产物（PID ↔ PT_ 映射表）含明文 PID，落 gitignore 目录，不入库 git

## Blocked by

None — 按 PID 键直填，不依赖 exam 侧工单（24/25）。

## Notes for implementer

- `anon_id = 'ANON_' + HMAC-SHA256(secret, 'xinqiao:'+pid)[:12]`，用引擎
  `compute_anon_id` 同式离线计算，join `lnrs_anon_patient.anon_id`；
  WHERE 加 `center_code='xinqiao' AND is_placeholder=TRUE` 守卫保证幂等。
- patient 表有 `updated_at` 触发器，UPDATE 自动留痕；涉及约 5 万行，
  单事务 + 分块执行，注意锁与超时。
- 同一患者多源值冲突（理论 0，已验证）→ 一律 fail-fast 中止并报告，不静默取舍。
- 与 [Issue 9](./issue-9-fix-shengyi-placeholder-flag.md) 结构对称、方向相反；
  可参照 `backend/etl2/backfill_shengyi_patient_placeholder.py` 的
  dry-run/apply/rollback 骨架。
