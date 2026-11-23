/* ══════════════════════════════════════════════════════════════
   TypeKeep Mobile & Companion — App Logic v3.4.0
   Hybrid Direct PC LAN + Supabase Cloud Sync
   ══════════════════════════════════════════════════════════════ */

const REFRESH_MS = 10000;
const STORAGE_KEY = 'typekeep_mobile_v3';

const DEFAULT_SUPA_URL = 'https://tnbxhpgrtekshowzfdrg.supabase.co';
const DEFAULT_SUPA_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRuYnhocGdydGVrc2hvd3pmZHJnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzExNzAzMzYsImV4cCI6MjA4Njc0NjMzNn0.2GfWPX6ryh_KHAURH4xlmdT4liqFpE01zPnB6Mlbn7E';

/* ── State ─────────────────────────────────────────────────── */
const S = {
  connected: false,
  config: { url: DEFAULT_SUPA_URL, key: DEFAULT_SUPA_KEY, syncKey: '', lanUrl: '', deviceName: '', deviceId: '' },
  clipboard: [],
  messages: [],
  devices: [],
  macros: [],
  pcStatus: null,
  activeTab: 'clipboard',
};

let _refreshTimer = null;
let _toastTimer = null;

/* ── Boot ──────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  loadConfig();
  checkBootParams();
  if (S.connected) {
    showMainScreen();
    refreshData();
    startRefresh();
  }
  registerSW();
});

function registerSW() {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js').catch(() => {});
  }
}

function checkBootParams() {
  try {
    const qp = new URLSearchParams(window.location.search);
    const paramKey = qp.get('key');
    const paramLan = qp.get('lan');
    const isHostedOnPC = window.location.protocol.startsWith('http') && window.location.pathname.startsWith('/mobile');
    const autoOrigin = isHostedOnPC ? window.location.origin : '';
    const detectedLan = paramLan || autoOrigin;

    if (detectedLan && (!S.connected || paramLan || paramKey)) {
      const banner = document.getElementById('lan-quick-banner');
      const hostEl = document.getElementById('lan-banner-host');
      if (banner && hostEl) {
        banner.style.display = 'block';
        hostEl.textContent = detectedLan;
      }
      if (!S.config.lanUrl) {
        const lanInput = document.getElementById('setup-lan-url');
        if (lanInput) lanInput.value = detectedLan;
      }
    }
    if (paramKey) {
      const keyInput = document.getElementById('setup-sync-key');
      if (keyInput) keyInput.value = paramKey;
    }
    if ((paramKey || paramLan) && !S.connected) {
      S.config = {
        url: DEFAULT_SUPA_URL,
        key: DEFAULT_SUPA_KEY,
        syncKey: paramKey || '',
        lanUrl: (detectedLan || '').replace(/\/$/, ''),
        deviceName: S.config.deviceName || defaultDeviceName(),
        deviceId: S.config.deviceId || genDeviceId(),
      };
      S.connected = true;
      saveConfig();
    }
  } catch (e) {}
}

function genDeviceId() {
  return 'mobile-' + Math.random().toString(36).substring(2, 10);
}

function defaultDeviceName() {
  const ua = navigator.userAgent || '';
  if (/android/i.test(ua)) return 'Android Phone';
  if (/iphone|ipad/i.test(ua)) return 'iPhone';
  return 'Companion Device';
}

/* ── Config Persistence ────────────────────────────────────── */
function loadConfig() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY) || localStorage.getItem('typekeep_mobile');
    if (raw) {
      const c = JSON.parse(raw);
      S.config = {
        url: c.url || DEFAULT_SUPA_URL,
        key: c.key || DEFAULT_SUPA_KEY,
        syncKey: c.syncKey || '',
        lanUrl: (c.lanUrl || '').replace(/\/$/, ''),
        deviceName: c.deviceName || defaultDeviceName(),
        deviceId: c.deviceId || genDeviceId(),
      };
      S.connected = !!(S.config.syncKey || S.config.lanUrl);
    }
  } catch (e) {}
}

function saveConfig() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(S.config));
}

function hasCloud() { return !!(S.config.url && S.config.key && S.config.syncKey); }
function hasLan() { return !!S.config.lanUrl; }

