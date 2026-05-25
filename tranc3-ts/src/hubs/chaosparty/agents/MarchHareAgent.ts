/**
 * MarchHareAgent — Chaos Orchestration Agent for The Chaos Party
 *
 * Identity:  SID-CHAOSPARTY-MARCHHARE
 * Tier:      4 (Autonomous Microservice)
 * Parent:    TheChaosPartyAI (AID-CHAOSPARTY)
 *
 * Responsibilities:
 *   - Plan chaos scenarios with target selection and intensity mapping
 *   - Execute chaos operations by coordinating bot pipelines
 *   - Escalate chaos intensity when systems prove too resilient
 *   - Track chaos campaign history and effectiveness
 *   - Generate chaos recipes from scenario parameters
 *
 * "Why is a raven like a writing desk?"
 * The March Hare doesn't answer — it just breaks both and observes.
 */

import { Agent, Logger, AuditLedger } from '../../../core/definitions';

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface MarchHareInput {
  operation: 'plan' | 'execute' | 'escalate';
  scenarioId?: string;
  scenarioName?: string;
  scenarioType?: 'fuzz' | 'stress' | 'fault-injection' | 'randomisation' | 'entropy-burst' | 'circuit-break';
  target?: string;
  intensity?: 'mild' | 'medium' | 'hot' | 'unleashed';
  parameters?: Record<string, unknown>;
  duration?: number;
  escalationFactor?: number;
  campaignId?: string;
}

export interface ChaosPlan {
  planId: string;
  scenarioId: string;
  scenarioName: string;
  type: MarchHareInput['scenarioType'];
  target: string;
  intensity: NonNullable<MarchHareInput['intensity']>;
  phases: Array<{
    name: string;
    bot: string;
    operation: string;
    params: Record<string, unknown>;
    expectedEffect: string;
  }>;
  estimatedChaosIndex: number;
  riskAssessment: {
    level: 'low' | 'medium' | 'high' | 'critical';
    cascadingFailure: boolean;
    dataLossRisk: boolean;
    recoveryTime: string;
  };
  createdAt: number;
}

export interface ChaosExecution {
  executionId: string;
  planId: string;
  scenarioId: string;
  status: 'initiated' | 'brewing' | 'armed' | 'sweetening' | 'tasting' | 'completed' | 'failed';
  phaseResults: Array<{
    phase: string;
    bot: string;
    success: boolean;
    chaosContributed: number;
    timestamp: number;
    details: Record<string, unknown>;
  }>;
  totalChaosContributed: number;
  startedAt: number;
  completedAt?: number;
}

export interface ChaosEscalation {
  escalationId: string;
  scenarioId: string;
  previousIntensity: string;
  newIntensity: string;
  escalationFactor: number;
  reason: string;
  additionalPhases: Array<{
    name: string;
    bot: string;
    operation: string;
    params: Record<string, unknown>;
  }>;
  timestamp: number;
}

export interface MarchHareResult {
  success: boolean;
  operation: MarchHareInput['operation'];
  plan?: ChaosPlan;
  execution?: ChaosExecution;
  escalation?: ChaosEscalation;
  message: string;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// MarchHareAgent Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class MarchHareAgent extends Agent {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private readonly plans: Map<string, ChaosPlan>;
  private readonly executions: Map<string, ChaosExecution>;
  private readonly escalations: Array<ChaosEscalation>;
  private readonly campaignHistory: Map<string, Array<{ scenarioId: string; intensity: string; result: string }>>;

