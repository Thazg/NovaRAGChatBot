@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo [nova] Missing .venv. Follow README Quick start to install dependencies first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" "scripts\dev.py" %*
set "NOVA_EXIT=%ERRORLEVEL%"
if not "%NOVA_EXIT%"=="0" pause
exit /b %NOVA_EXIT%
