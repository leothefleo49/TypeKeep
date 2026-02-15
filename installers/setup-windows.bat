@echo off
setlocal enabledelayedexpansion
title TypeKeep Installer
color 0B

echo.
echo  ============================================================
echo       _____ TypeKeep — All-in-One Installer (Windows) _____
echo  ============================================================
echo.
echo   This will install:
echo     1. TypeKeep          — Input logger, clipboard manager ^& macros
echo     2. TypeKeep Companion — Cross-device sync app
echo.
echo   Both apps will be linked automatically.
echo.

:: ── Determine install directory ────────────────────────────────
set "INSTALL_DIR=%LOCALAPPDATA%\TypeKeep"
echo   Install location: %INSTALL_DIR%
echo.

set /p CONFIRM="  Proceed with installation? [Y/n] "
if /i "%CONFIRM%"=="n" (
    echo   Installation cancelled.
    pause
    exit /b 0
)

echo.
echo  [1/5] Creating install directory...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
if not exist "%INSTALL_DIR%\data" mkdir "%INSTALL_DIR%\data"

:: ── Copy files from the bundle ─────────────────────────────────
echo  [2/5] Installing TypeKeep...
set "BUNDLE_DIR=%~dp0"

:: Copy TypeKeep main executable
if exist "%BUNDLE_DIR%TypeKeep.exe" (
    copy /y "%BUNDLE_DIR%TypeKeep.exe" "%INSTALL_DIR%\TypeKeep.exe" >nul
    echo        TypeKeep.exe installed.
) else (
    echo   ERROR: TypeKeep.exe not found in the installer bundle.
    echo   Make sure you extracted the full zip before running setup.
    pause
    exit /b 1
)

:: Copy TypeKeep Companion executable
if exist "%BUNDLE_DIR%TypeKeep-Companion.exe" (
    copy /y "%BUNDLE_DIR%TypeKeep-Companion.exe" "%INSTALL_DIR%\TypeKeep-Companion.exe" >nul
    echo        TypeKeep-Companion.exe installed.
) else (
    echo   WARNING: TypeKeep-Companion.exe not found. Companion will not be installed.
)

:: ── Auto-link: write shared config ─────────────────────────────
echo  [3/5] Linking TypeKeep ^& Companion...
(
    echo {
    echo   "typekeep_host": "127.0.0.1",
    echo   "typekeep_port": 7700,
    echo   "companion_installed": true,
    echo   "install_dir": "%INSTALL_DIR:\=\\%",
    echo   "auto_start_typekeep": true
    echo }
) > "%INSTALL_DIR%\data\link.json"
echo        Apps linked via shared config.

:: ── Create shortcuts ───────────────────────────────────────────
echo  [4/5] Creating shortcuts...

:: Desktop shortcut for TypeKeep
powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; ^
   $sc = $ws.CreateShortcut('%USERPROFILE%\Desktop\TypeKeep.lnk'); ^
   $sc.TargetPath = '%INSTALL_DIR%\TypeKeep.exe'; ^
   $sc.WorkingDirectory = '%INSTALL_DIR%'; ^
   $sc.Description = 'TypeKeep — Input Logger ^& Clipboard Manager'; ^
   $sc.Save()"
echo        Desktop shortcut: TypeKeep

:: Desktop shortcut for Companion
if exist "%INSTALL_DIR%\TypeKeep-Companion.exe" (
    powershell -NoProfile -Command ^
      "$ws = New-Object -ComObject WScript.Shell; ^
       $sc = $ws.CreateShortcut('%USERPROFILE%\Desktop\TypeKeep Companion.lnk'); ^
       $sc.TargetPath = '%INSTALL_DIR%\TypeKeep-Companion.exe'; ^
       $sc.WorkingDirectory = '%INSTALL_DIR%'; ^
       $sc.Description = 'TypeKeep Companion — Cross-device Sync'; ^
       $sc.Save()"
    echo        Desktop shortcut: TypeKeep Companion
)

:: Start Menu shortcuts
set "STARTMENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs\TypeKeep"
if not exist "%STARTMENU%" mkdir "%STARTMENU%"

powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; ^
   $sc = $ws.CreateShortcut('%STARTMENU%\TypeKeep.lnk'); ^
   $sc.TargetPath = '%INSTALL_DIR%\TypeKeep.exe'; ^
   $sc.WorkingDirectory = '%INSTALL_DIR%'; ^
   $sc.Save()"

if exist "%INSTALL_DIR%\TypeKeep-Companion.exe" (
    powershell -NoProfile -Command ^
      "$ws = New-Object -ComObject WScript.Shell; ^
       $sc = $ws.CreateShortcut('%STARTMENU%\TypeKeep Companion.lnk'); ^
       $sc.TargetPath = '%INSTALL_DIR%\TypeKeep-Companion.exe'; ^
       $sc.WorkingDirectory = '%INSTALL_DIR%'; ^
       $sc.Save()"
)

:: Create uninstaller
(
    echo @echo off
    echo title TypeKeep Uninstaller
    echo echo Removing TypeKeep...
    echo.
    echo :: Remove auto-start
    echo reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "TypeKeep" /f 2^>nul
    echo.
    echo :: Remove shortcuts
    echo del /f "%%USERPROFILE%%\Desktop\TypeKeep.lnk" 2^>nul
    echo del /f "%%USERPROFILE%%\Desktop\TypeKeep Companion.lnk" 2^>nul
    echo rmdir /s /q "%%APPDATA%%\Microsoft\Windows\Start Menu\Programs\TypeKeep" 2^>nul
    echo.
    echo :: Remove install directory (keep data)
    echo echo.
    echo set /p KEEPDATA="Keep your data (typing history, config)? [Y/n] "
    echo if /i "%%KEEPDATA%%"=="n" (
    echo     rmdir /s /q "%INSTALL_DIR%"
    echo ^) else (
    echo     del /f "%INSTALL_DIR%\TypeKeep.exe" 2^>nul
    echo     del /f "%INSTALL_DIR%\TypeKeep-Companion.exe" 2^>nul
    echo     echo Data kept in %INSTALL_DIR%\data
    echo ^)
    echo echo.
    echo echo TypeKeep uninstalled.
    echo pause
) > "%INSTALL_DIR%\uninstall.bat"
echo        Uninstaller created.

:: ── Register auto-start ────────────────────────────────────────
echo  [5/5] Registering auto-start...
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "TypeKeep" /t REG_SZ /d "\"%INSTALL_DIR%\TypeKeep.exe\" --background" /f >nul 2>&1
echo        TypeKeep will start automatically on login.

:: ── Done ───────────────────────────────────────────────────────
echo.
echo  ============================================================
echo       Installation complete!
echo  ============================================================
echo.
echo   TypeKeep:           %INSTALL_DIR%\TypeKeep.exe
echo   TypeKeep Companion: %INSTALL_DIR%\TypeKeep-Companion.exe
echo   Dashboard:          http://127.0.0.1:7700
echo   Data:               %INSTALL_DIR%\data\
echo.
echo   Shortcuts added to Desktop and Start Menu.
echo   TypeKeep will auto-start on login.
echo.
echo   To uninstall: run %INSTALL_DIR%\uninstall.bat
echo.

set /p LAUNCH="  Launch TypeKeep now? [Y/n] "
if /i not "%LAUNCH%"=="n" (
    echo   Starting TypeKeep...
    start "" "%INSTALL_DIR%\TypeKeep.exe"
    timeout /t 3 /nobreak >nul
    start "" "%INSTALL_DIR%\TypeKeep-Companion.exe"
    echo   Both apps launched!
)

echo.
pause
