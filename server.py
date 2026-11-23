"""TypeKeep Flask Server - API + web dashboard with version tracking,
health checks, and LAN/CORS support."""

import io
import json
import os
import time
import uuid
import logging
import queue
import threading
from flask import Flask, jsonify, request, render_template, send_file, send_from_directory, Response

import glob
import io
import json
import os
import socket
import sys
import time
import uuid
import logging
import queue
import threading
from flask import Flask, jsonify, request, render_template, send_file, send_from_directory, Response

from config import APP_VERSION
from paths import BUNDLE_DIR, APP_DIR, DATA_DIR, BACKUP_DIR, CLIPS_DIR


def _get_lan_ips():
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        primary = s.getsockname()[0]
        s.close()
        if primary and not primary.startswith('127.'):
            ips.append(primary)
    except Exception:
        pass
    try:
        for res in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = res[4][0]
            if ip and not ip.startswith('127.') and not ip.startswith('169.254.') and ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    return ips or ['127.0.0.1']


def _make_qr_svg(payload_text: str) -> str:
    try:
        import qrcode
        import qrcode.image.svg
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2,
        )
        qr.add_data(payload_text)
        qr.make(fit=True)
        img = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
        buf = io.BytesIO()
        img.save(buf)
        return buf.getvalue().decode('utf-8', errors='replace')
    except Exception:
        return ''


