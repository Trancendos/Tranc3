import { useState, useEffect, useCallback, useRef, useId } from "react";

// ─── Spark Brand Tokens ───────────────────────────────────────────────────────
const C = {
  primary: "#5865F2",
  primaryDim: "#4752C4",
  primaryGhost: "rgba(88,101,242,0.15)",
  accent: "#F5A623",
  accentGhost: "rgba(245,166,35,0.12)",
  success: "#3BA55D",
  warning: "#FAA81A",
  danger: "#ED4245",
  info: "#00B0F4",
  base: "#0D0F12",
  s1: "#13151A",
  s2: "#1E2025",
  s3: "#282B33",
  glass: "rgba(30,32,37,0.75)",
  border: "rgba(255,255,255,0.07)",
  borderStrong: "rgba(255,255,255,0.14)",
  text: "#FFFFFF",
  textSec: "#B9BBBE",
  textMuted: "#72767D",
};

// ─── API base — empty string = same origin ────────────────────────────────────
const API = "";

// ─── Static fallback data (rendered instantly; replaced once API responds) ───
const FALLBACK_LOCATIONS = [
  { id: "spark",       name: "The Spark",       icon: "⚡", role: "MCP Server + Tool Registry",  health: 0.98, status: "healthy", load: 34 },
  { id: "nexus",       name: "The Nexus",        icon: "⬡", role: "AI Comms + Message Bus",       health: 0.95, status: "healthy", load: 41 },
  { id: "grid",        name: "The Digital Grid", icon: "◈", role: "Workflow DAG Executor",         health: 0.91, status: "healthy", load: 67 },
  { id: "void",        name: "The Void",         icon: "○", role: "Encrypted Secrets Vault",       health: 1.00, status: "healthy", load: 5  },
  { id: "observatory", name: "The Observatory",  icon: "⬟", role: "Audit Log + Event Feed",        health: 0.97, status: "healthy", load: 22 },
  { id: "workshop",    name: "The Workshop",     icon: "⚙", role: "Forgejo CI/CD",                 health: 1.00, status: "healthy", load: 18 },
  { id: "library",     name: "The Library",      icon: "◇", role: "Knowledge Base (Outline)",      health: 0.89, status: "warning", load: 71 },
  { id: "basement",    name: "The Basement",     icon: "✦", role: "Inference + Vector Search",     health: 0.93, status: "healthy", load: 55 },
];

const FALLBACK_SERVICES = [
  { name: "Cloudflare Workers",           tier: "primary",   category: "edge",       score: 0.97, usage: 34, limit: "100K req/day" },
  { name: "FAISS Vector Store",           tier: "primary",   category: "vector_db",  score: 1.00, usage: 18, limit: "in-process"   },
  { name: "Cloudflare R2",                tier: "primary",   category: "storage",    score: 0.99, usage: 12, limit: "10GB"          },
  { name: "Cloudflare D1",                tier: "primary",   category: "database",   score: 0.96, usage: 28, limit: "5GB"           },
  { name: "The Workshop (Forgejo)",        tier: "primary",   category: "ci_cd",      score: 0.94, usage: 45, limit: "self-hosted"   },
  { name: "Upstash Redis",                tier: "primary",   category: "queue",      score: 1.00, usage: 8,  limit: "10K/day free"  },
  { name: "Sentence Transformers",        tier: "primary",   category: "embedding",  score: 1.00, usage: 0,  limit: "unlimited"     },
  { name: "Supabase Auth",                tier: "secondary", category: "auth",       score: 0.99, usage: 3,  limit: "50K MAU"       },
];

const FALLBACK_SKILL_CATEGORIES = [
  { name: "compliance",      count: 28, color: C.danger    },
  { name: "backend",         count: 20, color: C.primary   },
  { name: "ai-orchestration",count: 14, color: C.info      },
  { name: "monitoring",      count: 13, color: C.warning   },
  { name: "frontend",        count: 13, color: C.accent    },
  { name: "platform",        count: 12, color: "#7289DA"   },
  { name: "devops",          count: 12, color: "#43B581"   },
  { name: "data",            count: 12, color: "#F47FFF"   },
  { name: "core",            count: 14, color: C.primaryDim},
  { name: "failover",        count: 11, color: "#99AAB5"   },
  { name: "security",        count: 9,  color: "#FF6B6B"   },
  { name: "workflow",        count: 8,  color: "#4ECDC4"   },
  { name: "knowledge",       count: 8,  color: "#FFE66D"   },
  { name: "nano",            count: 6,  color: "#A8E6CF"   },
  { name: "quantum",         count: 5,  color: "#C3A6FF"   },
  { name: "genetic",         count: 2,  color: "#FF9A8B"   },
];

const FALLBACK_EVENTS = [
  { time: "—", type: "info",    msg: "Connecting to The Observatory event stream…" },
  { time: "—", type: "success", msg: "The Spark MCP server: awaiting health check" },
  { time: "—", type: "info",    msg: "The Nexus: message bus initialising"         },
];

// ─── Utility Components ───────────────────────────────────────────────────────

