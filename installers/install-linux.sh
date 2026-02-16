#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  TypeKeep — Single-File Installer (Linux)
#
#  This is a self-extracting archive. Just run:
#    chmod +x TypeKeep-Installer-Linux.sh && ./TypeKeep-Installer-Linux.sh
#
#  It installs BOTH:
#    1. TypeKeep          — Input logger, clipboard manager & macros
#    2. TypeKeep Companion — Cross-device sync app (AppImage)
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
echo -e "${CYAN}${BOLD}     TypeKeep — Installer for Linux${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""
echo "  This will install:"
echo "    1. TypeKeep          — Input logger, clipboard manager & macros"
echo "    2. TypeKeep Companion — Cross-device sync app"
echo ""
echo "  Both apps will be linked automatically."
echo ""

# ── Determine install directory ──────────────────────────────────
INSTALL_DIR="$HOME/.local/share/typekeep"
BIN_DIR="$HOME/.local/bin"

echo "  Install location: $INSTALL_DIR"
echo ""
read -r -p "  Proceed with installation? [Y/n] " CONFIRM
if [[ "$CONFIRM" =~ ^[Nn]$ ]]; then
    echo "  Installation cancelled."
    exit 0
fi

echo ""

# ── Extract payload ──────────────────────────────────────────────
echo -e "  ${CYAN}[1/7]${NC} Extracting files..."
TMPDIR_INST=$(mktemp -d)
ARCHIVE_LINE=$(awk '/^__PAYLOAD_BEGINS__$/{print NR + 1; exit 0;}' "${BASH_SOURCE[0]}")
tail -n +"$ARCHIVE_LINE" "${BASH_SOURCE[0]}" | tar -xzf - -C "$TMPDIR_INST"
echo "         Extracted to temporary directory."

# ── Create directories ───────────────────────────────────────────
echo -e "  ${CYAN}[2/7]${NC} Creating directories..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/data"
mkdir -p "$BIN_DIR"
mkdir -p "$HOME/.local/share/applications"
mkdir -p "$HOME/.config/autostart"

# ── Install files ────────────────────────────────────────────────
echo -e "  ${CYAN}[3/7]${NC} Installing applications..."

if [ -f "$TMPDIR_INST/TypeKeep" ]; then
    cp "$TMPDIR_INST/TypeKeep" "$INSTALL_DIR/TypeKeep"
    chmod +x "$INSTALL_DIR/TypeKeep"
    echo "         TypeKeep installed."
else
    echo -e "  ${RED}ERROR:${NC} TypeKeep binary not found in archive."
    rm -rf "$TMPDIR_INST"
    exit 1
fi

COMPANION_INSTALLED=false
COMPANION_FILE=""
APPIMAGE=$(find "$TMPDIR_INST" -maxdepth 1 -name "*.AppImage" | head -1)
if [ -n "$APPIMAGE" ]; then
    COMPANION_FILE=$(basename "$APPIMAGE")
    cp "$APPIMAGE" "$INSTALL_DIR/$COMPANION_FILE"
    chmod +x "$INSTALL_DIR/$COMPANION_FILE"
    COMPANION_INSTALLED=true
    echo "         TypeKeep Companion ($COMPANION_FILE) installed."
else
    echo -e "  ${YELLOW}WARNING:${NC} TypeKeep Companion AppImage not found. Skipping."
fi

# ── Auto-link ────────────────────────────────────────────────────
echo -e "  ${CYAN}[4/7]${NC} Linking TypeKeep & Companion..."
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

# ── Symlinks in PATH ─────────────────────────────────────────────
echo -e "  ${CYAN}[5/7]${NC} Adding to PATH..."

ln -sf "$INSTALL_DIR/TypeKeep" "$BIN_DIR/typekeep"
echo "         'typekeep' → $BIN_DIR/typekeep"

if [ "$COMPANION_INSTALLED" = true ]; then
    ln -sf "$INSTALL_DIR/$COMPANION_FILE" "$BIN_DIR/typekeep-companion"
    echo "         'typekeep-companion' → $BIN_DIR/typekeep-companion"
fi

if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo -e "  ${YELLOW}NOTE:${NC} $BIN_DIR may not be in your PATH."
    echo "         Add to ~/.bashrc or ~/.zshrc:  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# ── Desktop entries ───────────────────────────────────────────────
echo -e "  ${CYAN}[6/7]${NC} Creating desktop entries..."

cat > "$HOME/.local/share/applications/typekeep.desktop" << EOF
[Desktop Entry]
Type=Application
Name=TypeKeep
Comment=Input logger, clipboard manager & macro engine
Exec=$INSTALL_DIR/TypeKeep
Terminal=false
Categories=Utility;
StartupNotify=false
EOF
echo "         typekeep.desktop created."

if [ "$COMPANION_INSTALLED" = true ]; then
    cat > "$HOME/.local/share/applications/typekeep-companion.desktop" << EOF
[Desktop Entry]
Type=Application
Name=TypeKeep Companion
Comment=Cross-device clipboard sync & typing history
Exec=$INSTALL_DIR/$COMPANION_FILE --no-sandbox
Terminal=false
Categories=Utility;
StartupNotify=false
EOF
    echo "         typekeep-companion.desktop created."
fi

# ── Autostart ─────────────────────────────────────────────────────
echo -e "  ${CYAN}[7/7]${NC} Registering auto-start..."

cat > "$HOME/.config/autostart/typekeep.desktop" << EOF
[Desktop Entry]
Type=Application
Name=TypeKeep
Exec=$INSTALL_DIR/TypeKeep --background
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
echo "         TypeKeep will start automatically on login."

# ── Create uninstaller ───────────────────────────────────────────
cat > "$INSTALL_DIR/uninstall.sh" << 'UNINSTALL'
#!/usr/bin/env bash
echo "Removing TypeKeep..."
read -r -p "Keep your data (typing history, config)? [Y/n] " KEEPDATA
INSTALL_DIR="$HOME/.local/share/typekeep"
BIN_DIR="$HOME/.local/bin"
rm -f "$BIN_DIR/typekeep" 2>/dev/null
rm -f "$BIN_DIR/typekeep-companion" 2>/dev/null
rm -f "$HOME/.local/share/applications/typekeep.desktop" 2>/dev/null
rm -f "$HOME/.local/share/applications/typekeep-companion.desktop" 2>/dev/null
rm -f "$HOME/.config/autostart/typekeep.desktop" 2>/dev/null
if [[ "$KEEPDATA" =~ ^[Nn]$ ]]; then
    rm -rf "$INSTALL_DIR"
else
    rm -f "$INSTALL_DIR/TypeKeep"
    find "$INSTALL_DIR" -maxdepth 1 -name "*.AppImage" -delete 2>/dev/null
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
echo "  TypeKeep Companion: $INSTALL_DIR/$COMPANION_FILE"
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
    nohup "$INSTALL_DIR/TypeKeep" > /dev/null 2>&1 &
    sleep 2
    if [ "$COMPANION_INSTALLED" = true ]; then
        nohup "$INSTALL_DIR/$COMPANION_FILE" --no-sandbox > /dev/null 2>&1 &
    fi
    echo "  Done!"
fi

echo ""
exit 0
__PAYLOAD_BEGINS__
