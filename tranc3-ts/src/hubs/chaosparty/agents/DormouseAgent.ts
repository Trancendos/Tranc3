/**
 * DormouseAgent — Chaos Calming & Stabilisation Agent for The Chaos Party
 *
 * Identity:  SID-CHAOSPARTY-DORMOUSE
 * Tier:      4 (Autonomous Microservice)
 * Parent:    TheChaosPartyAI (AID-CHAOSPARTY)
 *
 * Responsibilities:
 *   - Assess the current chaos level and system impact
 *   - Calm disruptive chaos events that exceed thresholds
 *   - Stabilise the system after chaos campaigns complete
 *   - Monitor resilience scores and recovery trajectories
 *   - Provide recommendations for chaos containment
 *
 * "You might just as well say that 'I see what I eat' is the same
 *  thing as 'I eat what I see'!" — The Dormouse, mostly asleep
 */

import { Agent, Logger, AuditLedger } from '../../../core/definitions'

const auditLedger = new AuditLedger();

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface DormouseInput {
  operation: 'assess' | 'calm' | 'stabilise';
  scenarioId?: string;
  chaosIndex?: number;
  resilienceScore?: number;
  activeEvents?: Array<{
    id: string;
    type: string;
    effect: 'disruptive' | 'subtle' | 'catalytic' | 'nullifying';
    target: string;
    age: number;
  }>;
  threshold?: number;
  targetSystem?: string;
  calmStrategy?: 'gradual' | 'immediate' | 'selective' | 'cascade';
  stabilisationTarget?: number;
}

export interface ChaosAssessment {
  assessmentId: string;
  scenarioId?: string;
  currentChaosIndex: number;
  currentResilience: number;
  impactLevel: 'negligible' | 'minor' | 'moderate' | 'severe' | 'critical';
  activeDisruptions: number;
  systemStability: number; // 0..100
  affectedTargets: string[];
  riskTrajectory: 'improving' | 'stable' | 'degrading' | 'critical';
  recommendedAction: 'monitor' | 'calm' | 'stabilise' | 'emergency-shutdown';
  assessmentDetails: {
    eventBreakdown: Record<string, number>;
    peakChaosIndex: number;
    averageChaosDuration: number;
    cascadingRisk: boolean;
    dataIntegrity: number;
  };
  timestamp: number;
}

export interface CalmResult {
  calmId: string;
  strategy: NonNullable<DormouseInput['calmStrategy']>;
  eventsCalmed: number;
  eventsRemaining: number;
  chaosIndexBefore: number;
  chaosIndexAfter: number;
  resilienceChange: number;
  calmingActions: Array<{
    eventId: string;
    action: 'defused' | 'absorbed' | 'redirected' | 'nullified';
    success: boolean;
    reductionInChaos: number;
  }>;
  sideEffects: string[];
  timestamp: number;
}

export interface StabilisationResult {
  stabilisationId: string;
  targetSystem: string;
  chaosIndexStart: number;
  chaosIndexEnd: number;
  resilienceStart: number;
  resilienceEnd: number;
  stabilisationTarget: number;
  achieved: boolean;
  phases: Array<{
    name: string;
    action: string;
    chaosReduction: number;
    resilienceGain: number;
    timestamp: number;
  }>;
  recoveryTime: number;
  timestamp: number;
}

export interface DormouseResult {
  success: boolean;
  operation: DormouseInput['operation'];
  assessment?: ChaosAssessment;
  calm?: CalmResult;
  stabilisation?: StabilisationResult;
  message: string;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// DormouseAgent Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class DormouseAgent extends Agent {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private readonly assessmentHistory: Array<ChaosAssessment>;
  private readonly calmHistory: Array<CalmResult>;
  private readonly stabilisationHistory: Array<StabilisationResult>;
  private baselineChaosIndex: number;
  private baselineResilience: number;

