/**
 * PocketWatchBot — Time Bomb Management Bot for The Chaos Party
 *
 * Identity:  NID-CHAOSPARTY-POCKETWATCH
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TheChaosPartyAI (AID-CHAOSPARTY)
 *
 * Responsibilities:
 *   - Arm time bombs with configurable delays and triggers
 *   - Manage delayed, recurring, conditional, and random bomb types
 *   - Track armed, detonated, and defused bomb states
 *   - Calculate blast radius and chaos contribution
 *   - Support bomb defusal and chain management
 *
 * "No room! No room! — But there's plenty of room for timed chaos."
 */

import { Bot, Logger, AuditLedger } from '../../../core/definitions';

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface PocketWatchInput {
  operation: 'ARM';
  delay: number;
  payload: Record<string, unknown>;
  type?: 'delayed' | 'recurring' | 'conditional' | 'random';
  recurring?: boolean;
  recurrenceInterval?: number;
  condition?: string;
  jitterRange?: number;
  blastRadius?: number;
  target?: string;
}

export interface BombState {
  bombId: string;
  type: NonNullable<PocketWatchInput['type']>;
  status: 'armed' | 'detonated' | 'defused' | 'misfired' | 'dud';
  armedAt: number;
  triggerAt: number;
  payload: Record<string, unknown>;
  blastRadius: number;
  chaosContribution: number;
  target: string;
  recurrence?: {
    interval: number;
    count: number;
    maxCount?: number;
  };
  condition?: string;
  jitter?: number;
}

export interface ArmResult {
  success: boolean;
  bombId: string;
  type: NonNullable<PocketWatchInput['type']>;
  status: BombState['status'];
  armedAt: number;
  triggerAt: number;
  delay: number;
  blastRadius: number;
  estimatedChaosContribution: number;
  payload: Record<string, unknown>;
  target: string;
  recurring: boolean;
  recurrenceInterval?: number;
  condition?: string;
  jitter?: number;
  defusalCode: string;
  warning: string;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// PocketWatchBot Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class PocketWatchBot extends Bot {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private readonly bombs: Map<string, BombState>;
  private bombCounter: number;

  constructor() {
    const handler = async (input: PocketWatchInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-CHAOSPARTY-POCKETWATCH',
      'PocketWatch',
      handler,
      'Time bomb management with delayed, recurring, conditional, and random trigger types'
    );

    this.log = new Logger('PocketWatchBot');
    this.audit = AuditLedger.getInstance();
    this.bombs = new Map();
    this.bombCounter = 0;
  }

