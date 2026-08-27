---
name: lnrs-dev-start
description: 启动/停止本项目（lnrs）的前端与后端开发服务器。跨平台：Windows 用 backend/dev.ps1（PowerShell 7），Linux 用 uv run / run-h196_3.sh（命令映射见正文"Linux 适配"节）。后端为 FastAPI(uv)，前端为 Vite(pnpm)。使用场景：用户要求"启动前后端"、"启动项目"、"重启后端"、"停止服务"、"查看服务状态"等。
---
<!-- skill 同步副本：.zcode/skills/lnrs-dev-start/ 与 .claude/skills/lnrs-dev-start/ 内容须保持一致（.zcode 被 gitignore，.claude/skills 是 harness 注册位置）；修改任一侧请同步另一侧 -->

# lnrs 前后端启动 / 停止

本项目（lnrs / fastapiadmin）的前后端开发服务器启停指南（Windows / Linux 双平台）。

## Linux 适配（本机实测 2026-08，Ubuntu 22.04）

本机无 `pwsh`，`backend/dev.ps1` 不可用；正文 Windows 命令按此表替换（幂等重启语义不变：总是先停旧再起新）：

| Windows（正文） | Linux（本机） |
|---|---|
| `pwsh -NoProfile -File backend/dev.ps1 start -NoWindow` | `cd backend && uv run main.py run --env=dev`，后台任务方式运行（agent 环境用 hub `op:start`）；成功标志同为 `Application startup complete` |
| `dev.ps1 stop` / `stop -Force` | `pkill -f "main.py run --env=dev"`（强杀加 `-9`）；**必须带 `--env=<profile>` 精确匹配，勿杀错其它 profile** |
| `dev.ps1 status` | `ps aux \| grep "main.py run" \| grep -v grep` + `ss -ltnp \| grep -E ':(8001\|8610\|5610)\b'` |
| `dev.ps1 restart` | 先 pkill 后 start |
| `netstat -ano \| grep -E ":(8610\|5610)\s"` | `ss -ltnp \| grep -E ':(8001\|8610\|5610)\b'` |
| 幽灵 PID（`multiprocessing-fork` 子进程查不到） | `ss -ltnp \| grep :<port>` 找监听 PID 后 `kill -9`，或 `pkill -9 -f multiprocessing-fork` |
| 日志 `backend/.run/dev.log` / `dev.err.log` | 后台任务 stdout/stderr；或 `uv run main.py run --env=dev > backend/.run/dev.log 2> backend/.run/dev.err.log`（.run 目录需自建） |
| `./.venv/Scripts/python.exe` | `./.venv/bin/python`（或 `uv run python`） |

**Linux 环境 profile 与端口**——本机 dev 与 h196_3 两个后端 profile 并存（正文 8610 是 Windows 机器的 dev 端口；本机 dev 为 8001，勿混）：

| profile | 启动 | 端口 | 说明 |
|---|---|---|---|
| `dev` | `cd backend && uv run main.py run --env=dev`（后台任务） | 8001（`backend/env/.env.dev` 的 `SERVER_PORT`） | 无 pid 文件管理，停止用 pkill |
| `h196_3` | 仓库根 `./run-h196_3.sh start\|stop\|restart\|status\|logs` | 8610（`backend/env/.env.h196_3`） | 后端为 systemd 服务 `lnrs-backend`（本机实测 active）；脚本同时管理前端 |

- 前端不变：`cd frontend/web && pnpm dev`（5610，`frontend/web/.env` 的 `VITE_PORT`）。
- 验证 URL：dev → `http://localhost:8001/docs`；h196_3 → `http://localhost:8610/docs`；前端 → `http://localhost:5610/web`。
- 两 profile 可同机共存（端口不同）；pkill / 验证时严格区分 `--env=` 参数与端口。
- `backend/run_linux.sh` 是交互式菜单版（`./run_linux.sh --start-dev` 可非交互启 dev）；agent 环境建议直接后台跑 `uv run main.py run --env=dev`。
- `run-h196_3.sh` 依赖 `sudo`（systemctl）；sudo 不可用时退化为手动 `cd backend && uv run main.py run --env=h196_3`（后台任务）+ pkill。

## 端口与角色

| 服务 | 命令/入口 | 地址 | 说明 |
|------|-----------|------|------|
| 后端 | `backend/dev.ps1`（uv run main.py run --env=dev） | http://localhost:8610 | SERVER_PORT 在 `backend/env/.env.dev` |
| 前端 | `frontend/web`（pnpm dev / vite） | http://localhost:5610/web | VITE_PORT 在 `frontend/web/.env`，代理 `VITE_API_BASE_URL` → http://127.0.0.1:8610 |

