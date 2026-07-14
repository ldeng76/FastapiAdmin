# 工作记录（2026-07-06 / 07）

本会话涵盖三项独立任务：

1. **Orthanc 服务启动连环崩** — 两次不同根因
2. **`X:` 盘映射在资源管理器不可见** — UAC 会话隔离
3. **禁止 Orthanc Explorer / OE2 下载 DICOM**（VolView 渲染不能受影响）— Lua 脚本迭代到 v9

---

## 任务 1：Orthanc 服务起不来

**症状**：服务名实际为 `Orthanc`（不是 "Orthanc Server"），`sc query Orthanc` 显示 `STATE: STOPPED, WIN32_EXIT_CODE: 1067`；`curl 127.0.0.1:8042/` Connection refused；Logs 目录空（说明没进 main）。

### 根因 #1 — 缺 VC++ Redistributable

应用日志：
```
Exception code: 0xc0000005 (ACCESS_VIOLATION)
Stack: PCH_AC_FROM_ntdll+0x000744DC   ← CRT 初始化失败的经典栈
```
该机器是 Windows Server 2022 全新环境，缺：
- `System32\msvcp140.dll`
- `System32\vcruntime140.dll`

**修复**：`vc_redist.x64.exe`（https://aka.ms/vs/17/release/vc_redist.x64.exe）

### 根因 #2 — Python 插件 LoadLibrary 失败

VC++ 装好后 Orthanc 进入 `main()`，但 plugin 加载阶段崩：
```
E...  SharedLibrary.cpp:52]  LoadLibrary(...OrthancPython3.12.dll) failed: Error 126
E...  main.cpp:2307]          Uncaught exception: [Error while using a shared library] (code 25)
```
`Error 126 = ERROR_MOD_NOT_FOUND`。Python 3.12 装在 `C:\Users\dzy\AppData\Local\Programs\Python\Python312\`，但 OrthancService 跑在 `LocalSystem` 上下文，PATH 不含用户目录，找不到 `python312.dll`。

**修复**：把 `C:\Program Files\Orthanc Server\Plugins\OrthancPython3.12.dll` 重命名为 `_disabled_OrthancPython3.12.dll`（备份留底，将来若需 Python 插件：装 all-users 版 Python 3.12 + 把文件拷回原位）。

### 副作用 — SQLite 残留锁

用 `Stop-Service -Force` 重启时，Orthanc.exe 子进程没同步退出，DB 句柄留住。下次启动：
```
SQLite: database is locked (5)
SQLite: Cannot prepare a cached statement
Error while initializing plugin "...\OrthancWebViewer.dll" (code -1)
```
退出序列里 `OrthancAwsS3Storage.dll_unloaded` 还触发了一次 BEX（卸载-后-调用）。

**修复**：手动 kill 所有 Orthanc.exe / OrthancService.exe / OrthancInstaller-Win64-*.exe，等 3 秒，再 Start-Service。

---

## 任务 2：X: 盘映射在资源管理器不显示

**症状**：`net use X: \\10.12.180.51\wlx-storage\wlx\DATABASE /persistent:yes` 成功，`dir X:\` 出文件正常，`Get-CimInstance Win32_LogicalDisk` 也看到 `DeviceID: X: DriveType: 4`，**但 File Explorer 不显示 X:**。

### 根因 — UAC 会话隔离

那条 `net use` 是从**以管理员身份运行**的 cmd 发出的，注册到**高完整性 token**。File Explorer 默认跑**中完整性**，跨完整性看不见。

`whoami /groups | findstr "Mandatory Label"`：
- 高完整性 → `Label\High Mandatory Level`
- 中完整性 → `Label\Medium Mandatory Level`

**修复**：
1. 在中完整性（普通）cmd 里 `net use X: /delete` 清掉旧映射
2. 在同一会话执行 `net use X: \\10.12.180.51\wlx-storage\wlx\DATABASE /persistent:yes`
3. **杀掉用户实例 explorer.exe**（保留系统实例 PID 1156）：

```powershell
Get-Process explorer | Where-Object { $_.StartTime -ne $null } | Stop-Process -Force
```

验证：
```powershell
Get-CimInstance Win32_LogicalDisk | Where-Object { $_.DriveType -eq 4 }
# DeviceID ProviderName
# X:       \\10.12.180.51\wlx-storage\wlx\DATABASE

