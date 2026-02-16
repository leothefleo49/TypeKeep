#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  TypeKeep — Single-File Installer (macOS)
#
#  This is a self-extracting archive. Just run:
#    chmod +x TypeKeep-Installer-macOS.sh && ./TypeKeep-Installer-macOS.sh
#
#  It installs BOTH:
#    1. TypeKeep          — Input logger, clipboard manager & macros
#    2. TypeKeep Companion — Cross-device sync app
#  And links them together automatically.
# ─────────────────────────────────────────────────────────────────
set -e

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

echo ""
echo -e "${CYAN}${BOLD}============================================================${NC}"
echo -e "${CYAN}${BOLD}     TypeKeep — Installer for macOS${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""
echo "  This will install:"
echo "    1. TypeKeep          — Input logger, clipboard manager & macros"
echo "    2. TypeKeep Companion — Cross-device sync app"
echo ""
echo "  Both apps will be linked automatically."
echo ""

# ── Determine install directory ──────────────────────────────────
INSTALL_DIR="$HOME/Applications/TypeKeep"

echo "  Install location: $INSTALL_DIR"
echo ""
read -r -p "  Proceed with installation? [Y/n] " CONFIRM
if [[ "$CONFIRM" =~ ^[Nn]$ ]]; then
    echo "  Installation cancelled."
    exit 0
fi

echo ""

# ── Extract payload ──────────────────────────────────────────────
echo -e "  ${CYAN}[1/6]${NC} Extracting files..."
TMPDIR_INST=$(mktemp -d)
ARCHIVE_LINE=$(awk '/^__PAYLOAD_BEGINS__$/{print NR + 1; exit 0;}' "${BASH_SOURCE[0]}")
tail -n +"$ARCHIVE_LINE" "${BASH_SOURCE[0]}" | tar -xzf - -C "$TMPDIR_INST"
echo "         Extracted to temporary directory."

# ── Create directories ───────────────────────────────────────────
echo -e "  ${CYAN}[2/6]${NC} Creating install directory..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/data"

# ── Install files ────────────────────────────────────────────────
echo -e "  ${CYAN}[3/6]${NC} Installing applications..."

if [ -f "$TMPDIR_INST/TypeKeep" ]; then
    cp "$TMPDIR_INST/TypeKeep" "$INSTALL_DIR/TypeKeep"
    chmod +x "$INSTALL_DIR/TypeKeep"
    echo "         TypeKeep installed."
else
    echo -e "  ${RED}ERROR:${NC} TypeKeep binary not found in archive."
    rm -rf "$TMPDIR_INST"
    exit 1
fi

# Companion — could be a .dmg or a .app directory
COMPANION_INSTALLED=false
DMG=$(find "$TMPDIR_INST" -maxdepth 1 -name "*.dmg" | head -1)
APP=$(find "$TMPDIR_INST" -maxdepth 1 -name "*.app" -type d | head -1)

if [ -n "$DMG" ]; then
    echo "         Mounting Companion DMG..."
    MOUNT_PT=$(hdiutil attach "$DMG" -nobrowse -quiet | tail -1 | awk '{$1=$2=""; print $0}' | sed 's/^ *//')
    INNER_APP=$(find "$MOUNT_PT" -maxdepth 1 -name "*.app" -type d | head -1)
    if [ -n "$INNER_APP" ]; then
        cp -R "$INNER_APP" "$INSTALL_DIR/TypeKeep Companion.app"
        COMPANION_INSTALLED=true
        echo "         TypeKeep Companion.app installed."
    fi
    hdiutil detach "$MOUNT_PT" -quiet 2>/dev/null || true
elif [ -n "$APP" ]; then
    cp -R "$APP" "$INSTALL_DIR/TypeKeep Companion.app"
    COMPANION_INSTALLED=true
    echo "         TypeKeep Companion.app installed."
else
    echo -e "  ${YELLOW}WARNING:${NC} TypeKeep Companion not found in archive. Skipping."
fi

# ── Auto-link ────────────────────────────────────────────────────
echo -e "  ${CYAN}[4/6]${NC} Linking TypeKeep & Companion..."
cat > "$INSTALL_DIR/data/link.json" << EOF
{
  "typekeep_host": "127.0.0.1",
  "typekeep_port": 7700,
  "companion_installed": $COMPANION_INSTALLED,
  "install_dir": "$INSTALL_DIR",
  "auto_start_typekeep": true
}
EOF
echo "         Apps linked via shared config."

# ── App wrapper + CLI ────────────────────────────────────────────
echo -e "  ${CYAN}[5/6]${NC} Creating app launcher & CLI command..."

