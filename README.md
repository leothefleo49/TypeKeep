<p align="center">
  <img src="https://img.shields.io/badge/TypeKeep-v2.0-2dd4bf?style=for-the-badge" alt="TypeKeep">
</p>

<h1 align="center">⌨ TypeKeep</h1>

<p align="center">
  <strong>Lightweight local input logger, clipboard manager & macro engine</strong><br>
  <em>Everything runs locally. Your data never leaves your machine.</em>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#installation">Installation</a> •
  <a href="#usage">Usage</a> •
  <a href="#device-sync">Device Sync</a> •
  <a href="#screenshots">Screenshots</a> •
  <a href="#building">Building</a>
</p>

<p align="center">
  <a href="https://github.com/YOUR_USERNAME/TypeKeep/releases/latest">
    <img src="https://img.shields.io/badge/Download-Windows-0078D4?style=for-the-badge&logo=windows&logoColor=white" alt="Windows Download">
  </a>
  &nbsp;
  <a href="https://github.com/YOUR_USERNAME/TypeKeep/releases/latest">
    <img src="https://img.shields.io/badge/Download-macOS-000000?style=for-the-badge&logo=apple&logoColor=white" alt="macOS Download">
  </a>
  &nbsp;
  <a href="https://github.com/YOUR_USERNAME/TypeKeep/releases/latest">
    <img src="https://img.shields.io/badge/Download-Linux-FCC624?style=for-the-badge&logo=linux&logoColor=black" alt="Linux Download">
  </a>
</p>

---

## Features

### ⌨ Smart Text History
- **Context-aware grouping** — Groups keystrokes by active window and time gaps
- **Cursor-position-aware reconstruction** — Correctly handles backspaces, delete, arrow keys, Home/End
- **3 view modes** — Final text (corrected), raw keystrokes (with symbols), chronological (timestamped)
- **Search & filter** — Search text history, filter by app, time range, gap size

### 📋 Clipboard History
- **Automatic clipboard tracking** — Text, images, and files are recorded automatically
- **Image thumbnails** — Clipboard images are saved with thumbnails for quick browsing
- **File tracking** — Copied file paths are logged with metadata
- **Pin important entries** — Star/pin clipboard entries to keep them from being cleaned up
- **Copy back** — Click to copy any past entry back to your clipboard

### 🔄 Cross-Device Sync
- **Peer-to-peer sync** — Pair devices on your network using IP + shared passphrase
- **Clipboard sync** — Optionally sync clipboard history across all paired devices
- **Pull on demand** — Pull clipboard data from any paired device at any time
- **No cloud required** — Everything stays on your local network

### ⚡ Macros
- **Build automations** — Combine hotkeys, text input, delays, and mouse clicks
- **Quick presets** — One-click macros for Task Manager, Screenshot, File Explorer, etc.
- **Custom shortcuts** — Assign keyboard shortcuts to your macros

### 🖱️ Activity Tracking
- **Mouse clicks** — Track click positions and button types
- **Mouse scroll & movement** — Optional high-fidelity mouse tracking
- **Shortcuts** — Automatically detect and log Ctrl/Alt/Cmd combinations
- **Notifications** — Detect Windows toast notifications

### 🛡️ Privacy & Control
- **100% local** — All data stored in a local SQLite database
- **Export/Import** — Full JSON export and import of all data
- **Granular delete** — Delete individual messages, time ranges, or everything
- **Configurable retention** — Auto-cleanup after N days
- **Start on boot** — Optional Windows startup registration

### 🎨 Dashboard
- **Dark theme** — Beautiful dark UI with teal accents
- **System tray** — Runs silently in the background with a tray icon
- **Anti-flicker** — Smart rendering that only updates when data changes
- **Custom dropdowns** — Styled select menus (no ugly native dropdowns)
- **Responsive** — Works on any screen size
- **Onboarding wizard** — Guided setup on first launch

---

## Installation

### Quick Start (Python)

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/TypeKeep.git
cd TypeKeep

# Install dependencies
pip install -r requirements.txt

# Run TypeKeep
python typekeep.py
```

### Windows Installer

```batch
# Double-click install.bat to install dependencies
install.bat

