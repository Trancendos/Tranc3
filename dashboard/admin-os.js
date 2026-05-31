/**
 * Infinity Admin OS — shell logic (ARIA-aware, zero-cost APIs)
 */
(function () {
  'use strict';

  const API_BASE = window.API_BASE || `${location.protocol}//${location.hostname}:8000`;
  const ADMIN_URL = window.ADMIN_URL || `${location.protocol}//${location.hostname}:8044`;

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

  async function showEntities() {
    try {
      const data = await fetchJson(`${ADMIN_URL}/admin/entities`);
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
        if (app === 'entities') showEntities();
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
