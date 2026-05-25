/**
 * RenikAI — Lead AI for The Cryptex Hub
 *
 * Identity:  AID-CRYPTEX-RENIK
 * Pillar:    Renik
 * Tier:      3 (Lead AI / Domain Orchestrator)
 * Domain:    Cyber defense, threat intelligence, CVE tracking, vulnerability assessment,
 *            attack surface analysis, security posture management, incident triage
 *
 * Philosophy: The Cryptex is the shield that thinks — a living security perimeter
 *             that does not wait for attacks but hunts them. Renik does not merely
 *             defend; it anticipates, predicts, and neutralizes. Every vulnerability
 *             is a crack in the shell; every threat intel feed is a whisper of intent.
 *             The Cryptex seals the cracks before the pressure breaks through.
 *
 * Fluidic Architecture:
 *   - ThreatIntel: Fluidic threat intelligence with confidence decay
 *   - VulnerabilityEntry: Particle-based CVE tracking with exploit probability
 *   - AttackSurface: CognitiveIsotope of exposed assets and attack vectors
 *   - SecurityPosture: Thermodynamic assessment of defense readiness
 *
 * Pipeline:  ThreatAgent (hunt/assess/triage/patch) → CipherBot (ENCRYPT/DECRYPT/HASH/SIGN/VERIFY)
 */

import { AI, Agent, Bot, Logger, AuditLedger } from '../../core/definitions'
import { ThreatAgent } from './agents/ThreatAgent';
import { CipherBot } from './bots/CipherBot';

const auditLedger = new AuditLedger();

// ─────────────────────────────────────────────────────────────────────────────
// Domain Interfaces
// ─────────────────────────────────────────────────────────────────────────────

export interface ThreatIntel {
  id: string;
  type: 'apt' | 'malware' | 'phishing' | 'zero_day' | 'ddos' | 'insider' | 'supply_chain' | 'misconfiguration';
  severity: 'info' | 'low' | 'medium' | 'high' | 'critical';
  source: string;
  confidence: number;
  iocs: string[];
  description: string;
  affectedSystems: string[];
  mitreTactics: string[];
  firstSeen: Date;
  lastSeen: Date;
  decayRate: number;
  metadata: Record<string, unknown>;
}

export interface VulnerabilityEntry {
  id: string;
  cveId: string;
  title: string;
  severity: 'none' | 'low' | 'medium' | 'high' | 'critical';
  cvssScore: number;
  exploitProbability: number;
  affectedComponent: string;
  affectedVersions: string[];
  patchAvailable: boolean;
  patchVersion: string | null;
  publishedAt: Date;
  updatedAt: Date;
  references: string[];
  metadata: Record<string, unknown>;
}

export interface AttackSurface {
  id: string;
  assetId: string;
  assetType: 'server' | 'container' | 'service' | 'api' | 'endpoint' | 'database' | 'network';
  exposedPorts: number[];
  protocols: string[];
  riskScore: number;
  vulnerabilities: string[];
  lastAssessed: Date;
  metadata: Record<string, unknown>;
}

export interface SecurityPosture {
  id: string;
  overallScore: number;
  vulnerabilityCount: number;
  criticalCount: number;
  threatLevel: 'minimal' | 'low' | 'moderate' | 'high' | 'critical';
  lastIncident: Date | null;
  complianceScore: number;
  assessedAt: Date;
}

