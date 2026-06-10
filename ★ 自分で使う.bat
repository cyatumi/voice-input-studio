@echo off
rem === Voice Input Studio を自分用に起動する ===
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" goto noenv
start "" ".venv\Scripts\pythonw.exe" -m voice_input
exit /b 0

:noenv
chcp 65001 >nul
echo.
echo アプリの本体（.venv）が見つかりませんでした。
echo フォルダを移動・コピーした直後はこの状態になることがあります。
echo Claude に「自分で使う.bat が動かない」と伝えてください。
echo.
pause
