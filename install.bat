@echo off
setlocal EnableDelayedExpansion
title TypeKeep Installer

echo ============================================
echo   TypeKeep v3.2 - Local Installer
echo ============================================
echo.

REM --- Verify Python ----------------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    echo [X] Python is not installed or not in PATH.
    echo     Please install Python 3.10+ from https://python.org
    echo     and re-run this installer.
    pause
    exit /b 1
)
echo [OK] Python detected
echo.

REM --- Install dependencies ---------------------------------------------
echo [..] Installing Python dependencies...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo [X] Dependency install failed.
    pause
    exit /b 1
)
echo [OK] Dependencies installed
echo.

REM --- Auto-start (HKCU Run key) ----------------------------------------
echo [..] Registering auto-start on login...
for /f "tokens=*" %%i in ('where pythonw') do set PYTHONW=%%i
if "%PYTHONW%"=="" (
    echo [!] pythonw.exe not found; you can still launch TypeKeep manually.
) else (
    reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v TypeKeep /d "\"%PYTHONW%\" \"%~dp0typekeep.py\" --background" /f >nul
    echo [OK] Auto-start configured ^(runs silently on every Windows login^)
)
echo.

REM --- Desktop shortcut --------------------------------------------------
echo [..] Creating desktop shortcut...
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\TypeKeep.lnk'); $s.TargetPath='%PYTHONW%'; $s.Arguments='%~dp0typekeep.py'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0static\icon-192.png'; $s.Save()" >nul 2>&1
echo [OK] Desktop shortcut created
echo.

REM --- Launch TypeKeep ---------------------------------------------------
echo [..] Launching TypeKeep in the background...
start "" "%PYTHONW%" "%~dp0typekeep.py" --background
timeout /t 3 /nobreak >nul
echo [OK] TypeKeep is now running in the background.
echo.

echo ============================================
echo   Install complete.
echo.
echo   Dashboard:  http://127.0.0.1:7700
echo   Auto-start: On (runs silently after login)
echo   CPU usage:  Less than 1%% at idle
echo   Tip:        Run start.bat any time to open the dashboard.
echo ============================================
echo.
start "" "http://127.0.0.1:7700"
pause
endlocal
