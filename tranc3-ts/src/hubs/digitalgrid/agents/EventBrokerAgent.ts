/**
 * EventBrokerAgent — Event Routing Agent for DigitalGrid
 *
 * Identity:  SID-DIGITALGRID-EVENTBROKER
 * Tier:      4 (Autonomous Microservice)
 * Parent:    DigitalGridAI (AID-DIGITALGRID)
 *
 * Responsibilities:
 *   - Route events to matching subscriptions
 *   - Evaluate subscription filters against event payloads
 *   - Dispatch matched events to workflow entry steps
 *   - Track event delivery statistics
 *   - Support wildcard and pattern-based event type matching
 */

import { Agent, Logger } from '../../../core/definitions';

// ─────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────

export interface BrokerEvent {
  id: string;
  type: string;
  source: string;
  timestamp: number;
  payload: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

export interface BrokerSubscription {
  id: string;
  eventType: string;
  workflowId: string;
  entryStepId: string;
  filter?: Record<string, unknown>;
  createdAt: number;
}

export interface BrokerInput {
  event: BrokerEvent;
  subscriptions: BrokerSubscription[];
}

export interface MatchResult {
  subscriptionId: string;
  eventType: string;
  workflowId: string;
  entryStepId: string;
  matched: boolean;
  filterPassed: boolean;
  matchScore: number;
}

export interface BrokerOutput {
  eventId: string;
  eventType: string;
  totalSubscriptions: number;
  matchedSubscriptions: number;
  matches: MatchResult[];
  deliveryLog: Array<{
    subscriptionId: string;
    workflowId: string;
    status: 'dispatched' | 'filtered' | 'error';
    reason?: string;
  }>;
}

// ─────────────────────────────────────────────────────────────
// EventBrokerAgent Implementation
// ─────────────────────────────────────────────────────────────

export class EventBrokerAgent extends Agent {
  private readonly log: Logger;
  private deliveryStats: Map<string, { dispatched: number; filtered: number; errors: number }>;

  constructor() {
    super('SID-DIGITALGRID-EVENTBROKER');
    this.log = new Logger('EventBrokerAgent');
    this.deliveryStats = new Map();
  }

  async perceive(observation: BrokerInput): Promise<{
    event: BrokerEvent;
    subscriptions: BrokerSubscription[];
    candidates: BrokerSubscription[];
  }> {
    const { event, subscriptions } = observation;

    // Pre-filter subscriptions by event type (exact or wildcard)
    const candidates = subscriptions.filter((sub) => this.matchesEventType(sub.eventType, event.type));

    this.log.info('Perceived event for routing', {
      eventId: event.id,
      eventType: event.type,
      totalSubs: subscriptions.length,
      candidates: candidates.length,
    });

    return { event, subscriptions, candidates };
  }

  async decide(perceived: Awaited<ReturnType<typeof this.perceive>>): Promise<{
    event: BrokerEvent;
    matches: MatchResult[];
  }> {
    const { event, candidates } = perceived;

    // Evaluate each candidate's filter against the event
    const matches: MatchResult[] = [];

    for (const sub of candidates) {
      const filterResult = this.evaluateFilter(sub.filter ?? {}, event);
      const matchScore = this.computeMatchScore(sub, event, filterResult);

      matches.push({
        subscriptionId: sub.id,
        eventType: sub.eventType,
        workflowId: sub.workflowId,
        entryStepId: sub.entryStepId,
        matched: filterResult.passed,
        filterPassed: filterResult.passed,
        matchScore,
      });
    }

    this.log.info('Decided on event routing', {
      eventId: event.id,
      candidateCount: candidates.length,
      matchedCount: matches.filter((m) => m.matched).length,
    });

    return { event, matches };
  }

  async act(decision: Awaited<ReturnType<typeof this.decide>>): Promise<BrokerOutput> {
    const { event, matches } = decision;
    const deliveryLog: BrokerOutput['deliveryLog'] = [];

    const matchedSubscriptions: MatchResult[] = [];

    for (const match of matches) {
      if (match.matched) {
        // Dispatch to workflow
        deliveryLog.push({
          subscriptionId: match.subscriptionId,
          workflowId: match.workflowId,
          status: 'dispatched',
        });
        matchedSubscriptions.push(match);

        this.updateStats(match.subscriptionId, 'dispatched');
      } else {
        deliveryLog.push({
          subscriptionId: match.subscriptionId,
          workflowId: match.workflowId,
          status: 'filtered',
          reason: 'Filter conditions not met',
        });

        this.updateStats(match.subscriptionId, 'filtered');
      }
    }

    this.log.info('Event routed', {
      eventId: event.id,
      dispatched: matchedSubscriptions.length,
      filtered: matches.length - matchedSubscriptions.length,
    });

    return {
      eventId: event.id,
      eventType: event.type,
      totalSubscriptions: matches.length,
      matchedSubscriptions: matchedSubscriptions.length,
      matches,
      deliveryLog,
    };
  }

