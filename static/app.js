/* ══════════════════════════════════════════════════════════════
   TypeKeep – frontend SPA logic  v2
   ══════════════════════════════════════════════════════════════ */

const PAGE_SIZE  = 50;
const REFRESH_MS = 6000;
const DEBOUNCE_MS = 300;

/* ── State ─────────────────────────────────────────────────── */
const S = {
  messages: [], total: 0, hasMore: false, offset: 0,
  loading: false, recording: true, settings: {},
  apps: [], macros: [],
  viewMode: 'final',          // final | raw | chrono
  activeTab: 'history',
  activityEvents: [],
  filters: { time: '24h', gap: '5', app: '', sort: 'newest', search: '' },
  actFilters: { time: '24h', type: '' },
  clipFilters: { time: '24h', type: '', pinned: false },
  clipEntries: [], clipTotal: 0, clipHasMore: false, clipOffset: 0,
  syncInfo: {},
  pairedDevices: [],
  _lastMsgHash: '', _forceRender: false,
  _editingMacroId: null,
  _macroActions: [],
  _onboardingStep: 0,
};

let _refreshTimer = null, _toastTimer = null;

/* ── Boot ──────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', async () => {
  restoreFilters();
  initCustomSelects();
  wireEvents();
  await Promise.all([loadStatus(), loadStats(), loadApps(), loadSettings()]);
  await loadMessages();
  startRefresh();
  checkOnboarding();
});

/* ── API helper ────────────────────────────────────────────── */
async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    const j = await r.json().catch(() => ({}));
    throw new Error(j.error || r.statusText);
  }
  return r.json();
}

/* ══════════════════════════════════════════════════════════════
   TABS
   ══════════════════════════════════════════════════════════════ */
function switchTab(tab) {
  S.activeTab = tab;
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === 'tab-' + tab));
  if (tab === 'activity') loadActivity();
  if (tab === 'macros') loadMacros();
  if (tab === 'shortcuts-guide') updateGuide();
  if (tab === 'clipboard') loadClipboard();
  if (tab === 'devices') loadSyncInfo();
}

/* ══════════════════════════════════════════════════════════════
   CUSTOM SELECTS
   ══════════════════════════════════════════════════════════════ */
function initCustomSelects() {
  document.querySelectorAll('.custom-select').forEach(cs => {
    const trigger = cs.querySelector('.cs-trigger');
    trigger.addEventListener('click', e => {
      e.stopPropagation();
      document.querySelectorAll('.custom-select.open').forEach(o => { if (o !== cs) o.classList.remove('open'); });
      cs.classList.toggle('open');
    });
    cs.querySelectorAll('.cs-option').forEach(opt => {
      opt.addEventListener('click', () => {
        cs.querySelectorAll('.cs-option').forEach(o => o.classList.remove('selected'));
        opt.classList.add('selected');
        trigger.textContent = opt.textContent;
        trigger.dataset.value = opt.dataset.value;
        cs.classList.remove('open');
        trigger.dispatchEvent(new Event('change', { bubbles: true }));
      });
    });
  });
  document.addEventListener('click', () => {
    document.querySelectorAll('.custom-select.open').forEach(cs => cs.classList.remove('open'));
  });
}

function getCSValue(id) {
  const cs = el(id);
  return cs ? cs.querySelector('.cs-trigger').dataset.value : '';
}

function setCSValue(id, value) {
  const cs = el(id);
  if (!cs) return;
  const opt = cs.querySelector(`.cs-option[data-value="${value}"]`);
  if (opt) {
    cs.querySelectorAll('.cs-option').forEach(o => o.classList.remove('selected'));
    opt.classList.add('selected');
    cs.querySelector('.cs-trigger').textContent = opt.textContent;
    cs.querySelector('.cs-trigger').dataset.value = value;
  }
}

/* ══════════════════════════════════════════════════════════════
   MESSAGES / TEXT HISTORY
   ══════════════════════════════════════════════════════════════ */
async function loadMessages(append = false) {
  if (S.loading) return;
  S.loading = true;
  showLoading(true);
  try {
    const p = new URLSearchParams({
      gap: S.filters.gap, range: S.filters.time, sort: S.filters.sort,
      limit: PAGE_SIZE, offset: append ? S.offset : 0, min_length: 1,
    });
    if (S.filters.app)    p.set('app', S.filters.app);
    if (S.filters.search) p.set('search', S.filters.search);

    const d = await api('/api/messages?' + p);
    S.messages = append ? S.messages.concat(d.messages) : d.messages;
    S.total    = d.total;
    S.hasMore  = d.has_more;
    S.offset   = append ? S.offset + PAGE_SIZE : PAGE_SIZE;
    renderMessages();
  } catch (e) { console.error('loadMessages', e); }
  finally { S.loading = false; showLoading(false); }
}

function renderMessages() {
  const c = el('messages');
  const empty = el('empty-state');
  const more  = el('load-more-wrap');

  if (!S.messages.length) {
    if (c.children.length > 0) c.innerHTML = '';
    empty.style.display = 'flex'; more.style.display = 'none'; return;
  }
  empty.style.display = 'none';
  more.style.display  = S.hasMore ? 'flex' : 'none';

  // Anti-flicker: only re-render if data changed
  const hash = S.messages.map(m => `${m.start_time}:${m.keystroke_count}:${m.final_text.length}`).join('|');
  if (hash === S._lastMsgHash && !S._forceRender) return;
  S._lastMsgHash = hash;
  S._forceRender = false;

  requestAnimationFrame(() => {
    c.innerHTML = S.messages.map((m, i) => cardHTML(m, i)).join('');
  });
}

