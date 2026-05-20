@echo off
REM TypeKeep launcher - opens dashboard, starts background recorder if needed.
title TypeKeep
cd /d "%~dp0"

REM Use typekeep.py --open which already handles "running? open dashboard
REM : start background and open" intelligently, and falls back gracefully.
python typekeep.py --open
if errorlevel 1 (
    REM Fallback: detect existing port-7700 instance manually.
    netstat -an | findstr ":7700 " | findstr "LISTENING" >nul 2>&1
    if not errorlevel 1 (
        start "" "http://127.0.0.1:7700"
        exit /b 0
    )

    REM Last resort: launch silently with pythonw (no console window).
    start "" pythonw typekeep.py --background
    timeout /t 2 /nobreak >nul
    start "" "http://127.0.0.1:7700"
)