/* ── HTTP Helpers ──────────────────────────────────────────── */
function supaFetch(table, params = {}, method = 'GET', body = null) {
  const url = new URL(`${S.config.url}/rest/v1/${table}`);
  Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
  const opts = {
    method,
    headers: {
      'apikey': S.config.key,
      'Authorization': `Bearer ${S.config.key}`,
      'Content-Type': 'application/json',
      'Prefer': method === 'POST' ? 'return=representation' : '',
    },
  };
  if (body) opts.body = JSON.stringify(body);
  return fetch(url, opts).then(r => {
    if (!r.ok) throw new Error(`Cloud API ${r.status}`);
    return r.text().then(t => t ? JSON.parse(t) : null);
  });
}

async function lanFetch(path, method = 'GET', body = null) {
  const base = S.config.lanUrl.replace(/\/$/, '');
  const headers = { 'Content-Type': 'application/json' };
  if (S.config.syncKey) headers['X-TypeKeep-Key'] = S.config.syncKey;
  const opts = { method, headers };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(`${base}${path}`, opts);
  if (!r.ok) throw new Error(`LAN API ${r.status}`);
  return r.json();
}

/* ── Screens ───────────────────────────────────────────────── */
function showSetupScreen() {
  document.getElementById('setup-screen').classList.add('active');
  document.getElementById('main-screen').classList.remove('active');
}

function showMainScreen() {
  document.getElementById('setup-screen').classList.remove('active');
  document.getElementById('main-screen').classList.add('active');
  document.getElementById('self-device-name').textContent = S.config.deviceName || 'This Device';
  const pill = document.getElementById('conn-mode-pill');
  if (pill) {
    if (hasLan() && hasCloud()) pill.textContent = 'LAN + Cloud';
    else if (hasLan()) pill.textContent = 'Direct LAN';
    else pill.textContent = 'Cloud';
  }
}

/* ── Connect ───────────────────────────────────────────────── */
async function connectQuickLan() {
  const detected = document.getElementById('lan-banner-host')?.textContent?.trim();
  if (!detected) return;
  document.getElementById('setup-lan-url').value = detected;
  await connectAccount();
}

async function connectAccount() {
  const syncKey = document.getElementById('setup-sync-key').value.trim();
  const lanUrl = (document.getElementById('setup-lan-url')?.value || '').trim().replace(/\/$/, '');
  const name = document.getElementById('setup-device-name').value.trim() || defaultDeviceName();
  const errEl = document.getElementById('setup-error');
  errEl.style.display = 'none';

  if (!syncKey && !lanUrl) {
    errEl.textContent = 'Enter a Sync Key or a Direct PC LAN URL.';
    errEl.style.display = 'block';
    return;
  }

  try {
    if (lanUrl) {
      const headers = {};
      if (syncKey) headers['X-TypeKeep-Key'] = syncKey;
      const lr = await fetch(`${lanUrl}/api/health`, { headers });
      if (!lr.ok) throw new Error(`PC unreachable (${lr.status})`);
    }
    if (syncKey) {
      const testUrl = `${DEFAULT_SUPA_URL}/rest/v1/sync_groups?sync_key=eq.${encodeURIComponent(syncKey)}&limit=1`;
      const cr = await fetch(testUrl, {
        headers: { 'apikey': DEFAULT_SUPA_KEY, 'Authorization': `Bearer ${DEFAULT_SUPA_KEY}` },
      });
      if (!cr.ok) throw new Error(`Cloud check failed (${cr.status})`);
    }

    S.config = {
      url: DEFAULT_SUPA_URL,
      key: DEFAULT_SUPA_KEY,
      syncKey,
      lanUrl,
      deviceName: name,
      deviceId: S.config.deviceId || genDeviceId(),
    };
    S.connected = true;
    saveConfig();
    if (hasCloud()) await registerDevice();

    showMainScreen();
    await refreshData();
    startRefresh();
    toast('Connected!');
  } catch (e) {
    errEl.textContent = `Connection failed: ${e.message}`;
    errEl.style.display = 'block';
  }
}

async function registerDevice() {
  if (!hasCloud()) return;
  try {
    await supaFetch('sync_groups', { on_conflict: 'sync_key' }, 'POST', {
      sync_key: S.config.syncKey,
    }).catch(() => {});
    await supaFetch('sync_devices', { on_conflict: 'id' }, 'POST', {
      id: S.config.deviceId,
      sync_key: S.config.syncKey,
      device_name: S.config.deviceName,
      device_type: detectDeviceType(),
      last_seen: new Date().toISOString(),
    });
  } catch (e) {}
}

function detectDeviceType() {
  const ua = navigator.userAgent.toLowerCase();
  if (/iphone|ipad|ipod/.test(ua)) return 'ios';
  if (/android/.test(ua)) return 'android';
  return 'mobile';
}