function cardHTML(m, i) {
  let text;
  if (S.viewMode === 'raw') text = m.raw_text;
  else if (S.viewMode === 'chrono') text = m.chrono_text;
  else text = m.final_text;

  const time = fmtTime(m.start_time);
  const rel  = fmtRelative(m.start_time);
  const icon = appIcon(m.app);
  const dur  = m.duration > 0 ? fmtDuration(m.duration) : '';
  const win  = m.window ? truncate(m.window, 50) : '';

  return `<div class="message-card" data-key="${m.start_time}">
  <div class="card-header">
    <div class="card-app-info">
      <span class="app-icon">${icon}</span>
      <span class="app-name">${esc(m.app || 'Unknown')}</span>
      ${win ? `<span class="window-title">${esc(win)}</span>` : ''}
    </div>
    <div class="card-meta">
      <span>${time}</span><span class="card-separator">&middot;</span>
      <span>${rel}</span><span class="card-separator">&middot;</span>
      <span>${m.keystroke_count} keys</span>
      ${dur ? `<span class="card-separator">&middot;</span><span>${dur}</span>` : ''}
      <button class="copy-btn" onclick="copyMsg(this,${i})" title="Copy">${svgCopy}</button>
      <button class="delete-msg-btn" onclick="deleteMsg(${i})" title="Delete">
        <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4h8v2M5 6v14a2 2 0 002 2h10a2 2 0 002-2V6"/></svg>
      </button>
    </div>
  </div>
  <div class="card-body"><pre class="card-text">${esc(text)}</pre></div>
</div>`;
}

function loadMore() { loadMessages(true); }

/* ── Copy (with fallback for HTTP context) ─────────────────── */
function copyToClipboard(text) {
  if (navigator.clipboard && window.isSecureContext) {
    return navigator.clipboard.writeText(text);
  }
  // Fallback for non-HTTPS
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.cssText = 'position:fixed;opacity:0;left:-9999px';
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand('copy'); } catch(_) {}
  document.body.removeChild(ta);
  return Promise.resolve();
}

function copyMsg(btn, idx) {
  const m = S.messages[idx];
  if (!m) return;
  let text;
  if (S.viewMode === 'raw') text = m.raw_text;
  else if (S.viewMode === 'chrono') text = m.chrono_text;
  else text = m.final_text;

  copyToClipboard(text).then(() => {
    btn.classList.add('copied');
    btn.innerHTML = svgCheck;
    setTimeout(() => { btn.classList.remove('copied'); btn.innerHTML = svgCopy; }, 1600);
    toast('Copied to clipboard');
  }).catch(() => toast('Copy failed'));
}

/* ── Delete single message ─────────────────────────────────── */
async function deleteMsg(idx) {
  const m = S.messages[idx];
  if (!m) return;
  if (!confirm('Delete this message? This cannot be undone.')) return;
  try {
    await api('/api/delete-events', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ start_time: m.start_time, end_time: m.end_time,
                             process: m.app, confirm: true }),
    });
    S.messages.splice(idx, 1);
    S._forceRender = true;
    renderMessages();
    toast('Message deleted');
    loadStats();
  } catch (e) { toast('Delete failed: ' + e.message); }
}

/* ══════════════════════════════════════════════════════════════
   ACTIVITY
   ══════════════════════════════════════════════════════════════ */
async function loadActivity() {
  try {
    const p = new URLSearchParams({ range: S.actFilters.time, limit: 300 });
    if (S.actFilters.type) p.set('types', S.actFilters.type);
    const d = await api('/api/activity?' + p);
    S.activityEvents = d.events;
    renderActivity();
  } catch (e) { console.error('loadActivity', e); }
}

function renderActivity() {
  const c = el('activity-list');
  const empty = el('activity-empty');
  if (!S.activityEvents.length) {
    c.innerHTML = ''; empty.style.display = 'flex'; return;
  }
  empty.style.display = 'none';
  c.innerHTML = S.activityEvents.map(ev => {
    const icon = activityIcon(ev.event_type);
    const type = ev.event_type.replace('_', ' ');
    let detail = '';
    if (ev.event_type === 'mouse_click') {
      const ex = safeJSON(ev.extra);
      detail = `(${ex.x}, ${ex.y}) ${ev.key_name || ''}`;
    } else if (ev.event_type === 'mouse_move') {
      const ex = safeJSON(ev.extra);
      detail = `(${ex.x}, ${ex.y})`;
    } else if (ev.event_type === 'shortcut') {
      detail = `${ev.modifiers ? ev.modifiers + '+' : ''}${ev.key_name || ''}`;
    } else if (ev.event_type === 'notification') {
      detail = ev.window_title || '';
    } else if (ev.event_type === 'mouse_scroll') {
      const ex = safeJSON(ev.extra);
      detail = `(${ex.x}, ${ex.y}) dx:${ex.dx} dy:${ex.dy}`;
    }
    return `<div class="activity-item">
      <span class="act-icon">${icon}</span>
      <span class="act-type">${esc(type)}</span>
      <span class="act-detail">${esc(detail)}</span>
      <span class="act-app">${esc(ev.window_process || '')}</span>
      <span class="act-time">${fmtTime(ev.timestamp)} ${fmtRelative(ev.timestamp)}</span>
    </div>`;
  }).join('');
}

function activityIcon(type) {
  switch (type) {
    case 'mouse_click': return '\ud83d\uddb1\ufe0f';
    case 'mouse_move': return '\u2194\ufe0f';
    case 'mouse_scroll': return '\ud83d\uddd8\ufe0f';
    case 'shortcut': return '\u2328\ufe0f';
    case 'notification': return '\ud83d\udd14';
    default: return '\ud83d\udcdd';
  }
}

