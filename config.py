"""TypeKeep Configuration Manager - Atomic JSON-based persistent settings
with backup on every save to prevent data loss."""

import json
import os
import shutil
import threading
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
CONFIG_FILE = os.path.join(DATA_DIR, 'config.json')
CONFIG_BACKUP = os.path.join(DATA_DIR, 'config.backup.json')

APP_VERSION = '3.2.0'

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
    'split_on_enter': True,
    'context_aware_grouping': True,
    'smart_enter': True,

    # Display
    'min_message_length': 1,
    'max_messages_display': 200,

    # Retention & backup
    'retention_days': 30,
    'server_port': 7700,
    'cleanup_interval_seconds': 3600,
    'buffer_flush_seconds': 2,
    'auto_save_interval': 1,
    'auto_backup_enabled': True,

    # Startup
    'start_on_boot': True,
    'start_background_on_boot': True,
    'start_ui_on_boot': False,
    'start_minimized': True,
    'show_onboarding': True,

    # Clipboard
    'record_clipboard': True,
    'clipboard_poll_seconds': 1.25,
    'clipboard_retention_days': 30,

    # Sync
    'device_id': '',
    'device_name': '',
    'sync_key': '',
    'sync_enabled': False,
    'clipboard_sync': False,
    'paired_devices': [],

    # Cloud Sync (Supabase)
    'cloud_sync_enabled': False,
    'supabase_url': 'https://tnbxhpgrtekshowzfdrg.supabase.co',
    'supabase_anon_key': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRuYnhocGdydGVrc2hvd3pmZHJnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzExNzAzMzYsImV4cCI6MjA4Njc0NjMzNn0.2GfWPX6ryh_KHAURH4xlmdT4liqFpE01zPnB6Mlbn7E',
    'cloud_sync_key': '',
    'cloud_sync_clipboard': True,
    'cloud_sync_messages': True,
    'cloud_sync_interval_seconds': 30,

    # Theme
    'theme': 'dark',
}


class Config:
    """Thread-safe JSON configuration with atomic writes and auto-backup."""

    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self._config = dict(DEFAULTS)
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        loaded = False
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                self._config.update(saved)
                loaded = True
            except (json.JSONDecodeError, IOError, OSError):
                pass

        if not loaded and os.path.exists(CONFIG_BACKUP):
            try:
                with open(CONFIG_BACKUP, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                self._config.update(saved)
                self._save()
            except (json.JSONDecodeError, IOError, OSError):
                pass

    def _save(self):
        try:
            tmp = CONFIG_FILE + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            shutil.move(tmp, CONFIG_FILE)
            try:
                shutil.copy2(CONFIG_FILE, CONFIG_BACKUP)
            except Exception:
                pass
        except (IOError, OSError) as e:
            print(f"[TypeKeep] Config save error: {e}")

    def get(self, key, default=None):
        with self._lock:
            return self._config.get(key, default if default is not None else DEFAULTS.get(key))

    def set(self, key, value):
        with self._lock:
            self._config[key] = value
            self._save()

    def update(self, data: dict):
        with self._lock:
            self._config.update(data)
            self._save()

    def to_dict(self):
        with self._lock:
            result = dict(self._config)
            result['app_version'] = APP_VERSION
            return result
