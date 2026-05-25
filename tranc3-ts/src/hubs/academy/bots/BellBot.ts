/**
 * BellBot — Academic Signalling Bot for The Academy
 *
 * Identity:  NID-ACADEMY-BELL
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TheAcademyAI (AID-ACADEMY)
 *
 * Responsibilities:
 *   - RING: Emit academic time signals and event notifications
 *   - Support class_start, class_end, exam_start, exam_end,
 *     announcement, emergency, and graduation bell types
 *   - Track bell schedule, history, and institutional rhythm
 *   - Manage bell priority: emergency > exam > class > announcement > graduation
 *   - Coordinate bell cadence and avoid signal collision
 *
 * "The bell does not merely mark time — it shapes it. Each ring
 *  is a heartbeat of the Academy, synchronising the rhythm of learning."
 */

import { Bot, Logger, AuditLedger } from '../../../core/definitions'

const auditLedger = new AuditLedger();

// ────────────────────────────────────────────────────────────────────────────
// Input / Output Types
// ────────────────────────────────────────────────────────────────────────────

export interface BellInput {
  operation: 'RING';
  bellType: 'class_start' | 'class_end' | 'exam_start' | 'exam_end' | 'announcement' | 'emergency' | 'graduation';
  target?: string;
  courseId?: string;
  roomId?: string;
  message?: string;
  duration?: number;          // Signal duration in seconds
  priority?: 'low' | 'normal' | 'high' | 'critical';
  scheduledAt?: number;       // If this is a scheduled future ring
  suppressDuplicates?: boolean;
  repeatInterval?: number;    // Repeat every N seconds (0 = no repeat)
  maxRepeats?: number;        // Maximum number of repeats
}

export interface BellSignal {
  id: string;
  bellType: BellInput['bellType'];
  target: string;
  courseId: string;
  roomId: string;
  message: string;
  duration: number;
  priority: BellInput['priority'];
  status: 'ringing' | 'acknowledged' | 'silenced' | 'expired' | 'cancelled';
  cadence: number;
  repeatCount: number;
  maxRepeats: number;
  scheduledAt: number;
  rangAt: number;
  acknowledgedAt?: number;
  acknowledgedBy?: string;
  silencedAt?: number;
  expiredAt?: number;
  deliveryTargets: string[];
  deliveryStatus: Record<string, 'pending' | 'delivered' | 'failed'>;
}

export interface BellSchedule {
  id: string;
  dayOfWeek: number;          // 0=Sun, 1=Mon, ..., 6=Sat
  bellType: BellInput['bellType'];
  timeSlot: string;           // HH:MM format
  target: string;
  courseId: string;
  roomId: string;
  isActive: boolean;
  effectiveFrom: number;
  effectiveUntil?: number;
}

export interface BellHistory {
  signal: BellSignal;
  correlationId?: string;
  relatedSignals: string[];
}

export interface BellStats {
  totalRings: number;
  byBellType: Record<NonNullable<BellInput['bellType']>, number>;
  byPriority: Record<NonNullable<BellInput['priority']>, number>;
  byStatus: Record<NonNullable<BellSignal['status']>, number>;
  emergencyRings: number;
  averageResponseTime: number;
  scheduleCompliance: number;
  collisionCount: number;
  peakHour: number;
  timestamp: number;
}

export interface RingResult {
  success: boolean;
  signal: BellSignal;
  correlatedSignals: BellSignal[];
  stats: BellStats;
  schedule?: BellSchedule;
  message: string;
  timestamp: number;
}

// ────────────────────────────────────────────────────────────────────────────
// Bell Configuration
// ────────────────────────────────────────────────────────────────────────────

const BELL_DEFAULTS: Record<BellInput['bellType'], {
  duration: number;
  priority: BellInput['priority'];
  cadence: number;
  defaultMessage: string;
  targetPrefix: string;
}> = {
  class_start: {
    duration: 5,
    priority: 'normal',
    cadence: 2,
    defaultMessage: 'Classes are now in session. Please proceed to your designated rooms.',
    targetPrefix: 'campus-wide',
  },
  class_end: {
    duration: 5,
    priority: 'normal',
    cadence: 2,
    defaultMessage: 'Class session has ended. Please clear the rooms promptly.',
    targetPrefix: 'campus-wide',
  },
  exam_start: {
    duration: 10,
    priority: 'high',
    cadence: 3,
    defaultMessage: 'Examination has commenced. Silence is required. Good luck to all candidates.',
    targetPrefix: 'examination-halls',
  },
  exam_end: {
    duration: 8,
    priority: 'high',
    cadence: 3,
    defaultMessage: 'Examination has concluded. Please cease writing and submit your papers.',
    targetPrefix: 'examination-halls',
  },
  announcement: {
    duration: 3,
    priority: 'low',
    cadence: 1,
    defaultMessage: 'Attention: An announcement is forthcoming.',
    targetPrefix: 'campus-wide',
  },
  emergency: {
    duration: 30,
    priority: 'critical',
    cadence: 5,
    defaultMessage: 'EMERGENCY ALERT: Follow evacuation procedures immediately. Emergency services have been notified.',
    targetPrefix: 'campus-wide',
  },
  graduation: {
    duration: 15,
    priority: 'normal',
    cadence: 4,
    defaultMessage: 'Graduation ceremony is commencing. Congratulations to all graduates!',
    targetPrefix: 'ceremony-hall',
  },
};

