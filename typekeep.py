"""
TypeKeep — lightweight local keystroke & input logger.

Run this file to start:
  python typekeep.py

Dashboard opens at  http://127.0.0.1:7700
Sits quietly in the system tray; right-click tray icon for controls.
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


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def main():
    config = Config()
    port = config.get('server_port', 7700)

    # ── Prevent duplicate instances ────────────────────────────────
    if _port_in_use(port):
        print(f"TypeKeep is already running → opening dashboard.")
        webbrowser.open(f'http://127.0.0.1:{port}')
        sys.exit(0)

    # ── Core components ────────────────────────────────────────────
    db = Database()
    recorder = Recorder(db, config)
    app = create_app(db, recorder, config)

    # ── Flask in background thread ─────────────────────────────────
    server_thread = threading.Thread(
        target=lambda: app.run(
            host='127.0.0.1', port=port,
            debug=False, use_reloader=False, threaded=True,
        ),
        daemon=True,
        name='flask-server',
    )
    server_thread.start()

    # ── Recorder (pynput starts its own threads) ───────────────────
    recorder.start()

    # ── Periodic flush & cleanup ───────────────────────────────────
    def _periodic():
        flush_sec = config.get('buffer_flush_seconds', 2)
        cleanup_interval = config.get('cleanup_interval_seconds', 3600)
        last_cleanup = time.time()
        while True:
            try:
                db.flush_buffer()
                now = time.time()
                if now - last_cleanup >= cleanup_interval:
                    db.cleanup(config.get('retention_days', 7))
                    last_cleanup = now
            except Exception as exc:
                print(f"[TypeKeep] periodic error: {exc}")
            time.sleep(flush_sec)

    threading.Thread(target=_periodic, daemon=True, name='flush-thread').start()

    # ── Startup banner ─────────────────────────────────────────────
    print("=" * 48)
    print("  TypeKeep is running")
    print(f"  Dashboard → http://127.0.0.1:{port}")
    print("  Look for the teal  T  icon in your system tray.")
    print("=" * 48)

    # ── System tray (blocks main thread) ───────────────────────────
    tray = TrayIcon(config, recorder, port)
    try:
        tray.run()
    except KeyboardInterrupt:
        pass

    # ── Clean shutdown ─────────────────────────────────────────────
    print("\n[TypeKeep] Shutting down…")
    recorder.stop()
    db.flush_buffer()
    db.close()


if __name__ == '__main__':
    main()
