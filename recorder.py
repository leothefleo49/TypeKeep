"""TypeKeep Recorder - captures keyboard, mouse, shortcuts, and notifications.

Overhauled v3.4.0:
- Hook callbacks remain strictly non-blocking enqueue-only (microseconds).
- Windows physical modifier resync via GetAsyncKeyState eliminates stuck
  Ctrl/Alt/Shift/Win modifiers after Alt+Tab, Win+L, or UAC prompts.
- Control-character normalization (e.g. Ctrl+A -> 'a' instead of '\\x01').
- Event-driven idle-quiet writer loop: blocks up to 5s with 0 wakeups when
  no events are queued/buffered, draining zero battery when idle.
- Resilient notification watcher: stays alive across pause/macro cycles with
  adaptive idle polling and captures actual toast title/process.
- Live global macro hotkey triggering from saved macros.
"""

import json
import platform
import queue
import threading
import time

from pynput import keyboard, mouse

_IS_WINDOWS = platform.system() == 'Windows'

if _IS_WINDOWS:
    import ctypes
    import ctypes.wintypes

    class _LASTINPUTINFO(ctypes.Structure):
        _fields_ = [('cbSize', ctypes.wintypes.UINT),
                    ('dwTime', ctypes.wintypes.DWORD)]

    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32
    _psapi = ctypes.windll.psapi

    _user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    _user32.GetAsyncKeyState.restype = ctypes.c_short
    _user32.GetLastInputInfo.argtypes = [ctypes.POINTER(_LASTINPUTINFO)]
    _user32.GetLastInputInfo.restype = ctypes.wintypes.BOOL
    _kernel32.GetTickCount.argtypes = []
    _kernel32.GetTickCount.restype = ctypes.wintypes.DWORD

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

    def _get_idle_seconds() -> float:
        try:
            lii = _LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(_LASTINPUTINFO)
            if _user32.GetLastInputInfo(ctypes.byref(lii)):
                tick = _kernel32.GetTickCount()
                return max(0.0, ((tick - lii.dwTime) & 0xFFFFFFFF) / 1000.0)
        except Exception:
            pass
        return 0.0
else:
    def _get_active_window_info():
        return '', 'Unknown'

    def _get_idle_seconds() -> float:
        return 0.0

# ── Modifier key set ──────────────────────────────────────────

_MODIFIER_KEYS = {
    keyboard.Key.shift, keyboard.Key.shift_r,
    keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
    keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr,
    keyboard.Key.cmd, keyboard.Key.cmd_r,
}

# Shortcut-worthy modifier combos
_SHORTCUT_MODS = {'ctrl_l', 'ctrl_r', 'alt_l', 'alt_r', 'cmd', 'cmd_r'}

# Windows virtual-key checks to clear stuck modifiers if key-release was swallowed
_WIN_MOD_VK_GROUPS = (
    (0x11, (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r)),               # VK_CONTROL
    (0x12, (keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr)),  # VK_MENU
    (0x10, (keyboard.Key.shift, keyboard.Key.shift_r)),               # VK_SHIFT
    (0x5B, (keyboard.Key.cmd,)),                                      # VK_LWIN
    (0x5C, (keyboard.Key.cmd_r,)),                                    # VK_RWIN
)

# Canonical modifier aliases for macro shortcut matching
_MOD_ALIAS = {
    'ctrl_l': 'ctrl', 'ctrl_r': 'ctrl', 'control': 'ctrl',
    'alt_l': 'alt', 'alt_r': 'alt', 'alt_gr': 'alt',
    'shift_l': 'shift', 'shift_r': 'shift',
    'cmd': 'win', 'cmd_r': 'win', 'super': 'win', 'meta': 'win',
}

# ── Safety limits ─────────────────────────────────────────────

_QUEUE_MAX = 20000          # hook queue ceiling; unprotected dropped first
_STORM_EVENTS_PER_SEC = 80  # sustained rate above this = flood (unprotected only)
_STORM_BURST = 200          # instantaneous burst allowance
_PROTECTED_TYPES = frozenset({'key_press', 'shortcut'})
_MACRO_LOCK = threading.Lock()
_MACRO_MAX_ACTIONS = 300    # refuse absurdly large macros
_MACRO_MIN_INTERVAL = 0.025 # min seconds between injected key actions
_MACRO_SETTLE = 0.3         # seconds to keep recording paused after a macro


