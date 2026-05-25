/**
 * SentinelAgent — Watchful Guardian Agent for The Observatory
 *
 * Identity:  SID-OBSERVATORY-SENTINEL
 * Tier:      4 (Autonomous Microservice)
 * Parent:    TheObservatoryAI (AID-OBSERVATORY)
 *
 * Responsibilities:
 *   - Watch: Continuously monitor observation streams for anomalies
 *   - Detect: Identify deviations from normal patterns and baselines
 *   - Classify: Categorise detected anomalies by type and severity
 *   - Escalate: Promote critical anomalies to alert signals
 *
 * "The Sentinel never sleeps. Every shadow is examined, every flicker weighed."
 */

import { Agent, Bot, Logger, AuditLedger } from '../../../core/definitions';

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface SentinelInput {
  operation: 'watch' | 'detect' | 'classify' | 'escalate';
  observations?: RawObservation[];
  target?: string;
  threshold?: number;
  anomalyId?: string;
  classification?: string;
  confidence?: number;
  riskScore?: number;
  escalationTarget?: string;
  escalationReason?: string;
}

export interface RawObservation {
  source: string;
  metric: string;
  value: number;
  baseline: number;
  unit: string;
  timestamp: number;
  tags: string[];
}

export interface WatchResult {
  watched: number;
  flagged: number;
  baselines: Record<string, { metric: string; baseline: number; current: number; deviation: number }>;
  flaggedItems: { source: string; metric: string; value: number; baseline: number; deviationPercent: number }[];
  surveillanceStatus: 'nominal' | 'elevated' | 'alert';
  message: string;
}

export interface DetectionResult {
  detections: AnomalyDetection[];
  totalScanned: number;
  detectedCount: number;
  detectionRate: number;
  scanDuration: number;
  message: string;
}

export interface AnomalyDetection {
  id: string;
  source: string;
  metric: string;
  value: number;
  baseline: number;
  deviation: number;
  deviationPercent: number;
  type: 'spike' | 'drop' | 'drift' | 'oscillation' | 'flatline' | 'unknown';
  severity: 'low' | 'medium' | 'high' | 'critical';
  detectedAt: number;
}

export interface ClassificationResult {
  anomalyId: string;
  classification: string;
  category: AnomalyCategory;
  confidence: number;
  riskScore: number;
  description: string;
  recommendedAction: string;
  relatedPatterns: string[];
  classifiedAt: number;
}

export type AnomalyCategory =
  | 'performance_degradation'
  | 'security_breach'
  | 'resource_exhaustion'
  | 'data_corruption'
  | 'service_outage'
  | 'configuration_drift'
  | 'capacity_threshold'
  | 'compliance_violation'
  | 'celestial_interference'
  | 'unknown';

export interface EscalationResult {
  anomalyId: string;
  escalated: boolean;
  escalationTarget: string;
  escalationLevel: 'advisory' | 'watch' | 'warning' | 'emergency';
  reason: string;
  signalId: string;
  timestamp: number;
}

export interface SentinelPerception {
  operation: string;
  data: any;
  timestamp: number;
}

export interface SentinelDecision {
  action: string;
  params: Record<string, unknown>;
}

