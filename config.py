"""TypeKeep Configuration Manager - JSON-based persistent settings."""

import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
CONFIG_FILE = os.path.join(DATA_DIR, 'config.json')

DEFAULTS = {
    'retention_days': 7,
    'default_gap_seconds': 5,
    'server_port': 7700,
    'cleanup_interval_seconds': 3600,
    'buffer_flush_seconds': 2,
    'buffer_size': 100,
    'record_mouse_clicks': True,
    'record_mouse_scroll': False,
    'min_message_length': 1,
    'max_messages_display': 200,
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
