"""TypeKeep Database - SQLite storage with buffered writes and message grouping."""

import sqlite3
import threading
import time
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_FILE = os.path.join(DATA_DIR, 'typekeep.db')


class Database:
    """Thread-safe SQLite database with buffered inserts and WAL mode."""

    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self._local = threading.local()
        self._buffer = []
        self._buffer_lock = threading.Lock()
        self._init_db()

    # ── Connection management ──────────────────────────────────────

    def _get_conn(self):
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            conn = sqlite3.connect(DB_FILE, timeout=15)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-8000")  # 8 MB cache
            conn.execute("PRAGMA temp_store=MEMORY")
            self._local.conn = conn
        return self._local.conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                event_type TEXT NOT NULL,
                key_name TEXT,
                character TEXT,
                modifiers TEXT,
                window_title TEXT,
                window_process TEXT,
                extra TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp);
            CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
            CREATE INDEX IF NOT EXISTS idx_events_proc ON events(window_process);
        """)
        conn.commit()

    # ── Buffered writes ────────────────────────────────────────────

    def buffer_event(self, event: dict):
        with self._buffer_lock:
            self._buffer.append(event)

    def flush_buffer(self):
        with self._buffer_lock:
            if not self._buffer:
                return
            batch = list(self._buffer)
            self._buffer.clear()

        conn = self._get_conn()
        try:
            conn.executemany(
                """INSERT INTO events
                   (timestamp, event_type, key_name, character, modifiers,
                    window_title, window_process, extra)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [(e['timestamp'], e['event_type'], e['key_name'],
                  e['character'], e['modifiers'], e['window_title'],
                  e['window_process'], e['extra']) for e in batch]
            )
            conn.commit()
        except Exception as exc:
            print(f"[TypeKeep] DB flush error: {exc}")

    # ── Queries ────────────────────────────────────────────────────

    def get_events(self, start_time=None, end_time=None,
                   event_type=None, process=None):
        conn = self._get_conn()
        clauses, params = ["1=1"], []

        if start_time is not None:
            clauses.append("timestamp >= ?"); params.append(start_time)
        if end_time is not None:
            clauses.append("timestamp <= ?"); params.append(end_time)
        if event_type:
            clauses.append("event_type = ?"); params.append(event_type)
        if process:
            clauses.append("window_process = ?"); params.append(process)

        sql = f"SELECT * FROM events WHERE {' AND '.join(clauses)} ORDER BY timestamp ASC"
        return [dict(r) for r in conn.execute(sql, params).fetchall()]

    # ── Message grouping ───────────────────────────────────────────

    def get_messages(self, gap_seconds=5, start_time=None, end_time=None,
                     process=None, search=None, min_length=1,
                     sort='newest', limit=50, offset=0):
        """Group key_press events into messages split by time gaps."""
        events = self.get_events(start_time, end_time, 'key_press', process)

        messages = []
        group = []

        for ev in events:
            if group and (ev['timestamp'] - group[-1]['timestamp']) > gap_seconds:
                msg = self._build_message(group)
                if msg and len(msg['text'].strip()) >= min_length:
                    messages.append(msg)
                group = []
            group.append(ev)

        if group:
            msg = self._build_message(group)
            if msg and len(msg['text'].strip()) >= min_length:
                messages.append(msg)

        # Search filter
        if search:
            q = search.lower()
            messages = [m for m in messages if q in m['text'].lower()]

        # Sort
        if sort == 'newest':
            messages.reverse()

        total = len(messages)
        page = messages[offset:offset + limit]
        return page, total

    def _build_message(self, events):
        text = self._reconstruct_text(events)
        raw = self._reconstruct_raw(events)
        if not text and not raw:
            return None

        # Most-frequent process
        procs = {}
        for e in events:
            p = e.get('window_process') or 'Unknown'
            procs[p] = procs.get(p, 0) + 1
        main_proc = max(procs, key=procs.get) if procs else 'Unknown'

        window = ''
        for e in events:
            if e.get('window_process') == main_proc and e.get('window_title'):
                window = e['window_title']
                break

        return {
            'start_time': events[0]['timestamp'],
            'end_time': events[-1]['timestamp'],
            'text': text,
            'raw_text': raw,
            'app': main_proc,
            'window': window,
            'keystroke_count': len(events),
            'duration': round(events[-1]['timestamp'] - events[0]['timestamp'], 2),
        }

    @staticmethod
    def _reconstruct_text(events):
        chars = []
        for e in events:
            mods = (e.get('modifiers') or '').lower()
            if 'ctrl' in mods or 'alt' in mods:
                continue

            ch = e.get('character')
            kn = (e.get('key_name') or '').lower()

            if ch and len(ch) == 1:
                chars.append(ch)
            elif 'space' in kn:
                chars.append(' ')
            elif 'enter' in kn or 'return' in kn:
                chars.append('\n')
            elif 'tab' in kn:
                chars.append('\t')
            elif 'backspace' in kn:
                if chars:
                    chars.pop()
        return ''.join(chars)

    @staticmethod
    def _reconstruct_raw(events):
        parts = []
        for e in events:
            mods = (e.get('modifiers') or '').lower()
            ch = e.get('character')
            kn = (e.get('key_name') or '')
            kn_low = kn.lower()

            if 'ctrl' in mods or 'alt' in mods:
                prefix = ''
                if 'ctrl' in mods:
                    prefix += 'Ctrl+'
                if 'alt' in mods:
                    prefix += 'Alt+'
                parts.append(f'[{prefix}{kn}]')
                continue

            if ch and len(ch) == 1:
                parts.append(ch)
            elif 'space' in kn_low:
                parts.append(' ')
            elif 'enter' in kn_low or 'return' in kn_low:
                parts.append('\u21b5\n')
            elif 'tab' in kn_low:
                parts.append('\u21e5')
            elif 'backspace' in kn_low:
                parts.append('\u232b')
            elif 'delete' in kn_low:
                parts.append('[Del]')
            elif 'escape' in kn_low:
                parts.append('[Esc]')
            else:
                clean = kn.replace('Key.', '')
                skip = {'shift', 'shift_r', 'ctrl_l', 'ctrl_r',
                        'alt_l', 'alt_r', 'alt_gr', 'cmd', 'cmd_r', 'caps_lock'}
                if clean and clean.lower() not in skip:
                    parts.append(f'[{clean}]')
        return ''.join(parts)

    # ── Utility queries ────────────────────────────────────────────

    def get_apps(self, start_time=None, end_time=None):
        conn = self._get_conn()
        clauses = ["window_process IS NOT NULL", "window_process != ''"]
        params = []
        if start_time is not None:
            clauses.append("timestamp >= ?"); params.append(start_time)
        if end_time is not None:
            clauses.append("timestamp <= ?"); params.append(end_time)
        sql = f"SELECT DISTINCT window_process FROM events WHERE {' AND '.join(clauses)} ORDER BY window_process"
        return [r['window_process'] for r in conn.execute(sql, params).fetchall()]

    def get_stats(self):
        conn = self._get_conn()
        now = time.time()
        day_ago = now - 86400

        total = conn.execute("SELECT COUNT(*) c FROM events").fetchone()['c']
        today = conn.execute("SELECT COUNT(*) c FROM events WHERE timestamp >= ?",
                             (day_ago,)).fetchone()['c']
        keys = conn.execute("SELECT COUNT(*) c FROM events WHERE event_type='key_press'"
                            ).fetchone()['c']
        clicks = conn.execute("SELECT COUNT(*) c FROM events WHERE event_type='mouse_click'"
                              ).fetchone()['c']
        oldest = conn.execute("SELECT MIN(timestamp) m FROM events").fetchone()['m']

        db_size = 0
        if os.path.exists(DB_FILE):
            db_size = round(os.path.getsize(DB_FILE) / (1024 * 1024), 2)

        return {
            'total_events': total,
            'events_24h': today,
            'total_keystrokes': keys,
            'total_mouse_clicks': clicks,
            'oldest_event': oldest,
            'db_size_mb': db_size,
        }

    def cleanup(self, retention_days):
        cutoff = time.time() - (retention_days * 86400)
        conn = self._get_conn()
        conn.execute("DELETE FROM events WHERE timestamp < ?", (cutoff,))
        conn.commit()

    def close(self):
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