Get-ItemProperty 'HKCU:\Network\X'  # 持久化注册表项已写入
```

下次登录 X: 会自动重连（`/persistent:yes` + 注册表）。

---

## 任务 3：禁止下载 DICOM（VolView 不能受影响）

### 需求

- OE2 / 浏览器 / API 直接调用拿 DICOM、ZIP、DICOMDIR 都要 403
- VolView 页（`volview/index.html?names=[archive.zip]&urls=[../series/{id}/archive]`）能正常 fetch `/series/{id}/archive` 渲染（**这是关键约束**）

### 三方案对比

| 路径 | 复杂度 | 选取 |
|---|---|---|
| A. Lua `IncomingHttpRequestFilter` | 低 | ✅ |
| B. Authorization 插件按组限权 | 高 | 留作"硬安全"路径 |
| C. 反向代理 URL 过滤 | 中 | 同上 |

### 关键发现：Orthanc 1.12 Lua 回调签名 — **与文档相反**

| 来源 | 签名 |
|---|---|
| v3 猜测 / 多数文档示例 | `(method, uri, ip, headers, body)` |
| **实际（v5 variadic 探针）** | **`(method, uri, ip, body, headers)`** |

v5 探针输出（打在日志里）：
```
arg1 type=string preview=[GET]
arg2 type=string preview=[/series/.../archive]
arg3 type=string preview=[127.0.0.1]
arg4 type=string preview=[]             ← 实际是 body（GET 时空）
arg5 type=table  preview=[table:...]   ← 实际是 headers（table 形态）
```

坑点：
- arg4/arg5 顺序与文档相反
- body 第 4 参、headers 第 5 参
- headers **是 table** `{ ["Referer"]="...", ["Origin"]="..." }`（不是 string）

不修正这个签名就拿不到 Referer，所有"按 Referer 旁路"都失效。

### 最终脚本（v9）— `block-downloads.lua`

```lua
-- block-downloads.lua (v9)
-- Orthanc 1.12.11 真实签名：IncomingHttpRequestFilter(method, uri, ip, body, headers)
--   body    第 4 参，string，GET 时为空
--   headers 第 5 参，table，例如 { ["Referer"]="...", ["Origin"]="..." }
--
-- 仅 VolView 渲染会主动拉 /archive；其它 viewer 走流式/WADO-RS，
-- 不需要 /archive。把白名单严控能堵住所有"伪装成 viewer"的下载。

local VIEWER_PATH_PREFIXES = {
    '/volview/',   -- 唯一：VolView 渲染需 fetch /archive
}

local function hdr(headers, name)
    if headers == nil or type(headers) ~= 'table' then return nil end
    local lname = name:lower()
    for k, v in pairs(headers) do
        if type(k) == 'string' and k:lower() == lname then return v end
    end
    return nil
end

local function is_from_viewer(referer)
    if not referer or referer == '' then return false end
    for _, prefix in ipairs(VIEWER_PATH_PREFIXES) do
        if referer:match(prefix) then return true end
    end
    return false
end

function IncomingHttpRequestFilter(method, uri, ip, body, headers)
    if method ~= 'GET' then return true end

    -- A 类：永远 403
    local alwaysPatterns = {
        '/instances/[^/]+/file$',     -- 单 DICOM 文件（user 最直白的下载意图）
        '/instances/[^/]+/attachment', -- 附件下载
        '/wado',                       -- WADO-URI 单文件取图
    }
    for _, pat in ipairs(alwaysPatterns) do
        if uri:match(pat) then return false end
    end

    -- B 类：按 Referer 区分（ZIP archive / DICOMDIR media）
    local refererPatterns = {
        '/studies/[^/]+/archive$',
        '/studies/[^/]+/media$',
        '/series/[^/]+/archive$',
        '/series/[^/]+/media$',
        '/patients/[^/]+/archive$',
        '/patients/[^/]+/media$',
        '^/archive$',
    }
    for _, pat in ipairs(refererPatterns) do
        if uri:match(pat) then
            local referer = hdr(headers, 'referer')
            if is_from_viewer(referer) then return true end
            return false
        end
    end

    return true