export interface SentinelActionResult {
  success: boolean;
  operation: string;
  result: WatchResult | DetectionResult | ClassificationResult | EscalationResult;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Simulated Baselines
// ─────────────────────────────────────────────────────────────────────────────

const BASELINES: Record<string, Record<string, { baseline: number; unit: string; threshold: number }>> = {
  'arcadia-hub': {
    cpu: { baseline: 45, unit: 'percent', threshold: 20 },
    memory: { baseline: 62, unit: 'percent', threshold: 15 },
    requests: { baseline: 1500, unit: 'req/s', threshold: 40 },
    latency: { baseline: 120, unit: 'ms', threshold: 50 },
    errorRate: { baseline: 0.5, unit: 'percent', threshold: 100 },
    connections: { baseline: 8500, unit: 'count', threshold: 30 },
  },
  'luminous-hub': {
    cpu: { baseline: 38, unit: 'percent', threshold: 20 },
    memory: { baseline: 55, unit: 'percent', threshold: 15 },
    inferenceLatency: { baseline: 85, unit: 'ms', threshold: 60 },
    modelAccuracy: { baseline: 94.5, unit: 'percent', threshold: 5 },
  },
  'exchange-hub': {
    orderThroughput: { baseline: 3200, unit: 'orders/min', threshold: 35 },
    tradeSettlement: { baseline: 98.7, unit: 'percent', threshold: 2 },
    spreadVariance: { baseline: 0.15, unit: 'basis_points', threshold: 100 },
  },
  'observatory-hub': {
    scanFrequency: { baseline: 60, unit: 'scans/hour', threshold: 25 },
    anomalyDetectionRate: { baseline: 2.3, unit: 'per_hour', threshold: 50 },
    alertLatency: { baseline: 250, unit: 'ms', threshold: 80 },
  },
};

let detectionCounter = 0;
let escalationCounter = 0;

// ─────────────────────────────────────────────────────────────────────────────
// SentinelAgent Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class SentinelAgent extends Agent {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private watchedItems: Map<string, { metric: string; baseline: number; current: number; deviation: number }>;
  private detections: Map<string, AnomalyDetection>;

  constructor() {
    super('SID-OBSERVATORY-SENTINEL');
    this.log = new Logger('SentinelAgent');
    this.audit = AuditLedger.getInstance();
    this.watchedItems = new Map();
    this.detections = new Map();
  }

  // ───────────────────────────────────────────────────────────────────────
  // Perceive
  // ───────────────────────────────────────────────────────────────────────

  async perceive(input: SentinelInput): Promise<SentinelPerception> {
    this.log.info('Perceiving input', { operation: input.operation });
    return {
      operation: input.operation,
      data: input,
      timestamp: Date.now(),
    };
  }

  // ───────────────────────────────────────────────────────────────────────
  // Decide
  // ───────────────────────────────────────────────────────────────────────

  async decide(perception: SentinelPerception): Promise<SentinelDecision> {
    const { operation } = perception;

    switch (operation) {
      case 'watch':
        return { action: 'executeWatch', params: { data: perception.data } };
      case 'detect':
        return { action: 'executeDetect', params: { data: perception.data } };
      case 'classify':
        return { action: 'executeClassify', params: { data: perception.data } };
      case 'escalate':
        return { action: 'executeEscalate', params: { data: perception.data } };
      default:
        return { action: 'unknown', params: {} };
    }
  }

  // ───────────────────────────────────────────────────────────────────────
  // Act
  // ───────────────────────────────────────────────────────────────────────

  async act(decision: SentinelDecision): Promise<SentinelActionResult> {
    switch (decision.action) {
      case 'executeWatch':
        return this.executeWatch(decision.params.data as SentinelInput);
      case 'executeDetect':
        return this.executeDetect(decision.params.data as SentinelInput);
      case 'executeClassify':
        return this.executeClassify(decision.params.data as SentinelInput);
      case 'executeEscalate':
        return this.executeEscalate(decision.params.data as SentinelInput);
      default:
        return {
          success: false,
          operation: 'unknown',
          result: {
            anomalyId: '',
            escalated: false,
            escalationTarget: '',
            escalationLevel: 'advisory',
            reason: `Unknown operation`,
            signalId: '',
            timestamp: Date.now(),
          } as EscalationResult,
          timestamp: Date.now(),
        };
    }
  }

  // ───────────────────────────────────────────────────────────────────────
  // WATCH — Monitor observation streams
  // ───────────────────────────────────────────────────────────────────────

