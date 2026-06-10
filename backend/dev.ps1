#requires -Version 7.0
<#
.SYNOPSIS
    FastAPI 后端开发服启动/停止/状态 (PowerShell 7.6+).

.DESCRIPTION
    - 启动: 在新窗口后台运行 `uv run main.py run --env=dev`,将 uv 进程 PID 写入
            backend/.run/dev.pid(同时记录 uvicorn 子进程 PID 便于强杀)。
    - 停止: 按 PID 文件结束进程(uv + uvicorn),支持强制 kill。
    - 状态: 显示 PID 文件中的进程是否存在、占用端口、命令等。

    用法(在 backend 目录下):
        pwsh -NoProfile -File .\dev.ps1 start
        pwsh -NoProfile -File .\dev.ps1 stop
        pwsh -NoProfile -File .\dev.ps1 status
        pwsh -NoProfile -File .\dev.ps1 restart

    可选参数:
        -NoWindow    启动时不弹新控制台窗口(用于 CI/远程)
        -Force       stop 时强制 Kill(包括子进程)

.NOTES
    目标平台: Windows
    测试版本: PowerShell 7.6
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'stop', 'status', 'restart')]
    [string]$Action = 'status',

    [switch]$NoWindow,

    [switch]$Force
)

$ErrorActionPreference = 'Stop'

# ---------- 路径 ----------
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Split-Path -Parent $ScriptDir
$EnvFile   = Join-Path $ScriptDir 'env\.env.dev'
$RunDir    = Join-Path $ScriptDir '.run'
$PidFile   = Join-Path $RunDir 'dev.pid'
$LogFile    = Join-Path $RunDir 'dev.log'
$ErrLogFile = Join-Path $RunDir 'dev.err.log'

# ---------- 颜色 ----------
if ($Host.UI.SupportsVirtualTerminal -or $env:WT_SESSION -or $env:TERM) {
    $cRed    = "`e[0;31m"
    $cGreen  = "`e[0;32m"
    $cYellow = "`e[33m"
    $cCyan   = "`e[36m"
    $cBlue   = "`e[34m"
    $cReset  = "`e[0m"
} else {
    $cRed = $cGreen = $cYellow = $cCyan = $cBlue = $cReset = ''
}

function Write-Info    { param($m) Write-Host "${cGreen}OK${cReset}  $m" }
function Write-Warn    { param($m) Write-Host "${cYellow}WARN${cReset} $m" }
function Write-Err     { param($m) Write-Host "${cRed}ERR${cReset} $m" }
function Write-Section { param($m) Write-Host "${cCyan}== $m ==${cReset}" }

# ---------- 解析 .env.dev ----------
# 兼容以下写法:
#   KEY = "value"
#   KEY=value
#   KEY = value # comment
function Get-EnvValue {
    param([string]$Key, [string]$File)

    if (-not (Test-Path -LiteralPath $File)) {
        throw "env file not found: $File"
    }
    $line = Select-String -LiteralPath $File -Pattern "^\s*$([regex]::Escape($Key))\s*=" |
            Select-Object -First 1
    if (-not $line) { return $null }
    $raw = ($line.Line -split '=', 2)[1].Trim()
    # 去掉行内注释(只在 # 不在引号内时)
    $raw = $raw -replace '\s+#.*$', ''
    $raw = $raw.Trim()
    # 去引号
    if ($raw -match '^"(.*)"$') { $raw = $matches[1] }
    elseif ($raw -match "^'(.*)'$") { $raw = $matches[1] }
    return $raw
}

function Test-EnvReady {
    if (-not (Test-Path -LiteralPath $EnvFile)) {
        Write-Err "env file not found: $EnvFile"
        return $false
    }
    $need = 'DATABASE_HOST','DATABASE_PORT','DATABASE_USER','DATABASE_NAME'
    foreach ($k in $need) {
        $v = Get-EnvValue -Key $k -File $EnvFile
        if ([string]::IsNullOrWhiteSpace($v)) {
            Write-Err "Database configuration incomplete: $k is empty in $EnvFile"
            return $false
        }
    }
    return $true
}

# ---------- 进程工具 ----------
function Get-StoredPids {
    if (-not (Test-Path -LiteralPath $PidFile)) { return @() }
    try {
        $ids = Get-Content -LiteralPath $PidFile -ErrorAction Stop |
               ForEach-Object { $_.Trim() } |
               Where-Object { $_ -match '^\d+$' }
        return @($ids | ForEach-Object { [int]$_ })
    } catch {
        return @()
    }
}

function Save-Pids {
    param([int[]]$Pids)
    New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
    $Pids -join "`n" | Set-Content -LiteralPath $PidFile -Encoding utf8NoBOM
}

function Clear-Pids {
    if (Test-Path -LiteralPath $PidFile) {
        Remove-Item -LiteralPath $PidFile -Force
    }
}

function Test-PidAlive {
    param([int]$Pid)
    $p = Get-Process -Id $Pid -ErrorAction SilentlyContinue
    return [bool]$p
}

# 结束一组 PID 及其子进程(尽力而为)
function Stop-PidTree {
    param(
        [int[]]$Pids,
        [switch]$ForceKill
    )
    foreach ($pid in $Pids) {
        $p = Get-Process -Id $pid -ErrorAction SilentlyContinue
        if (-not $p) { continue }
        try {
            if ($ForceKill) {
                $p | Stop-Process -Force -ErrorAction Stop
            } else {
                $p | Stop-Process -ErrorAction Stop
            }
        } catch {
            Write-Warn "failed to stop pid $pid : $($_.Exception.Message)"
        }
    }
    # 等一下,让进程清理
    Start-Sleep -Milliseconds 500
}