  // ─────────────────────────────────────────────────────────────
  // Event Type Matching
  // ─────────────────────────────────────────────────────────────

  /**
   * Check if a subscription's event type pattern matches the actual event type.
   * Supports:
   *   - Exact match: "order.created" === "order.created"
   *   - Wildcard (*): "order.*" matches "order.created", "order.updated"
   *   - Multi-segment wildcard (**): "order.**" matches "order.created", "order.item.added"
   */
  private matchesEventType(pattern: string, eventType: string): boolean {
    // Exact match
    if (pattern === eventType) return true;

    // Wildcard patterns
    if (pattern.includes('*')) {
      const patternParts = pattern.split('.');
      const eventParts = eventType.split('.');

      return this.matchPatternParts(patternParts, eventParts, 0, 0);
    }

    return false;
  }

  private matchPatternParts(
    patternParts: string[],
    eventParts: string[],
    pi: number,
    ei: number
  ): boolean {
    // Both exhausted — match
    if (pi === patternParts.length && ei === eventParts.length) return true;
    // Pattern exhausted but event remains — no match
    if (pi === patternParts.length) return false;
    // Event exhausted but pattern remains — only match if remaining is **
    if (ei === eventParts.length) {
      return patternParts.slice(pi).every((p) => p === '**');
    }

    const pattern = patternParts[pi];

    if (pattern === '**') {
      // ** matches zero or more segments
      // Try matching remaining pattern against current and all subsequent event positions
      for (let i = ei; i <= eventParts.length; i++) {
        if (this.matchPatternParts(patternParts, eventParts, pi + 1, i)) {
          return true;
        }
      }
      return false;
    }

    if (pattern === '*') {
      // * matches exactly one segment
      return this.matchPatternParts(patternParts, eventParts, pi + 1, ei + 1);
    }

    // Literal match
    if (pattern === eventParts[ei]) {
      return this.matchPatternParts(patternParts, eventParts, pi + 1, ei + 1);
    }

    return false;
  }

  // ─────────────────────────────────────────────────────────────
  // Filter Evaluation
  // ─────────────────────────────────────────────────────────────

  /**
   * Evaluate a subscription filter against an event.
   * Filter format: { "payload.status": "active", "metadata.priority": { "$gt": 5 } }
   * Supports:
   *   - Exact value match: { "payload.status": "active" }
   *   - Comparison operators: $eq, $ne, $gt, $gte, $lt, $lte, $in, $nin, $exists
   *   - Nested paths using dot notation
   *   - Logical: $and, $or (arrays of filter objects)
   */
  private evaluateFilter(
    filter: Record<string, unknown>,
    event: BrokerEvent
  ): { passed: boolean; details: Record<string, boolean> } {
    if (Object.keys(filter).length === 0) {
      return { passed: true, details: {} };
    }

    const details: Record<string, boolean> = {};
    let allPassed = true;

    for (const [key, condition] of Object.entries(filter)) {
      if (key === '$and') {
        const subFilters = condition as Record<string, unknown>[];
        const subResults = subFilters.map((sf) => this.evaluateFilter(sf, event));
        details['$and'] = subResults.every((r) => r.passed);
        if (!details['$and']) allPassed = false;
      } else if (key === '$or') {
        const subFilters = condition as Record<string, unknown>[];
        const subResults = subFilters.map((sf) => this.evaluateFilter(sf, event));
        details['$or'] = subResults.some((r) => r.passed);
        if (!details['$or']) allPassed = false;
      } else {
        const value = this.resolvePath(key, event);
        const result = this.evaluateCondition(value, condition);
        details[key] = result;
        if (!result) allPassed = false;
      }
    }

    return { passed: allPassed, details };
  }

