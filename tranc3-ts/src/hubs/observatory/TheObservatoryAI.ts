/**
 * TheObservatoryAI — Lead AI for The Observatory Hub
 *
 * Identity:  AID-OBSERVATORY
 * Pillar:    The Guardian
 * Tier:      3 (Lead AI / Domain Orchestrator)
 * Domain:    System monitoring, surveillance, celestial pattern recognition,
 *            threat detection, anomaly classification, alert escalation,
 *            cosmic data analysis, predictive observation
 *
 * Philosophy: The Observatory watches over all of Arcadia.
 *             Every flicker of data is a star in the sky — some burn bright
 *             and pass, some signal events yet to come. The Guardian sees
 *             what others miss, for vigilance is the price of safety.
 *
 * Pipeline:  TelescopeBot (scan) → SentinelAgent (watch/detect/classify/escalate)
 *            → StarMapBot (plot) → AstrologerAgent (read/interpret/predict/advise)
 *            → AlertBot (signal)
 */

import { AI, Agent, Bot, Logger, AuditLedger } from '../../core/definitions'
import { SentinelAgent } from './agents/SentinelAgent';
import { AstrologerAgent } from './agents/AstrologerAgent';
import { TelescopeBot } from './bots/TelescopeBot';
import { StarMapBot } from './bots/StarMapBot';
import { AlertBot } from './bots/AlertBot';

const auditLedger = new AuditLedger();

// ─────────────────────────────────────────────────────────────────────────────
// Domain Interfaces
// ─────────────────────────────────────────────────────────────────────────────

export interface Observation {
  id: string;
  source: string;
  type: 'metric' | 'event' | 'log' | 'trace' | 'anomaly' | 'celestial';
  severity: 'info' | 'low' | 'medium' | 'high' | 'critical';
  label: string;
  value: number | string | boolean;
  unit?: string;
  tags: string[];
  timestamp: number;
  sourceHub?: string;
  metadata?: Record<string, unknown>;
}

export interface Anomaly {
  id: string;
  observationId: string;
  classification: string;
  confidence: number;
  riskScore: number;
  description: string;
  detectedAt: number;
  status: 'detected' | 'classified' | 'escalated' | 'resolved' | 'dismissed';
  assignedTo?: string;
  resolvedAt?: number;
  resolution?: string;
}

export interface CelestialPattern {
  id: string;
  name: string;
  type: 'convergence' | 'divergence' | 'eclipse' | 'alignment' | 'nova' | 'void';
  intensity: number;
  affectedSystems: string[];
  predictedImpact: 'benign' | 'minor' | 'moderate' | 'significant' | 'catastrophic';
  observedAt: number;
  peakAt?: number;
  expiresAt?: number;
  metadata?: Record<string, unknown>;
}

export interface AlertSignal {
  id: string;
  source: string;
  level: 'advisory' | 'watch' | 'warning' | 'emergency';
  title: string;
  message: string;
  targetHubs: string[];
  targetAgents: string[];
  originHub: string;
  createdAt: number;
  acknowledgedAt?: number;
  acknowledgedBy?: string;
  expiresAt?: number;
  suppressed: boolean;
  correlatedAlertIds: string[];
}

export interface ObservationFilter {
  source?: string;
  type?: Observation['type'];
  severity?: Observation['severity'];
  tags?: string[];
  fromTimestamp?: number;
  toTimestamp?: number;
  limit?: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// TheObservatoryAI Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class TheObservatoryAI extends AI {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private observations: Map<string, Observation>;
  private anomalies: Map<string, Anomaly>;
  private patterns: Map<string, CelestialPattern>;
  private alerts: Map<string, AlertSignal>;
  private observationCounter: number;

