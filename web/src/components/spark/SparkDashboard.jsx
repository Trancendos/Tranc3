import { useState, useEffect, useCallback } from "react";

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

// ─── Mock Platform Data ───────────────────────────────────────────────────────
const LOCATIONS = [
  { id: "nexus", name: "The Nexus", icon: "⬡", role: "Integration Hub", health: 0.98, status: "healthy", load: 34 },
  { id: "luminous", name: "Luminous", icon: "◈", role: "Knowledge Layer", health: 0.95, status: "healthy", load: 67 },
  { id: "hive", name: "The HIVE", icon: "⬡", role: "Agent Coordination", health: 0.91, status: "healthy", load: 82 },
  { id: "void", name: "The Void", icon: "○", role: "Isolation/Testing", health: 1.00, status: "healthy", load: 5 },
  { id: "citadel", name: "The Citadel", icon: "⬟", role: "Security/Compliance", health: 0.97, status: "healthy", load: 22 },
  { id: "townhall", name: "Town Hall", icon: "⬡", role: "Governance", health: 1.00, status: "healthy", load: 18 },
  { id: "lab", name: "The Lab", icon: "◇", role: "R&D / Skills Dev", health: 0.89, status: "warning", load: 71 },
  { id: "chaos", name: "Code/Chaos Party", icon: "✦", role: "Rapid Prototyping", health: 0.76, status: "warning", load: 95 },
];

const SERVICES = [
  { name: "Cloudflare Workers", tier: "primary", category: "hosting", score: 0.97, usage: 34, limit: "100K req/day" },
  { name: "Qdrant Cloud", tier: "primary", category: "vector_db", score: 0.88, usage: 71, limit: "1GB storage" },
  { name: "Cloudflare R2", tier: "primary", category: "storage", score: 0.99, usage: 12, limit: "10GB" },
  { name: "Cloudflare D1", tier: "primary", category: "database", score: 0.96, usage: 28, limit: "5GB" },
  { name: "GitHub Actions", tier: "primary", category: "ci_cd", score: 0.94, usage: 45, limit: "2000 min/mo" },
  { name: "Cloudflare Queues", tier: "primary", category: "queue", score: 1.00, usage: 8, limit: "1M/mo" },
  { name: "Sentence Transformers", tier: "primary", category: "embedding", score: 1.00, usage: 0, limit: "unlimited" },
  { name: "Supabase Auth", tier: "secondary", category: "auth", score: 0.99, usage: 3, limit: "50K MAU" },
];

const SKILL_CATEGORIES = [
  { name: "compliance", count: 28, color: C.danger },
  { name: "backend", count: 20, color: C.primary },
  { name: "ai-orchestration", count: 14, color: C.info },
  { name: "monitoring", count: 13, color: C.warning },
  { name: "frontend", count: 13, color: C.accent },
  { name: "platform", count: 12, color: "#7289DA" },
  { name: "devops", count: 12, color: "#43B581" },
  { name: "data", count: 12, color: "#F47FFF" },
  { name: "core", count: 14, color: C.primaryDim },
  { name: "failover", count: 11, color: "#99AAB5" },
  { name: "security", count: 9, color: "#FF6B6B" },
  { name: "workflow", count: 8, color: "#4ECDC4" },
  { name: "knowledge", count: 8, color: "#FFE66D" },
  { name: "nano", count: 6, color: "#A8E6CF" },
  { name: "quantum", count: 5, color: "#C3A6FF" },
  { name: "genetic", count: 2, color: "#FF9A8B" },
];

const RECENT_EVENTS = [
  { time: "2m ago", type: "info", msg: "NanoMind: 12 skills retrieved for 'build authentication'" },
  { time: "8m ago", type: "success", msg: "QuantumShift: Qdrant cluster healthy — failover on standby" },
  { time: "15m ago", type: "warning", msg: "LogicCore: Code/Chaos Party health 0.76 — monitoring elevated" },
  { time: "23m ago", type: "success", msg: "NanoCode Bot: Refreshed 3 stale embeddings in Luminous" },
  { time: "1h ago", type: "info", msg: "Spark Ignition Bundle fired — 'build a dashboard' detected" },
  { time: "1h ago", type: "success", msg: "GitHub Actions: Skill validation passed — 193 skills, 0 errors" },
  { time: "3h ago", type: "info", msg: "Regulation Matrix: Full compliance sweep — overall score 0.97" },
  { time: "6h ago", type: "success", msg: "LogicCore: Health sweep complete — all services within free tier" },
];

