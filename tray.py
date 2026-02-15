"""TypeKeep System Tray Icon - pystray + Pillow."""

import webbrowser
import pystray
from PIL import Image, ImageDraw


def _make_icon(color=(45, 212, 191)):
    size = 64
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([2, 2, 62, 62], radius=14, fill=color + (255,))
    d.rectangle([15, 15, 49, 23], fill=(255, 255, 255, 255))
    d.rectangle([28, 15, 36, 50], fill=(255, 255, 255, 255))
    return img


class TrayIcon:
    TEAL = (45, 212, 191)
    RED = (239, 68, 68)

    def __init__(self, config, recorder, port):
        self.config = config
        self.recorder = recorder
        self.port = port
        self.icon = None

    def _open_dashboard(self, *_):
        webbrowser.open(f'http://127.0.0.1:{self.port}')

    def _toggle_recording(self, *_):
        self.recorder.recording = not self.recorder.recording
        self._refresh()

    def _quit(self, *_):
        if self.icon:
            self.icon.stop()

    def _refresh(self):
        if not self.icon:
            return
        color = self.TEAL if self.recorder.recording else self.RED
        self.icon.icon = _make_icon(color)
        self.icon.title = ('TypeKeep \u2013 Recording' if self.recorder.recording
                           else 'TypeKeep \u2013 Paused')

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

    def run(self):
        self.icon = pystray.Icon(
            'TypeKeep', _make_icon(self.TEAL),
            'TypeKeep \u2013 Recording', self._menu(),
        )
        self.icon.run()
