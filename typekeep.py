"""
TypeKeep - lightweight local input logger, clipboard manager, macro engine
& cross-device sync.

Run:  python typekeep.py
Dashboard opens at http://127.0.0.1:7700
System-tray icon stays running in the background.

Flags:
  --background   Run in background only (no browser, no tray UI)
  --install      Enable Windows startup and start TypeKeep in the background
  --uninstall    Remove Windows startup entry
  --status       Print local service status
  --open         Open the dashboard for the running service
"""

import os
import json
import platform
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config, APP_VERSION
from database import Database
from recorder import Recorder
from server import create_app
from tray import TrayIcon
from clipboard_monitor import ClipboardMonitor
from cloud_sync import CloudSync

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
LOG_FILE = os.path.join(DATA_DIR, 'typekeep.log')


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def _runtime_command(background=True):
    if getattr(sys, 'frozen', False):
        cmd = [sys.executable]
    else:
        exe = sys.executable
        if platform.system() == 'Windows' and exe.lower().endswith('python.exe'):
            exe = exe[:-10] + 'pythonw.exe'
        cmd = [exe, os.path.join(BASE_DIR, 'typekeep.py')]
    if background:
        cmd.append('--background')
    return cmd


def _quote_cmd(cmd):
    return ' '.join(f'"{part}"' if ' ' in part else part for part in cmd)


def _set_startup(enabled=True, background=True):
    if platform.system() != 'Windows':
        return False
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE)
        if enabled:
            winreg.SetValueEx(key, 'TypeKeep', 0, winreg.REG_SZ,
                              _quote_cmd(_runtime_command(background=background)))
        else:
            try:
                winreg.DeleteValue(key, 'TypeKeep')
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception as exc:
        print(f"[TypeKeep] Startup registry error: {exc}")
        return False


def _startup_status():
    if platform.system() != 'Windows':
        return {'supported': False, 'enabled': False, 'command': ''}
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ)
        value, _ = winreg.QueryValueEx(key, 'TypeKeep')
        winreg.CloseKey(key)
        return {'supported': True, 'enabled': True, 'command': value}
    except FileNotFoundError:
        return {'supported': True, 'enabled': False, 'command': ''}
    except Exception as exc:
        return {'supported': True, 'enabled': False, 'error': str(exc), 'command': ''}


def _start_background():
    cmd = _runtime_command(background=True)
    kwargs = {'cwd': BASE_DIR}
    if platform.system() == 'Windows':
        kwargs['creationflags'] = (
            getattr(subprocess, 'DETACHED_PROCESS', 0)
            | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
        )
    subprocess.Popen(cmd, **kwargs)


def _health(port):
    if not _port_in_use(port):
        return {'running': False, 'port': port}
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health',
                                    timeout=2) as response:
            payload = json.loads(response.read().decode('utf-8'))
        payload['running'] = True
        payload['port'] = port
        return payload
    except Exception as exc:
        return {'running': True, 'port': port, 'status': 'unknown', 'error': str(exc)}