// ─────────────────────────────────────────────────────────────────────────────
// RenikAI Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class RenikAI extends AI {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private threats: Map<string, ThreatIntel>;
  private vulnerabilities: Map<string, VulnerabilityEntry>;
  private surfaces: Map<string, AttackSurface>;
  private posture: SecurityPosture | null;
  private threatCounter: number;
  private vulnCounter: number;

  constructor() {
    super('AID-CRYPTEX-RENIK', 'Renik', 'cryptex', 'Renik', 3);
    this.log = new Logger('RenikAI');
    this.audit = auditLedger;
    this.threats = new Map();
    this.vulnerabilities = new Map();
    this.surfaces = new Map();
    this.posture = null;
    this.threatCounter = 0;
    this.vulnCounter = 0;

    this.registerAgent(new ThreatAgent());
    this.registerBot(new CipherBot());

    this.log.info('RenikAI initialised', {
      agents: this.listAgentIds(),
      bots: this.listBotNames(),
      message: 'The Cryptex is sealed. Renik watches. All threats shall be found. 🛡️',
    });
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Threat Intelligence
  // ─────────────────────────────────────────────────────────────────────────

  registerThreat(params: Omit<ThreatIntel, 'id' | 'firstSeen' | 'lastSeen' | 'decayRate'>): ThreatIntel {
    this.threatCounter++;
    const threat: ThreatIntel = {
      ...params,
      id: `THREAT-${this.threatCounter.toString().padStart(8, '0')}`,
      firstSeen: new Date(),
      lastSeen: new Date(),
      decayRate: 0.01,
    };
    this.threats.set(threat.id, threat);
    this.audit.append({ actor: 'RenikAI', action: 'REGISTER_THREAT', entity: threat.id, status: 'SUCCESS', details: { type: threat.type, severity: threat.severity } });
    return threat;
  }

  getThreat(threatId: string): ThreatIntel | undefined {
    return this.threats.get(threatId);
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Vulnerability Management
  // ─────────────────────────────────────────────────────────────────────────

  registerVulnerability(params: Omit<VulnerabilityEntry, 'id' | 'publishedAt' | 'updatedAt'>): VulnerabilityEntry {
    this.vulnCounter++;
    const vuln: VulnerabilityEntry = {
      ...params,
      id: `VULN-${this.vulnCounter.toString().padStart(8, '0')}`,
      publishedAt: new Date(),
      updatedAt: new Date(),
    };
    this.vulnerabilities.set(vuln.id, vuln);
    this.log.info('Vulnerability registered', { id: vuln.id, cveId: vuln.cveId, severity: vuln.severity });
    return vuln;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Bot / Agent Delegations
  // ─────────────────────────────────────────────────────────────────────────

  async threatOperation(
    operation: 'hunt' | 'assess' | 'triage' | 'patch',
    params: Record<string, unknown>
  ): Promise<unknown> {
    const agent = this.getAgent('SID-CRYPTEX-THREAT') as ThreatAgent;
    return agent.runCycle({ operation, ...params });
  }

  async cipherOperation(params: { action: 'ENCRYPT' | 'DECRYPT' | 'HASH' | 'SIGN' | 'VERIFY'; data?: string; algorithm?: string }): Promise<unknown> {
    const bot = this.getBot('Cipher')!;
    return bot.execute(params);
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Proactive Systems
  // ─────────────────────────────────────────────────────────────────────────

  /** Proactive threat confidence decay — reduce stale intel confidence */
  decayThreatConfidence(): number {
    let decayed = 0;
    for (const [, threat] of this.threats) {
      threat.confidence = Math.max(0, threat.confidence - threat.decayRate);
      if (threat.confidence < 0.1) {
        this.threats.delete(threat.id);
        decayed++;
      }
    }
    if (decayed > 0) this.log.info('Proactive threat decay', { removed: decayed });
    return decayed;
  }

  /** Proactive vulnerability scan — check for unpatched critical vulns */
  scanUnpatchedVulnerabilities(): VulnerabilityEntry[] {
    return Array.from(this.vulnerabilities.values()).filter(
      v => !v.patchAvailable && v.severity === 'critical'
    );
  }

  healthCheck(): {
    status: 'healthy' | 'degraded' | 'critical';
    threats: number;
    vulnerabilities: number;
    criticalVulns: number;
    attackSurfaces: number;
    postureScore: number;
    agents: number;
    bots: number;
    timestamp: Date;
  } {
    const criticalVulns = Array.from(this.vulnerabilities.values()).filter(v => v.severity === 'critical').length;
    return {
      status: criticalVulns > 5 ? 'critical' : criticalVulns > 0 ? 'degraded' : 'healthy',
      threats: this.threats.size,
      vulnerabilities: this.vulnerabilities.size,
      criticalVulns,
      attackSurfaces: this.surfaces.size,
      postureScore: this.posture?.overallScore ?? 100,
      agents: this.listAgentIds().length,
      bots: this.listBotNames().length,
      timestamp: new Date(),
    };
  }
}