# ---------- 动作: status ----------
function Invoke-Status {
    Write-Section "status"
    $pids = Get-StoredPids
    if ($pids.Count -eq 0) {
        Write-Warn "no pid file at $PidFile (server not managed by this script)"
        return
    }
    foreach ($p in $pids) {
        $proc = Get-Process -Id $p -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Info ("pid {0,-6} alive  {1}  {2}" -f $p, $proc.ProcessName, $proc.MainWindowTitle)
        } else {
            Write-Warn "pid $p  not alive (stale pid file?)"
        }
    }
    if (Test-Path -LiteralPath $LogFile) {
        Write-Host "  log: $LogFile"
    }
}

# ---------- 动作: stop ----------
function Invoke-Stop {
    Write-Section "stop"
    $pids = Get-StoredPids
    if ($pids.Count -eq 0) {
        Write-Warn "no pid file, nothing to stop"
        return
    }

    # 先发现还存活的 uvicorn/python 进程作为兜底(可能 PID 文件陈旧)
    $stale = $false
    foreach ($p in $pids) {
        if (-not (Test-PidAlive -Pid $p)) { $stale = $true }
    }
    if ($stale) {
        Write-Warn "pid file is stale; will also try to find uvicorn for this project"
    }

    $aliveCount = ($pids | Where-Object { Test-PidAlive -Pid $_ }).Count
    if ($aliveCount -eq 0 -and -not $Force) {
        Write-Warn "no live pid, removing stale pid file"
        Clear-Pids
        return
    }

    Stop-PidTree -Pids $pids -ForceKill:$Force

    # 二次确认:还活着的再强杀一次
    $stillAlive = $pids | Where-Object { Test-PidAlive -Pid $_ }
    if ($stillAlive) {
        if (-not $Force) {
            Write-Warn "still alive after graceful stop, retrying with -Force"
        }
        Stop-PidTree -Pids $stillAlive -ForceKill
    }

    # 最终检查
    $left = $pids | Where-Object { Test-PidAlive -Pid $_ }
    if ($left) {
        Write-Err "some processes refused to exit: $($left -join ', ')"
        return
    }
    Clear-Pids
    Write-Info "stopped"
}

# ---------- 动作: start ----------
function Invoke-Start {
    Write-Section "start"

    # 已运行?
    $pids = Get-StoredPids
    foreach ($p in $pids) {
        if (Test-PidAlive -Pid $p) {
            Write-Warn "already running (pid $p). Use 'restart' to relaunch."
            return
        }
    }
    Clear-Pids

    if (-not (Test-EnvReady)) { exit 1 }

    $host_ = Get-EnvValue -Key 'SERVER_HOST' -File $EnvFile
    $port  = Get-EnvValue -Key 'SERVER_PORT' -File $EnvFile
    if ([string]::IsNullOrWhiteSpace($host_)) { $host_ = '127.0.0.1' }
    if ([string]::IsNullOrWhiteSpace($port))  { $port  = '8000' }

    New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
    # 清空旧日志
    '' | Set-Content -LiteralPath $LogFile -Encoding utf8NoBOM
    '' | Set-Content -LiteralPath $ErrLogFile -Encoding utf8NoBOM

    Push-Location $ScriptDir
    try {
        $uv = Get-Command uv -ErrorAction SilentlyContinue
        if (-not $uv) {
            Write-Err "uv not found in PATH"
            exit 1
        }

        $args = @('run', 'main.py', 'run', '--env=dev')

        if ($NoWindow) {
            # 不弹窗,直接后台
            $proc = Start-Process -FilePath $uv.Source `
                                  -ArgumentList $args `
                                  -WorkingDirectory $ScriptDir `
                                  -RedirectStandardOutput $LogFile `
                                  -RedirectStandardError  $ErrLogFile `
                                  -WindowStyle Hidden `
                                  -PassThru
        } else {
            # 弹新控制台窗口,便于看实时日志
            $proc = Start-Process -FilePath $uv.Source `
                                  -ArgumentList $args `
                                  -WorkingDirectory $ScriptDir `
                                  -RedirectStandardOutput $LogFile `
                                  -RedirectStandardError  $ErrLogFile `
                                  -PassThru
        }

        # 记录 uv 进程 PID。等几秒,再尝试找 uvicorn 子 PID
        $pids = @($proc.Id)
        Start-Sleep -Seconds 2
        $child = Get-CimInstance Win32_Process -Filter "ParentProcessId=$($proc.Id)" -ErrorAction SilentlyContinue |
                 Where-Object { $_.Name -match '^(python|uvicorn)\.exe$' } |
                 Select-Object -First 1
        if ($child) {
            $pids += [int]$child.ProcessId
        }
        Save-Pids -Pids $pids

        Write-Info ("uv pid: {0}" -f $proc.Id)
        if ($child) { Write-Info ("child pid: {0} ({1})" -f $child.ProcessId, $child.Name) }
        Write-Info "log: $LogFile"
        Write-Info "url: http://${host_}:${port}/"
        Write-Info "use 'pwsh -File .\dev.ps1 stop' to stop"
    } finally {
        Pop-Location
    }
}

# ---------- 动作: restart ----------
function Invoke-Restart {
    Invoke-Stop
    Invoke-Start
}

# ---------- main ----------
switch ($Action) {
    'start'  { Invoke-Start  }
    'stop'   { Invoke-Stop   }
    'status' { Invoke-Status }
    'restart' { Invoke-Restart }
}