  private async process(input: PocketWatchInput): Promise<ArmResult> {
    switch (input.operation) {
      case 'ARM':
        return this.arm(input);
      default:
        throw new Error(`PocketWatchBot: Unknown operation "${(input as any).operation}"`);
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // ARM
  // ─────────────────────────────────────────────────────────────────────────

  private arm(input: PocketWatchInput): ArmResult {
    const {
      delay,
      payload,
      type,
      recurring,
      recurrenceInterval,
      condition,
      jitterRange,
      blastRadius,
      target,
    } = input;

    this.bombCounter++;
    const bombId = `BOMB-${this.bombCounter}`;
    const bombType = type ?? (recurring ? 'recurring' : 'delayed');
    const now = Date.now();

    // Calculate trigger time
    let triggerAt: number;
    let jitter: number | undefined;

    if (bombType === 'random') {
      // Random trigger within a range
      const range = jitterRange ?? delay;
      jitter = Math.floor(Math.random() * range);
      triggerAt = now + jitter;
    } else if (bombType === 'delayed' || bombType === 'conditional') {
      triggerAt = now + delay;
      if (jitterRange) {
        jitter = Math.floor(Math.random() * jitterRange * 2) - jitterRange;
        triggerAt += jitter;
      }
    } else {
      // Recurring
      triggerAt = now + delay;
    }

    // Estimate chaos contribution
    const radius = blastRadius ?? this.estimateBlastRadius(payload);
    const estimatedChaosContribution = this.estimateChaosContribution(bombType, delay, radius);

    // Build recurrence config
    const recurrence = (bombType === 'recurring' || recurring)
      ? {
          interval: recurrenceInterval ?? delay,
          count: 0,
          maxCount: Math.floor(Math.random() * 10) + 1,
        }
      : undefined;

    // Store bomb state
    const bombState: BombState = {
      bombId,
      type: bombType,
      status: 'armed',
      armedAt: now,
      triggerAt,
      payload,
      blastRadius: radius,
      chaosContribution: estimatedChaosContribution,
      target: target ?? 'system-default',
      recurrence,
      condition: bombType === 'conditional' ? (condition ?? 'true') : undefined,
      jitter,
    };

    this.bombs.set(bombId, bombState);

    // Generate defusal code
    const defusalCode = this.generateDefusalCode(bombId);

    // Build warning message
    const warning = this.buildWarning(bombType, delay, radius, target ?? 'system-default');

    const result: ArmResult = {
      success: true,
      bombId,
      type: bombType,
      status: 'armed',
      armedAt: now,
      triggerAt,
      delay,
      blastRadius: radius,
      estimatedChaosContribution,
      payload,
      target: target ?? 'system-default',
      recurring: recurring ?? bombType === 'recurring',
      recurrenceInterval: recurrence?.interval,
      condition: bombType === 'conditional' ? (condition ?? 'true') : undefined,
      jitter,
      defusalCode,
      warning,
      timestamp: now,
    };

    this.audit.append({
      actor: 'NID-CHAOSPARTY-POCKETWATCH',
      action: 'BOMB_ARMED',
      entity: bombId,
      status: 'SUCCESS',
      meta: {
        type: bombType,
        delay,
        target: target ?? 'system-default',
        blastRadius: radius,
        estimatedChaosContribution,
        recurring: recurring ?? false,
      },
    });

    this.log.info('Time bomb armed', {
      bombId,
      type: bombType,
      delay,
      triggerAt: new Date(triggerAt).toISOString(),
      blastRadius: radius,
    });

    return result;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Blast Radius Estimation
  // ─────────────────────────────────────────────────────────────────────────

  private estimateBlastRadius(payload: Record<string, unknown>): number {
    // Estimate based on payload size and keys
    const keyCount = Object.keys(payload).length;
    const payloadSize = JSON.stringify(payload).length;

    let radius = 1; // minimum: single target
    radius += Math.floor(keyCount / 2); // each key potentially affects another component
    radius += Math.floor(payloadSize / 200); // larger payloads = wider blast

    return Math.min(radius, 10); // cap at 10
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Chaos Contribution Estimation
  // ─────────────────────────────────────────────────────────────────────────

  private estimateChaosContribution(
    type: NonNullable<PocketWatchInput['type']>,
    delay: number,
    blastRadius: number
  ): number {
    // Base contribution by type
    const typeContribution: Record<string, number> = {
      delayed: 10,
      recurring: 20,
      conditional: 15,
      random: 25,
    };

    // Delay factor — longer delays are less predictable (more chaos)
    const delayFactor = Math.min(delay / 10000, 3); // cap at 3x

    // Blast radius factor
    const radiusFactor = Math.min(blastRadius / 3, 2); // cap at 2x

    return Math.floor(
      (typeContribution[type] ?? 10) * (1 + delayFactor) * (1 + radiusFactor)
    );
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Defusal Code Generation
  // ─────────────────────────────────────────────────────────────────────────

  private generateDefusalCode(bombId: string): string {
    const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    let code = '';
    for (let i = 0; i < 8; i++) {
      code += chars[Math.floor(Math.random() * chars.length)];
    }
    return code;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Warning Builder
  // ─────────────────────────────────────────────────────────────────────────

  private buildWarning(
    type: NonNullable<PocketWatchInput['type']>,
    delay: number,
    blastRadius: number,
    target: string
  ): string {
    const warnings: Record<string, string> = {
      delayed: `Time bomb armed — will detonate in ${delay}ms targeting "${target}" (radius: ${blastRadius}). Use defusal code to cancel.`,
      recurring: `Recurring time bomb armed — will detonate every ${delay}ms targeting "${target}" (radius: ${blastRadius}). Set maxCount to limit recursions.`,
      conditional: `Conditional time bomb armed — will detonate when condition is met targeting "${target}" (radius: ${blastRadius}). Monitor closely.`,
      random: `Random time bomb armed — will detonate at an unpredictable time within ${delay}ms targeting "${target}" (radius: ${blastRadius}). Stay vigilant.`,
    };

    return warnings[type] ?? warnings.delayed;
  }
}
