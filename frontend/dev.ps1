#requires -Version 7.0
<#
.SYNOPSIS
    Frontend dev server launcher.

.DESCRIPTION
    进入 frontend/web 目录，启动 Vite 开发服。
    等价于:
        cd frontend/web
        pnpm dev

    用法(在 frontend 目录下):
        pwsh -NoProfile -File .\dev.ps1
        pwsh -NoProfile -File .\dev.ps1 -Force   # 清缓存强启 (pnpm dev:force)

.NOTES
    目标平台: Windows (PowerShell 7+)
#>

[CmdletBinding()]
param(
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$WebDir    = Join-Path $ScriptDir 'web'

if (-not (Test-Path -LiteralPath $WebDir)) {
    Write-Error "frontend/web not found: $WebDir"
    exit 1
}

# 检查 pnpm 是否在 PATH
$pnpm = Get-Command pnpm -ErrorAction SilentlyContinue
if (-not $pnpm) {
    Write-Error "pnpm not found in PATH. 请先安装: npm i -g pnpm"
    exit 1
}

Push-Location $WebDir
try {
    if ($Force) {
        & $pnpm.Source dev:force
    } else {
        & $pnpm.Source dev
    }
} finally {
    Pop-Location
}