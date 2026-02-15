<p align="center">
  <img src="https://img.shields.io/badge/TypeKeep-v3.0.0-2dd4bf?style=for-the-badge" alt="TypeKeep v3.0.0">
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux%20%7C%20Android%20%7C%20iOS-blue?style=for-the-badge" alt="Platforms">
</p>

<h1 align="center">⌨ TypeKeep</h1>

<p align="center">
  <strong>Lightweight input logger, clipboard manager, macro engine & cross-device sync</strong><br>
  <em>Desktop app runs locally. Cloud sync (free) connects all your devices.</em>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#installation">Installation</a> •
  <a href="#cloud-sync">Cloud Sync</a> •
  <a href="#mobile-app">Mobile App</a> •
  <a href="#device-sync">Device Sync</a> •
  <a href="#building">Building</a>
</p>

<p align="center">
  <a href="https://github.com/leothefleo49/TypeKeep/releases/latest">
    <img src="https://img.shields.io/badge/Download-Windows-0078D4?style=for-the-badge&logo=windows&logoColor=white" alt="Windows Download">
  </a>
  &nbsp;
  <a href="https://github.com/leothefleo49/TypeKeep/releases/latest">
    <img src="https://img.shields.io/badge/Download-macOS-000000?style=for-the-badge&logo=apple&logoColor=white" alt="macOS Download">
  </a>
  &nbsp;
  <a href="https://github.com/leothefleo49/TypeKeep/releases/latest">
    <img src="https://img.shields.io/badge/Download-Linux-FCC624?style=for-the-badge&logo=linux&logoColor=black" alt="Linux Download">
  </a>
  &nbsp;
  <a href="https://leothefleo49.github.io/TypeKeep/">
    <img src="https://img.shields.io/badge/Mobile-Android%20%2F%20iOS-34A853?style=for-the-badge&logo=pwa&logoColor=white" alt="Mobile App">
  </a>
</p>

---

## What's New in v3.0.0

- **☁️ Cloud Sync** — Free Supabase-powered sync across all devices
- **📱 Mobile App** — PWA companion app for Android and iOS
- **🌐 Cross-Platform** — Desktop (Win/Mac/Linux) + Mobile (Android/iOS) all syncing together
- **🔄 Automatic Releases** — GitHub Actions builds and publishes installers automatically
- **🛠️ Improved Settings** — Cloud sync configuration built into the dashboard

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
- **Pin important entries** — Star/pin clipboard entries to keep them from being cleaned up
- **Copy back** — Click to copy any past entry back to your clipboard

### ☁️ Cloud Sync (Free)
- **Supabase-powered** — Uses Supabase free tier (500MB, unlimited API calls)
- **Clipboard sync** — Clipboard entries automatically sync across all devices
- **Typing history sync** — View your desktop typing history on mobile
- **Device management** — See all connected devices and their online status
- **Zero cost** — Works entirely on Supabase's generous free tier

### 📱 Mobile App (Android & iOS)
- **Progressive Web App** — Install directly from your browser, no app store needed
- **Full clipboard access** — View, copy, and send clipboard entries across devices
- **Typing history viewer** — Browse your desktop typing history on your phone
- **Device overview** — See all connected devices at a glance
- **Works offline** — Service worker caches the app for offline access

### 🔄 Local Network Sync
- **Peer-to-peer sync** — Pair devices on your network using IP + shared passphrase
- **Clipboard sync** — Optionally sync clipboard history across all paired devices
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
- **100% local** — Desktop data stored in a local SQLite database
- **Cloud is optional** — Cloud sync is entirely opt-in
- **Export/Import** — Full JSON export and import of all data
- **Granular delete** — Delete individual messages, time ranges, or everything
- **Configurable retention** — Auto-cleanup after N days

### 🎨 Dashboard
- **Dark theme** — Beautiful dark UI with teal accents
- **System tray** — Runs silently in the background with a tray icon
- **Anti-flicker** — Smart rendering that only updates when data changes
- **Responsive** — Works on any screen size
- **Onboarding wizard** — Guided setup on first launch

---

## Installation

### One-Click Download