/* ── Refresh ───────────────────────────────────────────────── */
async function refreshData() {
  if (!S.connected) return;
  try {
    await Promise.all([
      loadClipboard(),
      loadMessages(),
      loadDevices(),
      loadPcControls(),
    ]);
    if (hasCloud()) {
      supaFetch('sync_devices', { id: `eq.${S.config.deviceId}` }, 'PATCH', {
        last_seen: new Date().toISOString(),
      }).catch(() => {});
    }
  } catch (e) {
    console.error('Refresh error:', e);
  }
}

function startRefresh() {
  if (_refreshTimer) clearInterval(_refreshTimer);
  _refreshTimer = setInterval(refreshData, REFRESH_MS);
}

/* ── Load Clipboard (LAN first, merge/fallback Cloud) ──────── */
async function loadClipboard() {
  let items = [];
  if (hasLan()) {
    try {
      const d = await lanFetch('/api/clipboard?range=7d&limit=100');
      items = (d.entries || []).map(e => ({
        content_type: e.content_type,
        content_text: e.content_text,
        source_app: e.source_app,
        device_name: e.device_id ? e.device_id : 'Desktop PC',
        device_id: e.device_id || 'pc',
        timestamp: e.timestamp,
      }));
    } catch (e) {}
  }
  if (hasCloud()) {
    try {
      const cloud = await supaFetch('sync_clipboard', {
        sync_key: `eq.${S.config.syncKey}`,
        order: 'timestamp.desc',
        limit: '100',
      });
      if (!items.length) {
        items = cloud || [];
      } else {
        const seen = new Set(items.map(x => `${x.content_type}:${(x.content_text || '').slice(0, 80)}`));
        for (const c of (cloud || [])) {
          const k = `${c.content_type}:${(c.content_text || '').slice(0, 80)}`;
          if (!seen.has(k)) items.push(c);
        }
      }
    } catch (e) {}
  }
  S.clipboard = items;
  renderClipboard();
}

function renderClipboard() {
  const list = document.getElementById('clipboard-list');
  const empty = document.getElementById('clipboard-empty');
  const count = document.getElementById('clip-count');
  const q = (document.getElementById('m-clip-search')?.value || '').trim().toLowerCase();

  const filtered = q
    ? S.clipboard.filter(e =>
        (e.content_text || '').toLowerCase().includes(q)
        || (e.source_app || '').toLowerCase().includes(q))
    : S.clipboard;

  count.textContent = filtered.length;

  if (!filtered.length) {
    list.innerHTML = '';
    empty.style.display = 'flex';
    return;
  }
  empty.style.display = 'none';

  list.innerHTML = filtered.map(e => {
    const idx = S.clipboard.indexOf(e);
    const time = fmtTime(e.timestamp);
    const source = e.device_name || 'Unknown';
    const isMe = e.device_id === S.config.deviceId;
    const text = e.content_text || '[Image / File]';
    const longText = text.length > 200;
    const preview = longText ? text.substring(0, 200) + '...' : text;

    return `<div class="card" onclick="toggleExpand(this)">
      <div class="card-head">
        <div class="card-source">
          <span class="app-icon">${isMe ? '📱' : '💻'}</span>
          <span>${esc(source)}${e.source_app ? ' · ' + esc(e.source_app) : ''}</span>
        </div>
        <span class="card-time">${time}</span>
      </div>
      <div class="card-text" data-preview="${esc(preview)}" data-full="${esc(text)}">${esc(preview)}</div>
      <div class="card-actions">
        <button class="card-action-btn" onclick="event.stopPropagation(); copyText(${idx}, 'clipboard')">
          📋 Copy
        </button>
        ${hasLan() ? `<button class="card-action-btn" onclick="event.stopPropagation(); pushClipToPc(${idx})">💻 Send to PC Clipboard</button>` : ''}
      </div>
    </div>`;
  }).join('');
}

/* ── Load Messages ─────────────────────────────────────────── */
async function loadMessages() {
  let msgs = [];
  if (hasLan()) {
    try {
      const d = await lanFetch('/api/messages?range=7d&limit=80&sort=newest');
      msgs = (d.messages || []).map(m => ({
        final_text: m.final_text,
        app: m.app,
        win_title: m.window || m.win_title || '',
        keystroke_count: m.keystroke_count,
        synced_at: m.end_time || m.start_time,
        device_name: m.remote ? (m.app || 'Remote') : 'Desktop PC',
      }));
    } catch (e) {}
  }
  if (!msgs.length && hasCloud()) {
    try {
      msgs = await supaFetch('sync_messages', {
        sync_key: `eq.${S.config.syncKey}`,
        order: 'synced_at.desc',
        limit: '100',
      }) || [];
    } catch (e) {}
  }
  S.messages = msgs;
  renderMessages();
}