def _configure_background_logging(background_mode):
    os.makedirs(DATA_DIR, exist_ok=True)
    if not background_mode:
        return
    try:
        log = open(LOG_FILE, 'a', encoding='utf-8', buffering=1)
        sys.stdout = log
        sys.stderr = log
        print(f"\n[TypeKeep] Background log started {time.strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception:
        pass


def main():
    background_mode = '--background' in sys.argv

    config = Config()
    port = config.get('server_port', 7700)

    if '--status' in sys.argv:
        status = _health(port)
        status['startup'] = _startup_status()
        print(json.dumps(status, indent=2))
        return

    if '--open' in sys.argv:
        if _port_in_use(port):
            webbrowser.open(f'http://127.0.0.1:{port}')
        else:
            _start_background()
            time.sleep(2)
            webbrowser.open(f'http://127.0.0.1:{port}')
        return

    if '--install' in sys.argv:
        config.update({
            'start_on_boot': True,
            'start_background_on_boot': True,
            'start_ui_on_boot': False,
            'show_onboarding': False,
        })
        _set_startup(True, background=True)
        if not _port_in_use(port):
            _start_background()
        print(json.dumps({
            'status': 'installed',
            'port': port,
            'startup': _startup_status(),
        }, indent=2))
        return

    if '--uninstall' in sys.argv:
        _set_startup(False)
        config.update({'start_on_boot': False})
        print(json.dumps({'status': 'startup_removed', 'startup': _startup_status()}, indent=2))
        return

    _configure_background_logging(background_mode)

    if _port_in_use(port):
        if not background_mode:
            print("TypeKeep is already running - opening dashboard.")
            webbrowser.open(f'http://127.0.0.1:{port}')
        sys.exit(0)

    if config.get('start_on_boot', True):
        _set_startup(
            True,
            background=bool(config.get('start_background_on_boot', True)
                            and not config.get('start_ui_on_boot', False)),
        )

    db = Database()
    db.set_meta('last_version', APP_VERSION)
    db.set_meta('last_launch', str(time.time()))

    recorder = Recorder(db, config)
    clipboard = ClipboardMonitor(db, config)
    cloud = CloudSync(db, config)
    app = create_app(db, recorder, config, cloud)

    clipboard.set_broadcast_fn(app.broadcast_sse)

    threading.Thread(
        target=lambda: app.run(host='0.0.0.0', port=port,
                               debug=False, use_reloader=False, threaded=True),
        daemon=True, name='flask-server',
    ).start()

    recorder.start()
    clipboard.start()
    cloud.start()

    # Adaptive periodic loop: sleeps longer when idle, wakes faster when active.
    # Designed to use <1% CPU/RAM during idle background operation.
    # - Only flushes the buffer on every tick.
    # - Only broadcasts SSE updates when (a) something new was written AND (b) a
    #   client is actually listening. Saves wake-ups on both sides.
    # - Adaptive sleep: 0.5s when actively buffering, ramps up to 5s when idle.
    def _periodic():
        cleanup_interval = config.get('cleanup_interval_seconds', 3600)
        last_cleanup = time.time()
        last_broadcast = 0.0
        idle_streak = 0
        while True:
            try:
                had_data = db.flush_buffer_returning_count() > 0
                now = time.time()

                if had_data and app.sse_client_count() and now - last_broadcast >= 1.0:
                    try:
                        app.broadcast_sse('update', {'ts': now})
                    except Exception:
                        pass
                    last_broadcast = now

                if now - last_cleanup >= cleanup_interval:
                    db.cleanup(config.get('retention_days', 30))
                    db.cleanup_clipboard(config.get('clipboard_retention_days', 30))
                    last_cleanup = now

                if config.get('auto_backup_enabled', True):
                    db.maybe_backup()

                if had_data:
                    idle_streak = 0
                    time.sleep(0.5)
                else:
                    idle_streak = min(idle_streak + 1, 10)
                    time.sleep(min(5.0, 0.5 + idle_streak * 0.5))
            except Exception as exc:
                print(f"[TypeKeep] periodic error: {exc}")
                time.sleep(2.0)

    threading.Thread(target=_periodic, daemon=True, name='flush').start()

    print("=" * 48)
    print(f"  TypeKeep v{APP_VERSION} is running")
    print(f"  Dashboard -> http://127.0.0.1:{port}")
    print(f"  LAN access -> http://{_get_lan_ip()}:{port}")
    if background_mode:
        print("  Mode: background (dashboard + recorder, no tray/browser)")
    else:
        print("  Tray icon: teal T")
    print("=" * 48)

    if not background_mode and config.get('show_onboarding', True):
        webbrowser.open(f'http://127.0.0.1:{port}')

    if background_mode:
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            pass
    else:
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


def _get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


if __name__ == '__main__':
    main()
