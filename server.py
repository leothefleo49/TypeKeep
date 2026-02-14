"""TypeKeep Flask Server - API + web dashboard."""

import time
import logging
from flask import Flask, jsonify, request, render_template


def create_app(database, recorder, config):
    app = Flask(__name__)
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

    # Suppress noisy request logs
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.WARNING)

    # ── Pages ──────────────────────────────────────────────────────

    @app.route('/')
    def index():
        return render_template('index.html')

    # ── API: messages ──────────────────────────────────────────────

    @app.route('/api/messages')
    def api_messages():
        gap = request.args.get('gap', config.get('default_gap_seconds', 5), type=float)
        time_range = request.args.get('range', '24h')
        app_filter = request.args.get('app', '') or None
        search = request.args.get('search', '') or None
        min_length = request.args.get('min_length', config.get('min_message_length', 1), type=int)
        sort = request.args.get('sort', 'newest')
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)

        now = time.time()
        range_map = {
            '1h': 3600, '3h': 10800, '6h': 21600, '12h': 43200,
            '24h': 86400, '3d': 259200, '7d': 604800, 'all': None,
        }
        secs = range_map.get(time_range)
        start_time = (now - secs) if secs else None

        # Flush so latest keystrokes are visible
        database.flush_buffer()

        messages, total = database.get_messages(
            gap_seconds=gap,
            start_time=start_time,
            end_time=now,
            process=app_filter,
            search=search,
            min_length=min_length,
            sort=sort,
            limit=limit,
            offset=offset,
        )

        return jsonify({'messages': messages, 'total': total,
                        'has_more': (offset + limit) < total})

    # ── API: settings ──────────────────────────────────────────────

    @app.route('/api/settings', methods=['GET'])
    def api_get_settings():
        return jsonify(config.to_dict())

    @app.route('/api/settings', methods=['POST'])
    def api_set_settings():
        data = request.get_json(silent=True) or {}
        safe_keys = {
            'retention_days', 'default_gap_seconds', 'record_mouse_clicks',
            'record_mouse_scroll', 'min_message_length', 'max_messages_display',
        }
        filtered = {k: v for k, v in data.items() if k in safe_keys}
        config.update(filtered)
        return jsonify({'status': 'ok', 'settings': config.to_dict()})

    # ── API: stats ─────────────────────────────────────────────────

    @app.route('/api/stats')
    def api_stats():
        database.flush_buffer()
        return jsonify(database.get_stats())

    # ── API: apps list ─────────────────────────────────────────────

    @app.route('/api/apps')
    def api_apps():
        time_range = request.args.get('range', '24h')
        now = time.time()
        range_map = {
            '1h': 3600, '3h': 10800, '6h': 21600, '12h': 43200,
            '24h': 86400, '3d': 259200, '7d': 604800, 'all': None,
        }
        secs = range_map.get(time_range)
        start = (now - secs) if secs else None
        return jsonify(database.get_apps(start_time=start))

    # ── API: recording toggle / status ─────────────────────────────

    @app.route('/api/toggle', methods=['POST'])
    def api_toggle():
        recorder.recording = not recorder.recording
        return jsonify({'recording': recorder.recording})

    @app.route('/api/status')
    def api_status():
        return jsonify({'recording': recorder.recording})

    return app
