/**
 * AlertBot — Signal Emission & Alert Management Bot for The Observatory
 *
 * Identity:  NID-OBSERVATORY-ALERT
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TheObservatoryAI (AID-OBSERVATORY)
 *
 * Responsibilities:
 *   - SIGNAL: Emit, manage, and track alert signals across the ecosystem
 *   - Route alerts to appropriate hubs and agents
 *   - Correlate related alerts and suppress duplicates
 *   - Manage alert lifecycle: emit → acknowledge → resolve
 *   - Maintain alert history for audit and trend analysis
 *
 * "A signal unseen is no signal at all. The AlertBot ensures every warning finds its witness."
 */

import { Bot, Logger, AuditLedger } from '../../../core/definitions';

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface AlertInput {
  operation: 'SIGNAL';
  level: 'advisory' | 'watch' | 'warning' | 'emergency';
  title: string;
  message: string;
  targetHubs?: string[];
  targetAgents?: string[];
  sourceAgent?: string;
  anomalyId?: string;
  patternId?: string;
  correlationId?: string;
  ttl?: number;  // Time-to-live in milliseconds
  suppressDuplicates?: boolean;
  duplicateWindowMs?: number;
}

export interface AlertRecord {
  id: string;
  level: AlertInput['level'];
  title: string;
  message: string;
  sourceAgent: string;
  targetHubs: string[];
  targetAgents: string[];
  anomalyId?: string;
  patternId?: string;
  correlationId?: string;
  status: 'emitted' | 'acknowledged' | 'escalated' | 'resolved' | 'expired' | 'suppressed';
  emittedAt: number;
  acknowledgedAt?: number;
  acknowledgedBy?: string;
  resolvedAt?: number;
  resolvedBy?: string;
  resolution?: string;
  expiresAt: number;
  suppressionReason?: string;
  duplicateGroupId?: string;
  deliveryStatus: Record<string, 'pending' | 'delivered' | 'failed'>;
  timesEscalated: number;
  timesReemitted: number;
}

export interface AlertSummary {
  totalAlerts: number;
  byLevel: Record<AlertInput['level'], number>;
  byStatus: Record<AlertRecord['status'], number>;
  activeAlerts: number;
  emergencyCount: number;
  averageTimeToAcknowledge: number;
  averageTimeToResolve: number;
  suppressionRate: number;
  topSources: { source: string; count: number }[];
  alertTrend: 'increasing' | 'stable' | 'decreasing';
  timestamp: number;
}

export interface SignalResult {
  success: boolean;
  alert: AlertRecord;
  correlatedAlerts: AlertRecord[];
  summary: AlertSummary;
  routing: { hub: string; status: 'routed' | 'skipped' | 'failed' }[];
  message: string;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Alert Storage
// ─────────────────────────────────────────────────────────────────────────────

const ALL_HUBS = [
  'arcadia-hub', 'luminous-hub', 'townhall-hub', 'studio-hub', 'sashas-hub',
  'tranceflow-hub', 'tateking-hub', 'fabulousa-hub', 'docutari-hub', 'basement-hub',
  'imaginarium-hub', 'digitalgrid-hub', 'lab-hub', 'workshop-hub', 'chaosparty-hub',
  'artifactory-hub', 'apimarketplace-hub', 'royalbank-hub', 'arcadianexchange-hub', 'observatory-hub',
];

let alertCounter = 0;
let duplicateGroupCounter = 0;
const alertHistory: Map<string, AlertRecord> = new Map();

// ─────────────────────────────────────────────────────────────────────────────
// AlertBot Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class AlertBot extends Bot {
  private readonly log: Logger;
  private readonly audit: AuditLedger;

  constructor() {
    super(
      'NID-OBSERVATORY-ALERT',
      'Alert',
      async (input: AlertInput) => this.handle(input),
      'Alert signal emission with routing, correlation, suppression, and lifecycle management'
    );

    this.log = new Logger('AlertBot');
    this.audit = AuditLedger.getInstance();
  }

  private async handle(input: AlertInput): Promise<SignalResult> {
    if (input.operation !== 'SIGNAL') {
      return this.fail(`Unknown operation: ${input.operation}. AlertBot only accepts SIGNAL.`);
    }
    return this.signal(input);
  }

  // ───────────────────────────────────────────────────────────────────────
  // SIGNAL — Emit an alert
  // ───────────────────────────────────────────────────────────────────────

