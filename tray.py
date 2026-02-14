"""TypeKeep System Tray Icon - powered by pystray + Pillow."""

import webbrowser
import pystray
from PIL import Image, ImageDraw


def _make_icon(color=(45, 212, 191)):
    """Draw a simple teal (or given color) rounded-square icon with a 'T'."""
    size = 64
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([2, 2, 62, 62], radius=14, fill=color + (255,))
    # T – horizontal bar
    d.rectangle([15, 15, 49, 23], fill=(255, 255, 255, 255))
    # T – vertical bar
    d.rectangle([28, 15, 36, 50], fill=(255, 255, 255, 255))
    return img


class TrayIcon:
    """System-tray icon with Open / Pause / Quit controls."""

    TEAL = (45, 212, 191)
    RED = (239, 68, 68)

    def __init__(self, config, recorder, port):
        self.config = config
        self.recorder = recorder
        self.port = port
        self.icon = None

    # ── Actions ────────────────────────────────────────────────────

    def _open_dashboard(self, *_args):
        webbrowser.open(f'http://127.0.0.1:{self.port}')

    def _toggle_recording(self, *_args):
        self.recorder.recording = not self.recorder.recording
        self._refresh()

    def _quit(self, *_args):
        if self.icon:
            self.icon.stop()

    # ── Menu ───────────────────────────────────────────────────────

    def _refresh(self):
        if not self.icon:
            return
        color = self.TEAL if self.recorder.recording else self.RED
        self.icon.icon = _make_icon(color)
        tip = 'TypeKeep – Recording' if self.recorder.recording else 'TypeKeep – Paused'
        self.icon.title = tip

    def _menu(self):
        return pystray.Menu(
            pystray.MenuItem('Open Dashboard', self._open_dashboard, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda item: ('Resume Recording' if not self.recorder.recording
                              else 'Pause Recording'),
                self._toggle_recording,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Quit TypeKeep', self._quit),
        )

    # ── Run (blocks main thread) ───────────────────────────────────

    def run(self):
        self.icon = pystray.Icon(
            'TypeKeep',
            _make_icon(self.TEAL),
            'TypeKeep – Recording',
            self._menu(),
        )
        self.icon.run()
