# Build a standalone Windows .exe with PyInstaller.
# Output: dist\VoiceInputStudio.exe
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".venv")) {
    Write-Host "Run scripts\run_dev.ps1 first to bootstrap the venv." -ForegroundColor Red
    exit 1
}

. ".\.venv\Scripts\Activate.ps1"

Write-Host "[build] Generating app icon..." -ForegroundColor Cyan
python scripts\make_icon.py

Write-Host "[build] Cleaning previous build..." -ForegroundColor Cyan
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist, "VoiceInputStudio.spec"

$iconArg = @()
if (Test-Path "assets\app.ico") {
    $iconArg = @("--icon", "assets\app.ico")
}

# アプリが使う Qt モジュールは QtCore / QtGui / QtWidgets の3つだけ。
# PySide6 全体を収集すると QtWebEngine(Chromium) 等で約290MBに肥大するため、
# 自動収集はやめ、未使用の巨大モジュールを明示除外してサイズを削減する。
$excludeQt = @(
    "PySide6.QtWebEngineCore","PySide6.QtWebEngineWidgets","PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel","PySide6.QtWebSockets","PySide6.QtWebView",
    "PySide6.QtQml","PySide6.QtQmlModels","PySide6.QtQuick","PySide6.QtQuick3D",
    "PySide6.QtQuickWidgets","PySide6.QtQuickControls2",
    "PySide6.QtMultimedia","PySide6.QtMultimediaWidgets","PySide6.QtSpatialAudio",
    "PySide6.QtPdf","PySide6.QtPdfWidgets",
    "PySide6.QtCharts","PySide6.QtDataVisualization","PySide6.QtGraphs",
    "PySide6.Qt3DCore","PySide6.Qt3DRender","PySide6.Qt3DInput","PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation","PySide6.Qt3DExtras",
    "PySide6.QtDesigner","PySide6.QtUiTools","PySide6.QtHelp","PySide6.QtTest",
    "PySide6.QtSql","PySide6.QtNetworkAuth","PySide6.QtRemoteObjects",
    "PySide6.QtBluetooth","PySide6.QtNfc","PySide6.QtPositioning","PySide6.QtLocation",
    "PySide6.QtSerialPort","PySide6.QtSerialBus","PySide6.QtSensors",
    "PySide6.QtScxml","PySide6.QtStateMachine","PySide6.QtTextToSpeech"
) | ForEach-Object { @("--exclude-module", $_) }

Write-Host "[build] Running PyInstaller..." -ForegroundColor Cyan
pyinstaller `
    --name VoiceInputStudio `
    --windowed `
    --onefile `
    --noconsole `
    --add-data "assets;assets" `
    --hidden-import google.generativeai `
    @excludeQt `
    @iconArg `
    voice_input\__main__.py

if (Test-Path "dist\VoiceInputStudio.exe") {
    Write-Host "[done] dist\VoiceInputStudio.exe" -ForegroundColor Green
} else {
    Write-Host "[fail] Build did not produce an exe" -ForegroundColor Red
    exit 1
}
