"""TypeKeep Clipboard Monitor - tracks clipboard changes (text, images, files).

Uses the Windows clipboard API via ctypes (no extra dependencies).
Detected changes are stored in the database clipboard_entries table.
"""

import ctypes
import ctypes.wintypes
import hashlib
import json
import os
import platform
import threading
import time

from paths import CLIPS_DIR

_IS_WINDOWS = platform.system() == 'Windows'

CF_TEXT = 1
CF_BITMAP = 2
CF_UNICODETEXT = 13
CF_HDROP = 15

if _IS_WINDOWS:
    class _LASTINPUTINFO(ctypes.Structure):
        _fields_ = [('cbSize', ctypes.wintypes.UINT),
                    ('dwTime', ctypes.wintypes.DWORD)]

    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32
    _shell32 = ctypes.windll.shell32

    _user32.OpenClipboard.argtypes = [ctypes.wintypes.HWND]
    _user32.OpenClipboard.restype = ctypes.wintypes.BOOL
    _user32.CloseClipboard.argtypes = []
    _user32.CloseClipboard.restype = ctypes.wintypes.BOOL
    _user32.EmptyClipboard.argtypes = []
    _user32.EmptyClipboard.restype = ctypes.wintypes.BOOL
    _user32.SetClipboardData.argtypes = [ctypes.wintypes.UINT, ctypes.c_void_p]
    _user32.SetClipboardData.restype = ctypes.c_void_p
    _user32.GetClipboardData.argtypes = [ctypes.wintypes.UINT]
    _user32.GetClipboardData.restype = ctypes.c_void_p
    _user32.IsClipboardFormatAvailable.argtypes = [ctypes.wintypes.UINT]
    _user32.IsClipboardFormatAvailable.restype = ctypes.wintypes.BOOL
    _user32.GetClipboardSequenceNumber.argtypes = []
    _user32.GetClipboardSequenceNumber.restype = ctypes.wintypes.DWORD
    _user32.GetLastInputInfo.argtypes = [ctypes.POINTER(_LASTINPUTINFO)]
    _user32.GetLastInputInfo.restype = ctypes.wintypes.BOOL

    _kernel32.GlobalAlloc.argtypes = [ctypes.wintypes.UINT, ctypes.c_size_t]
    _kernel32.GlobalAlloc.restype = ctypes.c_void_p
    _kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
    _kernel32.GlobalFree.restype = ctypes.c_void_p
    _kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    _kernel32.GlobalLock.restype = ctypes.c_void_p
    _kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    _kernel32.GlobalUnlock.restype = ctypes.wintypes.BOOL
    _kernel32.GlobalSize.argtypes = [ctypes.c_void_p]
    _kernel32.GlobalSize.restype = ctypes.c_size_t
    _kernel32.GetTickCount.argtypes = []
    _kernel32.GetTickCount.restype = ctypes.wintypes.DWORD

    _shell32.DragQueryFileW.argtypes = [
        ctypes.c_void_p, ctypes.wintypes.UINT,
        ctypes.c_wchar_p, ctypes.wintypes.UINT,
    ]
    _shell32.DragQueryFileW.restype = ctypes.wintypes.UINT

    def _idle_seconds() -> float:
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
    def _idle_seconds() -> float:
        return 0.0


def _active_window_info():
    try:
        from recorder import _get_active_window_info
        return _get_active_window_info()
    except Exception:
        return ('', '')


