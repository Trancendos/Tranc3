/**
 * SugarCubeBot — Subtle Perturbation Bot for The Chaos Party
 *
 * Identity:  NID-CHAOSPARTY-SUGARCUBE
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TheChaosPartyAI (AID-CHAOSPARTY)
 *
 * Responsibilities:
 *   - Apply subtle perturbations to system parameters
 *   - Sweeten chaos with controlled amounts of disruption
 *   - Dissolve perturbations over configurable time periods
 *   - Track perturbation effects and accumulation
 *   - Support additive and multiplicative perturbation modes
 *
 * "A little sweetness goes a long way in chaos."
 */

import { Bot, Logger, AuditLedger } from '../../../core/definitions'

const auditLedger = new AuditLedger();

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface SugarCubeInput {
  operation: 'SWEETEN';
  target: string;
  perturbation: string;
  amount: number;
  dissolveTime: number;
  mode?: 'additive' | 'multiplicative' | 'replace' | 'noise';
  frequency?: 'once' | 'periodic' | 'continuous';
  variance?: number;
}

export interface PerturbationEffect {
  parameter: string;
  originalValue: number;
  perturbedValue: number;
  delta: number;
  direction: 'increase' | 'decrease' | 'random';
  mode: NonNullable<SugarCubeInput['mode']>;
}

