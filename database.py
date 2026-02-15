"""TypeKeep Database - SQLite storage with buffered writes, context-aware grouping,
cursor-position-aware text reconstruction, macros, import/export."""

import sqlite3
import threading
import time
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_FILE = os.path.join(DATA_DIR, 'typekeep.db')


class Database:
    """Thread-safe SQLite database with WAL mode and buffered inserts."""

    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self._local = threading.local()
        self._buffer = []
        self._buffer_lock = threading.Lock()
        self._init_db()

    # ── Connection ─────────────────────────────────────────────

    def _get_conn(self):
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            conn = sqlite3.connect(DB_FILE, timeout=15)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-8000")
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
            CREATE INDEX IF NOT EXISTS idx_events_ts   ON events(timestamp);
            CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
            CREATE INDEX IF NOT EXISTS idx_events_proc ON events(window_process);

            CREATE TABLE IF NOT EXISTS macros (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                shortcut TEXT,
                actions TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS clipboard_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                content_type TEXT NOT NULL,
                content_text TEXT,
                file_path TEXT,
                thumbnail_path TEXT,
                source_app TEXT,
                source_title TEXT,
                extra TEXT,
                pinned INTEGER DEFAULT 0,
                device_id TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_clip_ts   ON clipboard_entries(timestamp);
            CREATE INDEX IF NOT EXISTS idx_clip_type ON clipboard_entries(content_type);

            CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                ip_address TEXT,
                port INTEGER,
                last_seen REAL,
                sync_enabled INTEGER DEFAULT 1,
                clipboard_sync INTEGER DEFAULT 0,
                created_at REAL NOT NULL
            );
        """)
        conn.commit()

    # ── Buffered writes ────────────────────────────────────────

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
                   (timestamp,event_type,key_name,character,modifiers,
                    window_title,window_process,extra)
                   VALUES (?,?,?,?,?,?,?,?)""",
                [(e['timestamp'], e['event_type'], e['key_name'],
                  e['character'], e['modifiers'], e['window_title'],
                  e['window_process'], e.get('extra')) for e in batch]
            )
            conn.commit()
        except Exception as exc:
            print(f"[TypeKeep] DB flush error: {exc}")

    # ── Raw event queries ──────────────────────────────────────

    def get_events(self, start_time=None, end_time=None,
                   event_type=None, process=None, limit=None):
        conn = self._get_conn()
        clauses, params = ["1=1"], []
        if start_time is not None:
            clauses.append("timestamp >= ?"); params.append(start_time)
        if end_time is not None:
            clauses.append("timestamp <= ?"); params.append(end_time)
        if event_type:
            if ',' in event_type:
                types = event_type.split(',')
                placeholders = ','.join('?' * len(types))
                clauses.append(f"event_type IN ({placeholders})")
                params.extend(types)
            else:
                clauses.append("event_type = ?"); params.append(event_type)
        if process:
            clauses.append("window_process = ?"); params.append(process)
        sql = f"SELECT * FROM events WHERE {' AND '.join(clauses)} ORDER BY timestamp ASC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [dict(r) for r in conn.execute(sql, params).fetchall()]

    # ── Context-aware message grouping ─────────────────────────

    def get_messages(self, gap_seconds=5, same_window_gap=30,
                     start_time=None, end_time=None,
                     process=None, search=None, min_length=1,
                     sort='newest', limit=50, offset=0,
                     split_on_enter=False):
        """Group key_press events into messages using context-aware grouping.

        Same-window events tolerate a larger time gap (same_window_gap).
        Different-window transitions always split.
        """
        events = self.get_events(start_time, end_time, 'key_press', process)
        groups = self._group_events(events, gap_seconds, same_window_gap,
                                    split_on_enter)
        messages = []
        for grp in groups:
            msg = self._build_message(grp)
            if msg and len(msg['final_text'].strip()) >= min_length:
                messages.append(msg)

        if search:
            q = search.lower()
            messages = [m for m in messages
                        if q in m['final_text'].lower()
                        or q in m['raw_text'].lower()]

        if sort == 'newest':
            messages.reverse()

        total = len(messages)
        page = messages[offset:offset + limit]
        return page, total

    def _group_events(self, events, base_gap, same_window_gap,
                      split_on_enter):
        """Split events into groups by window context + time gaps."""
        if not events:
            return []
        groups = []
        group = [events[0]]

        for ev in events[1:]:
            last = group[-1]
            dt = ev['timestamp'] - last['timestamp']
            same_win = (ev.get('window_process') == last.get('window_process')
                        and ev.get('window_title') == last.get('window_title'))

            # Split on Enter if configured
            if split_on_enter:
                kn = (last.get('key_name') or '').lower()
                if 'enter' in kn or 'return' in kn:
                    groups.append(group)
                    group = [ev]
                    continue

            if same_win:
                if dt > same_window_gap:
                    groups.append(group)
                    group = [ev]
                else:
                    group.append(ev)
            else:
                if dt > base_gap:
                    groups.append(group)
                    group = [ev]
                else:
                    group.append(ev)

        if group:
            groups.append(group)
        return groups

    # ── Message construction ───────────────────────────────────

    def _build_message(self, events):
        final_text = self._reconstruct_final(events)
        raw_text = self._reconstruct_raw(events)
        chrono_text = self._reconstruct_chronological(events)
        if not final_text and not raw_text:
            return None

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
            'final_text': final_text,
            'raw_text': raw_text,
            'chrono_text': chrono_text,
            'app': main_proc,
            'window': window,
            'keystroke_count': len(events),
            'duration': round(events[-1]['timestamp'] - events[0]['timestamp'], 2),
        }

    @staticmethod
    def _reconstruct_final(events):
        """Rebuild text with cursor-position-aware editing (backspace, arrows, etc.)."""
        buf = []
        cur = 0
        for e in events:
            mods = (e.get('modifiers') or '').lower()
            if 'ctrl' in mods or 'alt' in mods:
                continue
            ch = e.get('character')
            kn = (e.get('key_name') or '').lower()

            if ch and len(ch) == 1:
                buf.insert(cur, ch); cur += 1
            elif 'backspace' in kn:
                if cur > 0:
                    cur -= 1; buf.pop(cur)
            elif 'space' in kn:
                buf.insert(cur, ' '); cur += 1
            elif 'enter' in kn or 'return' in kn:
                buf.insert(cur, '\n'); cur += 1
            elif 'tab' in kn:
                buf.insert(cur, '\t'); cur += 1
            elif kn == 'key.delete' or kn == 'delete':
                if cur < len(buf):
                    buf.pop(cur)
            elif 'left' in kn and 'alt' not in kn:
                if cur > 0: cur -= 1
            elif 'right' in kn and 'alt' not in kn:
                if cur < len(buf): cur += 1
            elif 'home' in kn:
                # move to start of line
                while cur > 0 and (cur <= len(buf) and buf[cur - 1] != '\n'):
                    cur -= 1
            elif 'end' in kn:
                while cur < len(buf) and buf[cur] != '\n':
                    cur += 1
        return ''.join(buf)

    @staticmethod
    def _reconstruct_raw(events):
        """Show every keystroke with symbols for special keys."""
        parts = []
        for e in events:
            mods = (e.get('modifiers') or '').lower()
            ch = e.get('character')
            kn = e.get('key_name') or ''
            kn_low = kn.lower()

            if 'ctrl' in mods or 'alt' in mods:
                prefix = ''
                if 'ctrl' in mods: prefix += 'Ctrl+'
                if 'alt' in mods: prefix += 'Alt+'
                parts.append(f'[{prefix}{kn}]')
                continue

            if ch and len(ch) == 1:
                parts.append(ch)
            elif 'backspace' in kn_low:
                parts.append('\u232b')
            elif 'space' in kn_low:
                parts.append(' ')
            elif 'enter' in kn_low or 'return' in kn_low:
                parts.append('\u21b5\n')
            elif 'tab' in kn_low:
                parts.append('\u21e5')
            elif 'delete' in kn_low:
                parts.append('\u2326')
            elif 'left' in kn_low:
                parts.append('\u2190')
            elif 'right' in kn_low:
                parts.append('\u2192')
            elif 'up' in kn_low:
                parts.append('\u2191')
            elif 'down' in kn_low:
                parts.append('\u2193')
            elif 'home' in kn_low:
                parts.append('[Home]')
            elif 'end' in kn_low:
                parts.append('[End]')
            elif 'escape' in kn_low:
                parts.append('[Esc]')
            else:
                clean = kn.replace('Key.', '')
                skip = {'shift', 'shift_r', 'ctrl_l', 'ctrl_r',
                        'alt_l', 'alt_r', 'alt_gr', 'cmd', 'cmd_r',
                        'caps_lock'}
                if clean and clean.lower() not in skip:
                    parts.append(f'[{clean}]')
        return ''.join(parts)

    @staticmethod
    def _reconstruct_chronological(events):
        """One-line-per-keystroke view with timestamps."""
        lines = []
        for e in events:
            ts = time.strftime('%H:%M:%S', time.localtime(e['timestamp']))
            ch = e.get('character') or ''
            kn = e.get('key_name') or ''
            mods = e.get('modifiers') or ''
            display = ch if (ch and len(ch) == 1) else kn.replace('Key.', '')
            if mods:
                display = f"{mods}+{display}"
            lines.append(f"[{ts}] {display}")
        return '\n'.join(lines)

    # ── Activity queries ───────────────────────────────────────

    def get_activity(self, start_time=None, end_time=None,
                     event_types=None, limit=200):
        """Return non-key events (clicks, moves, shortcuts, notifications)."""
        conn = self._get_conn()
        clauses = ["event_type != 'key_press'"]
        params = []
        if start_time:
            clauses.append("timestamp >= ?"); params.append(start_time)
        if end_time:
            clauses.append("timestamp <= ?"); params.append(end_time)
        if event_types:
            types = event_types if isinstance(event_types, list) else event_types.split(',')
            placeholders = ','.join('?' * len(types))
            clauses.append(f"event_type IN ({placeholders})")
            params.extend(types)
        sql = (f"SELECT * FROM events WHERE {' AND '.join(clauses)} "
               f"ORDER BY timestamp DESC LIMIT ?")
        params.append(limit)
        return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def get_shortcuts(self, start_time=None, end_time=None, limit=200):
        return self.get_activity(start_time, end_time, ['shortcut'], limit)

    # ── Stats ──────────────────────────────────────────────────

    def get_stats(self):
        conn = self._get_conn()
        now = time.time()
        day_ago = now - 86400
        total = conn.execute("SELECT COUNT(*) c FROM events").fetchone()['c']
        today = conn.execute("SELECT COUNT(*) c FROM events WHERE timestamp>=?",
                             (day_ago,)).fetchone()['c']
        keys = conn.execute("SELECT COUNT(*) c FROM events WHERE event_type='key_press'").fetchone()['c']
        clicks = conn.execute("SELECT COUNT(*) c FROM events WHERE event_type='mouse_click'").fetchone()['c']
        shortcuts = conn.execute("SELECT COUNT(*) c FROM events WHERE event_type='shortcut'").fetchone()['c']
        oldest = conn.execute("SELECT MIN(timestamp) m FROM events").fetchone()['m']
        db_size = 0
        if os.path.exists(DB_FILE):
            db_size = round(os.path.getsize(DB_FILE) / (1024 * 1024), 2)
        return {
            'total_events': total,
            'events_24h': today,
            'total_keystrokes': keys,
            'total_mouse_clicks': clicks,
            'total_shortcuts': shortcuts,
            'oldest_event': oldest,
            'db_size_mb': db_size,
        }

    def get_apps(self, start_time=None, end_time=None):
        conn = self._get_conn()
        clauses = ["window_process IS NOT NULL", "window_process != ''"]
        params = []
        if start_time:
            clauses.append("timestamp >= ?"); params.append(start_time)
        if end_time:
            clauses.append("timestamp <= ?"); params.append(end_time)
        sql = (f"SELECT DISTINCT window_process FROM events "
               f"WHERE {' AND '.join(clauses)} ORDER BY window_process")
        return [r['window_process'] for r in conn.execute(sql, params).fetchall()]

    # ── Delete operations ──────────────────────────────────────

    def delete_events_range(self, start_time, end_time, process=None):
        conn = self._get_conn()
        clauses = ["timestamp >= ?", "timestamp <= ?"]
        params = [start_time, end_time]
        if process:
            clauses.append("window_process = ?"); params.append(process)
        conn.execute(f"DELETE FROM events WHERE {' AND '.join(clauses)}", params)
        conn.commit()
        return conn.total_changes

    def delete_all_events(self):
        conn = self._get_conn()
        conn.execute("DELETE FROM events")
        conn.commit()
        try:
            conn.execute("VACUUM")
        except Exception:
            pass

    def cleanup(self, retention_days):
        cutoff = time.time() - (retention_days * 86400)
        conn = self._get_conn()
        conn.execute("DELETE FROM events WHERE timestamp < ?", (cutoff,))
        conn.commit()

    # ── Macros CRUD ────────────────────────────────────────────

    def get_macros(self):
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM macros ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    def get_macro(self, macro_id):
        conn = self._get_conn()
        r = conn.execute("SELECT * FROM macros WHERE id=?", (macro_id,)).fetchone()
        return dict(r) if r else None

    def create_macro(self, name, shortcut, actions):
        conn = self._get_conn()
        now = time.time()
        cur = conn.execute(
            "INSERT INTO macros (name,shortcut,actions,created_at,updated_at) VALUES (?,?,?,?,?)",
            (name, shortcut, json.dumps(actions), now, now))
        conn.commit()
        return cur.lastrowid

    def update_macro(self, macro_id, name=None, shortcut=None, actions=None):
        conn = self._get_conn()
        sets, params = [], []
        if name is not None:
            sets.append("name=?"); params.append(name)
        if shortcut is not None:
            sets.append("shortcut=?"); params.append(shortcut)
        if actions is not None:
            sets.append("actions=?"); params.append(json.dumps(actions))
        sets.append("updated_at=?"); params.append(time.time())
        params.append(macro_id)
        conn.execute(f"UPDATE macros SET {','.join(sets)} WHERE id=?", params)
        conn.commit()

    def delete_macro(self, macro_id):
        conn = self._get_conn()
        conn.execute("DELETE FROM macros WHERE id=?", (macro_id,))
        conn.commit()

    # ── Import / Export ────────────────────────────────────────

    def export_data(self, start_time=None, end_time=None):
        events = self.get_events(start_time, end_time)
        macros = self.get_macros()
        return {'events': events, 'macros': macros,
                'exported_at': time.time(), 'version': 2}

    def import_data(self, data, merge=True):
        conn = self._get_conn()
        imported = 0
        events = data.get('events', [])
        if events:
            conn.executemany(
                """INSERT INTO events
                   (timestamp,event_type,key_name,character,modifiers,
                    window_title,window_process,extra)
                   VALUES (?,?,?,?,?,?,?,?)""",
                [(e['timestamp'], e['event_type'], e.get('key_name'),
                  e.get('character'), e.get('modifiers'),
                  e.get('window_title'), e.get('window_process'),
                  e.get('extra')) for e in events])
            imported += len(events)
        macros = data.get('macros', [])
        for m in macros:
            actions = m.get('actions', '[]')
            if isinstance(actions, list):
                actions = json.dumps(actions)
            conn.execute(
                "INSERT INTO macros (name,shortcut,actions,created_at,updated_at) VALUES (?,?,?,?,?)",
                (m['name'], m.get('shortcut', ''), actions,
                 m.get('created_at', time.time()), time.time()))
            imported += 1
        conn.commit()
        return imported

    # ── Clipboard CRUD ─────────────────────────────────────────

    def add_clipboard_entry(self, content_type, content_text=None,
                            file_path=None, thumbnail_path=None,
                            source_app=None, source_title=None,
                            extra=None, device_id=None):
        conn = self._get_conn()
        cur = conn.execute(
            """INSERT INTO clipboard_entries
               (timestamp,content_type,content_text,file_path,thumbnail_path,
                source_app,source_title,extra,device_id)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (time.time(), content_type, content_text, file_path,
             thumbnail_path, source_app, source_title, extra, device_id))
        conn.commit()
        return cur.lastrowid

    def get_clipboard(self, start_time=None, end_time=None,
                      content_type=None, search=None,
                      limit=100, offset=0, pinned_only=False):
        conn = self._get_conn()
        clauses, params = ["1=1"], []
        if start_time:
            clauses.append("timestamp >= ?"); params.append(start_time)
        if end_time:
            clauses.append("timestamp <= ?"); params.append(end_time)
        if content_type:
            clauses.append("content_type = ?"); params.append(content_type)
        if search:
            clauses.append("content_text LIKE ?"); params.append(f'%{search}%')
        if pinned_only:
            clauses.append("pinned = 1")
        total_sql = f"SELECT COUNT(*) c FROM clipboard_entries WHERE {' AND '.join(clauses)}"
        total = conn.execute(total_sql, params).fetchone()['c']
        sql = (f"SELECT * FROM clipboard_entries WHERE {' AND '.join(clauses)} "
               f"ORDER BY pinned DESC, timestamp DESC LIMIT ? OFFSET ?")
        params.extend([limit, offset])
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
        return rows, total

    def toggle_clipboard_pin(self, entry_id):
        conn = self._get_conn()
        conn.execute(
            "UPDATE clipboard_entries SET pinned = CASE WHEN pinned=1 THEN 0 ELSE 1 END WHERE id=?",
            (entry_id,))
        conn.commit()

    def delete_clipboard_entry(self, entry_id):
        conn = self._get_conn()
        row = conn.execute(
            "SELECT file_path, thumbnail_path FROM clipboard_entries WHERE id=?",
            (entry_id,)).fetchone()
        if row:
            for p in (row['file_path'], row['thumbnail_path']):
                if p and os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
        conn.execute("DELETE FROM clipboard_entries WHERE id=?", (entry_id,))
        conn.commit()

    def clear_clipboard(self):
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT file_path, thumbnail_path FROM clipboard_entries WHERE pinned=0"
        ).fetchall()
        for row in rows:
            for p in (row['file_path'], row['thumbnail_path']):
                if p and os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
        conn.execute("DELETE FROM clipboard_entries WHERE pinned=0")
        conn.commit()

    def cleanup_clipboard(self, retention_days):
        cutoff = time.time() - (retention_days * 86400)
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT file_path, thumbnail_path FROM clipboard_entries "
            "WHERE timestamp < ? AND pinned=0", (cutoff,)).fetchall()
        for row in rows:
            for p in (row['file_path'], row['thumbnail_path']):
                if p and os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
        conn.execute(
            "DELETE FROM clipboard_entries WHERE timestamp < ? AND pinned=0",
            (cutoff,))
        conn.commit()

    def get_clipboard_stats(self):
        conn = self._get_conn()
        total = conn.execute(
            "SELECT COUNT(*) c FROM clipboard_entries").fetchone()['c']
        texts = conn.execute(
            "SELECT COUNT(*) c FROM clipboard_entries WHERE content_type='text'"
        ).fetchone()['c']
        images = conn.execute(
            "SELECT COUNT(*) c FROM clipboard_entries WHERE content_type='image'"
        ).fetchone()['c']
        files = conn.execute(
            "SELECT COUNT(*) c FROM clipboard_entries WHERE content_type='files'"
        ).fetchone()['c']
        return {'total': total, 'texts': texts, 'images': images, 'files': files}

    # ── Devices CRUD ───────────────────────────────────────────

    def upsert_device(self, device_id, name, ip_address=None, port=None,
                      sync_enabled=1, clipboard_sync=0):
        conn = self._get_conn()
        existing = conn.execute(
            "SELECT id FROM devices WHERE id=?", (device_id,)).fetchone()
        now = time.time()
        if existing:
            conn.execute(
                """UPDATE devices SET name=?, ip_address=?, port=?,
                   last_seen=?, sync_enabled=?, clipboard_sync=?
                   WHERE id=?""",
                (name, ip_address, port, now, sync_enabled,
                 clipboard_sync, device_id))
        else:
            conn.execute(
                """INSERT INTO devices
                   (id, name, ip_address, port, last_seen,
                    sync_enabled, clipboard_sync, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (device_id, name, ip_address, port, now,
                 sync_enabled, clipboard_sync, now))
        conn.commit()

    def get_devices(self):
        conn = self._get_conn()
        return [dict(r) for r in
                conn.execute("SELECT * FROM devices ORDER BY name").fetchall()]

    def remove_device(self, device_id):
        conn = self._get_conn()
        conn.execute("DELETE FROM devices WHERE id=?", (device_id,))
        conn.commit()

    def update_device(self, device_id, **kwargs):
        conn = self._get_conn()
        sets, params = [], []
        for k, v in kwargs.items():
            if k in ('name', 'ip_address', 'port', 'sync_enabled',
                     'clipboard_sync', 'last_seen'):
                sets.append(f"{k}=?"); params.append(v)
        if sets:
            params.append(device_id)
            conn.execute(
                f"UPDATE devices SET {','.join(sets)} WHERE id=?", params)
            conn.commit()

    # ── Close ──────────────────────────────────────────────────

    def close(self):
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