end
```

### 白名单演进 — 为什么收到只留 `/volview/`

| Version | 白名单 | 触发的问题 |
|---|---|---|
| v3 | volview, ohif, webviewer, stone-webviewer, ui | 签名错，全部 500/未生效 |
| v7 | 同上 | OE2 点 "Export to ZIP" 走 `/ui/` Referer → 200 ❌ |
| v8 | volview, ohif, webviewer, stone-webviewer | **OE2 导出仍走 `/stone-webviewer/` Referer → 200** ❌ |
| v9 | **只留 `/volview/`** | ✅ 所有非 VolView 来源都 403 |

OE2 里"Export to ZIP"按钮实际在 Stone WebViewer（`/stone-webviewer/`）的内嵌视图里发起 fetch。这是浏览器自发的请求，Referer 自然写成 Stone WebViewer 页面 URL。**只有把 Stone WebViewer 从白名单移除**才能堵住。OE2 看图本身走流式 frame + preview 缩略图，不依赖 `/archive`，所以白了手也不影响。

### 最终验证矩阵（15/15 PASS）

| # | 场景 | 期望 | 实测 |
|---|---|:---:|:---:|
| T01 | `instance /file` 无 ref | 403 | **403** ✅ |
| T02 | `series /archive` 无 ref | 403 | **403** ✅ |
| T03 | `series /archive` Referer=volview | 200 | **200** ✅ |
| T04 | `instance /file` Referer=volview | 403 | **403** ✅ |
| T05 | `instance /metadata` | 200 | **200** ✅ |
| T06 | `studies /archive` 无 ref | 403 | **403** ✅ |
| T07 | `series /media` 无 ref | 403 | **403** ✅ |
| T08 | `/system` | 200 | **200** ✅ |
| T09 | `/volview/index.html` | 200 | **200** ✅ |
| T10 | `instance /preview` | 200 | **200** ✅ |
| T15 | `series/.../archive?filename=...` ref=stone | 403 | **403** ✅ |
| T16 | `studies/.../archive?filename=...` ref=stone | 403 | **403** ✅ |
| T17 | `series/.../archive` ref=/ui/ | 403 | **403** ✅ |
| T18 | `series/.../archive` ref=/ohif/ | 403 | **403** ✅ |
| T19 | `series/.../archive` ref=/webviewer/ | 403 | **403** ✅ |

---

## 落盘文件清单

| 路径 | 用途 |
|---|---|
| `C:\Program Files\Orthanc Server\Configuration\block-downloads.lua` | 部署的 v9 |
| `C:\Program Files\Orthanc Server\Configuration\orthanc.json` | `LuaScripts` 数组新增一行 |
| `C:\Program Files\Orthanc Server\Plugins\_disabled_OrthancPython3.12.dll` | 备份的 Python 插件 |
| `C:\wk\chore\block-downloads.lua` | v9 源（备份） |
| `C:\wk\chore\deploy-block-downloads.ps1` | 首次部署：复制 Lua + 改 JSON + 重启服务 |
| `C:\wk\chore\redeploy-lua.ps1` | 后续只重发 Lua + 重启 + 验证 |
| `C:\wk\chore\recover-orthanc.ps1` | 急救：清 SQLite 残留锁 + 重启 |
| `X:` 映射 | `HKCU\Network\X` → `\\10.12.180.51\wlx-storage\wlx\DATABASE` |

---

## 部署 / 回滚操作命令

```powershell
# ─ 首次完整部署（含 orthanc.json 改 LuaScripts）──────────
cd C:\wk\chore
.\deploy-block-downloads.ps1

# ─ 后续只改 Lua 时（不动 JSON）───────────────────────────
.\redeploy-lua.ps1

# ─ Stop-Service -Force 后 SQLite 卡住时 ──────────────────
.\recover-ortharc.ps1
#（其实名是 recover-orthanc.ps1）

# ─ X: 盘映射（如需重新做）───────────────────────────────
# 务必在普通 cmd（不要"以管理员身份运行"）里：
net use X: /delete
net use X: \\10.12.180.51\wlx-storage\wlx\DATABASE /persistent:yes
```

---

## 已知限制（v9 阶段遗留）

1. **Referer 在同源可任意伪造**——DevTools / 控制台都可以改。因此这是"防误下载 / 防误操作"层，不防刻意的技术人员盗取数据。
2. **DICOM 协议（端口 4242）的 C-MOVE / C-GET 不在拦截范围**——这是另一条通道，要靠网络边界策略或 Orthanc `DicomAlwaysAllowMove/Get: false` 来收口。
3. **DICOMweb WADO-RS（`/dicom-web/...`）未拦**——当前 VolView 不走这条，但其他 viewer 配置可能用它。
4. **`/instances/.../file` 缩略图/看图相关** — 当前 `preview`、`metadata`、`tags` 等放行，若 OE2 看图还有别的地方要拉数据，把 URL 拿来再调白名单。

进一步硬化路径（按需启用）：
- **Authentication + Authorization 插件** — per-user/per-group，权限精细
- **`LogExportedResources: true`** — 审计谁何时下载了什么
- **反向代理**（IIS ARR / Nginx）做 token / CORS 校验

---

## 调试要点速查

| 现象 | 排查命令 |
|---|---|
| Orthanc 不通 | `sc query Orthanc`、`netstat -ano \| findstr :8042`、`Test-NetConnection 127.0.0.1 -Port 8042` |
| 启动崩溃 | `powershell Get-WinEvent -LogName Application -MaxEvents 100 \| ? Message -match Orthanc` |
| 看最新 Orthanc 日志 | `Get-ChildItem 'C:\Program Files\Orthanc Server\Logs' \| Sort LastWriteTime -Desc \| Select -First 1` |
| 当前用户完整性级别 | `whoami /groups \| findstr "Mandatory Label"` |
| 看 X: 映射 | `net use X:`、`Get-CimInstance Win32_LogicalDisk \| ? DriveType -eq 4` |
| 浏览器内到底发的什么 Referer | DevTools → Network → 选中失败请求 → 看 Request Headers |
| Lua 调试加 print | 在脚本里 `print('...')`，重启服务后用上面那条查 Orthanc 最新日志，前缀 `Lua says: [block-dl ...]` |