const PRIORITY_ORDER: Record<NonNullable<BellInput['priority']>, number> = {
  critical: 4,
  high: 3,
  normal: 2,
  low: 1,
};

// ────────────────────────────────────────────────────────────────────────────
// Bell Storage
// ────────────────────────────────────────────────────────────────────────────

let signalCounter = 0;
const signalStore: Map<string, BellSignal> = new Map();
const scheduleStore: Map<string, BellSchedule> = new Map();

// ────────────────────────────────────────────────────────────────────────────
// BellBot Implementation
// ────────────────────────────────────────────────────────────────────────────

export class BellBot extends Bot {
  private readonly log: Logger;
  private readonly audit: AuditLedger;

  constructor() {
    super(
      'NID-ACADEMY-BELL',
      'Bell',
      async (input: BellInput) => this.handleRing(input),
      'Emits academic time signals for class, exam, announcement, emergency, and graduation events'
    );

    this.log = new Logger('BellBot');
    this.audit = auditLedger;
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Main Handler
  // ──────────────────────────────────────────────────────────────────────────

  private async handleRing(input: BellInput): Promise<RingResult> {
    if (input.operation !== 'RING') {
      return this.fail(input, `Invalid operation: ${input.operation}. BellBot only accepts RING.`);
    }

    return this.ring(input);
  }

  // ──────────────────────────────────────────────────────────────────────────
  // RING — Emit a bell signal
  // ──────────────────────────────────────────────────────────────────────────

  private ring(input: BellInput): RingResult {
    const {
      bellType,
      target,
      courseId,
      roomId,
      message,
      duration,
      priority,
      scheduledAt,
      suppressDuplicates,
      repeatInterval,
      maxRepeats,
    } = input;

    const defaults = BELL_DEFAULTS[bellType];
    const resolvedTarget = target ?? defaults.targetPrefix;
    const resolvedMessage = message ?? defaults.defaultMessage;
    const resolvedDuration = duration ?? defaults.duration;
    const resolvedPriority = priority ?? defaults.priority;
    const resolvedCadence = defaults.cadence;
    const resolvedMaxRepeats = maxRepeats ?? 1;
    const resolvedRepeatInterval = repeatInterval ?? 0;
    const resolvedScheduledAt = scheduledAt ?? Date.now();

    // Check for duplicate suppression
    if (suppressDuplicates !== false) {
      const duplicate = this.findRecentDuplicate(bellType, resolvedTarget, 60000); // 1-minute window
      if (duplicate) {
        this.log.info('Duplicate bell suppressed', {
          bellType,
          target: resolvedTarget,
          duplicateOf: duplicate.id,
        });

        return {
          success: true,
          signal: duplicate,
          correlatedSignals: this.findCorrelatedSignals(duplicate),
          stats: this.buildStats(),
          message: `Bell suppressed as duplicate of ${duplicate.id} (${bellType} → ${resolvedTarget} within 60s)`,
          timestamp: Date.now(),
        };
      }
    }

    // Check for priority collision — a higher-priority bell currently ringing
    const activeSignals = Array.from(signalStore.values())
      .filter(s => s.status === 'ringing');
    const collision = activeSignals.find(s =>
      PRIORITY_ORDER[s.priority!] > PRIORITY_ORDER[resolvedPriority!]
    );

    if (collision) {
      this.log.warn('Bell collision detected — lower priority signal queued behind active signal', {
        requestedType: bellType,
        requestedPriority: resolvedPriority,
        activeType: collision.bellType,
        activePriority: collision.priority,
        activeId: collision.id,
      });
    }

    // Determine delivery targets
    const deliveryTargets = this.resolveDeliveryTargets(bellType, resolvedTarget, roomId);
    const deliveryStatus: Record<string, 'pending' | 'delivered' | 'failed'> = {};
    for (const dt of deliveryTargets) {
      deliveryStatus[dt] = 'delivered'; // Simulated delivery
    }

    // Create the signal
    signalCounter++;
    const signal: BellSignal = {
      id: `BELL-${signalCounter.toString().padStart(6, '0')}`,
      bellType,
      target: resolvedTarget,
      courseId: courseId ?? '',
      roomId: roomId ?? '',
      message: resolvedMessage,
      duration: resolvedDuration,
      priority: resolvedPriority,
      status: 'ringing',
      cadence: resolvedCadence,
      repeatCount: 0,
      maxRepeats: resolvedMaxRepeats,
      scheduledAt: resolvedScheduledAt,
      rangAt: Date.now(),
      deliveryTargets,
      deliveryStatus,
    };

    signalStore.set(signal.id, signal);

    // Handle repeat scheduling
    if (resolvedRepeatInterval > 0 && resolvedMaxRepeats > 1) {
      signal.repeatCount = 1;
      this.log.info('Bell scheduled for repeat', {
        signalId: signal.id,
        interval: resolvedRepeatInterval,
        maxRepeats: resolvedMaxRepeats,
      });
    }

    // Auto-acknowledge non-emergency signals after a simulated delay
    if (resolvedPriority !== 'critical' && resolvedPriority !== 'high') {
      signal.status = 'acknowledged';
      signal.acknowledgedAt = Date.now();
      signal.acknowledgedBy = 'BellBot-auto';
    }

    // Find correlated signals (same course, same time window)
    const correlatedSignals = this.findCorrelatedSignals(signal);

    // Check if this matches a schedule
    const matchingSchedule = this.findMatchingSchedule(bellType, resolvedTarget);

    const stats = this.buildStats();

    // Audit logging — emergency gets special audit treatment
    this.audit.append({
      actor: 'NID-ACADEMY-BELL',
      action: 'RING',
      entity: signal.id,
      status: 'SUCCESS',
      meta: {
        bellType,
        priority: resolvedPriority,
        target: resolvedTarget,
        courseId: courseId ?? '',
        roomId: roomId ?? '',
        duration: resolvedDuration,
        collisionDetected: !!collision,
      },
    });

    if (bellType === 'emergency') {
      this.log.error('EMERGENCY BELL RINGING', {
        signalId: signal.id,
        message: resolvedMessage,
        target: resolvedTarget,
      });
    } else {
      this.log.info('Bell rung', {
        signalId: signal.id,
        bellType,
        priority: resolvedPriority,
        target: resolvedTarget,
      });
    }

    return {
      success: true,
      signal,
      correlatedSignals,
      stats,
      schedule: matchingSchedule ?? undefined,
      message: `${bellType.replace('_', ' ').toUpperCase()} bell ${signal.id} rang → ${resolvedTarget} | ${resolvedPriority} priority | ${resolvedDuration}s duration | ${deliveryTargets.length} targets | ${correlatedSignals.length} correlated`,
      timestamp: Date.now(),
    };
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Duplicate Detection
  // ──────────────────────────────────────────────────────────────────────────

  private findRecentDuplicate(
    bellType: BellInput['bellType'],
    target: string,
    windowMs: number
  ): BellSignal | null {
    const cutoff = Date.now() - windowMs;

    for (const signal of signalStore.values()) {
      if (
        signal.bellType === bellType &&
        signal.target === target &&
        signal.rangAt >= cutoff &&
        signal.status === 'ringing'
      ) {
        return signal;
      }
    }

    return null;
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Correlated Signal Detection
  // ──────────────────────────────────────────────────────────────────────────

  private findCorrelatedSignals(signal: BellSignal): BellSignal[] {
    const correlated: BellSignal[] = [];
    const lookbackWindow = 300000; // 5 minutes

    for (const existing of signalStore.values()) {
      if (existing.id === signal.id) continue;
      if (existing.rangAt < Date.now() - lookbackWindow) continue;

      // Same course
      const sameCourse = signal.courseId && existing.courseId === signal.courseId;
      // Same room
      const sameRoom = signal.roomId && existing.roomId === signal.roomId;
      // Complementary bell types (start/end pairs)
      const complementaryPairs: [string, string][] = [
        ['class_start', 'class_end'],
        ['exam_start', 'exam_end'],
      ];
      const isComplementary = complementaryPairs.some(
        ([a, b]) => (signal.bellType === a && existing.bellType === b) ||
                     (signal.bellType === b && existing.bellType === a)
      );

      if (sameCourse || sameRoom || isComplementary) {
        correlated.push(existing);
      }
    }

    return correlated;
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Delivery Target Resolution
  // ──────────────────────────────────────────────────────────────────────────

  private resolveDeliveryTargets(
    bellType: BellInput['bellType'],
    target: string,
    roomId?: string
  ): string[] {
    const targets: string[] = [];

    // Always include the primary target
    targets.push(target);

    // Room-specific targeting
    if (roomId) {
      targets.push(`room:${roomId}`);
    }

    // Bell-type-specific additional targets
    switch (bellType) {
      case 'emergency':
        targets.push('security', 'administration', 'medical', 'all-staff');
        break;
      case 'exam_start':
      case 'exam_end':
        targets.push('invigilators', 'examination-office');
        break;
      case 'graduation':
        targets.push('chancellor', 'dean', 'registry', 'guest-services');
        break;
      case 'class_start':
      case 'class_end':
        targets.push('faculty-office');
        break;
      case 'announcement':
        targets.push('notice-board', 'digital-signage');
        break;
    }

    return [...new Set(targets)]; // Deduplicate
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Schedule Matching
  // ──────────────────────────────────────────────────────────────────────────

  private findMatchingSchedule(
    bellType: BellInput['bellType'],
    target: string
  ): BellSchedule | null {
    const now = new Date();
    const currentDay = now.getDay();
    const currentTime = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`;

    for (const schedule of scheduleStore.values()) {
      if (
        schedule.bellType === bellType &&
        schedule.target === target &&
        schedule.dayOfWeek === currentDay &&
        schedule.timeSlot === currentTime &&
        schedule.isActive
      ) {
        return schedule;
      }
    }

    return null;
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Statistics
  // ──────────────────────────────────────────────────────────────────────────

  private buildStats(): BellStats {
    const all = Array.from(signalStore.values());

    const byBellType: Record<NonNullable<BellInput['bellType']>, number> = {
      class_start: 0, class_end: 0, exam_start: 0, exam_end: 0,
      announcement: 0, emergency: 0, graduation: 0,
    };
    const byPriority: Record<NonNullable<BellInput['priority']>, number> = {
      low: 0, normal: 0, high: 0, critical: 0,
    };
    const byStatus: Record<NonNullable<BellSignal['status']>, number> = {
      ringing: 0, acknowledged: 0, silenced: 0, expired: 0, cancelled: 0,
    };

    for (const signal of all) {
      byBellType[signal.bellType!]++;
      byPriority[signal.priority!]++;
      byStatus[signal.status!]++;
    }

    const emergencyRings = all.filter(s => s.bellType === 'emergency').length;

    // Average response time (acknowledged signals)
    const acknowledged = all.filter(s => s.acknowledgedAt && s.rangAt);
    const averageResponseTime = acknowledged.length > 0
      ? Math.round(acknowledged.reduce((sum, s) => sum + (s.acknowledgedAt! - s.rangAt), 0) / acknowledged.length)
      : 0;

    // Schedule compliance (simplified — ratio of scheduled to total)
    const scheduled = all.filter(s => s.scheduledAt !== s.rangAt).length;
    const scheduleCompliance = all.length > 0
      ? Math.round((scheduled / all.length) * 10000) / 100
      : 100;

    // Collision count (signals that rang while another was active)
    const collisionCount = this.calculateCollisions(all);

    // Peak hour
    const hourCounts: Record<number, number> = {};
    for (const signal of all) {
      const hour = new Date(signal.rangAt).getHours();
      hourCounts[hour] = (hourCounts[hour] ?? 0) + 1;
    }
    const peakHour = Object.entries(hourCounts)
      .sort((a, b) => b[1] - a[1])[0]
      ? parseInt(Object.entries(hourCounts).sort((a, b) => b[1] - a[1])[0]![0])
      : 0;

    return {
      totalRings: all.length,
      byBellType,
      byPriority,
      byStatus,
      emergencyRings,
      averageResponseTime,
      scheduleCompliance,
      collisionCount,
      peakHour,
      timestamp: Date.now(),
    };
  }

  private calculateCollisions(signals: BellSignal[]): number {
    let collisions = 0;
    const sorted = [...signals].sort((a, b) => a.rangAt - b.rangAt);

    for (let i = 1; i < sorted.length; i++) {
      const prev = sorted[i - 1]!;
      const curr = sorted[i]!;

      // If current rang before previous expired, that's a collision
      const prevExpiry = prev.rangAt + (prev.duration * 1000);
      if (curr.rangAt < prevExpiry && curr.status === 'ringing' && prev.status === 'ringing') {
        collisions++;
      }
    }

    return collisions;
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Failure Helper
  // ──────────────────────────────────────────────────────────────────────────

  private fail(input: BellInput, message: string): RingResult {
    this.log.error('Ring failed', { message, bellType: input.bellType });

    const emptySignal: BellSignal = {
      id: '',
      bellType: input.bellType ?? 'announcement',
      target: '',
      courseId: '',
      roomId: '',
      message: '',
      duration: 0,
      priority: 'low',
      status: 'cancelled',
      cadence: 0,
      repeatCount: 0,
      maxRepeats: 1,
      scheduledAt: 0,
      rangAt: 0,
      deliveryTargets: [],
      deliveryStatus: {},
    };

    return {
      success: false,
      signal: emptySignal,
      correlatedSignals: [],
      stats: this.buildStats(),
      message,
      timestamp: Date.now(),
    };
  }
}
