"""TypeKeep Recorder - captures keyboard & mouse input via pynput."""

import json
import time
import threading
import ctypes
import ctypes.wintypes
import platform

from pynput import keyboard, mouse

# ── Windows active-window detection (ctypes, no pywin32 needed) ──

_IS_WINDOWS = platform.system() == 'Windows'

if _IS_WINDOWS:
    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32
    _psapi = ctypes.windll.psapi

    def _get_active_window_info():
        """Return (window_title, process_name) for the foreground window."""
        try:
            hwnd = _user32.GetForegroundWindow()
            # title
            length = _user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            _user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
            # process
            pid = ctypes.wintypes.DWORD()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            PROCESS_QUERY = 0x0400
            PROCESS_VM = 0x0010
            handle = _kernel32.OpenProcess(PROCESS_QUERY | PROCESS_VM, False, pid.value)
            proc = 'Unknown'
            if handle:
                nbuf = ctypes.create_unicode_buffer(260)
                _psapi.GetModuleBaseNameW(handle, None, nbuf, 260)
                _kernel32.CloseHandle(handle)
                proc = nbuf.value or 'Unknown'
            return title, proc
        except Exception:
            return '', 'Unknown'
else:
    def _get_active_window_info():
        return '', 'Unknown'


# ── Modifier key set ──────────────────────────────────────────────

_MODIFIER_KEYS = {
    keyboard.Key.shift, keyboard.Key.shift_r,
    keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
    keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr,
    keyboard.Key.cmd, keyboard.Key.cmd_r,
}


class Recorder:
    """Listens for keyboard and mouse events, buffers them to the database."""

    def __init__(self, database, config):
        self.db = database
        self.config = config
        self.recording = True
        self._modifiers = set()
        self._kb_listener = None
        self._mouse_listener = None
        self._window_cache = ('', 'Unknown')
        self._window_ts = 0

    # ── Public control ─────────────────────────────────────────────

    def start(self):
        self._kb_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        self._kb_listener.daemon = True
        self._kb_listener.start()

        if self.config.get('record_mouse_clicks', True):
            self._mouse_listener = mouse.Listener(
                on_click=self._on_mouse_click,
                on_scroll=self._on_mouse_scroll if self.config.get('record_mouse_scroll') else None,
            )
            self._mouse_listener.daemon = True
            self._mouse_listener.start()

    def stop(self):
        if self._kb_listener:
            self._kb_listener.stop()
        if self._mouse_listener:
            self._mouse_listener.stop()

    # ── Window detection (cached 150 ms) ───────────────────────────

    def _active_window(self):
        now = time.time()
        if now - self._window_ts > 0.15:
            try:
                self._window_cache = _get_active_window_info()
            except Exception:
                pass
            self._window_ts = now
        return self._window_cache

    # ── Keyboard callbacks ─────────────────────────────────────────

    def _on_key_press(self, key):
        if not self.recording:
            return

        # Track modifier state
        if key in _MODIFIER_KEYS:
            self._modifiers.add(key)
            return  # don't log bare modifier presses

        try:
            char = key.char
            key_name = key.char if key.char else str(key)
        except AttributeError:
            char = None
            key_name = str(key)

        mod_str = ','.join(
            str(m).replace('Key.', '') for m in self._modifiers
        ) if self._modifiers else ''

        title, proc = self._active_window()

        self.db.buffer_event({
            'timestamp': time.time(),
            'event_type': 'key_press',
            'key_name': key_name,
            'character': char,
            'modifiers': mod_str,
            'window_title': title,
            'window_process': proc,
            'extra': None,
        })

    def _on_key_release(self, key):
        self._modifiers.discard(key)

    # ── Mouse callbacks ────────────────────────────────────────────

    def _on_mouse_click(self, x, y, button, pressed):
        if not self.recording or not pressed:
            return

        title, proc = self._active_window()
        self.db.buffer_event({
            'timestamp': time.time(),
            'event_type': 'mouse_click',
            'key_name': str(button),
            'character': None,
            'modifiers': None,
            'window_title': title,
            'window_process': proc,
            'extra': json.dumps({'x': x, 'y': y}),
        })

    def _on_mouse_scroll(self, x, y, dx, dy):
        if not self.recording:
            return

        title, proc = self._active_window()
        self.db.buffer_event({
            'timestamp': time.time(),
            'event_type': 'mouse_scroll',
            'key_name': None,
            'character': None,
            'modifiers': None,
            'window_title': title,
            'window_process': proc,
            'extra': json.dumps({'x': x, 'y': y, 'dx': dx, 'dy': dy}),
        })
