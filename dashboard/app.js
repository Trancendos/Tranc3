/* ============================================================
   Tranc3 AI Platform — Application Logic
   Phase 22.8: Infinity Ecosystem Dashboard
   Smart Adaptive Intelligence · Proactive Defense · Fluidic Routing
   ============================================================ */

(function () {
  'use strict';

  // ── Configuration ──────────────────────────────────────────────────────────
  const CONFIG = {
    gatewayUrl:      window.GATEWAY_URL      || `${location.protocol}//${location.hostname}:8040`,
    portalUrl:       window.PORTAL_URL       || `${location.protocol}//${location.hostname}:8042`,
    oneUrl:          window.ONE_URL          || `${location.protocol}//${location.hostname}:8043`,
    adminUrl:        window.ADMIN_URL        || `${location.protocol}//${location.hostname}:8044`,
    sentinelUrl:     window.SENTINEL_URL     || `${location.protocol}//${location.hostname}:8041`,
    authUrl:         window.AUTH_URL         || `${location.protocol}//${location.hostname}:8005`,
    refreshInterval: 6000,       // 6 s primary polling
    sseReconnectMs:  4000,       // SSE back-off base
    sentinelFeedMax: 120,        // max events in live feed
  };

  // ── State ──────────────────────────────────────────────────────────────────
  const S = {
    activeView:      'overview',
    sidebarOpen:     true,
    sse:             null,
    sseRetries:      0,
    pollTimer:       null,
    clockTimer:      null,
    sentinelFeed:    [],   // [{ts, channel, eventType, source}]
    serviceData:     {},   // keyed by service name
    healthScores: {
      portal: null, one: null, admin: null,
      gateway: null, sentinel: null, auth: null,
    },
  };

  // ── DOM helpers ────────────────────────────────────────────────────────────
  const $         = id => document.getElementById(id);
  const setText   = (id, v, fallback = '—') => {
    const el = $(id);
    if (el) el.textContent = (v === null || v === undefined) ? fallback : String(v);
  };
  const addClass    = (el, c) => el && el.classList.add(c);
  const removeClass = (el, c) => el && el.classList.remove(c);

  // ── View Switching ─────────────────────────────────────────────────────────
  window.switchView = function (name, el) {
    document.querySelectorAll('.view').forEach(v => removeClass(v, 'active'));
    document.querySelectorAll('.nav-item').forEach(i => removeClass(i, 'active'));

    const viewEl = $('view-' + name);
    if (viewEl) addClass(viewEl, 'active');
    if (el)     addClass(el, 'active');

    S.activeView = name;

    const labels = {
      overview:          'Dashboard',
      security:          'Defense Layer',
      pulse:             'Adaptive Pulse',
      routing:           'Fluidic Routing',
      foresight:         'Foresight',
      tiers:             'Tier Structure',
      dimensionals:      'Dimensionals',
      agents:            'AI Agents',
      models:            'Models',
      workflows:         'Workflows',
      'infinity-portal': 'Portal :8042',
      'infinity-one':    'Infinity One :8043',
      'infinity-admin':  'Admin :8044',
      gateway:           'Gateway :8040',
      sentinel:          'Sentinel Station :8041',
    };
    setText('breadcrumb-current', labels[name] || name);

    switch (name) {
      case 'security':         renderSecurityView();    break;
      case 'pulse':            renderPulseView();       break;
      case 'routing':          renderRoutingView();     break;
      case 'foresight':        renderForesightView();   break;
      case 'dimensionals':     renderDimensionalsView(); break;
      case 'agents':           renderAgentsView();      break;
      case 'models':           renderModelsView();      break;
      case 'workflows':        renderWorkflowsView();   break;
      case 'infinity-portal':  renderPortalDetail();    break;
      case 'infinity-one':     renderOneDetail();       break;
      case 'infinity-admin':   renderAdminDetail();     break;
      case 'gateway':          renderGatewayDetail();   break;
      case 'sentinel':         renderSentinelDetail();  break;
      default: break;
    }
  };

  window.toggleSidebar = function () {
    S.sidebarOpen = !S.sidebarOpen;
    const sb = $('sidebar');
    if (sb) sb.classList.toggle('collapsed', !S.sidebarOpen);
  };

  window.refreshAll = function () { pollAll(); };

  // ── Clock ──────────────────────────────────────────────────────────────────
  function startClock() {
    const tick = () => {
      const now = new Date();
      setText('topbar-clock', now.toLocaleTimeString('en-GB', { hour12: false }));
      setText('footer-time',  now.toLocaleString('en-GB', { hour12: false }));
    };
    tick();
    S.clockTimer = setInterval(tick, 1000);
  }

  // ── Fetch helper ───────────────────────────────────────────────────────────
  async function apiFetch(url, timeout = 5000) {
    const ctrl = new AbortController();
    const tid  = setTimeout(() => ctrl.abort(), timeout);
    try {
      const res = await fetch(url, { signal: ctrl.signal });
      clearTimeout(tid);
      if (!res.ok) return null;
      return await res.json();
    } catch {
      clearTimeout(tid);
      return null;
    }
  }

  // ── Polling orchestrator ───────────────────────────────────────────────────
  async function pollAll() {
    await Promise.allSettled([
      pollGateway(),
      pollPortal(),
      pollOne(),
      pollAdmin(),
      pollSentinel(),
      pollAuth(),
    ]);
    setText('last-updated', new Date().toLocaleTimeString('en-GB', { hour12: false }));
    refreshCurrentView();
  }

  function refreshCurrentView() {
    switch (S.activeView) {
      case 'overview':         renderOverview();        break;
      case 'security':         renderSecurityView();    break;
      case 'pulse':            renderPulseView();       break;
      case 'routing':          renderRoutingView();     break;
      case 'foresight':        renderForesightView();   break;
      case 'dimensionals':     renderDimensionalsView(); break;
      case 'agents':           renderAgentsView();      break;
      case 'models':           renderModelsView();      break;
      case 'workflows':        renderWorkflowsView();   break;
      case 'infinity-portal':  renderPortalDetail();    break;
      case 'infinity-one':     renderOneDetail();       break;
      case 'infinity-admin':   renderAdminDetail();     break;
      case 'gateway':          renderGatewayDetail();   break;
      case 'sentinel':         renderSentinelDetail();  break;
    }
  }

  // ── Per-service pollers ────────────────────────────────────────────────────
  async function pollGateway() {
    const [health, stats, overview] = await Promise.allSettled([
      apiFetch(`${CONFIG.gatewayUrl}/health`),
      apiFetch(`${CONFIG.gatewayUrl}/stats`),
      apiFetch(`${CONFIG.gatewayUrl}/api/overview`),
    ]);
    const h = health.value   || {};
    const s = stats.value    || {};
    const o = overview.value || {};
    S.serviceData.gateway = { health: h, stats: s, overview: o };
    S.healthScores.gateway = (h.status === 'ok' || h.status === 'healthy') ? 1.0 : null;
    updateServiceCard('gateway', h, s);
  }

  async function pollPortal() {
    const [health, stats] = await Promise.allSettled([
      apiFetch(`${CONFIG.portalUrl}/health`),
      apiFetch(`${CONFIG.portalUrl}/stats`),
    ]);
    const h = health.value || {};
    const s = stats.value  || {};
    S.serviceData.portal = { health: h, stats: s };
    S.healthScores.portal = extractHealthScore(h);
    updateServiceCard('portal', h, s);
  }

  async function pollOne() {
    const [health, stats] = await Promise.allSettled([
      apiFetch(`${CONFIG.oneUrl}/health`),
      apiFetch(`${CONFIG.oneUrl}/stats`),
    ]);
    const h = health.value || {};
    const s = stats.value  || {};
    S.serviceData.one = { health: h, stats: s };
    S.healthScores.one = extractHealthScore(h);
    updateServiceCard('one', h, s);
  }

  async function pollAdmin() {
    const [health, stats] = await Promise.allSettled([
      apiFetch(`${CONFIG.adminUrl}/health`),
      apiFetch(`${CONFIG.adminUrl}/stats`),
    ]);
    const h = health.value || {};
    const s = stats.value  || {};
    S.serviceData.admin = { health: h, stats: s };
    S.healthScores.admin = extractHealthScore(h);
    updateServiceCard('admin', h, s);
  }

  async function pollSentinel() {
    const [health, stats] = await Promise.allSettled([
      apiFetch(`${CONFIG.sentinelUrl}/health`),
      apiFetch(`${CONFIG.sentinelUrl}/stats`),
    ]);
    const h = health.value || {};
    const s = stats.value  || {};
    S.serviceData.sentinel = { health: h, stats: s };
    S.healthScores.sentinel = (h.status === 'healthy' || h.status === 'ok') ? 1.0 : null;
    updateServiceCard('sentinel', h, s);
  }

  async function pollAuth() {
    const h = await apiFetch(`${CONFIG.authUrl}/health`) || {};
    S.serviceData.auth = { health: h };
    S.healthScores.auth = extractHealthScore(h) || ((h.status === 'ok' || h.status === 'healthy') ? 1.0 : null);
    updateAuthCard(h);
  }

  function extractHealthScore(h) {
    if (h.health_score !== undefined && h.health_score !== null) return parseFloat(h.health_score);
    if (h.status === 'healthy' || h.status === 'ok') return 1.0;
    return null;
  }

  // ── Service card updaters ──────────────────────────────────────────────────
  function updateServiceCard(name, h, s) {
    const alive = (h.status === 'healthy' || h.status === 'ok');
    const dot   = $(`dot-${name}`);
    if (dot) dot.className = 'service-health-dot ' + (alive ? 'dot-healthy' : 'dot-offline');

    const score = S.healthScores[name];
    setText(`${name}-health-score`,
      score !== null ? `${(score * 100).toFixed(0)}%` : (alive ? '—' : 'Offline'));

    switch (name) {
      case 'portal': {
        setText('portal-sessions', s?.sessions?.active ?? '—');
        setText('portal-defense',  s?.smart_adaptive?.defense?.evaluations ?? '—');
        break;
      }
      case 'one': {
        setText('one-identities', s?.identities?.active ?? '—');
        setText('one-apps',       s?.app_access?.active_grants ?? '—');
        break;
      }
      case 'admin': {
        setText('admin-configs',  s?.system_data?.config_keys ?? '—');
        setText('admin-blocked',
          h.defense_blocked_ips ?? s?.smart_adaptive?.defense?.blocked_ips_count ?? '—');
        break;
      }
      case 'gateway': {
        setText('gateway-cache',    s?.cache_entries ?? '—');
        setText('gateway-circuits',
          s?.circuit_breakers ? Object.keys(s.circuit_breakers).length : '—');
        break;
      }
      case 'sentinel': {
        setText('sentinel-events', s?.events?.total_published ?? '—');
        setText('sentinel-subs',   s?.subscriptions?.total   ?? '—');
        break;
      }
    }

    updateForesightBar(name, score);
  }

  function updateAuthCard(h) {
    const alive = (h.status === 'healthy' || h.status === 'ok');
    const dot   = $('dot-auth');
    if (dot) dot.className = 'service-health-dot ' + (alive ? 'dot-healthy' : 'dot-offline');
    const score = S.healthScores.auth;
    setText('auth-health-score',
      score !== null ? `${(score * 100).toFixed(0)}%` : (alive ? '—' : 'Offline'));
    setText('auth-blocked', h.defense_blocked_ips ?? '—');
  }

  // ── Foresight trajectory bars ──────────────────────────────────────────────
  function updateForesightBar(name, score) {
    const bar   = $(`traj-${name}`);
    const label = $(`traj-${name}-lbl`);
    if (!bar || !label) return;
    if (score === null) {
      bar.style.width   = '0%';
      bar.className     = 'traj-bar traj-offline';
      label.textContent = 'Offline';
      return;
    }
    const pct  = (score * 100).toFixed(0);
    const tier = healthTier(score);
    bar.style.width   = `${pct}%`;
    bar.className     = `traj-bar traj-${tier.toLowerCase()}`;
    label.textContent = `${pct}% · ${tier}`;
  }

  function healthTier(score) {
    if (score >= 0.95) return 'EXCELLENT';
    if (score >= 0.80) return 'GOOD';
    if (score >= 0.60) return 'FAIR';
    if (score >= 0.40) return 'POOR';
    return 'CRITICAL';
  }

  // ── Overview rendering ─────────────────────────────────────────────────────
  function renderOverview() {
    const gw  = S.serviceData.gateway || {};
    const ov  = gw.overview || {};
    const gs  = gw.stats    || {};

    setText('kpi-agents-val',    ov.agents?.active    ?? gs.agents_active    ?? '—');
    setText('kpi-models-val',    ov.models?.loaded    ?? gs.models_loaded    ?? '—');
    setText('kpi-workflows-val', ov.workflows?.active ?? gs.workflows_active ?? '—');
    setText('kpi-requests-val',  ov.requests_per_min  ?? '—');

    const scores    = Object.values(S.healthScores).filter(v => v !== null);
    const avgHealth = scores.length
      ? scores.reduce((a, b) => a + b, 0) / scores.length : null;
    setText('kpi-health-val',
      avgHealth !== null ? `${(avgHealth * 100).toFixed(0)}%` : '—');

    // Total blocked across all services
    let totalBlocked = 0;
    for (const data of Object.values(S.serviceData)) {
      const k = data?.stats?.smart_adaptive?.defense;
      if (k?.blocked_count) totalBlocked += k.blocked_count;
      const ip = data?.health?.defense_blocked_ips;
      if (ip)  totalBlocked += parseInt(ip, 10) || 0;
    }
    setText('kpi-threats-val', totalBlocked || '—');
    setText('count-threats',   totalBlocked || '0');
    setText('count-agents',    ov.agents?.active ?? gs.agents_active ?? '0');

    // Global health badge
    const healthBadge = $('health-badge');
    const healthLabel = $('health-label');
    if (healthBadge && avgHealth !== null) {
      const tier = healthTier(avgHealth);
      if (healthLabel)
        healthLabel.textContent = `${(avgHealth * 100).toFixed(0)}% · ${tier}`;
      healthBadge.className = `health-badge health-${tier.toLowerCase()}`;
    }

    // Status indicator
    const allAlive   = Object.values(S.healthScores).some(v => v !== null);
    const mainDot    = $('status-dot-main');
    const mainStatus = $('status-main');
    if (mainDot)    mainDot.className    = 'status-dot ' + (allAlive ? 'dot-healthy' : 'dot-offline');
    if (mainStatus) mainStatus.textContent = allAlive ? 'Online' : 'Connecting…';

    // Re-render sentinel feed when overview is visible
    renderSentinelFeedPanel();
  }

  // ── Security / Defense View ────────────────────────────────────────────────
  async function renderSecurityView() {
    let totalEval = 0, totalBlocked = 0, totalIncidents = 0, totalBlockedIps = 0;
    const rows = [];

    const services = [
      { name: 'portal',   label: 'Portal',        url: CONFIG.portalUrl,   port: '8042' },
      { name: 'one',      label: 'Infinity One',  url: CONFIG.oneUrl,      port: '8043' },
      { name: 'admin',    label: 'Admin',         url: CONFIG.adminUrl,    port: '8044' },
      { name: 'gateway',  label: 'Gateway',       url: CONFIG.gatewayUrl,  port: '8040' },
      { name: 'sentinel', label: 'Sentinel',      url: CONFIG.sentinelUrl, port: '8041' },
      { name: 'auth',     label: 'Auth',          url: CONFIG.authUrl,     port: '8005' },
    ];

    for (const svc of services) {
      const dStats = await apiFetch(`${svc.url}/defense/stats`, 2500)
                     || S.serviceData[svc.name]?.stats?.smart_adaptive?.defense
                     || {};
      const bIps   = await apiFetch(`${svc.url}/defense/blocked-ips`, 2500);
      const bIpCnt = Array.isArray(bIps?.blocked_ips)
        ? bIps.blocked_ips.length
        : (S.serviceData[svc.name]?.health?.defense_blocked_ips ?? 0);

      const evaluations = parseInt(dStats.evaluations   || 0, 10);
      const blocked     = parseInt(dStats.blocked_count || 0, 10);
      const incidents   = parseInt(dStats.incidents     || 0, 10);

      totalEval       += evaluations;
      totalBlocked    += blocked;
      totalIncidents  += incidents;
      totalBlockedIps += parseInt(bIpCnt, 10) || 0;

      rows.push({ ...svc, evaluations, blocked, incidents, bIpCnt });
    }

    setText('sec-evaluations', totalEval);
    setText('sec-blocks',      totalBlocked);
    setText('sec-incidents',   totalIncidents);
    setText('sec-blocked-ips', totalBlockedIps);

    const body = $('defense-stats-body');
    if (!body) return;
    body.innerHTML = `
      <table class="data-table">
        <thead><tr>
          <th>Service</th><th>Port</th>
          <th>Evaluations</th><th>Blocked Req</th>
          <th>Incidents</th><th>Blocked IPs</th>
          <th>Mode</th>
        </tr></thead>
        <tbody>
          ${rows.map(r => `
          <tr class="defense-service-row">
            <td><strong>${r.label}</strong></td>
            <td><span class="port-badge">${r.port}</span></td>
            <td>${r.evaluations}</td>
            <td class="${r.blocked   > 0 ? 'threat-value' : ''}">${r.blocked}</td>
            <td class="${r.incidents > 0 ? 'threat-value' : ''}">${r.incidents}</td>
            <td class="${r.bIpCnt   > 0 ? 'threat-value' : ''}">${r.bIpCnt}</td>
            <td><span class="smart-badge">🛡 ProactiveDefense</span></td>
          </tr>`).join('')}
        </tbody>
      </table>`;
  }

  // ── Adaptive Pulse View ────────────────────────────────────────────────────
  async function renderPulseView() {
    const body = $('pulse-daemons-body');
    if (!body) return;

    const services = [
      { label: 'Portal',   url: CONFIG.portalUrl  },
      { label: 'One',      url: CONFIG.oneUrl     },
      { label: 'Admin',    url: CONFIG.adminUrl   },
      { label: 'Gateway',  url: CONFIG.gatewayUrl },
      { label: 'Sentinel', url: CONFIG.sentinelUrl},
    ];

    const rows = [];
    for (const svc of services) {
      const smart   = await apiFetch(`${svc.url}/health/smart`, 2500) || {};
      const kit     = S.serviceData[svc.label.toLowerCase()]?.stats?.smart_adaptive || {};
      const pulse   = kit.health?.pulse_mode || smart.pulse_mode || 'STEADY';
      const interval= kit.health?.interval_ms || smart.interval_ms;
      const daemons = kit.health?.daemons  || smart.daemons || [];
      rows.push({ label: svc.label, pulse, interval, daemons });
    }

    body.innerHTML = `
      <div class="pulse-grid">
        ${rows.map(r => `
        <div class="pulse-card">
          <div class="pulse-card-header">
            <strong>${r.label}</strong>
            <span class="pulse-mode pulse-mode-${(r.pulse || 'steady').toLowerCase()}">${r.pulse}</span>
          </div>
          <div class="pulse-interval">
            Interval: <code>${r.interval !== undefined ? r.interval + 'ms' : '—'}</code>
          </div>
          <div class="pulse-daemons">
            ${Array.isArray(r.daemons) && r.daemons.length
              ? r.daemons.map(d =>
                  `<span class="daemon-chip">${typeof d === 'string' ? d : (d.name || JSON.stringify(d))}</span>`
                ).join('')
              : '<span class="muted">No daemons reported</span>'}
          </div>
        </div>`).join('')}
      </div>`;
  }

  // ── Fluidic Routing View ───────────────────────────────────────────────────
  async function renderRoutingView() {
    const body = $('routing-cells-body');
    if (!body) return;

    const targets = [
      { label: 'Portal',  url: CONFIG.portalUrl  },
      { label: 'One',     url: CONFIG.oneUrl     },
      { label: 'Admin',   url: CONFIG.adminUrl   },
      { label: 'Gateway', url: CONFIG.gatewayUrl },
    ];

    const topologies = [];
    for (const t of targets) {
      const topo = await apiFetch(`${t.url}/routing/topology`, 2500);
      if (topo?.routes && Object.keys(topo.routes).length) {
        topologies.push({ service: t.label, routes: topo.routes });
      }
    }

    if (!topologies.length) {
      body.innerHTML = `<div class="muted-state">
        Routing topology not yet available — will populate once routing events occur.
      </div>`;
      return;
    }

    body.innerHTML = topologies.map(t => `
      <div class="routing-service-block">
        <h4 class="routing-service-name">${t.service}</h4>
        <div class="routing-cells">
          ${Object.entries(t.routes).map(([loc, cell]) => `
          <div class="routing-cell">
            <div class="routing-cell-location">${loc}</div>
            <div class="routing-cell-weight">${(cell.weight ?? 1.0).toFixed(3)}</div>
            <div class="routing-cell-meta">
              <span>Calls: ${cell.call_count ?? 0}</span>
              <span>Latency: ${cell.avg_latency_ms !== undefined
                ? cell.avg_latency_ms.toFixed(0) + 'ms' : '—'}</span>
            </div>
          </div>`).join('')}
        </div>
      </div>`).join('');
  }

  // ── Foresight View ─────────────────────────────────────────────────────────
  function renderForesightView() {
    const body = $('foresight-detail-body');
    if (!body) return;

    const services = [
      { name: 'portal',   label: 'Portal' },
      { name: 'one',      label: 'Infinity One' },
      { name: 'admin',    label: 'Admin' },
      { name: 'gateway',  label: 'Gateway' },
      { name: 'sentinel', label: 'Sentinel Station' },
      { name: 'auth',     label: 'Auth' },
    ];

    body.innerHTML = `
      <div class="foresight-detail">
        ${services.map(svc => {
          const score = S.healthScores[svc.name];
          const tier  = score !== null ? healthTier(score) : 'UNKNOWN';
          const pct   = score !== null ? (score * 100).toFixed(1) : null;
          return `
          <div class="foresight-row">
            <div class="foresight-service">${svc.label}</div>
            <div class="foresight-bar-wrap">
              <div class="foresight-bar foresight-${tier.toLowerCase()}"
                   style="width:${pct !== null ? pct : 0}%"></div>
            </div>
            <div class="foresight-stats">
              <span class="tier-chip tier-chip-${tier.toLowerCase()}">${tier}</span>
              <span class="foresight-score">${pct !== null ? pct + '%' : 'Offline'}</span>
            </div>
          </div>`;
        }).join('')}
      </div>
      <div class="foresight-legend">
        <span class="legend-item foresight-excellent">EXCELLENT ≥95%</span>
        <span class="legend-item foresight-good">GOOD ≥80%</span>
        <span class="legend-item foresight-fair">FAIR ≥60%</span>
        <span class="legend-item foresight-poor">POOR ≥40%</span>
        <span class="legend-item foresight-critical">CRITICAL &lt;40%</span>
      </div>`;
  }

  // ── Dimensionals View ──────────────────────────────────────────────────────
  async function renderDimensionalsView() {
    const body = $('dimensionals-body');
    if (!body) return;

    const data     = await apiFetch(`${CONFIG.gatewayUrl}/api/dimensionals`) || {};
    const services = data.services || data.dimensional_services || [];
    const regStats = S.serviceData.gateway?.stats?.dimensional_registry || {};

    if (!services.length) {
      body.innerHTML = `
        <div class="dim-stats">
          <div class="dim-stat"><span class="stat-label">Registered</span>
            <span class="stat-value">${regStats.service_count ?? '—'}</span></div>
          <div class="dim-stat"><span class="stat-label">Active</span>
            <span class="stat-value">${regStats.active_count ?? '—'}</span></div>
          <div class="dim-stat"><span class="stat-label">Pillars</span>
            <span class="stat-value">${regStats.pillar_count ?? '—'}</span></div>
        </div>
        <div class="muted-state">Detailed dimensional registry available once the gateway is online.</div>`;
      return;
    }

    body.innerHTML = `
      <div class="dimensional-grid">
        ${services.map(svc => `
        <div class="dimensional-card pillar-${(svc.pillar || 'creation').toLowerCase()}">
          <div class="dim-card-header">
            <span class="dim-icon">⬡</span>
            <strong>${svc.name || svc.service_id}</strong>
            <span class="port-badge">${svc.port || ''}</span>
          </div>
          <div class="dim-card-body">
            <div class="dim-meta">Pillar: <em>${svc.pillar || '—'}</em></div>
            <div class="dim-meta">Status:
              <span class="${svc.is_active ? 'text-healthy' : 'text-offline'}">
                ${svc.is_active ? '● Online' : '○ Offline'}
              </span>
            </div>
            ${svc.description ? `<div class="dim-desc">${svc.description}</div>` : ''}
          </div>
        </div>`).join('')}
      </div>`;
  }

  // ── AI Agents View ─────────────────────────────────────────────────────────
  async function renderAgentsView() {
    const body = $('agents-body');
    if (!body) return;
    const data   = await apiFetch(`${CONFIG.gatewayUrl}/api/agents`) || {};
    const list   = data.agents || S.serviceData.gateway?.overview?.agents?.list || [];
    if (!list.length) {
      body.innerHTML = `<div class="muted-state">No active agents. Start an agent to see it here.</div>`;
      return;
    }
    body.innerHTML = `
      <div class="entity-grid">
        ${list.map(a => `
        <div class="entity-card">
          <div class="entity-header">
            <span class="entity-icon">⚡</span>
            <strong>${a.name || a.agent_id || 'Agent'}</strong>
            <span class="tier-badge tier-4">T4 · Agent</span>
          </div>
          <div class="entity-meta">Model: ${a.model || '—'}</div>
          <div class="entity-meta">Status: ${a.status || '—'}</div>
        </div>`).join('')}
      </div>`;
  }

  // ── Models View ────────────────────────────────────────────────────────────
  async function renderModelsView() {
    const body = $('models-body');
    if (!body) return;
    const data = await apiFetch(`${CONFIG.gatewayUrl}/api/models`) || {};
    const list = data.models || [];
    if (!list.length) {
      body.innerHTML = `<div class="muted-state">No models loaded. Deploy a model to see it here.</div>`;
      return;
    }
    body.innerHTML = `
      <div class="entity-grid">
        ${list.map(m => `
        <div class="entity-card">
          <div class="entity-header">
            <span class="entity-icon">🧠</span>
            <strong>${m.name || m.model_id || 'Model'}</strong>
            <span class="tier-badge tier-3">T3 · AI</span>
          </div>
          <div class="entity-meta">Type: ${m.type || '—'}</div>
          <div class="entity-meta">Status: ${m.status || 'ready'}</div>
        </div>`).join('')}
      </div>`;
  }

  // ── Workflows View ─────────────────────────────────────────────────────────
  async function renderWorkflowsView() {
    const body = $('workflows-body');
    if (!body) return;
    const data = await apiFetch(`${CONFIG.gatewayUrl}/api/workflows`) || {};
    const list = data.workflows || [];
    if (!list.length) {
      body.innerHTML = `<div class="muted-state">No workflows found. Create one to see it here.</div>`;
      return;
    }
    body.innerHTML = `
      <div class="entity-grid">
        ${list.map(w => `
        <div class="entity-card">
          <div class="entity-header">
            <span class="entity-icon">◈</span>
            <strong>${w.name || w.workflow_id || 'Workflow'}</strong>
            <span class="tier-badge tier-1">T1 · Orchestrator</span>
          </div>
          <div class="entity-meta">Status: ${w.status || '—'}</div>
          <div class="entity-meta">Steps: ${w.steps?.length ?? '—'}</div>
        </div>`).join('')}
      </div>`;
  }

  // ── Infinity Service Detail Views ──────────────────────────────────────────
  function renderPortalDetail() {
    const body = $('portal-detail-body');
    if (!body) return;
    const d = S.serviceData.portal || {};
    body.innerHTML = buildServiceDetail('Portal', 8042, d.health || {}, d.stats || {}, [
      { label: 'Active Sessions', value: d.stats?.sessions?.active   ?? '—' },
      { label: 'Total Sessions',  value: d.stats?.sessions?.total    ?? '—' },
      { label: 'Total Events',    value: d.stats?.events?.total      ?? '—' },
      { label: 'Gate Routings',   value: d.stats?.gate_routing?.total ?? '—' },
    ]);
  }

  function renderOneDetail() {
    const body = $('one-detail-body');
    if (!body) return;
    const d = S.serviceData.one || {};
    body.innerHTML = buildServiceDetail('Infinity One', 8043, d.health || {}, d.stats || {}, [
      { label: 'Active Identities', value: d.stats?.identities?.active         ?? '—' },
      { label: 'Total Identities',  value: d.stats?.identities?.total          ?? '—' },
      { label: 'App Grants',        value: d.stats?.app_access?.active_grants  ?? '—' },
      { label: 'Devices',           value: d.stats?.devices?.total             ?? '—' },
      { label: 'Identity Events',   value: d.stats?.events?.total              ?? '—' },
    ]);
  }

  function renderAdminDetail() {
    const body = $('admin-detail-body');
    if (!body) return;
    const d = S.serviceData.admin || {};
    body.innerHTML = buildServiceDetail('Admin', 8044, d.health || {}, d.stats || {}, [
      { label: 'Config Keys',   value: d.stats?.system_data?.config_keys       ?? '—' },
      { label: 'Feature Flags', value: d.stats?.system_data?.feature_flags     ?? '—' },
      { label: 'Audit Actions', value: d.stats?.system_data?.audit_actions     ?? '—' },
      { label: 'Compliance',    value: d.stats?.system_data?.compliance_events ?? '—' },
      { label: 'Blocked IPs',   value: d.health?.defense_blocked_ips           ?? '—' },
    ]);
  }

  function renderGatewayDetail() {
    const body = $('gateway-detail-body');
    if (!body) return;
    const d = S.serviceData.gateway || {};
    body.innerHTML = buildServiceDetail('Gateway', 8040, d.health || {}, d.stats || {}, [
      { label: 'Upstream Workers',  value: d.stats?.upstream_workers   ?? '—' },
      { label: 'Reachable',         value: d.stats?.reachable          ?? '—' },
      { label: 'WS Connections',    value: d.stats?.ws_connections     ?? '—' },
      { label: 'Cache Entries',     value: d.stats?.cache_entries      ?? '—' },
      { label: 'ABAC Threat Level', value: d.stats?.abac_threat_level  ?? '—' },
      { label: 'Sentinel Backend',  value: d.health?.sentinel_station?.backend ?? '—' },
    ]);
  }

  function renderSentinelDetail() {
    const body = $('sentinel-detail-body');
    if (!body) return;
    const d = S.serviceData.sentinel || {};
    body.innerHTML = buildServiceDetail('Sentinel Station', 8041, d.health || {}, d.stats || {}, [
      { label: 'Total Published',     value: d.stats?.events?.total_published  ?? '—' },
      { label: 'Total Subscriptions', value: d.stats?.subscriptions?.total     ?? '—' },
      { label: 'Active Channels',     value: d.stats?.channels?.active_count   ?? '—' },
      { label: 'Reactive Topology',   value: d.health?.reactive_topology ? '✓ Live' : '—' },
      { label: 'Redis Backend',
        value: d.health?.sentinel?.redis_connected !== undefined
          ? (d.health.sentinel.redis_connected ? 'Connected' : 'Fallback') : '—' },
    ]);
  }

  // ── Shared service detail builder ──────────────────────────────────────────
  function buildServiceDetail(name, port, health, stats, metrics) {
    const alive   = health.status === 'healthy' || health.status === 'ok';
    const score   = health.health_score;
    const tier    = health.health_tier
      || (score !== undefined ? healthTier(parseFloat(score)) : '—');
    const pct     = score !== undefined
      ? (parseFloat(score) * 100).toFixed(1) + '%' : '—';

    const kit     = stats.smart_adaptive  || {};
    const defStat = kit.defense           || {};
    const gwStat  = kit.gateway           || {};
    const hStat   = kit.health            || {};

    return `
      <div class="service-detail">
        <div class="service-detail-header">
          <div class="service-detail-status ${alive ? 'status-healthy' : 'status-offline'}">
            ${alive ? '● Online' : '○ Offline'}
          </div>
          <div class="service-detail-scores">
            <span class="score-chip">Health: <strong>${pct}</strong></span>
            <span class="tier-chip tier-chip-${tier.toLowerCase()}">${tier}</span>
          </div>
        </div>

        <div class="detail-section">
          <h4>📊 Service Metrics</h4>
          <div class="metrics-grid">
            ${metrics.map(m => `
            <div class="metric-item">
              <span class="metric-label">${m.label}</span>
              <span class="metric-value">${m.value}</span>
            </div>`).join('')}
          </div>
        </div>

        ${Object.keys(defStat).length ? `
        <div class="detail-section">
          <h4>🛡 Defense Layer</h4>
          <div class="metrics-grid">
            <div class="metric-item">
              <span class="metric-label">Evaluations</span>
              <span class="metric-value">${defStat.evaluations ?? '—'}</span>
            </div>
            <div class="metric-item">
              <span class="metric-label">Blocked</span>
              <span class="metric-value threat-value">${defStat.blocked_count ?? '—'}</span>
            </div>
            <div class="metric-item">
              <span class="metric-label">Incidents</span>
              <span class="metric-value threat-value">${defStat.incidents ?? '—'}</span>
            </div>
            <div class="metric-item">
              <span class="metric-label">Blocked IPs</span>
              <span class="metric-value threat-value">
                ${defStat.blocked_ips_count ?? (Array.isArray(defStat.blocked_ips) ? defStat.blocked_ips.length : '—')}
              </span>
            </div>
          </div>
        </div>` : ''}

        ${Object.keys(gwStat).length ? `
        <div class="detail-section">
          <h4>⟁ Fluidic Gateway</h4>
          <div class="metrics-grid">
            <div class="metric-item">
              <span class="metric-label">Route Count</span>
              <span class="metric-value">${gwStat.route_count ?? '—'}</span>
            </div>
            <div class="metric-item">
              <span class="metric-label">Last Route</span>
              <span class="metric-value">${gwStat.last_route ?? '—'}</span>
            </div>
          </div>
        </div>` : ''}

        ${Object.keys(hStat).length ? `
        <div class="detail-section">
          <h4>⬡ Adaptive Pulse</h4>
          <div class="metrics-grid">
            <div class="metric-item">
              <span class="metric-label">Mode</span>
              <span class="metric-value">${hStat.pulse_mode ?? '—'}</span>
            </div>
            <div class="metric-item">
              <span class="metric-label">Interval</span>
              <span class="metric-value">
                ${hStat.interval_ms !== undefined ? hStat.interval_ms + 'ms' : '—'}
              </span>
            </div>
            <div class="metric-item">
              <span class="metric-label">Total Requests</span>
              <span class="metric-value">${hStat.total_requests ?? '—'}</span>
            </div>
            <div class="metric-item">
              <span class="metric-label">Error Rate</span>
              <span class="metric-value">
                ${hStat.error_rate !== undefined
                  ? (hStat.error_rate * 100).toFixed(1) + '%' : '—'}
              </span>
            </div>
          </div>
        </div>` : ''}

        <div class="detail-meta">
          <span class="meta-chip">Port: ${port}</span>
          <span class="meta-chip">Smart Adaptive: ${health.smart_adaptive ? '✓' : '—'}</span>
          <span class="meta-chip">Sentinel: ${
            health.sentinel || stats.sentinel?.is_running ? '✓' : '—'
          }</span>
          <span class="meta-chip">Phase 22.6</span>
        </div>
      </div>`;
  }

  // ── Sentinel SSE Feed ──────────────────────────────────────────────────────
  function connectSentinelSSE() {
    if (S.sse && S.sse.readyState !== EventSource.CLOSED) return;

    try {
      S.sse = new EventSource(`${CONFIG.sentinelUrl}/events`);
    } catch {
      scheduleSSEReconnect();
      return;
    }

    S.sse.onopen = () => {
      S.sseRetries = 0;
      const dot = $('sentinel-live-dot');
      if (dot) { dot.className = 'live-dot live-connected'; dot.textContent = '●'; }
    };

    S.sse.onmessage = (e) => {
      try { pushFeedItem(JSON.parse(e.data)); } catch {}
    };

    // Subscribe to Sentinel channel events
    ['platform', 'security', 'bridge', 'agent', 'ai', 'dimensional', 'underverse'].forEach(ch => {
      S.sse.addEventListener(ch, (e) => {
        try {
          const ev = JSON.parse(e.data);
          ev._channel = ch;
          pushFeedItem(ev);
        } catch {}
      });
    });

    S.sse.onerror = () => {
      S.sse.close();
      const dot = $('sentinel-live-dot');
      if (dot) { dot.className = 'live-dot live-disconnected'; dot.textContent = '○'; }
      scheduleSSEReconnect();
    };
  }

  function scheduleSSEReconnect() {
    const delay = Math.min(CONFIG.sseReconnectMs * Math.pow(1.5, S.sseRetries), 30000);
    S.sseRetries++;
    setTimeout(connectSentinelSSE, delay);
  }

  function pushFeedItem(event) {
    const channel   = event._channel || event.channel   || 'platform';
    const eventType = event.event_type || event.type    || 'event';
    const source    = event.source                      || '—';
    const ts        = new Date().toLocaleTimeString('en-GB', { hour12: false });

    S.sentinelFeed.unshift({ ts, channel, eventType, source });
    if (S.sentinelFeed.length > CONFIG.sentinelFeedMax)
      S.sentinelFeed.length = CONFIG.sentinelFeedMax;

    renderSentinelFeedPanel();
  }

  function renderSentinelFeedPanel() {
    const feed = $('sentinel-feed');
    if (!feed) return;
    if (!S.sentinelFeed.length) {
      feed.innerHTML = '<div class="feed-empty">Connecting to Sentinel Station…</div>';
      return;
    }
    feed.innerHTML = S.sentinelFeed.slice(0, 40).map(item => `
      <div class="feed-item feed-channel-${item.channel}">
        <span class="feed-ts">${item.ts}</span>
        <span class="feed-channel">${item.channel.toUpperCase()}</span>
        <span class="feed-event">${item.eventType}</span>
        <span class="feed-source">${item.source}</span>
      </div>`).join('');
  }

  // ── Dynamic CSS injection ──────────────────────────────────────────────────
  function injectDynamicStyles() {
    const style = document.createElement('style');
    style.textContent = `
      .dot-healthy  { background: var(--health-excellent); box-shadow: 0 0 6px var(--health-excellent); }
      .dot-offline  { background: var(--color-text-muted); box-shadow: none; }

      .pulse-mode-steady      { background: var(--health-excellent); color: #0a0e1a; }
      .pulse-mode-accelerated { background: var(--pillar-intelligence); color: #0a0e1a; }
      .pulse-mode-emergency   { background: var(--health-critical); color: #fff; }
      .pulse-mode-recovery    { background: var(--health-poor); color: #0a0e1a; }

      .traj-offline   { background: var(--color-text-muted); }
      .traj-excellent { background: var(--health-excellent); }
      .traj-good      { background: var(--health-good); }
      .traj-fair      { background: var(--health-fair); }
      .traj-poor      { background: var(--health-poor); }
      .traj-critical  { background: var(--health-critical); }

      .foresight-detail    { display:flex; flex-direction:column; gap:.75rem; }
      .foresight-row       { display:grid; grid-template-columns:130px 1fr 200px; align-items:center; gap:1rem; }
      .foresight-service   { font-size:.88rem; color:var(--color-text-secondary); }
      .foresight-bar-wrap  { height:14px; background:var(--color-surface-raised); border-radius:3px; overflow:hidden; }
      .foresight-bar       { height:100%; border-radius:3px; transition:width .8s ease; }
      .foresight-excellent { background:var(--health-excellent); }
      .foresight-good      { background:var(--health-good); }
      .foresight-fair      { background:var(--health-fair); }
      .foresight-poor      { background:var(--health-poor); }
      .foresight-critical  { background:var(--health-critical); }
      .foresight-unknown   { background:var(--color-text-muted); }
      .foresight-stats     { display:flex; align-items:center; gap:.5rem; }
      .foresight-score     { font-size:.82rem; color:var(--color-text-muted); font-family:var(--font-mono); }
      .foresight-legend    { display:flex; gap:.75rem; flex-wrap:wrap; margin-top:1rem; padding-top:.75rem; border-top:1px solid var(--color-border); }
      .legend-item         { font-size:.72rem; padding:2px 8px; border-radius:10px; color:#0a0e1a; font-weight:700; }
      .legend-item.foresight-excellent { background:var(--health-excellent); }
      .legend-item.foresight-good      { background:var(--health-good); }
      .legend-item.foresight-fair      { background:var(--health-fair); }
      .legend-item.foresight-poor      { background:var(--health-poor); }
      .legend-item.foresight-critical  { background:var(--health-critical); }

      .tier-chip             { font-size:.72rem; padding:2px 8px; border-radius:10px; font-weight:700; color:#0a0e1a; }
      .tier-chip-excellent   { background:var(--health-excellent); }
      .tier-chip-good        { background:var(--health-good); }
      .tier-chip-fair        { background:var(--health-fair); }
      .tier-chip-poor        { background:var(--health-poor); }
      .tier-chip-critical    { background:var(--health-critical); }
      .tier-chip-unknown     { background:var(--color-text-muted); color:var(--color-text); }

      .feed-item   { display:grid; grid-template-columns:65px 100px 1fr 85px; gap:.5rem; padding:4px 8px; border-radius:4px; font-size:.76rem; font-family:var(--font-mono); }
      .feed-item:hover { background:var(--color-surface-raised); }
      .feed-ts     { color:var(--color-text-muted); }
      .feed-channel{ font-weight:700; font-size:.68rem; letter-spacing:.04em; }
      .feed-event  { color:var(--color-text-secondary); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
      .feed-source { color:var(--color-text-muted); font-size:.7rem; text-align:right; overflow:hidden; text-overflow:ellipsis; }
      .feed-empty  { color:var(--color-text-muted); font-size:.85rem; padding:1.5rem; text-align:center; }
      .feed-channel-security { border-left:2px solid var(--pillar-security); }
      .feed-channel-platform { border-left:2px solid var(--pillar-intelligence); }
      .feed-channel-bridge   { border-left:2px solid var(--pillar-governance); }
      .feed-channel-agent    { border-left:2px solid var(--pillar-nexus); }
      .feed-channel-ai       { border-left:2px solid var(--pillar-creation); }

      .health-badge      { display:flex; align-items:center; gap:.4rem; font-size:.82rem; font-family:var(--font-mono); font-weight:600; }
      .health-excellent  { color:var(--health-excellent); }
      .health-good       { color:var(--health-good); }
      .health-fair       { color:var(--health-fair); }
      .health-poor       { color:var(--health-poor); }
      .health-critical   { color:var(--health-critical); }

      .data-table           { width:100%; border-collapse:collapse; font-size:.83rem; }
      .data-table th        { text-align:left; padding:.5rem .75rem; color:var(--color-text-muted); font-weight:500; font-size:.72rem; border-bottom:1px solid var(--color-border); }
      .data-table td        { padding:.6rem .75rem; border-bottom:1px solid rgba(255,255,255,.04); }
      .data-table tr:hover td { background:var(--color-surface-raised); }
      .threat-value         { color:var(--health-critical); font-weight:700; }
      .text-healthy         { color:var(--health-excellent); }
      .text-offline         { color:var(--color-text-muted); }

      .pulse-grid           { display:grid; grid-template-columns:repeat(auto-fill,minmax(270px,1fr)); gap:1rem; }
      .pulse-card           { background:var(--color-surface); border:1px solid var(--color-border); border-radius:8px; padding:1rem; }
      .pulse-card-header    { display:flex; justify-content:space-between; align-items:center; margin-bottom:.5rem; }
      .pulse-mode           { font-size:.7rem; padding:2px 8px; border-radius:10px; font-weight:700; }
      .pulse-interval       { font-size:.8rem; color:var(--color-text-muted); margin-bottom:.5rem; }
      .pulse-interval code  { color:var(--color-text); background:var(--color-surface-raised); padding:1px 5px; border-radius:3px; }
      .pulse-daemons        { display:flex; flex-wrap:wrap; gap:.3rem; }
      .daemon-chip          { font-size:.7rem; padding:2px 6px; background:var(--color-surface-raised); border:1px solid var(--color-border); border-radius:4px; color:var(--color-text-secondary); }

      .routing-service-block { margin-bottom:1.5rem; }
      .routing-service-name  { color:var(--pillar-intelligence); font-size:.88rem; margin-bottom:.75rem; font-weight:600; }
      .routing-cells         { display:grid; grid-template-columns:repeat(auto-fill,minmax(180px,1fr)); gap:.75rem; }
      .routing-cell          { background:var(--color-surface); border:1px solid var(--color-border); border-radius:8px; padding:.75rem; }
      .routing-cell-location { font-weight:600; font-size:.83rem; color:var(--pillar-intelligence); margin-bottom:.2rem; }
      .routing-cell-weight   { font-size:1.2rem; font-family:var(--font-mono); font-weight:700; margin-bottom:.25rem; }
      .routing-cell-meta     { display:flex; justify-content:space-between; font-size:.72rem; color:var(--color-text-muted); }
      .muted-state           { color:var(--color-text-muted); font-size:.85rem; padding:2rem; text-align:center; }

      .dimensional-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(250px,1fr)); gap:1rem; }
      .dimensional-card { background:var(--color-surface); border-radius:8px; padding:1rem; border-left:3px solid var(--color-border); }
      .dim-card-header  { display:flex; align-items:center; gap:.5rem; margin-bottom:.5rem; font-size:.88rem; font-weight:600; }
      .dim-icon         { color:var(--color-text-muted); }
      .dim-card-body    { font-size:.8rem; }
      .dim-meta         { color:var(--color-text-muted); line-height:1.7; }
      .dim-desc         { color:var(--color-text-secondary); margin-top:.3rem; font-size:.75rem; }
      .dim-stats        { display:flex; gap:2rem; padding:1rem 0 1.5rem; }
      .dim-stat         { display:flex; flex-direction:column; }
      .dim-stat .stat-label { font-size:.7rem; color:var(--color-text-muted); text-transform:uppercase; letter-spacing:.04em; }
      .dim-stat .stat-value { font-size:1.5rem; font-family:var(--font-mono); font-weight:700; color:var(--color-text); }

      .entity-grid   { display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:1rem; }
      .entity-card   { background:var(--color-surface); border:1px solid var(--color-border); border-radius:8px; padding:1rem; }
      .entity-header { display:flex; align-items:center; gap:.5rem; margin-bottom:.5rem; }
      .entity-icon   { font-size:1.1rem; }
      .entity-meta   { font-size:.8rem; color:var(--color-text-muted); line-height:1.6; }

      .service-detail        { }
      .service-detail-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:1.25rem; }
      .service-detail-status { font-size:.9rem; font-weight:700; }
      .status-healthy { color:var(--health-excellent); }
      .status-offline { color:var(--color-text-muted); }
      .service-detail-scores { display:flex; gap:.5rem; align-items:center; }
      .score-chip            { font-size:.85rem; color:var(--color-text-secondary); }
      .score-chip strong     { color:var(--color-text); }
      .detail-section        { margin-bottom:1.25rem; }
      .detail-section h4     { font-size:.82rem; color:var(--color-text-muted); margin-bottom:.75rem; font-weight:600; }
      .metrics-grid          { display:grid; grid-template-columns:repeat(auto-fill,minmax(175px,1fr)); gap:.5rem; }
      .metric-item           { background:var(--color-surface-raised); border-radius:6px; padding:.6rem .75rem; display:flex; flex-direction:column; }
      .metric-label          { font-size:.7rem; color:var(--color-text-muted); text-transform:uppercase; letter-spacing:.04em; margin-bottom:.2rem; }
      .metric-value          { font-size:.98rem; font-family:var(--font-mono); font-weight:600; color:var(--color-text); }
      .detail-meta           { display:flex; gap:.5rem; flex-wrap:wrap; padding-top:.75rem; border-top:1px solid var(--color-border); margin-top:.5rem; }
      .meta-chip             { font-size:.72rem; padding:2px 8px; background:var(--color-surface-raised); border:1px solid var(--color-border); border-radius:4px; color:var(--color-text-muted); }

      .live-dot              { font-size:.8rem; margin-left:auto; }
      .live-connected        { color:var(--health-excellent); animation:pulse-dot 2s infinite; }
      .live-disconnected     { color:var(--color-text-muted); }
      @keyframes pulse-dot   { 0%,100%{opacity:1} 50%{opacity:.25} }

      .alert-banner { position:sticky; top:0; z-index:100; padding:.6rem 1.5rem; font-size:.85rem; font-weight:600; }
      .alert-info   { background:var(--pillar-intelligence); color:#0a0e1a; }
      .alert-warning{ background:var(--health-fair);         color:#0a0e1a; }
      .alert-error  { background:var(--health-critical);     color:#fff; }

      .port-badge { font-size:.7rem; font-family:var(--font-mono); padding:1px 6px; background:var(--color-surface-raised); border:1px solid var(--color-border); border-radius:4px; color:var(--color-text-muted); }
      .muted      { color:var(--color-text-muted); font-size:.8rem; }

      .sidebar.collapsed .brand-text,
      .sidebar.collapsed .nav-section-label,
      .sidebar.collapsed .nav-item span:not(.nav-icon),
      .sidebar.collapsed .nav-service-badge,
      .sidebar.collapsed .nav-count,
      .sidebar.collapsed .nav-badge,
      .sidebar.collapsed .status-info { display:none; }
    `;
    document.head.appendChild(style);
  }

  // ── Bootstrap ──────────────────────────────────────────────────────────────
  function init() {
    injectDynamicStyles();
    startClock();
    connectSentinelSSE();
    pollAll();
    S.pollTimer = setInterval(pollAll, CONFIG.refreshInterval);
    setInterval(renderSentinelFeedPanel, 2000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