  constructor() {
    super(
      'AID-OBSERVATORY',
      'Observatory',
      'observatory',
      'The Guardian',
      3
    );

    this.log = new Logger('TheObservatoryAI');
    this.audit = auditLedger;
    this.observations = new Map();
    this.anomalies = new Map();
    this.patterns = new Map();
    this.alerts = new Map();
    this.observationCounter = 0;

    // Register Agents
    this.registerAgent(new SentinelAgent());
    this.registerAgent(new AstrologerAgent());

    // Register Bots
    this.registerBot(new TelescopeBot());
    this.registerBot(new StarMapBot());
    this.registerBot(new AlertBot());

    this.log.info('TheObservatoryAI initialised', {
      agents: this.listAgentIds(),
      bots: this.listBotNames(),
      message: 'The Observatory stands vigilant. The Guardian watches. 🔭',
    });
  }

  // ───────────────────────────────────────────────────────────────────────
  // Observation Management
  // ───────────────────────────────────────────────────────────────────────

  addObservation(obs: Omit<Observation, 'id' | 'timestamp'>): Observation {
    this.observationCounter++;
    const observation: Observation = {
      ...obs,
      id: `OBS-${this.observationCounter.toString().padStart(6, '0')}`,
      timestamp: Date.now(),
    };
    this.observations.set(observation.id, observation);

    this.log.info('Observation recorded', {
      id: observation.id,
      type: observation.type,
      severity: observation.severity,
      source: observation.source,
    });

    return observation;
  }

  getObservation(id: string): Observation | undefined {
    return this.observations.get(id);
  }

  queryObservations(filter?: ObservationFilter): Observation[] {
    let results = Array.from(this.observations.values());

    if (filter) {
      if (filter.source) results = results.filter(o => o.source === filter.source);
      if (filter.type) results = results.filter(o => o.type === filter.type);
      if (filter.severity) results = results.filter(o => o.severity === filter.severity);
      if (filter.tags && filter.tags.length > 0) {
        results = results.filter(o => filter.tags!.some(t => o.tags.includes(t)));
      }
      if (filter.fromTimestamp) results = results.filter(o => o.timestamp >= filter.fromTimestamp!);
      if (filter.toTimestamp) results = results.filter(o => o.timestamp <= filter.toTimestamp!);
      if (filter.limit) results = results.slice(-filter.limit);
    }

    return results.sort((a, b) => b.timestamp - a.timestamp);
  }

  // ───────────────────────────────────────────────────────────────────────
  // Anomaly Management
  // ───────────────────────────────────────────────────────────────────────

  addAnomaly(anomaly: Anomaly): void {
    this.anomalies.set(anomaly.id, anomaly);
    this.log.warn('Anomaly registered', {
      id: anomaly.id,
      classification: anomaly.classification,
      confidence: anomaly.confidence,
      riskScore: anomaly.riskScore,
      status: anomaly.status,
    });
  }

  getAnomaly(id: string): Anomaly | undefined {
    return this.anomalies.get(id);
  }

  getAnomalies(status?: Anomaly['status']): Anomaly[] {
    const all = Array.from(this.anomalies.values());
    return status ? all.filter(a => a.status === status) : all;
  }

  // ───────────────────────────────────────────────────────────────────────
  // Celestial Pattern Management
  // ───────────────────────────────────────────────────────────────────────

  addPattern(pattern: CelestialPattern): void {
    this.patterns.set(pattern.id, pattern);
    this.log.info('Celestial pattern identified', {
      id: pattern.id,
      name: pattern.name,
      type: pattern.type,
      intensity: pattern.intensity,
      predictedImpact: pattern.predictedImpact,
    });
  }

  getPattern(id: string): CelestialPattern | undefined {
    return this.patterns.get(id);
  }

  getActivePatterns(): CelestialPattern[] {
    const now = Date.now();
    return Array.from(this.patterns.values())
      .filter(p => !p.expiresAt || p.expiresAt > now);
  }

  // ───────────────────────────────────────────────────────────────────────
  // Alert Management
  // ───────────────────────────────────────────────────────────────────────

  getAlert(id: string): AlertSignal | undefined {
    return this.alerts.get(id);
  }

