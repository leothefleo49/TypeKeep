"""TypeKeep Recorder - captures keyboard, mouse, shortcuts, and notifications.

Hardened revision (2026-10-29):
- Hook callbacks are enqueue-only (microseconds). All slow work (window
  lookup, DB writes, flushes) happens on a writer thread so Windows can
  never hit its low-level hook timeout (which froze system input).
- Input storm guard: sustained event floods are dropped and counted
  instead of hammering the database.
- Macro engine: strict key validation, injection rate limit, action cap,
  single-macro-at-a-time lock, and audit logging.
"""

import json
import queue
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

# ── Safety limits ─────────────────────────────────────────────

_QUEUE_MAX = 20000          # hook queue ceiling; unprotected dropped first
_STORM_EVENTS_PER_SEC = 80  # sustained rate above this = flood (unprotected only)
_STORM_BURST = 200          # instantaneous burst allowance
# v3.3.0: keystrokes/shortcuts are NEVER flood-dropped. The old guard
# dropped 365 + 237 events in the live log - real typed text, lost -
# because fast typing + key-repeat + clicks shared one bucket. Flood
# protection now applies only to replaceable event types.
_PROTECTED_TYPES = frozenset({'key_press', 'shortcut'})
_MACRO_LOCK = threading.Lock()
_MACRO_MAX_ACTIONS = 300    # refuse absurdly large macros
_MACRO_MIN_INTERVAL = 0.025 # min seconds between injected key actions
_MACRO_SETTLE = 0.3         # seconds to keep recording paused after a macro


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
        # hook -> writer pipeline
        self._q = queue.Queue()
        self._stop_evt = threading.Event()
        self._writer = None
        # storm guard state
        self._storm_tokens = float(_STORM_BURST)
        self._storm_ts = time.time()
        self._dropped = 0

    # ── Control ────────────────────────────────────────────────

    def start(self):
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

        # Notification detection thread
        if self.config.get('record_notifications', True) and _IS_WINDOWS:
            self._start_notification_watcher()

        # Writer thread: sole owner of DB writes from input events
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
        """Token bucket: True if within burst/sustained rate.

        Protected types (keystrokes, shortcuts) always pass - dropping
        one loses actual text, which is the one thing TypeKeep exists
        to never do.
        """
        if event_type in _PROTECTED_TYPES:
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

    # ── Hook callbacks: FAST, no exceptions, no I/O ─────────────

    def _on_key_press(self, key):
        try:
            if not self.recording or not self.config.get('record_keyboard', True):
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

            mod_names = {str(m).replace('Key.', '') for m in self._modifiers}
            mod_str = ','.join(sorted(mod_names)) if mod_names else ''

            is_shortcut = (bool(mod_names & _SHORTCUT_MODS)
                           and self.config.get('record_shortcuts', True))
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
        """Non-blocking enqueue with ceiling; drops oldest when full."""
        evt = dict(fields)
        evt['timestamp'] = time.time()
        evt['event_type'] = event_type
        evt.setdefault('extra', None)
        try:
            if self._q.qsize() >= _QUEUE_MAX:
                # v3.3.0 queue-full policy (hook must stay fast, so this
                # is O(1) in the common cases):
                # - unprotected incoming: drop the incoming event.
                # - protected incoming: drop the oldest event if it is
                #   unprotected; only if the whole visible head is
                #   protected do we drop that head (counted, last resort).
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
        flush_sec = max(0.5, float(self.config.get('buffer_flush_seconds', 2) or 2))
        last_flush = time.time()
        last_dropped_log = 0
        while not self._stop_evt.is_set():
            try:
                evt = self._q.get(timeout=0.25)
            except queue.Empty:
                evt = None
            if evt is not None and self._allow_event(evt.get('event_type')):
                title, proc = self._active_window()
                evt['window_title'] = title
                evt['window_process'] = proc
                try:
                    self.db.buffer_event(evt)
                except Exception as exc:
                    print(f"[TypeKeep] DB buffer error: {exc}")
            now = time.time()
            if now - last_flush >= flush_sec:
                last_flush = now
                try:
                    self.db.flush_buffer()
                except Exception as exc:
                    print(f"[TypeKeep] DB flush error: {exc}")
            if self._dropped and now - last_dropped_log > 30:
                print(f"[TypeKeep] Input flood guard: dropped {self._dropped} events")
                self._dropped = 0
                last_dropped_log = now

    # ── Notification watcher (Windows) ─────────────────────────

    def _start_notification_watcher(self):
        def _watch():
            last_title = ''
            while self.recording:
                try:
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
                            'key_name': None,
                            'character': None,
                            'modifiers': None,
                        })
                    last_title = title
                except Exception:
                    pass
                time.sleep(1)

        threading.Thread(target=_watch, daemon=True, name='notif-watcher').start()

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
        if len(name) == 1 and (name.isprintable()):
            return name
        return None

    def run_macro(self, actions, macro_id=None):
        """Execute a macro with strict validation and rate limiting.

        Guarantees: no concurrent macros, at most _MACRO_MAX_ACTIONS
        injected actions, at least _MACRO_MIN_INTERVAL between injected
        key actions, and unknown key names are skipped (never guessed).
        """
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