  private signal(input: AlertInput): SignalResult {
    const {
      level,
      title,
      message,
      targetHubs,
      targetAgents,
      sourceAgent,
      anomalyId,
      patternId,
      correlationId,
      ttl,
      suppressDuplicates,
      duplicateWindowMs,
    } = input;

    if (!title || !message) {
      return this.fail('Alert title and message are required');
    }

    const resolvedTargetHubs = targetHubs && targetHubs.length > 0
      ? targetHubs
      : this.inferTargetHubs(level);

    const resolvedSourceAgent = sourceAgent ?? 'SID-OBSERVATORY-SENTINEL';
    const defaultTtl = level === 'emergency' ? 3600000 : level === 'warning' ? 1800000 : level === 'watch' ? 900000 : 600000;

    // Check for duplicate suppression
    const suppressWindow = duplicateWindowMs ?? 300000; // 5-minute default window
    if (suppressDuplicates !== false) {
      const duplicate = this.findDuplicate(title, resolvedSourceAgent, suppressWindow);
      if (duplicate) {
        duplicateGroupCounter++;
        alertCounter++;

        const suppressedAlert: AlertRecord = {
          id: `ALERT-${alertCounter.toString().padStart(6, '0')}`,
          level,
          title,
          message,
          sourceAgent: resolvedSourceAgent,
          targetHubs: resolvedTargetHubs,
          targetAgents: targetAgents ?? [],
          anomalyId,
          patternId,
          correlationId,
          status: 'suppressed',
          emittedAt: Date.now(),
          expiresAt: Date.now() + (ttl ?? defaultTtl),
          suppressionReason: `Duplicate of ${duplicate.id} emitted ${Math.round((Date.now() - duplicate.emittedAt) / 1000)}s ago`,
          duplicateGroupId: duplicate.duplicateGroupId ?? `DUP-${duplicateGroupCounter}`,
          deliveryStatus: {},
          timesEscalated: 0,
          timesReemitted: 0,
        };

        alertHistory.set(suppressedAlert.id, suppressedAlert);

        this.log.info('Alert suppressed as duplicate', {
          suppressedId: suppressedAlert.id,
          originalId: duplicate.id,
          title,
        });

        return {
          success: true,
          alert: suppressedAlert,
          correlatedAlerts: [duplicate],
          summary: this.buildSummary(),
          routing: [],
          message: `Alert suppressed as duplicate of ${duplicate.id} (${suppressedAlert.suppressionReason})`,
          timestamp: Date.now(),
        };
      }
    }

    // Create the alert
    alertCounter++;
    const alert: AlertRecord = {
      id: `ALERT-${alertCounter.toString().padStart(6, '0')}`,
      level,
      title,
      message,
      sourceAgent: resolvedSourceAgent,
      targetHubs: resolvedTargetHubs,
      targetAgents: targetAgents ?? [],
      anomalyId,
      patternId,
      correlationId,
      status: 'emitted',
      emittedAt: Date.now(),
      expiresAt: Date.now() + (ttl ?? defaultTtl),
      deliveryStatus: Object.fromEntries(
        resolvedTargetHubs.map(hub => [hub, 'pending' as const])
      ),
      timesEscalated: 0,
      timesReemitted: 0,
    };

    alertHistory.set(alert.id, alert);

    // Route to target hubs
    const routing: SignalResult['routing'] = resolvedTargetHubs.map(hub => {
      if (ALL_HUBS.includes(hub)) {
        alert.deliveryStatus[hub] = 'delivered';
        return { hub, status: 'routed' as const };
      }
      alert.deliveryStatus[hub] = 'failed';
      return { hub, status: 'failed' as const };
    });

    // Find correlated alerts
    const correlatedAlerts = this.findCorrelatedAlerts(alert);

    // Auto-escalate emergency alerts
    if (level === 'emergency') {
      alert.timesEscalated++;
    }

    const summary = this.buildSummary();

    this.audit.append({
      actor: 'NID-OBSERVATORY-ALERT',
      action: 'ALERT_EMITTED',
      entity: alert.id,
      status: 'SUCCESS',
      meta: {
        level,
        title,
        targetHubs: resolvedTargetHubs,
        sourceAgent: resolvedSourceAgent,
        anomalyId,
        patternId,
        correlationId,
      },
    });

    this.log.info('Alert emitted', {
      alertId: alert.id,
      level,
      title,
      targetHubs: resolvedTargetHubs,
      sourceAgent: resolvedSourceAgent,
    });

    if (level === 'emergency') {
      this.log.error('EMERGENCY ALERT EMITTED', {
        alertId: alert.id,
        title,
        message,
      });
    }

    return {
      success: true,
      alert,
      correlatedAlerts,
      summary,
      routing,
      message: `${level.toUpperCase()} alert ${alert.id}: "${title}" → ${resolvedTargetHubs.join(', ')} | ${routing.filter(r => r.status === 'routed').length}/${resolvedTargetHubs.length} routed | ${correlatedAlerts.length} correlated`,
      timestamp: Date.now(),
    };
  }

  // ───────────────────────────────────────────────────────────────────────
  // Duplicate Detection
  // ───────────────────────────────────────────────────────────────────────

  private findDuplicate(title: string, sourceAgent: string, windowMs: number): AlertRecord | null {
    const cutoff = Date.now() - windowMs;

    for (const alert of alertHistory.values()) {
      if (
        alert.title === title &&
        alert.sourceAgent === sourceAgent &&
        alert.emittedAt >= cutoff &&
        alert.status !== 'suppressed'
      ) {
        return alert;
      }
    }

    return null;
  }

  // ───────────────────────────────────────────────────────────────────────
  // Alert Correlation
  // ───────────────────────────────────────────────────────────────────────