class ClipboardMonitor:
    """Polls the Windows clipboard and records changes to the database."""

    def __init__(self, db, config):
        self.db = db
        self.config = config
        self._running = False
        self._stop_evt = threading.Event()
        self._thread = None
        self._last_seq = 0
        self._last_hash = ''
        self._broadcast_fn = None
        self._clip_lock = threading.Lock()
        os.makedirs(CLIPS_DIR, exist_ok=True)

    def set_broadcast_fn(self, fn):
        self._broadcast_fn = fn

    def set_text(self, text: str) -> bool:
        """Write text to the OS clipboard without creating a duplicate local entry."""
        if not _IS_WINDOWS or not isinstance(text, str):
            return False
        with self._clip_lock:
            try:
                self._last_hash = hashlib.md5(text.encode('utf-8', errors='replace')).hexdigest()
                data = (text + '\x00').encode('utf-16-le')
                # GMEM_MOVEABLE = 0x0002
                h_mem = _kernel32.GlobalAlloc(0x0002, len(data))
                if not h_mem:
                    return False
                ptr = _kernel32.GlobalLock(h_mem)
                if not ptr:
                    _kernel32.GlobalFree(h_mem)
                    return False
                try:
                    ctypes.memmove(ptr, data, len(data))
                finally:
                    _kernel32.GlobalUnlock(h_mem)
                for _ in range(5):
                    if _user32.OpenClipboard(0):
                        try:
                            _user32.EmptyClipboard()
                            if _user32.SetClipboardData(CF_UNICODETEXT, h_mem):
                                h_mem = None
                                self._last_seq = _user32.GetClipboardSequenceNumber()
                                return True
                        finally:
                            _user32.CloseClipboard()
                        break
                    time.sleep(0.05)
                if h_mem:
                    _kernel32.GlobalFree(h_mem)
                return False
            except Exception:
                return False

    def _notify_copied(self, content_type, preview=''):
        if self._broadcast_fn:
            try:
                self._broadcast_fn('clipboard_copied', {
                    'type': content_type,
                    'preview': (preview[:100] + '...') if len(preview) > 100 else preview,
                    'ts': time.time(),
                })
            except Exception:
                pass

    def start(self):
        if not _IS_WINDOWS:
            return
        self._stop_evt.clear()
        self._running = True
        try:
            self._last_seq = _user32.GetClipboardSequenceNumber()
        except Exception:
            self._last_seq = 0
        self._thread = threading.Thread(
            target=self._poll_loop, daemon=True, name='clipboard-monitor')
        self._thread.start()

    def stop(self):
        self._running = False
        self._stop_evt.set()

    def _poll_loop(self):
        while self._running and not self._stop_evt.is_set():
            base_poll = max(0.5, float(self.config.get('clipboard_poll_seconds', 1.25) or 1.25))
            try:
                if not self.config.get('record_clipboard', True):
                    self._stop_evt.wait(3.0)
                    continue
                with self._clip_lock:
                    seq = _user32.GetClipboardSequenceNumber()
                    if seq != self._last_seq and self._last_seq != 0:
                        self._read_clipboard()
                    self._last_seq = seq
            except Exception:
                pass
            idle_sec = _idle_seconds()
            sleep_for = max(base_poll, 3.5) if idle_sec > 45.0 else base_poll
            self._stop_evt.wait(sleep_for)

    def _read_clipboard(self):
        try:
            if not _user32.OpenClipboard(0):
                return
            try:
                if _user32.IsClipboardFormatAvailable(CF_HDROP):
                    self._handle_files()
                elif _user32.IsClipboardFormatAvailable(CF_BITMAP):
                    self._handle_image()
                elif _user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                    self._handle_text()
            finally:
                _user32.CloseClipboard()
        except Exception:
            try:
                _user32.CloseClipboard()
            except Exception:
                pass

    def _handle_text(self):
        handle = _user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return
        ptr = _kernel32.GlobalLock(handle)
        if not ptr:
            return
        try:
            text = ctypes.wstring_at(ptr)
            if not text or not text.strip():
                return
            h = hashlib.md5(text.encode('utf-8', errors='replace')).hexdigest()
            if h == self._last_hash:
                return
            self._last_hash = h
            title, proc = _active_window_info()
            self.db.add_clipboard_entry(
                content_type='text',
                content_text=text[:50000],
                file_path=None,
                source_app=proc,
                source_title=title,
            )
            self._notify_copied('text', text[:200])
        finally:
            _kernel32.GlobalUnlock(handle)

    def _handle_image(self):
        try:
            from PIL import ImageGrab
            img = ImageGrab.grabclipboard()
            if img is None:
                return
            ts = int(time.time() * 1000)
            filename = f'clip_{ts}.png'
            filepath = os.path.join(CLIPS_DIR, filename)
            img.save(filepath, 'PNG')

            thumb_filename = f'thumb_{ts}.png'
            thumb_path = os.path.join(CLIPS_DIR, thumb_filename)
            thumb = img.copy()
            thumb.thumbnail((200, 200))
            thumb.save(thumb_path, 'PNG')

            with open(filepath, 'rb') as f:
                h = hashlib.md5(f.read(4096)).hexdigest()
            if h == self._last_hash:
                os.remove(filepath)
                os.remove(thumb_path)
                return
            self._last_hash = h

            title, proc = _active_window_info()
            self.db.add_clipboard_entry(
                content_type='image',
                content_text=None,
                file_path=filepath,
                thumbnail_path=thumb_path,
                source_app=proc,
                source_title=title,
                extra=json.dumps({
                    'width': img.width, 'height': img.height,
                    'size': os.path.getsize(filepath),
                }),
            )
            self._notify_copied('image', f'{img.width}x{img.height} image')
        except Exception:
            pass

    def _handle_files(self):
        handle = _user32.GetClipboardData(CF_HDROP)
        if not handle:
            return
        count = _shell32.DragQueryFileW(handle, 0xFFFFFFFF, None, 0)
        if count == 0:
            return

        files = []
        for i in range(count):
            buf = ctypes.create_unicode_buffer(260)
            _shell32.DragQueryFileW(handle, i, buf, 260)
            if buf.value:
                files.append(buf.value)

        if not files:
            return

        files_str = '\n'.join(files)
        h = hashlib.md5(files_str.encode('utf-8')).hexdigest()
        if h == self._last_hash:
            return
        self._last_hash = h

        title, proc = _active_window_info()
        self.db.add_clipboard_entry(
            content_type='files',
            content_text=files_str,
            file_path=files[0] if len(files) == 1 else None,
            source_app=proc,
            source_title=title,
            extra=json.dumps({'file_count': len(files), 'files': files}),
        )
        self._notify_copied('files', f'{len(files)} file(s)')