def create_app(database, recorder, config, cloud_sync=None, clipboard_monitor=None):
    app = Flask(
        __name__,
        template_folder=os.path.join(BUNDLE_DIR, 'templates'),
        static_folder=os.path.join(BUNDLE_DIR, 'static'),
    )
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

    log = logging.getLogger('werkzeug')
    log.setLevel(logging.WARNING)

    _sse_clients = []
    _sse_lock = threading.Lock()

    def _broadcast_sse(event_type, data=None):
        msg = f"event: {event_type}\ndata: {json.dumps(data or {})}\n\n"
        with _sse_lock:
            dead = []
            for q in _sse_clients:
                try:
                    q.put_nowait(msg)
                except Exception:
                    dead.append(q)
            for q in dead:
                _sse_clients.remove(q)

    def _sse_client_count():
        with _sse_lock:
            return len(_sse_clients)

    app.broadcast_sse = _broadcast_sse
    app.sse_client_count = _sse_client_count

    if not config.get('device_id'):
        config.set('device_id', str(uuid.uuid4())[:8])
    if not config.get('device_name'):
        import socket
        config.set('device_name', socket.gethostname())

    @app.before_request
    def _same_origin_guard():
        """Block cross-origin requests from external sites while permitting
        same-origin dashboard/mobile PWA calls and authenticated mobile companion apps."""
        origin = request.headers.get('Origin', '')
        if not origin:
            return None
        host = request.headers.get('Host', '')
        try:
            from urllib.parse import urlparse
            o = urlparse(origin)
            ohost = o.hostname or ''
            hhost = host.split(':')[0] if host else ''
            if ohost == hhost:
                return None
            # Allow TypeKeep Android/iOS Companion app (Capacitor/Cordova/WebView)
            # only when LAN access is enabled AND valid sync key is presented.
            native_app_origins = {'http://localhost', 'https://localhost', 'capacitor://localhost', 'ionic://localhost'}
            if config.get('server_lan_access', False) and origin.rstrip('/') in native_app_origins:
                req_key = request.headers.get('X-TypeKeep-Key', '') or request.args.get('key', '')
                valid_keys = {k for k in (config.get('sync_key', ''), config.get('cloud_sync_key', '')) if k}
                if req_key and valid_keys and req_key in valid_keys:
                    return None
                if request.method == 'OPTIONS':
                    return ('', 204)
            return jsonify({'error': 'cross-origin request blocked'}), 403
        except Exception:
            return jsonify({'error': 'bad origin'}), 403

    @app.after_request
    def _security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        origin = request.headers.get('Origin', '')
        native_app_origins = {'http://localhost', 'https://localhost', 'capacitor://localhost', 'ionic://localhost'}
        if origin and config.get('server_lan_access', False) and origin.rstrip('/') in native_app_origins:
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-TypeKeep-Key'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        return response

    @app.errorhandler(Exception)
    def _handle_error(e):
        return jsonify({'error': str(e)}), 500

    # ── Helpers ────────────────────────────────────────────────

    def _time_range():
        start_arg = request.args.get('start', type=float)
        end_arg = request.args.get('end', type=float)
        if start_arg is not None or end_arg is not None:
            return start_arg, end_arg
        tr = request.args.get('range', '24h')
        now = time.time()
        if tr == 'today':
            import datetime
            midnight = datetime.datetime.now().replace(
                hour=0, minute=0, second=0, microsecond=0).timestamp()
            return midnight, now
        m = {'1h': 3600, '3h': 10800, '6h': 21600, '12h': 43200,
             '24h': 86400, '3d': 259200, '7d': 604800, '30d': 2592000,
             'all': None}
        secs = m.get(tr)
        return (now - secs) if secs else None, now

    # ── Pages ──────────────────────────────────────────────────

    @app.route('/')
    def index():
        return render_template('index.html')

    # ── Version & Health ───────────────────────────────────────

    @app.route('/api/version')
    def api_version():
        return jsonify({
            'version': APP_VERSION,
            'device_id': config.get('device_id'),
            'device_name': config.get('device_name'),
            'recording': recorder.recording,
            'uptime': time.time() - float(database.get_meta('last_launch', str(time.time()))),
        })

    @app.route('/api/health')
    def api_health():
        # v3.3.0: health now reports the data-safety counters so a
        # silent data-loss problem is visible instead of buried in a
        # log file nobody reads. Reading them costs nothing (no flush).
        dropped = getattr(recorder, '_dropped', 0)
        return jsonify({
            'status': 'ok',
            'version': APP_VERSION,
            'recording': recorder.recording,
            'sse_clients': app.sse_client_count(),
            'ts': time.time(),
            'data_safety': {
                'buffered_events': database.buffer_size(),
                'session_flushed': database.total_flushed,
                'sanitized_fields': database.sanitized_fields,
                'bad_rows_skipped': database.bad_rows_skipped,
                'overflow_drops': database.buffer_overflow_drops,
                'flush_errors': database.flush_errors,
                'recorder_drops': dropped,
                'last_flush_ts': database.last_flush_ts,
            },
        })

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
        split_enter = request.args.get('split_enter', str(config.get('split_on_enter', True)).lower()) == 'true'
        context_aware = request.args.get('context_aware', str(config.get('context_aware_grouping', True)).lower()) == 'true'
        smart_enter = request.args.get('smart_enter', str(config.get('smart_enter', True)).lower()) == 'true'
        start, end = _time_range()

        database.flush_buffer()
        messages, total = database.get_messages(
            gap_seconds=gap, same_window_gap=sw_gap,
            start_time=start, end_time=end,
            process=app_filter, search=search,
            min_length=min_len, sort=sort,
            limit=limit, offset=offset,
            split_on_enter=split_enter,
            context_aware=context_aware,
            smart_enter=smart_enter,
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
        return jsonify({
            'recording': recorder.recording,
            'version': APP_VERSION,
        })

    # ── Settings ───────────────────────────────────────────────

    @app.route('/api/settings', methods=['GET'])
    def api_get_settings():
        return jsonify(config.to_dict())

    @app.route('/api/settings', methods=['POST'])
    def api_set_settings():
        data = request.get_json(silent=True) or {}
        safe_keys = {
            'retention_days', 'default_gap_seconds', 'same_window_gap_seconds',
            'record_keyboard',
            'record_mouse_clicks', 'record_mouse_scroll', 'record_mouse_movement',
            'record_shortcuts', 'record_notifications', 'record_clipboard',
            'clipboard_retention_days', 'clipboard_poll_seconds', 'mouse_sample_ms',
            'min_message_length', 'max_messages_display', 'split_on_enter',
            'context_aware_grouping', 'smart_enter',
            'start_on_boot', 'start_background_on_boot', 'start_ui_on_boot',
            'start_minimized', 'show_onboarding',
            'auto_backup_enabled', 'buffer_flush_seconds', 'theme',
            'cloud_sync_enabled', 'supabase_url', 'supabase_anon_key',
            'cloud_sync_key', 'cloud_sync_clipboard', 'cloud_sync_messages',
            'cloud_sync_interval_seconds',
            'server_lan_access', 'auto_copy_remote_clipboard',
        }
        prev_lan = bool(config.get('server_lan_access', False))
        filtered = {k: v for k, v in data.items() if k in safe_keys}
        config.update(filtered)

        if 'start_on_boot' in filtered or 'start_background_on_boot' in filtered:
            boot_enabled = filtered.get('start_on_boot', config.get('start_on_boot', True))
            bg_mode = filtered.get('start_background_on_boot', config.get('start_background_on_boot', True))
            ui_on_boot = filtered.get('start_ui_on_boot', config.get('start_ui_on_boot', False))
            _set_startup(boot_enabled, bg_mode, ui_on_boot)

        if cloud_sync and any(k in filtered for k in (
                'cloud_sync_enabled', 'supabase_url',
                'supabase_anon_key', 'cloud_sync_key')):
            cloud_sync.restart()

        restart_needed = ('server_lan_access' in filtered
                          and bool(filtered['server_lan_access']) != prev_lan)
        return jsonify({
            'status': 'ok',
            'restart_required': restart_needed,
            'settings': config.to_dict(),
        })

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
                try:
                    m['actions'] = json.loads(m['actions'])
                except Exception:
                    m['actions'] = []
        return jsonify({'macros': macros})

    @app.route('/api/macros', methods=['POST'])
    def api_macros_create():
        data = request.get_json(silent=True) or {}
        name = data.get('name', 'Untitled')
        shortcut = data.get('shortcut', '')
        actions = data.get('actions', [])
        mid = database.create_macro(name, shortcut, actions)
        if hasattr(recorder, 'reload_macros'):
            recorder.reload_macros()
        return jsonify({'id': mid, 'status': 'ok'})

    @app.route('/api/macros/<int:mid>', methods=['PUT'])
    def api_macros_update(mid):
        data = request.get_json(silent=True) or {}
        database.update_macro(mid, data.get('name'), data.get('shortcut'),
                              data.get('actions'))
        if hasattr(recorder, 'reload_macros'):
            recorder.reload_macros()
        return jsonify({'status': 'ok'})

    @app.route('/api/macros/<int:mid>', methods=['DELETE'])
    def api_macros_delete(mid):
        database.delete_macro(mid)
        if hasattr(recorder, 'reload_macros'):
            recorder.reload_macros()
        return jsonify({'status': 'ok'})

    @app.route('/api/macros/<int:mid>/run', methods=['POST'])
    def api_macros_run(mid):
        macro = database.get_macro(mid)
        if not macro:
            return jsonify({'error': 'Macro not found'}), 404
        actions = macro.get('actions', '[]')
        if isinstance(actions, str):
            actions = json.loads(actions)
        threading.Thread(target=recorder.run_macro, args=(actions, mid),
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

    @app.route('/api/clipboard/add', methods=['POST'])
    def api_clipboard_add():
        data = request.get_json(silent=True) or {}
        text = (data.get('content_text') or data.get('text') or '').strip()
        if not text:
            return jsonify({'error': 'content_text required'}), 400
        eid = database.add_clipboard_entry(
            content_type=data.get('content_type', 'text'),
            content_text=text[:50000],
            source_app=data.get('source_app', 'Remote'),
            source_title=data.get('source_title', ''),
            device_id=data.get('device_id'),
        )
        copied = False
        if data.get('copy_to_os', True) and clipboard_monitor:
            copied = clipboard_monitor.set_text(text)
        if cloud_sync and cloud_sync.enabled and data.get('push_cloud', True):
            cloud_sync.push_clipboard_entry('text', text, data.get('source_app', 'TypeKeep'))
        _broadcast_sse('clipboard_copied', {'type': 'text', 'preview': text[:100], 'ts': time.time()})
        return jsonify({'status': 'ok', 'id': eid, 'copied_to_os': copied})

    @app.route('/api/clipboard/<int:eid>/copy-to-os', methods=['POST'])
    def api_clipboard_copy_to_os(eid):
        conn = database._get_conn()
        row = conn.execute(
            "SELECT content_type, content_text FROM clipboard_entries WHERE id=?",
            (eid,),
        ).fetchone()
        if not row or not row['content_text']:
            return jsonify({'error': 'Text entry not found'}), 404
        if not clipboard_monitor:
            return jsonify({'error': 'Clipboard monitor unavailable'}), 503
        ok = clipboard_monitor.set_text(row['content_text'])
        return jsonify({'status': 'ok' if ok else 'error', 'copied': ok})

    @app.route('/api/notes/quick', methods=['POST'])
    def api_notes_quick():
        data = request.get_json(silent=True) or {}
        text = (data.get('text') or '').strip()
        if not text:
            return jsonify({'error': 'text required'}), 400
        device_name = data.get('device_name') or config.get('device_name', 'Device')
        device_id = data.get('device_id') or config.get('device_id', '')
        app_name = data.get('app') or 'Quick Note'
        nid = database.add_remote_message(
            final_text=text,
            device_id=device_id,
            device_name=device_name,
            app=app_name,
            win_title=data.get('title') or f'Note from {device_name}',
        )
        copied = False
        if data.get('copy_to_clipboard') and clipboard_monitor:
            database.add_clipboard_entry(
                content_type='text',
                content_text=text,
                source_app=app_name,
                source_title=f'[{device_name}]',
                device_id=device_id,
            )
            copied = clipboard_monitor.set_text(text)
        if cloud_sync and cloud_sync.enabled:
            cloud_sync.push_quick_note(text, source_app=app_name, win_title=f'Note from {device_name}')
        _broadcast_sse('update', {'ts': time.time()})
        return jsonify({'status': 'ok', 'id': nid, 'copied_to_clipboard': copied})

    @app.route('/api/clips/<path:filename>')
    def api_serve_clip(filename):
        return send_from_directory(CLIPS_DIR, filename)

    # ── Backup & Restore ───────────────────────────────────────

    @app.route('/api/backup', methods=['POST'])
    def api_backup():
        database.maybe_backup()
        return jsonify({'status': 'ok'})

    @app.route('/api/backups')
    def api_backups():
        files = sorted(glob.glob(os.path.join(BACKUP_DIR, 'typekeep_*.db')), reverse=True)
        backups = []
        for f in files:
            backups.append({
                'filename': os.path.basename(f),
                'size_mb': round(os.path.getsize(f) / (1024 * 1024), 2),
                'modified': os.path.getmtime(f),
            })
        return jsonify({'backups': backups})

    # ── Sync / Devices ─────────────────────────────────────────

    @app.route('/api/sync/info')
    def api_sync_info():
        return jsonify({
            'device_id': config.get('device_id'),
            'device_name': config.get('device_name'),
            'sync_key': config.get('sync_key', ''),
            'sync_enabled': config.get('sync_enabled', False),
            'clipboard_sync': config.get('clipboard_sync', False),
            'port': config.get('server_port', 7700),
            'lan_access': config.get('server_lan_access', False),
            'lan_ips': _get_lan_ips(),
            'cloud_sync_enabled': config.get('cloud_sync_enabled', False),
            'cloud_sync_key': config.get('cloud_sync_key', ''),
        })

    @app.route('/api/sync/qr')
    def api_sync_qr():
        ips = _get_lan_ips()
        primary_ip = ips[0] if ips else '127.0.0.1'
        port_num = config.get('server_port', 7700)
        lan_url = f"http://{primary_ip}:{port_num}/mobile"
        cloud_key = config.get('cloud_sync_key', '') or config.get('sync_key', '')
        from urllib.parse import urlencode
        params = {}
        if cloud_key:
            params['key'] = cloud_key
        if config.get('server_lan_access', False):
            params['lan'] = f"http://{primary_ip}:{port_num}"
        pair_url = f"{lan_url}?{urlencode(params)}" if params else lan_url
        svg = _make_qr_svg(pair_url)
        return jsonify({
            'pair_url': pair_url,
            'lan_url': lan_url,
            'lan_ips': ips,
            'port': port_num,
            'lan_access': bool(config.get('server_lan_access', False)),
            'sync_key': cloud_key,
            'device_name': config.get('device_name'),
            'qr_svg': svg,
        })

    @app.route('/api/sync/info', methods=['POST'])
    def api_sync_info_update():
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
        data = request.get_json(silent=True) or {}
        ip = data.get('ip', '').strip()
        port_num = int(data.get('port', 7700))
        key = data.get('sync_key', '').strip()

        if not ip:
            return jsonify({'error': 'IP address required'}), 400

        import requests as rq
        try:
            r = rq.get(f'http://{ip}:{port_num}/api/sync/handshake',
                       params={'key': key, 'device_id': config.get('device_id'),
                               'device_name': config.get('device_name'),
                               'port': config.get('server_port', 7700)},
                       timeout=5)
            if r.status_code != 200:
                return jsonify({'error': 'Pairing rejected: ' + r.json().get('error', 'unknown')}), 400
            remote = r.json()
        except Exception as exc:
            return jsonify({'error': f'Cannot reach device: {exc}'}), 400

        database.upsert_device(
            remote['device_id'], remote['device_name'],
            ip, port_num,
            sync_enabled=1,
            clipboard_sync=int(data.get('clipboard_sync', False)),
        )
        return jsonify({'status': 'ok', 'device': remote})

    @app.route('/api/sync/handshake')
    def api_sync_handshake():
        key = request.args.get('key', '')
        my_key = config.get('sync_key', '')
        if not config.get('sync_enabled', False):
            return jsonify({'error': 'Sync is disabled on this device'}), 403
        if not my_key or key != my_key:
            return jsonify({'error': 'Invalid sync key'}), 403

        remote_id = request.args.get('device_id', '')
        remote_name = request.args.get('device_name', 'Unknown')
        if remote_id:
            remote_ip = request.remote_addr
            remote_port = request.args.get('port', 7700, type=int)
            database.upsert_device(
                remote_id, remote_name, remote_ip, remote_port,
                sync_enabled=1, clipboard_sync=0)

        return jsonify({
            'device_id': config.get('device_id'),
            'device_name': config.get('device_name'),
            'port': config.get('server_port', 7700),
            'status': 'ok',
        })

    @app.route('/api/sync/unpair/<device_id>', methods=['DELETE'])
    def api_sync_unpair(device_id):
        database.remove_device(device_id)
        return jsonify({'status': 'ok'})

    @app.route('/api/sync/pull', methods=['POST'])
    def api_sync_pull():
        data = request.get_json(silent=True) or {}
        if not config.get('sync_enabled', False):
            return jsonify({'error': 'Sync is disabled on this device'}), 403
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

        imported = 0
        for entry in remote_data.get('clipboard', []):
            if database.clipboard_entry_exists(
                    entry['content_type'],
                    entry.get('content_text'),
                    device_id=device_id,
                    source_app=entry.get('source_app'),
                    since_seconds=86400):
                continue
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
        key = request.args.get('key', '')
        my_key = config.get('sync_key', '')
        if not config.get('sync_enabled', False):
            return jsonify({'error': 'Sync is disabled on this device'}), 403
        if not my_key or key != my_key:
            return jsonify({'error': 'Unauthorized'}), 403

        data_type = request.args.get('type', 'clipboard')
        result = {}
        if data_type in ('clipboard', 'all'):
            entries, _ = database.get_clipboard(limit=500)
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
        key = request.args.get('key', '')
        my_key = config.get('sync_key', '')
        if not config.get('sync_enabled', False):
            return jsonify({'error': 'Sync is disabled on this device'}), 403
        if not my_key or key != my_key:
            return jsonify({'error': 'Unauthorized'}), 403

        data = request.get_json(silent=True) or {}
        if data.get('content_type'):
            if database.clipboard_entry_exists(
                    data['content_type'],
                    data.get('content_text'),
                    device_id=data.get('device_id'),
                    source_app=data.get('source_app'),
                    since_seconds=86400):
                return jsonify({'status': 'ok', 'duplicate': True})
            database.add_clipboard_entry(
                content_type=data['content_type'],
                content_text=data.get('content_text'),
                source_app=data.get('source_app'),
                source_title=data.get('source_title'),
                extra=data.get('extra'),
                device_id=data.get('device_id'),
            )
        return jsonify({'status': 'ok'})

    # ── Cloud Sync API ──────────────────────────────────────────

    @app.route('/api/cloud/status')
    def api_cloud_status():
        if not cloud_sync:
            return jsonify({'available': False})
        return jsonify({
            'available': True,
            'enabled': cloud_sync.enabled,
            'connected': cloud_sync.enabled,
            'sync_key': config.get('cloud_sync_key', ''),
            'supabase_url': config.get('supabase_url', ''),
        })

    @app.route('/api/cloud/test', methods=['POST'])
    def api_cloud_test():
        if not cloud_sync:
            return jsonify({'status': 'error', 'error': 'Cloud sync not available'}), 400
        result = cloud_sync.test_connection()
        return jsonify(result)

    @app.route('/api/cloud/devices')
    def api_cloud_devices():
        if not cloud_sync:
            return jsonify({'devices': []})
        devices = cloud_sync.get_cloud_devices()
        return jsonify({'devices': devices})

    @app.route('/api/cloud/clipboard')
    def api_cloud_clipboard():
        if not cloud_sync:
            return jsonify({'entries': []})
        limit = request.args.get('limit', 50, type=int)
        entries = cloud_sync.get_cloud_clipboard(limit)
        return jsonify({'entries': entries})

    @app.route('/api/cloud/messages')
    def api_cloud_messages():
        if not cloud_sync:
            return jsonify({'messages': []})
        limit = request.args.get('limit', 50, type=int)
        messages = cloud_sync.get_cloud_messages(limit)
        return jsonify({'messages': messages})

    @app.route('/api/cloud/push-clipboard', methods=['POST'])
    def api_cloud_push_clipboard():
        if not cloud_sync:
            return jsonify({'error': 'Cloud sync not available'}), 400
        data = request.get_json(silent=True) or {}
        ok = cloud_sync.push_clipboard_entry(
            content_type=data.get('content_type', 'text'),
            content_text=data.get('content_text', ''),
            source_app=data.get('source_app', 'API'),
        )
        return jsonify({'status': 'ok' if ok else 'error'})

    # ── Server-Sent Events (live updates) ────────────────────

    @app.route('/api/events-stream')
    def api_sse():
        client_q = queue.Queue(maxsize=50)
        with _sse_lock:
            _sse_clients.append(client_q)

        def generate():
            try:
                yield 'event: connected\ndata: {}\n\n'
                while True:
                    try:
                        msg = client_q.get(timeout=15)
                        yield msg
                    except queue.Empty:
                        yield ': keepalive\n\n'
            except GeneratorExit:
                pass
            finally:
                with _sse_lock:
                    if client_q in _sse_clients:
                        _sse_clients.remove(client_q)

        return Response(
            generate(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no',
            },
        )

    # ── Mobile PWA serving ─────────────────────────────────────

    @app.route('/mobile')
    @app.route('/mobile/')
    def serve_mobile():
        mobile_dir = os.path.join(BUNDLE_DIR, 'mobile')
        return send_from_directory(mobile_dir, 'index.html')

    @app.route('/mobile/<path:filename>')
    def serve_mobile_files(filename):
        mobile_dir = os.path.join(BUNDLE_DIR, 'mobile')
        return send_from_directory(mobile_dir, filename)

    # ── Startup helper (Windows registry) ──────────────────────

    def _set_startup(enabled, bg_mode=True, ui_on_boot=False):
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE)
            if enabled:
                exe = sys.executable
                if getattr(sys, 'frozen', False):
                    base_cmd = f'"{exe}"'
                else:
                    script = os.path.abspath(os.path.join(APP_DIR, 'typekeep.py'))
                    if exe.lower().endswith('python.exe'):
                        pyw = exe[:-10] + 'pythonw.exe'
                        if os.path.exists(pyw):
                            exe = pyw
                    base_cmd = f'"{exe}" "{script}"'
                if bg_mode and not ui_on_boot:
                    winreg.SetValueEx(key, 'TypeKeep', 0, winreg.REG_SZ,
                                      f'{base_cmd} --background')
                else:
                    winreg.SetValueEx(key, 'TypeKeep', 0, winreg.REG_SZ,
                                      base_cmd)
            else:
                try:
                    winreg.DeleteValue(key, 'TypeKeep')
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as exc:
            print(f"[TypeKeep] Startup registry error: {exc}")

    return app
