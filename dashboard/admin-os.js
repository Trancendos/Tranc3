/**
 * Infinity Admin OS — shell logic (ARIA-aware, zero-cost APIs)
 */
(function () {
  'use strict';

  const API_BASE = window.API_BASE || `${location.protocol}//${location.hostname}:8000`;
  const ADMIN_OS = `${API_BASE}/admin-os`;
  const ADMIN_URL = window.ADMIN_URL || ADMIN_OS;

  const $ = (id) => document.getElementById(id);
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
    article.innerHTML = `
      <div class="window-chrome">
        <h2 id="${id}-title" class="window-title">${title}</h2>
        <button type="button" class="window-close" aria-label="Close ${title}">✕</button>
      </div>
      <div class="window-body">${html}</div>
    `;
    article.querySelector('.window-close')?.addEventListener('click', () => {
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

  async function showFiles() {
    let currentPath = '';
    const render = async () => {
      const data = await fetchJson(`${ADMIN_OS}/files?path=${encodeURIComponent(currentPath)}`);
      const rows = (data.entries || [])
        .map(
          (e) =>
            `<tr data-path="${e.path}" data-type="${e.type}"><td>${e.type === 'directory' ? '📁' : '📄'}</td><td>${e.name}</td><td>${e.size ?? ''}</td></tr>`
        )
        .join('');
      return `
        <div class="admin-toolbar">
          <input id="files-path" type="text" value="${currentPath}" style="flex:1" aria-label="Path" />
          <button type="button" id="files-refresh">Refresh</button>
          <button type="button" id="files-mkdir" class="secondary">New folder</button>
          <button type="button" id="files-delete" class="secondary">Delete</button>
        </div>
        <table class="admin-table" role="table"><tbody>${rows}</tbody></table>
        <label for="files-editor">File editor</label>
        <textarea id="files-editor" class="admin-editor" aria-label="File content"></textarea>
        <button type="button" id="files-save">Save file</button>
        <p id="files-msg"></p>`;
    };
    openAppWindow('win-files', 'Files', '<p>Loading…</p>');
    const win = document.getElementById('win-files');
    const bind = () => {
      win.querySelector('#files-refresh').onclick = async () => {
        currentPath = win.querySelector('#files-path').value;
        win.querySelector('.window-body').innerHTML = await render();
        bind();
      };
      win.querySelectorAll('.admin-table tr').forEach((tr) => {
        tr.onclick = async () => {
          const p = tr.dataset.path;
          if (tr.dataset.type === 'directory') {
            currentPath = p;
            win.querySelector('#files-path').value = p;
            win.querySelector('#files-refresh').click();
          } else {
            const f = await fetchJson(`${ADMIN_OS}/files/read?path=${encodeURIComponent(p)}`);
            win.querySelector('#files-editor').value = f.content;
            win.querySelector('#files-path').value = p;
            win.querySelector('#files-msg').textContent = `Editing ${p}`;
          }
        };
      });
      win.querySelector('#files-save').onclick = async () => {
        const p = win.querySelector('#files-path').value;
        const content = win.querySelector('#files-editor').value;
        await fetch(`${ADMIN_OS}/files/write?path=${encodeURIComponent(p)}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content, create: true }),
        });
        announce('File saved');
      };
      win.querySelector('#files-mkdir').onclick = async () => {
        const name = prompt('Folder name (relative to current path):');
        if (!name) return;
        const p = currentPath ? `${currentPath}/${name}` : name;
        await fetch(`${ADMIN_OS}/files/mkdir?path=${encodeURIComponent(p)}`, { method: 'POST' });
        win.querySelector('#files-refresh').click();
      };
      win.querySelector('#files-delete').onclick = async () => {
        const p = win.querySelector('#files-path').value;
        if (!p || !confirm(`Delete ${p}?`)) return;
        await fetch(`${ADMIN_OS}/files?path=${encodeURIComponent(p)}`, { method: 'DELETE' });
        currentPath = '';
        win.querySelector('#files-refresh').click();
      };
    };
    try {
      win.querySelector('.window-body').innerHTML = await render();
      bind();
    } catch (e) {
      win.querySelector('.window-body').innerHTML = `<p>${e.message}</p>`;
    }
  }

  async function showBackups() {
    try {
      const data = await fetchJson(`${ADMIN_OS}/backups`);
      const rows = (data.backups || [])
        .map((b) => `<tr><td>${b.created_at}</td><td>${b.trigger}</td><td>${b.size_bytes}</td><td>${b.path}</td></tr>`)
        .join('');
      openAppWindow(
        'win-backups',
        'Backups',
        `<p>Auto: every <strong>${data.config.auto_backup_hours}h</strong> (${data.config.auto_backup_enabled ? 'on' : 'off'})</p>
         <button type="button" id="btn-backup-run">Run backup now</button>
         <table class="admin-table"><thead><tr><th>When</th><th>Trigger</th><th>Size</th><th>Path</th></tr></thead><tbody>${rows}</tbody></table>`
      );
      document.getElementById('btn-backup-run')?.addEventListener('click', async () => {
        await fetch(`${ADMIN_OS}/backups/run`, { method: 'POST' });
        announce('Backup completed');
        showBackups();
      });
    } catch (e) {
      openAppWindow('win-backups', 'Backups', `<p>${e.message}</p>`);
    }
  }

  async function showSystem() {
    try {
      const data = await fetchJson(`${ADMIN_OS}/system`);
      openAppWindow(
        'win-system',
        'System Viewer',
        `<pre style="font-size:11px;overflow:auto;max-height:400px">${JSON.stringify(data, null, 2)}</pre>`
      );
    } catch (e) {
      openAppWindow('win-system', 'System Viewer', `<p>${e.message}</p>`);
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
      tbody.innerHTML = (data.events || [])
        .map(
          (e) =>
            `<tr><td>${new Date((e.timestamp || 0) * 1000).toLocaleTimeString()}</td><td>${e.event_type}</td><td>${e.actor || '—'}</td><td>${e.outcome}</td></tr>`
        )
        .join('');
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
            `<tr><td>${e.pid || ''}</td><td>${e.location || ''}</td><td>${e.lead_ai || ''}</td></tr>`
        )
        .join('');
      openAppWindow(
        'win-entities',
        'Entity Registry',
        `<p>${data.total || 0} entities. Full editor on <a href="index.html#infinity-admin">dashboard</a>.</p>
         <table style="width:100%;font-size:12px;border-collapse:collapse" role="table" aria-label="Entities preview">
           <thead><tr><th scope="col">PID</th><th scope="col">Location</th><th scope="col">Lead AI</th></tr></thead>
           <tbody>${rows || '<tr><td colspan="3">No data</td></tr>'}</tbody>
         </table>`
      );
    } catch (e) {
      openAppWindow('win-entities', 'Entity Registry', `<p>Cannot reach Admin API: ${e.message}</p>`);
    }
  }

  async function showAdaptive() {
    try {
      const data = await fetchJson(`${API_BASE}/adaptive/status`);
      openAppWindow(
        'win-adaptive',
        'Adaptive AI Rotation',
        `<pre style="font-size:11px;overflow:auto;max-height:320px">${JSON.stringify(data, null, 2)}</pre>
         <p><button type="button" id="btn-proactive-run">Run proactive check now</button></p>`
      );
      document.getElementById('btn-proactive-run')?.addEventListener('click', async () => {
        await fetch(`${API_BASE}/adaptive/proactive/run`, { method: 'POST' });
        announce('Proactive run triggered');
        showAdaptive();
      });
    } catch (e) {
      openAppWindow('win-adaptive', 'Adaptive AI', `<p>${e.message}</p>`);
    }
  }

  async function showOrchestrators() {
    try {
      const data = await fetchJson(`${ADMIN_URL}/admin/orchestrators`);
      const list = (data.orchestrators || [])
        .map((o) => `<li><strong>${o.name}</strong> <span style="color:var(--os-muted)">(${o.id})</span></li>`)
        .join('');
      openAppWindow(
        'win-orch',
        'Tier 1 Orchestrators',
        `<ul>${list}</ul><p>Rename via PATCH /admin/orchestrators/{id}</p>`
      );
    } catch (e) {
      openAppWindow('win-orch', 'Orchestrators', `<p>${e.message}</p>`);
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