// ─── Utility Components ───────────────────────────────────────────────────────
function ScorePill({ score }) {
  const color = score >= 0.9 ? C.success : score >= 0.7 ? C.warning : C.danger;
  return (
    <span style={{
      background: `${color}22`, color, border: `1px solid ${color}44`,
      borderRadius: 20, padding: "2px 10px", fontSize: 12, fontWeight: 700,
      fontFamily: "monospace",
    }}>
      {(score * 100).toFixed(0)}
    </span>
  );
}

function UsageBar({ usage, color = C.primary }) {
  const c = usage >= 90 ? C.danger : usage >= 70 ? C.warning : color;
  return (
    <div style={{ background: "rgba(255,255,255,0.06)", borderRadius: 4, height: 4, overflow: "hidden" }}>
      <div style={{
        width: `${usage}%`, height: "100%",
        background: `linear-gradient(90deg, ${c}, ${c}88)`,
        transition: "width 0.8s ease",
        boxShadow: usage >= 80 ? `0 0 8px ${c}88` : "none",
      }} />
    </div>
  );
}

function EventDot({ type }) {
  const color = { info: C.info, success: C.success, warning: C.warning, error: C.danger }[type] || C.textMuted;
  return <div style={{ width: 7, height: 7, borderRadius: "50%", background: color, flexShrink: 0, marginTop: 3, boxShadow: `0 0 6px ${color}` }} />;
}

// ─── Panel Wrapper ────────────────────────────────────────────────────────────
function Panel({ title, children, accent, flex, style = {} }) {
  return (
    <div style={{
      background: C.glass, backdropFilter: "blur(16px) saturate(180%)",
      border: `1px solid ${accent ? C.borderStrong : C.border}`,
      borderTop: accent ? `2px solid ${accent}` : undefined,
      borderRadius: 14, padding: "18px 20px",
      flex: flex || undefined,
      boxShadow: "0 8px 32px rgba(0,0,0,0.45)",
      ...style,
    }}>
      {title && (
        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase", color: C.textMuted, marginBottom: 14 }}>
          {title}
        </div>
      )}
      {children}
    </div>
  );
}

