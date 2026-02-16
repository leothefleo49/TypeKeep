; ─────────────────────────────────────────────────────────────────
;  TypeKeep — NSIS Installer (Windows)
;  Builds a single Setup.exe that installs both TypeKeep +
;  TypeKeep Companion, links them, creates shortcuts, auto-start,
;  and an uninstaller with Add/Remove Programs entry.
; ─────────────────────────────────────────────────────────────────

!include "MUI2.nsh"
!include "FileFunc.nsh"

; ── General ──────────────────────────────────────────────────────
Name "TypeKeep"
OutFile "TypeKeep-Setup-Windows.exe"
InstallDir "$LOCALAPPDATA\TypeKeep"
InstallDirRegKey HKCU "Software\TypeKeep" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma

; ── Version info ─────────────────────────────────────────────────
!define PRODUCT_NAME "TypeKeep"
!define PRODUCT_VERSION "3.1.0"
!define PRODUCT_PUBLISHER "leothefleo49"
!define PRODUCT_WEB_SITE "https://github.com/leothefleo49/TypeKeep"

VIProductVersion "3.1.0.0"
VIAddVersionKey "ProductName" "${PRODUCT_NAME}"
VIAddVersionKey "ProductVersion" "${PRODUCT_VERSION}"
VIAddVersionKey "FileDescription" "TypeKeep Installer"
VIAddVersionKey "LegalCopyright" "MIT License"

; ── MUI Settings ─────────────────────────────────────────────────
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Welcome to TypeKeep Setup"
!define MUI_WELCOMEPAGE_TEXT "This will install TypeKeep and TypeKeep Companion on your computer.$\r$\n$\r$\n• TypeKeep — Input logger, clipboard manager & macro engine$\r$\n• TypeKeep Companion — Cross-device sync app$\r$\n$\r$\nBoth apps will be linked automatically."
!define MUI_FINISHPAGE_RUN "$INSTDIR\TypeKeep.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Launch TypeKeep now"
!define MUI_FINISHPAGE_SHOWREADME ""
!define MUI_FINISHPAGE_SHOWREADME_TEXT "Launch TypeKeep Companion too"
!define MUI_FINISHPAGE_SHOWREADME_FUNCTION LaunchCompanion

; ── Pages ────────────────────────────────────────────────────────
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; ── Installer Section ────────────────────────────────────────────
Section "TypeKeep (required)" SecMain
    SectionIn RO

    ; Set output path
    SetOutPath "$INSTDIR"

    ; Install TypeKeep
    File "TypeKeep.exe"

    ; Install Companion
    File "TypeKeep-Companion.exe"

    ; Create data directory
    CreateDirectory "$INSTDIR\data"

    ; Write link config so both apps know about each other
    FileOpen $0 "$INSTDIR\data\link.json" w
    FileWrite $0 '{$\r$\n'
    FileWrite $0 '  "typekeep_host": "127.0.0.1",$\r$\n'
    FileWrite $0 '  "typekeep_port": 7700,$\r$\n'
    FileWrite $0 '  "companion_installed": true,$\r$\n'
    FileWrite $0 '  "auto_start_typekeep": true$\r$\n'
    FileWrite $0 '}$\r$\n'
    FileClose $0

    ; Store install dir in registry
    WriteRegStr HKCU "Software\TypeKeep" "InstallDir" "$INSTDIR"

    ; Register auto-start
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" \
        "TypeKeep" '"$INSTDIR\TypeKeep.exe" --background'

    ; ── Start Menu shortcuts ──
    CreateDirectory "$SMPROGRAMS\TypeKeep"
    CreateShortcut "$SMPROGRAMS\TypeKeep\TypeKeep.lnk" \
        "$INSTDIR\TypeKeep.exe" "" "$INSTDIR\TypeKeep.exe" 0
    CreateShortcut "$SMPROGRAMS\TypeKeep\TypeKeep Companion.lnk" \
        "$INSTDIR\TypeKeep-Companion.exe" "" "$INSTDIR\TypeKeep-Companion.exe" 0
    CreateShortcut "$SMPROGRAMS\TypeKeep\Dashboard.lnk" \
        "http://127.0.0.1:7700" "" "" 0
    CreateShortcut "$SMPROGRAMS\TypeKeep\Uninstall TypeKeep.lnk" \
        "$INSTDIR\Uninstall.exe" "" "$INSTDIR\Uninstall.exe" 0

    ; ── Desktop shortcuts ──
    CreateShortcut "$DESKTOP\TypeKeep.lnk" \
        "$INSTDIR\TypeKeep.exe" "" "$INSTDIR\TypeKeep.exe" 0
    CreateShortcut "$DESKTOP\TypeKeep Companion.lnk" \
        "$INSTDIR\TypeKeep-Companion.exe" "" "$INSTDIR\TypeKeep-Companion.exe" 0

    ; ── Uninstaller ──
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ; Add/Remove Programs entry
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TypeKeep" \
        "DisplayName" "TypeKeep"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TypeKeep" \
        "UninstallString" '"$INSTDIR\Uninstall.exe"'
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TypeKeep" \
        "DisplayVersion" "${PRODUCT_VERSION}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TypeKeep" \
        "Publisher" "${PRODUCT_PUBLISHER}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TypeKeep" \
        "URLInfoAbout" "${PRODUCT_WEB_SITE}"
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TypeKeep" \
        "NoModify" 1
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TypeKeep" \
        "NoRepair" 1

    ; Calculate installed size
    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TypeKeep" \
        "EstimatedSize" $0
SectionEnd

; ── Companion launch function (for finish page checkbox) ─────────
Function LaunchCompanion
    Exec '"$INSTDIR\TypeKeep-Companion.exe"'
FunctionEnd

; ── Uninstaller Section ──────────────────────────────────────────
Section "Uninstall"
    ; Kill running processes
    nsExec::ExecToLog 'taskkill /F /IM TypeKeep.exe'
    nsExec::ExecToLog 'taskkill /F /IM TypeKeep-Companion.exe'

    ; Remove auto-start
    DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "TypeKeep"

    ; Remove Add/Remove Programs entry
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TypeKeep"

    ; Remove registry key
    DeleteRegKey HKCU "Software\TypeKeep"

    ; Remove shortcuts
    Delete "$DESKTOP\TypeKeep.lnk"
    Delete "$DESKTOP\TypeKeep Companion.lnk"
    RMDir /r "$SMPROGRAMS\TypeKeep"

    ; Remove executables
    Delete "$INSTDIR\TypeKeep.exe"
    Delete "$INSTDIR\TypeKeep-Companion.exe"
    Delete "$INSTDIR\Uninstall.exe"
    Delete "$INSTDIR\data\link.json"

    ; Ask about data
    MessageBox MB_YESNO "Keep your data (typing history, config)?" IDYES keep_data
        RMDir /r "$INSTDIR\data"
    keep_data:

    ; Remove install dir if empty
    RMDir "$INSTDIR"
SectionEnd