  private executeWatch(input: SentinelInput): SentinelActionResult {
    const observations = input.observations ?? this.generateSimulatedObservations(input.target);
    const threshold = input.threshold ?? 20;

    let flagged = 0;
    const flaggedItems: WatchResult['flaggedItems'] = [];

    for (const obs of observations) {
      const deviationPercent = obs.baseline > 0
        ? Math.abs(((obs.value - obs.baseline) / obs.baseline) * 100)
        : obs.value > 0 ? 100 : 0;

      const key = `${obs.source}:${obs.metric}`;
      this.watchedItems.set(key, {
        metric: obs.metric,
        baseline: obs.baseline,
        current: obs.value,
        deviation: deviationPercent,
      });

      if (deviationPercent > threshold) {
        flagged++;
        flaggedItems.push({
          source: obs.source,
          metric: obs.metric,
          value: obs.value,
          baseline: obs.baseline,
          deviationPercent: Math.round(deviationPercent * 100) / 100,
        });
      }
    }

    const surveillanceStatus: WatchResult['surveillanceStatus'] =
      flagged > 5 ? 'alert' : flagged > 2 ? 'elevated' : 'nominal';

    const result: WatchResult = {
      watched: observations.length,
      flagged,
      baselines: Object.fromEntries(this.watchedItems),
      flaggedItems,
      surveillanceStatus,
      message: `Watched ${observations.length} observations, flagged ${flagged} (${surveillanceStatus})`,
    };

    this.audit.append({
      actor: 'SID-OBSERVATORY-SENTINEL',
      action: 'WATCH_COMPLETED',
      entity: input.target ?? 'all',
      status: 'SUCCESS',
      meta: { watched: observations.length, flagged, surveillanceStatus },
    });

    this.log.info('Watch cycle completed', {
      watched: observations.length,
      flagged,
      surveillanceStatus,
    });

    return {
      success: true,
      operation: 'watch',
      result,
      timestamp: Date.now(),
    };
  }

  // ───────────────────────────────────────────────────────────────────────
  // DETECT — Identify anomalies
  // ───────────────────────────────────────────────────────────────────────

  private executeDetect(input: SentinelInput): SentinelActionResult {
    const observations = input.observations ?? this.generateSimulatedObservations(input.target);
    const threshold = input.threshold ?? 25;

    const detections: AnomalyDetection[] = [];
    const startTime = Date.now();

    for (const obs of observations) {
      const deviation = obs.value - obs.baseline;
      const deviationPercent = obs.baseline > 0
        ? ((deviation / obs.baseline) * 100)
        : 0;

      if (Math.abs(deviationPercent) > threshold) {
        detectionCounter++;
        const absDeviation = Math.abs(deviationPercent);

        const type: AnomalyDetection['type'] =
          deviationPercent > 0 && absDeviation > 80 ? 'spike' :
          deviationPercent < 0 && absDeviation > 80 ? 'drop' :
          absDeviation > 0 && absDeviation < 30 ? 'drift' :
          absDeviation < 1 ? 'flatline' :
          deviationPercent > 0 && deviationPercent < 0 ? 'oscillation' :
          'unknown';

        const severity: AnomalyDetection['severity'] =
          absDeviation > 100 ? 'critical' :
          absDeviation > 60 ? 'high' :
          absDeviation > 35 ? 'medium' :
          'low';

        const detection: AnomalyDetection = {
          id: `DET-${detectionCounter.toString().padStart(6, '0')}`,
          source: obs.source,
          metric: obs.metric,
          value: obs.value,
          baseline: obs.baseline,
          deviation: Math.round(deviation * 100) / 100,
          deviationPercent: Math.round(deviationPercent * 100) / 100,
          type,
          severity,
          detectedAt: Date.now(),
        };

        detections.push(detection);
        this.detections.set(detection.id, detection);
      }
    }

    const scanDuration = Date.now() - startTime;
    const detectionRate = observations.length > 0
      ? Math.round((detections.length / observations.length) * 10000) / 100
      : 0;

    const result: DetectionResult = {
      detections,
      totalScanned: observations.length,
      detectedCount: detections.length,
      detectionRate,
      scanDuration,
      message: `Scanned ${observations.length} observations, detected ${detections.length} anomalies (${detectionRate}% rate, ${scanDuration}ms)`,
    };

    this.audit.append({
      actor: 'SID-OBSERVATORY-SENTINEL',
      action: 'DETECTION_COMPLETED',
      entity: input.target ?? 'all',
      status: detections.length > 0 ? 'SUCCESS' : 'SUCCESS',
      meta: { totalScanned: observations.length, detectedCount: detections.length, detectionRate },
    });

    this.log.info('Detection cycle completed', {
      totalScanned: observations.length,
      detectedCount: detections.length,
      detectionRate: `${detectionRate}%`,
    });

    return {
      success: true,
      operation: 'detect',
      result,
      timestamp: Date.now(),
    };
  }

