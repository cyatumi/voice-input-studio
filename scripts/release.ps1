# =============================================================================
#  Voice Input Studio — リリース作成スクリプト
# -----------------------------------------------------------------------------
#  使い方:
#     scripts\release.ps1 -Version 1.5.1 -Notes "バグ修正と高速化"
#
#  やること:
#     1. ソースのバージョンを書き換える (__init__.py / installer.iss)
#     2. .exe をビルド (PyInstaller --onefile)
#     3. release\ に配布用ZIP・更新用EXE・version.json を作成
#
#  作成物を Dropbox にアップロードすれば配布・自動更新ができます (下に手順)。
# =============================================================================
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$Notes = ""
)
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".venv")) {
    Write-Host "先に scripts\run_dev.ps1 を実行して .venv を作成してください。" -ForegroundColor Red
    exit 1
}

# --- 1. バージョンを書き換え -------------------------------------------------
Write-Host "[1/4] バージョンを v$Version に設定..." -ForegroundColor Cyan

$initFile = "voice_input\__init__.py"
(Get-Content $initFile -Raw) `
    -replace '__version__\s*=\s*"[^"]*"', "__version__ = `"$Version`"" |
    Set-Content $initFile -Encoding utf8 -NoNewline

$issFile = "scripts\installer.iss"
if (Test-Path $issFile) {
    (Get-Content $issFile -Raw) `
        -replace '#define MyAppVersion "[^"]*"', "#define MyAppVersion `"$Version`"" |
        Set-Content $issFile -Encoding utf8
}

# --- 2. ビルド ---------------------------------------------------------------
Write-Host "[2/4] .exe をビルド中 (数分かかります)..." -ForegroundColor Cyan
. ".\.venv\Scripts\Activate.ps1"
python scripts\make_icon.py
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist, "VoiceInputStudio.spec"

$iconArg = @()
if (Test-Path "assets\app.ico") { $iconArg = @("--icon", "assets\app.ico") }

pyinstaller `
    --name VoiceInputStudio `
    --windowed `
    --onefile `
    --noconsole `
    --add-data "assets;assets" `
    --collect-submodules PySide6 `
    --hidden-import google.generativeai `
    @iconArg `
    voice_input\__main__.py

if (-not (Test-Path "dist\VoiceInputStudio.exe")) {
    Write-Host "[失敗] .exe が生成されませんでした" -ForegroundColor Red
    exit 1
}

# --- 3. release フォルダを作成 ----------------------------------------------
Write-Host "[3/4] 配布物を release\ に作成..." -ForegroundColor Cyan
$rel = "release"
New-Item -ItemType Directory -Force $rel | Out-Null

# 更新用の単体EXE (Dropbox に固定パスで上書きアップロードする)
Copy-Item "dist\VoiceInputStudio.exe" "$rel\VoiceInputStudio.exe" -Force

# 初回配布用ZIP (相手はこれを解凍 → 中の .exe を実行 / ガイド同梱)
$zip = "$rel\VoiceInputStudio-v$Version.zip"
Remove-Item -Force -ErrorAction SilentlyContinue $zip
$zipItems = @("dist\VoiceInputStudio.exe")
$guide = "$rel\はじめにお読みください.txt"
if (Test-Path $guide) { $zipItems += $guide }
Compress-Archive -Path $zipItems -DestinationPath $zip -Force

# --- 4. version.json を生成 --------------------------------------------------
# exe_url は「更新用EXE の Dropbox 直リンク(?dl=1)」。一度決めたら毎回同じ。
# scripts\release.local.json に { "exe_url": "..." } を置いておくと自動で埋まる。
$exeUrl = "<<ここに VoiceInputStudio.exe の Dropbox 直リンク(?dl=1)を貼る>>"
$cfgFile = "scripts\release.local.json"
if (Test-Path $cfgFile) {
    try {
        $cfg = Get-Content $cfgFile -Raw | ConvertFrom-Json
        if ($cfg.exe_url) { $exeUrl = $cfg.exe_url }
    } catch {}
}

$manifest = [ordered]@{
    version = $Version
    exe_url = $exeUrl
    notes   = $Notes
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content "$rel\version.json" -Encoding utf8

Write-Host ""
Write-Host "==================== 完了 ====================" -ForegroundColor Green
Write-Host " 配布用ZIP   : $rel\VoiceInputStudio-v$Version.zip"
Write-Host " 更新用EXE   : $rel\VoiceInputStudio.exe"
Write-Host " マニフェスト : $rel\version.json"
Write-Host ""
Write-Host " 次の手順:" -ForegroundColor Yellow
Write-Host "  1. Dropbox の固定フォルダに VoiceInputStudio.exe を『上書き』アップロード"
Write-Host "  2. version.json も同じフォルダに『上書き』アップロード"
Write-Host "     (どちらも共有リンクは変わらないので、相手のアプリが自動で新版を検知)"
Write-Host "  3. 初回だけ: 相手に VoiceInputStudio-v$Version.zip を渡す"
Write-Host "=============================================="