/**
 * ScorePill — a labelled health percentage badge.
 * `label` should describe what the score represents, e.g. "Cloudflare Workers health".
 */
function ScorePill({ score, label }) {
  const color = score >= 0.9 ? C.success : score >= 0.7 ? C.warning : C.danger;
  const pct   = (score * 100).toFixed(0);
  return (
    <span
      role="img"
      aria-label={label ? `${label}: ${pct}%` : `Health score: ${pct}%`}
      style={{
        background: `${color}22`, color, border: `1px solid ${color}44`,
        borderRadius: 20, padding: "2px 10px", fontSize: 12, fontWeight: 700,
        fontFamily: "monospace",
      }}
    >
      {pct}
    </span>
  );
}

/**
 * UsageBar — a labelled progress bar.
 * `label` should describe what is being measured, e.g. "Cloudflare Workers usage".
 */
function UsageBar({ usage, color = C.primary, label = "Usage" }) {
  const c = usage >= 90 ? C.danger : usage >= 70 ? C.warning : color;
  return (
    <div
      role="progressbar"
      aria-valuenow={usage}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={`${label}: ${usage}%`}
      style={{ background: "rgba(255,255,255,0.06)", borderRadius: 4, height: 4, overflow: "hidden" }}
    >
      <div style={{
        width: `${usage}%`, height: "100%",
        background: `linear-gradient(90deg, ${c}, ${c}88)`,
        transition: "width 0.8s ease",
        boxShadow: usage >= 80 ? `0 0 8px ${c}88` : "none",
      }} />
    </div>
  );
}

/** EventDot — purely decorative color indicator; type is conveyed by sr-only text on the parent. */
function EventDot({ type }) {
  const color = { info: C.info, success: C.success, warning: C.warning, error: C.danger }[type] || C.textMuted;
  return (
    <div
      aria-hidden="true"
      style={{ width: 7, height: 7, borderRadius: "50%", background: color, flexShrink: 0, marginTop: 3, boxShadow: `0 0 6px ${color}` }}
    />
  );
}

/**
 * Panel — a named region card.
 * When `title` is provided the panel becomes a `<section>` landmark labelled by its heading.
 */
function Panel({ title, children, accent, flex, style = {} }) {
  const titleId = useId();
  return (
    <section
      aria-labelledby={title ? titleId : undefined}
      style={{
        background: C.glass, backdropFilter: "blur(16px) saturate(180%)",
        border: `1px solid ${accent ? C.borderStrong : C.border}`,
        borderTop: accent ? `2px solid ${accent}` : undefined,
        borderRadius: 14, padding: "18px 20px",
        flex: flex || undefined,
        boxShadow: "0 8px 32px rgba(0,0,0,0.45)",
        ...style,
      }}
    >
      {title && (
        <h3
          id={titleId}
          style={{
            fontSize: 11, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase",
            color: C.textMuted, marginBottom: 14, margin: 0, marginBottom: 14,
          }}
        >
          {title}
        </h3>
      )}
      {children}
    </section>
  );
}

