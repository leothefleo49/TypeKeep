/* ══════════════════════════════════════════════════════════════
   TypeKeep Mobile — App Logic v3.0
   Cross-device clipboard sync & history viewer
   ══════════════════════════════════════════════════════════════ */

const REFRESH_MS = 15000;
const STORAGE_KEY = 'typekeep_mobile';

/* ── State ─────────────────────────────────────────────────── */
const S = {
  connected: false,
  config: { url: '', key: '', syncKey: '', deviceName: '', deviceId: '' },
  clipboard: [],
  messages: [],
  devices: [],
  activeTab: 'clipboard',
};

let _refreshTimer = null;
let _toastTimer = null;

/* ── Boot ──────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  loadConfig();
  if (S.connected) {
    showMainScreen();
    refreshData();
    startRefresh();
  }
  registerSW();
});

/* ── Service Worker ────────────────────────────────────────── */
function registerSW() {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js').catch(() => {});
  }
}

/* ── Config Persistence ────────────────────────────────────── */
function loadConfig() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      const c = JSON.parse(saved);
      S.config = c;
      S.connected = !!(c.url && c.key && c.syncKey);
    }
  } catch (e) {}
}

function saveConfig() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(S.config));
}

/* ── Supabase API ──────────────────────────────────────────── */
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
    if (!r.ok) throw new Error(`API ${r.status}`);
    return r.text().then(t => t ? JSON.parse(t) : null);
  });
}

/* ── Screens ───────────────────────────────────────────────── */
function showSetupScreen() {
  document.getElementById('setup-screen').classList.add('active');
  document.getElementById('main-screen').classList.remove('active');
}

function showMainScreen() {
  document.getElementById('setup-screen').classList.remove('active');
  document.getElementById('main-screen').classList.add('active');
  document.getElementById('self-device-name').textContent =
    S.config.deviceName || 'This Device';
}

/* ── Connect ───────────────────────────────────────────────── */
async function connectCloud() {
  const url = document.getElementById('setup-url').value.trim().replace(/\/$/, '');
  const key = document.getElementById('setup-key').value.trim();
  const syncKey = document.getElementById('setup-sync-key').value.trim();
  const name = document.getElementById('setup-device-name').value.trim() || 'Mobile';
  const errEl = document.getElementById('setup-error');
  errEl.style.display = 'none';

  if (!url || !key || !syncKey) {
    errEl.textContent = 'All fields are required.';
    errEl.style.display = 'block';
    return;
  }

  try {
    // Test connection
    const testUrl = `${url}/rest/v1/sync_groups?sync_key=eq.${syncKey}&limit=1`;
    const r = await fetch(testUrl, {
      headers: { 'apikey': key, 'Authorization': `Bearer ${key}` },
    });
    if (!r.ok) throw new Error(`Connection failed (${r.status})`);

    // Generate device ID
    const deviceId = 'mobile-' + Math.random().toString(36).substr(2, 8);

    S.config = { url, key, syncKey, deviceName: name, deviceId };
    S.connected = true;
    saveConfig();

    // Register device
    await registerDevice();

    showMainScreen();
    refreshData();
    startRefresh();
    toast('Connected successfully!');
  } catch (e) {
    errEl.textContent = `Connection failed: ${e.message}`;
    errEl.style.display = 'block';
  }
}

async function registerDevice() {
  try {
    // Create sync group if needed
    await supaFetch('sync_groups', { on_conflict: 'sync_key' }, 'POST', {
      sync_key: S.config.syncKey,
    }).catch(() => {});

    // Register device
    await supaFetch('sync_devices', { on_conflict: 'id' }, 'POST', {
      id: S.config.deviceId,
      sync_key: S.config.syncKey,
      device_name: S.config.deviceName,
      device_type: detectDeviceType(),
      last_seen: new Date().toISOString(),
    });
  } catch (e) {
    console.warn('Device registration:', e);
  }
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
    ]);
    // Update heartbeat
    supaFetch('sync_devices', { id: `eq.${S.config.deviceId}` }, 'PATCH', {
      last_seen: new Date().toISOString(),
    }).catch(() => {});
  } catch (e) {
    console.error('Refresh error:', e);
  }
}

function startRefresh() {
  if (_refreshTimer) clearInterval(_refreshTimer);
  _refreshTimer = setInterval(refreshData, REFRESH_MS);
}

/* ── Load Clipboard ────────────────────────────────────────── */
async function loadClipboard() {
  try {
    const entries = await supaFetch('sync_clipboard', {
      sync_key: `eq.${S.config.syncKey}`,
      order: 'timestamp.desc',
      limit: '100',
    });
    S.clipboard = entries || [];
    renderClipboard();
  } catch (e) {
    console.error('loadClipboard:', e);
  }
}

