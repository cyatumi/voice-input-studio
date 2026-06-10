@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\publish_easy.ps1"
echo.
echo （このウィンドウは閉じて大丈夫です）
pause
