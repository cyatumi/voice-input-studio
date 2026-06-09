# Quick-start dev runner. Creates a venv on first run, then launches the app.
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".venv")) {
    Write-Host "[setup] Creating virtual environment..." -ForegroundColor Cyan
    python -m venv .venv
}

Write-Host "[setup] Activating venv..." -ForegroundColor Cyan
. ".\.venv\Scripts\Activate.ps1"

Write-Host "[setup] Installing requirements..." -ForegroundColor Cyan
pip install -q --upgrade pip
pip install -q -r requirements.txt

Write-Host "[run] Starting Voice Input Studio..." -ForegroundColor Green
python -m voice_input