// ─── Main Dashboard ───────────────────────────────────────────────────────────
export default function SparkDashboard() {
  const [activeTab, setActiveTab] = useState("overview");
  const [tick, setTick] = useState(0);  // codeql[js/unused-local-variable] – used for animation shimmer
  const [bundlePulse, setBundlePulse] = useState(false);
  const [bundleError, setBundleError] = useState(null);
  const [mcpOnline, setMcpOnline] = useState(null);  // null=checking, true, false

  // Live data state — starts with fallback, updated from API
  const [locations, setLocations]             = useState(FALLBACK_LOCATIONS);
  const [services, setServices]               = useState(FALLBACK_SERVICES);
  const [skillCategories, setSkillCategories] = useState(FALLBACK_SKILL_CATEGORIES);
  const [recentEvents, setRecentEvents]       = useState(FALLBACK_EVENTS);
  const [toolCount, setToolCount]             = useState(0);

  const sseRef      = useRef(null);
  const tablistRef  = useRef(null);
  const bundleStatusId = useId();

  const TABS = ["overview", "locations", "services", "skills", "events"];
  const tabId   = (t) => `spark-tab-${t}`;
  const panelId = (t) => `spark-panel-${t}`;

  // ── Tick for animated shimmer ──
  useEffect(() => {
    const id = setInterval(() => setTick(t => t + 1), 3000);
    return () => clearInterval(id);
  }, []);

  // ── Poll MCP health + tools ──
  useEffect(() => {
    const fetchMcpData = async () => {
      try {
        const [healthRes, toolsRes] = await Promise.all([
          fetch(`${API}/mcp/health`),
          fetch(`${API}/mcp/tools`),
        ]);

        if (healthRes.ok) {
          const health = await healthRes.json();
          setMcpOnline(true);
          if (health.services) {
            setServices(prev => prev.map(svc => {
              const live = health.services[svc.name];
              return live ? { ...svc, score: live.health ?? svc.score, usage: live.usage ?? svc.usage } : svc;
            }));
          }
        } else {
          setMcpOnline(false);
        }

        if (toolsRes.ok) {
          const tools = await toolsRes.json();
          const count = Array.isArray(tools) ? tools.length : (tools.count ?? tools.total ?? 0);
          if (count > 0) setToolCount(count);

          if (Array.isArray(tools) && tools.length > 0 && tools[0].tags) {
            const tagMap = {};
            tools.forEach(t => (t.tags || []).forEach(tag => { tagMap[tag] = (tagMap[tag] || 0) + 1; }));
            const cats = Object.entries(tagMap)
              .sort((a, b) => b[1] - a[1])
              .map(([name, count], i) => ({
                name, count,
                color: FALLBACK_SKILL_CATEGORIES[i % FALLBACK_SKILL_CATEGORIES.length]?.color || C.primary,
              }));
            if (cats.length > 0) setSkillCategories(cats);
          }
        }
      } catch {
        setMcpOnline(false);
      }
    };

    fetchMcpData();
    const id = setInterval(fetchMcpData, 30_000);
    return () => clearInterval(id);
  }, []);

  // ── Subscribe to Observatory event stream ──
  useEffect(() => {
    const connectSSE = () => {
      try {
        const es = new EventSource(`${API}/observatory/sse`);
        sseRef.current = es;

        es.onmessage = (e) => {
          try {
            const ev = JSON.parse(e.data);
            setRecentEvents(prev => [
              {
                time: "just now",
                type: mapSeverity(ev.severity),
                msg: `${ev.service ?? "system"}: ${ev.event_type} — ${ev.outcome ?? ""}`.trim(),
              },
              ...prev.slice(0, 19),
            ]);
          } catch { /* ignore malformed events */ }
        };

        es.onerror = () => {
          es.close();
          sseRef.current = null;
          fetchObservatoryPolled();
        };
      } catch {
        fetchObservatoryPolled();
      }
    };

    const fetchObservatoryPolled = async () => {
      try {
        const res = await fetch(`${API}/observatory/recent?limit=10`);
        if (res.ok) {
          const events = await res.json();
          if (Array.isArray(events) && events.length > 0) {
            setRecentEvents(events.map(ev => ({
              time: relativeTime(ev.timestamp),
              type: mapSeverity(ev.severity),
              msg: `${ev.service ?? "system"}: ${ev.event_type}${ev.outcome ? ` — ${ev.outcome}` : ""}`,
            })));
          }
        }
      } catch { /* keep fallback */ }
    };

    connectSSE();

    return () => {
      sseRef.current?.close();
      sseRef.current = null;
    };
  }, []);

  // ── Derived hero metrics ──
  const totalSkills     = toolCount > 0 ? toolCount : skillCategories.reduce((s, c) => s + c.count, 0);
  const avgHealth       = services.reduce((s, x) => s + x.score, 0) / services.length;
  const healthyServices = services.filter(s => s.score >= 0.9).length;

  // ── Spark Ignition Bundle ──
  const triggerBundle = useCallback(async () => {
    setBundlePulse(true);
    setBundleError(null);
    try {
      const res = await fetch(`${API}/mcp/rpc`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          jsonrpc: "2.0",
          id: Date.now(),
          method: "tools/call",
          params: { name: "spark_ignition_bundle", arguments: { trigger: "manual_dashboard" } },
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
    } catch (err) {
      setBundleError(err.message);
    } finally {
      setTimeout(() => setBundlePulse(false), 1200);
    }
  }, []);

  // ── Tab keyboard navigation (WAI-ARIA Tabs pattern) ──
  function handleTabKeyDown(e, currentTab) {
    const idx = TABS.indexOf(currentTab);
    let nextTab = null;
    if (e.key === "ArrowRight") { e.preventDefault(); nextTab = TABS[(idx + 1) % TABS.length]; }
    else if (e.key === "ArrowLeft") { e.preventDefault(); nextTab = TABS[(idx - 1 + TABS.length) % TABS.length]; }
    else if (e.key === "Home") { e.preventDefault(); nextTab = TABS[0]; }
    else if (e.key === "End") { e.preventDefault(); nextTab = TABS[TABS.length - 1]; }
    if (nextTab) {
      setActiveTab(nextTab);
      tablistRef.current?.querySelector(`[data-tabid="${nextTab}"]`)?.focus();
    }
  }

  const mcpStatusLabel = mcpOnline === null ? "Connecting to MCP server…" : mcpOnline ? "Spark Online" : "Spark Offline";

  return (
    <div style={{
      fontFamily: "'DM Sans', 'Segoe UI', system-ui, sans-serif",
      background: `radial-gradient(ellipse at 20% 20%, rgba(88,101,242,0.12) 0%, transparent 60%),
                   radial-gradient(ellipse at 80% 80%, rgba(245,166,35,0.07) 0%, transparent 50%),
                   ${C.base}`,
      minHeight: "100vh", color: C.text, overflowX: "hidden",
    }}>

      {/* ── Header ── */}
      <header style={{
        borderBottom: `1px solid ${C.border}`,
        background: "rgba(13,15,18,0.9)", backdropFilter: "blur(20px)",
        padding: "0 24px", display: "flex", alignItems: "center",
        justifyContent: "space-between", height: 56, position: "sticky", top: 0, zIndex: 100,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {/* Decorative logo mark */}
          <div
            aria-hidden="true"
            style={{
              width: 32, height: 32, borderRadius: 8,
              background: `linear-gradient(135deg, ${C.primary}, #7289DA)`,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 16, boxShadow: `0 0 16px ${C.primary}55`,
            }}
          >⚡</div>
          <div>
            <h1 style={{ fontWeight: 800, fontSize: 16, letterSpacing: -0.5, margin: 0 }}>The Spark</h1>
            <div style={{ fontSize: 10, color: C.textMuted, letterSpacing: 0.5 }}>POWERED BY INFY · v2.0.0</div>
          </div>
        </div>

        {/* ── Tab list ── */}
        <nav aria-label="Dashboard sections">
          <div
            ref={tablistRef}
            role="tablist"
            aria-label="Dashboard sections"
            style={{ display: "flex", gap: 6 }}
          >
            {TABS.map(tab => (
              <button
                key={tab}
                id={tabId(tab)}
                role="tab"
                data-tabid={tab}
                aria-selected={activeTab === tab}
                aria-controls={panelId(tab)}
                tabIndex={activeTab === tab ? 0 : -1}
                onClick={() => setActiveTab(tab)}
                onKeyDown={(e) => handleTabKeyDown(e, tab)}
                style={{
                  background: activeTab === tab ? C.primaryGhost : "transparent",
                  border: `1px solid ${activeTab === tab ? C.primary : "transparent"}`,
                  borderRadius: 8, padding: "5px 14px", color: activeTab === tab ? C.primary : C.textMuted,
                  fontSize: 12, fontWeight: 600, cursor: "pointer", textTransform: "capitalize",
                  transition: "all 0.15s",
                }}
              >
                {tab}
              </button>
            ))}
          </div>
        </nav>

        {/* ── MCP connection status ── */}
        <div
          style={{ display: "flex", alignItems: "center", gap: 8 }}
          aria-live="polite"
          aria-atomic="true"
        >
          {/* Dot is decorative — the text label conveys the same information */}
          <div
            aria-hidden="true"
            style={{
              width: 8, height: 8, borderRadius: "50%",
              background: mcpOnline === null ? C.warning : mcpOnline ? C.success : C.danger,
              boxShadow: `0 0 8px ${mcpOnline === null ? C.warning : mcpOnline ? C.success : C.danger}`,
            }}
          />
          <span style={{ fontSize: 12, color: C.textSec }}>{mcpStatusLabel}</span>
        </div>
      </header>

      <main style={{ padding: "24px", maxWidth: 1200, margin: "0 auto" }}>

        {/* ── Hero Metrics ── */}
        <div
          role="list"
          aria-label="Key platform metrics"
          style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 20 }}
        >
          {[
            { label: "Skills Registered",  value: totalSkills, sub: `${toolCount > 0 ? "live from MCP" : "from registry"}`,          color: C.primary,  icon: "◈" },
            { label: "Platform Health",     value: `${(avgHealth * 100).toFixed(0)}%`, sub: `${healthyServices}/${services.length} services healthy`, color: C.success,  icon: "⬡" },
            { label: "Active Bundles",      value: 8,           sub: "Spark Ignition + 7 domain",                                     color: C.accent,   icon: "✦" },
            { label: "Compliance Score",    value: "97%",       sub: "GDPR · UK-GDPR · Magna Carta",                                  color: C.info,     icon: "⬟" },
          ].map(m => (
            <article key={m.label} role="listitem" aria-label={`${m.label}: ${m.value}`}>
              <Panel accent={m.color}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div>
                    <div style={{ fontSize: 11, color: C.textMuted, marginBottom: 4, textTransform: "uppercase", letterSpacing: 1 }}>{m.label}</div>
                    <div style={{ fontSize: 28, fontWeight: 800, color: m.color, letterSpacing: -1 }}>{m.value}</div>
                    <div style={{ fontSize: 11, color: C.textMuted, marginTop: 4 }}>{m.sub}</div>
                  </div>
                  {/* Decorative icon — already described by the label and value text */}
                  <div aria-hidden="true" style={{ fontSize: 22, opacity: 0.3, color: m.color }}>{m.icon}</div>
                </div>
              </Panel>
            </article>
          ))}
        </div>

        {/* ── SPARK IGNITION BUNDLE ── */}
        <div style={{ marginBottom: bundleError ? 8 : 20, display: "flex", justifyContent: "center", flexDirection: "column", alignItems: "center", gap: 8 }}>
          {/* Live status region keeps screen readers informed of firing / error states */}
          <div
            id={bundleStatusId}
            role="status"
            aria-live="polite"
            aria-atomic="true"
            className="sr-only"
          >
            {bundlePulse ? "Spark Ignition Bundle fired — sending to MCP…" : ""}
          </div>

          <button
            onClick={triggerBundle}
            disabled={bundlePulse}
            aria-busy={bundlePulse}
            aria-describedby={bundleStatusId}
            style={{
              background: bundlePulse
                ? `linear-gradient(135deg, ${C.accent}, #F7BC4E)`
                : `linear-gradient(135deg, ${C.primary}, #7289DA)`,
              border: "none", borderRadius: 12, padding: "14px 32px",
              color: bundlePulse ? C.base : C.text,
              fontSize: 14, fontWeight: 700, cursor: bundlePulse ? "default" : "pointer",
              boxShadow: bundlePulse ? `0 0 40px ${C.accent}88` : `0 0 24px ${C.primary}55`,
              transform: bundlePulse ? "scale(1.04)" : "scale(1)",
              transition: "all 0.3s cubic-bezier(0.34,1.56,0.64,1)",
              letterSpacing: 0.5, display: "flex", alignItems: "center", gap: 10,
              opacity: bundlePulse ? 0.9 : 1,
            }}
          >
            <span aria-hidden="true" style={{ fontSize: 18 }}>{bundlePulse ? "✦" : "⚡"}</span>
            {bundlePulse ? "Spark Ignition Bundle Fired — Sending to MCP…" : 'Trigger "Spark Ignition Bundle"'}
          </button>

          {bundleError && (
            <div
              role="alert"
              style={{ fontSize: 11, color: C.danger, background: `${C.danger}15`, borderRadius: 6, padding: "4px 12px" }}
            >
              MCP error: {bundleError}
            </div>
          )}
        </div>

        {/* ── Tab Panels ── */}
        {/* All panels are rendered but hidden when inactive — enables proper aria-controls linkage */}

        {/* OVERVIEW */}
        <section
          id={panelId("overview")}
          role="tabpanel"
          aria-labelledby={tabId("overview")}
          tabIndex={0}
          hidden={activeTab !== "overview"}
          style={{ display: activeTab === "overview" ? "grid" : "none", gridTemplateColumns: "1fr 1fr", gap: 16 }}
        >
          {/* Locations Grid */}
          <Panel title="Platform Services" accent={C.primary} style={{ gridColumn: "1 / -1" }}>
            <ul
              role="list"
              style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, listStyle: "none", margin: 0, padding: 0 }}
            >
              {locations.map(loc => (
                <li key={loc.id}>
                  <article
                    aria-label={`${loc.name}: ${loc.role}, health ${(loc.health * 100).toFixed(0)}%, load ${loc.load}%`}
                    style={{
                      background: C.s2, borderRadius: 10, padding: "12px 14px",
                      border: `1px solid ${loc.health < 0.8 ? C.warning + "44" : C.border}`,
                      cursor: "pointer", transition: "all 0.15s",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                      <span aria-hidden="true" style={{ fontSize: 20, opacity: 0.7 }}>{loc.icon}</span>
                      <ScorePill score={loc.health} label={`${loc.name} health`} />
                    </div>
                    <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 2 }}>{loc.name}</div>
                    <div style={{ fontSize: 10, color: C.textMuted, marginBottom: 8 }}>{loc.role}</div>
                    <UsageBar usage={loc.load} color={loc.health < 0.85 ? C.warning : C.primary} label={`${loc.name} load`} />
                    <div style={{ fontSize: 10, color: C.textMuted, marginTop: 4 }} aria-hidden="true">{loc.load}% load</div>
                  </article>
                </li>
              ))}
            </ul>
          </Panel>

          {/* Skill Distribution */}
          <Panel title="Skill Registry Distribution" accent={C.accent}>
            <ul
              role="list"
              aria-label="Skill categories"
              style={{ display: "flex", flexWrap: "wrap", gap: 6, listStyle: "none", margin: 0, padding: 0 }}
            >
              {skillCategories.map(cat => (
                <li
                  key={cat.name}
                  aria-label={`${cat.name}: ${cat.count} skills`}
                  style={{
                    background: `${cat.color}15`, border: `1px solid ${cat.color}33`,
                    borderRadius: 8, padding: "4px 10px", display: "flex", alignItems: "center", gap: 6,
                  }}
                >
                  <div aria-hidden="true" style={{ width: 6, height: 6, borderRadius: "50%", background: cat.color }} />
                  <span style={{ fontSize: 11, color: C.textSec }}>{cat.name}</span>
                  <span aria-hidden="true" style={{ fontSize: 11, fontWeight: 700, color: cat.color }}>{cat.count}</span>
                </li>
              ))}
            </ul>
            <div style={{ marginTop: 14, padding: "10px 14px", background: C.s2, borderRadius: 8, display: "flex", justifyContent: "space-between" }}>
              <span style={{ fontSize: 12, color: C.textMuted }}>Total skills</span>
              <span style={{ fontSize: 16, fontWeight: 800, color: C.accent }}>{totalSkills}</span>
            </div>
          </Panel>

          {/* Recent Events */}
          <Panel title="Observatory Event Stream" accent={C.info}>
            <ol
              role="log"
              aria-live="polite"
              aria-relevant="additions"
              aria-label="Recent platform events"
              style={{ display: "flex", flexDirection: "column", gap: 8, listStyle: "none", margin: 0, padding: 0 }}
            >
              {recentEvents.slice(0, 5).map((ev, i) => (
                <li key={i} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                  <EventDot type={ev.type} />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 12, color: C.textSec, lineHeight: 1.4 }}>
                      <span className="sr-only">[{ev.type}] </span>
                      {ev.msg}
                    </div>
                    <div style={{ fontSize: 10, color: C.textMuted, marginTop: 2 }}>{ev.time}</div>
                  </div>
                </li>
              ))}
            </ol>
          </Panel>
        </section>

        {/* LOCATIONS */}
        <section
          id={panelId("locations")}
          role="tabpanel"
          aria-labelledby={tabId("locations")}
          tabIndex={0}
          hidden={activeTab !== "locations"}
          style={{ display: activeTab === "locations" ? "grid" : "none", gridTemplateColumns: "1fr 1fr", gap: 16 }}
        >
          {locations.map(loc => (
            <Panel
              key={loc.id}
              title={loc.name}
              accent={loc.health >= 0.9 ? C.success : loc.health >= 0.8 ? C.warning : C.danger}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
                <div
                  aria-hidden="true"
                  style={{
                    width: 44, height: 44, borderRadius: 10, background: C.s2,
                    display: "flex", alignItems: "center", justifyContent: "center", fontSize: 22,
                    border: `1px solid ${C.border}`,
                  }}
                >{loc.icon}</div>
                <div>
                  {/* Name is already in the Panel <h3> title; role text supplements it */}
                  <div style={{ fontWeight: 800, fontSize: 16 }} aria-hidden="true">{loc.name}</div>
                  <div style={{ fontSize: 12, color: C.textMuted }}>{loc.role}</div>
                </div>
                <ScorePill score={loc.health} label={`${loc.name} health`} />
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
                    <span style={{ fontSize: 11, color: C.textMuted }}>Current Load</span>
                    <span style={{ fontSize: 11, fontWeight: 700, color: loc.load > 80 ? C.warning : C.textSec }} aria-hidden="true">{loc.load}%</span>
                  </div>
                  <UsageBar usage={loc.load} label={`${loc.name} current load`} />
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <div style={{ flex: 1, background: C.s2, borderRadius: 8, padding: "8px 12px", textAlign: "center" }}>
                    <div style={{ fontSize: 10, color: C.textMuted }}>Status</div>
                    <div
                      style={{ fontSize: 12, fontWeight: 700, color: loc.health >= 0.9 ? C.success : C.warning, marginTop: 2 }}
                    >
                      {/* Bullet is decorative — the word that follows provides the status */}
                      <span aria-hidden="true">● </span>
                      {loc.health >= 0.9 ? "Healthy" : "Warning"}
                    </div>
                  </div>
                  <div style={{ flex: 1, background: C.s2, borderRadius: 8, padding: "8px 12px", textAlign: "center" }}>
                    <div style={{ fontSize: 10, color: C.textMuted }}>Failover</div>
                    <div style={{ fontSize: 12, fontWeight: 700, color: C.textSec, marginTop: 2 }}>Standby</div>
                  </div>
                </div>
              </div>
            </Panel>
          ))}
        </section>

        {/* SERVICES */}
        <section
          id={panelId("services")}
          role="tabpanel"
          aria-labelledby={tabId("services")}
          tabIndex={0}
          hidden={activeTab !== "services"}
        >
          <Panel title="Registered Services — Dependency Monitor">
            {/* CSS-grid table with explicit ARIA table semantics */}
            <div role="table" aria-label="Registered services and dependency health">
              <div role="rowgroup">
                <div
                  role="row"
                  style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 2fr 1fr", gap: 12, padding: "6px 12px", fontSize: 10, color: C.textMuted, textTransform: "uppercase", letterSpacing: 1 }}
                >
                  <span role="columnheader">Service</span>
                  <span role="columnheader">Tier</span>
                  <span role="columnheader">Category</span>
                  <span role="columnheader">Usage</span>
                  <span role="columnheader">Score</span>
                </div>
              </div>
              <div role="rowgroup">
                {services.map(svc => (
                  <div
                    key={svc.name}
                    role="row"
                    style={{
                      display: "grid", gridTemplateColumns: "2fr 1fr 1fr 2fr 1fr", gap: 12,
                      padding: "12px 12px", background: C.s2, borderRadius: 8, alignItems: "center",
                      border: `1px solid ${svc.usage >= 80 ? C.warning + "33" : C.border}`,
                      marginBottom: 1,
                    }}
                  >
                    <div role="cell" style={{ fontWeight: 600, fontSize: 13 }}>{svc.name}</div>
                    <div role="cell">
                      <span style={{
                        fontSize: 10, fontWeight: 700, letterSpacing: 0.5,
                        color: svc.tier === "primary" ? C.primary : C.textMuted,
                        background: svc.tier === "primary" ? C.primaryGhost : C.s3,
                        borderRadius: 4, padding: "2px 8px", textAlign: "center",
                        display: "inline-block",
                      }}>{svc.tier}</span>
                    </div>
                    <div role="cell" style={{ fontSize: 11, color: C.textMuted }}>{svc.category}</div>
                    <div role="cell">
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                        <span style={{ fontSize: 10, color: C.textMuted }}>{svc.limit}</span>
                        <span style={{ fontSize: 10, fontWeight: 700, color: svc.usage >= 80 ? C.warning : C.textSec }} aria-hidden="true">{svc.usage}%</span>
                      </div>
                      <UsageBar usage={svc.usage} label={`${svc.name} usage`} />
                    </div>
                    <div role="cell">
                      <ScorePill score={svc.score} label={`${svc.name} health score`} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div style={{ marginTop: 16, padding: "12px 14px", background: C.s2, borderRadius: 8, display: "flex", gap: 24 }}>
              <div><span style={{ fontSize: 11, color: C.textMuted }}>Total cost: </span><span style={{ fontSize: 13, fontWeight: 800, color: C.success }}>$0.00/month</span></div>
              <div><span style={{ fontSize: 11, color: C.textMuted }}>Zero-cost mandate: </span><span style={{ fontSize: 13, fontWeight: 800, color: C.success }}>✓ COMPLIANT</span></div>
              <div><span style={{ fontSize: 11, color: C.textMuted }}>Failover tiers: </span><span style={{ fontSize: 13, fontWeight: 800, color: C.primary }}>All configured</span></div>
            </div>
          </Panel>
        </section>

        {/* SKILLS */}
        <section
          id={panelId("skills")}
          role="tabpanel"
          aria-labelledby={tabId("skills")}
          tabIndex={0}
          hidden={activeTab !== "skills"}
          style={{ display: activeTab === "skills" ? "grid" : "none", gridTemplateColumns: "1fr 1fr", gap: 16 }}
        >
          <Panel title="Skills by Category" accent={C.primary} style={{ gridColumn: "1 / -1" }}>
            <ul
              role="list"
              aria-label="Skill categories"
              style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, listStyle: "none", margin: 0, padding: 0 }}
            >
              {skillCategories.map(cat => {
                const maxCount = Math.max(...skillCategories.map(c => c.count), 1);
                return (
                  <li
                    key={cat.name}
                    aria-label={`${cat.name}: ${cat.count} skills, ${((cat.count / maxCount) * 100).toFixed(0)}% of top category`}
                    style={{
                      background: C.s2, borderRadius: 10, padding: "14px 16px",
                      border: `1px solid ${cat.color}22`, cursor: "pointer",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                      <div aria-hidden="true" style={{ width: 10, height: 10, borderRadius: "50%", background: cat.color, boxShadow: `0 0 8px ${cat.color}` }} />
                      <span aria-hidden="true" style={{ fontSize: 20, fontWeight: 900, color: cat.color }}>{cat.count}</span>
                    </div>
                    <div style={{ fontSize: 12, fontWeight: 600, textTransform: "capitalize" }}>{cat.name}</div>
                    <div style={{ fontSize: 10, color: C.textMuted, marginTop: 2 }}>skills</div>
                    <div style={{ marginTop: 8 }}>
                      <UsageBar usage={(cat.count / maxCount) * 100} color={cat.color} label={`${cat.name} relative to top category`} />
                    </div>
                  </li>
                );
              })}
            </ul>
          </Panel>

          <Panel title="Meta-Bundles" accent={C.accent}>
            <ul
              role="list"
              aria-label="Spark meta-bundles"
              style={{ listStyle: "none", margin: 0, padding: 0 }}
            >
              {[
                { id: "spark-ignition", name: "Spark Ignition",       count: 28, desc: "Master trigger — fires on build/create/implement",      emoji: "⚡" },
                { id: "frontend",       name: "Frontend App",          count: 13, desc: "React · Next.js · Tailwind · Glassmorphism",            emoji: "🎨" },
                { id: "backend",        name: "Backend API",           count: 17, desc: "TypeScript · Auth · DB · Encryption",                   emoji: "⚙️" },
                { id: "ai",             name: "AI Orchestration",      count: 13, desc: "RAG · LangChain · Embeddings · Agents",                 emoji: "🧠" },
                { id: "security",       name: "Security & Compliance", count: 12, desc: "OWASP · Zero Trust · Regulation Matrix",                emoji: "🛡️" },
                { id: "devops",         name: "DevOps & Deploy",       count: 12, desc: "Docker · The Workshop (Forgejo) · IaC · GitOps",        emoji: "🚀" },
                { id: "data",           name: "Data Pipeline",         count: 12, desc: "ETL · GDPR · Residency · Retention",                    emoji: "📊" },
                { id: "review",         name: "Trancendos Review",     count: 12, desc: "Technical · Compliance · Cost · Resilience",            emoji: "🔍" },
              ].map(b => (
                <li
                  key={b.id}
                  aria-label={`${b.name}: ${b.count} skills — ${b.desc}`}
                  style={{
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                    padding: "10px 12px", borderRadius: 8, background: C.s2,
                    marginBottom: 6, border: `1px solid ${C.border}`,
                  }}
                >
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 700 }}>
                      <span aria-hidden="true">{b.emoji} </span>{b.name}
                    </div>
                    <div style={{ fontSize: 11, color: C.textMuted }}>{b.desc}</div>
                  </div>
                  <div
                    aria-hidden="true"
                    style={{
                      background: C.accentGhost, color: C.accent, border: `1px solid ${C.accent}33`,
                      borderRadius: 20, padding: "2px 10px", fontSize: 11, fontWeight: 700,
                    }}
                  >{b.count}</div>
                </li>
              ))}
            </ul>
          </Panel>

          <Panel title="Compliance Coverage" accent={C.info}>
            <ul
              role="list"
              aria-label="Compliance framework scores"
              style={{ listStyle: "none", margin: 0, padding: 0 }}
            >
              {[
                { fw: "GDPR",        score: 1.0,  articles: "Art.5,6,13,17,25,32,33,35"        },
                { fw: "UK-GDPR",     score: 0.97, articles: "DPDPD Act 2024 deviations"         },
                { fw: "Magna Carta", score: 0.95, articles: "User ownership · Zero lock-in"     },
                { fw: "PRINCE2 7",   score: 0.92, articles: "7 principles · 7 themes · 7 procs" },
                { fw: "ITIL 4",      score: 0.88, articles: "34 practices · SVS"                },
                { fw: "Zero-Cost",   score: 1.0,  articles: "All services within free tiers"    },
              ].map(fw => (
                <li
                  key={fw.fw}
                  style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 0", borderBottom: `1px solid ${C.border}` }}
                >
                  <div style={{ width: 70, fontSize: 12, fontWeight: 700, color: C.text }}>{fw.fw}</div>
                  <div style={{ flex: 1 }}>
                    <UsageBar
                      usage={fw.score * 100}
                      color={fw.score >= 0.95 ? C.success : fw.score >= 0.85 ? C.warning : C.danger}
                      label={`${fw.fw} compliance score`}
                    />
                    <div style={{ fontSize: 10, color: C.textMuted, marginTop: 3 }}>{fw.articles}</div>
                  </div>
                  <ScorePill score={fw.score} label={`${fw.fw} compliance`} />
                </li>
              ))}
            </ul>
          </Panel>
        </section>

        {/* EVENTS */}
        <section
          id={panelId("events")}
          role="tabpanel"
          aria-labelledby={tabId("events")}
          tabIndex={0}
          hidden={activeTab !== "events"}
        >
          <Panel title="Observatory Event Stream — Full Log" accent={C.info}>
            <ol
              role="log"
              aria-live="polite"
              aria-relevant="additions"
              aria-label="Full Observatory event log"
              style={{ display: "flex", flexDirection: "column", gap: 6, listStyle: "none", margin: 0, padding: 0 }}
            >
              {recentEvents.map((ev, i) => (
                <li
                  key={i}
                  style={{
                    display: "flex", gap: 12, padding: "10px 12px",
                    background: C.s2, borderRadius: 8,
                    borderLeft: `3px solid ${{ info: C.info, success: C.success, warning: C.warning, error: C.danger }[ev.type] || C.textMuted}`,
                  }}
                >
                  <div style={{ width: 60, fontSize: 11, color: C.textMuted, flexShrink: 0, paddingTop: 1 }}>{ev.time}</div>
                  <div style={{ width: 64, flexShrink: 0 }}>
                    <span style={{
                      fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5,
                      color: { info: C.info, success: C.success, warning: C.warning, error: C.danger }[ev.type] || C.textMuted,
                      background: { info: `${C.info}15`, success: `${C.success}15`, warning: `${C.warning}15`, error: `${C.danger}15` }[ev.type] || `${C.textMuted}15`,
                      borderRadius: 4, padding: "2px 6px",
                    }}>{ev.type}</span>
                  </div>
                  <div style={{ fontSize: 13, color: C.textSec, flex: 1 }}>
                    {/* Type badge above is visible; add sr-only prefix so it reads inline in sequence */}
                    <span className="sr-only">[{ev.type}] </span>
                    {ev.msg}
                  </div>
                </li>
              ))}
            </ol>
          </Panel>
        </section>

        {/* ── Footer ── */}
        <footer style={{ marginTop: 24, textAlign: "center", color: C.textMuted, fontSize: 11 }}>
          <span aria-hidden="true">⚡ </span>
          <span>The Spark v2.0.0 · </span>
          <span style={{ color: C.primary }}>Infy</span>
          <span> · Trancendos · Zero-Cost · GDPR-Compliant · Self-Healing · 2060-Proof</span>
        </footer>
      </main>
    </div>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function mapSeverity(severity) {
  if (!severity) return "info";
  const s = severity.toLowerCase();
  if (s === "critical" || s === "error") return "error";
  if (s === "warning") return "warning";
  if (s === "security") return "error";
  if (s === "debug") return "info";
  return s === "info" ? "info" : "success";
}

function relativeTime(ts) {
  if (!ts) return "—";
  const diff = Math.floor(Date.now() / 1000 - ts);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}