  getAlerts(level?: AlertSignal['level']): AlertSignal[] {
    const all = Array.from(this.alerts.values());
    return level ? all.filter(a => a.level === level) : all;
  }

  // ───────────────────────────────────────────────────────────────────────
  // Bot Delegations
  // ───────────────────────────────────────────────────────────────────────

  /**
   * Scan the environment via TelescopeBot.
   */
  async scanEnvironment(
    target: string,
    scanType: 'full' | 'targeted' | 'deep' | 'surface',
    depth?: number
  ): Promise<unknown> {
    const telescope = this.getBot('Telescope')!;
    const result = await telescope.execute({
      operation: 'SCAN',
      target,
      scanType,
      depth,
    });
    return result;
  }

  /**
   * Plot celestial patterns via StarMapBot.
   */
  async plotPattern(
    patternType: 'convergence' | 'divergence' | 'eclipse' | 'alignment' | 'nova' | 'void',
    entities: string[],
    timeframe?: string
  ): Promise<unknown> {
    const starMap = this.getBot('StarMap')!;
    const result = await starMap.execute({
      operation: 'PLOT',
      patternType,
      entities,
      timeframe,
    });
    return result;
  }

  /**
   * Emit alert signal via AlertBot.
   */
  async emitSignal(
    level: 'advisory' | 'watch' | 'warning' | 'emergency',
    title: string,
    message: string,
    targetHubs?: string[]
  ): Promise<unknown> {
    const alert = this.getBot('Alert')!;
    const result = await alert.execute({
      operation: 'SIGNAL',
      level,
      title,
      message,
      targetHubs: targetHubs ?? [],
    });
    return result;
  }

  // ───────────────────────────────────────────────────────────────────────
  // Agent Delegations
  // ───────────────────────────────────────────────────────────────────────

  /**
   * Monitor and detect threats via SentinelAgent.
   */
  async monitor(
    operation: 'watch' | 'detect' | 'classify' | 'escalate',
    params: Record<string, unknown>
  ): Promise<unknown> {
    const sentinel = this.getAgent('SID-OBSERVATORY-SENTINEL') as SentinelAgent;
    const result = await sentinel.runCycle({
      operation,
      ...params,
    });
    return result;
  }

  /**
   * Read and interpret patterns via AstrologerAgent.
   */
  async interpret(
    operation: 'read' | 'interpret' | 'predict' | 'advise',
    params: Record<string, unknown>
  ): Promise<unknown> {
    const astrologer = this.getAgent('SID-OBSERVATORY-ASTROLOGER') as AstrologerAgent;
    const result = await astrologer.runCycle({
      operation,
      ...params,
    });
    return result;
  }

  // ───────────────────────────────────────────────────────────────────────
  // Health Check
  // ───────────────────────────────────────────────────────────────────────

  healthCheck(): {
    status: 'healthy' | 'degraded' | 'critical';
    totalObservations: number;
    activeAnomalies: number;
    activePatterns: number;
    activeAlerts: number;
    agents: number;
    bots: number;
    uptime: number;
    timestamp: number;
  } {
    const activeAnomalies = this.getAnomalies()
      .filter(a => a.status === 'detected' || a.status === 'classified' || a.status === 'escalated').length;
    const activeAlerts = this.getAlerts()
      .filter(a => !a.suppressed && !a.acknowledgedAt).length;
    const criticalAnomalies = this.getAnomalies()
      .filter(a => a.riskScore >= 80 && a.status !== 'resolved' && a.status !== 'dismissed').length;

    const status: 'healthy' | 'degraded' | 'critical' =
      criticalAnomalies > 3 ? 'critical' :
      activeAnomalies > 10 || activeAlerts > 5 ? 'degraded' :
      'healthy';

    return {
      status,
      totalObservations: this.observations.size,
      activeAnomalies,
      activePatterns: this.getActivePatterns().length,
      activeAlerts,
      agents: this.listAgentIds().length,
      bots: this.listBotNames().length,
      uptime: Date.now(),
      timestamp: Date.now(),
    };
  }
}