Go to [**Releases**](https://github.com/leothefleo49/TypeKeep/releases/latest) and download the executable for your platform:

| Platform | Download |
|----------|----------|
| Windows  | [`TypeKeep-windows.exe`](https://github.com/leothefleo49/TypeKeep/releases/latest) |
| macOS    | [`TypeKeep-macos`](https://github.com/leothefleo49/TypeKeep/releases/latest) |
| Linux    | [`TypeKeep-linux`](https://github.com/leothefleo49/TypeKeep/releases/latest) |
| Android / iOS | [**Mobile Web App**](https://leothefleo49.github.io/TypeKeep/) |

### Quick Start (Python)

```bash
# Clone the repository
git clone https://github.com/leothefleo49/TypeKeep.git
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

---

## Mobile App

TypeKeep includes a **Progressive Web App (PWA)** that works on both Android and iOS. It connects to the same cloud sync as the desktop app.

### Install on Android
1. Open **https://leothefleo49.github.io/TypeKeep/** in Chrome
2. Tap the **⋮** menu → **"Add to Home Screen"** or **"Install App"**
3. The app appears on your home screen like a native app

### Install on iOS
1. Open **https://leothefleo49.github.io/TypeKeep/** in Safari
2. Tap the **Share** button (□↑)  → **"Add to Home Screen"**
3. The app appears on your home screen like a native app

### LAN Access (no cloud needed)
If your phone is on the same network as your desktop:
1. Find your PC's IP address (e.g. `192.168.1.100`)
2. Open `http://192.168.1.100:7700/mobile` on your phone
3. You can access the full dashboard at `http://192.168.1.100:7700/`

---

## Cloud Sync

Cloud sync uses **Supabase** (free tier) to connect all your devices — desktop, Android, iOS — even across different networks.

### Setup (5 minutes, completely free)

1. **Create a Supabase account** at [supabase.com](https://supabase.com) (free)
2. **Create a new project** (any name and password)
3. **Run the setup SQL:**
   - Go to **SQL Editor** → **New Query**
   - Copy the contents of [`supabase_setup.sql`](supabase_setup.sql) and run it
4. **Get your credentials:**
   - Go to **Settings** → **API**
   - Copy your **Project URL** (e.g. `https://xxxxx.supabase.co`)
   - Copy your **anon/public key** (starts with `eyJ...`)
5. **Configure TypeKeep:**
   - Open the TypeKeep dashboard → **Settings** → **Cloud Sync**
   - Paste your Supabase URL and anon key
   - Enter a **Sync Key** (shared passphrase — same on all devices)
   - Enable cloud sync and save
6. **Connect your phone:**
   - Open the [mobile app](https://leothefleo49.github.io/TypeKeep/)
   - Enter the same Supabase URL, anon key, and sync key
   - Done! Your devices are now synced

### What syncs?
| Data | Desktop → Cloud | Cloud → Mobile | Mobile → Cloud | Cloud → Desktop |
|------|:---:|:---:|:---:|:---:|
| Clipboard | ✅ | ✅ | ✅ | ✅ |
| Typing History | ✅ | ✅ | — | — |
| Devices | ✅ | ✅ | ✅ | ✅ |

### Free tier limits
- **500 MB** database storage (plenty for years of clipboard/text data)
- **Unlimited** API requests
- **2 GB** bandwidth per month
- No credit card required

---

## Usage

1. **Launch** — Run `python typekeep.py` or double-click `start.bat`, or run the downloaded executable
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
| **Devices** | Pair and sync with other TypeKeep instances (LAN) |
| **Shortcut Guide** | Reference for common keyboard shortcuts |

---

## Device Sync (LAN)

TypeKeep also supports peer-to-peer sync between devices on the same network (no cloud required).

### Setup

1. Open the **Devices** tab on both devices
2. Set a **device name** and **sync key** (shared passphrase) on both
3. Enable **sync** on both devices
4. On Device A, enter Device B's **IP** and **port** (default: 7700)
5. Click **Pair**

---

## Configuration

Settings are stored in `data/config.json`. Key options:

| Setting | Default | Description |
|---------|---------|-------------|
| `record_keyboard` | `true` | Record keystrokes |
| `record_mouse_clicks` | `true` | Record mouse clicks |
| `record_clipboard` | `true` | Track clipboard changes |
| `default_gap_seconds` | `5` | Time gap to split messages |
| `retention_days` | `30` | Auto-delete events older than N days |
| `cloud_sync_enabled` | `false` | Enable Supabase cloud sync |
| `supabase_url` | `""` | Supabase project URL |
| `supabase_anon_key` | `""` | Supabase anon/public key |
| `cloud_sync_key` | `""` | Shared sync passphrase |
| `sync_enabled` | `false` | Enable LAN device sync |
| `start_on_boot` | `false` | Run on Windows startup |

---

## Building

### Build Executable (PyInstaller)

```bash
pip install pyinstaller

# Windows
pyinstaller --onefile --noconsole --name TypeKeep --add-data "templates;templates" --add-data "static;static" --add-data "mobile;mobile" typekeep.py

# macOS / Linux
pyinstaller --onefile --noconsole --name TypeKeep --add-data "templates:templates" --add-data "static:static" --add-data "mobile:mobile" typekeep.py
```

### Automated Releases

Push a version tag to trigger automatic builds:
```bash
git tag v3.0.0
git push origin v3.0.0
```

Or manually trigger the workflow from the GitHub Actions tab.

---

## Tech Stack

- **Python 3.10+** — Core runtime
- **Flask** — Web server & API
- **pynput** — Keyboard & mouse input capture
- **pystray** — System tray icon
- **Pillow** — Image processing
- **SQLite** — Local database with WAL mode
- **Supabase** — Cloud sync (free tier)
- **PWA** — Mobile app (HTML/CSS/JS)

---

## Project Structure

```
TypeKeep/
├── typekeep.py           # Main entry point
├── config.py             # JSON config manager
├── database.py           # SQLite storage & queries
├── recorder.py           # Input capture (keyboard, mouse)
├── clipboard_monitor.py  # Clipboard change detection
├── server.py             # Flask API server
├── cloud_sync.py         # Supabase cloud sync
├── tray.py               # System tray icon
├── supabase_setup.sql    # Database setup for Supabase
├── requirements.txt      # Python dependencies
├── install.bat           # Windows dependency installer
├── start.bat             # Windows background launcher
├── templates/
│   └── index.html        # Dashboard SPA
├── static/
│   ├── app.js            # Frontend logic
│   └── style.css         # Dark theme stylesheet
├── mobile/               # Mobile PWA companion app
│   ├── index.html        # Mobile app shell
│   ├── app.js            # Mobile app logic
│   ├── style.css         # Mobile styles
│   ├── manifest.json     # PWA manifest
│   ├── sw.js             # Service worker
│   ├── icon-192.png      # App icon
│   └── icon-512.png      # App icon (large)
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
  <strong>TypeKeep v3.0.0</strong> — Your keystrokes, your clipboard, every device, your control.
</p>
