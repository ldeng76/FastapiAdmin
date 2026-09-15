# Web 部署面板设计（固定密码触发 h196_3 部署）

日期：2026-09-15　状态：已批准（用户确认方案 A）

## 目标

访问一个特殊 URL，输入固定密码，即可在本机执行
`./deploy-h196_3.sh deploy --frontend --force`，免去 SSH 登录手工敲命令。

## 关键环境事实（设计约束来源）

- 后端 = FastAPI，systemd 单元 `lnrs-backend.service`（User=dzy，监听 127.0.0.1:8610，
  前端 dist 由 FastAPI 挂载在 `/web/...`，业务 API 在 `/api/v1` 前缀下）。
- **本机即 h196_3 部署机**（repo 在 `/home/dzy/wk/lnrs`，服务 active）。
- dzy 拥有 `NOPASSWD: ALL` 免密 sudo；`lnrs-backend` 单元 PATH 已含 uv / node24。
- `deploy` 子命令耗时数分钟，且流程末端会 `systemctl stop` 后端自身 → 触发必须异步，
  且子进程必须**脱离后端 cgroup**（systemd 默认 `KillMode=control-group` 会连
  同一 cgroup 的后端子进程一起杀掉）。
- SOCKS5 外网通道为临时隧道（127.0.0.1:1080，30 分钟自动关），`net-on` 函数定义在
  `/etc/profile.d/socks5-tunnel.sh`（login shell 加载，`export -f` 导出）。
- 环境文件 `backend/env/.env.h196_3` 提交在 git（项目既有约定，已含多个密钥）；
  配置经 pydantic `Settings` 从 `.env.{ENVIRONMENT}` 加载。
- 全局异常处理器会把 `HTTPException` 包成 `ErrorResponse{code,msg,data,status_code,success}`。

## 方案（已选 A）

在 lnrs 后端内新增独立 ops 路由模块 + 自包含 HTML 页面；固定密码鉴权，不走 JWT。
（备选 B「独立小服务」多养一个进程收益小；备选 C「密码放 URL」泄露风险大，均否决。）

### 1. URL 与鉴权

- 页面：`GET /ops/<slug>`，slug 为随机 8 字符（`OPS_DEPLOY_SLUG`），路径不可枚举。
  返回自包含 HTML（内联 CSS/JS，零外部依赖，不依赖前端构建）。
- 触发：`POST /ops/<slug>/run`，JSON `{password}`，`hmac.compare_digest` 常量时间比对；
  错误 → 403（slug 错误与功能关闭一律 404，不泄露面板存在性），记录来源 IP。
- 状态：`POST /ops/<slug>/status`，JSON `{password}`，返回
  `{state: idle|running|succeeded|failed|unknown, started_at, exit_code, tail[300行]}`。
- 限流（fastapi_limiter，项目已在用）：run 5 次/10s；status 30 次/10s；页面 30 次/60s。
- 密码 `OPS_DEPLOY_PASSWORD` 写入 `.env.h196_3`（已批准：16 位随机值）；
  密码或 slug 任一为空 → 全部路由 404（功能关闭）。

### 2. 执行模型（核心）

触发时**不直接 fork 子进程**，而是用 `sudo -n systemd-run` 起一个瞬态 oneshot 单元
`lnrs-web-deploy`（独立 cgroup，位于 system.slice）：

```
sudo -n systemd-run --unit=lnrs-web-deploy --description="lnrs web deploy (panel)" \
  -p Type=oneshot -p User=dzy -p Group=dzy \
  -p WorkingDirectory=/home/dzy/wk/lnrs \
  -p Environment=HOME=/home/dzy \
  -p Environment=PATH=<当前后端 PATH> \
  bash -c 'source /etc/profile.d/socks5-tunnel.sh 2>/dev/null; \
           net-on >/dev/null 2>&1 || true; \
           exec bash <script> deploy --frontend --force >> <log> 2>&1'
```

- wrapper 先 `source` profile.d 并调用 `net-on` 预热 SOCKS5 隧道（脚本自身的
  `proxy_probe` 仍会兜底校验），再 `exec` 部署脚本（单元主进程=脚本，退出码即部署结果）。
- 单元**不加 --collect**：结束后保持 inactive 可查（`Result` / `ExecMainStatus` /
  `ActiveEnterTimestamp`），重启机器后瞬态单元消失 → 自然回到 idle。
