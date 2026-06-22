import type { Meta, StoryObj } from "@storybook/react";
import { ThreatCard } from "@/components/shadcn/threat-card";
import { SecurityEngineStatus } from "@/components/shadcn/security-engine-status";

// ── ThreatCard ────────────────────────────────────────────────────────────────

const threatMeta: Meta<typeof ThreatCard> = {
  title: "Cryptex / ThreatCard",
  component: ThreatCard,
  parameters: { layout: "centered" },
  decorators: [(Story) => <div style={{ width: 380 }}><Story /></div>],
};
export default threatMeta;

type ThreatStory = StoryObj<typeof ThreatCard>;

export const Clean: ThreatStory = {
  args: {
    scanId: "abc12345-0000-0000-0000-000000000001",
    scanType: "file",
    target: "/tmp/suspicious_file.exe",
    status: "completed",
    engineUsed: "clamav",
    threatFound: false,
    severity: "info",
    startedAt: new Date().toISOString(),
    completedAt: new Date().toISOString(),
  },
};

export const ThreatDetectedHigh: ThreatStory = {
  args: {
    scanId: "abc12345-0000-0000-0000-000000000002",
    scanType: "ioc",
    target: "185.220.101.50",
    status: "completed",
    engineUsed: "wazuh",
    threatFound: true,
    severity: "high",
    findings: [
      { rule_id: "87703", description: "IP associated with TOR exit node", level: 10 },
      { rule_id: "87704", description: "Multiple failed login attempts", level: 9 },
    ],
    startedAt: new Date().toISOString(),
    completedAt: new Date().toISOString(),
  },
};

export const CriticalMalware: ThreatStory = {
  args: {
    scanId: "abc12345-0000-0000-0000-000000000003",
    scanType: "file",
    target: "/uploads/document.pdf",
    status: "completed",
    engineUsed: "clamav",
    threatFound: true,
    severity: "critical",
    findings: [{ virus: "Trojan.GenericKD.69420" }, { virus: "Exploit.PDF.CVE-2023-1234" }],
    startedAt: new Date().toISOString(),
    completedAt: new Date().toISOString(),
  },
};

export const SASTFindings: ThreatStory = {
  args: {
    scanId: "abc12345-0000-0000-0000-000000000004",
    scanType: "sast",
    target: "/app/src/api.py",
    status: "completed",
    engineUsed: "semgrep",
    threatFound: true,
    severity: "medium",
    findings: [
      { check_id: "python.flask.security.injection.taint-sql-injection", path: "api.py", line: 42 },
      { check_id: "python.requests.security.no-auth.missing-auth", path: "api.py", line: 88 },
    ],
    startedAt: new Date().toISOString(),
    completedAt: new Date().toISOString(),
  },
};

export const Running: ThreatStory = {
  args: {
    scanId: "abc12345-0000-0000-0000-000000000005",
    scanType: "vulnerability",
    target: "192.168.1.0/24",
    status: "running",
    engineUsed: "openvas",
    threatFound: false,
    severity: "unknown",
    startedAt: new Date().toISOString(),
  },
};

export const GlassVariant: ThreatStory = {
  decorators: [
    (Story) => (
      <div
        style={{
          width: 380,
          background: "linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)",
          padding: 24,
          borderRadius: 12,
        }}
      >
        <Story />
      </div>
    ),
  ],
  args: {
    scanId: "abc12345-0000-0000-0000-000000000006",
    scanType: "threat_intel",
    target: "phishing-domain.xyz",
    status: "completed",
    engineUsed: "misp",
    threatFound: true,
    severity: "high",
    findings: [{ event_id: "4427", type: "domain", category: "Network activity" }],
    startedAt: new Date().toISOString(),
    completedAt: new Date().toISOString(),
    variant: "glass",
  },
};

// ── SecurityEngineStatus ──────────────────────────────────────────────────────

const MOCK_ENGINES = [
  { engine: "wazuh", healthy: true, pheromone: 0.85, requests_in_window: 42, threshold: 500, blocked: false },
  { engine: "misp", healthy: true, pheromone: 0.8, requests_in_window: 15, threshold: 500, blocked: false },
  { engine: "openvas", healthy: false, pheromone: 0.3, requests_in_window: 0, threshold: 100, blocked: false },
  { engine: "clamav", healthy: true, pheromone: 0.75, requests_in_window: 230, threshold: 1000, blocked: false },
  { engine: "yara", healthy: true, pheromone: 0.65, requests_in_window: 89, threshold: 1000, blocked: false },
  { engine: "suricata", healthy: false, pheromone: 0.2, requests_in_window: 0, threshold: 500, blocked: false },
  { engine: "semgrep", healthy: true, pheromone: 0.55, requests_in_window: 195, threshold: 200, blocked: false },
  { engine: "offline", healthy: true, pheromone: 0.1, requests_in_window: 3, threshold: 999999, blocked: false },
];

export const EngineStatusPanel: StoryObj<typeof SecurityEngineStatus> = {
  render: () => <SecurityEngineStatus engines={MOCK_ENGINES} />,
  parameters: { layout: "centered" },
  decorators: [(Story) => <div style={{ width: 480 }}><Story /></div>],
};

export const EngineStatusGlass: StoryObj<typeof SecurityEngineStatus> = {
  render: () => <SecurityEngineStatus engines={MOCK_ENGINES} variant="glass" />,
  parameters: { layout: "centered" },
  decorators: [
    (Story) => (
      <div
        style={{
          width: 480,
          background: "linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%)",
          padding: 24,
          borderRadius: 12,
        }}
      >
        <Story />
      </div>
    ),
  ],
};

export const FullSecurityDashboard: StoryObj = {
  render: () => (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 380px)", gap: 16 }}>
      <ThreatCard
        scanId="scan-001" scanType="file" target="/var/uploads/payload.bin"
        status="completed" engineUsed="clamav" threatFound={true} severity="critical"
        findings={[{ virus: "Ransomware.Lockbit.3" }]}
        startedAt={new Date().toISOString()} completedAt={new Date().toISOString()}
      />
      <ThreatCard
        scanId="scan-002" scanType="ioc" target="evil-c2.onion"
        status="completed" engineUsed="misp" threatFound={true} severity="high"
        findings={[{ event_id: "9001", type: "domain", category: "C2" }]}
        startedAt={new Date().toISOString()} completedAt={new Date().toISOString()}
      />
      <ThreatCard
        scanId="scan-003" scanType="sast" target="/app/auth/login.py"
        status="completed" engineUsed="semgrep" threatFound={false} severity="info"
        startedAt={new Date().toISOString()} completedAt={new Date().toISOString()}
      />
      <ThreatCard
        scanId="scan-004" scanType="vulnerability" target="10.0.0.1"
        status="running" engineUsed="openvas" threatFound={false} severity="unknown"
        startedAt={new Date().toISOString()}
      />
      <div style={{ gridColumn: "span 2" }}>
        <SecurityEngineStatus engines={MOCK_ENGINES} />
      </div>
    </div>
  ),
  parameters: { layout: "centered" },
};
