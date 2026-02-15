"""TypeKeep Flask Server - API + web dashboard."""

import io
import json
import os
import time
import uuid
import logging
from flask import Flask, jsonify, request, render_template, send_file, send_from_directory


def create_app(database, recorder, config):
    app = Flask(__name__)
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

    log = logging.getLogger('werkzeug')
    log.setLevel(logging.WARNING)

    # Ensure device identity
    if not config.get('device_id'):
        config.set('device_id', str(uuid.uuid4())[:8])
    if not config.get('device_name'):
        import socket
        config.set('device_name', socket.gethostname())

    # ── Helpers ────────────────────────────────────────────────

    def _time_range():
        """Parse common time-range query param."""
        tr = request.args.get('range', '24h')
        now = time.time()
        m = {'1h': 3600, '3h': 10800, '6h': 21600, '12h': 43200,
             '24h': 86400, '3d': 259200, '7d': 604800, '30d': 2592000,
             'all': None}
        secs = m.get(tr)
        return (now - secs) if secs else None, now

    # ── Pages ──────────────────────────────────────────────────

    @app.route('/')
    def index():
        return render_template('index.html')

    # ── Messages (text history) ────────────────────────────────

    @app.route('/api/messages')
    def api_messages():
        gap = request.args.get('gap', config.get('default_gap_seconds'), type=float)
        sw_gap = request.args.get('sw_gap', config.get('same_window_gap_seconds', 30), type=float)
        app_filter = request.args.get('app', '') or None
        search = request.args.get('search', '') or None
        min_len = request.args.get('min_length', config.get('min_message_length', 1), type=int)
        sort = request.args.get('sort', 'newest')
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        split_enter = request.args.get('split_enter', 'false') == 'true'
        start, end = _time_range()

        database.flush_buffer()
        messages, total = database.get_messages(
            gap_seconds=gap, same_window_gap=sw_gap,
            start_time=start, end_time=end,
            process=app_filter, search=search,
            min_length=min_len, sort=sort,
            limit=limit, offset=offset,
            split_on_enter=split_enter,
        )
        return jsonify({'messages': messages, 'total': total,
                        'has_more': (offset + limit) < total})

    # ── Activity feed ──────────────────────────────────────────

    @app.route('/api/activity')
    def api_activity():
        start, end = _time_range()
        types = request.args.get('types', '') or None
        limit = request.args.get('limit', 200, type=int)
        database.flush_buffer()
        events = database.get_activity(start, end, types, limit)
        return jsonify({'events': events, 'total': len(events)})

    # ── Shortcuts log ──────────────────────────────────────────

    @app.route('/api/shortcuts')
    def api_shortcuts():
        start, end = _time_range()
        limit = request.args.get('limit', 200, type=int)
        database.flush_buffer()
        events = database.get_shortcuts(start, end, limit)
        return jsonify({'events': events})

    # ── Stats ──────────────────────────────────────────────────

    @app.route('/api/stats')
    def api_stats():
        database.flush_buffer()
        return jsonify(database.get_stats())

    # ── Apps list ──────────────────────────────────────────────

    @app.route('/api/apps')
    def api_apps():
        start, _ = _time_range()
        return jsonify(database.get_apps(start_time=start))

    # ── Recording toggle/status ────────────────────────────────

    @app.route('/api/toggle', methods=['POST'])
    def api_toggle():
        recorder.recording = not recorder.recording
        return jsonify({'recording': recorder.recording})

    @app.route('/api/status')
    def api_status():
        return jsonify({'recording': recorder.recording})

    # ── Settings ───────────────────────────────────────────────

    @app.route('/api/settings', methods=['GET'])
    def api_get_settings():
        return jsonify(config.to_dict())

    @app.route('/api/settings', methods=['POST'])
    def api_set_settings():
        data = request.get_json(silent=True) or {}
        safe_keys = {
            'retention_days', 'default_gap_seconds', 'same_window_gap_seconds',
            'record_mouse_clicks', 'record_mouse_scroll', 'record_mouse_movement',
            'record_shortcuts', 'record_notifications', 'record_clipboard',
            'clipboard_retention_days', 'mouse_sample_ms',
            'min_message_length', 'max_messages_display', 'split_on_enter',
            'start_on_boot', 'start_minimized', 'show_onboarding',
            'backup_enabled', 'backup_service', 'backup_interval_minutes',
            'buffer_flush_seconds', 'theme',
        }
        filtered = {k: v for k, v in data.items() if k in safe_keys}
        config.update(filtered)

        # Handle start-on-boot toggle
        if 'start_on_boot' in filtered:
            _set_startup(filtered['start_on_boot'])

        return jsonify({'status': 'ok', 'settings': config.to_dict()})

    # ── Delete ─────────────────────────────────────────────────

    @app.route('/api/delete-events', methods=['POST'])
    def api_delete_events():
        data = request.get_json(silent=True) or {}
        start = data.get('start_time')
        end = data.get('end_time')
        proc = data.get('process')
        confirm = data.get('confirm', False)
        if not confirm:
            return jsonify({'error': 'Confirmation required', 'needs_confirm': True}), 400
        if start is None or end is None:
            return jsonify({'error': 'start_time and end_time required'}), 400
        deleted = database.delete_events_range(start, end, proc)
        return jsonify({'deleted': deleted})

    @app.route('/api/delete-all', methods=['POST'])
    def api_delete_all():
        data = request.get_json(silent=True) or {}
        if not data.get('confirm'):
            return jsonify({'error': 'Confirmation required', 'needs_confirm': True}), 400
        database.delete_all_events()
        return jsonify({'status': 'ok'})

    # ── Export / Import ────────────────────────────────────────

    @app.route('/api/export')
    def api_export():
        start, end = _time_range()
        data = database.export_data(start, end)
        data['settings'] = config.to_dict()
        buf = io.BytesIO(json.dumps(data, indent=2).encode('utf-8'))
        return send_file(buf, mimetype='application/json',
                         as_attachment=True,
                         download_name=f'typekeep_export_{int(time.time())}.json')

    @app.route('/api/import', methods=['POST'])
    def api_import():
        f = request.files.get('file')
        if not f:
            raw = request.get_json(silent=True)
            if not raw:
                return jsonify({'error': 'No file or JSON provided'}), 400
        else:
            try:
                raw = json.loads(f.read().decode('utf-8'))
            except Exception:
                return jsonify({'error': 'Invalid JSON file'}), 400

        count = database.import_data(raw)
        if raw.get('settings'):
            config.update(raw['settings'])
        return jsonify({'imported': count})

    # ── Macros ─────────────────────────────────────────────────

    @app.route('/api/macros', methods=['GET'])
    def api_macros_list():
        macros = database.get_macros()
        for m in macros:
            if isinstance(m.get('actions'), str):
                try: m['actions'] = json.loads(m['actions'])
                except Exception: m['actions'] = []
        return jsonify({'macros': macros})

    @app.route('/api/macros', methods=['POST'])
    def api_macros_create():
        data = request.get_json(silent=True) or {}
        name = data.get('name', 'Untitled')
        shortcut = data.get('shortcut', '')
        actions = data.get('actions', [])
        mid = database.create_macro(name, shortcut, actions)
        return jsonify({'id': mid, 'status': 'ok'})

    @app.route('/api/macros/<int:mid>', methods=['PUT'])
    def api_macros_update(mid):
        data = request.get_json(silent=True) or {}
        database.update_macro(mid, data.get('name'), data.get('shortcut'),
                              data.get('actions'))
        return jsonify({'status': 'ok'})

    @app.route('/api/macros/<int:mid>', methods=['DELETE'])
    def api_macros_delete(mid):
        database.delete_macro(mid)
        return jsonify({'status': 'ok'})

    @app.route('/api/macros/<int:mid>/run', methods=['POST'])
    def api_macros_run(mid):
        macro = database.get_macro(mid)
        if not macro:
            return jsonify({'error': 'Macro not found'}), 404
        actions = macro.get('actions', '[]')
        if isinstance(actions, str):
            actions = json.loads(actions)
        import threading
        threading.Thread(target=recorder.run_macro, args=(actions,),
                         daemon=True).start()
        return jsonify({'status': 'running'})

    # ── Onboarding ─────────────────────────────────────────────

    @app.route('/api/onboarding', methods=['GET'])
    def api_onboarding():
        return jsonify({'show': config.get('show_onboarding', True)})

    @app.route('/api/onboarding/complete', methods=['POST'])
    def api_onboarding_complete():
        config.set('show_onboarding', False)
        return jsonify({'status': 'ok'})

    # ── Clipboard History ──────────────────────────────────────

    @app.route('/api/clipboard')
    def api_clipboard():
        start, end = _time_range()
        ctype = request.args.get('type', '')
        search = request.args.get('search', '')
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))
        pinned = request.args.get('pinned', '') == '1'
        entries, total = database.get_clipboard(
            start, end, ctype or None, search or None,
            limit, offset, pinned)
        # Convert file paths to serve URLs
        for e in entries:
            if e.get('file_path') and os.path.exists(e['file_path']):
                e['file_url'] = f"/api/clips/{os.path.basename(e['file_path'])}"
            if e.get('thumbnail_path') and os.path.exists(e['thumbnail_path']):
                e['thumbnail_url'] = f"/api/clips/{os.path.basename(e['thumbnail_path'])}"
        return jsonify({
            'entries': entries, 'total': total,
            'has_more': offset + limit < total,
        })

    @app.route('/api/clipboard/stats')
    def api_clipboard_stats():
        return jsonify(database.get_clipboard_stats())

    @app.route('/api/clipboard/<int:eid>/pin', methods=['POST'])
    def api_clipboard_pin(eid):
        database.toggle_clipboard_pin(eid)
        return jsonify({'status': 'ok'})

    @app.route('/api/clipboard/<int:eid>', methods=['DELETE'])
    def api_clipboard_delete(eid):
        database.delete_clipboard_entry(eid)
        return jsonify({'status': 'ok'})

    @app.route('/api/clipboard/clear', methods=['POST'])
    def api_clipboard_clear():
        data = request.get_json(silent=True) or {}
        if not data.get('confirm'):
            return jsonify({'error': 'Confirmation required'}), 400
        database.clear_clipboard()
        return jsonify({'status': 'ok'})

    @app.route('/api/clips/<path:filename>')
    def api_serve_clip(filename):
        clips_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'data', 'clips')
        return send_from_directory(clips_dir, filename)

    # ── Sync / Devices ─────────────────────────────────────────

    @app.route('/api/sync/info')
    def api_sync_info():
        """Return this device's identity and sync configuration."""
        return jsonify({
            'device_id': config.get('device_id'),
            'device_name': config.get('device_name'),
            'sync_key': config.get('sync_key', ''),
            'sync_enabled': config.get('sync_enabled', False),
            'clipboard_sync': config.get('clipboard_sync', False),
            'port': config.get('server_port', 7700),
        })

    @app.route('/api/sync/info', methods=['POST'])
    def api_sync_info_update():
        """Update this device's sync configuration."""
        data = request.get_json(silent=True) or {}
        safe = {k: v for k, v in data.items()
                if k in ('device_name', 'sync_key', 'sync_enabled',
                         'clipboard_sync')}
        config.update(safe)
        return jsonify({'status': 'ok'})

    @app.route('/api/sync/devices')
    def api_sync_devices():
        return jsonify({'devices': database.get_devices()})

    @app.route('/api/sync/pair', methods=['POST'])
    def api_sync_pair():
        """Pair with a remote device by IP:port + sync key."""
        data = request.get_json(silent=True) or {}
        ip = data.get('ip', '').strip()
        port = int(data.get('port', 7700))
        key = data.get('sync_key', '').strip()

        if not ip:
            return jsonify({'error': 'IP address required'}), 400

        # Verify remote device
        import requests as rq
        try:
            r = rq.get(f'http://{ip}:{port}/api/sync/handshake',
                       params={'key': key, 'device_id': config.get('device_id'),
                               'device_name': config.get('device_name')},
                       timeout=5)
            if r.status_code != 200:
                return jsonify({'error': 'Pairing rejected: ' + r.json().get('error', 'unknown')}), 400
            remote = r.json()
        except Exception as exc:
            return jsonify({'error': f'Cannot reach device: {exc}'}), 400

        database.upsert_device(
            remote['device_id'], remote['device_name'],
            ip, port,
            sync_enabled=1,
            clipboard_sync=int(data.get('clipboard_sync', False)),
        )
        return jsonify({'status': 'ok', 'device': remote})

    @app.route('/api/sync/handshake')
    def api_sync_handshake():
        """Respond to a pairing request from a remote device."""
        key = request.args.get('key', '')
        my_key = config.get('sync_key', '')
        if not my_key or key != my_key:
            return jsonify({'error': 'Invalid sync key'}), 403

        remote_id = request.args.get('device_id', '')
        remote_name = request.args.get('device_name', 'Unknown')
        if remote_id:
            remote_ip = request.remote_addr
            database.upsert_device(
                remote_id, remote_name, remote_ip, 7700,
                sync_enabled=1, clipboard_sync=0)

        return jsonify({
            'device_id': config.get('device_id'),
            'device_name': config.get('device_name'),
            'status': 'ok',
        })

    @app.route('/api/sync/unpair/<device_id>', methods=['DELETE'])
    def api_sync_unpair(device_id):
        database.remove_device(device_id)
        return jsonify({'status': 'ok'})

    @app.route('/api/sync/pull', methods=['POST'])
    def api_sync_pull():
        """Pull clipboard data from a paired device."""
        data = request.get_json(silent=True) or {}
        device_id = data.get('device_id')
        devices = database.get_devices()
        target = next((d for d in devices if d['id'] == device_id), None)
        if not target:
            return jsonify({'error': 'Device not found'}), 404

        import requests as rq
        try:
            r = rq.get(
                f"http://{target['ip_address']}:{target['port']}/api/sync/data",
                params={'key': config.get('sync_key', ''),
                        'type': data.get('data_type', 'clipboard')},
                timeout=10)
            if r.status_code != 200:
                return jsonify({'error': 'Pull failed'}), 400
            remote_data = r.json()
        except Exception as exc:
            return jsonify({'error': f'Cannot reach device: {exc}'}), 400

        # Import clipboard entries from remote
        imported = 0
        for entry in remote_data.get('clipboard', []):
            database.add_clipboard_entry(
                content_type=entry['content_type'],
                content_text=entry.get('content_text'),
                source_app=entry.get('source_app'),
                source_title=entry.get('source_title'),
                extra=entry.get('extra'),
                device_id=device_id,
            )
            imported += 1
        return jsonify({'status': 'ok', 'imported': imported})

    @app.route('/api/sync/data')
    def api_sync_serve_data():
        """Serve local data to a paired device (authenticated)."""
        key = request.args.get('key', '')
        my_key = config.get('sync_key', '')
        if not my_key or key != my_key:
            return jsonify({'error': 'Unauthorized'}), 403

        data_type = request.args.get('type', 'clipboard')
        result = {}
        if data_type in ('clipboard', 'all'):
            entries, _ = database.get_clipboard(limit=500)
            # Strip file paths (they're local)
            for e in entries:
                e.pop('file_path', None)
                e.pop('thumbnail_path', None)
            result['clipboard'] = entries
        if data_type in ('events', 'all'):
            now = time.time()
            result['events'] = database.get_events(
                start_time=now - 86400, limit=5000)
        return jsonify(result)

    @app.route('/api/sync/push-clipboard', methods=['POST'])
    def api_sync_receive_clipboard():
        """Receive a clipboard entry pushed from a paired device."""
        key = request.args.get('key', '')
        my_key = config.get('sync_key', '')
        if not my_key or key != my_key:
            return jsonify({'error': 'Unauthorized'}), 403

        data = request.get_json(silent=True) or {}
        if data.get('content_type'):
            database.add_clipboard_entry(
                content_type=data['content_type'],
                content_text=data.get('content_text'),
                source_app=data.get('source_app'),
                source_title=data.get('source_title'),
                extra=data.get('extra'),
                device_id=data.get('device_id'),
            )
        return jsonify({'status': 'ok'})

    # ── Startup helper (Windows registry) ──────────────────────

    def _set_startup(enabled):
        try:
            import sys, os, winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE)
            if enabled:
                script = os.path.abspath(os.path.join(
                    os.path.dirname(__file__), '..', 'typekeep.py'))
                winreg.SetValueEx(key, 'TypeKeep', 0, winreg.REG_SZ,
                                  f'pythonw "{script}"')
            else:
                try:
                    winreg.DeleteValue(key, 'TypeKeep')
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as exc:
            print(f"[TypeKeep] Startup registry error: {exc}")

    return app