- 日志：重定向追加到 `backend/.run/web-deploy.log`（每次触发前由后端截断；
  文件属主 dzy，status 端可直接读）。
- 并发：触发前 `systemctl is-active lnrs-web-deploy` == active → 409。
- 触发前先 `systemctl reset-failed lnrs-web-deploy || true`（清理上次失败态，
  保证同名瞬态单元可再次 systemd-run）。
- 状态查询（status 端点）= 每次 3 个 `sudo -n systemctl` 只读调用（免密，毫秒级）。
- 部署流程末端 `systemctl stop lnrs-backend` 只杀后端自身 cgroup，
  `lnrs-web-deploy` 单元不受影响；HTTP 响应在 systemd-run 返回后立即发出
  （~100ms），远早于脚本停服时刻，不会丢响应。

### 3. 页面行为

- 密码框 + 「刷新状态」+「开始部署」两个按钮；展示将要执行的命令。
- 触发成功后每 3s 轮询 status；网络不可达（后端重启中）显示「后端重启中，请稍候」
  并继续重试（自触发起上限 10 分钟）；终态（succeeded/failed/unknown）停止轮询。
- 状态区：state 徽标 + started_at + exit_code；`<pre>` 展示日志尾 300 行。
- 密码只存页面内存，刷新即失效；错误提示读响应 JSON 的 `msg` 字段。

### 4. 代码落点

- 新建 `backend/app/api/v1/module_ops/`（`__init__.py` 汇总 + `deploy.py` 单文件模块，
  无 ORM，不套 controller/service 空壳拆分）。
- `backend/app/scripts/init_app.py:register_routers` 注册 `ops_router`
  （独立于 `/api/v1` 业务前缀；路由 `include_in_schema=False` 不进 Swagger）。
- `backend/app/config/setting.py` 新增 3 个字段：`OPS_DEPLOY_PASSWORD` / `OPS_DEPLOY_SLUG` /
  `OPS_DEPLOY_SCRIPT`（默认 `/home/dzy/wk/lnrs/deploy-h196_3.sh`）。
- 命令参数 `deploy --frontend --force` 按要求写死在模块常量里。
- 新增 `scripts/web-deploy-dummy.sh`（dev 环境用的无害假部署脚本，2s 后 exit 0）。

### 5. 配置值

- `.env.h196_3`（入库）：`OPS_DEPLOY_PASSWORD="JrhWEk231yPQ-ZTy"`、
  `OPS_DEPLOY_SLUG="TbnQz0L-"` → 访问地址 `http://<h196_3>:8610/ops/TbnQz0L-`。
- `.env.dev`（gitignore，仅本机）：测试密码 + `OPS_DEPLOY_SCRIPT` 指向 dummy 脚本，
  保证 dev 触发不碰真实服务。

### 6. 安全边界（如实说明）

- 密码随 env 文件在 git 中（与项目现有密钥管理一致）；纵深防御 = 随机 slug
  + 限流 + 内网可达；不做 IP 白名单（以后要加一行中间件即可）。
- 密码失败/部署成功均写后端日志（含来源 IP），密码本身不落日志。
- 该端点等价于「持有密码者可远程重启后端并拉取 main 部署」，权限与手工执行脚本相同。

### 7. 测试与验收

1. 单元测试（pytest，不依赖 DB）：状态解析（active→running / unknown→idle /
   inactive+success+0→succeeded / 非零→failed / 无退出码→unknown）、slug/密码校验
   （404/403）、日志尾截取、systemd-run 命令构造。
2. TestClient 端点测试：功能关闭 404；页面 200 HTML；错密码 403；
   正确密码触发 202（mock 掉 systemd-run）；status 返回结构。
3. dev 活体验证（:8001，dummy 脚本）：页面、403、触发 → 真实走一遍
   systemd-run 单元 → 轮询到 succeeded → 日志正确。
4. h196_3 真实 E2E：push → `./deploy-h196_3.sh deploy --frontend --force` 部署新代码 →
   浏览器/curl 走完整触发-轮询-完成流程 → 服务探活 200。

### 8. 已知取舍

- 部署期间（约 1-2 分钟）后端重启，status 轮询会短暂连接失败，页面按「重启中」处理。
- 若 SOCKS5 隧道过期且 `net-on` 启动失败，脚本会在代理探测处 die，日志给出明确指引。
- 建议先把本功能 push 到 main 再使用（脚本 `pull --rebase --autostash` 会保住
  未提交改动，端点不会丢，但 push 后最稳）。