# Double-click start.bat to run in the background
start.bat
```

### Download Pre-built

Go to [**Releases**](https://github.com/YOUR_USERNAME/TypeKeep/releases/latest) and download the executable for your platform:

| Platform | Download |
|----------|----------|
| Windows  | `TypeKeep-windows.exe` |
| macOS    | `TypeKeep-macos` |
| Linux    | `TypeKeep-linux` |

---

## Usage

1. **Launch** — Run `python typekeep.py` or double-click `start.bat`
2. **Dashboard** — Opens automatically at `http://127.0.0.1:7700`
3. **System Tray** — Look for the teal **T** icon in your taskbar
   - Right-click → **Open Dashboard**
   - Right-click → **Pause/Resume** recording
   - Right-click → **Quit**

### Tabs

| Tab | Description |
|-----|-------------|
| **Text History** | View grouped, reconstructed text from your typing |
| **Clipboard** | Browse clipboard history (text, images, files) |
| **Activity** | Mouse clicks, scroll, shortcuts, notifications |
| **Macros** | Create and run automated key/mouse sequences |
| **Devices** | Pair and sync with other TypeKeep instances |
| **Shortcut Guide** | Reference for common keyboard shortcuts |

### Keyboard Shortcuts Detected

TypeKeep automatically records all keyboard shortcuts:
`Ctrl+C`, `Ctrl+V`, `Ctrl+Z`, `Alt+Tab`, `Win+E`, `Ctrl+Shift+Esc`, etc.

---

## Device Sync

TypeKeep supports peer-to-peer sync between devices on the same network.

### Setup

1. Open the **Devices** tab on both devices
2. Set a **device name** and **sync key** (shared passphrase) on both
3. Enable **sync** on both devices
4. On Device A, enter Device B's **IP address** and **port** (default: 7700)
5. Click **Pair**
6. Optionally enable **clipboard sync** to share clipboard entries

### How It Works

- Devices authenticate using the shared sync key
- Pairing is mutual — both devices register each other
- **Pull Clipboard** fetches clipboard history from the remote device
- With clipboard sync enabled, new clipboard entries are pushed automatically

---

## Screenshots

> *Screenshots coming soon — run TypeKeep and explore the dashboard!*

---

## Configuration

Settings are stored in `data/config.json`. Key options:

| Setting | Default | Description |
|---------|---------|-------------|
| `record_keyboard` | `true` | Record keystrokes |
| `record_mouse_clicks` | `true` | Record mouse clicks |
| `record_clipboard` | `true` | Track clipboard changes |
| `default_gap_seconds` | `5` | Time gap to split messages |
| `same_window_gap_seconds` | `30` | Gap tolerance for same window |
| `retention_days` | `30` | Auto-delete events older than N days |
| `clipboard_retention_days` | `30` | Auto-delete clipboard entries |
| `start_on_boot` | `false` | Run on Windows startup |
| `sync_enabled` | `false` | Enable device sync |
| `clipboard_sync` | `false` | Sync clipboard across devices |

---

## Building

### Build Executable (PyInstaller)

```bash
pip install pyinstaller

# Windows
pyinstaller --onefile --noconsole --name TypeKeep --add-data "templates;templates" --add-data "static;static" typekeep.py

# macOS / Linux
pyinstaller --onefile --noconsole --name TypeKeep --add-data "templates:templates" --add-data "static:static" typekeep.py
```

The executable will be in `dist/TypeKeep`.

---

## Tech Stack

- **Python 3.10+** — Core runtime
- **Flask** — Web server & API
- **pynput** — Keyboard & mouse input capture
- **pystray** — System tray icon
- **Pillow** — Image processing (clipboard images, tray icon)
- **SQLite** — Local database with WAL mode

---

## Project Structure

```
TypeKeep/
├── typekeep.py           # Main entry point
├── config.py             # JSON config manager
├── database.py           # SQLite storage & queries
├── recorder.py           # Input capture (keyboard, mouse, shortcuts)
├── clipboard_monitor.py  # Clipboard change detection
├── server.py             # Flask API server
├── tray.py               # System tray icon
├── requirements.txt      # Python dependencies
├── install.bat           # Windows dependency installer
├── start.bat             # Windows background launcher
├── templates/
│   └── index.html        # Dashboard SPA
├── static/
│   ├── app.js            # Frontend logic
│   └── style.css         # Dark theme stylesheet
└── data/                 # Runtime data (gitignored)
    ├── typekeep.db       # SQLite database
    ├── config.json       # User settings
    └── clips/            # Clipboard images
```

---

## License

MIT License — free for personal and commercial use.

---

<p align="center">
  <strong>TypeKeep</strong> — Your keystrokes, your clipboard, your data, your control.
</p>