  private findCorrelatedAlerts(alert: AlertRecord): AlertRecord[] {
    const correlated: AlertRecord[] = [];
    const lookbackWindow = 3600000; // 1 hour lookback

    for (const existing of alertHistory.values()) {
      if (existing.id === alert.id) continue;
      if (existing.emittedAt < Date.now() - lookbackWindow) continue;

      // Correlation criteria
      const sameSource = existing.sourceAgent === alert.sourceAgent;
      const sameAnomaly = existing.anomalyId && existing.anomalyId === alert.anomalyId;
      const samePattern = existing.patternId && existing.patternId === alert.patternId;
      const sameCorrelationId = existing.correlationId && existing.correlationId === alert.correlationId;
      const overlappingTargets = existing.targetHubs.some(h => alert.targetHubs.includes(h));

      if (sameAnomaly || samePattern || sameCorrelationId || (sameSource && overlappingTargets)) {
        correlated.push(existing);
      }
    }

    return correlated;
  }

  // ───────────────────────────────────────────────────────────────────────
  // Target Hub Inference
  // ───────────────────────────────────────────────────────────────────────

  private inferTargetHubs(level: AlertInput['level']): string[] {
    switch (level) {
      case 'emergency':
        return ALL_HUBS; // Broadcast to all
      case 'warning':
        return ['observatory-hub', 'arcadia-hub', 'luminous-hub'];
      case 'watch':
        return ['observatory-hub', 'arcadia-hub'];
      case 'advisory':
        return ['observatory-hub'];
      default:
        return ['observatory-hub'];
    }
  }

  // ───────────────────────────────────────────────────────────────────────
  // Alert Summary
  // ───────────────────────────────────────────────────────────────────────

  private buildSummary(): AlertSummary {
    const all = Array.from(alertHistory.values());
    const now = Date.now();

    const byLevel: Record<AlertInput['level'], number> = { advisory: 0, watch: 0, warning: 0, emergency: 0 };
    const byStatus: Record<AlertRecord['status'], number> = {
      emitted: 0, acknowledged: 0, escalated: 0, resolved: 0, expired: 0, suppressed: 0,
    };

    for (const alert of all) {
      byLevel[alert.level]++;
      byStatus[alert.status]++;
    }

    const activeAlerts = all.filter(a =>
      a.status === 'emitted' || a.status === 'acknowledged' || a.status === 'escalated'
    ).length;

    const emergencyCount = all.filter(a => a.level === 'emergency' && a.status !== 'resolved' && a.status !== 'suppressed').length;

    // Calculate average times
    const acknowledged = all.filter(a => a.acknowledgedAt && a.emittedAt);
    const resolved = all.filter(a => a.resolvedAt && a.emittedAt);

    const averageTimeToAcknowledge = acknowledged.length > 0
      ? Math.round(acknowledged.reduce((s, a) => s + (a.acknowledgedAt! - a.emittedAt), 0) / acknowledged.length)
      : 0;

    const averageTimeToResolve = resolved.length > 0
      ? Math.round(resolved.reduce((s, a) => s + (a.resolvedAt! - a.emittedAt), 0) / resolved.length)
      : 0;

    const suppressionRate = all.length > 0
      ? Math.round((byStatus.suppressed / all.length) * 10000) / 100
      : 0;

    // Top sources
    const sourceCount: Record<string, number> = {};
    for (const alert of all) {
      sourceCount[alert.sourceAgent] = (sourceCount[alert.sourceAgent] ?? 0) + 1;
    }
    const topSources = Object.entries(sourceCount)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([source, count]) => ({ source, count }));

    // Trend (based on last hour)
    const recentAlerts = all.filter(a => a.emittedAt >= now - 3600000).length;
    const previousHourAlerts = all.filter(a => a.emittedAt >= now - 7200000 && a.emittedAt < now - 3600000).length;

    const alertTrend: AlertSummary['alertTrend'] =
      recentAlerts > previousHourAlerts * 1.3 ? 'increasing' :
      recentAlerts < previousHourAlerts * 0.7 ? 'decreasing' :
      'stable';

    return {
      totalAlerts: all.length,
      byLevel,
      byStatus,
      activeAlerts,
      emergencyCount,
      averageTimeToAcknowledge,
      averageTimeToResolve,
      suppressionRate,
      topSources,
      alertTrend,
      timestamp: now,
    };
  }

  // ───────────────────────────────────────────────────────────────────────
  // Helpers
  // ───────────────────────────────────────────────────────────────────────

  private fail(message: string): SignalResult {
    this.log.error('Signal failed', { message });
    const emptyAlert: AlertRecord = {
      id: 'ALERT-000000',
      level: 'advisory',
      title: '',
      message: '',
      sourceAgent: '',
      targetHubs: [],
      targetAgents: [],
      status: 'emitted',
      emittedAt: Date.now(),
      expiresAt: Date.now(),
      deliveryStatus: {},
      timesEscalated: 0,
      timesReemitted: 0,
    };

    return {
      success: false,
      alert: emptyAlert,
      correlatedAlerts: [],
      summary: this.buildSummary(),
      routing: [],
      message,
      timestamp: Date.now(),
    };
  }
}
