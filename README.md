# TypeKeep

A lightweight, local keystroke & input logger with a modern web dashboard.  
Runs silently in your system tray and records everything you type — then lets you search, filter, and copy from a sleek dark-themed UI.

---

## Features

- **Always-on background recording** — keyboard, mouse clicks, and (optionally) scroll events
- **Active window detection** — captures which app/window each keystroke belongs to
- **Smart message grouping** — adjustable time-gap splitting (1 s → 5 min)
- **7-day default retention** with configurable cleanup
- **One-click copy** on any past message
- **Search, filter, sort** — by time range, app, session gap, keyword
- **Raw-key toggle** — see backspaces (`⌫`), enters (`↵`), shortcuts (`[Ctrl+c]`)
- **System tray** — pause/resume recording, open dashboard, quit
- **SQLite + WAL mode** — rock-solid, zero-config database
- **< 30 MB RAM** typical usage

## Quick Start

```
1.  Run  install.bat        (installs Python dependencies)
2.  Run  start.bat          (launches TypeKeep to the system tray)
3.  Open http://127.0.0.1:7700  or click the tray icon
```

### Manual start

```bash
pip install -r requirements.txt
python typekeep.py
```

## Dashboard Controls

| Control | What it does |
|---------|-------------|
| **Time range** dropdown | Show last 1 h / 6 h / 24 h / 3 d / 7 d / all |
| **Gap** dropdown | How many seconds of silence splits one "message" from the next |
| **App** dropdown | Filter to a specific application |
| **Sort** | Newest or oldest first |
| **Raw keys** toggle | Show literal keypresses including backspaces & shortcuts |
| **Search** | Full-text search across all messages |
| **Copy** button (📋) | Copies that message's text to your clipboard |

## Settings (gear icon)

- **Retention days** — how long to keep data (default 7)
- **Default gap** — session split threshold in seconds
- **Min message length** — hide very short messages
- **Record mouse clicks / scroll** — toggle mouse event logging

## Files

```
TypeKeep/
├── typekeep.py        Main entry point
├── recorder.py        pynput keyboard + mouse listener
├── database.py        SQLite storage & message grouping
├── server.py          Flask API + web server
├── tray.py            System tray icon (pystray)
├── config.py          JSON settings manager
├── requirements.txt   Python dependencies
├── install.bat        One-click dependency installer
├── start.bat          One-click launcher
├── data/              (auto-created)
│   ├── typekeep.db    SQLite database
│   └── config.json    Persisted settings
├── templates/
│   └── index.html     Dashboard HTML
└── static/
    ├── style.css      Dark-theme styles
    └── app.js         Frontend SPA
```

## Privacy & Security

- **100 % local** — nothing leaves your machine; no network calls, no telemetry.
- The Flask server binds to `127.0.0.1` only (not accessible from other devices).
- Keystrokes **include passwords**. Use the tray's **Pause** button when entering sensitive data, or keep the database secured.

## Requirements

- Windows 10/11
- Python 3.10+
- ~30 MB RAM while running

## License

Personal use / MIT — do whatever you want with it.