  constructor() {
    super('SID-CHAOSPARTY-MARCHHARE');
    this.log = new Logger('MarchHareAgent');
    this.audit = AuditLedger.getInstance();
    this.plans = new Map();
    this.executions = new Map();
    this.escalations = [];
    this.campaignHistory = new Map();
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Agent Lifecycle: Perceive → Decide → Act
  // ─────────────────────────────────────────────────────────────────────────

  protected async perceive(input: MarchHareInput): Promise<MarchHareInput> {
    this.log.info('Perceiving chaos operation', { operation: input.operation });

    // Validate scenario references
    if (input.scenarioId) {
      this.log.debug('Scenario reference present', { scenarioId: input.scenarioId });
    }

    // Validate intensity escalation path
    if (input.operation === 'escalate' && input.escalationFactor) {
      if (input.escalationFactor < 1 || input.escalationFactor > 5) {
        this.log.warn('Escalation factor out of range', { factor: input.escalationFactor });
      }
    }

    // Check campaign history for similar targets
    if (input.target) {
      const history = this.campaignHistory.get(input.target) ?? [];
      this.log.debug('Target campaign history', { target: input.target, previousRuns: history.length });
    }

    return input;
  }

  protected async decide(input: MarchHareInput): Promise<string> {
    this.log.info('Deciding chaos action', { operation: input.operation });

    switch (input.operation) {
      case 'plan': return 'planChaos';
      case 'execute': return 'executeChaos';
      case 'escalate': return 'escalateChaos';
      default: return 'unknown';
    }
  }

  protected async act(input: MarchHareInput, decision: string): Promise<MarchHareResult> {
    this.log.info('Acting on chaos decision', { decision });

    switch (decision) {
      case 'planChaos': return this.planChaos(input);
      case 'executeChaos': return this.executeChaos(input);
      case 'escalateChaos': return this.escalateChaos(input);
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
  // Plan Chaos
  // ─────────────────────────────────────────────────────────────────────────

  private planChaos(input: MarchHareInput): MarchHareResult {
    const scenarioId = input.scenarioId ?? `CHAOS-${this.plans.size + 1}`;
    const scenarioName = input.scenarioName ?? `Unnamed Chaos ${Date.now()}`;
    const type = input.scenarioType ?? 'fuzz';
    const target = input.target ?? 'system-default';
    const intensity = input.intensity ?? 'medium';
    const duration = input.duration ?? 60000;

    // Build phased plan based on type and intensity
    const phases = this.buildChaosPhases(type, intensity, target, duration);

    // Estimate chaos index contribution
    const intensityMultiplier: Record<string, number> = {
      mild: 5, medium: 15, hot: 30, unleashed: 50,
    };
    const estimatedChaosIndex = Math.min(100,
      (intensityMultiplier[intensity] ?? 15) * phases.length
    );

    // Risk assessment
    const riskAssessment = this.assessRisk(type, intensity, target);

    const plan: ChaosPlan = {
      planId: `PLAN-${this.plans.size + 1}`,
      scenarioId,
      scenarioName,
      type,
      target,
      intensity,
      phases,
      estimatedChaosIndex,
      riskAssessment,
      createdAt: Date.now(),
    };

    this.plans.set(plan.planId, plan);

    this.audit.append({
      actor: this.id,
      action: 'CHAOS_PLAN_CREATED',
      entity: plan.planId,
      status: 'SUCCESS',
      meta: { scenarioName, type, intensity, target, phaseCount: phases.length },
    });

    this.log.info('Chaos plan created', {
      planId: plan.planId,
      phases: phases.length,
      estimatedChaosIndex,
      riskLevel: riskAssessment.level,
    });

    return {
      success: true,
      operation: 'plan',
      plan,
      message: `Chaos plan "${scenarioName}" created with ${phases.length} phases at ${intensity} intensity`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Execute Chaos
  // ─────────────────────────────────────────────────────────────────────────

  private executeChaos(input: MarchHareInput): MarchHareResult {
    // Find plan or create inline execution
    let plan = input.scenarioId ? this.findPlanByScenario(input.scenarioId) : undefined;

    if (!plan) {
      // Auto-plan if no plan exists
      const planResult = this.planChaos(input);
      plan = planResult.plan!;
    }

    const executionId = `EXEC-${this.executions.size + 1}`;
    const phaseResults: ChaosExecution['phaseResults'] = [];
    let totalChaosContributed = 0;

    // Simulate executing each phase in sequence
    for (const phase of plan.phases) {
      const success = Math.random() > 0.1; // 90% success rate per phase
      const chaosContributed = success ? Math.floor(Math.random() * 20) + 5 : 0;
      totalChaosContributed += chaosContributed;

      phaseResults.push({
        phase: phase.name,
        bot: phase.bot,
        success,
        chaosContributed,
        timestamp: Date.now(),
        details: success
          ? { effect: phase.expectedEffect, chaosGenerated: chaosContributed }
          : { error: 'Phase execution failed — chaos was absorbed', chaosGenerated: 0 },
      });
    }

    const allSucceeded = phaseResults.every((r) => r.success);
    const someSucceeded = phaseResults.some((r) => r.success);

    const execution: ChaosExecution = {
      executionId,
      planId: plan.planId,
      scenarioId: plan.scenarioId,
      status: allSucceeded ? 'completed' : someSucceeded ? 'completed' : 'failed',
      phaseResults,
      totalChaosContributed,
      startedAt: Date.now() - plan.phases.length * 1000,
      completedAt: Date.now(),
    };

    this.executions.set(executionId, execution);

    // Update campaign history
    const history = this.campaignHistory.get(plan.target) ?? [];
    history.push({
      scenarioId: plan.scenarioId,
      intensity: plan.intensity,
      result: execution.status,
    });
    this.campaignHistory.set(plan.target, history);

    this.audit.append({
      actor: this.id,
      action: 'CHAOS_EXECUTED',
      entity: executionId,
      status: allSucceeded ? 'SUCCESS' : 'PARTIAL',
      meta: {
        planId: plan.planId,
        phases: phaseResults.length,
        succeeded: phaseResults.filter((r) => r.success).length,
        totalChaosContributed,
      },
    });

    this.log.info('Chaos executed', {
      executionId,
      status: execution.status,
      totalChaosContributed,
      phaseResults: phaseResults.length,
    });

    return {
      success: someSucceeded,
      operation: 'execute',
      execution,
      message: someSucceeded
        ? `Chaos execution ${executionId} completed — ${totalChaosContributed} chaos units generated`
        : `Chaos execution ${executionId} failed — system absorbed all disruption`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Escalate Chaos
  // ─────────────────────────────────────────────────────────────────────────

  private escalateChaos(input: MarchHareInput): MarchHareResult {
    const scenarioId = input.scenarioId ?? 'CHAOS-1';
    const escalationFactor = input.escalationFactor ?? 2;

    // Determine current and new intensity
    const intensityLadder: Array<MarchHareInput['intensity']> = ['mild', 'medium', 'hot', 'unleashed'];
    const currentIntensity = input.intensity ?? 'medium';
    const currentIndex = intensityLadder.indexOf(currentIntensity);
    const newIndex = Math.min(intensityLadder.length - 1, currentIndex + Math.min(escalationFactor, 3));
    const newIntensity = intensityLadder[newIndex] ?? 'unleashed';

    // Generate additional escalation phases
    const target = input.target ?? 'system-default';
    const additionalPhases = this.buildChaosPhases(
      input.scenarioType ?? 'entropy-burst',
      newIntensity ?? 'hot',
      target,
      input.duration ?? 30000
    ).slice(0, escalationFactor); // Add phases proportional to escalation

    // Build escalation record
    const escalation: ChaosEscalation = {
      escalationId: `ESC-${this.escalations.length + 1}`,
      scenarioId,
      previousIntensity: currentIntensity ?? 'medium',
      newIntensity: newIntensity ?? 'hot',
      escalationFactor,
      reason: this.generateEscalationReason(currentIntensity, newIntensity, input.parameters),
      additionalPhases,
      timestamp: Date.now(),
    };

    this.escalations.push(escalation);

    this.audit.append({
      actor: this.id,
      action: 'CHAOS_ESCALATED',
      entity: escalation.escalationId,
      status: 'SUCCESS',
      meta: {
        scenarioId,
        from: escalation.previousIntensity,
        to: escalation.newIntensity,
        additionalPhases: additionalPhases.length,
      },
    });

    this.log.info('Chaos escalated', {
      escalationId: escalation.escalationId,
      from: escalation.previousIntensity,
      to: escalation.newIntensity,
      additionalPhases: additionalPhases.length,
    });

    return {
      success: true,
      operation: 'escalate',
      escalation,
      message: `Chaos escalated from ${escalation.previousIntensity} to ${escalation.newIntensity} — ${additionalPhases.length} additional phases added`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Chaos Phase Builder
  // ─────────────────────────────────────────────────────────────────────────

  private buildChaosPhases(
    type: NonNullable<MarchHareInput['scenarioType']>,
    intensity: NonNullable<MarchHareInput['intensity']>,
    target: string,
    duration: number
  ): ChaosPlan['phases'] {
    const phaseDuration = Math.floor(duration / 4);
    const phases: ChaosPlan['phases'] = [];

    // Phase 1: Brew — TeapotBot prepares the chaos
    phases.push({
      name: 'Brew Chaos',
      bot: 'Teapot',
      operation: 'BREW',
      params: {
        recipe: `${type}-${intensity}-blend`,
        intensity,
        servings: intensity === 'unleashed' ? 5 : intensity === 'hot' ? 3 : 1,
        sugarLevel: intensity === 'mild' ? 20 : intensity === 'medium' ? 50 : 80,
      },
      expectedEffect: `Prepare ${intensity} ${type} chaos recipe targeting ${target}`,
    });

    // Phase 2: Arm — PocketWatchBot sets timing
    phases.push({
      name: 'Arm Time Bomb',
      bot: 'PocketWatch',
      operation: 'ARM',
      params: {
        delay: phaseDuration,
        payload: { type, target },
        type: intensity === 'unleashed' ? 'random' : 'delayed',
        recurring: intensity === 'hot' || intensity === 'unleashed',
      },
      expectedEffect: `Arm ${intensity === 'unleashed' ? 'random' : 'delayed'} trigger for ${phaseDuration}ms`,
    });

    // Phase 3: Sweeten — SugarCubeBot adds perturbation
    phases.push({
      name: 'Add Perturbation',
      bot: 'SugarCube',
      operation: 'SWEETEN',
      params: {
        target,
        perturbation: type,
        amount: intensity === 'unleashed' ? 100 : intensity === 'hot' ? 75 : 30,
        dissolveTime: phaseDuration,
      },
      expectedEffect: `Inject ${type} perturbation into ${target} at ${intensity} strength`,
    });

    // Phase 4: Taste — JamTartBot analyses results
    phases.push({
      name: 'Taste Results',
      bot: 'JamTart',
      operation: 'TASTE',
      params: {
        scenarioId: 'auto',
        flavour: intensity === 'unleashed' ? 'bitter' : 'mixed',
      },
      expectedEffect: `Analyse chaos impact and generate flavour report`,
    });

    return phases;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Risk Assessment
  // ─────────────────────────────────────────────────────────────────────────

  private assessRisk(
    type: NonNullable<MarchHareInput['scenarioType']>,
    intensity: NonNullable<MarchHareInput['intensity']>,
    target: string
  ): ChaosPlan['riskAssessment'] {
    // Base risk by type
    const typeRisk: Record<string, 'low' | 'medium' | 'high' | 'critical'> = {
      fuzz: 'low',
      stress: 'medium',
      'fault-injection': 'high',
      randomisation: 'low',
      'entropy-burst': 'medium',
      'circuit-break': 'high',
    };

    // Intensity escalation
    const intensityEscalation: Record<string, number> = {
      mild: 0, medium: 1, hot: 2, unleashed: 3,
    };

    const levels: Array<'low' | 'medium' | 'high' | 'critical'> = ['low', 'medium', 'high', 'critical'];
    const baseLevel = levels.indexOf(typeRisk[type] ?? 'medium');
    const escalatedLevel = Math.min(3, baseLevel + intensityEscalation[intensity]);

    const level = levels[escalatedLevel];

    // Determine specific risks
    const cascadingFailure = level === 'critical' || (level === 'high' && type === 'fault-injection');
    const dataLossRisk = type === 'fault-injection' && (intensity === 'hot' || intensity === 'unleashed');

    const recoveryTime: Record<string, string> = {
      low: '< 1 minute',
      medium: '1-5 minutes',
      high: '5-30 minutes',
      critical: '30+ minutes (may require manual intervention)',
    };

    return {
      level,
      cascadingFailure,
      dataLossRisk,
      recoveryTime: recoveryTime[level],
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Utilities
  // ─────────────────────────────────────────────────────────────────────────

  private findPlanByScenario(scenarioId: string): ChaosPlan | undefined {
    for (const plan of this.plans.values()) {
      if (plan.scenarioId === scenarioId) return plan;
    }
    return undefined;
  }

  private generateEscalationReason(
    from: string | undefined,
    to: string | undefined,
    params?: Record<string, unknown>
  ): string {
    const reasons = [
      `System resilience detected at ${from ?? 'medium'} intensity — escalating to ${to ?? 'hot'}`,
      `Target absorbing disruption — increasing entropy injection`,
      `Chaos index below expected threshold — amplifying scenario`,
    ];

    if (params?.reason) return String(params.reason);
    return reasons[Math.floor(Math.random() * reasons.length)];
  }
}