## 统一语义：幂等重启

无论请求是"启动"还是"重启"，执行时**总是先确保旧实例干净停止，再启动新实例**：

- 后端未运行 → 直接 `start`；已运行 → 先 `stop` 再 `start`（等价于 `restart`）。
- 前端 → 先结束旧的后台任务，再 `pnpm dev`。

## 启动步骤

### 1. 前置检查（可选）

```bash
# 端口是否被占用
netstat -ano | grep -E ":(8610|5610)\s"
# 后端是否有残留进程（陈旧 pid 文件会显示 not alive）
pwsh -NoProfile -File backend/dev.ps1 status
```

### 2. 启动后端（后台运行，无弹窗，先停旧再起新）

```bash
# 先停旧实例（未运行时提示 no pid file，可忽略；杀不干净时改用 -Force）
pwsh -NoProfile -File backend/dev.ps1 stop
# 再启动
pwsh -NoProfile -File backend/dev.ps1 start -NoWindow
```

（可直接用 `pwsh -NoProfile -File backend/dev.ps1 restart -NoWindow` 一步完成。）

- 日志：`backend/.run/dev.log`、`backend/.run/dev.err.log`
- 成功标志：日志出现 `Application startup complete` / `Uvicorn running on http://localhost:8610`
- 若 stop 后 8610 端口仍被占用，用 `stop -Force` 强杀后再 `start`。

### 3. 启动前端（后台运行，先停旧再起新）

1. 先结束旧实例：结束此前启动的 pnpm/node 后台任务（或由启动它的终端 Ctrl+C）；不确定时可先检查 5610 端口占用。
2. 再启动：

```bash
cd frontend/web && pnpm dev
```

（在 agent 环境中用后台任务方式运行；若页面异常可改用 `pnpm dev:force` 清 Vite 缓存强启。）

### 4. 验证

```bash
# 后端：/docs 应返回 200（根路径 404 是正常的，无根路由）
curl -s -o /dev/null -w "%{http_code}" http://localhost:8610/docs
# 前端：页面可访问
curl -s -o /dev/null -w "%{http_code}" http://localhost:5610/web
```

浏览器访问 http://localhost:5610/web 即可使用。

## 停止 / 重启 / 状态

```bash
# 后端（按 .run/dev.pid 结束 uv + uvicorn 进程）
pwsh -NoProfile -File backend/dev.ps1 stop      # 优雅停止
pwsh -NoProfile -File backend/dev.ps1 stop -Force   # 强杀（含子进程）
pwsh -NoProfile -File backend/dev.ps1 restart   # = stop + start，幂等重启语义
pwsh -NoProfile -File backend/dev.ps1 status
# 前端：结束对应的 pnpm/node 后台任务（或由启动它的终端 Ctrl+C）
```

## 常见问题

- **`uv not found in PATH`**：需先安装 uv（pip install uv / winget install astral-sh.uv）。
- **`already running (pid ...)`**：说明 stop 未生效（进程未杀干净），用 `stop -Force` 强杀后再 `start`。
- **stop 后 8610 端口仍被占用，且 PID 查不到进程**：uvicorn 使用 multiprocessing 模式，监听端口的父进程可能不在 pid 文件记录中（幽灵 PID，Get-Process/taskkill 均查不到）。处理：列出 python 进程，找到命令行含 `multiprocessing-fork`/`spawn_main` 的子进程，`Stop-Process -Force` 杀掉它，父进程随之退出、端口释放。
- **启动失败（进程退出但无日志尾部）**：查看 `backend/.run/dev.err.log`，那里有完整 traceback。例如 `Directory .../docs/dicom_static does not exist` 表示 DICOM 静态目录缺失（init_app.py 已做 mkdir 保护，如再出现说明目录被删）。
- **启动后立即退出 / 端口被占用**：先查 `netstat`，杀掉占用进程或改 `.env.dev` 的 `SERVER_PORT`。
- **日志出现 UnicodeEncodeError**：dev.ps1 已设置 `PYTHONIOENCODING=utf-8` / `PYTHONUTF8=1`，正常不会出现；如出现请检查终端代码页（chcp 65001）。
- **数据库配置不完整**：dev.ps1 会校验 `backend/env/.env.dev` 中 `DATABASE_HOST/PORT/USER/NAME`，缺失时报 `Database configuration incomplete`。
- **后端启动慢**：首次启动会做 PostgreSQL 序列对齐、Redis 缓存初始化、动态路由注册（约 10~20 秒），等待日志出现 `Application startup complete` 再验证。
