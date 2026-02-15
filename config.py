"""TypeKeep Configuration Manager - JSON-based persistent settings."""

import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
CONFIG_FILE = os.path.join(DATA_DIR, 'config.json')

DEFAULTS = {
    # Recording
    'record_keyboard': True,
    'record_mouse_clicks': True,
    'record_mouse_scroll': False,
    'record_mouse_movement': False,
    'record_shortcuts': True,
    'record_notifications': True,
    'mouse_sample_ms': 500,

    # Grouping
    'default_gap_seconds': 5,
    'same_window_gap_seconds': 30,
    'split_on_enter': False,

    # Display
    'min_message_length': 1,
    'max_messages_display': 200,

    # Retention & backup
    'retention_days': 30,
    'server_port': 7700,
    'cleanup_interval_seconds': 3600,
    'buffer_flush_seconds': 1,
    'auto_save_interval': 1,

    # Startup
    'start_on_boot': False,
    'start_minimized': True,
    'show_onboarding': True,

    # Clipboard
    'record_clipboard': True,
    'clipboard_retention_days': 30,

    # Sync
    'device_id': '',
    'device_name': '',
    'sync_key': '',
    'sync_enabled': False,
    'clipboard_sync': False,
    'paired_devices': [],           # [{ id, name, ip, port, clipboard_sync }]

    # Backup (stubs)
    'backup_enabled': False,
    'backup_service': 'none',        # none / gdrive / onedrive
    'backup_interval_minutes': 60,

    # Theme
    'theme': 'dark',
}


class Config:
    """Thread-safe JSON configuration with auto-persistence."""

    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self._config = dict(DEFAULTS)
        self._load()

    def _load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                self._config.update(saved)
            except (json.JSONDecodeError, IOError, OSError):
                pass

    def _save(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2)
        except (IOError, OSError) as e:
            print(f"[TypeKeep] Config save error: {e}")

    def get(self, key, default=None):
        return self._config.get(key, default if default is not None else DEFAULTS.get(key))

    def set(self, key, value):
        self._config[key] = value
        self._save()

    def update(self, data: dict):
        self._config.update(data)
        self._save()

    def to_dict(self):
        return dict(self._config)
