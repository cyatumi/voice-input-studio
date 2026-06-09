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

Write-Host "[build] Running PyInstaller..." -ForegroundColor Cyan
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

if (Test-Path "dist\VoiceInputStudio.exe") {
    Write-Host "[done] dist\VoiceInputStudio.exe" -ForegroundColor Green
} else {
    Write-Host "[fail] Build did not produce an exe" -ForegroundColor Red
    exit 1
}
