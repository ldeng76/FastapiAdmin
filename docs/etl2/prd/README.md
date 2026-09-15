# 方案 B — PRD 与 Issue 拆分

本目录包含方案 B（让 `/#/medicalFiles` 文件大小显示真实数字）的 PRD 与独立 issue 拆分。

## 文件

| 文件 | 用途 |
|---|---|
| `PRD.md` | 完整 PRD：问题陈述 / 方案 / 用户故事 / 实施决策 / ADR / 测试决策 / 范围外 |
| `issue-1-backfill-imaging-study-exam-id.md` | Issue 1: 回填 imaging_study.anon_exam_id（zhujiang 全量） |
| `issue-2-run-dicom-series-etl.md` | Issue 2: 跑 ETL-2 dicom_series 阶段（zhujiang） |
| `issue-3-switch-files-statistics-to-view.md` | Issue 3: service 切视图 + 清理方案 A 临时改动 |
| `issue-4-investigate-shengyi-exam-gap.md` | Issue 4（独立调研）: shengyi exam 缺口根因调查 |

## 依赖关系

```
Issue 1 ──→ Issue 2 ──→ Issue 3
                ↑
        Issue 4（独立并行；与 1/2/3 无依赖）
```

## 启动方式

每个 issue 在独立会话启动时：

```bash
# 新会话的入口
cat docs/etl2/prd/PRD.md
cat docs/etl2/prd/issue-N-*.md
# 然后调用 /implement
```

issue 已 self-contained：包含 Parent / What to build / Acceptance criteria / Blocked by / Notes for implementer 五段；接手人不需要回看本会话上下文。

## 与既有 commit 的关系

- `722e4f66`（方案 A 止血，已 commit 并 push）：本目录的所有 issue 与之不冲突；Issue 3 撤除方案 A 的临时 null/— 兜底。
- `a9000c56`（方案 B 脚本骨架，已 commit 未 push）：本目录的 Issue 1/2 直接调用该 commit 的脚本；不需要新增代码。

## 后续动作

- 本次 commit：PRD + 4 个 issue 落到 `docs/etl2/prd/`，不 push。
- 用户 review → 选择接下来跑哪个 issue（在哪个新会话用 `/implement` 启动）。