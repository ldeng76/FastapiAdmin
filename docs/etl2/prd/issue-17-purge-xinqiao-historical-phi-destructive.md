# Issue 17: git 历史 PHI 清除 — 扩展 issue-11 覆盖新桥 PHI 文件（**破坏性**）

## Parent

[plan-xinqiao-disk03-import.md](../plan-xinqiao-disk03-import.md)（§7-7）

## What to build

新桥导入新增两个含明文 PHI 的文件：

| 文件 | PHI 类型 |
|---|---|
| `docs/sour/ct_image_patient_map_xinqiao.csv` | 明文院内 PID（patient_id）|
| `docs/sour/xinqiao_imaging_study_patient_added.txt` | 明文院内 PID（patient_id）|

`.gitignore` 已有规则 `docs/sour/ct_image_patient_map*.csv` 与
`docs/sour/*_imaging_study_patient_added.txt`，理论上不会被新加入索引，但**历史未追踪
时不会被自动 ignore**——若曾被 `git add .` / `git add -A` 加进去再撤销，仍会留下历史快照。

本 issue 是 issue-11 的扩展，将所有 PHI 文件统一一次 filter-repo 处理。

**端到端目标**：`git log --all` 取不到任何 xinqiao / zhujiang / shengyi PHI 文件的明文内容。

## Acceptance criteria

- [ ] **决策门**：用户明确批准（在 issue 留痕或 commit message 引用批准来源）。
  未批准则本 issue 保持 open，**不做任何写操作**
- [ ] 执行前备份整个仓库（含 `.git`）到仓库外路径，备份路径记入 commit message
- [ ] 执行前确认远端可达（当前 `git push` 返回 **502**，`gz.proxy.git.sz` 代理不可用 —— 不可达时**不要**开始，
  否则改写完无法推送，本地历史与远端分支会永久分裂）
- [ ] 合并 filter-repo 路径：issue-11 的 2 个 + 本 issue 的 2 个，共 **4 个文件**：
  - `docs/sour/ct_image_patient_map.csv`
  - `docs/sour/shengyi_imaging_study_patient_added.txt`
  - `docs/sour/ct_image_patient_map_xinqiao.csv`
  - `docs/sour/xinqiao_imaging_study_patient_added.txt`
- [ ] 执行 `git filter-repo --path <上述 4 个> --invert-paths`（或等价的 BFG 流程）
- [ ] 验证断言 1：`git log --all --diff-filter=A --name-only | grep -E 'ct_image_patient_map(_xinqiao)?\.csv|.*imaging_study_patient_added\.txt' | wc -l` 返回 **0**
- [ ] 验证断言 2：对 4 个文件中出现过的敏感串做内容搜索，
  `git log --all -S '<sentinel>'` 无命中（sentinel 用不落盘的方式临时构造，**不要**把真实 PHI 写进 issue/commit message）
- [ ] 验证断言 3：`git fsck --lost-found` 后确认无悬挂对象仍含 PHI
  （`git reflog expire --expire=now --all && git gc --prune=now --aggressive`）
- [ ] 强推：`git push --force-with-lease`（**不要**用裸 `--force`）
- [ ] 强推后**通知协作者** re-clone（旧 clone 的 hash 已全部失效）；通知模板写入 commit message
- [ ] 确认工作区当前文件（`docs/sour/ct_image_patient_map_xinqiao.csv` 等）仍被 `.gitignore` 覆盖，避免再次误提交

## Blocked by

None - can start immediately（**但必须先得到用户对破坏性的明确批准**）。

## Notes for implementer

- 建议与 issue-11 合并实施（一次性处理 4 个文件，减少 `--force-with-lease` 次数）；
  本 issue 文档独立保留以体现「决策门 + 不可逆」特性
- push 不通时**禁止**开始；`gz.proxy.git.sz` 502 期间挂起，等推送恢复 + 协作者在场时再做
- 4 个文件在 `.gitignore` 里已有规则，所以**新增**文件不会再进来；本 issue 只处理**历史**
- 若团队决定接受残留 PHI 风险、不清理历史，本 issue 应**显式关闭**并写明「接受残留 PHI 风险，理由：…」，
  避免无限期挂着掩盖风险
- 参考：`.gitignore` 末尾注释已记录「这两个文件仍在历史提交中，彻底清除需 filter-repo/BFG 重写历史」；
  本 issue 完成后该注释也需更新为「已清除」