# .app wrapper for Finder / Launchpad
APP_BUNDLE="$HOME/Applications/TypeKeep.app"
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"

cat > "$APP_BUNDLE/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>   <string>TypeKeep</string>
    <key>CFBundleIdentifier</key>   <string>com.typekeep.app</string>
    <key>CFBundleName</key>         <string>TypeKeep</string>
    <key>CFBundleVersion</key>      <string>3.1.0</string>
    <key>CFBundlePackageType</key>  <string>APPL</string>
    <key>LSUIElement</key>          <true/>
</dict>
</plist>
PLIST

cat > "$APP_BUNDLE/Contents/MacOS/TypeKeep" << WRAPPER
#!/usr/bin/env bash
"$INSTALL_DIR/TypeKeep" "\$@"
WRAPPER
chmod +x "$APP_BUNDLE/Contents/MacOS/TypeKeep"
echo "         TypeKeep.app wrapper created."

# CLI command
if [ -w "/usr/local/bin" ] 2>/dev/null; then
    cat > "/usr/local/bin/typekeep" << LAUNCHER
#!/usr/bin/env bash
"$INSTALL_DIR/TypeKeep" "\$@"
LAUNCHER
    chmod +x "/usr/local/bin/typekeep"
    echo "         'typekeep' command added to PATH."
else
    echo "         (Skipped CLI symlink — run with sudo for /usr/local/bin access)"
fi

# ── Auto-start (LaunchAgent) ─────────────────────────────────────
echo -e "  ${CYAN}[6/6]${NC} Registering auto-start..."
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$HOME/Library/LaunchAgents/com.typekeep.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>            <string>com.typekeep</string>
    <key>ProgramArguments</key>
    <array>
        <string>$INSTALL_DIR/TypeKeep</string>
        <string>--background</string>
    </array>
    <key>RunAtLoad</key>        <true/>
    <key>KeepAlive</key>        <false/>
    <key>WorkingDirectory</key> <string>$INSTALL_DIR</string>
</dict>
</plist>
PLIST
echo "         TypeKeep will start automatically on login."

# ── Create uninstaller ───────────────────────────────────────────
cat > "$INSTALL_DIR/uninstall.sh" << 'UNINSTALL'
#!/usr/bin/env bash
echo "Removing TypeKeep..."
read -r -p "Keep your data (typing history, config)? [Y/n] " KEEPDATA
INSTALL_DIR="$HOME/Applications/TypeKeep"
rm -f /usr/local/bin/typekeep 2>/dev/null
rm -rf "$HOME/Applications/TypeKeep.app" 2>/dev/null
launchctl unload "$HOME/Library/LaunchAgents/com.typekeep.plist" 2>/dev/null
rm -f "$HOME/Library/LaunchAgents/com.typekeep.plist" 2>/dev/null
if [[ "$KEEPDATA" =~ ^[Nn]$ ]]; then
    rm -rf "$INSTALL_DIR"
else
    rm -f "$INSTALL_DIR/TypeKeep"
    rm -rf "$INSTALL_DIR/TypeKeep Companion.app"
    rm -f "$INSTALL_DIR/uninstall.sh"
    echo "Data kept in $INSTALL_DIR/data"
fi
echo "TypeKeep uninstalled."
UNINSTALL
chmod +x "$INSTALL_DIR/uninstall.sh"

# ── Cleanup temp ─────────────────────────────────────────────────
rm -rf "$TMPDIR_INST"

# ── Done ─────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}============================================================${NC}"
echo -e "${GREEN}${BOLD}     Installation complete!${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo "  TypeKeep:           $INSTALL_DIR/TypeKeep"
if [ "$COMPANION_INSTALLED" = true ]; then
echo "  TypeKeep Companion: $INSTALL_DIR/TypeKeep Companion.app"
fi
echo "  Dashboard:          http://127.0.0.1:7700"
echo "  Data:               $INSTALL_DIR/data/"
echo ""
echo "  TypeKeep will auto-start on login."
echo "  To uninstall: bash $INSTALL_DIR/uninstall.sh"
echo ""

read -r -p "  Launch TypeKeep now? [Y/n] " LAUNCH
if [[ ! "$LAUNCH" =~ ^[Nn]$ ]]; then
    echo "  Starting TypeKeep..."
    "$INSTALL_DIR/TypeKeep" &
    sleep 2
    if [ -d "$INSTALL_DIR/TypeKeep Companion.app" ]; then
        open "$INSTALL_DIR/TypeKeep Companion.app"
    fi
    echo "  Done!"
fi

echo ""
exit 0
__PAYLOAD_BEGINS__
