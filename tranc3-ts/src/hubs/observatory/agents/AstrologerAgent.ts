/**
 * AstrologerAgent — Celestial Pattern Interpreter for The Observatory
 *
 * Identity:  SID-OBSERVATORY-ASTROLOGER
 * Tier:      4 (Autonomous Microservice)
 * Parent:    TheObservatoryAI (AID-OBSERVATORY)
 *
 * Responsibilities:
 *   - Read:    Parse celestial data streams and observation feeds
 *   - Interpret: Decode the meaning behind observed patterns and alignments
 *   - Predict: Forecast future events from celestial pattern progression
 *   - Advise:  Recommend actions based on astrological analysis
 *
 * "The stars do not dictate — they whisper. The Astrologer listens."
 */

import { Agent, Bot, Logger, AuditLedger } from '../../../core/definitions';

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface AstrologerInput {
  operation: 'read' | 'interpret' | 'predict' | 'advise';
  dataSource?: string;
  patternId?: string;
  patternType?: CelestialPatternType;
  entities?: string[];
  timeframe?: 'immediate' | 'short_term' | 'medium_term' | 'long_term';
  context?: Record<string, unknown>;
  riskTolerance?: 'conservative' | 'moderate' | 'aggressive';
}

export type CelestialPatternType =
  | 'convergence'   // Systems/data streams moving toward alignment
  | 'divergence'    // Systems/data streams moving apart
  | 'eclipse'       // One system obscuring another
  | 'alignment'     // Multiple systems in harmonic synchrony
  | 'nova'          // Sudden bright event — unexpected spike
  | 'void';         // Absence of expected signal — dark zone

export interface CelestialReading {
  id: string;
  source: string;
  timestamp: number;
  entities: string[];
  dominantPattern: CelestialPatternType;
  intensity: number;
  harmonics: number;
  noiseLevel: number;
  signalStrength: number;
  readingType: 'stellar' | 'orbital' | 'spectral' | 'gravitational' | 'temporal';
  dataPoints: number;
  quality: 'excellent' | 'good' | 'fair' | 'poor';
  rawMetrics: Record<string, number>;
}

export interface Interpretation {
  patternId: string;
  patternType: CelestialPatternType;
  meaning: string;
  significance: 'trivial' | 'minor' | 'notable' | 'major' | 'epochal';
  affectedDomains: string[];
  confidence: number;
  narrative: string;
  keySymbols: string[];
  historicalPrecedent?: string;
  crossReferences: string[];
  interpretedAt: number;
}

export interface Prediction {
  id: string;
  patternId: string;
  forecast: PredictionEntry[];
  overallTrend: 'improving' | 'stable' | 'degrading' | 'volatile' | 'critical';
  probability: number;
  confidenceInterval: { low: number; high: number };
  keyDrivers: string[];
  riskFactors: string[];
  timeline: string;
  predictedAt: number;
}

export interface PredictionEntry {
  period: string;
  description: string;
  probability: number;
  impact: 'negligible' | 'low' | 'moderate' | 'high' | 'catastrophic';
  affectedSystems: string[];
  indicator: 'bullish' | 'neutral' | 'bearish';
}

export interface Advice {
  id: string;
  patternId: string;
  recommendation: string;
  priority: 'informational' | 'suggested' | 'recommended' | 'imperative';
  actions: AdvisedAction[];
  reasoning: string;
  alternativeScenarios: string[];
  riskOfInaction: string;
  validUntil: number;
  issuedAt: number;
}

export interface AdvisedAction {
  step: number;
  action: string;
  target: string;
  expectedOutcome: string;
  urgency: 'immediate' | 'within_hour' | 'within_day' | 'within_week';
  dependencies: string[];
}

export interface AstrologerPerception {
  operation: string;
  data: any;
  timestamp: number;
}

export interface AstrologerDecision {
  action: string;
  params: Record<string, unknown>;
}