  // ───────────────────────────────────────────────────────────────────────
  // CLASSIFY — Categorise anomalies
  // ───────────────────────────────────────────────────────────────────────

  private executeClassify(input: SentinelInput): SentinelActionResult {
    const { anomalyId, classification, confidence, riskScore } = input;

    if (!anomalyId) {
      return {
        success: false,
        operation: 'classify',
        result: {
          anomalyId: anomalyId ?? '',
          classification: '',
          category: 'unknown' as AnomalyCategory,
          confidence: 0,
          riskScore: 0,
          description: 'Anomaly ID is required for classification',
          recommendedAction: 'Provide an anomaly ID',
          relatedPatterns: [],
          classifiedAt: Date.now(),
        } as ClassificationResult,
        timestamp: Date.now(),
      };
    }

    const detection = this.detections.get(anomalyId);
    const resolvedClassification = classification ?? this.inferClassification(detection);
    const resolvedConfidence = confidence ?? (detection ? Math.min(95, 60 + Math.abs(detection.deviationPercent) * 0.3) : 50);
    const resolvedRiskScore = riskScore ?? (detection ? this.calculateRiskScore(detection) : 50);

    const category = this.mapClassificationToCategory(resolvedClassification);
    const description = this.generateDescription(resolvedClassification, detection);
    const recommendedAction = this.getRecommendedAction(category, resolvedRiskScore);
    const relatedPatterns = this.findRelatedPatterns(category);

    const result: ClassificationResult = {
      anomalyId,
      classification: resolvedClassification,
      category,
      confidence: Math.round(resolvedConfidence * 100) / 100,
      riskScore: Math.round(resolvedRiskScore * 100) / 100,
      description,
      recommendedAction,
      relatedPatterns,
      classifiedAt: Date.now(),
    };

    this.audit.append({
      actor: 'SID-OBSERVATORY-SENTINEL',
      action: 'ANOMALY_CLASSIFIED',
      entity: anomalyId,
      status: 'SUCCESS',
      meta: { classification: resolvedClassification, category, confidence: resolvedConfidence, riskScore: resolvedRiskScore },
    });

    this.log.info('Anomaly classified', {
      anomalyId,
      classification: resolvedClassification,
      category,
      confidence: resolvedConfidence,
      riskScore: resolvedRiskScore,
    });

    return {
      success: true,
      operation: 'classify',
      result,
      timestamp: Date.now(),
    };
  }

  // ───────────────────────────────────────────────────────────────────────
  // ESCALATE — Promote anomaly to alert
  // ───────────────────────────────────────────────────────────────────────