  constructor() {
    super('SID-CHAOSPARTY-DORMOUSE');
    this.log = new Logger('DormouseAgent');
    this.audit = auditLedger;
    this.assessmentHistory = [];
    this.calmHistory = [];
    this.stabilisationHistory = [];
    this.baselineChaosIndex = 0;
    this.baselineResilience = 100;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Agent Lifecycle: Perceive → Decide → Act
  // ─────────────────────────────────────────────────────────────────────────

  public async perceive(input: DormouseInput): Promise<DormouseInput> {
    this.log.info('Perceiving chaos calming operation', { operation: input.operation });

    // Enrich with current state if not provided
    if (input.chaosIndex === undefined) {
      this.log.debug('No chaos index provided — using last known baseline');
      input.chaosIndex = this.baselineChaosIndex;
    }

    if (input.resilienceScore === undefined) {
      input.resilienceScore = this.baselineResilience;
    }

    // Validate threshold
    if (input.threshold !== undefined && (input.threshold < 0 || input.threshold > 100)) {
      this.log.warn('Threshold out of valid range (0-100)', { threshold: input.threshold });
    }

    // Check for active events
    if (input.activeEvents && input.activeEvents.length > 0) {
      const disruptiveCount = input.activeEvents.filter((e) => e.effect === 'disruptive').length;
      this.log.debug('Active events detected', {
        total: input.activeEvents.length,
        disruptive: disruptiveCount,
      });
    }

    return input;
  }

  public async decide(input: DormouseInput): Promise<string> {
    this.log.info('Deciding calming action', { operation: input.operation });

    switch (input.operation) {
      case 'assess': return 'assessChaos';
      case 'calm': return 'calmChaos';
      case 'stabilise': return 'stabiliseSystem';
      default: return 'unknown';
    }
  }

  public async act(input: DormouseInput, decision: string): Promise<DormouseResult> {
    this.log.info('Acting on calming decision', { decision });

    switch (decision) {
      case 'assessChaos': return this.assessChaos(input);
      case 'calmChaos': return this.calmChaos(input);
      case 'stabiliseSystem': return this.stabiliseSystem(input);
      default:
        return {
          success: false,
          operation: input.operation,
          message: `Unknown operation: ${input.operation}`,
          timestamp: Date.now(),
        };
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Assess Chaos
  // ─────────────────────────────────────────────────────────────────────────

  private assessChaos(input: DormouseInput): DormouseResult {
    const chaosIndex = input.chaosIndex ?? this.baselineChaosIndex;
    const resilience = input.resilienceScore ?? this.baselineResilience;
    const activeEvents = input.activeEvents ?? [];

    // Determine impact level
    let impactLevel: ChaosAssessment['impactLevel'];
    if (chaosIndex <= 10) impactLevel = 'negligible';
    else if (chaosIndex <= 25) impactLevel = 'minor';
    else if (chaosIndex <= 50) impactLevel = 'moderate';
    else if (chaosIndex <= 75) impactLevel = 'severe';
    else impactLevel = 'critical';

    // Calculate system stability (inverse of chaos, adjusted by resilience)
    const systemStability = Math.max(0, Math.min(100,
      (100 - chaosIndex) * 0.6 + resilience * 0.4
    ));

    // Determine risk trajectory
    let riskTrajectory: ChaosAssessment['riskTrajectory'];
    if (this.assessmentHistory.length >= 2) {
      const recent = this.assessmentHistory.slice(-2);
      if (recent[1].currentChaosIndex < recent[0].currentChaosIndex) {
        riskTrajectory = 'improving';
      } else if (recent[1].currentChaosIndex === recent[0].currentChaosIndex) {
        riskTrajectory = 'stable';
      } else if (recent[1].currentChaosIndex < 75) {
        riskTrajectory = 'degrading';
      } else {
        riskTrajectory = 'critical';
      }
    } else {
      riskTrajectory = chaosIndex <= 25 ? 'stable' : 'degrading';
    }

    // Recommended action
    let recommendedAction: ChaosAssessment['recommendedAction'];
    if (chaosIndex <= 15 && resilience >= 80) recommendedAction = 'monitor';
    else if (chaosIndex <= 40) recommendedAction = 'calm';
    else if (chaosIndex <= 70) recommendedAction = 'stabilise';
    else recommendedAction = 'emergency-shutdown';

    // Event breakdown
    const eventBreakdown: Record<string, number> = {};
    for (const event of activeEvents) {
      eventBreakdown[event.effect] = (eventBreakdown[event.effect] ?? 0) + 1;
    }

    // Affected targets
    const affectedTargets = [...new Set(activeEvents.map((e) => e.target))];

    // Peak chaos from history
    const peakChaosIndex = this.assessmentHistory.length > 0
      ? Math.max(...this.assessmentHistory.map((a) => a.currentChaosIndex), chaosIndex)
      : chaosIndex;

    // Cascading risk
    const cascadingRisk = activeEvents.filter((e) => e.effect === 'catalytic').length > 2;

    // Data integrity estimate
    const dataIntegrity = Math.max(0, 100 - (chaosIndex > 60 ? (chaosIndex - 60) * 2 : 0));

    const assessment: ChaosAssessment = {
      assessmentId: `ASSESS-${this.assessmentHistory.length + 1}`,
      scenarioId: input.scenarioId,
      currentChaosIndex: chaosIndex,
      currentResilience: resilience,
      impactLevel,
      activeDisruptions: activeEvents.filter((e) => e.effect === 'disruptive').length,
      systemStability,
      affectedTargets,
      riskTrajectory,
      recommendedAction,
      assessmentDetails: {
        eventBreakdown,
        peakChaosIndex,
        averageChaosDuration: activeEvents.length > 0
          ? activeEvents.reduce((sum, e) => sum + e.age, 0) / activeEvents.length
          : 0,
        cascadingRisk,
        dataIntegrity,
      },
      timestamp: Date.now(),
    };

    this.assessmentHistory.push(assessment);
    this.baselineChaosIndex = chaosIndex;
    this.baselineResilience = resilience;

    this.audit.append({
      actor: this.id,
      action: 'CHAOS_ASSESSED',
      entity: assessment.assessmentId,
      status: 'SUCCESS',
      meta: {
        chaosIndex,
        resilience,
        impactLevel,
        recommendedAction,
        activeDisruptions: assessment.activeDisruptions,
      },
    });

    this.log.info('Chaos assessed', {
      chaosIndex,
      impactLevel,
      riskTrajectory,
      recommendedAction,
    });

    return {
      success: true,
      operation: 'assess',
      assessment,
      message: `Chaos assessment: ${impactLevel} impact (index ${chaosIndex}) — recommend ${recommendedAction}`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Calm Chaos
  // ─────────────────────────────────────────────────────────────────────────

  private calmChaos(input: DormouseInput): DormouseResult {
    const strategy = input.calmStrategy ?? 'gradual';
    const chaosIndexBefore = input.chaosIndex ?? this.baselineChaosIndex;
    const activeEvents = input.activeEvents ?? [];
    const threshold = input.threshold ?? 25;

    // If chaos is already below threshold, nothing to calm
    if (chaosIndexBefore <= threshold) {
      return {
        success: true,
        operation: 'calm',
        calm: {
          calmId: `CALM-${this.calmHistory.length + 1}`,
          strategy,
          eventsCalmed: 0,
          eventsRemaining: activeEvents.length,
          chaosIndexBefore,
          chaosIndexAfter: chaosIndexBefore,
          resilienceChange: 0,
          calmingActions: [],
          sideEffects: ['Chaos already below threshold — no calming needed'],
          timestamp: Date.now(),
        },
        message: `Chaos index (${chaosIndexBefore}) already below threshold (${threshold}) — nothing to calm`,
        timestamp: Date.now(),
      };
    }

    // Apply calming strategy
    const calmingActions: CalmResult['calmingActions'] = [];
    const sideEffects: string[] = [];
    let totalChaosReduction = 0;

    const actionTypes: Array<'defused' | 'absorbed' | 'redirected' | 'nullified'> = [
      'defused', 'absorbed', 'redirected', 'nullified',
    ];

    // Strategy determines which events to target and how aggressively
    const eventsToTarget = this.selectEventsForCalming(activeEvents, strategy);

    for (const event of eventsToTarget) {
      const actionType = actionTypes[Math.floor(Math.random() * actionTypes.length)];
      const success = Math.random() > 0.15; // 85% success rate

      const reductionInChaos = success
        ? Math.floor(Math.random() * 15) + 5
        : 0;
      totalChaosReduction += reductionInChaos;

      calmingActions.push({
        eventId: event.id,
        action: actionType,
        success,
        reductionInChaos,
      });

      // Side effects from aggressive calming
      if (strategy === 'immediate' && Math.random() > 0.7) {
        sideEffects.push(`Residual ripple from rapid defusal of ${event.id}`);
      }
      if (actionType === 'redirected' && Math.random() > 0.6) {
        sideEffects.push(`Redirected chaos may affect downstream system: ${event.target}-secondary`);
      }
    }

    const chaosIndexAfter = Math.max(0, chaosIndexBefore - totalChaosReduction);
    const resilienceChange = Math.floor((chaosIndexBefore - chaosIndexAfter) * 0.3);
    const eventsCalmed = calmingActions.filter((a) => a.success).length;
    const eventsRemaining = activeEvents.length - eventsCalmed;

    const calmResult: CalmResult = {
      calmId: `CALM-${this.calmHistory.length + 1}`,
      strategy,
      eventsCalmed,
      eventsRemaining,
      chaosIndexBefore,
      chaosIndexAfter,
      resilienceChange,
      calmingActions,
      sideEffects,
      timestamp: Date.now(),
    };

    this.calmHistory.push(calmResult);
    this.baselineChaosIndex = chaosIndexAfter;
    this.baselineResilience = Math.min(100, this.baselineResilience + resilienceChange);

    this.audit.append({
      actor: this.id,
      action: 'CHAOS_CALMED',
      entity: calmResult.calmId,
      status: 'SUCCESS',
      meta: {
        strategy,
        eventsCalmed,
        chaosIndexBefore,
        chaosIndexAfter,
        resilienceChange,
      },
    });

    this.log.info('Chaos calmed', {
      strategy,
      eventsCalmed,
      chaosIndexBefore,
      chaosIndexAfter,
      resilienceChange,
    });

    return {
      success: eventsCalmed > 0,
      operation: 'calm',
      calm: calmResult,
      message: eventsCalmed > 0
        ? `Calmly addressed ${eventsCalmed} events — chaos index reduced from ${chaosIndexBefore} to ${chaosIndexAfter}`
        : 'Unable to calm any chaos events — the dormouse is too sleepy',
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Stabilise System
  // ─────────────────────────────────────────────────────────────────────────

  private stabiliseSystem(input: DormouseInput): DormouseResult {
    const targetSystem = input.targetSystem ?? 'default-system';
    const stabilisationTarget = input.stabilisationTarget ?? 10; // target chaos index
    const chaosIndexStart = input.chaosIndex ?? this.baselineChaosIndex;
    const resilienceStart = input.resilienceScore ?? this.baselineResilience;

    // Build stabilisation phases
    const phases: StabilisationResult['phases'] = [];
    let currentChaos = chaosIndexStart;
    let currentResilience = resilienceStart;

    // Phase 1: Assess and contain
    const containmentReduction = Math.floor(currentChaos * 0.3);
    currentChaos = Math.max(0, currentChaos - containmentReduction);
    currentResilience = Math.min(100, currentResilience + Math.floor(containmentReduction * 0.4));
    phases.push({
      name: 'Contain',
      action: 'Isolate active chaos zones and prevent spread',
      chaosReduction: containmentReduction,
      resilienceGain: Math.floor(containmentReduction * 0.4),
      timestamp: Date.now(),
    });

    // Phase 2: Drain
    if (currentChaos > stabilisationTarget * 2) {
      const drainReduction = Math.floor(currentChaos * 0.4);
      currentChaos = Math.max(0, currentChaos - drainReduction);
      currentResilience = Math.min(100, currentResilience + Math.floor(drainReduction * 0.3));
      phases.push({
        name: 'Drain',
        action: 'Systematically reduce chaos injection points',
        chaosReduction: drainReduction,
        resilienceGain: Math.floor(drainReduction * 0.3),
        timestamp: Date.now(),
      });
    }

    // Phase 3: Restore
    if (currentChaos > stabilisationTarget) {
      const restoreReduction = Math.floor((currentChaos - stabilisationTarget) * 0.7);
      currentChaos = Math.max(0, currentChaos - restoreReduction);
      currentResilience = Math.min(100, currentResilience + Math.floor(restoreReduction * 0.5));
      phases.push({
        name: 'Restore',
        action: 'Rebuild system resilience and verify integrity',
        chaosReduction: restoreReduction,
        resilienceGain: Math.floor(restoreReduction * 0.5),
        timestamp: Date.now(),
      });
    }

    // Phase 4: Verify
    const finalReduction = Math.max(0, currentChaos - stabilisationTarget);
    currentChaos = Math.max(0, currentChaos - finalReduction);
    currentResilience = Math.min(100, currentResilience + 5); // baseline recovery bonus
    phases.push({
      name: 'Verify',
      action: 'Confirm system stability and chaos containment',
      chaosReduction: finalReduction,
      resilienceGain: 5,
      timestamp: Date.now(),
    });

    const achieved = currentChaos <= stabilisationTarget;
    const totalChaosReduction = chaosIndexStart - currentChaos;
    const totalResilienceGain = currentResilience - resilienceStart;
    const recoveryTime = phases.length * 15000; // ~15s per phase estimate

    const stabilisation: StabilisationResult = {
      stabilisationId: `STAB-${this.stabilisationHistory.length + 1}`,
      targetSystem,
      chaosIndexStart,
      chaosIndexEnd: currentChaos,
      resilienceStart,
      resilienceEnd: currentResilience,
      stabilisationTarget,
      achieved,
      phases,
      recoveryTime,
      timestamp: Date.now(),
    };

    this.stabilisationHistory.push(stabilisation);
    this.baselineChaosIndex = currentChaos;
    this.baselineResilience = currentResilience;

    this.audit.append({
      actor: this.id,
      action: 'SYSTEM_STABILISED',
      entity: stabilisation.stabilisationId,
      status: achieved ? 'SUCCESS' : 'PENDING',
      meta: {
        targetSystem,
        chaosIndexStart,
        chaosIndexEnd: currentChaos,
        resilienceStart,
        resilienceEnd: currentResilience,
        achieved,
        phases: phases.length,
      },
    });

    this.log.info('System stabilised', {
      targetSystem,
      chaosIndexStart,
      chaosIndexEnd: currentChaos,
      achieved,
      phases: phases.length,
    });

    return {
      success: achieved,
      operation: 'stabilise',
      stabilisation,
      message: achieved
        ? `System "${targetSystem}" stabilised — chaos index reduced from ${chaosIndexStart} to ${currentChaos} (target: ${stabilisationTarget})`
        : `System "${targetSystem}" partially stabilised — chaos index reduced to ${currentChaos} (target: ${stabilisationTarget} not yet achieved)`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Event Selection for Calming
  // ─────────────────────────────────────────────────────────────────────────

  private selectEventsForCalming(
    events: DormouseInput['activeEvents'],
    strategy: NonNullable<DormouseInput['calmStrategy']>
  ): NonNullable<DormouseInput['activeEvents']> {
    if (!events || events.length === 0) return [];

    switch (strategy) {
      case 'immediate':
        // Target all events aggressively
        return [...events];

      case 'gradual':
        // Target most disruptive first, then catalytic
        return [...events].sort((a, b) => {
          const priority: Record<string, number> = { disruptive: 4, catalytic: 3, subtle: 2, nullifying: 1 };
          return (priority[b.effect] ?? 0) - (priority[a.effect] ?? 0);
        });

      case 'selective':
        // Only target disruptive events
        return events.filter((e) => e.effect === 'disruptive' || e.effect === 'catalytic');

      case 'cascade':
        // Target events that could cascade (oldest first)
        return [...events].sort((a, b) => a.age - b.age);

      default:
        return [...events];
    }
  }
}
