"""TypeKeep Cloud Sync — Supabase-powered cross-device synchronization.

Overhauled v3.4.0:
- Persists push/pull checkpoints in app_meta so restarts never echo duplicates.
- True bidirectional clipboard + message/notes sync (_pull_messages + _pull_clipboard).
- Optional auto_copy_remote_clipboard pushes newly synced remote text straight
  into the Windows OS clipboard.
"""

import json
import threading
import time
import traceback
from urllib.parse import urlencode

try:
    import requests as _rq
except ImportError:
    _rq = None

_SYNC_INTERVAL = 30  # seconds between sync cycles


def _parse_iso_ts(val) -> float:
    if not val:
        return 0.0
    try:
        return float(val)
    except (TypeError, ValueError):
        pass
    try:
        import datetime as _dt
        s = str(val).replace('Z', '+00:00')
        return _dt.datetime.fromisoformat(s).timestamp()
    except Exception:
        return time.time()


class CloudSync:
    """Handles bidirectional sync with Supabase."""

    def __init__(self, database, config, clipboard_monitor=None):
        self.db = database
        self.config = config
        self.clipboard_monitor = clipboard_monitor
        self._running = False
        self._stop_evt = threading.Event()
        self._thread = None
        self._last_push_ts = self._load_ts('cloud_last_push_ts')
        self._last_pull_ts = self._load_ts('cloud_last_pull_ts')
        self._last_message_push_ts = self._load_ts('cloud_last_msg_push_ts')
        self._last_message_pull_ts = self._load_ts('cloud_last_msg_pull_ts')

    def _load_ts(self, key: str) -> float:
        try:
            v = self.db.get_meta(key)
            return float(v) if v else 0.0
        except Exception:
            return 0.0

    def _save_ts(self, key: str, val: float) -> None:
        try:
            self.db.set_meta(key, f"{val:.3f}")
        except Exception:
            pass

    # ── Configuration ──────────────────────────────────────────

    @property
    def enabled(self):
        return (self.config.get('cloud_sync_enabled', False)
                and bool(self.supabase_url)
                and bool(self.supabase_key)
                and bool(self.sync_key))

    @property
    def supabase_url(self):
        return (self.config.get('supabase_url', '') or '').rstrip('/')

    @property
    def supabase_key(self):
        return self.config.get('supabase_anon_key', '') or ''

    @property
    def sync_key(self):
        return self.config.get('cloud_sync_key', '') or ''

    @property
    def device_id(self):
        return self.config.get('device_id', '') or ''

    @property
    def device_name(self):
        return self.config.get('device_name', '') or ''

    def _headers(self, upsert=False):
        h = {
            'apikey': self.supabase_key,
            'Authorization': f'Bearer {self.supabase_key}',
            'Content-Type': 'application/json',
        }
        if upsert:
            h['Prefer'] = 'resolution=merge-duplicates,return=representation'
        else:
            h['Prefer'] = 'return=representation'
        return h

    def _api(self, method, table, params=None, data=None, upsert=False):
        """Make a Supabase REST API call."""
        if not _rq:
            raise RuntimeError('requests library not available')
        url = f'{self.supabase_url}/rest/v1/{table}'
        if params:
            url += '?' + urlencode(params)
        r = _rq.request(method, url, headers=self._headers(upsert=upsert),
                        json=data, timeout=15)
        if r.status_code >= 400:
            raise RuntimeError(f'Supabase API error {r.status_code}: {r.text[:200]}')
        if r.text:
            return r.json()
        return None

    # ── Lifecycle ──────────────────────────────────────────────

    def start(self):
        if not self.enabled:
            return
        if self._thread and self._thread.is_alive():
            self._running = True
            return
        self._stop_evt.clear()
        self._running = True
        self._register_device()
        self._thread = threading.Thread(
            target=self._sync_loop, daemon=True, name='cloud-sync')
        self._thread.start()
        print(f'[TypeKeep] Cloud sync started (key={self.sync_key[:4]}...)')

    def stop(self):
        self._running = False
        self._stop_evt.set()

    def restart(self):
        self.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self.start()

    # ── Device registration ────────────────────────────────────

    def _register_device(self):
        try:
            self._api('POST', 'sync_groups', data={
                'sync_key': self.sync_key,
            }, params={'on_conflict': 'sync_key'}, upsert=True)
        except Exception:
            pass

        try:
            self._api('POST', 'sync_devices',
                      params={'on_conflict': 'id'},
                      upsert=True,
                      data={
                          'id': self.device_id,
                          'sync_key': self.sync_key,
                          'device_name': self.device_name,
                          'device_type': 'desktop',
                          'last_seen': time.strftime('%Y-%m-%dT%H:%M:%SZ',
                                                     time.gmtime()),
                      })
        except Exception as e:
            print(f'[TypeKeep] Cloud sync device registration error: {e}')

    # ── Main sync loop ─────────────────────────────────────────

    def _sync_loop(self):
        while self._running and not self._stop_evt.is_set():
            if not self.enabled:
                self._stop_evt.wait(5)
                continue
            try:
                self._push_clipboard()
                self._pull_clipboard()
                self._push_messages()
                self._pull_messages()
                self._update_heartbeat()
            except Exception as e:
                print(f'[TypeKeep] Cloud sync error: {e}')
                traceback.print_exc()
            interval = max(10, int(self.config.get(
                'cloud_sync_interval_seconds', _SYNC_INTERVAL) or _SYNC_INTERVAL))
            self._stop_evt.wait(interval)

    # ── Push clipboard to cloud ────────────────────────────────

    def _push_clipboard(self):
        if not self.config.get('cloud_sync_clipboard', True):
            return
        since = self._last_push_ts or (time.time() - 300)
        entries, _ = self.db.get_clipboard(start_time=since, limit=50)
        if not entries:
            return
        batch = []
        max_ts = self._last_push_ts
        for e in entries:
            if e.get('device_id') and e['device_id'] != self.device_id:
                continue
            ts_val = float(e.get('timestamp') or 0)
            if ts_val <= self._last_push_ts:
                continue
            if ts_val > max_ts:
                max_ts = ts_val
            batch.append({
                'sync_key': self.sync_key,
                'device_id': self.device_id,
                'device_name': self.device_name,
                'content_type': e['content_type'],
                'content_text': (e.get('content_text') or '')[:10000],
                'source_app': e.get('source_app', ''),
                'timestamp': time.strftime(
                    '%Y-%m-%dT%H:%M:%SZ',
                    time.gmtime(ts_val)),
                'extra': json.dumps({'local_id': e['id']}),
            })
        if batch:
            try:
                self._api('POST', 'sync_clipboard', data=batch)
                self._last_push_ts = max(max_ts, time.time())
                self._save_ts('cloud_last_push_ts', self._last_push_ts)
            except Exception as e:
                print(f'[TypeKeep] Cloud push clipboard error: {e}')
        else:
            self._last_push_ts = time.time()
            self._save_ts('cloud_last_push_ts', self._last_push_ts)

    # ── Pull clipboard from cloud ──────────────────────────────

    def _pull_clipboard(self):
        if not self.config.get('cloud_sync_clipboard', True):
            return
        since = self._last_pull_ts or (time.time() - 3600)
        since_str = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(since))
        try:
            entries = self._api('GET', 'sync_clipboard', params={
                'sync_key': f'eq.{self.sync_key}',
                'device_id': f'neq.{self.device_id}',
                'timestamp': f'gt.{since_str}',
                'order': 'timestamp.desc',
                'limit': '50',
            })
        except Exception as e:
            print(f'[TypeKeep] Cloud pull clipboard error: {e}')
            return
        now = time.time()
        if not entries:
            self._last_pull_ts = now
            self._save_ts('cloud_last_pull_ts', now)
            return

        newest_remote_text = None
        for e in entries:
            if self.db.clipboard_entry_exists(
                    e['content_type'],
                    e.get('content_text'),
                    device_id=e.get('device_id'),
                    source_app=e.get('source_app'),
                    since_seconds=86400):
                continue
            self.db.add_clipboard_entry(
                content_type=e['content_type'],
                content_text=e.get('content_text'),
                source_app=e.get('source_app'),
                source_title=f"[{e.get('device_name', 'Remote')}]",
                device_id=e.get('device_id'),
            )
            if newest_remote_text is None and e.get('content_type') == 'text' and e.get('content_text'):
                newest_remote_text = e.get('content_text')

        if newest_remote_text and self.clipboard_monitor and self.config.get('auto_copy_remote_clipboard', False):
            self.clipboard_monitor.set_text(newest_remote_text)

        self._last_pull_ts = now
        self._save_ts('cloud_last_pull_ts', now)

    # ── Push message summaries ─────────────────────────────────

    def _push_messages(self):
        """Push recent local message summaries to cloud for mobile viewing."""
        if not self.config.get('cloud_sync_messages', True):
            return
        if self.db.buffer_size() > 0:
            self.db.flush_buffer()
        now = time.time()
        since = self._last_message_push_ts or (now - 300)
        messages, _ = self.db.get_messages(
            start_time=since,
            limit=25,
            sort='newest')
        if not messages:
            self._last_message_push_ts = now
            self._save_ts('cloud_last_msg_push_ts', now)
            return
        batch = []
        for m in messages:
            if m.get('remote'):
                continue
            batch.append({
                'sync_key': self.sync_key,
                'device_id': self.device_id,
                'device_name': self.device_name,
                'final_text': (m['final_text'] or '')[:5000],
                'app': m.get('app', ''),
                'win_title': (m.get('window') or '')[:200],
                'start_time': m['start_time'],
                'end_time': m['end_time'],
                'keystroke_count': m.get('keystroke_count', 0),
                'synced_at': time.strftime(
                    '%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            })
        if batch:
            try:
                self._api('POST', 'sync_messages', data=batch)
            except Exception as e:
                print(f'[TypeKeep] Cloud push messages error: {e}')
        self._last_message_push_ts = now
        self._save_ts('cloud_last_msg_push_ts', now)

    # ── Pull remote messages / notes ───────────────────────────

    def _pull_messages(self):
        """Pull notes and typing summaries composed on mobile/other PCs."""
        if not self.config.get('cloud_sync_messages', True):
            return
        since = self._last_message_pull_ts or (time.time() - 86400)
        since_str = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(since))
        try:
            msgs = self._api('GET', 'sync_messages', params={
                'sync_key': f'eq.{self.sync_key}',
                'device_id': f'neq.{self.device_id}',
                'synced_at': f'gt.{since_str}',
                'order': 'synced_at.desc',
                'limit': '30',
            })
        except Exception as e:
            print(f'[TypeKeep] Cloud pull messages error: {e}')
            return
        now = time.time()
        if not msgs:
            self._last_message_pull_ts = now
            self._save_ts('cloud_last_msg_pull_ts', now)
            return

        for m in msgs:
            txt = (m.get('final_text') or '').strip()
            if not txt:
                continue
            st = float(m.get('start_time') or _parse_iso_ts(m.get('synced_at')) or now)
            et = float(m.get('end_time') or st)
            did = m.get('device_id') or ''
            if self.db.remote_message_exists(txt, device_id=did, start_time=st):
                continue
            self.db.add_remote_message(
                final_text=txt,
                device_id=did,
                device_name=m.get('device_name') or 'Remote',
                app=m.get('app') or 'TypeKeep Mobile',
                win_title=m.get('win_title') or '',
                start_time=st,
                end_time=et,
                keystroke_count=m.get('keystroke_count') or len(txt),
            )
        self._last_message_pull_ts = now
        self._save_ts('cloud_last_msg_pull_ts', now)

    # ── Heartbeat ──────────────────────────────────────────────

    def _update_heartbeat(self):
        try:
            self._api('PATCH', 'sync_devices',
                      params={'id': f'eq.{self.device_id}'},
                      data={
                          'last_seen': time.strftime(
                              '%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                      })
        except Exception:
            pass

    # ── Manual operations (called from API) ────────────────────

    def get_cloud_devices(self):
        """Get all devices in the sync group."""
        if not self.enabled:
            return []
        try:
            return self._api('GET', 'sync_devices', params={
                'sync_key': f'eq.{self.sync_key}',
                'order': 'last_seen.desc',
            }) or []
        except Exception:
            return []

    def get_cloud_clipboard(self, limit=50):
        """Get recent clipboard entries from cloud."""
        if not self.enabled:
            return []
        try:
            return self._api('GET', 'sync_clipboard', params={
                'sync_key': f'eq.{self.sync_key}',
                'order': 'timestamp.desc',
                'limit': str(limit),
            }) or []
        except Exception:
            return []

    def get_cloud_messages(self, limit=50):
        """Get recent messages from cloud."""
        if not self.enabled:
            return []
        try:
            return self._api('GET', 'sync_messages', params={
                'sync_key': f'eq.{self.sync_key}',
                'order': 'synced_at.desc',
                'limit': str(limit),
            }) or []
        except Exception:
            return []

    def push_clipboard_entry(self, content_type, content_text,
                              source_app='Mobile'):
        """Push a single clipboard entry to cloud (from mobile/API)."""
        if not self.enabled:
            return False
        if not self.config.get('cloud_sync_clipboard', True):
            return False
        try:
            self._api('POST', 'sync_clipboard', data={
                'sync_key': self.sync_key,
                'device_id': self.device_id,
                'device_name': self.device_name,
                'content_type': content_type,
                'content_text': content_text[:10000],
                'source_app': source_app,
                'timestamp': time.strftime(
                    '%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            })
            return True
        except Exception:
            return False

    def push_quick_note(self, final_text, source_app='Quick Note', win_title='TypeKeep'):
        """Push a single quick note to cloud sync_messages."""
        if not self.enabled or not self.config.get('cloud_sync_messages', True):
            return False
        now = time.time()
        try:
            self._api('POST', 'sync_messages', data={
                'sync_key': self.sync_key,
                'device_id': self.device_id,
                'device_name': self.device_name,
                'final_text': (final_text or '')[:5000],
                'app': source_app,
                'win_title': win_title[:200],
                'start_time': now,
                'end_time': now,
                'keystroke_count': len(final_text or ''),
                'synced_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            })
            return True
        except Exception:
            return False

    def test_connection(self):
        """Test Supabase connectivity."""
        if not self.sync_key:
            return {'status': 'error', 'connected': False,
                    'error': 'Enter a sync key first.'}
        if not self.supabase_url or not self.supabase_key:
            return {'status': 'error', 'connected': False,
                    'error': 'Supabase URL and anon key are required.'}
        try:
            self._api('GET', 'sync_groups', params={
                'sync_key': f'eq.{self.sync_key}',
                'limit': '1',
            })
            return {'status': 'ok', 'connected': True}
        except Exception as e:
            return {'status': 'error', 'connected': False,
                    'error': str(e)}