  /**
   * Resolve a dot-notation path against an event object.
   * e.g. "payload.status" → event.payload.status
   */
  private resolvePath(path: string, event: BrokerEvent): unknown {
    const parts = path.split('.');
    let current: unknown = event;

    for (const part of parts) {
      if (current === null || current === undefined) return undefined;
      if (typeof current === 'object') {
        current = (current as Record<string, unknown>)[part];
      } else {
        return undefined;
      }
    }

    return current;
  }

  /**
   * Evaluate a single condition against a resolved value.
   */
  private evaluateCondition(actual: unknown, condition: unknown): boolean {
    if (condition === null || condition === undefined) {
      return actual === condition;
    }

    // If condition is an object with operators
    if (typeof condition === 'object' && !Array.isArray(condition)) {
      const condObj = condition as Record<string, unknown>;

      for (const [op, operand] of Object.entries(condObj)) {
        switch (op) {
          case '$eq':
            if (actual !== operand) return false;
            break;
          case '$ne':
            if (actual === operand) return false;
            break;
          case '$gt':
            if (typeof actual !== 'number' || actual <= (operand as number)) return false;
            break;
          case '$gte':
            if (typeof actual !== 'number' || actual < (operand as number)) return false;
            break;
          case '$lt':
            if (typeof actual !== 'number' || actual >= (operand as number)) return false;
            break;
          case '$lte':
            if (typeof actual !== 'number' || actual > (operand as number)) return false;
            break;
          case '$in':
            if (!Array.isArray(operand) || !operand.includes(actual)) return false;
            break;
          case '$nin':
            if (!Array.isArray(operand) || operand.includes(actual)) return false;
            break;
          case '$exists':
            if (operand ? actual === undefined : actual !== undefined) return false;
            break;
          default:
            // Unknown operator — treat as literal comparison
            if (actual !== condition) return false;
        }
      }
      return true;
    }

    // Primitive equality
    return actual === condition;
  }

  // ─────────────────────────────────────────────────────────────
  // Match Scoring
  // ─────────────────────────────────────────────────────────────

  /**
   * Compute a match quality score (0-1) for a subscription-event pair.
   * Higher scores indicate stronger matches (more specific).
   */
  private computeMatchScore(
    subscription: BrokerSubscription,
    event: BrokerEvent,
    filterResult: { passed: boolean; details: Record<string, boolean> }
  ): number {
    let score = 0;

    // Base score for event type match
    const patternParts = subscription.eventType.split('.');
    const eventParts = event.type.split('.');

    // Exact match = 1.0, wildcard = 0.7 per segment, ** = 0.4
    let typeScore = 0;
    const maxParts = Math.max(patternParts.length, eventParts.length);
    for (let i = 0; i < patternParts.length; i++) {
      if (patternParts[i] === '**') {
        typeScore += 0.4 / maxParts;
      } else if (patternParts[i] === '*') {
        typeScore += 0.7 / maxParts;
      } else {
        typeScore += 1.0 / maxParts;
      }
    }
    score += typeScore * 0.5; // 50% weight on type match

    // Filter specificity — more filter keys = more specific = higher score
    const filterKeys = Object.keys(subscription.filter ?? {});
    if (filterKeys.length > 0) {
      const specificityScore = Math.min(filterKeys.length / 5, 1.0); // cap at 5 keys
      score += specificityScore * 0.3; // 30% weight on filter specificity
    } else {
      score += 0.1; // No filter = low specificity bonus
    }

    // Filter pass rate
    if (filterResult.passed) {
      const passedKeys = Object.values(filterResult.details).filter(Boolean).length;
      const totalKeys = Object.keys(filterResult.details).length;
      score += (totalKeys > 0 ? passedKeys / totalKeys : 1) * 0.2; // 20% weight on filter pass rate
    }

    return Math.min(score, 1.0);
  }

  // ─────────────────────────────────────────────────────────────
  // Statistics
  // ─────────────────────────────────────────────────────────────

  private updateStats(subscriptionId: string, type: 'dispatched' | 'filtered' | 'errors'): void {
    if (!this.deliveryStats.has(subscriptionId)) {
      this.deliveryStats.set(subscriptionId, { dispatched: 0, filtered: 0, errors: 0 });
    }
    const stats = this.deliveryStats.get(subscriptionId)!;
    stats[type]++;
  }

  /**
   * Get delivery statistics for a subscription.
   */
  getStats(subscriptionId: string): { dispatched: number; filtered: number; errors: number } | undefined {
    return this.deliveryStats.get(subscriptionId);
  }
}
