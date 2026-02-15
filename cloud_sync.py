"""TypeKeep Cloud Sync — Supabase-powered cross-device synchronization.

Free tier: 500MB storage, 2GB bandwidth, unlimited API requests.
Users create their own Supabase project and enter URL + anon key.
"""

import json
import threading
import time
import traceback

try:
    import requests as _rq
except ImportError:
    _rq = None

_SYNC_INTERVAL = 30  # seconds between sync cycles


class CloudSync:
    """Handles bidirectional sync with Supabase."""

    def __init__(self, database, config):
        self.db = database
        self.config = config
        self._running = False
        self._thread = None
        self._last_push_ts = 0
        self._last_pull_ts = 0

    # ── Configuration ──────────────────────────────────────────

    @property
    def enabled(self):
        return (self.config.get('cloud_sync_enabled', False)
                and bool(self.supabase_url)
                and bool(self.supabase_key))

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
            url += '?' + '&'.join(f'{k}={v}' for k, v in params.items())
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
        self._running = True
        self._register_device()
        self._thread = threading.Thread(
            target=self._sync_loop, daemon=True, name='cloud-sync')
        self._thread.start()
        print(f'[TypeKeep] Cloud sync started (key={self.sync_key[:4]}...)')

    def stop(self):
        self._running = False

    def restart(self):
        self.stop()
        time.sleep(1)
        self.start()

    # ── Device registration ────────────────────────────────────

    def _register_device(self):
        try:
            # Upsert sync group
            self._api('POST', 'sync_groups', data={
                'sync_key': self.sync_key,
            }, params={'on_conflict': 'sync_key'}, upsert=True)
        except Exception:
            pass  # Group may already exist

        try:
            # Upsert this device
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
        while self._running:
            if not self.enabled:
                time.sleep(5)
                continue
            try:
                self._push_clipboard()
                self._pull_clipboard()
                self._push_messages()
                self._update_heartbeat()
            except Exception as e:
                print(f'[TypeKeep] Cloud sync error: {e}')
                traceback.print_exc()
            time.sleep(_SYNC_INTERVAL)

    # ── Push clipboard to cloud ────────────────────────────────

    def _push_clipboard(self):
        entries, _ = self.db.get_clipboard(
            start_time=self._last_push_ts or (time.time() - 300),
            limit=50)
        if not entries:
            return
        batch = []
        for e in entries:
            # Skip entries that came from cloud (avoid echo)
            if e.get('device_id') and e['device_id'] != self.device_id:
                continue
            batch.append({
                'sync_key': self.sync_key,
                'device_id': self.device_id,
                'device_name': self.device_name,
                'content_type': e['content_type'],
                'content_text': (e.get('content_text') or '')[:10000],
                'source_app': e.get('source_app', ''),
                'timestamp': time.strftime(
                    '%Y-%m-%dT%H:%M:%SZ',
                    time.gmtime(e['timestamp'])),
                'extra': json.dumps({'local_id': e['id']}),
            })
        if batch:
            try:
                self._api('POST', 'sync_clipboard', data=batch)
            except Exception as e:
                print(f'[TypeKeep] Cloud push clipboard error: {e}')
        self._last_push_ts = time.time()

    # ── Pull clipboard from cloud ──────────────────────────────

    def _pull_clipboard(self):
        since = self._last_pull_ts or (time.time() - 300)
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
        if not entries:
            self._last_pull_ts = time.time()
            return
        for e in entries:
            self.db.add_clipboard_entry(
                content_type=e['content_type'],
                content_text=e.get('content_text'),
                source_app=e.get('source_app'),
                source_title=f"[{e.get('device_name', 'Remote')}]",
                device_id=e.get('device_id'),
            )
        self._last_pull_ts = time.time()

    # ── Push message summaries ─────────────────────────────────

    def _push_messages(self):
        """Push recent message summaries to cloud for mobile viewing."""
        self.db.flush_buffer()
        now = time.time()
        messages, _ = self.db.get_messages(
            start_time=now - 300, limit=20, sort='newest')
        if not messages:
            return
        batch = []
        for m in messages:
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

    def test_connection(self):
        """Test Supabase connectivity."""
        try:
            result = self._api('GET', 'sync_groups', params={
                'sync_key': f'eq.{self.sync_key}',
                'limit': '1',
            })
            return {'status': 'ok', 'connected': True}
        except Exception as e:
            return {'status': 'error', 'connected': False,
                    'error': str(e)}