export interface AstrologerActionResult {
  success: boolean;
  operation: string;
  result: CelestialReading | Interpretation | Prediction | Advice;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Simulated Celestial Data
// ─────────────────────────────────────────────────────────────────────────────

const CELESTIAL_SOURCES: Record<string, {
  type: CelestialReading['readingType'];
  entities: string[];
  dominantPattern: CelestialPatternType;
  baseIntensity: number;
}> = {
  'arcadia-nexus': { type: 'stellar', entities: ['arcadia-hub', 'luminous-hub', 'exchange-hub'], dominantPattern: 'alignment', baseIntensity: 72 },
  'perimeter-scan': { type: 'orbital', entities: ['observatory-hub', 'workshop-hub'], dominantPattern: 'convergence', baseIntensity: 45 },
  'deep-field': { type: 'spectral', entities: ['lab-hub', 'basement-hub', 'digitalgrid-hub'], dominantPattern: 'divergence', baseIntensity: 58 },
  'core-resonance': { type: 'gravitational', entities: ['arcadia-hub', 'townhall-hub', 'royalbank-hub'], dominantPattern: 'alignment', baseIntensity: 85 },
  'temporal-stream': { type: 'temporal', entities: ['all-hubs'], dominantPattern: 'eclipse', baseIntensity: 33 },
  'void-sector': { type: 'spectral', entities: ['unknown'], dominantPattern: 'void', baseIntensity: 12 },
};

let readingCounter = 0;
let predictionCounter = 0;
let adviceCounter = 0;

// ─────────────────────────────────────────────────────────────────────────────
// AstrologerAgent Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class AstrologerAgent extends Agent {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private readings: Map<string, CelestialReading>;
  private interpretations: Map<string, Interpretation>;
  private predictions: Map<string, Prediction>;

  constructor() {
    super('SID-OBSERVATORY-ASTROLOGER');
    this.log = new Logger('AstrologerAgent');
    this.audit = AuditLedger.getInstance();
    this.readings = new Map();
    this.interpretations = new Map();
    this.predictions = new Map();
  }

  // ───────────────────────────────────────────────────────────────────────
  // Perceive
  // ───────────────────────────────────────────────────────────────────────

