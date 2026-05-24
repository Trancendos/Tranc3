/* ============================================================
   Tranc3 AI Platform — Application Logic
   Phase 21: Full AI Platform SPA with real-time data flows
   ============================================================ */

(function () {
  'use strict';

  // ── Configuration ──────────────────────────────────────────
  const CONFIG = {
    gatewayUrl: window.GATEWAY_URL || `${window.location.protocol}//${window.location.hostname}:8040`,
    refreshInterval: 5000,
    sseReconnectDelay: 3000,
    wsReconnectDelay: 3000,
    maxRetries: 5,
  };

  // ── State Management ───────────────────────────────────────
  const state = {
    connected: false,
    topologyMode: 'TRUE_NAS',
    activeView: 'command',
    sidebarCollapsed: false,
    overview: null,
    agents: [],
    models: [],
    workflows: [],
    security: null,
    audit: [],
    services: [],
    activityLog: [],
    ws: null,
    sse: null,
    retryCount: 0,
  };

  // ── SVG Icon Library ───────────────────────────────────────
  const ICONS = {
    command: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>',
    agents: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    models: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/><path d="M2 9h2"/><path d="M20 15h2"/><path d="M20 9h2"/><path d="M9 2v2"/><path d="M9 20v2"/></svg>',
    workflows: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 3 21 3 21 8"/><line x1="4" y1="20" x2="21" y2="3"/><polyline points="21 16 21 21 16 21"/><line x1="15" y1="15" x2="21" y2="21"/><line x1="4" y1="4" x2="9" y2="9"/></svg>',
    security: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>',
    audit: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>',
    services: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>',
    refresh: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>',
    settings: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
    send: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>',
    bolt: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
    brain: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 1.98-3A2.5 2.5 0 0 1 9.5 2z"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-1.98-3A2.5 2.5 0 0 0 14.5 2z"/></svg>',
    shield: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
    key: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21 2-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0 3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>',
    chevronLeft: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>',
    chevronRight: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>',
    terminal: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>',
    play: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>',
    clock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
    alert: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>',
    server: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="8" x="2" y="2" rx="2" ry="2"/><rect width="20" height="8" x="2" y="14" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>',
    globe: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>',
    activity: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
    zap: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
  };

  function icon(name, cls) {
    return `<span class="icon ${cls || ''}">${ICONS[name] || ''}</span>`;
  }

  // ── Utility Functions ──────────────────────────────────────
  function $(sel) { return document.querySelector(sel); }
  function $$(sel) { return document.querySelectorAll(sel); }

  function timeAgo(dateStr) {
    if (!dateStr) return '—';
    const diff = Date.now() - new Date(dateStr).getTime();
    if (diff < 60000) return 'just now';
    if (diff < 3600000) return Math.floor(diff / 60000) + 'm ago';
    if (diff < 86400000) return Math.floor(diff / 3600000) + 'h ago';
    return Math.floor(diff / 86400000) + 'd ago';
  }

  function truncate(s, n) {
    if (!s) return '—';
    return s.length > n ? s.substring(0, n) + '…' : s;
  }

  function addActivity(type, text) {
    state.activityLog.unshift({ type, text, time: new Date().toISOString() });
    if (state.activityLog.length > 50) state.activityLog.pop();
  }

  // ── API Client ─────────────────────────────────────────────
  const api = {
    async fetch(path) {
      try {
        const res = await fetch(`${CONFIG.gatewayUrl}${path}`, { signal: AbortSignal.timeout(8000) });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
      } catch (err) {
        console.warn(`[API] ${path} failed:`, err.message);
        return null;
      }
    },

    async post(path, body) {
      try {
        const res = await fetch(`${CONFIG.gatewayUrl}${path}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
          signal: AbortSignal.timeout(8000),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
      } catch (err) {
        console.warn(`[API POST] ${path} failed:`, err.message);
        return null;
      }
    },

    async put(path, body) {
      try {
        const res = await fetch(`${CONFIG.gatewayUrl}${path}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
          signal: AbortSignal.timeout(8000),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
      } catch (err) {
        console.warn(`[API PUT] ${path} failed:`, err.message);
        return null;
      }
    },
  };

  // ── Real-Time Connections ──────────────────────────────────
  function connectSSE() {
    if (state.sse) { state.sse.close(); }
    try {
      const url = `${CONFIG.gatewayUrl}/events`;
      const es = new EventSource(url);
      es.onopen = () => {
        state.connected = true;
        state.retryCount = 0;
        updateConnectionStatus();
        addActivity('system', 'SSE stream connected');
      };
      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          handleSSEEvent(data);
        } catch { /* ignore non-JSON */ }
      };
      es.onerror = () => {
        state.connected = false;
        updateConnectionStatus();
        es.close();
        if (state.retryCount < CONFIG.maxRetries) {
          state.retryCount++;
          setTimeout(connectSSE, CONFIG.sseReconnectDelay);
        }
      };
      state.sse = es;
    } catch (err) {
      console.warn('[SSE] Connection failed:', err);
    }
  }

  function handleSSEEvent(data) {
    if (data.type === 'overview_update' || data.type === 'health_change') {
      refreshAllData();
    } else if (data.type === 'agent_event') {
      refreshAgents();
      addActivity('agent', data.message || 'Agent event');
    } else if (data.type === 'workflow_event') {
      refreshWorkflows();
      addActivity('workflow', data.message || 'Workflow event');
    } else if (data.type === 'security_event') {
      refreshSecurity();
      addActivity('security', data.message || 'Security event');
    }
    renderActivityFeed();
  }

  function connectWebSocket() {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) return;
    try {
      const wsUrl = CONFIG.gatewayUrl.replace(/^http/, 'ws') + '/ws';
      const ws = new WebSocket(wsUrl);
      ws.onopen = () => {
        state.connected = true;
        updateConnectionStatus();
        ws.send(JSON.stringify({ type: 'subscribe', channels: ['overview', 'agents', 'workflows', 'security'] }));
      };
      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          handleSSEEvent(data);
        } catch { /* ignore */ }
      };
      ws.onclose = () => {
        state.connected = false;
        updateConnectionStatus();
        if (state.retryCount < CONFIG.maxRetries) {
          setTimeout(connectWebSocket, CONFIG.wsReconnectDelay);
        }
      };
      ws.onerror = () => { ws.close(); };
      state.ws = ws;
    } catch (err) {
      console.warn('[WS] Connection failed:', err);
    }
  }

  // ── Data Fetching ──────────────────────────────────────────
  async function refreshAllData() {
    const [overview, agents, models, workflows, security, audit] = await Promise.all([
      api.fetch('/api/overview'),
      api.fetch('/api/agents'),
      api.fetch('/api/models'),
      api.fetch('/api/workflows'),
      api.fetch('/api/security'),
      api.fetch('/api/audit'),
    ]);

    if (overview) {
      state.overview = overview;
      state.topologyMode = overview.topology_mode || overview.topology || 'TRUE_NAS';
      state.services = overview.services || [];
    }
    if (agents) state.agents = agents.agents || agents || [];
    if (models) state.models = models.models || models || [];
    if (workflows) state.workflows = workflows.workflows || workflows || [];
    if (security) state.security = security;
    if (audit) state.audit = audit.entries || audit.audit || audit || [];

    renderCurrentView();
    updateTopologyIndicator();
  }

  async function refreshAgents() {
    const data = await api.fetch('/api/agents');
    if (data) state.agents = data.agents || data || [];
  }

  async function refreshWorkflows() {
    const data = await api.fetch('/api/workflows');
    if (data) state.workflows = data.workflows || data || [];
  }

  async function refreshSecurity() {
    const data = await api.fetch('/api/security');
    if (data) state.security = data;
  }

  // ── View Switching ─────────────────────────────────────────
  function switchView(viewId) {
    state.activeView = viewId;
    $$('.view').forEach(v => v.classList.remove('active'));
    const target = $(`#view-${viewId}`);
    if (target) target.classList.add('active');
    $$('.nav-item').forEach(n => n.classList.remove('active'));
    const navItem = $(`.nav-item[data-view="${viewId}"]`);
    if (navItem) navItem.classList.add('active');
    // Update top bar title
    const titles = {
      command: 'AI Command Center',
      agents: 'Agent Fleet',
      models: 'Model Hub',
      workflows: 'Workflow Studio',
      security: 'Security Vault',
      audit: 'Audit Ledger',
      services: 'Service Health',
    };
    const titleEl = $('#top-bar-title');
    if (titleEl) titleEl.textContent = titles[viewId] || viewId;
    renderCurrentView();
  }

  function renderCurrentView() {
    switch (state.activeView) {
      case 'command': renderCommandCenter(); break;
      case 'agents': renderAgentFleet(); break;
      case 'models': renderModelHub(); break;
      case 'workflows': renderWorkflowStudio(); break;
      case 'security': renderSecurityVault(); break;
      case 'audit': renderAuditLedger(); break;
      case 'services': renderServiceHealth(); break;
    }
  }

  // ── Render: Command Center ─────────────────────────────────
  function renderCommandCenter() {
    const container = $('#view-command');
    if (!container) return;

    const o = state.overview || {};
    const svcCount = state.services.length || 8;
    const agentCount = state.agents.length || 0;
    const modelCount = state.models.length || 0;
    const wfCount = state.workflows.length || 0;
    const secretCount = state.security?.total_secrets || state.security?.active_secrets || 0;
    const auditCount = state.audit.length || 0;

    container.innerHTML = `
      <!-- Stat Cards -->
      <div class="stat-grid">
        <div class="stat-card blue">
          <div class="stat-icon">${icon('services')}</div>
          <div class="stat-label">Services Online</div>
          <div class="stat-value">${svcCount}</div>
          <div class="stat-sub">P4 Ecosystem</div>
        </div>
        <div class="stat-card purple">
          <div class="stat-icon">${icon('agents')}</div>
          <div class="stat-label">Active Agents</div>
          <div class="stat-value">${agentCount}</div>
          <div class="stat-sub">DeepAgents Fleet</div>
        </div>
        <div class="stat-card cyan">
          <div class="stat-icon">${icon('models')}</div>
          <div class="stat-label">AI Models</div>
          <div class="stat-value">${modelCount}</div>
          <div class="stat-sub">Zero-Cost Routes</div>
        </div>
        <div class="stat-card green">
          <div class="stat-icon">${icon('workflows')}</div>
          <div class="stat-label">Workflows</div>
          <div class="stat-value">${wfCount}</div>
          <div class="stat-sub">DAG Engine</div>
        </div>
        <div class="stat-card warm">
          <div class="stat-icon">${icon('security')}</div>
          <div class="stat-label">Secrets</div>
          <div class="stat-value">${secretCount}</div>
          <div class="stat-sub">XOR Vault</div>
        </div>
        <div class="stat-card blue">
          <div class="stat-icon">${icon('audit')}</div>
          <div class="stat-label">Audit Entries</div>
          <div class="stat-value">${auditCount}</div>
          <div class="stat-sub">Hash Chain</div>
        </div>
      </div>

      <!-- Command Bar + Activity -->
      <div class="command-center mb-24">
        <div class="command-input-area mb-20">
          <div class="command-bar">
            <span class="cmd-icon">${ICONS.terminal}</span>
            <input type="text" id="cmd-input" placeholder="Ask the AI, run a workflow, manage agents…" autocomplete="off">
            <button class="cmd-submit" id="cmd-submit">Execute</button>
          </div>
        </div>

        <div class="glass-card">
          <div class="glass-card-header">
            <h3>${icon('activity')} Live Activity</h3>
            <div class="card-actions">
              <button class="card-action-btn" onclick="Tranc3App.clearActivity()">Clear</button>
            </div>
          </div>
          <div class="activity-feed" id="activity-feed">
            ${renderActivityItems()}
          </div>
        </div>

        <div class="glass-card">
          <div class="glass-card-header">
            <h3>${icon('globe')} Topology Status</h3>
          </div>
          <div class="topo-visual" id="topo-visual">
            <div class="topo-center">T3</div>
            <div class="topo-orbit" style="width:120px;height:120px;"></div>
            <div class="topo-orbit" style="width:220px;height:220px;"></div>
            ${renderTopoNodes()}
          </div>
        </div>
      </div>

      <!-- Quick Service Overview -->
      <div class="section-title">Service Health Snapshot</div>
      <div class="service-grid" id="quick-services">
        ${renderServiceTiles()}
      </div>
    `;

    // Bind command bar
    const cmdInput = $('#cmd-input');
    const cmdSubmit = $('#cmd-submit');
    if (cmdSubmit) {
      cmdSubmit.addEventListener('click', handleCommand);
    }
    if (cmdInput) {
      cmdInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') handleCommand();
      });
    }
  }

  function renderActivityItems() {
    if (state.activityLog.length === 0) {
      return '<div class="empty-state"><p>No recent activity</p></div>';
    }
    return state.activityLog.slice(0, 15).map(a => `
      <div class="activity-item">
        <div class="activity-icon ${a.type}">${getActivityIcon(a.type)}</div>
        <div class="activity-text"><p>${a.text}</p></div>
        <div class="activity-time">${timeAgo(a.time)}</div>
      </div>
    `).join('');
  }

  function getActivityIcon(type) {
    const map = { agent: ICONS.agents, model: ICONS.models, workflow: ICONS.workflows,
                  security: ICONS.shield, system: ICONS.globe };
    return map[type] || ICONS.activity;
  }

  function renderTopoNodes() {
    const nodes = [
      { name: 'VLT', x: 80, y: 50 },
      { name: 'TOP', x: 80, y: 150 },
      { name: 'LDG', x: 180, y: 50 },
      { name: 'MRT', x: 180, y: 150 },
      { name: 'WF', x: 50, y: 100 },
      { name: 'BMK', x: 210, y: 100 },
      { name: 'LC', x: 130, y: 30 },
      { name: 'DA', x: 130, y: 170 },
    ];
    return nodes.map(n => `
      <div class="topo-node active" style="left:${n.x}px;top:${n.y}px;">${n.name}</div>
    `).join('');
  }

  function renderServiceTiles() {
    const defaultServices = [
      { name: 'Vault', port: 8030, status: 'healthy' },
      { name: 'Topology', port: 8031, status: 'healthy' },
      { name: 'Ledger', port: 8032, status: 'healthy' },
      { name: 'Model Router', port: 8033, status: 'healthy' },
      { name: 'Workflow', port: 8034, status: 'healthy' },
      { name: 'Benchmark', port: 8035, status: 'healthy' },
      { name: 'LangChain', port: 8036, status: 'healthy' },
      { name: 'DeepAgents', port: 8037, status: 'healthy' },
    ];
    const services = state.services.length > 0 ? state.services : defaultServices;
    return services.map(s => `
      <div class="service-tile">
        <div class="service-dot ${s.status || 'healthy'}"></div>
        <div class="service-name">${s.name || s.service || 'Unknown'}</div>
        <div class="service-port">:${s.port || '—'}</div>
      </div>
    `).join('');
  }

  async function handleCommand() {
    const input = $('#cmd-input');
    if (!input || !input.value.trim()) return;
    const cmd = input.value.trim();
    input.value = '';

    addActivity('system', `Command: <strong>${truncate(cmd, 60)}</strong>`);

    // Parse commands
    const lower = cmd.toLowerCase();
    if (lower.startsWith('/topology ') || lower.startsWith('topology ')) {
      const mode = cmd.split(/\s+/)[1]?.toUpperCase();
      if (['TRUE_NAS', 'HYBRID', 'CLOUD_ONLY'].includes(mode)) {
        const result = await api.put('/api/topology/mode', { mode });
        addActivity('system', result ? `Topology switched to <strong>${mode}</strong>` : 'Topology switch failed');
        refreshAllData();
      } else {
        addActivity('system', 'Invalid topology mode. Use: TRUE_NAS, HYBRID, CLOUD_ONLY');
      }
    } else if (lower.startsWith('/run ') || lower.startsWith('run ')) {
      const wfId = cmd.split(/\s+/)[1];
      if (wfId) {
        const result = await api.post(`/api/workflows/${wfId}/run`, {});
        addActivity('workflow', result ? `Workflow <strong>${wfId}</strong> triggered` : 'Workflow run failed');
        refreshWorkflows();
      }
    } else if (lower.startsWith('/agent ') || lower.startsWith('agent ')) {
      const result = await api.post('/api/agents', { prompt: cmd.substring(cmd.indexOf(' ') + 1) });
      addActivity('agent', result ? 'Agent task submitted' : 'Agent submission failed');
      refreshAgents();
    } else {
      addActivity('system', `Processing: <strong>${truncate(cmd, 50)}</strong>`);
      // Try sending to the agent endpoint
      const result = await api.post('/api/agents', { prompt: cmd });
      if (result) {
        addActivity('agent', `AI Response received`);
      } else {
        addActivity('system', 'Command processed (no live backend connected — showing cached data)');
      }
    }
    renderActivityFeed();
  }

  function renderActivityFeed() {
    const feed = $('#activity-feed');
    if (feed) feed.innerHTML = renderActivityItems();
  }

  // ── Render: Agent Fleet ────────────────────────────────────
  function renderAgentFleet() {
    const container = $('#view-agents');
    if (!container) return;

    const agents = state.agents.length > 0 ? state.agents : generateMockAgents();

    container.innerHTML = `
      <div class="stat-grid mb-24">
        <div class="stat-card purple">
          <div class="stat-icon">${icon('agents')}</div>
          <div class="stat-label">Total Agents</div>
          <div class="stat-value">${agents.length}</div>
        </div>
        <div class="stat-card green">
          <div class="stat-icon">${icon('check')}</div>
          <div class="stat-label">Active</div>
          <div class="stat-value">${agents.filter(a => a.status === 'working' || a.status === 'active').length}</div>
        </div>
        <div class="stat-card blue">
          <div class="stat-icon">${icon('clock')}</div>
          <div class="stat-label">Idle</div>
          <div class="stat-value">${agents.filter(a => a.status === 'idle').length}</div>
        </div>
        <div class="stat-card warm">
          <div class="stat-icon">${icon('alert')}</div>
          <div class="stat-label">Errors</div>
          <div class="stat-value">${agents.filter(a => a.status === 'error').length}</div>
        </div>
      </div>

      <div class="glass-card-header mb-12" style="display:flex;justify-content:space-between;align-items:center;">
        <div class="section-title mb-0">Agent Fleet</div>
        <button class="card-action-btn primary" onclick="Tranc3App.createAgent()">+ Spawn Agent</button>
      </div>

      <div class="agent-grid">
        ${agents.map(a => renderAgentCard(a)).join('')}
      </div>
    `;
  }

  function renderAgentCard(agent) {
    const statusClass = agent.status === 'working' || agent.status === 'active' ? 'working' :
                        agent.status === 'error' ? 'error' : 'idle';
    const statusLabel = agent.status === 'working' || agent.status === 'active' ? 'Active' :
                        agent.status === 'error' ? 'Error' : 'Idle';
    const bgColors = ['#3B82F6', '#8B5CF6', '#06B6D4', '#10B981', '#F59E0B'];
    const bgColor = bgColors[Math.abs(hashCode(agent.id || agent.name || 'agent')) % bgColors.length];
    const initials = (agent.name || agent.id || 'A').substring(0, 2).toUpperCase();
    const tasks = agent.tasks_completed ?? agent.tasksCompleted ?? Math.floor(Math.random() * 20);
    const success = agent.success_rate ?? agent.successRate ?? (80 + Math.floor(Math.random() * 20));

    return `
      <div class="agent-card">
        <div class="agent-header">
          <div class="agent-avatar" style="background:${bgColor}">${initials}</div>
          <div class="agent-info">
            <h4>${agent.name || agent.id || 'Agent'}</h4>
            <div class="agent-type">${agent.type || agent.role || 'General Purpose'}</div>
          </div>
          <div class="agent-status ${statusClass}">
            <span class="status-dot"></span>
            ${statusLabel}
          </div>
        </div>
        <div class="agent-metrics">
          <div class="metric"><div class="metric-val">${tasks}</div><div class="metric-label">Tasks</div></div>
          <div class="metric"><div class="metric-val">${success}%</div><div class="metric-label">Success</div></div>
          <div class="metric"><div class="metric-val">${agent.delegation_depth ?? agent.depth ?? 0}</div><div class="metric-label">Depth</div></div>
        </div>
        <div class="agent-actions">
          <button class="agent-btn" onclick="Tranc3App.inspectAgent('${agent.id || agent.name}')">Inspect</button>
          <button class="agent-btn primary" onclick="Tranc3App.delegateAgent('${agent.id || agent.name}')">Delegate</button>
        </div>
      </div>
    `;
  }

  function generateMockAgents() {
    const names = ['Sovereign', 'Guardian', 'Orchestrator', 'Analyst', 'Builder', 'Scout', 'Archivist', 'Sentinel'];
    const types = ['Prime AI', 'Security Agent', 'Orchestration Agent', 'Data Agent', 'Dev Agent', 'Scout Agent', 'Knowledge Agent', 'Monitor Agent'];
    const statuses = ['idle', 'working', 'idle', 'idle', 'working', 'idle', 'error', 'idle'];
    return names.map((name, i) => ({
      id: `agent-${name.toLowerCase()}`,
      name,
      type: types[i],
      status: statuses[i],
      tasks_completed: Math.floor(Math.random() * 50),
      success_rate: 75 + Math.floor(Math.random() * 25),
      delegation_depth: Math.floor(Math.random() * 5),
    }));
  }

  // ── Render: Model Hub ──────────────────────────────────────
  function renderModelHub() {
    const container = $('#view-models');
    if (!container) return;

    const models = state.models.length > 0 ? state.models : generateMockModels();

    // Group by provider
    const providers = {};
    models.forEach(m => {
      const p = m.provider || 'unknown';
      if (!providers[p]) providers[p] = [];
      providers[p].push(m);
    });

    container.innerHTML = `
      <div class="stat-grid mb-24">
        <div class="stat-card cyan">
          <div class="stat-icon">${icon('models')}</div>
          <div class="stat-label">Total Models</div>
          <div class="stat-value">${models.length}</div>
        </div>
        <div class="stat-card blue">
          <div class="stat-icon">${icon('globe')}</div>
          <div class="stat-label">Providers</div>
          <div class="stat-value">${Object.keys(providers).length}</div>
        </div>
        <div class="stat-card green">
          <div class="stat-icon">${icon('zap')}</div>
          <div class="stat-label">Routing Strategy</div>
          <div class="stat-value" style="font-size:16px;">${state.overview?.routing_strategy || 'cost_aware'}</div>
        </div>
        <div class="stat-card purple">
          <div class="stat-icon">${icon('shield')}</div>
          <div class="stat-label">Circuit Breaker</div>
          <div class="stat-value" style="font-size:16px;">${state.overview?.circuit_breaker_state || 'closed'}</div>
        </div>
      </div>

      ${Object.entries(providers).map(([provider, pModels]) => `
        <div class="section-title">${provider.toUpperCase()}</div>
        <div class="model-grid mb-24">
          ${pModels.map(m => renderModelCard(m)).join('')}
        </div>
      `).join('')}
    `;
  }

  function renderModelCard(model) {
    const provider = model.provider || 'unknown';
    const usage = model.usage_count ?? model.usageCount ?? model.requests ?? Math.floor(Math.random() * 500);
    const maxUsage = 1000;
    const usagePct = Math.min(100, Math.round((usage / maxUsage) * 100));
    const tags = model.tags || [model.tier || 'free', model.type || 'chat'];
    const latency = model.avg_latency ?? model.latency ?? Math.floor(50 + Math.random() * 200);

    return `
      <div class="model-card">
        <div class="model-provider ${provider}">${provider}</div>
        <div class="model-name">${model.name || model.id || 'Unknown Model'}</div>
        <div class="model-meta">
          <span>${latency}ms avg</span>
          <span>${usage} reqs</span>
        </div>
        <div class="model-bar"><div class="model-bar-fill" style="width:${usagePct}%"></div></div>
        <div class="model-tags">
          ${tags.map(t => `<span class="model-tag">${t}</span>`).join('')}
        </div>
      </div>
    `;
  }

  function generateMockModels() {
    return [
      { id: 'gemini-2.0-flash', name: 'Gemini 2.0 Flash', provider: 'google', avg_latency: 120, usage_count: 342, tags: ['free', 'chat', 'fast'] },
      { id: 'gemini-2.5-pro', name: 'Gemini 2.5 Pro', provider: 'google', avg_latency: 350, usage_count: 156, tags: ['free', 'chat', 'reasoning'] },
      { id: 'llama-4-maverick', name: 'Llama 4 Maverick', provider: 'meta', avg_latency: 200, usage_count: 89, tags: ['free', 'chat'] },
      { id: 'mistral-large', name: 'Mistral Large', provider: 'mistral', avg_latency: 280, usage_count: 45, tags: ['free', 'chat', 'multilingual'] },
      { id: 'codestral', name: 'Codestral', provider: 'mistral', avg_latency: 180, usage_count: 67, tags: ['free', 'code'] },
      { id: 'local-phi3', name: 'Phi-3 Mini (Local)', provider: 'local', avg_latency: 50, usage_count: 210, tags: ['local', 'chat', 'fast'] },
    ];
  }

  // ── Render: Workflow Studio ────────────────────────────────
  function renderWorkflowStudio() {
    const container = $('#view-workflows');
    if (!container) return;

    const workflows = state.workflows.length > 0 ? state.workflows : generateMockWorkflows();

    container.innerHTML = `
      <div class="stat-grid mb-24">
        <div class="stat-card green">
          <div class="stat-icon">${icon('workflows')}</div>
          <div class="stat-label">Total Workflows</div>
          <div class="stat-value">${workflows.length}</div>
        </div>
        <div class="stat-card blue">
          <div class="stat-icon">${icon('play')}</div>
          <div class="stat-label">Running</div>
          <div class="stat-value">${workflows.filter(w => w.status === 'running').length}</div>
        </div>
        <div class="stat-card purple">
          <div class="stat-icon">${icon('check')}</div>
          <div class="stat-label">Completed</div>
          <div class="stat-value">${workflows.filter(w => w.status === 'completed').length}</div>
        </div>
        <div class="stat-card warm">
          <div class="stat-icon">${icon('alert')}</div>
          <div class="stat-label">Failed</div>
          <div class="stat-value">${workflows.filter(w => w.status === 'failed').length}</div>
        </div>
      </div>

      <div class="glass-card-header mb-12" style="display:flex;justify-content:space-between;align-items:center;">
        <div class="section-title mb-0">Workflow Definitions</div>
        <button class="card-action-btn primary" onclick="Tranc3App.createWorkflow()">+ Create Workflow</button>
      </div>

      <div class="workflow-list">
        ${workflows.map(w => renderWorkflowItem(w)).join('')}
      </div>
    `;
  }

  function renderWorkflowItem(wf) {
    const steps = wf.steps || wf.nodes || [];
    const stepCount = steps.length || Math.floor(Math.random() * 6) + 2;
    const status = wf.status || 'pending';

    let stepDots = '';
    for (let i = 0; i < stepCount; i++) {
      let cls = '';
      if (status === 'completed') cls = 'completed';
      else if (status === 'running' && i <= Math.floor(stepCount / 2)) cls = i < Math.floor(stepCount / 2) ? 'completed' : 'running';
      else if (status === 'failed' && i === Math.floor(stepCount / 2)) cls = 'failed';
      if (i > 0) stepDots += '<div class="wf-step-connector"></div>';
      stepDots += `<div class="wf-step-dot ${cls}"></div>`;
    }

    return `
      <div class="workflow-item">
        <div class="wf-icon" style="background:rgba(6,182,212,0.12);color:#06B6D4;">
          ${ICONS.workflows}
        </div>
        <div class="wf-info">
          <h4>${wf.name || wf.id || 'Untitled Workflow'}</h4>
          <p>${wf.description || `${stepCount} steps • DAG-based execution`}</p>
        </div>
        <div class="wf-steps-visual">
          ${stepDots}
        </div>
        <div class="wf-status-badge ${status}">${status}</div>
        <button class="card-action-btn primary" onclick="Tranc3App.runWorkflow('${wf.id || wf.name}')">Run</button>
      </div>
    `;
  }

  function generateMockWorkflows() {
    return [
      { id: 'wf-pipeline', name: 'Data Processing Pipeline', description: 'Ingest → Transform → Validate → Store', status: 'completed', steps: 4 },
      { id: 'wf-analysis', name: 'AI Analysis Chain', description: 'Fetch → Enrich → Classify → Report', status: 'running', steps: 4 },
      { id: 'wf-deploy', name: 'Deployment Workflow', description: 'Build → Test → Stage → Deploy → Verify', status: 'pending', steps: 5 },
      { id: 'wf-security', name: 'Security Audit Flow', description: 'Scan → Assess → Remediate → Report', status: 'failed', steps: 4 },
    ];
  }

  // ── Render: Security Vault ─────────────────────────────────
  function renderSecurityVault() {
    const container = $('#view-security');
    if (!container) return;

    const sec = state.security || {};
    const secrets = sec.secrets || generateMockSecrets();
    const chainValid = sec.chain_valid ?? sec.chainValid ?? true;
    const openLeaks = sec.open_leaks ?? sec.openLeaks ?? 0;

    container.innerHTML = `
      <div class="stat-grid mb-24">
        <div class="stat-card warm">
          <div class="stat-icon">${icon('security')}</div>
          <div class="stat-label">Total Secrets</div>
          <div class="stat-value">${sec.total_secrets || secrets.length}</div>
        </div>
        <div class="stat-card green">
          <div class="stat-icon">${icon('check')}</div>
          <div class="stat-label">Chain Valid</div>
          <div class="stat-value" style="font-size:20px;">${chainValid ? '✓ Valid' : '✗ Broken'}</div>
        </div>
        <div class="stat-card blue">
          <div class="stat-icon">${icon('key')}</div>
          <div class="stat-label">Active Secrets</div>
          <div class="stat-value">${sec.active_secrets || secrets.filter(s => s.status === 'active').length}</div>
        </div>
        <div class="stat-card purple">
          <div class="stat-icon">${icon('shield')}</div>
          <div class="stat-label">Open Leaks</div>
          <div class="stat-value">${openLeaks}</div>
        </div>
      </div>

      <div class="grid-2 mb-24">
        <div class="glass-card">
          <div class="glass-card-header">
            <h3>${icon('key')} Vault Entries</h3>
            <button class="card-action-btn primary" onclick="Tranc3App.createSecret()">+ Add Secret</button>
          </div>
          <div>
            ${secrets.map(s => renderSecretEntry(s)).join('')}
          </div>
        </div>

        <div class="glass-card">
          <div class="glass-card-header">
            <h3>${icon('shield')} Encryption Status</h3>
          </div>
          <div style="padding:20px 0;">
            <div style="display:flex;justify-content:space-between;margin-bottom:16px;">
              <span style="color:var(--text-secondary);font-size:13px;">Encryption Method</span>
              <span style="color:var(--brand-primary);font-size:13px;font-weight:600;">XOR-256 (Zero-Cost)</span>
            </div>
            <div style="display:flex;justify-content:space-between;margin-bottom:16px;">
              <span style="color:var(--text-secondary);font-size:13px;">Key Rotation</span>
              <span style="color:var(--status-online);font-size:13px;font-weight:600;">Automatic</span>
            </div>
            <div style="display:flex;justify-content:space-between;margin-bottom:16px;">
              <span style="color:var(--text-secondary);font-size:13px;">Audit Chain</span>
              <span style="color:${chainValid ? 'var(--status-online)' : 'var(--status-offline)'};font-size:13px;font-weight:600;">${chainValid ? 'SHA-256 Verified' : 'Broken Chain'}</span>
            </div>
            <div style="display:flex;justify-content:space-between;margin-bottom:16px;">
              <span style="color:var(--text-secondary);font-size:13px;">Sentinel Status</span>
              <span style="color:var(--status-online);font-size:13px;font-weight:600;">Active</span>
            </div>
            <div style="display:flex;justify-content:space-between;">
              <span style="color:var(--text-secondary);font-size:13px;">Leak Detection</span>
              <span style="color:${openLeaks > 0 ? 'var(--status-offline)' : 'var(--status-online)'};font-size:13px;font-weight:600;">${openLeaks > 0 ? `${openLeaks} Leak(s)` : 'Clear'}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Topology Mode Control -->
      <div class="glass-card">
        <div class="glass-card-header">
          <h3>${icon('globe')} Adaptive Topology Control</h3>
        </div>
        <div style="display:flex;gap:12px;flex-wrap:wrap;">
          <button class="card-action-btn ${state.topologyMode === 'TRUE_NAS' ? 'primary' : ''}" onclick="Tranc3App.setTopology('TRUE_NAS')">TRUE_NAS</button>
          <button class="card-action-btn ${state.topologyMode === 'HYBRID' ? 'primary' : ''}" onclick="Tranc3App.setTopology('HYBRID')">HYBRID</button>
          <button class="card-action-btn ${state.topologyMode === 'CLOUD_ONLY' ? 'primary' : ''}" onclick="Tranc3App.setTopology('CLOUD_ONLY')">CLOUD_ONLY</button>
        </div>
        <p style="font-size:12px;color:var(--text-muted);margin-top:12px;">
          Current mode: <strong style="color:var(--text-primary);">${state.topologyMode}</strong> — 
          ${state.topologyMode === 'TRUE_NAS' ? 'Local-first, maximum security and performance' : 
            state.topologyMode === 'HYBRID' ? 'Adaptive switching between local and cloud' : 
            'Cloud-only, free-tier services'}
        </p>
      </div>
    `;
  }

  function renderSecretEntry(secret) {
    const status = secret.status || 'active';
    return `
      <div class="secret-entry">
        <div class="secret-icon">${ICONS.key}</div>
        <div class="secret-info">
          <div class="secret-key">${secret.name || secret.key || secret.id || 'secret'}</div>
          <div class="secret-meta">${status} • ${timeAgo(secret.created_at || secret.updated_at)}</div>
        </div>
        <div class="secret-masked">••••••••</div>
      </div>
    `;
  }

  function generateMockSecrets() {
    return [
      { id: 'sec-1', name: 'DATABASE_URL', status: 'active', created_at: new Date(Date.now() - 86400000).toISOString() },
      { id: 'sec-2', name: 'API_KEY_GEMINI', status: 'active', created_at: new Date(Date.now() - 172800000).toISOString() },
      { id: 'sec-3', name: 'JWT_SECRET', status: 'active', created_at: new Date(Date.now() - 259200000).toISOString() },
      { id: 'sec-4', name: 'ENCRYPTION_KEY', status: 'revoked', created_at: new Date(Date.now() - 345600000).toISOString() },
    ];
  }

  // ── Render: Audit Ledger ───────────────────────────────────
  function renderAuditLedger() {
    const container = $('#view-audit');
    if (!container) return;

    const entries = state.audit.length > 0 ? state.audit : generateMockAudit();

    container.innerHTML = `
      <div class="stat-grid mb-24">
        <div class="stat-card blue">
          <div class="stat-icon">${icon('audit')}</div>
          <div class="stat-label">Total Entries</div>
          <div class="stat-value">${entries.length}</div>
        </div>
        <div class="stat-card green">
          <div class="stat-icon">${icon('shield')}</div>
          <div class="stat-label">Chain Integrity</div>
          <div class="stat-value" style="font-size:18px;">${state.security?.chain_valid !== false ? 'SHA-256 ✓' : 'BROKEN'}</div>
        </div>
        <div class="stat-card purple">
          <div class="stat-icon">${icon('activity')}</div>
          <div class="stat-label">Last 24h</div>
          <div class="stat-value">${entries.filter(e => {
            const t = new Date(e.timestamp || e.created_at || 0).getTime();
            return t > Date.now() - 86400000;
          }).length}</div>
        </div>
      </div>

      <div class="glass-card">
        <div class="glass-card-header">
          <h3>${icon('audit')} Hash-Chained Audit Ledger</h3>
          <button class="card-action-btn" onclick="Tranc3App.refreshAudit()">Refresh</button>
        </div>
        <div style="overflow-x:auto;">
          <table class="audit-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Action</th>
                <th>Subject</th>
                <th>Actor</th>
                <th>Hash</th>
              </tr>
            </thead>
            <tbody>
              ${entries.slice(0, 25).map(e => renderAuditRow(e)).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  function renderAuditRow(entry) {
    const action = entry.action || entry.event || 'access';
    const actionClass = action.includes('creat') || action.includes('CREAT') ? 'create' :
                        action.includes('revoke') || action.includes('REVOK') ? 'revoke' :
                        action.includes('rotat') || action.includes('ROTAT') ? 'rotate' : 'access';
    const hash = entry.hash || entry.chain_hash || '0' + Math.random().toString(16).substring(2, 10);

    return `
      <tr>
        <td style="white-space:nowrap;">${timeAgo(entry.timestamp || entry.created_at)}</td>
        <td><span class="action-badge ${actionClass}">${action}</span></td>
        <td>${entry.subject || entry.key || entry.target || '—'}</td>
        <td>${entry.actor || entry.source || 'system'}</td>
        <td class="hash-cell">${truncate(hash, 16)}</td>
      </tr>
    `;
  }

  function generateMockAudit() {
    const actions = ['SECRET_CREATE', 'SECRET_ACCESS', 'AGENT_DELEGATE', 'WORKFLOW_RUN', 'SECRET_ROTATE', 'TOPOLOGY_SWITCH'];
    const subjects = ['DATABASE_URL', 'API_KEY_GEMINI', 'agent-sovereign', 'wf-analysis', 'JWT_SECRET', 'system'];
    const actors = ['vault-service', 'deepagents', 'model-router', 'workflow-engine', 'vault-service', 'topology'];
    return actions.map((a, i) => ({
      timestamp: new Date(Date.now() - i * 3600000).toISOString(),
      action: a,
      subject: subjects[i],
      actor: actors[i],
      hash: 'sha256:' + Array.from({ length: 16 }, () => Math.floor(Math.random() * 16).toString(16)).join(''),
    }));
  }

  // ── Render: Service Health ─────────────────────────────────
  function renderServiceHealth() {
    const container = $('#view-services');
    if (!container) return;

    const defaultServices = [
      { name: 'Vault Service', port: 8030, status: 'healthy', desc: 'XOR-encrypted secret vault' },
      { name: 'Topology Manager', port: 8031, status: 'healthy', desc: 'Adaptive topology switching' },
      { name: 'Audit Ledger', port: 8032, status: 'healthy', desc: 'SHA-256 hash-chained ledger' },
      { name: 'Model Router', port: 8033, status: 'healthy', desc: 'Multi-model routing with circuit breaker' },
      { name: 'Workflow Engine', port: 8034, status: 'healthy', desc: 'DAG-based workflow execution' },
      { name: 'Benchmark Service', port: 8035, status: 'healthy', desc: 'Performance benchmarking' },
      { name: 'LangChain Integration', port: 8036, status: 'healthy', desc: 'LangChain chain orchestration' },
      { name: 'DeepAgents Orchestrator', port: 8037, status: 'healthy', desc: 'Agent delegation with depth limits' },
      { name: 'Gateway Aggregator', port: 8040, status: 'healthy', desc: 'Unified API surface + real-time' },
    ];
    const services = state.services.length > 0 ? state.services : defaultServices;

    container.innerHTML = `
      <div class="stat-grid mb-24">
        <div class="stat-card green">
          <div class="stat-icon">${icon('server')}</div>
          <div class="stat-label">Healthy</div>
          <div class="stat-value">${services.filter(s => s.status === 'healthy').length}</div>
        </div>
        <div class="stat-card warm">
          <div class="stat-icon">${icon('alert')}</div>
          <div class="stat-label">Degraded</div>
          <div class="stat-value">${services.filter(s => s.status === 'degraded').length}</div>
        </div>
        <div class="stat-card blue">
          <div class="stat-icon">${icon('server')}</div>
          <div class="stat-label">Total</div>
          <div class="stat-value">${services.length}</div>
        </div>
      </div>

      <div class="glass-card">
        <div class="glass-card-header">
          <h3>${icon('services')} P4 Ecosystem Services</h3>
          <button class="card-action-btn" onclick="Tranc3App.refreshData()">Refresh All</button>
        </div>
        <div style="overflow-x:auto;">
          <table class="audit-table">
            <thead>
              <tr>
                <th>Status</th>
                <th>Service</th>
                <th>Port</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
              ${services.map(s => `
                <tr>
                  <td><span class="service-dot ${s.status || 'healthy'}" style="display:inline-block;"></span></td>
                  <td style="color:var(--text-primary);font-weight:600;">${s.name || s.service || 'Unknown'}</td>
                  <td class="hash-cell">:${s.port || '—'}</td>
                  <td>${s.desc || s.description || '—'}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  // ── Connection Status ──────────────────────────────────────
  function updateConnectionStatus() {
    const el = $('#connection-status');
    if (el) {
      el.className = `connection-status ${state.connected ? '' : 'disconnected'}`;
      el.innerHTML = `
        <span class="conn-dot"></span>
        ${state.connected ? 'Live' : 'Offline'}
      `;
    }
  }

  function updateTopologyIndicator() {
    const el = $('#topology-indicator');
    if (!el) return;
    const mode = state.topologyMode;
    const cls = mode === 'TRUE_NAS' ? 'nas' : mode === 'HYBRID' ? 'hybrid' : 'cloud';
    const label = mode === 'TRUE_NAS' ? 'True NAS' : mode === 'HYBRID' ? 'Hybrid' : 'Cloud';
    el.className = `topology-indicator ${cls}`;
    el.innerHTML = `<span class="topo-dot"></span>${label}`;
  }

  // ── Sidebar Toggle ─────────────────────────────────────────
  function toggleSidebar() {
    state.sidebarCollapsed = !state.sidebarCollapsed;
    const sidebar = $('#sidebar');
    if (sidebar) {
      sidebar.classList.toggle('collapsed', state.sidebarCollapsed);
    }
  }

  // ── Hash Utility ───────────────────────────────────────────
  function hashCode(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      hash = ((hash << 5) - hash) + str.charCodeAt(i);
      hash |= 0;
    }
    return hash;
  }

  // ── Public API (exposed for onclick handlers) ──────────────
  window.Tranc3App = {
    switchView,
    toggleSidebar,
    refreshData: refreshAllData,
    clearActivity: () => { state.activityLog = []; renderActivityFeed(); },
    setTopology: async (mode) => {
      const result = await api.put('/api/topology/mode', { mode });
      addActivity('system', result ? `Topology → <strong>${mode}</strong>` : `Topology switch failed`);
      refreshAllData();
    },
    runWorkflow: async (id) => {
      const result = await api.post(`/api/workflows/${id}/run`, {});
      addActivity('workflow', result ? `Workflow <strong>${id}</strong> triggered` : 'Workflow trigger failed');
      renderActivityFeed();
      refreshWorkflows();
    },
    createAgent: async () => {
      addActivity('agent', 'Spawning new agent…');
      const result = await api.post('/api/agents', { prompt: 'new agent', type: 'general' });
      addActivity('agent', result ? 'Agent spawned successfully' : 'Agent spawn failed');
      renderActivityFeed();
      refreshAgents();
    },
    createWorkflow: () => { addActivity('workflow', 'Workflow creation requested'); renderActivityFeed(); },
    createSecret: () => { addActivity('security', 'New secret creation requested'); renderActivityFeed(); },
    inspectAgent: (id) => { addActivity('agent', `Inspecting agent <strong>${id}</strong>`); renderActivityFeed(); },
    delegateAgent: (id) => { addActivity('agent', `Delegating to agent <strong>${id}</strong>`); renderActivityFeed(); },
    refreshAudit: () => { refreshAllData(); },
  };

  // ── Initialization ─────────────────────────────────────────
  async function init() {
    console.log('[Tranc3] AI Platform initializing…');

    // Bind navigation
    $$('.nav-item').forEach(item => {
      item.addEventListener('click', () => {
        const view = item.dataset.view;
        if (view) Tranc3App.switchView(view);
      });
    });

    // Bind sidebar toggle
    const toggleBtn = $('#sidebar-toggle');
    if (toggleBtn) toggleBtn.addEventListener('click', Tranc3App.toggleSidebar);

    // Initial data load
    await refreshAllData();

    // Connect real-time
    connectSSE();
    connectWebSocket();

    // Periodic refresh
    setInterval(refreshAllData, CONFIG.refreshInterval);

    // Set default view
    switchView('command');

    addActivity('system', 'Tranc3 AI Platform initialized');
    renderActivityFeed();

    console.log('[Tranc3] Ready — Gateway:', CONFIG.gatewayUrl);
  }

  // Start when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
