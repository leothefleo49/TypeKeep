"""
TypeKeep - lightweight local input logger & macro engine.

Run:  python typekeep.py
Dashboard opens at http://127.0.0.1:7700
System-tray icon stays running in the background.
"""

import socket
import sys
import threading
import time
import webbrowser

from config import Config
from database import Database
from recorder import Recorder
from server import create_app
from tray import TrayIcon
from clipboard_monitor import ClipboardMonitor
from cloud_sync import CloudSync


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def main():
    config = Config()
    port = config.get('server_port', 7700)

    if _port_in_use(port):
        print("TypeKeep is already running - opening dashboard.")
        webbrowser.open(f'http://127.0.0.1:{port}')
        sys.exit(0)

    db = Database()
    recorder = Recorder(db, config)
    clipboard = ClipboardMonitor(db, config)
    cloud = CloudSync(db, config)
    app = create_app(db, recorder, config, cloud)

    # Flask in background thread
    threading.Thread(
        target=lambda: app.run(host='127.0.0.1', port=port,
                               debug=False, use_reloader=False, threaded=True),
        daemon=True, name='flask-server',
    ).start()

    recorder.start()
    clipboard.start()
    cloud.start()

    # Periodic flush & cleanup (crash-resistant: flush every 1s)
    def _periodic():
        flush_sec = config.get('buffer_flush_seconds', 1)
        cleanup_interval = config.get('cleanup_interval_seconds', 3600)
        last_cleanup = time.time()
        while True:
            try:
                db.flush_buffer()
                now = time.time()
                if now - last_cleanup >= cleanup_interval:
                    db.cleanup(config.get('retention_days', 30))
                    db.cleanup_clipboard(config.get('clipboard_retention_days', 30))
                    last_cleanup = now
            except Exception as exc:
                print(f"[TypeKeep] periodic error: {exc}")
            time.sleep(flush_sec)

    threading.Thread(target=_periodic, daemon=True, name='flush').start()

    print("=" * 48)
    print("  TypeKeep is running")
    print(f"  Dashboard -> http://127.0.0.1:{port}")
    print("  Tray icon: teal T")
    print("=" * 48)

    # Open browser on first run
    if config.get('show_onboarding', True):
        webbrowser.open(f'http://127.0.0.1:{port}')

    tray = TrayIcon(config, recorder, port)
    try:
        tray.run()
    except KeyboardInterrupt:
        pass

    print("\n[TypeKeep] Shutting down...")
    recorder.stop()
    clipboard.stop()
    cloud.stop()
    db.flush_buffer()
    db.close()


if __name__ == '__main__':
    main()
