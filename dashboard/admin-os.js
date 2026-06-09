/**
 * Infinity Admin OS — shell logic (ARIA-aware, zero-cost APIs)
 */
(function () {
  'use strict';

  const API_BASE = window.API_BASE || `${location.protocol}//${location.hostname}:8000`;
  const ADMIN_OS = `${API_BASE}/admin-os`;
  const ADMIN_URL = window.ADMIN_URL || ADMIN_OS;

  const $ = (id) => document.getElementById(id);
  function esc(s) {
    return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
  }
  const announce = (msg) => {
    const lr = $('live-region');
    if (lr) lr.textContent = msg;
  };

  function clockTick() {
    const now = new Date();
    const text = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const titleClock = $('title-clock');
    const trayClock = $('tray-clock');
    if (titleClock) titleClock.textContent = text;
    if (trayClock) trayClock.textContent = text;
  }

  function toggleStartMenu(open) {
    const menu = $('start-menu');
    const btn = $('taskbar-start');
    if (!menu || !btn) return;
    const show = open ?? menu.hidden;
    menu.hidden = !show;
    btn.setAttribute('aria-expanded', String(show));
    if (show) {
      const search = $('start-search');
      if (search) search.focus();
      announce('Start menu opened');
    } else {
      announce('Start menu closed');
    }
  }

  /** Populate a container from app-authored markup (escape dynamic values with esc()). */
  function setTrustedWindowHtml(container, html) {
    const template = document.createElement('template');
    template.innerHTML = html;
    container.replaceChildren(...template.content.childNodes);
  }

  function openAppWindow(id, title, html) {
    const stack = $('window-stack');
    if (!stack) return;
    const existing = document.getElementById(id);
    if (existing) {
      existing.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      return;
    }
    const article = document.createElement('article');
    article.className = 'app-window';
    article.id = id;
    article.setAttribute('role', 'region');
    article.setAttribute('aria-labelledby', `${id}-title`);

    const chrome = document.createElement('div');
    chrome.className = 'window-chrome';
    const heading = document.createElement('h2');
    heading.id = `${id}-title`;
    heading.className = 'window-title';
    heading.textContent = title;
    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'window-close';
    closeBtn.setAttribute('aria-label', `Close ${title}`);
    closeBtn.textContent = '✕';
    chrome.append(heading, closeBtn);

    const body = document.createElement('div');
    body.className = 'window-body';
    setTrustedWindowHtml(body, html);

    article.append(chrome, body);
    closeBtn.addEventListener('click', () => {
      article.remove();
      announce(`${title} closed`);
    });
    stack.appendChild(article);
    announce(`${title} opened`);
  }

  async function fetchJson(url) {
    const r = await fetch(url, { headers: { Accept: 'application/json' } });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  }

  async function loadTrayStatus() {
    const healthBtn = $('tray-health');
    const rotBtn = $('tray-rotation');
    try {
      const h = await fetchJson(`${API_BASE}/health`);
      if (healthBtn) {
        healthBtn.classList.toggle('healthy', h.status === 'healthy' || h.status === 'ok');
        healthBtn.setAttribute('aria-label', `Platform ${h.status || 'unknown'}`);
      }
    } catch {
      if (healthBtn) healthBtn.classList.remove('healthy');
    }
    try {
      const a = await fetchJson(`${API_BASE}/adaptive/status`);
      const provider = a.active_provider || a.rotation?.state?.active_provider || '—';
      if (rotBtn) {
        rotBtn.textContent = provider.slice(0, 6);
        rotBtn.setAttribute('aria-label', `Active AI provider ${provider}`);
      }
    } catch {
      if (rotBtn) rotBtn.textContent = 'AI';
    }
  }

  async function showDomainModel() {
    const html = `
      <div class="admin-toolbar">
        <select id="dm-pid" aria-label="Select entity PID"></select>
        <button type="button" id="dm-load">Load</button>
        <button type="button" id="dm-graph" class="secondary">Graph stats</button>
      </div>
      <div class="admin-split">
        <div>
          <label for="dm-location">Location name</label>
          <input id="dm-location" type="text" style="width:100%;margin:4px 0 8px" />
          <button type="button" id="dm-save-loc">Save location</button>
          <label for="dm-lead" style="display:block;margin-top:12px">Lead AI</label>
          <input id="dm-lead" type="text" style="width:100%;margin:4px 0 8px" />
          <button type="button" id="dm-save-lead">Save Lead AI</button>
        </div>
        <pre id="dm-detail" style="font-size:11px;overflow:auto;max-height:320px"></pre>
      </div>
      <p id="dm-msg" style="font-size:12px;color:var(--os-muted)"></p>`;
    openAppWindow('win-domain', 'Domain Model', html);
    try {
      const data = await fetchJson(`${ADMIN_OS}/domain-model`);
      const sel = document.getElementById('dm-pid');
      (data.entities || []).forEach((e) => {
        const o = document.createElement('option');
        o.value = e.pid;
        o.textContent = `${e.pid} — ${e.location}`;
        sel.appendChild(o);
      });
      const loadPid = async () => {
        const pid = sel.value;
        const d = await fetchJson(`${ADMIN_OS}/domain-model/entities/${pid}`);
        document.getElementById('dm-location').value = d.location || '';
        document.getElementById('dm-lead').value = d.lead_ai || '';
        document.getElementById('dm-detail').textContent = JSON.stringify(d, null, 2);
      };
      document.getElementById('dm-load').onclick = loadPid;
      document.getElementById('dm-graph').onclick = async () => {
        const g = await fetchJson(`${ADMIN_OS}/domain-model/graph`);
        document.getElementById('dm-msg').textContent = `Graph: ${g.total_nodes} nodes, ${g.edges.length} edges`;
      };
      document.getElementById('dm-save-loc').onclick = async () => {
        const pid = sel.value;
        const new_name = document.getElementById('dm-location').value;
        await fetch(`${ADMIN_OS}/domain-model/entities/${pid}/location`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ new_name }),
        });
        announce('Location saved');
        loadPid();
      };
      document.getElementById('dm-save-lead').onclick = async () => {
        const pid = sel.value;
        const new_name = document.getElementById('dm-lead').value;
        await fetch(`${ADMIN_OS}/domain-model/entities/${pid}/lead-ai`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ new_name }),
        });
        announce('Lead AI saved');
        loadPid();
      };
      if (sel.options.length) await loadPid();
    } catch (e) {
      document.getElementById('dm-msg').textContent = e.message;
    }
  }

  function showWindowError(win, message) {
    const body = win.querySelector('.window-body');
    body.replaceChildren();
    const p = document.createElement('p');
    p.textContent = message;
    body.appendChild(p);
  }

  async function mountFilesPanel(win, pathValue) {
    const body = win.querySelector('.window-body');
    body.replaceChildren();
    const loading = document.createElement('p');
    loading.textContent = 'Loading…';
    body.appendChild(loading);

    const data = await fetchJson(`${ADMIN_OS}/files?path=${encodeURIComponent(pathValue)}`);

    const toolbar = document.createElement('div');
    toolbar.className = 'admin-toolbar';

    const pathInput = document.createElement('input');
    pathInput.id = 'files-path';
    pathInput.type = 'text';
    pathInput.value = pathValue;
    pathInput.style.flex = '1';
    pathInput.setAttribute('aria-label', 'Path');

    const refreshBtn = document.createElement('button');
    refreshBtn.type = 'button';
    refreshBtn.id = 'files-refresh';
    refreshBtn.textContent = 'Refresh';

    const mkdirBtn = document.createElement('button');
    mkdirBtn.type = 'button';
    mkdirBtn.id = 'files-mkdir';
    mkdirBtn.className = 'secondary';
    mkdirBtn.textContent = 'New folder';

    const deleteBtn = document.createElement('button');
    deleteBtn.type = 'button';
    deleteBtn.id = 'files-delete';
    deleteBtn.className = 'secondary';
    deleteBtn.textContent = 'Delete';

    toolbar.append(pathInput, refreshBtn, mkdirBtn, deleteBtn);

    const table = document.createElement('table');
    table.className = 'admin-table';
    table.setAttribute('role', 'table');
    const tbody = document.createElement('tbody');
    for (const entry of data.entries || []) {
      const tr = document.createElement('tr');
      tr.dataset.path = entry.path ?? '';
      tr.dataset.type = entry.type ?? '';
      const iconCell = document.createElement('td');
      iconCell.textContent = entry.type === 'directory' ? '📁' : '📄';
      const nameCell = document.createElement('td');
      nameCell.textContent = entry.name ?? '';
      const sizeCell = document.createElement('td');
      sizeCell.textContent = entry.size ?? '';
      tr.append(iconCell, nameCell, sizeCell);
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);

    const editorLabel = document.createElement('label');
    editorLabel.setAttribute('for', 'files-editor');
    editorLabel.textContent = 'File editor';

    const editor = document.createElement('textarea');
    editor.id = 'files-editor';
    editor.className = 'admin-editor';
    editor.setAttribute('aria-label', 'File content');

    const saveBtn = document.createElement('button');
    saveBtn.type = 'button';
    saveBtn.id = 'files-save';
    saveBtn.textContent = 'Save file';

    const msg = document.createElement('p');
    msg.id = 'files-msg';

    body.replaceChildren(toolbar, table, editorLabel, editor, saveBtn, msg);

    refreshBtn.onclick = async () => {
      await mountFilesPanel(win, pathInput.value);
    };

    tbody.querySelectorAll('tr').forEach((tr) => {
      tr.onclick = async () => {
        const p = tr.dataset.path;
        if (tr.dataset.type === 'directory') {
          pathInput.value = p;
          refreshBtn.click();
        } else {
          const f = await fetchJson(`${ADMIN_OS}/files/read?path=${encodeURIComponent(p)}`);
          editor.value = f.content;
          pathInput.value = p;
          msg.textContent = `Editing ${p}`;
        }
      };
    });

    saveBtn.onclick = async () => {
      const p = pathInput.value;
      await fetch(`${ADMIN_OS}/files/write?path=${encodeURIComponent(p)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: editor.value, create: true }),
      });
      announce('File saved');
    };

    mkdirBtn.onclick = async () => {
      const name = prompt('Folder name (relative to current path):');
      if (!name) return;
      const p = pathValue ? `${pathValue}/${name}` : name;
      await fetch(`${ADMIN_OS}/files/mkdir?path=${encodeURIComponent(p)}`, { method: 'POST' });
      refreshBtn.click();
    };

    deleteBtn.onclick = async () => {
      const p = pathInput.value;
      if (!p || !confirm(`Delete ${p}?`)) return;
      await fetch(`${ADMIN_OS}/files?path=${encodeURIComponent(p)}`, { method: 'DELETE' });
      pathInput.value = '';
      refreshBtn.click();
    };
  }

  async function showFiles() {
    openAppWindow('win-files', 'Files', '<p>Loading…</p>');
    const win = document.getElementById('win-files');
    try {
      await mountFilesPanel(win, '');
    } catch (e) {
      showWindowError(win, e.message);
    }
  }

  async function showBackups() {
    try {
      const data = await fetchJson(`${ADMIN_OS}/backups`);
      const rows = (data.backups || [])
        .map((b) => `<tr><td>${esc(b.created_at)}</td><td>${esc(b.trigger)}</td><td>${esc(b.size_bytes)}</td><td>${esc(b.path)}</td></tr>`)
        .join('');
      openAppWindow(
        'win-backups',
        'Backups',
        `<p>Auto: every <strong>${esc(data.config.auto_backup_hours)}h</strong> (${data.config.auto_backup_enabled ? 'on' : 'off'})</p>
         <button type="button" id="btn-backup-run">Run backup now</button>
         <table class="admin-table"><thead><tr><th>When</th><th>Trigger</th><th>Size</th><th>Path</th></tr></thead><tbody>${rows}</tbody></table>`
      );
      document.getElementById('btn-backup-run')?.addEventListener('click', async () => {
        await fetch(`${ADMIN_OS}/backups/run`, { method: 'POST' });
        announce('Backup completed');
        showBackups();
      });
    } catch (e) {
      openAppWindow('win-backups', 'Backups', `<p>${esc(e.message)}</p>`);
    }
  }

  async function showSystem() {
    try {
      const data = await fetchJson(`${ADMIN_OS}/system`);
      openAppWindow(
        'win-system',
        'System Viewer',
        `<pre style="font-size:11px;overflow:auto;max-height:400px">${esc(JSON.stringify(data, null, 2))}</pre>`
      );
    } catch (e) {
      openAppWindow('win-system', 'System Viewer', `<p>${esc(e.message)}</p>`);
    }
  }

  async function showEvents() {
    const html = `
      <div class="admin-toolbar">
        <button type="button" id="ev-refresh">Refresh</button>
        <button type="button" id="ev-live" class="secondary">Live stream</button>
        <select id="ev-cat" aria-label="Category"><option value="">All categories</option>
          <option value="governance">governance</option><option value="system">system</option>
          <option value="security">security</option><option value="audit">audit</option></select>
      </div>
      <div id="ev-live-box" class="event-live" hidden></div>
      <table class="admin-table" id="ev-table"><thead><tr><th>Time</th><th>Type</th><th>Actor</th><th>Outcome</th></tr></thead><tbody></tbody></table>`;
    openAppWindow('win-events', 'Event Viewer — The Observatory', html);
    const load = async () => {
      const cat = document.getElementById('ev-cat').value;
      const q = cat ? `?limit=80&category=${encodeURIComponent(cat)}` : '?limit=80';
      const data = await fetchJson(`${ADMIN_OS}/events${q}`);
      const tbody = document.querySelector('#ev-table tbody');
      tbody.replaceChildren();
      for (const e of data.events || []) {
        const tr = document.createElement('tr');
        const cells = [
          new Date((e.timestamp || 0) * 1000).toLocaleTimeString(),
          e.event_type ?? '',
          e.actor || '—',
          e.outcome ?? '',
        ];
        for (const cell of cells) {
          const td = document.createElement('td');
          td.textContent = cell;
          tr.appendChild(td);
        }
        tbody.appendChild(tr);
      }
    };
    document.getElementById('ev-refresh').onclick = load;
    document.getElementById('ev-live').onclick = () => {
      const box = document.getElementById('ev-live-box');
      box.hidden = false;
      box.textContent = 'Connecting to Observatory SSE…\n';
      const es = new EventSource(`${API_BASE}/observatory/sse`);
      es.onmessage = (msg) => {
        try {
          const ev = JSON.parse(msg.data);
          box.textContent = `${new Date().toLocaleTimeString()} ${ev.event_type} ${ev.actor || ''}\n` + box.textContent;
        } catch {
          /* keepalive */
        }
      };
      es.onerror = () => {
        box.textContent += 'Stream ended or unavailable.\n';
        es.close();
      };
    };
    await load();
  }

  async function showEntities() {
    try {
      const data = await fetchJson(`${ADMIN_OS}/entities`);
      const rows = (data.entities || [])
        .slice(0, 40)
        .map(
          (e) =>
            `<tr><td>${esc(e.pid || '')}</td><td>${esc(e.location || '')}</td><td>${esc(e.lead_ai || '')}</td></tr>`
        )
        .join('');
      openAppWindow(
        'win-entities',
        'Entity Registry',
        `<p>${esc(data.total || 0)} entities. Full editor on <a href="index.html#infinity-admin">dashboard</a>.</p>
         <table style="width:100%;font-size:12px;border-collapse:collapse" role="table" aria-label="Entities preview">
           <thead><tr><th scope="col">PID</th><th scope="col">Location</th><th scope="col">Lead AI</th></tr></thead>
           <tbody>${rows || '<tr><td colspan="3">No data</td></tr>'}</tbody>
         </table>`
      );
    } catch (e) {
      openAppWindow('win-entities', 'Entity Registry', `<p>Cannot reach Admin API: ${esc(e.message)}</p>`);
    }
  }

  async function showAdaptive() {
    try {
      const data = await fetchJson(`${API_BASE}/adaptive/status`);
      openAppWindow(
        'win-adaptive',
        'Adaptive AI Rotation',
        `<pre style="font-size:11px;overflow:auto;max-height:320px">${esc(JSON.stringify(data, null, 2))}</pre>
         <p><button type="button" id="btn-proactive-run">Run proactive check now</button></p>`
      );
      document.getElementById('btn-proactive-run')?.addEventListener('click', async () => {
        await fetch(`${API_BASE}/adaptive/proactive/run`, { method: 'POST' });
        announce('Proactive run triggered');
        showAdaptive();
      });
    } catch (e) {
      openAppWindow('win-adaptive', 'Adaptive AI', `<p>${esc(e.message)}</p>`);
    }
  }

  async function showOrchestrators() {
    try {
      const data = await fetchJson(`${ADMIN_URL}/admin/orchestrators`);
      const list = (data.orchestrators || [])
        .map((o) => `<li><strong>${esc(o.name)}</strong> <span style="color:var(--os-muted)">(${esc(o.id)})</span></li>`)
        .join('');
      openAppWindow(
        'win-orch',
        'Tier 1 Orchestrators',
        `<ul>${list}</ul><p>Rename via PATCH /admin/orchestrators/{id}</p>`
      );
    } catch (e) {
      openAppWindow('win-orch', 'Orchestrators', `<p>${esc(e.message)}</p>`);
    }
  }

  function bindEvents() {
    $('taskbar-start')?.addEventListener('click', () => toggleStartMenu());
    $('btn-power')?.addEventListener('click', () => {
      toggleStartMenu(false);
      location.href = 'index.html';
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') toggleStartMenu(false);
    });
    document.querySelectorAll('.start-tile').forEach((tile) => {
      tile.addEventListener('click', () => {
        toggleStartMenu(false);
        const app = tile.dataset.app;
        if (app === 'domain-model') showDomainModel();
        else if (app === 'files') showFiles();
        else if (app === 'backups') showBackups();
        else if (app === 'system') showSystem();
        else if (app === 'events') showEvents();
        else if (app === 'entities') showEntities();
        else if (app === 'adaptive') showAdaptive();
        else if (app === 'orchestrators') showOrchestrators();
        else if (app === 'health') location.href = 'index.html#overview';
        else if (app === 'swarm') openAppWindow('win-swarm', 'Swarm', '<p>Coordinator on port <strong>8053</strong>. Logs: <code>logs/swarm-coordinator.jsonl</code></p>');
        else if (app === 'dashboard') location.href = 'index.html';
      });
    });
    $('tray-health')?.addEventListener('click', () => loadTrayStatus());
    $('tray-rotation')?.addEventListener('click', showAdaptive);
  }

  clockTick();
  setInterval(clockTick, 30000);
  bindEvents();
  loadTrayStatus();
  setInterval(loadTrayStatus, 60000);
})();
