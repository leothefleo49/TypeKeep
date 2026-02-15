#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  TypeKeep — All-in-One Installer (macOS)
#
#  Installs:
#    1. TypeKeep          — Input logger, clipboard manager & macros
#    2. TypeKeep Companion — Cross-device sync app
#
#  Both apps are linked automatically.
# ─────────────────────────────────────────────────────────────────
set -e

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}     TypeKeep — All-in-One Installer (macOS)${NC}"
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
BUNDLE_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "  Install location: $INSTALL_DIR"
echo ""
read -r -p "  Proceed with installation? [Y/n] " CONFIRM
if [[ "$CONFIRM" =~ ^[Nn]$ ]]; then
    echo "  Installation cancelled."
    exit 0
fi

echo ""

# ── Create directories ───────────────────────────────────────────
echo -e "  ${CYAN}[1/5]${NC} Creating install directory..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/data"

# ── Copy files ───────────────────────────────────────────────────
echo -e "  ${CYAN}[2/5]${NC} Installing TypeKeep..."

if [ -f "$BUNDLE_DIR/TypeKeep" ]; then
    cp "$BUNDLE_DIR/TypeKeep" "$INSTALL_DIR/TypeKeep"
    chmod +x "$INSTALL_DIR/TypeKeep"
    echo "         TypeKeep binary installed."
else
    echo -e "  ${RED}ERROR:${NC} TypeKeep binary not found in the installer bundle."
    echo "  Make sure you extracted the full archive before running install."
    exit 1
fi

if [ -f "$BUNDLE_DIR/TypeKeep Companion.dmg" ]; then
    echo "         Mounting Companion DMG..."
    MOUNT_DIR=$(hdiutil attach "$BUNDLE_DIR/TypeKeep Companion.dmg" -nobrowse -quiet | tail -1 | awk '{print $3}')
    if [ -d "$MOUNT_DIR/TypeKeep Companion.app" ]; then
        cp -R "$MOUNT_DIR/TypeKeep Companion.app" "$INSTALL_DIR/TypeKeep Companion.app"
        echo "         TypeKeep Companion.app installed."
    fi
    hdiutil detach "$MOUNT_DIR" -quiet 2>/dev/null || true
elif [ -d "$BUNDLE_DIR/TypeKeep Companion.app" ]; then
    cp -R "$BUNDLE_DIR/TypeKeep Companion.app" "$INSTALL_DIR/TypeKeep Companion.app"
    echo "         TypeKeep Companion.app installed."
else
    echo -e "  ${YELLOW}WARNING:${NC} TypeKeep Companion not found. Companion will not be installed."
fi

# ── Auto-link: write shared config ───────────────────────────────
echo -e "  ${CYAN}[3/5]${NC} Linking TypeKeep & Companion..."
cat > "$INSTALL_DIR/data/link.json" << EOF
{
  "typekeep_host": "127.0.0.1",
  "typekeep_port": 7700,
  "companion_installed": true,
  "install_dir": "$INSTALL_DIR",
  "auto_start_typekeep": true
}
EOF
echo "         Apps linked via shared config."

# ── Create launch script & symlinks ──────────────────────────────
echo -e "  ${CYAN}[4/5]${NC} Creating launcher & symlinks..."

# Create a launcher script in /usr/local/bin
LAUNCHER="/usr/local/bin/typekeep"
if [ -w "/usr/local/bin" ] || [ -w "$(dirname "$LAUNCHER")" ]; then
    cat > "$LAUNCHER" << 'LAUNCH'
#!/usr/bin/env bash
INSTALL_DIR="$HOME/Applications/TypeKeep"
"$INSTALL_DIR/TypeKeep" "$@"
LAUNCH
    chmod +x "$LAUNCHER"
    echo "         Command 'typekeep' added to PATH."
else
    echo "         (Skipped adding to PATH — run with sudo for that)"
fi

# Create .app wrapper for Finder / Launchpad
APP_DIR="$HOME/Applications/TypeKeep.app"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

cat > "$APP_DIR/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>TypeKeep</string>
    <key>CFBundleIdentifier</key>
    <string>com.typekeep.app</string>
    <key>CFBundleName</key>
    <string>TypeKeep</string>
    <key>CFBundleVersion</key>
    <string>3.1.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSUIElement</key>
    <true/>
</dict>
</plist>
PLIST

cat > "$APP_DIR/Contents/MacOS/TypeKeep" << WRAPPER
#!/usr/bin/env bash
"$INSTALL_DIR/TypeKeep" "\$@"
WRAPPER
chmod +x "$APP_DIR/Contents/MacOS/TypeKeep"
echo "         TypeKeep.app created for Launchpad."

# ── Create uninstaller ───────────────────────────────────────────
cat > "$INSTALL_DIR/uninstall.sh" << 'UNINSTALL'
#!/usr/bin/env bash
echo "Removing TypeKeep..."

read -r -p "Keep your data (typing history, config)? [Y/n] " KEEPDATA

INSTALL_DIR="$HOME/Applications/TypeKeep"

# Remove launcher
rm -f /usr/local/bin/typekeep 2>/dev/null

# Remove .app wrapper
rm -rf "$HOME/Applications/TypeKeep.app" 2>/dev/null

# Remove LaunchAgent
rm -f "$HOME/Library/LaunchAgents/com.typekeep.plist" 2>/dev/null
launchctl unload "$HOME/Library/LaunchAgents/com.typekeep.plist" 2>/dev/null

if [[ "$KEEPDATA" =~ ^[Nn]$ ]]; then
    rm -rf "$INSTALL_DIR"
else
    rm -f "$INSTALL_DIR/TypeKeep"
    rm -rf "$INSTALL_DIR/TypeKeep Companion.app"
    echo "Data kept in $INSTALL_DIR/data"
fi

echo "TypeKeep uninstalled."
UNINSTALL
chmod +x "$INSTALL_DIR/uninstall.sh"
echo "         Uninstaller created."

# ── Register auto-start (LaunchAgent) ────────────────────────────
echo -e "  ${CYAN}[5/5]${NC} Registering auto-start..."
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$HOME/Library/LaunchAgents/com.typekeep.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.typekeep</string>
    <key>ProgramArguments</key>
    <array>
        <string>$INSTALL_DIR/TypeKeep</string>
        <string>--background</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>WorkingDirectory</key>
    <string>$INSTALL_DIR</string>
</dict>
</plist>
PLIST
echo "         TypeKeep will start automatically on login."

# ── Done ─────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}     Installation complete!${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo "  TypeKeep:           $INSTALL_DIR/TypeKeep"
echo "  TypeKeep Companion: $INSTALL_DIR/TypeKeep Companion.app"
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
    echo "  Both apps launched!"
fi

echo ""