/* ══════════════════════════════════════════════════════════════
   MACROS
   ══════════════════════════════════════════════════════════════ */
async function loadMacros() {
  try {
    const d = await api('/api/macros');
    S.macros = d.macros;
    renderMacros();
    updateGuide();
  } catch (e) { console.error('loadMacros', e); }
}

function renderMacros() {
  const c = el('macro-list');
  const empty = el('macros-empty');
  if (!S.macros.length) {
    c.innerHTML = ''; empty.style.display = 'flex'; return;
  }
  empty.style.display = 'none';
  c.innerHTML = S.macros.map(m => {
    const acts = (Array.isArray(m.actions) ? m.actions : []);
    const summary = acts.map(a => a.type).join(', ') || 'No actions';
    return `<div class="macro-card">
      <div class="macro-icon">\u26a1</div>
      <div class="macro-info">
        <div class="macro-name">${esc(m.name)}</div>
        <div class="macro-shortcut">${m.shortcut ? esc(m.shortcut) : 'No shortcut'} \u2022 ${esc(summary)}</div>
      </div>
      <div class="macro-btns">
        <button class="btn-accent" style="padding:5px 12px;font-size:.78rem" onclick="runMacro(${m.id})">Run</button>
        <button class="btn-ghost-sm" onclick="editMacro(${m.id})">Edit</button>
        <button class="btn-icon-sm danger" onclick="deleteMacro(${m.id})" title="Delete">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4h8v2M5 6v14a2 2 0 002 2h10a2 2 0 002-2V6"/></svg>
        </button>
      </div>
    </div>`;
  }).join('');
}

async function runMacro(id) {
  try {
    await api(`/api/macros/${id}/run`, { method: 'POST' });
    toast('Macro running...');
  } catch (e) { toast('Macro failed: ' + e.message); }
}

async function deleteMacro(id) {
  if (!confirm('Delete this macro?')) return;
  try {
    await api(`/api/macros/${id}`, { method: 'DELETE' });
    toast('Macro deleted');
    loadMacros();
  } catch (e) { toast('Delete failed'); }
}

/* ── Macro Editor ──────────────────────────────────────────── */
function openMacroEditor(id) {
  S._editingMacroId = id || null;
  S._macroActions = [];
  el('macro-name').value = '';
  el('macro-shortcut').value = '';
  el('macro-modal-title').textContent = id ? 'Edit Macro' : 'New Macro';

  if (id) {
    const m = S.macros.find(m => m.id === id);
    if (m) {
      el('macro-name').value = m.name;
      el('macro-shortcut').value = m.shortcut || '';
      S._macroActions = Array.isArray(m.actions) ? [...m.actions] : [];
    }
  }
  renderMacroActions();
  el('macro-modal').style.display = '';
}
function editMacro(id) { openMacroEditor(id); }
function closeMacroEditor() { el('macro-modal').style.display = 'none'; }

function addMacroAction(type) {
  if (type === 'hotkey') S._macroActions.push({ type: 'hotkey', keys: ['ctrl', 'c'] });
  else if (type === 'type') S._macroActions.push({ type: 'type', text: '' });
  else if (type === 'delay') S._macroActions.push({ type: 'delay', ms: 200 });
  else if (type === 'click') S._macroActions.push({ type: 'click', x: 0, y: 0, button: 'left' });
  renderMacroActions();
}

function removeMacroAction(idx) {
  S._macroActions.splice(idx, 1);
  renderMacroActions();
}

function renderMacroActions() {
  const c = el('macro-actions');
  c.innerHTML = S._macroActions.map((a, i) => {
    let fields = '';
    if (a.type === 'hotkey') {
      fields = `<input type="text" value="${esc(a.keys.join('+'))}" onchange="updateAction(${i},'keys',this.value)" placeholder="ctrl+shift+esc" class="mono">`;
    } else if (a.type === 'type') {
      fields = `<input type="text" value="${esc(a.text)}" onchange="updateAction(${i},'text',this.value)" placeholder="Text to type">`;
    } else if (a.type === 'delay') {
      fields = `<input type="number" value="${a.ms}" onchange="updateAction(${i},'ms',+this.value)" min="10" max="30000" style="width:80px"><span style="font-size:.78rem;color:var(--text-muted)">ms</span>`;
    } else if (a.type === 'click') {
      fields = `<input type="number" value="${a.x}" onchange="updateAction(${i},'x',+this.value)" placeholder="X" style="width:70px">
                <input type="number" value="${a.y}" onchange="updateAction(${i},'y',+this.value)" placeholder="Y" style="width:70px">`;
    }
    return `<div class="macro-action-row">
      <span class="act-label">${a.type}</span>${fields}
      <button class="remove-action" onclick="removeMacroAction(${i})">&times;</button>
    </div>`;
  }).join('');
}

function updateAction(idx, key, val) {
  if (key === 'keys') {
    S._macroActions[idx].keys = val.split('+').map(s => s.trim().toLowerCase());
  } else {
    S._macroActions[idx][key] = val;
  }
}

const PRESETS = {
  taskmanager: { name: 'Open Task Manager', shortcut: '', actions: [{ type: 'hotkey', keys: ['ctrl', 'shift', 'esc'] }] },
  screenshot:  { name: 'Screenshot', shortcut: '', actions: [{ type: 'hotkey', keys: ['win', 'shift', 's'] }] },
  explorer:    { name: 'File Explorer', shortcut: '', actions: [{ type: 'hotkey', keys: ['win', 'e'] }] },
  desktop:     { name: 'Show Desktop', shortcut: '', actions: [{ type: 'hotkey', keys: ['win', 'd'] }] },
  lock:        { name: 'Lock Screen', shortcut: '', actions: [{ type: 'hotkey', keys: ['win', 'l'] }] },
};