function renderMessages() {
  const list = document.getElementById('history-list');
  const empty = document.getElementById('history-empty');
  const count = document.getElementById('msg-count');
  const q = (document.getElementById('m-msg-search')?.value || '').trim().toLowerCase();

  const filtered = q
    ? S.messages.filter(m =>
        (m.final_text || '').toLowerCase().includes(q)
        || (m.app || '').toLowerCase().includes(q)
        || (m.win_title || '').toLowerCase().includes(q))
    : S.messages;

  count.textContent = filtered.length;

  if (!filtered.length) {
    list.innerHTML = '';
    empty.style.display = 'flex';
    return;
  }
  empty.style.display = 'none';

  list.innerHTML = filtered.map(m => {
    const idx = S.messages.indexOf(m);
    const text = m.final_text || '';
    const preview = text.length > 200 ? text.substring(0, 200) + '...' : text;
    const time = m.synced_at ? fmtTime(m.synced_at) : '';
    const device = m.device_name || 'Desktop';

    return `<div class="card msg-card" onclick="toggleExpand(this)">
      <div class="card-head">
        <div class="card-source">
          <span class="app-icon">💻</span>
          <span>${esc(device)}${m.app ? ' · ' + esc(m.app) : ''}</span>
        </div>
        <span class="card-time">${time}</span>
      </div>
      <div class="card-text" data-preview="${esc(preview)}" data-full="${esc(text)}">${esc(preview)}</div>
      <div class="msg-meta">
        <span>${m.keystroke_count || 0} keys</span>
        ${m.win_title ? `<span>${esc(m.win_title.substring(0, 40))}</span>` : ''}
      </div>
      <div class="card-actions">
        <button class="card-action-btn" onclick="event.stopPropagation(); copyText(${idx}, 'messages')">
          📋 Copy
        </button>
      </div>
    </div>`;
  }).join('');
}

/* ── Load PC Remote Controls & Macros ──────────────────────── */
async function loadPcControls() {
  const box = document.getElementById('pc-control-box');
  if (!box) return;
  if (!hasLan()) {
    box.style.display = 'none';
    return;
  }
  try {
    const [status, stats, mac] = await Promise.all([
      lanFetch('/api/status'),
      lanFetch('/api/stats'),
      lanFetch('/api/macros'),
    ]);
    box.style.display = 'block';
    S.pcStatus = status;
    S.macros = mac.macros || [];
    const badge = document.getElementById('pc-rec-badge');
    if (badge) badge.textContent = status.recording ? 'Recording' : 'Paused';
    const sl = document.getElementById('pc-stats-line');
    if (sl) sl.textContent = `${(stats.total_keystrokes || 0).toLocaleString()} keys · ${(stats.events_24h || 0).toLocaleString()} events (24h)`;
    const hl = document.getElementById('pc-host-line');
    if (hl) hl.textContent = S.config.lanUrl;
    renderMobileMacros();
  } catch (e) {
    box.style.display = 'none';
  }
}

function renderMobileMacros() {
  const c = document.getElementById('mobile-macro-list');
  const cnt = document.getElementById('macro-count');
  if (!c) return;
  if (cnt) cnt.textContent = S.macros.length;
  if (!S.macros.length) {
    c.innerHTML = '<div class="card" style="color:var(--text-dim);font-size:13px">No macros configured on PC.</div>';
    return;
  }
  c.innerHTML = S.macros.map(m => `
    <div class="card" style="display:flex;align-items:center;justify-content:space-between;gap:10px">
      <div>
        <div style="font-weight:600;font-size:14px">${esc(m.name)}</div>
        <div style="font-size:11px;color:var(--text-dim)">${esc(m.shortcut || 'Manual trigger')}</div>
      </div>
      <button class="card-action-btn" style="color:var(--accent);border-color:var(--accent)" onclick="runPcMacro(${m.id}, '${esc(m.name)}')">▶ Run</button>
    </div>
  `).join('');
}

async function runPcMacro(id, name) {
  try {
    await lanFetch(`/api/macros/${id}/run`, 'POST');
    toast(`Running macro: ${name}`);
  } catch (e) {
    toast('Failed to run macro');
  }
}