// ─── Main Dashboard ───────────────────────────────────────────────────────────
export default function SparkDashboard() {
  const [activeTab, setActiveTab] = useState("overview");
  const [tick, setTick] = useState(0);
  const [bundlePulse, setBundlePulse] = useState(false);

  // Simulate live metrics
  useEffect(() => {
    const id = setInterval(() => setTick(t => t + 1), 3000);
    return () => clearInterval(id);
  }, []);

  const totalSkills = SKILL_CATEGORIES.reduce((s, c) => s + c.count, 0);
  const avgHealth = SERVICES.reduce((s, x) => s + x.score, 0) / SERVICES.length;
  const healthyServices = SERVICES.filter(s => s.score >= 0.9).length;

  // Animated shimmer value
  const shimmer = Math.sin(tick * 0.5) * 0.5 + 0.5;

  const triggerBundle = useCallback(() => {
    setBundlePulse(true);
    setTimeout(() => setBundlePulse(false), 1200);
  }, []);

  const tabs = ["overview", "locations", "services", "skills", "events"];

  return (
    <div style={{
      fontFamily: "'DM Sans', 'Segoe UI', system-ui, sans-serif",
      background: `radial-gradient(ellipse at 20% 20%, rgba(88,101,242,0.12) 0%, transparent 60%),
                   radial-gradient(ellipse at 80% 80%, rgba(245,166,35,0.07) 0%, transparent 50%),
                   ${C.base}`,
      minHeight: "100vh", color: C.text, overflowX: "hidden",
    }}>

      {/* ── Header ── */}
      <div style={{
        borderBottom: `1px solid ${C.border}`,
        background: "rgba(13,15,18,0.9)", backdropFilter: "blur(20px)",
        padding: "0 24px", display: "flex", alignItems: "center",
        justifyContent: "space-between", height: 56, position: "sticky", top: 0, zIndex: 100,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {/* Spark Logo */}
          <div style={{
            width: 32, height: 32, borderRadius: 8,
            background: `linear-gradient(135deg, ${C.primary}, #7289DA)`,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 16, boxShadow: `0 0 16px ${C.primary}55`,
          }}>⚡</div>
          <div>
            <div style={{ fontWeight: 800, fontSize: 16, letterSpacing: -0.5 }}>The Spark</div>
            <div style={{ fontSize: 10, color: C.textMuted, letterSpacing: 0.5 }}>POWERED BY INFY · v2.0.0</div>
          </div>
        </div>

        <div style={{ display: "flex", gap: 6 }}>
          {tabs.map(tab => (
            <button key={tab} onClick={() => setActiveTab(tab)} style={{
              background: activeTab === tab ? C.primaryGhost : "transparent",
              border: `1px solid ${activeTab === tab ? C.primary : "transparent"}`,
              borderRadius: 8, padding: "5px 14px", color: activeTab === tab ? C.primary : C.textMuted,
              fontSize: 12, fontWeight: 600, cursor: "pointer", textTransform: "capitalize",
              transition: "all 0.15s",
            }}>{tab}</button>
          ))}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ width: 8, height: 8, borderRadius: "50%", background: C.success, boxShadow: `0 0 8px ${C.success}` }} />
          <span style={{ fontSize: 12, color: C.textSec }}>Infy Online</span>
        </div>
      </div>

      <div style={{ padding: "24px", maxWidth: 1200, margin: "0 auto" }}>

        {/* ── Hero Metrics ── */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 20 }}>
          {[
            { label: "Skills Registered", value: totalSkills, sub: "193 validated · 0 errors", color: C.primary, icon: "◈" },
            { label: "Platform Health", value: `${(avgHealth * 100).toFixed(0)}%`, sub: `${healthyServices}/${SERVICES.length} services healthy`, color: C.success, icon: "⬡" },
            { label: "Active Bundles", value: 8, sub: "Spark Ignition + 7 domain", color: C.accent, icon: "✦" },
            { label: "Compliance Score", value: "97%", sub: "GDPR · UK-GDPR · Magna Carta", color: C.info, icon: "⬟" },
          ].map(m => (
            <Panel key={m.label} accent={m.color}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <div style={{ fontSize: 11, color: C.textMuted, marginBottom: 4, textTransform: "uppercase", letterSpacing: 1 }}>{m.label}</div>
                  <div style={{ fontSize: 28, fontWeight: 800, color: m.color, letterSpacing: -1 }}>{m.value}</div>
                  <div style={{ fontSize: 11, color: C.textMuted, marginTop: 4 }}>{m.sub}</div>
                </div>
                <div style={{ fontSize: 22, opacity: 0.3, color: m.color }}>{m.icon}</div>
              </div>
            </Panel>
          ))}
        </div>

        {/* ── SPARK IGNITION BUNDLE BUTTON ── */}
        <div style={{ marginBottom: 20, display: "flex", justifyContent: "center" }}>
          <button onClick={triggerBundle} style={{
            background: bundlePulse
              ? `linear-gradient(135deg, ${C.accent}, #F7BC4E)`
              : `linear-gradient(135deg, ${C.primary}, #7289DA)`,
            border: "none", borderRadius: 12, padding: "14px 32px",
            color: bundlePulse ? C.base : C.text,
            fontSize: 14, fontWeight: 700, cursor: "pointer",
            boxShadow: bundlePulse ? `0 0 40px ${C.accent}88` : `0 0 24px ${C.primary}55`,
            transform: bundlePulse ? "scale(1.04)" : "scale(1)",
            transition: "all 0.3s cubic-bezier(0.34,1.56,0.64,1)",
            letterSpacing: 0.5, display: "flex", alignItems: "center", gap: 10,
          }}>
            <span style={{ fontSize: 18 }}>{bundlePulse ? "✦" : "⚡"}</span>
            {bundlePulse ? "Spark Ignition Bundle Fired — 28 Skills Injected" : 'Trigger "Spark Ignition Bundle"'}
          </button>
        </div>

        {/* ── Tab Content ── */}
        {activeTab === "overview" && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            {/* Locations Grid */}
            <Panel title="Platform Locations" accent={C.primary} style={{ gridColumn: "1 / -1" }}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
                {LOCATIONS.map(loc => (
                  <div key={loc.id} style={{
                    background: C.s2, borderRadius: 10, padding: "12px 14px",
                    border: `1px solid ${loc.health < 0.8 ? C.warning + "44" : C.border}`,
                    cursor: "pointer", transition: "all 0.15s",
                  }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                      <span style={{ fontSize: 20, opacity: 0.7 }}>{loc.icon}</span>
                      <ScorePill score={loc.health} />
                    </div>
                    <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 2 }}>{loc.name}</div>
                    <div style={{ fontSize: 10, color: C.textMuted, marginBottom: 8 }}>{loc.role}</div>
                    <UsageBar usage={loc.load} color={loc.health < 0.85 ? C.warning : C.primary} />
                    <div style={{ fontSize: 10, color: C.textMuted, marginTop: 4 }}>{loc.load}% load</div>
                  </div>
                ))}
              </div>
            </Panel>

            {/* Skill Distribution */}
            <Panel title="Skill Registry Distribution" accent={C.accent}>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {SKILL_CATEGORIES.map(cat => (
                  <div key={cat.name} style={{
                    background: `${cat.color}15`, border: `1px solid ${cat.color}33`,
                    borderRadius: 8, padding: "4px 10px", display: "flex", alignItems: "center", gap: 6,
                  }}>
                    <div style={{ width: 6, height: 6, borderRadius: "50%", background: cat.color }} />
                    <span style={{ fontSize: 11, color: C.textSec }}>{cat.name}</span>
                    <span style={{ fontSize: 11, fontWeight: 700, color: cat.color }}>{cat.count}</span>
                  </div>
                ))}
              </div>
              <div style={{ marginTop: 14, padding: "10px 14px", background: C.s2, borderRadius: 8, display: "flex", justifyContent: "space-between" }}>
                <span style={{ fontSize: 12, color: C.textMuted }}>Total skills</span>
                <span style={{ fontSize: 16, fontWeight: 800, color: C.accent }}>{totalSkills}</span>
              </div>
            </Panel>

            {/* Recent Events */}
            <Panel title="Nanofibers Event Stream" accent={C.info}>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {RECENT_EVENTS.slice(0, 5).map((ev, i) => (
                  <div key={i} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                    <EventDot type={ev.type} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 12, color: C.textSec, lineHeight: 1.4 }}>{ev.msg}</div>
                      <div style={{ fontSize: 10, color: C.textMuted, marginTop: 2 }}>{ev.time}</div>
                    </div>
                  </div>
                ))}
              </div>
            </Panel>
          </div>
        )}

        {activeTab === "locations" && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            {LOCATIONS.map(loc => (
              <Panel key={loc.id} accent={loc.health >= 0.9 ? C.success : loc.health >= 0.8 ? C.warning : C.danger}>
                <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
                  <div style={{
                    width: 44, height: 44, borderRadius: 10, background: C.s2,
                    display: "flex", alignItems: "center", justifyContent: "center", fontSize: 22,
                    border: `1px solid ${C.border}`,
                  }}>{loc.icon}</div>
                  <div>
                    <div style={{ fontWeight: 800, fontSize: 16 }}>{loc.name}</div>
                    <div style={{ fontSize: 12, color: C.textMuted }}>{loc.role}</div>
                  </div>
                  <ScorePill score={loc.health} />
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
                      <span style={{ fontSize: 11, color: C.textMuted }}>Current Load</span>
                      <span style={{ fontSize: 11, fontWeight: 700, color: loc.load > 80 ? C.warning : C.textSec }}>{loc.load}%</span>
                    </div>
                    <UsageBar usage={loc.load} />
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <div style={{ flex: 1, background: C.s2, borderRadius: 8, padding: "8px 12px", textAlign: "center" }}>
                      <div style={{ fontSize: 10, color: C.textMuted }}>Status</div>
                      <div style={{ fontSize: 12, fontWeight: 700, color: loc.health >= 0.9 ? C.success : C.warning, marginTop: 2 }}>
                        {loc.health >= 0.9 ? "● Healthy" : "● Warning"}
                      </div>
                    </div>
                    <div style={{ flex: 1, background: C.s2, borderRadius: 8, padding: "8px 12px", textAlign: "center" }}>
                      <div style={{ fontSize: 10, color: C.textMuted }}>QuantumShift</div>
                      <div style={{ fontSize: 12, fontWeight: 700, color: C.textSec, marginTop: 2 }}>Standby</div>
                    </div>
                  </div>
                </div>
              </Panel>
            ))}
          </div>
        )}

        {activeTab === "services" && (
          <Panel title="Registered Services — Dependency Monitor">
            <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
              <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 2fr 1fr", gap: 12, padding: "6px 12px", fontSize: 10, color: C.textMuted, textTransform: "uppercase", letterSpacing: 1 }}>
                <span>Service</span><span>Tier</span><span>Category</span><span>Usage</span><span>Score</span>
              </div>
              {SERVICES.map(svc => (
                <div key={svc.name} style={{
                  display: "grid", gridTemplateColumns: "2fr 1fr 1fr 2fr 1fr", gap: 12,
                  padding: "12px 12px", background: C.s2, borderRadius: 8, alignItems: "center",
                  border: `1px solid ${svc.usage >= 80 ? C.warning + "33" : C.border}`,
                }}>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>{svc.name}</div>
                  <div style={{
                    fontSize: 10, fontWeight: 700, letterSpacing: 0.5,
                    color: svc.tier === "primary" ? C.primary : C.textMuted,
                    background: svc.tier === "primary" ? C.primaryGhost : C.s3,
                    borderRadius: 4, padding: "2px 8px", textAlign: "center",
                    width: "fit-content",
                  }}>{svc.tier}</div>
                  <div style={{ fontSize: 11, color: C.textMuted }}>{svc.category}</div>
                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                      <span style={{ fontSize: 10, color: C.textMuted }}>{svc.limit}</span>
                      <span style={{ fontSize: 10, fontWeight: 700, color: svc.usage >= 80 ? C.warning : C.textSec }}>{svc.usage}%</span>
                    </div>
                    <UsageBar usage={svc.usage} />
                  </div>
                  <ScorePill score={svc.score} />
                </div>
              ))}
            </div>
            <div style={{ marginTop: 16, padding: "12px 14px", background: C.s2, borderRadius: 8, display: "flex", gap: 24 }}>
              <div><span style={{ fontSize: 11, color: C.textMuted }}>Total cost: </span><span style={{ fontSize: 13, fontWeight: 800, color: C.success }}>$0.00/month</span></div>
              <div><span style={{ fontSize: 11, color: C.textMuted }}>Zero-cost mandate: </span><span style={{ fontSize: 13, fontWeight: 800, color: C.success }}>✓ COMPLIANT</span></div>
              <div><span style={{ fontSize: 11, color: C.textMuted }}>Failover tiers: </span><span style={{ fontSize: 13, fontWeight: 800, color: C.primary }}>All configured</span></div>
            </div>
          </Panel>
        )}

        {activeTab === "skills" && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <Panel title="Skills by Category" accent={C.primary} style={{ gridColumn: "1 / -1" }}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
                {SKILL_CATEGORIES.map(cat => (
                  <div key={cat.name} style={{
                    background: C.s2, borderRadius: 10, padding: "14px 16px",
                    border: `1px solid ${cat.color}22`, cursor: "pointer",
                  }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                      <div style={{ width: 10, height: 10, borderRadius: "50%", background: cat.color, boxShadow: `0 0 8px ${cat.color}` }} />
                      <span style={{ fontSize: 20, fontWeight: 900, color: cat.color }}>{cat.count}</span>
                    </div>
                    <div style={{ fontSize: 12, fontWeight: 600, textTransform: "capitalize" }}>{cat.name}</div>
                    <div style={{ fontSize: 10, color: C.textMuted, marginTop: 2 }}>skills</div>
                    <div style={{ marginTop: 8 }}>
                      <UsageBar usage={(cat.count / 28) * 100} color={cat.color} />
                    </div>
                  </div>
                ))}
              </div>
            </Panel>

            <Panel title="Meta-Bundles" accent={C.accent}>
              {[
                { id: "spark-ignition", name: "⚡ Spark Ignition", count: 28, desc: "Master trigger — fires on build/create/implement" },
                { id: "frontend", name: "🎨 Frontend App", count: 13, desc: "React · Next.js · Tailwind · Glassmorphism" },
                { id: "backend", name: "⚙️ Backend API", count: 17, desc: "TypeScript · Auth · DB · Encryption" },
                { id: "ai", name: "🧠 AI Orchestration", count: 13, desc: "RAG · LangChain · Embeddings · Agents" },
                { id: "security", name: "🛡️ Security & Compliance", count: 12, desc: "OWASP · Zero Trust · Regulation Matrix" },
                { id: "devops", name: "🚀 DevOps & Deploy", count: 12, desc: "Docker · GitHub Actions · IaC · GitOps" },
                { id: "data", name: "📊 Data Pipeline", count: 12, desc: "ETL · GDPR · Residency · Retention" },
                { id: "review", name: "🔍 Trancendos Review", count: 12, desc: "Technical · Compliance · Cost · Resilience" },
              ].map(b => (
                <div key={b.id} style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                  padding: "10px 12px", borderRadius: 8, background: C.s2,
                  marginBottom: 6, border: `1px solid ${C.border}`,
                }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 700 }}>{b.name}</div>
                    <div style={{ fontSize: 11, color: C.textMuted }}>{b.desc}</div>
                  </div>
                  <div style={{
                    background: C.accentGhost, color: C.accent, border: `1px solid ${C.accent}33`,
                    borderRadius: 20, padding: "2px 10px", fontSize: 11, fontWeight: 700,
                  }}>{b.count}</div>
                </div>
              ))}
            </Panel>

            <Panel title="Compliance Coverage" accent={C.info}>
              {[
                { fw: "GDPR", score: 1.0, articles: "Art.5,6,13,17,25,32,33,35" },
                { fw: "UK-GDPR", score: 0.97, articles: "DPDPD Act 2024 deviations" },
                { fw: "Magna Carta", score: 0.95, articles: "User ownership · Zero lock-in" },
                { fw: "PRINCE2 7", score: 0.92, articles: "7 principles · 7 themes · 7 processes" },
                { fw: "ITIL 4", score: 0.88, articles: "34 practices · SVS" },
                { fw: "Zero-Cost", score: 1.0, articles: "All services within free tiers" },
              ].map(fw => (
                <div key={fw.fw} style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 0", borderBottom: `1px solid ${C.border}` }}>
                  <div style={{ width: 70, fontSize: 12, fontWeight: 700, color: C.text }}>{fw.fw}</div>
                  <div style={{ flex: 1 }}>
                    <UsageBar usage={fw.score * 100} color={fw.score >= 0.95 ? C.success : fw.score >= 0.85 ? C.warning : C.danger} />
                    <div style={{ fontSize: 10, color: C.textMuted, marginTop: 3 }}>{fw.articles}</div>
                  </div>
                  <ScorePill score={fw.score} />
                </div>
              ))}
            </Panel>
          </div>
        )}

        {activeTab === "events" && (
          <Panel title="Nanofibers Event Stream — Full Log" accent={C.info}>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {RECENT_EVENTS.map((ev, i) => (
                <div key={i} style={{
                  display: "flex", gap: 12, padding: "10px 12px",
                  background: C.s2, borderRadius: 8,
                  borderLeft: `3px solid ${{ info: C.info, success: C.success, warning: C.warning, error: C.danger }[ev.type]}`,
                }}>
                  <div style={{ width: 60, fontSize: 11, color: C.textMuted, flexShrink: 0, paddingTop: 1 }}>{ev.time}</div>
                  <div style={{ width: 64, flexShrink: 0 }}>
                    <span style={{
                      fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5,
                      color: { info: C.info, success: C.success, warning: C.warning, error: C.danger }[ev.type],
                      background: { info: `${C.info}15`, success: `${C.success}15`, warning: `${C.warning}15`, error: `${C.danger}15` }[ev.type],
                      borderRadius: 4, padding: "2px 6px",
                    }}>{ev.type}</span>
                  </div>
                  <div style={{ fontSize: 13, color: C.textSec, flex: 1 }}>{ev.msg}</div>
                </div>
              ))}
            </div>
          </Panel>
        )}

        {/* ── Footer ── */}
        <div style={{ marginTop: 24, textAlign: "center", color: C.textMuted, fontSize: 11 }}>
          <span>⚡ The Spark v2.0.0 · </span>
          <span style={{ color: C.primary }}>Infy</span>
          <span> · Trancendos · Zero-Cost · GDPR-Compliant · Self-Healing · 2060-Proof</span>
        </div>
      </div>
    </div>
  );
}