function loadPreset(name) {
  const p = PRESETS[name];
  if (!p) return;
  el('macro-name').value = p.name;
  el('macro-shortcut').value = p.shortcut;
  S._macroActions = JSON.parse(JSON.stringify(p.actions));
  renderMacroActions();
}

async function saveMacro() {
  const name = el('macro-name').value.trim() || 'Untitled';
  const shortcut = el('macro-shortcut').value.trim();
  const actions = S._macroActions;
  try {
    if (S._editingMacroId) {
      await api(`/api/macros/${S._editingMacroId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, shortcut, actions }),
      });
    } else {
      await api('/api/macros', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, shortcut, actions }),
      });
    }
    toast('Macro saved');
    closeMacroEditor();
    loadMacros();
  } catch (e) { toast('Save failed: ' + e.message); }
}

/* ══════════════════════════════════════════════════════════════
   STATS / APPS / STATUS
   ══════════════════════════════════════════════════════════════ */
async function loadStats() {
  try {
    const d = await api('/api/stats');
    el('stat-keys').textContent     = fmt(d.total_keystrokes);
    el('stat-messages').textContent = fmt(d.events_24h);
    el('stat-clicks').textContent   = fmt(d.total_mouse_clicks);
    el('stat-shortcuts').textContent = fmt(d.total_shortcuts);
    el('stat-dbsize').textContent   = d.db_size_mb + ' MB';
  } catch (_) {}
}

async function loadApps() {
  try {
    S.apps = await api('/api/apps?range=' + S.filters.time);
    const cs = el('cs-app');
    if (!cs) return;
    const dd = cs.querySelector('.cs-dropdown');
    const cur = getCSValue('cs-app');
    dd.innerHTML = '<div class="cs-option selected" data-value="">All Apps</div>';
    S.apps.forEach(a => {
      const div = document.createElement('div');
      div.className = 'cs-option';
      div.dataset.value = a;
      div.textContent = a;
      dd.appendChild(div);
    });
    // Re-wire options
    dd.querySelectorAll('.cs-option').forEach(opt => {
      opt.addEventListener('click', () => {
        dd.querySelectorAll('.cs-option').forEach(o => o.classList.remove('selected'));
        opt.classList.add('selected');
        cs.querySelector('.cs-trigger').textContent = opt.textContent;
        cs.querySelector('.cs-trigger').dataset.value = opt.dataset.value;
        cs.classList.remove('open');
        cs.querySelector('.cs-trigger').dispatchEvent(new Event('change', { bubbles: true }));
      });
    });
    if (cur) setCSValue('cs-app', cur);
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

async function toggleRecording() {
  try {
    const d = await api('/api/toggle', { method: 'POST' });
    S.recording = d.recording;
    renderStatus();
    toast(S.recording ? 'Recording resumed' : 'Recording paused');
  } catch (_) {}
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

/* ══════════════════════════════════════════════════════════════
   SETTINGS
   ══════════════════════════════════════════════════════════════ */
function openSettings() {
  const s = S.settings;
  el('s-keyboard').checked    = s.record_keyboard ?? true;
  el('s-mouse').checked       = s.record_mouse_clicks ?? true;
  el('s-scroll').checked      = s.record_mouse_scroll ?? false;
  el('s-movement').checked    = s.record_mouse_movement ?? false;
  el('s-shortcuts').checked   = s.record_shortcuts ?? true;
  el('s-notifications').checked = s.record_notifications ?? true;
  el('s-clipboard').checked     = s.record_clipboard ?? true;
  el('s-gap').value           = s.default_gap_seconds ?? 5;
  el('s-swgap').value         = s.same_window_gap_seconds ?? 30;
  el('s-minlen').value        = s.min_message_length ?? 1;
  el('s-split-enter').checked = s.split_on_enter ?? false;
  el('s-retention').value     = s.retention_days ?? 30;
  el('s-flush').value         = s.buffer_flush_seconds ?? 1;
  el('s-boot').checked        = s.start_on_boot ?? false;
  // Cloud sync
  el('s-supa-url').value      = s.supabase_url ?? '';
  el('s-supa-key').value      = s.supabase_anon_key ?? '';
  el('s-cloud-key').value     = s.cloud_sync_key ?? '';
  el('s-cloud-enabled').checked = s.cloud_sync_enabled ?? false;
  el('s-cloud-clipboard').checked = s.cloud_sync_clipboard ?? true;
  el('s-cloud-messages').checked = s.cloud_sync_messages ?? true;
  el('cloud-test-result').textContent = '';
  el('settings-modal').style.display = '';
}

function closeSettings() { el('settings-modal').style.display = 'none'; }

async function saveSettings() {
  const data = {
    record_keyboard:       el('s-keyboard').checked,
    record_mouse_clicks:   el('s-mouse').checked,
    record_mouse_scroll:   el('s-scroll').checked,
    record_mouse_movement: el('s-movement').checked,
    record_shortcuts:      el('s-shortcuts').checked,
    record_notifications:  el('s-notifications').checked,
    record_clipboard:      el('s-clipboard').checked,
    default_gap_seconds:   +el('s-gap').value,
    same_window_gap_seconds: +el('s-swgap').value,
    min_message_length:    +el('s-minlen').value,
    split_on_enter:        el('s-split-enter').checked,
    retention_days:        +el('s-retention').value,
    buffer_flush_seconds:  +el('s-flush').value,
    start_on_boot:         el('s-boot').checked,
    // Cloud sync
    supabase_url:          el('s-supa-url').value.trim().replace(/\/$/, ''),
    supabase_anon_key:     el('s-supa-key').value.trim(),
    cloud_sync_key:        el('s-cloud-key').value.trim(),
    cloud_sync_enabled:    el('s-cloud-enabled').checked,
    cloud_sync_clipboard:  el('s-cloud-clipboard').checked,
    cloud_sync_messages:   el('s-cloud-messages').checked,
  };
  try {
    const r = await api('/api/settings', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    S.settings = r.settings || { ...S.settings, ...data };
    toast('Settings saved');
    closeSettings();
  } catch (_) { toast('Failed to save settings'); }
}

/* ══════════════════════════════════════════════════════════════
   CLOUD SYNC
   ══════════════════════════════════════════════════════════════ */
async function testCloudConnection() {
  const result = el('cloud-test-result');
  result.textContent = 'Testing...';
  result.style.color = 'var(--txt-muted)';
  try {
    // Save settings first so the backend has the latest config
    await saveSettings();
    const r = await api('/api/cloud/test', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
    });
    if (r.connected) {
      result.textContent = '✅ Connected!';
      result.style.color = '#22c55e';
    } else {
      result.textContent = '❌ ' + (r.error || 'Failed');
      result.style.color = '#ef4444';
    }
  } catch (e) {
    result.textContent = '❌ ' + e.message;
    result.style.color = '#ef4444';
  }
}

/* ══════════════════════════════════════════════════════════════
   DELETE
   ══════════════════════════════════════════════════════════════ */
function openDeleteModal() {
  el('del-start').value = '';
  el('del-end').value = '';
  el('delete-modal').style.display = '';
}
function closeDeleteModal() { el('delete-modal').style.display = 'none'; }

async function confirmDelete() {
  let start = el('del-start').value;
  let end   = el('del-end').value;

  // If blank, use current filter range
  if (!start || !end) {
    const now = Date.now() / 1000;
    const ranges = { '1h': 3600, '3h': 10800, '6h': 21600, '12h': 43200,
                     '24h': 86400, '3d': 259200, '7d': 604800, '30d': 2592000, 'all': now };
    const secs = ranges[S.filters.time] || 86400;
    start = now - secs;
    end = now;
  } else {
    start = new Date(start).getTime() / 1000;
    end   = new Date(end).getTime() / 1000;
  }

  if (!confirm('Are you SURE you want to permanently delete this data?')) return;

  try {
    await api('/api/delete-events', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ start_time: start, end_time: end, confirm: true }),
    });
    toast('Data deleted');
    closeDeleteModal();
    S._forceRender = true;
    loadMessages();
    loadStats();
  } catch (e) { toast('Delete failed: ' + e.message); }
}

async function clearAllData() {
  if (!confirm('DELETE ALL DATA? This action CANNOT be undone!')) return;
  if (!confirm('Are you ABSOLUTELY sure? Every event, every message will be gone.')) return;
  try {
    await api('/api/delete-all', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirm: true }),
    });
    toast('All data cleared');
    closeSettings();
    S._forceRender = true;
    loadMessages();
    loadStats();
  } catch (e) { toast('Clear failed: ' + e.message); }
}

/* ══════════════════════════════════════════════════════════════
   IMPORT / EXPORT
   ══════════════════════════════════════════════════════════════ */
function exportData() {
  const range = S.filters.time;
  window.open(`/api/export?range=${range}`, '_blank');
  toast('Exporting data...');
}

async function importData(input) {
  const file = input.files && input.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append('file', file);
  try {
    const d = await api('/api/import', { method: 'POST', body: formData });
    toast(`Imported ${d.imported} items`);
    S._forceRender = true;
    loadMessages();
    loadStats();
  } catch (e) { toast('Import failed: ' + e.message); }
  input.value = '';
}

/* ══════════════════════════════════════════════════════════════
   SHORTCUT GUIDE
   ══════════════════════════════════════════════════════════════ */
function updateGuide() {
  const c = el('guide-macros-list');
  if (!c) return;
  if (!S.macros.length) {
    c.innerHTML = '<em class="text-muted">No macros configured</em>';
    return;
  }
  c.innerHTML = S.macros.map(m => {
    const keys = m.shortcut || (Array.isArray(m.actions) && m.actions[0]?.keys?.join('+')) || '—';
    return `<div class="guide-item"><kbd>${esc(keys)}</kbd><span>${esc(m.name)}</span></div>`;
  }).join('');
}

/* ══════════════════════════════════════════════════════════════
   ONBOARDING
   ══════════════════════════════════════════════════════════════ */
const OB_STEPS = [
  { icon: '\u2328\ufe0f', title: 'Welcome to TypeKeep!',
    body: 'TypeKeep silently records your keyboard, mouse, and shortcut activity in the background. Everything is stored locally on your device.' },
  { icon: '\ud83d\udcbb', title: 'Runs in the Background',
    body: 'TypeKeep lives in your system tray. You don\'t need to keep this window open — it records automatically. Right-click the teal T icon to pause or open the dashboard.' },
  { icon: '\ud83d\udcc4', title: 'Smart Text History',
    body: 'Your typing is grouped by context: same app, same window, with cursor-aware reconstruction. Backspaces, arrow keys, and corrections are handled — you see the <strong>final result</strong> by default.',
    features: ['Final text (corrected)', 'Raw keystrokes', 'Chronological view'] },
  { icon: '\u26a1', title: 'Macros & Shortcuts',
    body: 'Record and execute macros — automate key combinations like Ctrl+Shift+Esc (Task Manager) with one click. Build complex sequences with hotkeys, text, delays, and clicks.' },
  { icon: '\ud83d\udee1\ufe0f', title: 'Your Data, Your Control',
    body: 'Export/import your data anytime. Delete individual messages or clear everything. Set retention periods. All data stays local on your machine.' },
];

async function checkOnboarding() {
  try {
    const d = await api('/api/onboarding');
    if (d.show) showOnboarding();
  } catch (_) {}
}

function showOnboarding() {
  S._onboardingStep = 0;
  renderOnboardingStep();
  el('onboarding-modal').style.display = '';
}

function renderOnboardingStep() {
  const step = OB_STEPS[S._onboardingStep];
  const c = el('onboarding-content');
  let html = `<div class="ob-icon">${step.icon}</div><h2>${step.title}</h2><p>${step.body}</p>`;
  if (step.features) {
    html += '<div class="ob-features">' +
      step.features.map(f => `<div class="ob-feature"><span class="ob-feature-icon">\u2713</span><span>${f}</span></div>`).join('') +
      '</div>';
  }
  c.innerHTML = html;

  // Dots
  const dots = el('onboarding-dots');
  dots.innerHTML = OB_STEPS.map((_, i) =>
    `<div class="onboarding-dot${i === S._onboardingStep ? ' active' : ''}"></div>`
  ).join('');

  // Button labels
  el('ob-next').textContent = S._onboardingStep === OB_STEPS.length - 1 ? 'Get Started' : 'Next';
}

function nextOnboardingStep() {
  S._onboardingStep++;
  if (S._onboardingStep >= OB_STEPS.length) {
    skipOnboarding();
    return;
  }
  renderOnboardingStep();
}

async function skipOnboarding() {
  el('onboarding-modal').style.display = 'none';
  try { await api('/api/onboarding/complete', { method: 'POST' }); } catch (_) {}
}

/* ══════════════════════════════════════════════════════════════
   CLIPBOARD HISTORY
   ══════════════════════════════════════════════════════════════ */
async function loadClipboard(append = false) {
  try {
    const ranges = { '1h': 3600, '3h': 10800, '6h': 21600, '12h': 43200,
                     '24h': 86400, '3d': 259200, '7d': 604800, '30d': 2592000 };
    const now = Date.now() / 1000;
    const secs = ranges[S.clipFilters.time];
    const p = new URLSearchParams({
      limit: 60, offset: append ? S.clipOffset : 0,
    });
    if (secs) { p.set('start', now - secs); p.set('end', now); }
    if (S.clipFilters.type) p.set('type', S.clipFilters.type);
    if (S.clipFilters.pinned) p.set('pinned', '1');

    const d = await api('/api/clipboard?' + p);
    S.clipEntries = append ? S.clipEntries.concat(d.entries) : d.entries;
    S.clipTotal = d.total;
    S.clipHasMore = d.has_more;
    S.clipOffset = append ? S.clipOffset + 60 : 60;
    renderClipboard();
    loadClipStats();
  } catch (e) { console.error('loadClipboard', e); }
}

async function loadClipStats() {
  try {
    const d = await api('/api/clipboard/stats');
    const c = el('clip-stats');
    if (c) c.innerHTML = `<span>📋 ${d.total} entries</span><span>📝 ${d.texts} text</span><span>🖼️ ${d.images} images</span><span>📁 ${d.files} files</span>`;
  } catch (_) {}
}

function renderClipboard() {
  const c = el('clipboard-list');
  const empty = el('clipboard-empty');
  const more = el('clip-load-more');

  if (!S.clipEntries.length) {
    c.innerHTML = ''; empty.style.display = 'flex'; more.style.display = 'none'; return;
  }
  empty.style.display = 'none';
  more.style.display = S.clipHasMore ? 'flex' : 'none';

  c.innerHTML = S.clipEntries.map(e => clipCardHTML(e)).join('');
}

function clipCardHTML(e) {
  const time = fmtTime(e.timestamp);
  const rel = fmtRelative(e.timestamp);
  const pinCls = e.pinned ? ' pinned' : '';
  const deviceBadge = e.device_id ? `<span class="clip-device">${esc(e.device_id)}</span>` : '';
  let content = '';

  if (e.content_type === 'text') {
    const preview = truncate(e.content_text || '', 300);
    content = `<pre class="clip-text">${esc(preview)}</pre>`;
  } else if (e.content_type === 'image') {
    const src = e.thumbnail_url || e.file_url || '';
    content = src
      ? `<img class="clip-img" src="${src}" alt="Clipboard image" loading="lazy" onclick="window.open('${e.file_url || src}','_blank')">`
      : '<span class="text-muted">Image (file missing)</span>';
  } else if (e.content_type === 'files') {
    const files = (e.content_text || '').split('\n').filter(Boolean);
    content = `<div class="clip-files">${files.map(f => `<div class="clip-file-item">📄 ${esc(f.split('\\\\').pop().split('/').pop())}</div>`).join('')}</div>`;
  }

  const typeIcon = e.content_type === 'text' ? '📝' : e.content_type === 'image' ? '🖼️' : '📁';

  return `<div class="clip-card${pinCls}" data-id="${e.id}">
    <div class="clip-header">
      <span class="clip-type">${typeIcon} ${e.content_type}</span>
      ${deviceBadge}
      <span class="clip-app">${esc(e.source_app || '')}</span>
      <span class="clip-time">${time} ${rel}</span>
      <div class="clip-actions">
        ${e.content_type === 'text' ? `<button class="copy-btn" onclick="copyClipEntry(this,${e.id})" title="Copy">${svgCopy}</button>` : ''}
        <button class="copy-btn" onclick="toggleClipPin(${e.id})" title="${e.pinned ? 'Unpin' : 'Pin'}">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="${e.pinned ? 'var(--warning)' : 'none'}" stroke="currentColor" stroke-width="2"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
        </button>
        <button class="delete-msg-btn" onclick="deleteClipEntry(${e.id})" title="Delete">
          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4h8v2M5 6v14a2 2 0 002 2h10a2 2 0 002-2V6"/></svg>
        </button>
      </div>
    </div>
    <div class="clip-body">${content}</div>
  </div>`;
}

function loadMoreClipboard() { loadClipboard(true); }

function toggleClipPinFilter() {
  S.clipFilters.pinned = !S.clipFilters.pinned;
  const btn = el('clip-pin-filter');
  btn.classList.toggle('active', S.clipFilters.pinned);
  loadClipboard();
}

async function copyClipEntry(btn, id) {
  const e = S.clipEntries.find(x => x.id === id);
  if (!e || !e.content_text) return;
  copyToClipboard(e.content_text).then(() => {
    btn.classList.add('copied');
    btn.innerHTML = svgCheck;
    setTimeout(() => { btn.classList.remove('copied'); btn.innerHTML = svgCopy; }, 1600);
    toast('Copied to clipboard');
  }).catch(() => toast('Copy failed'));
}

async function toggleClipPin(id) {
  try {
    await api(`/api/clipboard/${id}/pin`, { method: 'POST' });
    loadClipboard();
  } catch (e) { toast('Pin toggle failed'); }
}

async function deleteClipEntry(id) {
  if (!confirm('Delete this clipboard entry?')) return;
  try {
    await api(`/api/clipboard/${id}`, { method: 'DELETE' });
    S.clipEntries = S.clipEntries.filter(e => e.id !== id);
    renderClipboard();
    toast('Entry deleted');
  } catch (e) { toast('Delete failed'); }
}

async function clearClipboard() {
  if (!confirm('Clear all unpinned clipboard entries?')) return;
  try {
    await api('/api/clipboard/clear', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirm: true }),
    });
    toast('Clipboard cleared');
    loadClipboard();
  } catch (e) { toast('Clear failed'); }
}

/* ══════════════════════════════════════════════════════════════
   SYNC / DEVICES
   ══════════════════════════════════════════════════════════════ */
async function loadSyncInfo() {
  try {
    const d = await api('/api/sync/info');
    S.syncInfo = d;
    el('my-device-name').textContent = d.device_name || 'This Device';
    el('my-device-id').textContent = 'ID: ' + (d.device_id || '—');
    el('sync-device-name').value = d.device_name || '';
    el('sync-key').value = d.sync_key || '';
    el('sync-enabled').checked = !!d.sync_enabled;
    el('sync-clipboard').checked = !!d.clipboard_sync;
  } catch (_) {}
  loadDevices();
}

async function loadDevices() {
  try {
    const d = await api('/api/sync/devices');
    S.pairedDevices = d.devices;
    renderDevices();
  } catch (_) {}
}

function renderDevices() {
  const c = el('device-list');
  const empty = el('devices-empty');
  if (!S.pairedDevices.length) {
    c.innerHTML = ''; empty.style.display = 'flex'; return;
  }
  empty.style.display = 'none';
  c.innerHTML = S.pairedDevices.map(d => {
    const seen = d.last_seen ? fmtRelative(d.last_seen) : 'never';
    return `<div class="device-card">
      <div class="device-card-header">
        <span class="device-icon">💻</span>
        <div class="device-info">
          <span class="device-name">${esc(d.name)}</span>
          <span class="device-id">${esc(d.id)} • ${esc(d.ip_address || '?')}:${d.port || 7700}</span>
        </div>
        <span class="device-seen">Seen ${seen}</span>
      </div>
      <div class="device-actions">
        <button class="btn-ghost-sm" onclick="pullFromDevice('${esc(d.id)}')">Pull Clipboard</button>
        <button class="btn-danger-sm" onclick="unpairDevice('${esc(d.id)}')">Unpair</button>
      </div>
    </div>`;
  }).join('');
}

async function saveSyncSettings() {
  try {
    await api('/api/sync/info', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        device_name: el('sync-device-name').value,
        sync_key: el('sync-key').value,
        sync_enabled: el('sync-enabled').checked,
        clipboard_sync: el('sync-clipboard').checked,
      }),
    });
    toast('Sync settings saved');
    loadSyncInfo();
  } catch (e) { toast('Save failed: ' + e.message); }
}

async function pairDevice() {
  const ip = el('pair-ip').value.trim();
  const port = el('pair-port').value || 7700;
  const key = el('pair-key').value.trim();
  if (!ip) { toast('Enter an IP address'); return; }
  if (!key) { toast('Enter the sync key'); return; }
  try {
    const d = await api('/api/sync/pair', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ip, port: +port, sync_key: key }),
    });
    toast('Device paired: ' + (d.device?.device_name || ip));
    el('pair-ip').value = '';
    el('pair-key').value = '';
    loadDevices();
  } catch (e) { toast('Pair failed: ' + e.message); }
}

async function unpairDevice(id) {
  if (!confirm('Unpair this device?')) return;
  try {
    await api(`/api/sync/unpair/${id}`, { method: 'DELETE' });
    toast('Device unpaired');
    loadDevices();
  } catch (e) { toast('Unpair failed'); }
}

async function pullFromDevice(id) {
  toast('Pulling clipboard data...');
  try {
    const d = await api('/api/sync/pull', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_id: id, data_type: 'clipboard' }),
    });
    toast(`Imported ${d.imported} clipboard entries`);
    if (S.activeTab === 'clipboard') loadClipboard();
  } catch (e) { toast('Pull failed: ' + e.message); }
}

/* ══════════════════════════════════════════════════════════════
   EVENT WIRING
   ══════════════════════════════════════════════════════════════ */
function wireEvents() {
  const reload = () => { S.offset = 0; S._forceRender = true; loadMessages(); };

  // History filters via custom selects
  document.getElementById('cs-time')?.addEventListener('change', () => {
    S.filters.time = getCSValue('cs-time'); saveFilters(); loadApps(); reload();
  });
  document.getElementById('cs-gap')?.addEventListener('change', () => {
    S.filters.gap = getCSValue('cs-gap'); saveFilters(); reload();
  });
  document.getElementById('cs-app')?.addEventListener('change', () => {
    S.filters.app = getCSValue('cs-app'); saveFilters(); reload();
  });
  document.getElementById('cs-sort')?.addEventListener('change', () => {
    S.filters.sort = getCSValue('cs-sort'); saveFilters(); reload();
  });
  document.getElementById('cs-view')?.addEventListener('change', () => {
    S.viewMode = getCSValue('cs-view'); S._forceRender = true; renderMessages();
  });

  // Activity filters
  document.getElementById('cs-act-time')?.addEventListener('change', () => {
    S.actFilters.time = getCSValue('cs-act-time'); loadActivity();
  });
  document.getElementById('cs-act-type')?.addEventListener('change', () => {
    S.actFilters.type = getCSValue('cs-act-type'); loadActivity();
  });

  // Clipboard filters
  document.getElementById('cs-clip-time')?.addEventListener('change', () => {
    S.clipFilters.time = getCSValue('cs-clip-time'); loadClipboard();
  });
  document.getElementById('cs-clip-type')?.addEventListener('change', () => {
    S.clipFilters.type = getCSValue('cs-clip-type'); loadClipboard();
  });

  // Search
  el('search-input').addEventListener('input', debounce(e => {
    S.filters.search = e.target.value; saveFilters(); reload();
  }, DEBOUNCE_MS));

  // Modals
  ['settings-modal', 'delete-modal', 'macro-modal', 'onboarding-modal'].forEach(id => {
    el(id)?.addEventListener('click', e => { if (e.target.id === id) el(id).style.display = 'none'; });
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      ['settings-modal', 'delete-modal', 'macro-modal'].forEach(id => el(id).style.display = 'none');
    }
  });

  // Restore filter values
  setCSValue('cs-time', S.filters.time);
  setCSValue('cs-gap', S.filters.gap);
  setCSValue('cs-sort', S.filters.sort);
  el('search-input').value = S.filters.search;
}

/* ── Auto-refresh (no flicker) ─────────────────────────────── */
function startRefresh() {
  _refreshTimer = setInterval(() => {
    if (document.hidden) return;
    loadMessages();
    loadStats();
  }, REFRESH_MS);
}

/* ── Persistence ───────────────────────────────────────────── */
function saveFilters() {
  try { localStorage.setItem('tk_filters', JSON.stringify(S.filters)); } catch (_) {}
}
function restoreFilters() {
  try {
    const s = localStorage.getItem('tk_filters');
    if (s) Object.assign(S.filters, JSON.parse(s));
  } catch (_) {}
}

/* ── Utilities ─────────────────────────────────────────────── */
function el(id) { return document.getElementById(id); }
function showLoading(on) { el('loading').style.display = on ? 'flex' : 'none'; }

function toast(msg) {
  const t = el('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => t.classList.remove('show'), 2200);
}

function fmt(n) { return n == null ? '\u2014' : n.toLocaleString(); }

function fmtTime(ts) {
  if (!ts) return '';
  return new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function fmtRelative(ts) {
  if (!ts) return '';
  const s = Math.floor(Date.now() / 1000 - ts);
  if (s < 5)     return 'just now';
  if (s < 60)    return s + 's ago';
  if (s < 3600)  return Math.floor(s / 60) + 'm ago';
  if (s < 86400) return Math.floor(s / 3600) + 'h ago';
  return Math.floor(s / 86400) + 'd ago';
}

function fmtDuration(s) {
  if (s < 1)    return '<1s';
  if (s < 60)   return Math.round(s) + 's';
  if (s < 3600) return Math.floor(s / 60) + 'm ' + Math.round(s % 60) + 's';
  return Math.floor(s / 3600) + 'h ' + Math.floor((s % 3600) / 60) + 'm';
}

function truncate(s, n) { return s.length > n ? s.slice(0, n) + '\u2026' : s; }

function esc(s) {
  if (!s) return '';
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function debounce(fn, ms) {
  let t;
  return function (...args) { clearTimeout(t); t = setTimeout(() => fn.apply(this, args), ms); };
}

function safeJSON(s) {
  try { return JSON.parse(s || '{}'); } catch (_) { return {}; }
}

/* ── App icons ─────────────────────────────────────────────── */
const APP_ICONS = {
  'chrome.exe':'🌐','msedge.exe':'🌐','firefox.exe':'🦊','brave.exe':'🦁',
  'opera.exe':'🌐','vivaldi.exe':'🌐','Code.exe':'💻','code.exe':'💻',
  'discord.exe':'💬','Telegram.exe':'💬','slack.exe':'💬','Teams.exe':'💬',
  'explorer.exe':'📁','notepad.exe':'📝','notepad++.exe':'📝',
  'cmd.exe':'⚡','powershell.exe':'⚡','WindowsTerminal.exe':'⚡',
  'WINWORD.EXE':'📄','EXCEL.EXE':'📊','POWERPNT.EXE':'📊',
  'Spotify.exe':'🎵','vlc.exe':'🎬','steam.exe':'🎮',
};
function appIcon(name) { return (name && APP_ICONS[name]) || '🖥️'; }

/* ── SVGs ──────────────────────────────────────────────────── */
const svgCopy = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>`;
const svgCheck = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`;