async function togglePcRecording() {
  try {
    const r = await lanFetch('/api/toggle', 'POST');
    toast(r.recording ? 'PC Recording resumed' : 'PC Recording paused');
    loadPcControls();
  } catch (e) {
    toast('Could not toggle PC recording');
  }
}

/* ── Load Devices ──────────────────────────────────────────── */
async function loadDevices() {
  if (!hasCloud()) {
    S.devices = hasLan() ? [{ id: 'lan-pc', device_name: 'Connected PC', device_type: 'desktop', last_seen: new Date().toISOString() }] : [];
    renderDevices();
    renderDeviceBar();
    return;
  }
  try {
    const devs = await supaFetch('sync_devices', {
      sync_key: `eq.${S.config.syncKey}`,
      order: 'last_seen.desc',
    });
    S.devices = devs || [];
    renderDevices();
    renderDeviceBar();
  } catch (e) {}
}

function renderDevices() {
  const list = document.getElementById('devices-list');
  const empty = document.getElementById('devices-empty');

  if (!S.devices.length) {
    list.innerHTML = '';
    empty.style.display = 'flex';
    return;
  }
  empty.style.display = 'none';

  list.innerHTML = S.devices.map(d => {
    const isMe = d.id === S.config.deviceId;
    const icon = d.device_type === 'desktop' ? '💻' :
                 d.device_type === 'ios' ? '📱' :
                 d.device_type === 'android' ? '📱' : '🖥️';
    const lastSeen = d.last_seen ? fmtTime(d.last_seen) : 'Never';
    const isOnline = d.last_seen &&
      (Date.now() - new Date(d.last_seen).getTime()) < 120000;

    return `<div class="card device-card-full">
      <span class="device-icon-large">${icon}</span>
      <div class="device-details">
        <h3>${esc(d.device_name)}${isMe ? ' (You)' : ''}</h3>
        <p>${d.device_type || 'unknown'} · Last seen: ${lastSeen}</p>
      </div>
      <div class="device-status">
        <span class="device-dot ${isOnline ? 'online' : ''}"></span>
        <span class="${isOnline ? 'online' : 'offline'}">${isOnline ? 'Online' : 'Offline'}</span>
      </div>
    </div>`;
  }).join('');
}

function renderDeviceBar() {
  const bar = document.getElementById('device-bar');
  const chips = S.devices.map(d => {
    const isMe = d.id === S.config.deviceId;
    const isOnline = d.last_seen &&
      (Date.now() - new Date(d.last_seen).getTime()) < 120000;
    return `<div class="device-chip ${isMe ? 'self' : ''}">
      <span class="device-dot ${isOnline ? 'online' : ''}"></span>
      <span>${esc(d.device_name)}${isMe ? ' (You)' : ''}</span>
    </div>`;
  }).join('');
  bar.innerHTML = chips || `<div class="device-chip self">
    <span class="device-dot online"></span>
    <span>${esc(S.config.deviceName || 'This Device')}</span>
  </div>`;
}

/* ── Send Text / Notes ─────────────────────────────────────── */
async function sendToAllDevices(kind = 'clipboard') {
  const text = document.getElementById('add-text').value.trim();
  if (!text) {
    toast('Please enter some text');
    return;
  }

  let ok = false;
  if (hasLan()) {
    try {
      if (kind === 'note') {
        await lanFetch('/api/notes/quick', 'POST', {
          text,
          device_id: S.config.deviceId,
          device_name: S.config.deviceName,
          app: 'Mobile Note',
          copy_to_clipboard: true,
        });
      } else {
        await lanFetch('/api/clipboard/add', 'POST', {
          content_text: text,
          source_app: `${S.config.deviceName || 'Mobile'}`,
          device_id: S.config.deviceId,
          copy_to_os: true,
        });
      }
      ok = true;
    } catch (e) {}
  }

  if (hasCloud()) {
    try {
      if (kind === 'note') {
        await supaFetch('sync_messages', {}, 'POST', {
          sync_key: S.config.syncKey,
          device_id: S.config.deviceId,
          device_name: S.config.deviceName,
          final_text: text.slice(0, 5000),
          app: 'Mobile Note',
          win_title: `Note from ${S.config.deviceName}`,
          start_time: Date.now() / 1000,
          end_time: Date.now() / 1000,
          keystroke_count: text.length,
          synced_at: new Date().toISOString(),
        });
      } else {
        await supaFetch('sync_clipboard', {}, 'POST', {
          sync_key: S.config.syncKey,
          device_id: S.config.deviceId,
          device_name: S.config.deviceName,
          content_type: 'text',
          content_text: text,
          source_app: 'TypeKeep Mobile',
          timestamp: new Date().toISOString(),
        });
      }
      ok = true;
    } catch (e) {}
  }

  if (ok) {
    document.getElementById('add-text').value = '';
    toast(kind === 'note' ? 'Quick note saved & sent!' : 'Sent to PC clipboard!');
    await refreshData();
    switchTab(kind === 'note' ? 'history' : 'clipboard');
  } else {
    toast('Failed to send — check connection');
  }
}

