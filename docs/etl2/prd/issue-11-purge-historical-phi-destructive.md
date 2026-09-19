# Issue 11: 清除 git 历史中的 PHI（**破坏性**）

## Parent

[plan-disk1-disk2-disk4-zhujiang-import.md](../plan-disk1-disk2-disk4-zhujiang-import.md)（§7-7）

## What to build

两个 PHI 文件曾进入 git 历史，虽已 `git rm --cached` 并从工作区移除跟踪，
但**内容仍存在于历史提交中** —— 任何 clone 都能 `git show` 取到：

| 文件 | PHI 类型 |
|---|---|
| `docs/sour/ct_image_patient_map.csv` | 明文患者姓名 |
| `docs/sour/shengyi_imaging_study_patient_added.txt` | 院内 PID |

**端到端目标**：`git log --all` 不再能取到这两个文件的任何内容。

> 这是**破坏性**操作：改写所有 commit hash，影响协作者、CI、已克隆的工作区。
> **必须先得到用户的明确批准**再动手。

## Acceptance criteria

- [ ] **决策门**：用户明确批准执行（在 issue 上留痕或 commit message 引用批准来源）。未批准则本 issue 保持 open，不做任何写操作
- [ ] 执行前备份整个仓库（含 `.git`）到仓库外路径，备份路径记入 commit message
- [ ] 执行前确认远端可达（当前 `git push` 返回 **502**，`gz.proxy.git.sz` 代理不可用 —— 不可达时**不要**开始，否则改写完无法推送）
- [ ] 执行 `git filter-repo --path docs/sour/ct_image_patient_map.csv --path docs/sour/shengyi_imaging_study_patient_added.txt --invert-paths`（或等价的 BFG 流程）
- [ ] 验证断言 1：`git log --all --diff-filter=A --name-only | grep -c 'ct_image_patient_map.csv'` 返回 **0**
- [ ] 验证断言 2：`git log --all --diff-filter=A --name-only | grep -c 'shengyi_imaging_study_patient_added.txt'` 返回 **0**
- [ ] 验证断言 3：对两个文件中出现过的敏感串做内容搜索，`git log --all -S '<sentinel>'` 无命中（sentinel 用不落盘的方式临时构造，**不要**把真实 PHI 写进 issue/commit message）
- [ ] 验证断言 4：`git fsck --lost-found` 后确认无悬挂对象仍含 PHI（`filter-repo` 会清理 reflog，需 `git reflog expire --expire=now --all && git gc --prune=now --aggressive`）
- [ ] 强推：`git push --force-with-lease`（**不要**用裸 `--force`）
- [ ] 强推后**通知协作者** re-clone（旧 clone 的 hash 已全部失效）；通知模板写入 commit message
- [ ] 确认工作区当前文件（`docs/sour/ct_image_patient_map_xinqiao.csv` 等）仍被 `.gitignore` 覆盖，避免再次误提交

## Blocked by

None - can start immediately（**但必须先得到用户对破坏性的明确批准**）。

## Notes for implementer

- **不要在批准前执行**。这是全仓历史改写，误操作不可逆（备份也只在本地）。
- 与当前 push 502 故障叠加：**push 不通时做 filter-repo 是危险的** —— 本地历史已改写但推不上去，
  期间协作者的提交会与改写后的历史冲突。等 push 恢复且协作者在场时再做。
- 两个文件在 `.gitignore` 里已有规则（`docs/sour/ct_image_patient_map*.csv`、
  `docs/sour/*_imaging_study_patient_added.txt`），所以**新增**文件不会再进来；本 issue 只处理**历史**。
- 若团队决定接受风险、不清理历史，则本 issue 应显式关闭并写明「接受残留 PHI 风险，理由：…」，
  而不是无限期挂着 —— 挂着的 issue 会掩盖风险。
- 参考：`.gitignore` 末尾注释已记录「这两个文件仍在历史提交中，彻底清除需 filter-repo/BFG 重写历史」。
