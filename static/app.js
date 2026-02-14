/* ══════════════════════════════════════════════════════════════
   TypeKeep – frontend SPA logic
   ══════════════════════════════════════════════════════════════ */

const PAGE_SIZE     = 50;
const REFRESH_MS    = 8000;      // auto-refresh interval
const DEBOUNCE_MS   = 350;

// ── State ─────────────────────────────────────────────────────
const S = {
  messages: [],
  total: 0,
  hasMore: false,
  offset: 0,
  loading: false,
  recording: true,
  showRaw: false,
  settings: {},
  apps: [],
  filters: { time: '24h', gap: '5', app: '', sort: 'newest', search: '' },
};

let _refreshTimer = null;
let _toastTimer   = null;

// ── Boot ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  restoreFilters();
  wireEvents();
  await Promise.all([ loadStatus(), loadStats(), loadApps(), loadSettings() ]);
  await loadMessages();
  startRefresh();
});

// ── API helpers ───────────────────────────────────────────────

async function api(path, opts) {
  const r = await fetch(path, opts);
  return r.json();
}

async function loadMessages(append = false) {
  if (S.loading) return;
  S.loading = true;
  showLoading(true);

  try {
    const p = new URLSearchParams({
      gap: S.filters.gap,
      range: S.filters.time,
      sort: S.filters.sort,
      limit: PAGE_SIZE,
      offset: append ? S.offset : 0,
      min_length: 1,
    });
    if (S.filters.app)    p.set('app', S.filters.app);
    if (S.filters.search) p.set('search', S.filters.search);

    const d = await api('/api/messages?' + p);

    S.messages = append ? S.messages.concat(d.messages) : d.messages;
    S.total    = d.total;
    S.hasMore  = d.has_more;
    S.offset   = append ? S.offset + PAGE_SIZE : PAGE_SIZE;

    renderMessages();
  } catch (e) {
    console.error('loadMessages', e);
  } finally {
    S.loading = false;
    showLoading(false);
  }
}

async function loadStats() {
  try {
    const d = await api('/api/stats');
    el('stat-keys').textContent     = fmt(d.total_keystrokes);
    el('stat-messages').textContent = fmt(d.events_24h);
    el('stat-clicks').textContent   = fmt(d.total_mouse_clicks);
    el('stat-dbsize').textContent   = d.db_size_mb + ' MB';
  } catch (_) {}
}

async function loadApps() {
  try {
    S.apps = await api('/api/apps?range=' + S.filters.time);
    const sel = el('f-app');
    const cur = sel.value;
    sel.innerHTML = '<option value="">All Apps</option>';
    S.apps.forEach(a => {
      const o = document.createElement('option');
      o.value = a; o.textContent = a;
      sel.appendChild(o);
    });
    sel.value = cur;
  } catch (_) {}
}

async function loadStatus() {
  try {
    const d = await api('/api/status');
    S.recording = d.recording;
    renderStatus();
  } catch (_) {}
}

async function loadSettings() {
  try { S.settings = await api('/api/settings'); } catch (_) {}
}

// ── Actions ───────────────────────────────────────────────────

async function toggleRecording() {
  try {
    const d = await api('/api/toggle', { method: 'POST' });
    S.recording = d.recording;
    renderStatus();
    toast(S.recording ? 'Recording resumed' : 'Recording paused');
  } catch (_) {}
}

function loadMore() { loadMessages(true); }

function copyMessageText(btn, idx) {
  const msg = S.messages[idx];
  if (!msg) return;
  const text = S.showRaw ? msg.raw_text : msg.text;
  navigator.clipboard.writeText(text).then(() => {
    btn.classList.add('copied');
    btn.innerHTML = svgCheck;
    setTimeout(() => {
      btn.classList.remove('copied');
      btn.innerHTML = svgCopy;
    }, 1800);
    toast('Copied to clipboard');
  });
}

// ── Settings modal ────────────────────────────────────────────