  async perceive(input: AstrologerInput): Promise<AstrologerPerception> {
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

  async decide(perception: AstrologerPerception): Promise<AstrologerDecision> {
    switch (perception.operation) {
      case 'read': return { action: 'executeRead', params: { data: perception.data } };
      case 'interpret': return { action: 'executeInterpret', params: { data: perception.data } };
      case 'predict': return { action: 'executePredict', params: { data: perception.data } };
      case 'advise': return { action: 'executeAdvise', params: { data: perception.data } };
      default: return { action: 'unknown', params: {} };
    }
  }

  // ───────────────────────────────────────────────────────────────────────
  // Act
  // ───────────────────────────────────────────────────────────────────────

  async act(decision: AstrologerDecision): Promise<AstrologerActionResult> {
    switch (decision.action) {
      case 'executeRead': return this.executeRead(decision.params.data as AstrologerInput);
      case 'executeInterpret': return this.executeInterpret(decision.params.data as AstrologerInput);
      case 'executePredict': return this.executePredict(decision.params.data as AstrologerInput);
      case 'executeAdvise': return this.executeAdvise(decision.params.data as AstrologerInput);
      default:
        return {
          success: false,
          operation: 'unknown',
          result: {
            id: '',
            patternId: '',
            recommendation: 'Unknown operation',
            priority: 'informational',
            actions: [],
            reasoning: '',
            alternativeScenarios: [],
            riskOfInaction: '',
            validUntil: Date.now(),
            issuedAt: Date.now(),
          } as Advice,
          timestamp: Date.now(),
        };
    }
  }

  // ───────────────────────────────────────────────────────────────────────
  // READ — Parse celestial data streams
  // ───────────────────────────────────────────────────────────────────────

  private executeRead(input: AstrologerInput): AstrologerActionResult {
    const source = input.dataSource ?? 'arcadia-nexus';
    const sourceData = CELESTIAL_SOURCES[source];

    if (!sourceData) {
      this.log.warn('Unknown celestial source, generating synthetic reading', { source });
    }

    const data = sourceData ?? {
      type: 'spectral' as const,
      entities: input.entities ?? ['unknown'],
      dominantPattern: input.patternType ?? 'void',
      baseIntensity: 50,
    };

    readingCounter++;
    const intensityVariation = data.baseIntensity * (0.85 + Math.random() * 0.3);
    const harmonics = Math.round(Math.random() * 12 + 1);
    const noiseLevel = Math.round(Math.random() * 30);
    const signalStrength = Math.max(0, Math.min(100, intensityVariation - noiseLevel));

    const quality: CelestialReading['quality'] =
      signalStrength > 80 ? 'excellent' :
      signalStrength > 60 ? 'good' :
      signalStrength > 35 ? 'fair' :
      'poor';

    const rawMetrics: Record<string, number> = {
      luminosity: Math.round(intensityVariation * 10) / 10,
      frequency: Math.round(harmonics * 7.83 * 100) / 100,
      amplitude: Math.round(signalStrength * 0.5 * 100) / 100,
      phase: Math.round(Math.random() * 360 * 100) / 100,
      redshift: Math.round(Math.random() * 0.01 * 10000) / 10000,
      coherence: Math.round((signalStrength / 100) * 100) / 100,
    };

    const reading: CelestialReading = {
      id: `READ-${readingCounter.toString().padStart(6, '0')}`,
      source,
      timestamp: Date.now(),
      entities: data.entities,
      dominantPattern: data.dominantPattern,
      intensity: Math.round(intensityVariation * 100) / 100,
      harmonics,
      noiseLevel,
      signalStrength: Math.round(signalStrength * 100) / 100,
      readingType: data.type,
      dataPoints: Math.floor(Math.random() * 10000) + 500,
      quality,
      rawMetrics,
    };

    this.readings.set(reading.id, reading);

    this.audit.append({
      actor: 'SID-OBSERVATORY-ASTROLOGER',
      action: 'CELESTIAL_READING',
      entity: source,
      status: 'SUCCESS',
      meta: { readingId: reading.id, pattern: reading.dominantPattern, intensity: reading.intensity, quality },
    });

    this.log.info('Celestial reading completed', {
      readingId: reading.id,
      source,
      pattern: reading.dominantPattern,
      intensity: reading.intensity,
      signalStrength: reading.signalStrength,
      quality,
    });

    return {
      success: true,
      operation: 'read',
      result: reading,
      timestamp: Date.now(),
    };
  }

  // ───────────────────────────────────────────────────────────────────────
  // INTERPRET — Decode observed patterns
  // ───────────────────────────────────────────────────────────────────────

  private executeInterpret(input: AstrologerInput): AstrologerActionResult {
    const patternType = input.patternType ?? 'alignment';
    const entities = input.entities ?? ['arcadia-hub'];
    const patternId = input.patternId ?? `PAT-INTERP-${Date.now()}`;

    const interpretation = this.generateInterpretation(patternId, patternType, entities);

    this.interpretations.set(patternId, interpretation);

    this.audit.append({
      actor: 'SID-OBSERVATORY-ASTROLOGER',
      action: 'PATTERN_INTERPRETED',
      entity: patternId,
      status: 'SUCCESS',
      meta: {
        patternType,
        significance: interpretation.significance,
        confidence: interpretation.confidence,
        affectedDomains: interpretation.affectedDomains,
      },
    });

    this.log.info('Pattern interpreted', {
      patternId,
      patternType,
      significance: interpretation.significance,
      confidence: interpretation.confidence,
    });

    return {
      success: true,
      operation: 'interpret',
      result: interpretation,
      timestamp: Date.now(),
    };
  }

  // ───────────────────────────────────────────────────────────────────────
  // PREDICT — Forecast from pattern progression
  // ───────────────────────────────────────────────────────────────────────

  private executePredict(input: AstrologerInput): AstrologerActionResult {
    const patternId = input.patternId ?? `PAT-PRED-${Date.now()}`;
    const patternType = input.patternType ?? 'alignment';
    const timeframe = input.timeframe ?? 'short_term';
    const entities = input.entities ?? ['arcadia-hub'];

    predictionCounter++;
    const overallTrend = this.determineTrend(patternType);
    const probability = Math.round((40 + Math.random() * 55) * 100) / 100;
    const confidenceSpread = 15 + Math.random() * 20;

    const forecast = this.generateForecast(patternType, timeframe, entities);

    const prediction: Prediction = {
      id: `PRED-${predictionCounter.toString().padStart(6, '0')}`,
      patternId,
      forecast,
      overallTrend,
      probability,
      confidenceInterval: {
        low: Math.max(0, Math.round((probability - confidenceSpread) * 100) / 100),
        high: Math.min(100, Math.round((probability + confidenceSpread) * 100) / 100),
      },
      keyDrivers: this.identifyKeyDrivers(patternType),
      riskFactors: this.identifyRiskFactors(patternType),
      timeline: this.timelineLabel(timeframe),
      predictedAt: Date.now(),
    };

    this.predictions.set(prediction.id, prediction);

    this.audit.append({
      actor: 'SID-OBSERVATORY-ASTROLOGER',
      action: 'PREDICTION_ISSUED',
      entity: patternId,
      status: 'SUCCESS',
      meta: {
        predictionId: prediction.id,
        overallTrend,
        probability,
        forecastCount: forecast.length,
      },
    });

    this.log.info('Prediction issued', {
      predictionId: prediction.id,
      patternType,
      overallTrend,
      probability,
      forecastPeriods: forecast.length,
    });

    return {
      success: true,
      operation: 'predict',
      result: prediction,
      timestamp: Date.now(),
    };
  }

  // ───────────────────────────────────────────────────────────────────────
  // ADVISE — Recommend actions
  // ───────────────────────────────────────────────────────────────────────

  private executeAdvise(input: AstrologerInput): AstrologerActionResult {
    const patternId = input.patternId ?? `PAT-ADV-${Date.now()}`;
    const patternType = input.patternType ?? 'alignment';
    const riskTolerance = input.riskTolerance ?? 'moderate';

    adviceCounter++;
    const significance = this.patternSignificance(patternType);
    const priority: Advice['priority'] =
      significance === 'epochal' ? 'imperative' :
      significance === 'major' ? 'recommended' :
      significance === 'notable' ? 'suggested' :
      'informational';

    const actions = this.generateAdvisedActions(patternType, riskTolerance);
    const reasoning = this.generateReasoning(patternType, significance);
    const alternativeScenarios = this.generateAlternatives(patternType);
    const riskOfInaction = this.assessInactionRisk(patternType);

    const advice: Advice = {
      id: `ADV-${adviceCounter.toString().padStart(6, '0')}`,
      patternId,
      recommendation: this.primaryRecommendation(patternType, riskTolerance),
      priority,
      actions,
      reasoning,
      alternativeScenarios,
      riskOfInaction,
      validUntil: Date.now() + 3600000, // Valid for 1 hour
      issuedAt: Date.now(),
    };

    this.audit.append({
      actor: 'SID-OBSERVATORY-ASTROLOGER',
      action: 'ADVICE_ISSUED',
      entity: patternId,
      status: 'SUCCESS',
      meta: {
        adviceId: advice.id,
        priority,
        riskTolerance,
        actionCount: actions.length,
      },
    });

    this.log.info('Advice issued', {
      adviceId: advice.id,
      patternType,
      priority,
      recommendation: advice.recommendation,
    });

    return {
      success: true,
      operation: 'advise',
      result: advice,
      timestamp: Date.now(),
    };
  }

  // ───────────────────────────────────────────────────────────────────────
  // Interpretation Helpers
  // ───────────────────────────────────────────────────────────────────────

  private generateInterpretation(
    patternId: string,
    patternType: CelestialPatternType,
    entities: string[]
  ): Interpretation {
    const meanings: Record<CelestialPatternType, string> = {
      convergence: 'Multiple systems are drawing together, creating a gravitational well of activity. Resources will concentrate, potentially straining capacity at convergence points.',
      divergence: 'Systems are moving apart, creating gaps in coverage and communication. Inter-dependent processes may experience desynchronisation.',
      eclipse: 'A dominant system is temporarily obscuring secondary systems. Dependency chains may break if the eclipsed system cannot maintain its shadow load.',
      alignment: 'Systems are entering harmonic synchrony. This is typically a positive indicator for throughput and stability, though it may amplify cascading failures.',
      nova: 'An unexpected bright event — a sudden spike in activity from an unanticipated source. This could represent a new capability, an attack, or a misconfiguration.',
      void: 'An expected signal is absent. This dark zone may indicate a failed system, a network partition, or deliberate suppression of telemetry.',
    };

    const narratives: Record<CelestialPatternType, string> = {
      convergence: `The celestial streams draw inward — ${entities.join(', ')} move toward a common attractor. Watch for resource contention as gravitational pressure builds.`,
      divergence: `The cosmic threads fray — ${entities.join(', ')} drift apart like constellations losing their myth. Strengthen the bonds before they stretch to breaking.`,
      eclipse: `A great body passes before the light — ${entities[0] ?? 'the primary'} casts its shadow across ${entities.slice(1).join(', ') || 'lesser bodies'}. The obscured must find their own illumination.`,
      alignment: `The stars align — ${entities.join(', ')} resonate in celestial harmony. This is the hour of peak efficiency, but also the moment of greatest vulnerability to resonance cascades.`,
      nova: `A new star blazes — ${entities[0] ?? 'an unknown source'} erupts with startling brilliance. Is this birth or cataclysm? The spectrum will tell.`,
      void: `The sky darkens where light should be — silence from ${entities.join(', ')}. The absence of signal is itself the most urgent signal.`,
    };

    const symbols: Record<CelestialPatternType, string[]> = {
      convergence: ['gravity', 'concentration', 'pressure', 'attraction'],
      divergence: ['separation', 'isolation', 'fracture', 'independence'],
      eclipse: ['shadow', 'obscuration', 'dependency', 'interference'],
      alignment: ['harmony', 'synchrony', 'resonance', 'amplification'],
      nova: ['eruption', 'brightness', 'surprise', 'intensity'],
      void: ['silence', 'absence', 'darkness', 'unknown'],
    };

    const significance = this.patternSignificance(patternType);
    const confidence = 60 + Math.random() * 35;

    return {
      patternId,
      patternType,
      meaning: meanings[patternType],
      significance,
      affectedDomains: this.mapToAffectedDomains(patternType),
      confidence: Math.round(confidence * 100) / 100,
      narrative: narratives[patternType],
      keySymbols: symbols[patternType],
      historicalPrecedent: this.findHistoricalPrecedent(patternType),
      crossReferences: this.findCrossReferences(patternType),
      interpretedAt: Date.now(),
    };
  }

  private patternSignificance(patternType: CelestialPatternType): Interpretation['significance'] {
    const map: Record<CelestialPatternType, Interpretation['significance']> = {
      alignment: 'notable',
      convergence: 'major',
      divergence: 'minor',
      eclipse: 'major',
      nova: 'epochal',
      void: 'notable',
    };
    return map[patternType] ?? 'minor';
  }

  private mapToAffectedDomains(patternType: CelestialPatternType): string[] {
    const domainMap: Record<CelestialPatternType, string[]> = {
      convergence: ['compute', 'network', 'storage'],
      divergence: ['network', 'security', 'communication'],
      eclipse: ['dependencies', 'observability', 'redundancy'],
      alignment: ['performance', 'throughput', 'stability'],
      nova: ['security', 'capacity', 'incident_response'],
      void: ['observability', 'monitoring', 'availability'],
    };
    return domainMap[patternType] ?? [];
  }

  private findHistoricalPrecedent(patternType: CelestialPatternType): string {
    const precedents: Record<CelestialPatternType, string> = {
      convergence: 'The Great Convergence of Epoch 7 — three hubs merged traffic causing cascading timeout failures.',
      divergence: 'Divergence Event DX-12 — cluster partition led to split-brain data inconsistency.',
      eclipse: 'Eclipse of the Forge — primary CI/CD shadow caused all deployment pipelines to stall.',
      alignment: 'Harmonic Alignment ARC-004 — peak throughput achieved but amplified a latent deadlock bug.',
      nova: 'Nova Incident N-01 — unprecedented traffic spike traced to misconfigured retry storm.',
      void: 'The Great Silence — monitoring agent failure masked a 4-hour outage across two hubs.',
    };
    return precedents[patternType];
  }

  private findCrossReferences(patternType: CelestialPatternType): string[] {
    const refs: Record<CelestialPatternType, string[]> = {
      convergence: ['DET-convergence-hub-overlap', 'PAT-resource-concentration'],
      divergence: ['DET-network-partition', 'PAT-cluster-split'],
      eclipse: ['DET-dependency-shadow', 'PAT-cascading-failure'],
      alignment: ['PAT-harmonic-sync', 'DET-resonance-cascade'],
      nova: ['DET-spike-anomaly', 'PAT-capacity-breach'],
      void: ['DET-missing-telemetry', 'PAT-dark-zone'],
    };
    return refs[patternType];
  }

  // ───────────────────────────────────────────────────────────────────────
  // Prediction Helpers
  // ───────────────────────────────────────────────────────────────────────

  private determineTrend(patternType: CelestialPatternType): Prediction['overallTrend'] {
    const map: Record<CelestialPatternType, Prediction['overallTrend']> = {
      convergence: 'volatile',
      divergence: 'degrading',
      eclipse: 'degrading',
      alignment: 'improving',
      nova: 'critical',
      void: 'critical',
    };
    return map[patternType] ?? 'stable';
  }

  private generateForecast(
    patternType: CelestialPatternType,
    timeframe: AstrologerInput['timeframe'],
    entities: string[]
  ): PredictionEntry[] {
    const periods = timeframe === 'immediate' ? 3 : timeframe === 'short_term' ? 5 : timeframe === 'medium_term' ? 7 : 10;
    const entries: PredictionEntry[] = [];

    for (let i = 1; i <= periods; i++) {
      const decayFactor = 1 - (i * 0.08);
      const baseProbability = (50 + Math.random() * 40) * decayFactor;
      const impactLevels: PredictionEntry['impact'][] = ['negligible', 'low', 'moderate', 'high', 'catastrophic'];
      const indicators: PredictionEntry['indicator'][] = ['bullish', 'neutral', 'bearish'];

      entries.push({
        period: `T+${i}`,
        description: this.forecastDescription(patternType, i, entities),
        probability: Math.round(baseProbability * 100) / 100,
        impact: impactLevels[Math.min(4, Math.floor(patternType === 'nova' || patternType === 'void' ? 2 + Math.random() * 3 : Math.random() * 3))],
        affectedSystems: entities.slice(0, Math.min(entities.length, 1 + Math.floor(Math.random() * 2))),
        indicator: indicators[Math.floor(Math.random() * 3)],
      });
    }

    return entries;
  }

  private forecastDescription(patternType: CelestialPatternType, period: number, entities: string[]): string {
    const templates: Record<CelestialPatternType, string[]> = {
      convergence: [
        `${entities[0] ?? 'Systems'} experience increased load pressure as convergence intensifies`,
        'Resource contention reaches peak — auto-scaling should activate',
        'Convergence begins to disperse — normal service resuming',
      ],
      divergence: [
        'Communication gaps widen between diverging systems',
        'Data consistency at risk — sync mechanisms should engage',
        'Divergence stabilises — new equilibrium forming',
      ],
      eclipse: [
        'Eclipsed systems report degraded visibility',
        'Shadow load peaks — dependency fallback chains tested',
        'Eclipse passes — secondary systems re-emerge',
      ],
      alignment: [
        'Systems approach harmonic resonance — throughput peaking',
        'Maximum alignment — optimal performance window',
        'Alignment begins to shift — efficiency gradually declining',
      ],
      nova: [
        'Nova event detected — intensity building rapidly',
        'Peak brightness — maximum impact on surrounding systems',
        'Nova fading — residual effects persist, recovery beginning',
      ],
      void: [
        'Signal absence confirmed — dark zone expanding',
        'Void at maximum extent — no telemetry from affected systems',
        'Signal tentatively returning — void may be receding',
      ],
    };

    const pool = templates[patternType] ?? templates.alignment;
    return pool[Math.min(period - 1, pool.length - 1)];
  }

  private identifyKeyDrivers(patternType: CelestialPatternType): string[] {
    const drivers: Record<CelestialPatternType, string[]> = {
      convergence: ['traffic_growth', 'resource_concentration', 'load_balancer_config'],
      divergence: ['network_partition', 'configuration_drift', 'deployment_asynchrony'],
      eclipse: ['dependency_heavy_load', 'cascading_requests', 'shared_resource_contention'],
      alignment: ['synchronised_schedules', 'harmonic_frequencies', 'shared_caches'],
      nova: ['unexpected_spike', 'retry_storm', 'external_event'],
      void: ['agent_failure', 'network_outage', 'telemetry_suppression'],
    };
    return drivers[patternType] ?? [];
  }

  private identifyRiskFactors(patternType: CelestialPatternType): string[] {
    const risks: Record<CelestialPatternType, string[]> = {
      convergence: ['capacity_exhaustion', 'cascading_timeout', 'single_point_failure'],
      divergence: ['data_inconsistency', 'split_brain', 'orphaned_processes'],
      eclipse: ['shadow_overload', 'fallback_failure', 'visibility_loss'],
      alignment: ['resonance_cascade', 'amplified_failure', 'synchronised_outage'],
      nova: ['capacity_breach', 'service_degradation', 'incident_escalation'],
      void: ['blind_spot', 'delayed_detection', 'silent_failure'],
    };
    return risks[patternType] ?? [];
  }

  private timelineLabel(timeframe: AstrologerInput['timeframe']): string {
    switch (timeframe) {
      case 'immediate': return '0-15 minutes';
      case 'short_term': return '15 minutes - 4 hours';
      case 'medium_term': return '4 hours - 3 days';
      case 'long_term': return '3 days - 30 days';
      default: return 'unspecified';
    }
  }

  // ───────────────────────────────────────────────────────────────────────
  // Advice Helpers
  // ───────────────────────────────────────────────────────────────────────

  private primaryRecommendation(
    patternType: CelestialPatternType,
    riskTolerance: AstrologerInput['riskTolerance']
  ): string {
    const conservative: Record<CelestialPatternType, string> = {
      convergence: 'Pre-provision additional capacity at convergence points. Enable auto-scaling with conservative thresholds.',
      divergence: 'Establish redundant communication paths. Pre-deploy sync reconciliation agents.',
      eclipse: 'Activate secondary observability pipelines. Pre-warm fallback service instances.',
      alignment: 'Monitor resonance indicators closely. Prepare circuit breakers for cascade prevention.',
      nova: 'Invoke incident response protocol immediately. Isolate affected systems.',
      void: 'Deploy backup monitoring agents. Establish out-of-band health checks.',
    };

    const aggressive: Record<CelestialPatternType, string> = {
      convergence: 'Redirect traffic to underutilised nodes. Implement aggressive load shedding at convergence edges.',
      divergence: 'Force synchronise via administrative override. Accept temporary inconsistency for availability.',
      eclipse: 'Manually promote eclipsed systems. Bypass shadow dependencies.',
      alignment: 'Ride the alignment wave — push maximum throughput. Disable non-critical safety limits temporarily.',
      nova: 'Aggressively scale horizontally. Accept elevated error rates to maintain partial availability.',
      void: 'Send targeted probe agents into the void. Accept risk of probe loss.',
    };

    return riskTolerance === 'aggressive' ? aggressive[patternType] : conservative[patternType];
  }

  private generateAdvisedActions(
    patternType: CelestialPatternType,
    riskTolerance: AstrologerInput['riskTolerance']
  ): AdvisedAction[] {
    const baseActions: Record<CelestialPatternType, AdvisedAction[]> = {
      convergence: [
        { step: 1, action: 'Verify auto-scaling policies are active', target: 'infrastructure', expectedOutcome: 'Scaling events triggered', urgency: 'within_hour', dependencies: [] },
        { step: 2, action: 'Increase monitoring frequency to 10s intervals', target: 'observatory', expectedOutcome: 'Faster anomaly detection', urgency: 'immediate', dependencies: [] },
        { step: 3, action: 'Pre-warm additional service instances', target: 'compute_cluster', expectedOutcome: 'Buffer capacity available', urgency: 'within_hour', dependencies: ['step_1'] },
      ],
      divergence: [
        { step: 1, action: 'Verify network connectivity between diverging systems', target: 'network_layer', expectedOutcome: 'Connectivity confirmed or issue isolated', urgency: 'immediate', dependencies: [] },
        { step: 2, action: 'Force data synchronisation checkpoint', target: 'data_layer', expectedOutcome: 'Consistency restored', urgency: 'within_hour', dependencies: ['step_1'] },
        { step: 3, action: 'Enable quorum-based decision making', target: 'cluster_manager', expectedOutcome: 'Split-brain prevention', urgency: 'within_hour', dependencies: [] },
      ],
      eclipse: [
        { step: 1, action: 'Activate secondary observability pipeline', target: 'monitoring', expectedOutcome: 'Visibility restored for eclipsed systems', urgency: 'immediate', dependencies: [] },
        { step: 2, action: 'Pre-warm fallback service instances', target: 'compute_cluster', expectedOutcome: 'Shadow load absorbed by fallbacks', urgency: 'within_hour', dependencies: [] },
        { step: 3, action: 'Review dependency health of eclipsed systems', target: 'service_mesh', expectedOutcome: 'Dependency status confirmed', urgency: 'within_day', dependencies: ['step_1'] },
      ],
      alignment: [
        { step: 1, action: 'Monitor resonance indicators and cascade potential', target: 'observatory', expectedOutcome: 'Early warning of resonance cascade', urgency: 'within_hour', dependencies: [] },
        { step: 2, action: 'Prepare circuit breaker activation thresholds', target: 'resilience_layer', expectedOutcome: 'Cascade isolation ready', urgency: 'within_day', dependencies: [] },
        { step: 3, action: 'Optimise for throughput during alignment window', target: 'workload_scheduler', expectedOutcome: 'Maximum efficiency achieved', urgency: 'within_day', dependencies: ['step_1'] },
      ],
      nova: [
        { step: 1, action: 'Invoke incident response protocol', target: 'incident_management', expectedOutcome: 'Response team activated', urgency: 'immediate', dependencies: [] },
        { step: 2, action: 'Isolate affected systems', target: 'security_layer', expectedOutcome: 'Blast radius contained', urgency: 'immediate', dependencies: ['step_1'] },
        { step: 3, action: 'Deploy additional capacity to absorb spike', target: 'infrastructure', expectedOutcome: 'Service maintained under load', urgency: 'within_hour', dependencies: ['step_2'] },
      ],
      void: [
        { step: 1, action: 'Deploy backup monitoring agents', target: 'observatory', expectedOutcome: 'Telemetry restored via alternate path', urgency: 'immediate', dependencies: [] },
        { step: 2, action: 'Establish out-of-band health checks', target: 'network_layer', expectedOutcome: 'Health status confirmed independently', urgency: 'immediate', dependencies: [] },
        { step: 3, action: 'Investigate root cause of signal absence', target: 'affected_systems', expectedOutcome: 'Void cause identified', urgency: 'within_hour', dependencies: ['step_1', 'step_2'] },
      ],
    };

    return baseActions[patternType] ?? [];
  }

  private generateReasoning(patternType: CelestialPatternType, significance: Interpretation['significance']): string {
    return `Based on the observed ${patternType} pattern (significance: ${significance}), the celestial data indicates a ${this.determineTrend(patternType)} trend. The recommended actions address the most probable progression of this pattern while accounting for known risk factors. Historical precedents suggest that early intervention significantly improves outcomes.`;
  }

  private generateAlternatives(patternType: CelestialPatternType): string[] {
    const alternatives: Record<CelestialPatternType, string[]> = {
      convergence: ['Allow natural convergence and accept temporary performance degradation', 'Redirect traffic away from convergence points entirely'],
      divergence: ['Allow divergence to complete and re-synchronise post-event', 'Force convergence via administrative override'],
      eclipse: ['Wait for eclipse to pass naturally', 'Manually restart eclipsed systems'],
      alignment: ['Do nothing — alignment is typically beneficial', 'Intentionally break alignment to prevent cascade risk'],
      nova: ['Observe and gather data before acting', 'Full system shutdown for safety'],
      void: ['Wait for signal to return naturally', 'Deploy physical inspection agents'],
    };
    return alternatives[patternType] ?? [];
  }

  private assessInactionRisk(patternType: CelestialPatternType): string {
    const risks: Record<CelestialPatternType, string> = {
      convergence: 'Without intervention, resource exhaustion at convergence points may cause cascading failures across dependent systems within 2-4 hours.',
      divergence: 'Continued divergence risks permanent data inconsistency and potential split-brain scenarios requiring manual reconciliation.',
      eclipse: 'Prolonged eclipse may cause the obscured systems to degrade beyond automatic recovery, requiring manual intervention.',
      alignment: 'While alignment is generally positive, extended resonance without circuit breakers risks amplified cascade failures.',
      nova: 'Uncontrolled nova events can rapidly exceed system capacity, leading to widespread service disruption and data loss.',
      void: 'Extended signal absence masks system health — failures may propagate undetected until they become catastrophic.',
    };
    return risks[patternType];
  }
}