function renderClipboard() {
  const list = document.getElementById('clipboard-list');
  const empty = document.getElementById('clipboard-empty');
  const count = document.getElementById('clip-count');

  count.textContent = S.clipboard.length;

  if (!S.clipboard.length) {
    list.innerHTML = '';
    empty.style.display = 'flex';
    return;
  }
  empty.style.display = 'none';

  list.innerHTML = S.clipboard.map((e, i) => {
    const time = fmtTime(e.timestamp);
    const source = e.device_name || 'Unknown';
    const isMe = e.device_id === S.config.deviceId;
    const text = e.content_text || '[No text]';
    const preview = text.length > 200 ? text.substring(0, 200) + '...' : text;

    return `<div class="card" onclick="toggleExpand(this)">
      <div class="card-head">
        <div class="card-source">
          <span class="app-icon">${isMe ? '📱' : '💻'}</span>
          <span>${esc(source)}${e.source_app ? ' · ' + esc(e.source_app) : ''}</span>
        </div>
        <span class="card-time">${time}</span>
      </div>
      <div class="card-text">${esc(preview)}</div>
      <div class="card-actions">
        <button class="card-action-btn" onclick="event.stopPropagation(); copyText(${i}, 'clipboard')">
          📋 Copy
        </button>
      </div>
    </div>`;
  }).join('');
}

/* ── Load Messages ─────────────────────────────────────────── */
async function loadMessages() {
  try {
    const msgs = await supaFetch('sync_messages', {
      sync_key: `eq.${S.config.syncKey}`,
      order: 'synced_at.desc',
      limit: '100',
    });
    S.messages = msgs || [];
    renderMessages();
  } catch (e) {
    console.error('loadMessages:', e);
  }
}

function renderMessages() {
  const list = document.getElementById('history-list');
  const empty = document.getElementById('history-empty');
  const count = document.getElementById('msg-count');

  count.textContent = S.messages.length;

  if (!S.messages.length) {
    list.innerHTML = '';
    empty.style.display = 'flex';
    return;
  }
  empty.style.display = 'none';

  list.innerHTML = S.messages.map((m, i) => {
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
      <div class="card-text">${esc(preview)}</div>
      <div class="msg-meta">
        <span>${m.keystroke_count || 0} keys</span>
        ${m.window ? `<span>${esc(m.window.substring(0, 40))}</span>` : ''}
      </div>
      <div class="card-actions">
        <button class="card-action-btn" onclick="event.stopPropagation(); copyText(${i}, 'messages')">
          📋 Copy
        </button>
      </div>
    </div>`;
  }).join('');
}

/* ── Load Devices ──────────────────────────────────────────── */
async function loadDevices() {
  try {
    const devs = await supaFetch('sync_devices', {
      sync_key: `eq.${S.config.syncKey}`,
      order: 'last_seen.desc',
    });
    S.devices = devs || [];
    renderDevices();
    renderDeviceBar();
  } catch (e) {
    console.error('loadDevices:', e);
  }
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

/* ── Add Clipboard ─────────────────────────────────────────── */
async function addClipboardEntry() {
  const text = document.getElementById('add-text').value.trim();
  if (!text) {
    toast('Please enter some text');
    return;
  }

  try {
    await supaFetch('sync_clipboard', {}, 'POST', {
      sync_key: S.config.syncKey,
      device_id: S.config.deviceId,
      device_name: S.config.deviceName,
      content_type: 'text',
      content_text: text,
      source_app: 'TypeKeep Mobile',
      timestamp: new Date().toISOString(),
    });
    document.getElementById('add-text').value = '';
    toast('Sent to all devices!');
    await loadClipboard();
    switchTab('clipboard');
  } catch (e) {
    toast('Failed to send: ' + e.message);
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
  let text = '';
  if (source === 'clipboard') {
    text = S.clipboard[idx]?.content_text || '';
  } else {
    text = S.messages[idx]?.final_text || '';
  }
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
  document.getElementById('s-url').value = S.config.url;
  document.getElementById('s-key').value = S.config.key;
  document.getElementById('s-sync-key').value = S.config.syncKey;
  document.getElementById('s-device-name').value = S.config.deviceName;
  document.getElementById('settings-overlay').style.display = 'flex';
}

function closeSettings() {
  document.getElementById('settings-overlay').style.display = 'none';
}

function saveSettings() {
  S.config.url = document.getElementById('s-url').value.trim().replace(/\/$/, '');
  S.config.key = document.getElementById('s-key').value.trim();
  S.config.syncKey = document.getElementById('s-sync-key').value.trim();
  S.config.deviceName = document.getElementById('s-device-name').value.trim();
  S.connected = !!(S.config.url && S.config.key && S.config.syncKey);
  saveConfig();
  closeSettings();
  registerDevice();
  refreshData();
  toast('Settings saved');
}

function disconnect() {
  localStorage.removeItem(STORAGE_KEY);
  S.connected = false;
  S.config = { url: '', key: '', syncKey: '', deviceName: '', deviceId: '' };
  if (_refreshTimer) clearInterval(_refreshTimer);
  showSetupScreen();
  toast('Disconnected');
}

/* ── Expand/Collapse ───────────────────────────────────────── */
function toggleExpand(card) {
  const text = card.querySelector('.card-text');
  if (text) text.classList.toggle('expanded');
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
  const now = new Date();
  const diff = (now - d) / 1000;
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