function openSettings() {
  el('s-retention').value = S.settings.retention_days ?? 7;
  el('s-gap').value       = S.settings.default_gap_seconds ?? 5;
  el('s-minlen').value    = S.settings.min_message_length ?? 1;
  el('s-mouse').checked   = S.settings.record_mouse_clicks ?? true;
  el('s-scroll').checked  = S.settings.record_mouse_scroll ?? false;
  el('settings-modal').style.display = '';
}

function closeSettings() {
  el('settings-modal').style.display = 'none';
}

async function saveSettings() {
  const data = {
    retention_days:       +el('s-retention').value,
    default_gap_seconds:  +el('s-gap').value,
    min_message_length:   +el('s-minlen').value,
    record_mouse_clicks:  el('s-mouse').checked,
    record_mouse_scroll:  el('s-scroll').checked,
  };
  try {
    const r = await api('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    S.settings = r.settings || { ...S.settings, ...data };
    toast('Settings saved');
    closeSettings();
  } catch (_) { toast('Failed to save settings'); }
}

// ── Rendering ─────────────────────────────────────────────────

function renderMessages() {
  const c = el('messages');
  const empty = el('empty-state');
  const more  = el('load-more-wrap');

  if (!S.messages.length) {
    c.innerHTML = '';
    empty.style.display = 'flex';
    more.style.display  = 'none';
    return;
  }
  empty.style.display = 'none';
  more.style.display  = S.hasMore ? 'flex' : 'none';

  c.innerHTML = S.messages.map((m, i) => cardHTML(m, i)).join('');
}

function cardHTML(m, i) {
  const text     = S.showRaw ? m.raw_text : m.text;
  const time     = fmtTime(m.start_time);
  const relative = fmtRelative(m.start_time);
  const icon     = appIcon(m.app);
  const dur      = m.duration > 0 ? fmtDuration(m.duration) : '';
  const win      = m.window ? truncate(m.window, 55) : '';

  return `<div class="message-card" style="animation-delay:${Math.min(i * 0.025, 0.6)}s">
  <div class="card-header">
    <div class="card-app-info">
      <span class="app-icon">${icon}</span>
      <span class="app-name">${esc(m.app || 'Unknown')}</span>
      ${win ? `<span class="window-title">${esc(win)}</span>` : ''}
    </div>
    <div class="card-meta">
      <span>${time}</span>
      <span class="card-separator">&middot;</span>
      <span>${relative}</span>
      <span class="card-separator">&middot;</span>
      <span>${m.keystroke_count} keys</span>
      ${dur ? `<span class="card-separator">&middot;</span><span>${dur}</span>` : ''}
      <button class="copy-btn" onclick="copyMessageText(this,${i})" title="Copy">${svgCopy}</button>
    </div>
  </div>
  <div class="card-body"><pre class="card-text">${esc(text)}</pre></div>
</div>`;
}

function renderStatus() {
  const btn = el('status-btn');
  if (S.recording) {
    btn.className = 'status-btn recording';
    btn.querySelector('.status-label').textContent = 'Recording';
  } else {
    btn.className = 'status-btn paused';
    btn.querySelector('.status-label').textContent = 'Paused';
  }
}

// ── Event wiring ──────────────────────────────────────────────

function wireEvents() {
  const reload = () => { S.offset = 0; loadMessages(); };

  el('f-time').addEventListener('change', e => {
    S.filters.time = e.target.value; saveFilters(); loadApps(); reload();
  });
  el('f-gap').addEventListener('change', e => {
    S.filters.gap = e.target.value; saveFilters(); reload();
  });
  el('f-app').addEventListener('change', e => {
    S.filters.app = e.target.value; saveFilters(); reload();
  });
  el('f-sort').addEventListener('change', e => {
    S.filters.sort = e.target.value; saveFilters(); reload();
  });
  el('f-raw').addEventListener('change', e => {
    S.showRaw = e.target.checked; renderMessages();
  });
  el('search-input').addEventListener('input', debounce(e => {
    S.filters.search = e.target.value; saveFilters(); reload();
  }, DEBOUNCE_MS));

  // close modal on backdrop click or Escape
  el('settings-modal').addEventListener('click', e => {
    if (e.target === el('settings-modal')) closeSettings();
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeSettings();
  });

  // Apply saved filter values to selects
  el('f-time').value = S.filters.time;
  el('f-gap').value  = S.filters.gap;
  el('f-sort').value = S.filters.sort;
  el('search-input').value = S.filters.search;
}

// ── Auto-refresh ──────────────────────────────────────────────

function startRefresh() {
  _refreshTimer = setInterval(() => {
    if (document.hidden) return;
    loadMessages();   // silent refresh (replaces list)
    loadStats();
  }, REFRESH_MS);
}

// ── Persistence helpers ───────────────────────────────────────

function saveFilters() {
  try { localStorage.setItem('tk_filters', JSON.stringify(S.filters)); } catch (_) {}
}
function restoreFilters() {
  try {
    const s = localStorage.getItem('tk_filters');
    if (s) Object.assign(S.filters, JSON.parse(s));
  } catch (_) {}
}

// ── UI helpers ────────────────────────────────────────────────

function el(id) { return document.getElementById(id); }

function showLoading(on) {
  el('loading').style.display = on ? 'flex' : 'none';
}

function toast(msg) {
  const t = el('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => t.classList.remove('show'), 2200);
}

// ── Formatters ────────────────────────────────────────────────

function fmt(n) {
  if (n == null) return '—';
  return n.toLocaleString();
}

function fmtTime(ts) {
  if (!ts) return '';
  return new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function fmtRelative(ts) {
  if (!ts) return '';
  const secs = Math.floor(Date.now() / 1000 - ts);
  if (secs < 5)     return 'just now';
  if (secs < 60)    return secs + 's ago';
  if (secs < 3600)  return Math.floor(secs / 60) + 'm ago';
  if (secs < 86400) return Math.floor(secs / 3600) + 'h ago';
  return Math.floor(secs / 86400) + 'd ago';
}

function fmtDuration(secs) {
  if (secs < 1)   return '<1s';
  if (secs < 60)  return Math.round(secs) + 's';
  if (secs < 3600) return Math.floor(secs / 60) + 'm ' + Math.round(secs % 60) + 's';
  return Math.floor(secs / 3600) + 'h ' + Math.floor((secs % 3600) / 60) + 'm';
}

function truncate(s, n) {
  return s.length > n ? s.slice(0, n) + '…' : s;
}

function esc(s) {
  if (!s) return '';
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
          .replace(/"/g,'&quot;');
}

function debounce(fn, ms) {
  let t;
  return function(...args) { clearTimeout(t); t = setTimeout(() => fn.apply(this, args), ms); };
}

// ── App icons ─────────────────────────────────────────────────

const APP_ICONS = {
  'chrome.exe':      '🌐', 'msedge.exe':     '🌐', 'firefox.exe':    '🦊',
  'brave.exe':       '🦁', 'opera.exe':      '🌐', 'vivaldi.exe':    '🌐',
  'Code.exe':        '💻', 'code.exe':       '💻',
  'discord.exe':     '💬', 'Telegram.exe':   '💬', 'slack.exe':      '💬',
  'Teams.exe':       '💬', 'ms-teams.exe':   '💬',
  'explorer.exe':    '📁', 'notepad.exe':    '📝', 'notepad++.exe':  '📝',
  'cmd.exe':         '⚡', 'powershell.exe': '⚡', 'WindowsTerminal.exe': '⚡',
  'WINWORD.EXE':     '📄', 'EXCEL.EXE':     '📊', 'POWERPNT.EXE':  '📊',
  'Spotify.exe':     '🎵', 'vlc.exe':       '🎬',
  'GameBar.exe':     '🎮', 'steam.exe':     '🎮',
};

function appIcon(name) {
  if (!name) return '🖥️';
  return APP_ICONS[name] || '🖥️';
}

// ── SVG constants ─────────────────────────────────────────────

const svgCopy = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none"
  stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
</svg>`;

const svgCheck = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none"
  stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
  <polyline points="20 6 9 17 4 12"/>
</svg>`;