  private executeEscalate(input: SentinelInput): SentinelActionResult {
    const { anomalyId, escalationTarget, escalationReason } = input;

    if (!anomalyId) {
      return {
        success: false,
        operation: 'escalate',
        result: {
          anomalyId: anomalyId ?? '',
          escalated: false,
          escalationTarget: escalationTarget ?? '',
          escalationLevel: 'advisory',
          reason: 'Anomaly ID is required for escalation',
          signalId: '',
          timestamp: Date.now(),
        } as EscalationResult,
        timestamp: Date.now(),
      };
    }

    const detection = this.detections.get(anomalyId);
    const resolvedTarget = escalationTarget ?? 'AID-OBSERVATORY';

    // Determine escalation level based on severity/risk
    const riskScore = input.riskScore ?? (detection ? this.calculateRiskScore(detection) : 50);
    const escalationLevel: EscalationResult['escalationLevel'] =
      riskScore >= 90 ? 'emergency' :
      riskScore >= 70 ? 'warning' :
      riskScore >= 40 ? 'watch' :
      'advisory';

    escalationCounter++;
    const signalId = `SIG-${escalationCounter.toString().padStart(6, '0')}`;
    const reason = escalationReason ?? `Anomaly ${anomalyId} risk score ${riskScore} exceeds threshold`;

    const result: EscalationResult = {
      anomalyId,
      escalated: true,
      escalationTarget: resolvedTarget,
      escalationLevel,
      reason,
      signalId,
      timestamp: Date.now(),
    };

    this.audit.append({
      actor: 'SID-OBSERVATORY-SENTINEL',
      action: 'ANOMALY_ESCALATED',
      entity: anomalyId,
      status: 'SUCCESS',
      meta: { escalationLevel, escalationTarget: resolvedTarget, signalId, riskScore },
    });

    this.log.warn('Anomaly escalated', {
      anomalyId,
      escalationLevel,
      escalationTarget: resolvedTarget,
      signalId,
      riskScore,
    });

    return {
      success: true,
      operation: 'escalate',
      result,
      timestamp: Date.now(),
    };
  }

  // ───────────────────────────────────────────────────────────────────────
  // Helpers
  // ───────────────────────────────────────────────────────────────────────

  private generateSimulatedObservations(target?: string): RawObservation[] {
    const observations: RawObservation[] = [];
    const targets = target ? [target] : Object.keys(BASELINES);

    for (const src of targets) {
      const metrics = BASELINES[src];
      if (!metrics) continue;

      for (const [metricName, config] of Object.entries(metrics)) {
        // Simulate mostly-normal with occasional anomalies
        const anomalyChance = Math.random();
        const deviationMultiplier = anomalyChance > 0.85
          ? (2 + Math.random() * 3)   // Major anomaly: 200-500% deviation
          : anomalyChance > 0.6
          ? (1.1 + Math.random() * 0.9) // Minor anomaly: 110-200% deviation
          : (0.9 + Math.random() * 0.2); // Normal: 90-110% of baseline

        const value = config.baseline * deviationMultiplier;

        observations.push({
          source: src,
          metric: metricName,
          value: Math.round(value * 100) / 100,
          baseline: config.baseline,
          unit: config.unit,
          timestamp: Date.now(),
          tags: [src, metricName, config.unit],
        });
      }
    }

    return observations;
  }

  private inferClassification(detection?: AnomalyDetection): string {
    if (!detection) return 'unclassified_anomaly';

    const { type, source, metric } = detection;
    const prefix = source.replace(/-hub$/, '');

    switch (type) {
      case 'spike': return `${prefix}_${metric}_spike`;
      case 'drop': return `${prefix}_${metric}_drop`;
      case 'drift': return `${prefix}_${metric}_drift`;
      case 'oscillation': return `${prefix}_${metric}_oscillation`;
      case 'flatline': return `${prefix}_${metric}_flatline`;
      default: return `${prefix}_${metric}_anomaly`;
    }
  }

