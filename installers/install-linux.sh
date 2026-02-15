#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  TypeKeep — All-in-One Installer (Linux)
#
#  Installs:
#    1. TypeKeep          — Input logger, clipboard manager & macros
#    2. TypeKeep Companion — Cross-device sync app (AppImage)
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
echo -e "${CYAN}     TypeKeep — All-in-One Installer (Linux)${NC}"
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
echo -e "  ${CYAN}[1/6]${NC} Creating directories..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/data"
mkdir -p "$BIN_DIR"
mkdir -p "$HOME/.local/share/applications"
mkdir -p "$HOME/.config/autostart"

# ── Copy files ───────────────────────────────────────────────────
echo -e "  ${CYAN}[2/6]${NC} Installing TypeKeep..."

if [ -f "$BUNDLE_DIR/TypeKeep" ]; then
    cp "$BUNDLE_DIR/TypeKeep" "$INSTALL_DIR/TypeKeep"
    chmod +x "$INSTALL_DIR/TypeKeep"
    echo "         TypeKeep binary installed."
else
    echo -e "  ${RED}ERROR:${NC} TypeKeep binary not found in the installer bundle."
    echo "  Make sure you extracted the full archive before running install."
    exit 1
fi

COMPANION_INSTALLED=false
COMPANION_FILE=""
for f in "$BUNDLE_DIR"/TypeKeep-Companion*.AppImage "$BUNDLE_DIR"/TypeKeep_Companion*.AppImage; do
    if [ -f "$f" ]; then
        COMPANION_FILE="$(basename "$f")"
        cp "$f" "$INSTALL_DIR/$COMPANION_FILE"
        chmod +x "$INSTALL_DIR/$COMPANION_FILE"
        COMPANION_INSTALLED=true
        echo "         TypeKeep Companion ($COMPANION_FILE) installed."
        break
    fi
done

if [ "$COMPANION_INSTALLED" = false ]; then
    echo -e "  ${YELLOW}WARNING:${NC} TypeKeep Companion AppImage not found. Companion will not be installed."
fi

# ── Auto-link: write shared config ───────────────────────────────
echo -e "  ${CYAN}[3/6]${NC} Linking TypeKeep & Companion..."
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

# ── Create symlinks in PATH ──────────────────────────────────────
echo -e "  ${CYAN}[4/6]${NC} Adding to PATH..."

ln -sf "$INSTALL_DIR/TypeKeep" "$BIN_DIR/typekeep"
echo "         Command 'typekeep' symlinked to $BIN_DIR/"

if [ "$COMPANION_INSTALLED" = true ]; then
    ln -sf "$INSTALL_DIR/$COMPANION_FILE" "$BIN_DIR/typekeep-companion"
    echo "         Command 'typekeep-companion' symlinked to $BIN_DIR/"
fi

# Check if ~/.local/bin is in PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo -e "  ${YELLOW}NOTE:${NC} $BIN_DIR is not in your PATH."
    echo "         Add this to your ~/.bashrc or ~/.zshrc:"
    echo "         export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# ── Create .desktop entries ──────────────────────────────────────
echo -e "  ${CYAN}[5/6]${NC} Creating desktop entries..."

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

# ── Register autostart ───────────────────────────────────────────
echo -e "  ${CYAN}[6/6]${NC} Registering auto-start..."

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

INSTALL_DIR="$HOME/.local/share/typekeep"
BIN_DIR="$HOME/.local/bin"

read -r -p "Keep your data (typing history, config)? [Y/n] " KEEPDATA

# Remove symlinks
rm -f "$BIN_DIR/typekeep" 2>/dev/null
rm -f "$BIN_DIR/typekeep-companion" 2>/dev/null

# Remove desktop entries
rm -f "$HOME/.local/share/applications/typekeep.desktop" 2>/dev/null
rm -f "$HOME/.local/share/applications/typekeep-companion.desktop" 2>/dev/null

# Remove autostart
rm -f "$HOME/.config/autostart/typekeep.desktop" 2>/dev/null

if [[ "$KEEPDATA" =~ ^[Nn]$ ]]; then
    rm -rf "$INSTALL_DIR"
else
    rm -f "$INSTALL_DIR/TypeKeep"
    rm -f "$INSTALL_DIR"/TypeKeep-Companion*.AppImage
    rm -f "$INSTALL_DIR"/TypeKeep_Companion*.AppImage
    echo "Data kept in $INSTALL_DIR/data"
fi

echo "TypeKeep uninstalled."
UNINSTALL
chmod +x "$INSTALL_DIR/uninstall.sh"

# ── Done ─────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}     Installation complete!${NC}"
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
    echo "  Both apps launched!"
fi

echo ""
