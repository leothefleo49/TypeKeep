@echo off
echo ============================================
echo   TypeKeep - Installing dependencies
echo ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

pip install -r "%~dp0requirements.txt"

echo.
echo ============================================
echo   Done!  Run  start.bat  to launch TypeKeep.
echo ============================================
pause