  private calculateRiskScore(detection: AnomalyDetection): number {
    const severityMultiplier = { low: 1, medium: 2, high: 3, critical: 5 };
    const baseScore = Math.min(100, Math.abs(detection.deviationPercent) * 0.8);
    const severityBonus = (severityMultiplier[detection.severity] - 1) * 10;
    return Math.min(100, Math.round((baseScore + severityBonus) * 100) / 100);
  }

  private mapClassificationToCategory(classification: string): AnomalyCategory {
    const lower = classification.toLowerCase();

    if (lower.includes('cpu') || lower.includes('memory') || lower.includes('resource')) return 'resource_exhaustion';
    if (lower.includes('latency') || lower.includes('performance') || lower.includes('slow')) return 'performance_degradation';
    if (lower.includes('security') || lower.includes('breach') || lower.includes('unauthorised')) return 'security_breach';
    if (lower.includes('error') || lower.includes('outage') || lower.includes('down')) return 'service_outage';
    if (lower.includes('corrupt') || lower.includes('data')) return 'data_corruption';
    if (lower.includes('config') || lower.includes('drift')) return 'configuration_drift';
    if (lower.includes('capacity') || lower.includes('threshold')) return 'capacity_threshold';
    if (lower.includes('compliance') || lower.includes('violation')) return 'compliance_violation';
    if (lower.includes('celestial') || lower.includes('nova') || lower.includes('eclipse')) return 'celestial_interference';
    return 'unknown';
  }

  private generateDescription(classification: string, detection?: AnomalyDetection): string {
    if (!detection) return `Classified as ${classification}. Insufficient data for detailed description.`;

    const direction = detection.deviation > 0 ? 'above' : 'below';
    return `${classification}: ${detection.source}/${detection.metric} is ${Math.abs(detection.deviationPercent).toFixed(1)}% ${direction} baseline (${detection.value} vs ${detection.baseline} ${detection.unit}). Type: ${detection.type}, Severity: ${detection.severity}.`;
  }

  private getRecommendedAction(category: AnomalyCategory, riskScore: number): string {
    const actions: Record<AnomalyCategory, string> = {
      performance_degradation: 'Investigate resource allocation and scaling policies. Consider enabling auto-scaling or optimising queries.',
      security_breach: 'Immediately isolate affected systems. Rotate credentials, review access logs, and engage incident response protocols.',
      resource_exhaustion: 'Scale up resources or reduce load. Review capacity planning and set proactive alerting thresholds.',
      data_corruption: 'Halt write operations to affected stores. Initiate data recovery from last known good backup.',
      service_outage: 'Activate failover systems. Check health endpoints and dependency status. Engage on-call engineering.',
      configuration_drift: 'Compare current configuration against known-good baseline. Apply corrective configuration via deployment pipeline.',
      capacity_threshold: 'Review current utilisation trends. Plan capacity expansion before threshold breach.',
      compliance_violation: 'Document the violation. Notify compliance team and initiate remediation workflow.',
      celestial_interference: 'Monitor pattern evolution. Cross-reference with StarMap data. Prepare contingency for predicted impact.',
      unknown: 'Gather additional data points. Increase monitoring frequency. Consider escalation if risk score exceeds 70.',
    };

    const base = actions[category] ?? actions.unknown;
    return riskScore >= 80 ? `URGENT: ${base}` : base;
  }

  private findRelatedPatterns(category: AnomalyCategory): string[] {
    const patternMap: Record<AnomalyCategory, string[]> = {
      performance_degradation: ['convergence', 'eclipse'],
      security_breach: ['nova', 'void'],
      resource_exhaustion: ['convergence', 'alignment'],
      data_corruption: ['void', 'nova'],
      service_outage: ['eclipse', 'void'],
      configuration_drift: ['drift', 'alignment'],
      capacity_threshold: ['convergence', 'alignment'],
      compliance_violation: ['eclipse', 'alignment'],
      celestial_interference: ['nova', 'eclipse', 'convergence', 'alignment'],
      unknown: [],
    };
    return patternMap[category] ?? [];
  }
}
