"""TypeKeep Recorder - captures keyboard, mouse, shortcuts, and notifications."""

import json
import time
import threading
import platform

from pynput import keyboard, mouse

# ── Windows active-window detection ───────────────────────────

_IS_WINDOWS = platform.system() == 'Windows'

if _IS_WINDOWS:
    import ctypes
    import ctypes.wintypes
    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32
    _psapi = ctypes.windll.psapi

    def _get_active_window_info():
        try:
            hwnd = _user32.GetForegroundWindow()
            length = _user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            _user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
            pid = ctypes.wintypes.DWORD()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            handle = _kernel32.OpenProcess(0x0400 | 0x0010, False, pid.value)
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

# ── Modifier key set ──────────────────────────────────────────

_MODIFIER_KEYS = {
    keyboard.Key.shift, keyboard.Key.shift_r,
    keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
    keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr,
    keyboard.Key.cmd, keyboard.Key.cmd_r,
}

# Shortcut-worthy modifier combos
_SHORTCUT_MODS = {'ctrl_l', 'ctrl_r', 'alt_l', 'alt_r', 'cmd', 'cmd_r'}


class Recorder:
    """Listens for keyboard, mouse, and shortcut events."""

    def __init__(self, database, config):
        self.db = database
        self.config = config
        self.recording = True
        self._modifiers = set()
        self._kb_listener = None
        self._mouse_listener = None
        self._move_thread = None
        self._window_cache = ('', 'Unknown')
        self._window_ts = 0
        self._last_move_pos = (0, 0)
        self._last_move_ts = 0
        self._last_window_title = ''

    # ── Control ────────────────────────────────────────────────

    def start(self):
        self._kb_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        self._kb_listener.daemon = True
        self._kb_listener.start()

        record_clicks = self.config.get('record_mouse_clicks', True)
        record_scroll = self.config.get('record_mouse_scroll', False)
        record_move = self.config.get('record_mouse_movement', False)

        if record_clicks or record_scroll or record_move:
            self._mouse_listener = mouse.Listener(
                on_click=self._on_mouse_click if record_clicks else None,
                on_scroll=self._on_mouse_scroll if record_scroll else None,
                on_move=self._on_mouse_move if record_move else None,
            )
            self._mouse_listener.daemon = True
            self._mouse_listener.start()

        # Notification detection thread
        if self.config.get('record_notifications', True) and _IS_WINDOWS:
            self._start_notification_watcher()

    def stop(self):
        if self._kb_listener:
            self._kb_listener.stop()
        if self._mouse_listener:
            self._mouse_listener.stop()

    # ── Window detection (cached 100ms) ────────────────────────

    def _active_window(self):
        now = time.time()
        if now - self._window_ts > 0.1:
            try:
                self._window_cache = _get_active_window_info()
            except Exception:
                pass
            self._window_ts = now
        return self._window_cache

    # ── Keyboard ───────────────────────────────────────────────

    def _on_key_press(self, key):
        if not self.recording:
            return

        if key in _MODIFIER_KEYS:
            self._modifiers.add(key)
            return

        try:
            char = key.char
            key_name = key.char if key.char else str(key)
        except AttributeError:
            char = None
            key_name = str(key)

        mod_names = set()
        for m in self._modifiers:
            mod_names.add(str(m).replace('Key.', ''))

        mod_str = ','.join(sorted(mod_names)) if mod_names else ''
        title, proc = self._active_window()

        # Detect shortcuts (Ctrl/Alt/Cmd + key)
        is_shortcut = bool(mod_names & _SHORTCUT_MODS) and self.config.get('record_shortcuts', True)

        if is_shortcut:
            self.db.buffer_event({
                'timestamp': time.time(),
                'event_type': 'shortcut',
                'key_name': key_name,
                'character': char,
                'modifiers': mod_str,
                'window_title': title,
                'window_process': proc,
                'extra': None,
            })

        # Always also log as key_press for text reconstruction
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

    # ── Mouse ──────────────────────────────────────────────────

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

    def _on_mouse_move(self, x, y):
        if not self.recording:
            return
        now = time.time()
        sample_ms = self.config.get('mouse_sample_ms', 500)
        if (now - self._last_move_ts) * 1000 < sample_ms:
            return
        self._last_move_ts = now
        self._last_move_pos = (x, y)
        title, proc = self._active_window()
        self.db.buffer_event({
            'timestamp': now,
            'event_type': 'mouse_move',
            'key_name': None,
            'character': None,
            'modifiers': None,
            'window_title': title,
            'window_process': proc,
            'extra': json.dumps({'x': x, 'y': y}),
        })

    # ── Notification watcher (Windows) ─────────────────────────

    def _start_notification_watcher(self):
        def _watch():
            last_title = ''
            while self.recording:
                try:
                    title, proc = _get_active_window_info()
                    # Detect notification-related windows
                    lower_proc = (proc or '').lower()
                    lower_title = (title or '').lower()
                    is_notif = (
                        'notification' in lower_title
                        or 'toast' in lower_title
                        or lower_proc in ('shellexperiencehost.exe',
                                          'systemsettings.exe')
                    )
                    if is_notif and title != last_title and title:
                        self.db.buffer_event({
                            'timestamp': time.time(),
                            'event_type': 'notification',
                            'key_name': None,
                            'character': None,
                            'modifiers': None,
                            'window_title': title,
                            'window_process': proc,
                            'extra': None,
                        })
                    last_title = title
                except Exception:
                    pass
                time.sleep(1)

        t = threading.Thread(target=_watch, daemon=True, name='notif-watcher')
        t.start()

    # ── Macro execution ────────────────────────────────────────

    def run_macro(self, actions):
        """Execute a list of macro actions. Pauses recording to avoid feedback."""
        was_recording = self.recording
        self.recording = False
        try:
            kb = keyboard.Controller()
            ms = mouse.Controller()
            key_map = self._build_key_map()

            for action in actions:
                atype = action.get('type', '')
                if atype == 'hotkey':
                    keys = action.get('keys', [])
                    resolved = [key_map.get(k, k) for k in keys]
                    for k in resolved:
                        if isinstance(k, str) and len(k) == 1:
                            kb.press(k)
                        else:
                            kb.press(k)
                    for k in reversed(resolved):
                        if isinstance(k, str) and len(k) == 1:
                            kb.release(k)
                        else:
                            kb.release(k)
                elif atype == 'type':
                    text = action.get('text', '')
                    kb.type(text)
                elif atype == 'delay':
                    time.sleep(action.get('ms', 100) / 1000)
                elif atype == 'key':
                    k = key_map.get(action.get('key', ''), action.get('key', ''))
                    act = action.get('action', 'tap')
                    if act == 'press':
                        kb.press(k)
                    elif act == 'release':
                        kb.release(k)
                    else:
                        kb.press(k); kb.release(k)
                elif atype == 'click':
                    x = action.get('x', 0)
                    y = action.get('y', 0)
                    btn_name = action.get('button', 'left')
                    btn = mouse.Button.left if btn_name == 'left' else mouse.Button.right
                    ms.position = (x, y)
                    ms.click(btn)
        except Exception as exc:
            print(f"[TypeKeep] Macro error: {exc}")
        finally:
            self.recording = was_recording

    @staticmethod
    def _build_key_map():
        return {
            'ctrl': keyboard.Key.ctrl_l,
            'ctrl_l': keyboard.Key.ctrl_l,
            'ctrl_r': keyboard.Key.ctrl_r,
            'shift': keyboard.Key.shift,
            'shift_l': keyboard.Key.shift,
            'shift_r': keyboard.Key.shift_r,
            'alt': keyboard.Key.alt_l,
            'alt_l': keyboard.Key.alt_l,
            'alt_r': keyboard.Key.alt_r,
            'cmd': keyboard.Key.cmd,
            'win': keyboard.Key.cmd,
            'esc': keyboard.Key.esc,
            'escape': keyboard.Key.esc,
            'enter': keyboard.Key.enter,
            'return': keyboard.Key.enter,
            'tab': keyboard.Key.tab,
            'space': keyboard.Key.space,
            'backspace': keyboard.Key.backspace,
            'delete': keyboard.Key.delete,
            'up': keyboard.Key.up,
            'down': keyboard.Key.down,
            'left': keyboard.Key.left,
            'right': keyboard.Key.right,
            'home': keyboard.Key.home,
            'end': keyboard.Key.end,
            'f1': keyboard.Key.f1, 'f2': keyboard.Key.f2,
            'f3': keyboard.Key.f3, 'f4': keyboard.Key.f4,
            'f5': keyboard.Key.f5, 'f6': keyboard.Key.f6,
            'f7': keyboard.Key.f7, 'f8': keyboard.Key.f8,
            'f9': keyboard.Key.f9, 'f10': keyboard.Key.f10,
            'f11': keyboard.Key.f11, 'f12': keyboard.Key.f12,
            'insert': keyboard.Key.insert,
            'page_up': keyboard.Key.page_up,
            'page_down': keyboard.Key.page_down,
            'print_screen': keyboard.Key.print_screen,
        }