async function pushClipToPc(idx) {
  const e = S.clipboard[idx];
  if (!e || !e.content_text) return;
  try {
    await lanFetch('/api/clipboard/add', 'POST', {
      content_text: e.content_text,
      source_app: e.source_app || 'Mobile',
      device_id: S.config.deviceId,
      copy_to_os: true,
      push_cloud: false,
    });
    toast('Pushed to Windows clipboard!');
  } catch (err) {
    toast('Could not push to PC');
  }
}

async function pasteFromClipboard() {
  try {
    const text = await navigator.clipboard.readText();
    if (text) {
      document.getElementById('add-text').value = text;
      toast('Pasted from clipboard');
    }
  } catch (e) {
    toast('Cannot access clipboard. Try pasting manually.');
  }
}

/* ── Copy ──────────────────────────────────────────────────── */
function copyText(idx, source) {
  const text = source === 'clipboard'
    ? (S.clipboard[idx]?.content_text || '')
    : (S.messages[idx]?.final_text || '');
  if (!text) return;

  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(() => toast('Copied!'));
  } else {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;opacity:0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    toast('Copied!');
  }
}

/* ── Tabs ──────────────────────────────────────────────────── */
function switchTab(tab) {
  S.activeTab = tab;
  document.querySelectorAll('.tab').forEach(t =>
    t.classList.toggle('active', t.dataset.tab === tab));
  document.querySelectorAll('.tab-panel').forEach(p =>
    p.classList.toggle('active', p.id === 'tab-' + tab));
}

/* ── Settings ──────────────────────────────────────────────── */
function openSettings() {
  document.getElementById('s-sync-key').value = S.config.syncKey || '';
  const lanInput = document.getElementById('s-lan-url');
  if (lanInput) lanInput.value = S.config.lanUrl || '';
  document.getElementById('s-device-name').value = S.config.deviceName || '';
  document.getElementById('settings-overlay').style.display = 'flex';
}

function closeSettings() {
  document.getElementById('settings-overlay').style.display = 'none';
}

function saveSettings() {
  S.config.syncKey = document.getElementById('s-sync-key').value.trim();
  const lanInput = document.getElementById('s-lan-url');
  S.config.lanUrl = lanInput ? lanInput.value.trim().replace(/\/$/, '') : '';
  S.config.deviceName = document.getElementById('s-device-name').value.trim() || defaultDeviceName();
  S.config.url = DEFAULT_SUPA_URL;
  S.config.key = DEFAULT_SUPA_KEY;
  S.connected = !!(S.config.syncKey || S.config.lanUrl);
  saveConfig();
  closeSettings();
  showMainScreen();
  registerDevice();
  refreshData();
  toast('Settings saved');
}

function disconnect() {
  localStorage.removeItem(STORAGE_KEY);
  localStorage.removeItem('typekeep_mobile');
  S.connected = false;
  S.config = { url: DEFAULT_SUPA_URL, key: DEFAULT_SUPA_KEY, syncKey: '', lanUrl: '', deviceName: '', deviceId: '' };
  if (_refreshTimer) clearInterval(_refreshTimer);
  showSetupScreen();
  toast('Disconnected');
}

/* ── Expand / Collapse (Fixed full-text expansion!) ───────── */
function toggleExpand(card) {
  const el = card.querySelector('.card-text');
  if (!el) return;
  const expanding = !el.classList.contains('expanded');
  el.classList.toggle('expanded', expanding);
  if (el.dataset.full && el.dataset.preview) {
    el.textContent = expanding ? el.dataset.full : el.dataset.preview;
  }
}

/* ── Helpers ───────────────────────────────────────────────── */
function esc(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function fmtTime(ts) {
  if (!ts) return '';
  const d = typeof ts === 'number' ? new Date(ts * 1000) : new Date(ts);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return 'Just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return d.toLocaleDateString();
}

function toast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => t.classList.remove('show'), 2500);
}