export interface SweetenResult {
  success: boolean;
  target: string;
  perturbation: string;
  amount: number;
  dissolveTime: number;
  mode: NonNullable<SugarCubeInput['mode']>;
  frequency: NonNullable<SugarCubeInput['frequency']>;
  effects: PerturbationEffect[];
  totalDelta: number;
  chaosContribution: number;
  sweetness: number; // 0..100 — how subtle the perturbation is
  dissolution: {
    rate: number;
    unit: string;
    completeAt: number;
  };
  accumulation: {
    previousPerturbations: number;
    cumulativeEffect: number;
    riskOfSaturation: boolean;
  };
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Perturbation Mappings
// ─────────────────────────────────────────────────────────────────────────────

const PERTURBATION_TARGETS: Record<string, Array<{
  parameter: string;
  baseValue: number;
  unit: string;
  sensitivity: 'low' | 'medium' | 'high';
}>> = {
  'latency': [
    { parameter: 'response_time_ms', baseValue: 50, unit: 'ms', sensitivity: 'medium' },
    { parameter: 'timeout_threshold_ms', baseValue: 5000, unit: 'ms', sensitivity: 'high' },
    { parameter: 'retry_delay_ms', baseValue: 1000, unit: 'ms', sensitivity: 'low' },
  ],
  'memory': [
    { parameter: 'heap_usage_pct', baseValue: 45, unit: '%', sensitivity: 'high' },
    { parameter: 'gc_interval_ms', baseValue: 10000, unit: 'ms', sensitivity: 'medium' },
    { parameter: 'cache_size_mb', baseValue: 256, unit: 'MB', sensitivity: 'low' },
  ],
  'cpu': [
    { parameter: 'cpu_usage_pct', baseValue: 30, unit: '%', sensitivity: 'high' },
    { parameter: 'thread_count', baseValue: 8, unit: 'threads', sensitivity: 'medium' },
    { parameter: 'scheduler_interval_ms', baseValue: 100, unit: 'ms', sensitivity: 'low' },
  ],
  'network': [
    { parameter: 'bandwidth_mbps', baseValue: 1000, unit: 'Mbps', sensitivity: 'medium' },
    { parameter: 'packet_loss_pct', baseValue: 0.1, unit: '%', sensitivity: 'high' },
    { parameter: 'connection_pool_size', baseValue: 50, unit: 'connections', sensitivity: 'low' },
  ],
  'disk': [
    { parameter: 'iops', baseValue: 5000, unit: 'IOPS', sensitivity: 'medium' },
    { parameter: 'write_latency_ms', baseValue: 2, unit: 'ms', sensitivity: 'high' },
    { parameter: 'available_space_gb', baseValue: 500, unit: 'GB', sensitivity: 'low' },
  ],
  'fuzz': [
    { parameter: 'input_length', baseValue: 256, unit: 'bytes', sensitivity: 'medium' },
    { parameter: 'mutation_rate', baseValue: 0.05, unit: 'ratio', sensitivity: 'high' },
    { parameter: 'corpus_size', baseValue: 1000, unit: 'entries', sensitivity: 'low' },
  ],
  'randomisation': [
    { parameter: 'seed_value', baseValue: 42, unit: 'integer', sensitivity: 'high' },
    { parameter: 'shuffle_depth', baseValue: 3, unit: 'levels', sensitivity: 'medium' },
    { parameter: 'entropy_bits', baseValue: 128, unit: 'bits', sensitivity: 'low' },
  ],
  'entropy-burst': [
    { parameter: 'entropy_rate', baseValue: 1024, unit: 'bits/s', sensitivity: 'high' },
    { parameter: 'randomness_quality', baseValue: 0.95, unit: 'score', sensitivity: 'medium' },
    { parameter: 'pool_size', baseValue: 4096, unit: 'bits', sensitivity: 'low' },
  ],
  'fault-injection': [
    { parameter: 'failure_rate_pct', baseValue: 1, unit: '%', sensitivity: 'high' },
    { parameter: 'recovery_time_ms', baseValue: 5000, unit: 'ms', sensitivity: 'medium' },
    { parameter: 'cascade_probability', baseValue: 0.1, unit: 'ratio', sensitivity: 'high' },
  ],
  'circuit-break': [
    { parameter: 'failure_threshold', baseValue: 5, unit: 'failures', sensitivity: 'high' },
    { parameter: 'reset_timeout_ms', baseValue: 30000, unit: 'ms', sensitivity: 'medium' },
    { parameter: 'half_open_requests', baseValue: 3, unit: 'requests', sensitivity: 'low' },
  ],
};

// ─────────────────────────────────────────────────────────────────────────────
// SugarCubeBot Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class SugarCubeBot extends Bot {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private readonly perturbationHistory: Map<string, Array<{
    perturbation: string;
    amount: number;
    timestamp: number;
  }>>;

  constructor() {
    const handler = async (input: SugarCubeInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-CHAOSPARTY-SUGARCUBE',
      'SugarCube',
      handler,
      'Subtle perturbation injection with controlled dissolution and accumulation tracking'
    );

    this.log = new Logger('SugarCubeBot');
    this.audit = auditLedger;
    this.perturbationHistory = new Map();
  }

  private async process(input: SugarCubeInput): Promise<SweetenResult> {
    switch (input.operation) {
      case 'SWEETEN':
        return this.sweeten(input);
      default:
        throw new Error(`SugarCubeBot: Unknown operation "${(input as any).operation}"`);
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // SWEETEN
  // ─────────────────────────────────────────────────────────────────────────

  private sweeten(input: SugarCubeInput): SweetenResult {
    const { target, perturbation, amount, dissolveTime, mode, frequency, variance } = input;
    const perturbMode = mode ?? 'additive';
    const freq = frequency ?? 'once';

    // Find perturbation targets
    const targets = PERTURBATION_TARGETS[perturbation] ?? PERTURBATION_TARGETS['latency'];

    // Apply perturbation effects
    const effects: PerturbationEffect[] = targets.map((t) => {
      const varianceAmount = variance ? (Math.random() - 0.5) * 2 * variance : 0;
      const effectiveAmount = amount + varianceAmount;
      let perturbedValue: number;
      let direction: PerturbationEffect['direction'];

      switch (perturbMode) {
        case 'additive':
          perturbedValue = t.baseValue + effectiveAmount;
          direction = effectiveAmount >= 0 ? 'increase' : 'decrease';
          break;
        case 'multiplicative':
          perturbedValue = t.baseValue * (1 + effectiveAmount / 100);
          direction = effectiveAmount >= 0 ? 'increase' : 'decrease';
          break;
        case 'replace':
          perturbedValue = effectiveAmount;
          direction = effectiveAmount > t.baseValue ? 'increase' : 'decrease';
          break;
        case 'noise':
          const noise = (Math.random() - 0.5) * 2 * effectiveAmount;
          perturbedValue = t.baseValue + noise;
          direction = noise >= 0 ? 'increase' : 'decrease';
          break;
        default:
          perturbedValue = t.baseValue + effectiveAmount;
          direction = effectiveAmount >= 0 ? 'increase' : 'decrease';
      }

      // Ensure non-negative for most parameters
      perturbedValue = Math.max(0, perturbedValue);

      return {
        parameter: t.parameter,
        originalValue: t.baseValue,
        perturbedValue: Math.round(perturbedValue * 100) / 100,
        delta: Math.round((perturbedValue - t.baseValue) * 100) / 100,
        direction,
        mode: perturbMode,
      };
    });

    // Calculate total delta
    const totalDelta = effects.reduce((sum, e) => sum + Math.abs(e.delta), 0);

    // Calculate chaos contribution
    const chaosContribution = this.calculateChaosContribution(effects, targets, perturbMode);

    // Calculate sweetness (inverse of perturbation magnitude — subtle = sweet)
    const maxDelta = Math.max(...effects.map((e) => Math.abs(e.delta)));
    const sweetness = Math.max(0, 100 - maxDelta);

    // Dissolution schedule
    const dissolutionRate = dissolveTime / 1000; // seconds
    const completeAt = Date.now() + dissolveTime;

    // Accumulation tracking
    const history = this.perturbationHistory.get(target) ?? [];
    const cumulativeEffect = history.reduce((sum, h) => sum + h.amount, 0) + amount;
    const riskOfSaturation = cumulativeEffect > 200;

    history.push({ perturbation, amount, timestamp: Date.now() });
    this.perturbationHistory.set(target, history);

    const result: SweetenResult = {
      success: true,
      target,
      perturbation,
      amount,
      dissolveTime,
      mode: perturbMode,
      frequency: freq,
      effects,
      totalDelta: Math.round(totalDelta * 100) / 100,
      chaosContribution,
      sweetness,
      dissolution: {
        rate: Math.round(dissolutionRate * 100) / 100,
        unit: 'seconds',
        completeAt,
      },
      accumulation: {
        previousPerturbations: history.length - 1,
        cumulativeEffect: Math.round(cumulativeEffect * 100) / 100,
        riskOfSaturation,
      },
      timestamp: Date.now(),
    };

    this.audit.append({
      actor: 'NID-CHAOSPARTY-SUGARCUBE',
      action: 'PERTURBATION_APPLIED',
      entity: target,
      status: 'SUCCESS',
      meta: {
        perturbation,
        amount,
        mode: perturbMode,
        chaosContribution,
        sweetness,
        riskOfSaturation,
      },
    });

    this.log.info('Perturbation sweetened', {
      target,
      perturbation,
      amount,
      mode: perturbMode,
      chaosContribution,
      sweetness,
    });

    return result;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Chaos Contribution Calculation
  // ─────────────────────────────────────────────────────────────────────────

  private calculateChaosContribution(
    effects: PerturbationEffect[],
    targets: Array<{ sensitivity: string }>,
    mode: NonNullable<SugarCubeInput['mode']>
  ): number {
    let contribution = 0;

    for (let i = 0; i < effects.length; i++) {
      const effect = effects[i];
      const sensitivity = targets[i]?.sensitivity ?? 'medium';

      const sensitivityMultiplier: Record<string, number> = {
        low: 0.5,
        medium: 1.0,
        high: 1.5,
      };

      const baseContribution = Math.abs(effect.delta) * (sensitivityMultiplier[sensitivity] ?? 1.0);
      contribution += baseContribution;
    }

    // Mode multiplier
    const modeMultiplier: Record<string, number> = {
      additive: 1.0,
      multiplicative: 1.3,
      replace: 1.5,
      noise: 1.2,
    };

    contribution *= modeMultiplier[mode] ?? 1.0;

    return Math.floor(contribution);
  }
}