def _normalize_shortcut_combo(shortcut_str: str):
    """Parse 'ctrl+shift+t' -> frozenset({'ctrl', 'shift', 't'}) or None."""
    if not shortcut_str or not isinstance(shortcut_str, str):
        return None
    parts = [p.strip().lower() for p in shortcut_str.replace('-', '+').split('+') if p.strip()]
    if not parts:
        return None
    normalized = frozenset(_MOD_ALIAS.get(p, p) for p in parts)
    return normalized if normalized else None


class Recorder:
    """Listens for keyboard, mouse, and shortcut events."""

    def __init__(self, database, config):
        self.db = database
        self.config = config
        self.recording = True
        self._modifiers = set()
        self._kb_listener = None
        self._mouse_listener = None
        self._window_cache = ('', 'Unknown')
        self._window_ts = 0
        self._last_move_pos = (0, 0)
        self._last_move_ts = 0
        # hook -> writer pipeline
        self._q = queue.Queue()
        self._stop_evt = threading.Event()
        self._writer = None
        self._notif_thread = None
        # storm guard state
        self._storm_tokens = float(_STORM_BURST)
        self._storm_ts = time.time()
        self._dropped = 0
        # macro hotkey lookup cache
        self._macro_hotkeys = {}   # frozenset(tokens) -> macro dict
        self._macro_lock_state = threading.Lock()
        self._macro_running = False
        self.reload_macros()

    # ── Macro Hotkey Cache ─────────────────────────────────────

    def reload_macros(self):
        """Refresh the hotkey -> macro lookup table from the database."""
        table = {}
        try:
            for m in self.db.get_macros():
                combo = _normalize_shortcut_combo(m.get('shortcut', ''))
                if combo and len(combo) >= 2:
                    actions = m.get('actions', '[]')
                    if isinstance(actions, str):
                        try:
                            actions = json.loads(actions)
                        except Exception:
                            actions = []
                    if isinstance(actions, list) and actions:
                        table[combo] = {'id': m['id'], 'actions': actions}
        except Exception:
            pass
        with self._macro_lock_state:
            self._macro_hotkeys = table

    def _maybe_trigger_macro_hotkey(self, mod_names, key_name):
        if self._macro_running:
            return
        mods = {_MOD_ALIAS.get(m, m) for m in mod_names}
        k = (key_name or '').replace('Key.', '').strip().lower()
        if not k or not mods:
            return
        combo = frozenset(mods | {k})
        with self._macro_lock_state:
            macro = self._macro_hotkeys.get(combo)
        if macro:
            threading.Thread(
                target=self.run_macro,
                args=(macro['actions'], macro['id']),
                daemon=True,
                name=f"macro-hk-{macro['id']}",
            ).start()

    # ── Control ────────────────────────────────────────────────

    def start(self):
        self._stop_evt.clear()
        self.reload_macros()
        try:
            self._kb_listener = keyboard.Listener(
                on_press=self._on_key_press,
                on_release=self._on_key_release,
            )
            self._kb_listener.daemon = True
            self._kb_listener.start()
        except Exception as exc:
            print(f"[TypeKeep] Keyboard listener failed to start: {exc}")

        try:
            self._mouse_listener = mouse.Listener(
                on_click=self._on_mouse_click,
                on_scroll=self._on_mouse_scroll,
                on_move=(self._on_mouse_move
                         if self.config.get('record_mouse_movement', False)
                         else None),
            )
            self._mouse_listener.daemon = True
            self._mouse_listener.start()
        except Exception as exc:
            print(f"[TypeKeep] Mouse listener failed to start: {exc}")

        if _IS_WINDOWS:
            self._start_notification_watcher()

        self._writer = threading.Thread(
            target=self._writer_loop, daemon=True, name='rec-writer')
        self._writer.start()

    def stop(self):
        self._stop_evt.set()
        if self._kb_listener:
            self._kb_listener.stop()
        if self._mouse_listener:
            self._mouse_listener.stop()
        if self._writer:
            self._writer.join(timeout=2)

    # ── Storm guard (writer side decision, cheap counters) ──────

    def _allow_event(self, event_type=None):
        """Token bucket: True if within burst/sustained rate."""
        if event_type in _PROTECTED_TYPES or event_type == 'notification':
            return True
        now = time.time()
        self._storm_tokens = min(
            _STORM_BURST,
            self._storm_tokens + (now - self._storm_ts) * _STORM_EVENTS_PER_SEC)
        self._storm_ts = now
        if self._storm_tokens >= 1.0:
            self._storm_tokens -= 1.0
            return True
        self._dropped += 1
        return False

    # ── Physical Modifier Reconciliation ───────────────────────

    def _sync_physical_modifiers(self):
        """Discard any stuck modifiers that Windows says are no longer pressed."""
        if not _IS_WINDOWS or not self._modifiers:
            return
        try:
            for vk, mod_tuple in _WIN_MOD_VK_GROUPS:
                if not (_user32.GetAsyncKeyState(vk) & 0x8000):
                    for m in mod_tuple:
                        self._modifiers.discard(m)
        except Exception:
            pass

    @staticmethod
    def _decode_key(key, has_ctrl: bool):
        """Extract clean (char, key_name), fixing Ctrl+A..Z control codes on Windows."""
        try:
            char = key.char
            key_name = key.char if key.char else str(key)
        except AttributeError:
            char = None
            key_name = str(key)

        if has_ctrl:
            if char and len(char) == 1 and 1 <= ord(char) <= 26:
                decoded = chr(ord(char) + 96)
                char = decoded
                key_name = decoded
            elif not char or (len(char) == 1 and ord(char) < 32):
                vk = getattr(key, 'vk', None)
                if isinstance(vk, int):
                    if 65 <= vk <= 90:
                        decoded = chr(vk + 32)
                        char = decoded
                        key_name = decoded
                    elif 48 <= vk <= 57:
                        decoded = chr(vk)
                        char = decoded
                        key_name = decoded
        return char, key_name

    # ── Hook callbacks: FAST, no exceptions, no I/O ─────────────

    def _on_key_press(self, key):
        try:
            if not self.recording or not self.config.get('record_keyboard', True):
                return
            if key in _MODIFIER_KEYS:
                self._modifiers.add(key)
                return

            self._sync_physical_modifiers()
            mod_names = {str(m).replace('Key.', '') for m in self._modifiers}
            has_ctrl = bool(mod_names & {'ctrl_l', 'ctrl_r'})
            char, key_name = self._decode_key(key, has_ctrl)
            mod_str = ','.join(sorted(mod_names)) if mod_names else ''

            is_shortcut = (bool(mod_names & _SHORTCUT_MODS)
                           and self.config.get('record_shortcuts', True))

            if mod_names & _SHORTCUT_MODS:
                self._maybe_trigger_macro_hotkey(mod_names, key_name)

            self._enqueue('shortcut' if is_shortcut else 'key_press', {
                'key_name': key_name,
                'character': char,
                'modifiers': mod_str,
            })
        except Exception:
            pass

    def _on_key_release(self, key):
        try:
            self._modifiers.discard(key)
        except Exception:
            pass

    def _on_mouse_click(self, x, y, button, pressed):
        try:
            if not self.recording or not pressed:
                return
            if not self.config.get('record_mouse_clicks', True):
                return
            self._enqueue('mouse_click', {
                'key_name': str(button),
                'character': None,
                'modifiers': None,
                'extra': json.dumps({'x': x, 'y': y}),
            })
        except Exception:
            pass

    def _on_mouse_scroll(self, x, y, dx, dy):
        try:
            if not self.recording:
                return
            if not self.config.get('record_mouse_scroll', False):
                return
            self._enqueue('mouse_scroll', {
                'key_name': None,
                'character': None,
                'modifiers': None,
                'extra': json.dumps({'x': x, 'y': y, 'dx': dx, 'dy': dy}),
            })
        except Exception:
            pass

    def _on_mouse_move(self, x, y):
        try:
            if not self.recording:
                return
            now = time.time()
            sample_ms = self.config.get('mouse_sample_ms', 500)
            if (now - self._last_move_ts) * 1000 < sample_ms:
                return
            self._last_move_ts = now
            self._last_move_pos = (x, y)
            self._enqueue('mouse_move', {
                'key_name': None,
                'character': None,
                'modifiers': None,
                'extra': json.dumps({'x': x, 'y': y}),
            })
        except Exception:
            pass

    def _enqueue(self, event_type, fields):
        """Non-blocking enqueue with ceiling; drops unprotected oldest when full."""
        evt = dict(fields)
        evt.setdefault('timestamp', time.time())
        evt['event_type'] = event_type
        evt.setdefault('extra', None)
        try:
            if self._q.qsize() >= _QUEUE_MAX:
                if evt.get('event_type') not in _PROTECTED_TYPES:
                    self._dropped += 1
                    return
                try:
                    self._q.get_nowait()
                    self._dropped += 1
                except queue.Empty:
                    pass
            self._q.put_nowait(evt)
        except Exception:
            pass

    # ── Writer: the only place input events touch the DB ────────

    def _active_window(self):
        now = time.time()
        if now - self._window_ts > 0.1:
            try:
                self._window_cache = _get_active_window_info()
            except Exception:
                pass
            self._window_ts = now
        return self._window_cache

    def _writer_loop(self):
        last_flush = time.time()
        last_dropped_log = 0
        while not self._stop_evt.is_set():
            flush_sec = max(0.5, float(self.config.get('buffer_flush_seconds', 2) or 2))
            buf_len = self.db.buffer_size()
            # When buffer is empty, wait up to 5s (zero wakeups while PC is idle);
            # when buffer has un-flushed events, wake cleanly at flush deadline.
            wait_timeout = min(0.5, flush_sec) if buf_len > 0 else 5.0
            try:
                evt = self._q.get(timeout=wait_timeout)
            except queue.Empty:
                evt = None

            if evt is not None and self._allow_event(evt.get('event_type')):
                if 'window_title' not in evt or 'window_process' not in evt:
                    title, proc = self._active_window()
                    evt.setdefault('window_title', title)
                    evt.setdefault('window_process', proc)
                try:
                    self.db.buffer_event(evt)
                except Exception as exc:
                    print(f"[TypeKeep] DB buffer error: {exc}")

                # Drain immediately available queued events before checking flush
                drained = 0
                while drained < 250:
                    try:
                        nxt = self._q.get_nowait()
                    except queue.Empty:
                        break
                    drained += 1
                    if self._allow_event(nxt.get('event_type')):
                        if 'window_title' not in nxt or 'window_process' not in nxt:
                            title, proc = self._active_window()
                            nxt.setdefault('window_title', title)
                            nxt.setdefault('window_process', proc)
                        try:
                            self.db.buffer_event(nxt)
                        except Exception as exc:
                            print(f"[TypeKeep] DB buffer error: {exc}")

            now = time.time()
            cur_buf = self.db.buffer_size()
            if cur_buf > 0 and ((now - last_flush >= flush_sec) or cur_buf >= 150):
                last_flush = now
                try:
                    self.db.flush_buffer()
                except Exception as exc:
                    print(f"[TypeKeep] DB flush error: {exc}")
            elif cur_buf == 0:
                last_flush = now

            if self._dropped and now - last_dropped_log > 30:
                print(f"[TypeKeep] Input flood guard: dropped {self._dropped} events")
                self._dropped = 0
                last_dropped_log = now

    # ── Notification watcher (Windows) ─────────────────────────

    def _start_notification_watcher(self):
        if self._notif_thread and self._notif_thread.is_alive():
            return

        def _watch():
            last_title = ''
            while not self._stop_evt.is_set():
                try:
                    if self.recording and self.config.get('record_notifications', True):
                        title, proc = _get_active_window_info()
                        lower_proc = (proc or '').lower()
                        lower_title = (title or '').lower()
                        is_notif = (
                            'notification' in lower_title
                            or 'toast' in lower_title
                            or lower_proc in ('shellexperiencehost.exe',
                                              'systemsettings.exe')
                        )
                        if is_notif and title != last_title and title:
                            self._enqueue('notification', {
                                'key_name': 'notification',
                                'character': None,
                                'modifiers': None,
                                'window_title': title,
                                'window_process': proc,
                                'extra': json.dumps({'title': title, 'process': proc}),
                            })
                        last_title = title
                except Exception:
                    pass
                idle = _get_idle_seconds()
                sleep_s = 5.0 if (not self.recording or idle > 60.0) else 1.5
                self._stop_evt.wait(sleep_s)

        self._notif_thread = threading.Thread(
            target=_watch, daemon=True, name='notif-watcher')
        self._notif_thread.start()

    # ── Macro execution (hardened) ─────────────────────────────

    @staticmethod
    def _resolve_key(name):
        """Return a pynput key for a known name or single printable char,
        else None (refuse to inject unknown keys)."""
        if not isinstance(name, str):
            return None
        km = Recorder._build_key_map()
        k = km.get(name.strip().lower())
        if k is not None:
            return k
        if len(name) == 1 and name.isprintable():
            return name
        return None

    def run_macro(self, actions, macro_id=None):
        """Execute a macro with strict validation and rate limiting."""
        if not isinstance(actions, list) or not actions:
            print("[TypeKeep] Macro refused: empty or invalid action list")
            return
        if len(actions) > _MACRO_MAX_ACTIONS:
            print(f"[TypeKeep] Macro refused: {len(actions)} actions "
                  f"exceeds cap of {_MACRO_MAX_ACTIONS}")
            return
        if not _MACRO_LOCK.acquire(blocking=False):
            print("[TypeKeep] Macro refused: another macro is already running")
            return
        was_recording = self.recording
        self.recording = False
        self._macro_running = True
        label = f"macro {macro_id}" if macro_id is not None else "macro"
        injected = 0
        skipped = 0
        try:
            kb = keyboard.Controller()
            ms = mouse.Controller()

            def _paced(fn, *a):
                nonlocal injected
                time.sleep(_MACRO_MIN_INTERVAL)
                fn(*a)
                injected += 1

            for action in actions:
                if not isinstance(action, dict):
                    skipped += 1
                    continue
                atype = action.get('type', '')
                if atype == 'hotkey':
                    keys = action.get('keys', [])
                    resolved = [self._resolve_key(k) for k in keys]
                    pairs = [(orig, r) for orig, r in zip(keys, resolved)]
                    resolved = [r for r in resolved if r is not None]
                    skipped += sum(1 for _, r in pairs if r is None)
                    if not resolved:
                        continue
                    for k in resolved:
                        _paced(kb.press, k)
                    for k in reversed(resolved):
                        _paced(kb.release, k)
                elif atype == 'type':
                    text = action.get('text', '')
                    if isinstance(text, str) and text:
                        for ch in text[:_MACRO_MAX_ACTIONS]:
                            if ch.isprintable():
                                _paced(kb.tap, ch)
                            else:
                                skipped += 1
                elif atype == 'delay':
                    time.sleep(min(action.get('ms', 100), 5000) / 1000)
                elif atype == 'key':
                    k = self._resolve_key(action.get('key', ''))
                    if k is None:
                        skipped += 1
                        continue
                    act = action.get('action', 'tap')
                    if act == 'press':
                        _paced(kb.press, k)
                    elif act == 'release':
                        _paced(kb.release, k)
                    else:
                        _paced(kb.tap, k)
                elif atype == 'click':
                    x = action.get('x', 0)
                    y = action.get('y', 0)
                    btn_name = action.get('button', 'left')
                    btn = mouse.Button.left if btn_name == 'left' else mouse.Button.right
                    time.sleep(_MACRO_MIN_INTERVAL)
                    try:
                        ms.position = (x, y)
                        ms.click(btn)
                        injected += 1
                    except Exception:
                        skipped += 1
                else:
                    skipped += 1
            print(f"[TypeKeep] {label} finished: {injected} actions injected, "
                  f"{skipped} skipped as invalid")
        except Exception as exc:
            print(f"[TypeKeep] Macro error (aborted safely): {exc}")
        finally:
            time.sleep(_MACRO_SETTLE)
            self._modifiers.clear()
            self._macro_running = False
            self.recording = was_recording
            _MACRO_LOCK.release()

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
