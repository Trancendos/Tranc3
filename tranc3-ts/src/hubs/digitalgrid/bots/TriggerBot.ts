/**
 * TriggerBot — Trigger Evaluation Bot for DigitalGrid
 *
 * Identity:  NID-DIGITALGRID-TRIGGER
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    DigitalGridAI (AID-DIGITALGRID)
 *
 * Responsibilities:
 *   - Evaluate trigger conditions against incoming events
 *   - Support trigger types: event, schedule, webhook, threshold, compound
 *   - Compute trigger activation status and confidence
 *   - Provide trigger match metadata for workflow routing
 */

import { Bot, Logger } from '../../../core/definitions';

// ─────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────

export interface TriggerEvaluateInput {
  operation: 'EVALUATE';
  triggerType: 'event' | 'schedule' | 'webhook' | 'threshold' | 'compound';
  config: Record<string, unknown>;
  event: {
    id: string;
    type: string;
    source: string;
    timestamp: number;
    payload: Record<string, unknown>;
    metadata: Record<string, unknown>;
  } | null;
}

export type TriggerInput = TriggerEvaluateInput;

export interface TriggerResult {
  triggered: boolean;
  triggerType: string;
  confidence: number; // 0..1
  matchDetails: Record<string, unknown>;
  evaluatedAt: number;
}

// ─────────────────────────────────────────────────────────────
// TriggerBot Implementation
// ─────────────────────────────────────────────────────────────

export class TriggerBot extends Bot {
  private readonly log: Logger;

  constructor() {
    const handler = async (input: TriggerInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-DIGITALGRID-TRIGGER',
      'Trigger',
      handler,
      'Trigger evaluation (event, schedule, webhook, threshold, compound)'
    );

    this.log = new Logger('TriggerBot');
  }

  private async process(input: TriggerInput): Promise<TriggerResult> {
    switch (input.operation) {
      case 'EVALUATE':
        return this.evaluate(input);
      default:
        throw new Error(`TriggerBot: Unknown operation "${(input as any).operation}"`);
    }
  }

  // ─────────────────────────────────────────────────────────────
  // EVALUATE
  // ─────────────────────────────────────────────────────────────

  private evaluate(input: TriggerEvaluateInput): TriggerResult {
    const { triggerType, config, event } = input;

    switch (triggerType) {
      case 'event':
        return this.evaluateEventTrigger(config, event);
      case 'schedule':
        return this.evaluateScheduleTrigger(config);
      case 'webhook':
        return this.evaluateWebhookTrigger(config, event);
      case 'threshold':
        return this.evaluateThresholdTrigger(config, event);
      case 'compound':
        return this.evaluateCompoundTrigger(config, event);
      default:
        this.log.warn('Unknown trigger type', { triggerType });
        return {
          triggered: false,
          triggerType,
          confidence: 0,
          matchDetails: { error: `Unknown trigger type: ${triggerType}` },
          evaluatedAt: Date.now(),
        };
    }
  }

  // ─────────────────────────────────────────────────────────────
  // Event Trigger
  // ─────────────────────────────────────────────────────────────

  /**
   * Event trigger: activates when an event matches the configured type and optional filters.
   * Config: { eventTypes: string[], sourceFilter?: string, payloadFilter?: Record<string, unknown> }
   */
  private evaluateEventTrigger(
    config: Record<string, unknown>,
    event: TriggerEvaluateInput['event']
  ): TriggerResult {
    if (!event) {
      return {
        triggered: false,
        triggerType: 'event',
        confidence: 0,
        matchDetails: { reason: 'No event provided' },
        evaluatedAt: Date.now(),
      };
    }

    const eventTypes = (config.eventTypes as string[]) ?? [];
    const sourceFilter = config.sourceFilter as string | undefined;
    const payloadFilter = config.payloadFilter as Record<string, unknown> | undefined;

    // Check event type match
    const typeMatch = eventTypes.length === 0 || eventTypes.includes(event.type);

    // Check source filter
    const sourceMatch = !sourceFilter || event.source === sourceFilter;

    // Check payload filter
    let payloadMatch = true;
    let payloadDetails: Record<string, boolean> = {};
    if (payloadFilter) {
      for (const [key, expected] of Object.entries(payloadFilter)) {
        const actual = this.resolveNestedValue(event.payload, key);
        const match = actual === expected;
        payloadDetails[key] = match;
        if (!match) payloadMatch = false;
      }
    }

    const triggered = typeMatch && sourceMatch && payloadMatch;

    // Confidence based on how many conditions were checked and passed
    let conditions = 0;
    let passed = 0;
    if (eventTypes.length > 0) { conditions++; if (typeMatch) passed++; }
    if (sourceFilter) { conditions++; if (sourceMatch) passed++; }
    if (payloadFilter) { conditions++; if (payloadMatch) passed++; }
    const confidence = conditions > 0 ? passed / conditions : (triggered ? 1 : 0);

    this.log.info('Event trigger evaluated', { triggered, confidence, eventType: event.type });

    return {
      triggered,
      triggerType: 'event',
      confidence,
      matchDetails: {
        eventId: event.id,
        eventType: event.type,
        typeMatch,
        sourceMatch,
        payloadMatch,
        payloadDetails,
      },
      evaluatedAt: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────
  // Schedule Trigger
  // ─────────────────────────────────────────────────────────────

  /**
   * Schedule trigger: activates based on time conditions.
   * Config: { cron?: string, intervalMs?: number, startTime?: number, endTime?: number, timezone?: string }
   */
  private evaluateScheduleTrigger(config: Record<string, unknown>): TriggerResult {
    const now = Date.now();
    const intervalMs = config.intervalMs as number | undefined;
    const startTime = config.startTime as number | undefined;
    const endTime = config.endTime as number | undefined;
    const cron = config.cron as string | undefined;

    // Check time window
    let inWindow = true;
    if (startTime && now < startTime) inWindow = false;
    if (endTime && now > endTime) inWindow = false;

    // Check interval
    let intervalTriggered = false;
    if (intervalMs && intervalMs > 0) {
      // If we have a reference start time, check if current time aligns with interval
      const reference = startTime ?? 0;
      intervalTriggered = (now - reference) % intervalMs < 1000; // within 1 second of interval
    }

    // Check cron expression (simplified — supports minute/hour/day-of-month/month/day-of-week)
    let cronTriggered = false;
    if (cron) {
      cronTriggered = this.evaluateCron(cron, new Date(now));
    }

    const triggered = inWindow && (intervalTriggered || cronTriggered || (!intervalMs && !cron));
    const confidence = triggered ? 1.0 : 0.0;

    this.log.info('Schedule trigger evaluated', { triggered, inWindow });

    return {
      triggered,
      triggerType: 'schedule',
      confidence,
      matchDetails: {
        now,
        inWindow,
        intervalTriggered,
        cronTriggered,
        hasInterval: !!intervalMs,
        hasCron: !!cron,
      },
      evaluatedAt: now,
    };
  }

  /**
   * Simplified cron evaluator.
   * Format: minute hour dayOfMonth month dayOfWeek
   * Supports: *, specific values, ranges (1-5), lists (1,3,5), steps (*&#47;5)
   */
  private evaluateCron(cron: string, date: Date): boolean {
    const parts = cron.trim().split(/\s+/);
    if (parts.length < 5) return false;

    const fields = [
      { value: date.getMinutes(), pattern: parts[0], range: [0, 59] },
      { value: date.getHours(), pattern: parts[1], range: [0, 23] },
      { value: date.getDate(), pattern: parts[2], range: [1, 31] },
      { value: date.getMonth() + 1, pattern: parts[3], range: [1, 12] },
      { value: date.getDay(), pattern: parts[4], range: [0, 6] },
    ];

    return fields.every((field) => this.cronFieldMatches(field.value, field.pattern, field.range as [number, number]));
  }

  private cronFieldMatches(value: number, pattern: string, range: [number, number]): boolean {
    if (pattern === '*') return true;

    // Step pattern: */5
    if (pattern.startsWith('*/')) {
      const step = parseInt(pattern.slice(2), 10);
      return step > 0 && value % step === 0;
    }

    // List pattern: 1,3,5
    if (pattern.includes(',')) {
      return pattern.split(',').some((p) => this.cronFieldMatches(value, p.trim(), range));
    }

    // Range pattern: 1-5
    if (pattern.includes('-')) {
      const [start, end] = pattern.split('-').map(Number);
      return value >= start && value <= end;
    }

    // Exact value
    return value === parseInt(pattern, 10);
  }

  // ─────────────────────────────────────────────────────────────
  // Webhook Trigger
  // ─────────────────────────────────────────────────────────────

  /**
   * Webhook trigger: activates when a webhook payload matches.
   * Config: { path?: string, method?: string, headers?: Record<string, string>, bodyFilter?: Record<string, unknown> }
   */
  private evaluateWebhookTrigger(
    config: Record<string, unknown>,
    event: TriggerEvaluateInput['event']
  ): TriggerResult {
    if (!event) {
      return {
        triggered: false,
        triggerType: 'webhook',
        confidence: 0,
        matchDetails: { reason: 'No event provided' },
        evaluatedAt: Date.now(),
      };
    }

    const expectedPath = config.path as string | undefined;
    const expectedMethod = config.method as string | undefined;
    const expectedHeaders = config.headers as Record<string, string> | undefined;
    const bodyFilter = config.bodyFilter as Record<string, unknown> | undefined;

    // Check path match (from event metadata)
    const pathMatch = !expectedPath || event.metadata.path === expectedPath;

    // Check method match
    const methodMatch = !expectedMethod || event.metadata.method === expectedMethod;

    // Check headers
    let headersMatch = true;
    if (expectedHeaders) {
      const eventHeaders = (event.metadata.headers as Record<string, string>) ?? {};
      for (const [key, expected] of Object.entries(expectedHeaders)) {
        if (eventHeaders[key.toLowerCase()] !== expected) {
          headersMatch = false;
          break;
        }
      }
    }

    // Check body filter
    let bodyMatch = true;
    let bodyDetails: Record<string, boolean> = {};
    if (bodyFilter) {
      for (const [key, expected] of Object.entries(bodyFilter)) {
        const actual = this.resolveNestedValue(event.payload, key);
        const match = actual === expected;
        bodyDetails[key] = match;
        if (!match) bodyMatch = false;
      }
    }

    const triggered = pathMatch && methodMatch && headersMatch && bodyMatch;

    let conditions = 0;
    let passed = 0;
    if (expectedPath) { conditions++; if (pathMatch) passed++; }
    if (expectedMethod) { conditions++; if (methodMatch) passed++; }
    if (expectedHeaders) { conditions++; if (headersMatch) passed++; }
    if (bodyFilter) { conditions++; if (bodyMatch) passed++; }
    const confidence = conditions > 0 ? passed / conditions : 1;

    this.log.info('Webhook trigger evaluated', { triggered, confidence });

    return {
      triggered,
      triggerType: 'webhook',
      confidence,
      matchDetails: {
        pathMatch,
        methodMatch,
        headersMatch,
        bodyMatch,
        bodyDetails,
      },
      evaluatedAt: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────
  // Threshold Trigger
  // ─────────────────────────────────────────────────────────────

  /**
   * Threshold trigger: activates when a metric crosses a threshold.
   * Config: { metric: string, operator: '>'|'>='|'<'|'<='|'=='|'!=', threshold: number, valuePath?: string }
   */
  private evaluateThresholdTrigger(
    config: Record<string, unknown>,
    event: TriggerEvaluateInput['event']
  ): TriggerResult {
    const metric = config.metric as string;
    const operator = (config.operator as string) ?? '>';
    const threshold = config.threshold as number;
    const valuePath = config.valuePath as string | undefined;

    // Get current value from event or config
    let value: number | undefined;
    if (event && valuePath) {
      const raw = this.resolveNestedValue(event.payload, valuePath);
      value = typeof raw === 'number' ? raw : parseFloat(String(raw));
    } else if (event) {
      const raw = this.resolveNestedValue(event.payload, metric);
      value = typeof raw === 'number' ? raw : parseFloat(String(raw));
    }

    if (value === undefined || isNaN(value)) {
      return {
        triggered: false,
        triggerType: 'threshold',
        confidence: 0,
        matchDetails: { reason: 'Unable to resolve metric value', metric, valuePath },
        evaluatedAt: Date.now(),
      };
    }

    let triggered = false;
    switch (operator) {
      case '>':  triggered = value > threshold; break;
      case '>=': triggered = value >= threshold; break;
      case '<':  triggered = value < threshold; break;
      case '<=': triggered = value <= threshold; break;
      case '==': triggered = value === threshold; break;
      case '!=': triggered = value !== threshold; break;
    }

    // Confidence based on distance from threshold
    const distance = Math.abs(value - threshold);
    const relativeDistance = threshold !== 0 ? distance / Math.abs(threshold) : distance;
    const confidence = triggered ? Math.min(1, 0.5 + relativeDistance * 0.5) : 0;

    this.log.info('Threshold trigger evaluated', { triggered, metric, value, threshold, operator });

    return {
      triggered,
      triggerType: 'threshold',
      confidence,
      matchDetails: {
        metric,
        value,
        threshold,
        operator,
        distance,
      },
      evaluatedAt: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────
  // Compound Trigger
  // ─────────────────────────────────────────────────────────────

  /**
   * Compound trigger: combines multiple trigger evaluations using logical operators.
   * Config: { logic: 'AND' | 'OR' | 'NOT', triggers: Array<{ triggerType: string, config: Record<string, unknown> }> }
   */
  private evaluateCompoundTrigger(
    config: Record<string, unknown>,
    event: TriggerEvaluateInput['event']
  ): TriggerResult {
    const logic = (config.logic as string) ?? 'AND';
    const triggers = config.triggers as Array<{ triggerType: string; config: Record<string, unknown> }>;

    if (!triggers || triggers.length === 0) {
      return {
        triggered: false,
        triggerType: 'compound',
        confidence: 0,
        matchDetails: { reason: 'No sub-triggers defined' },
        evaluatedAt: Date.now(),
      };
    }

    // Evaluate each sub-trigger
    const subResults: Array<{ triggered: boolean; confidence: number; triggerType: string }> = [];

    for (const sub of triggers) {
      const subInput: TriggerEvaluateInput = {
        operation: 'EVALUATE',
        triggerType: sub.triggerType as TriggerEvaluateInput['triggerType'],
        config: sub.config,
        event,
      };

      const result = this.evaluate(subInput);
      subResults.push({
        triggered: result.triggered,
        confidence: result.confidence,
        triggerType: result.triggerType,
      });
    }

    // Apply logical operator
    let triggered = false;
    switch (logic) {
      case 'AND':
        triggered = subResults.every((r) => r.triggered);
        break;
      case 'OR':
        triggered = subResults.some((r) => r.triggered);
        break;
      case 'NOT':
        triggered = !subResults.some((r) => r.triggered);
        break;
    }

    // Confidence: average of sub-results for AND/OR, complement for NOT
    const avgConfidence = subResults.reduce((sum, r) => sum + r.confidence, 0) / subResults.length;
    const confidence = logic === 'NOT' ? 1 - avgConfidence : avgConfidence;

    this.log.info('Compound trigger evaluated', { triggered, logic, subTriggerCount: triggers.length });

    return {
      triggered,
      triggerType: 'compound',
      confidence: triggered ? confidence : 0,
      matchDetails: {
        logic,
        subResults: subResults.map((r) => ({
          triggerType: r.triggerType,
          triggered: r.triggered,
          confidence: r.confidence,
        })),
      },
      evaluatedAt: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────
  // Utilities
  // ─────────────────────────────────────────────────────────────

  private resolveNestedValue(obj: Record<string, unknown>, path: string): unknown {
    const parts = path.split('.');
    let current: unknown = obj;
    for (const part of parts) {
      if (current === null || current === undefined || typeof current !== 'object') return undefined;
      current = (current as Record<string, unknown>)[part];
    }
    return current;
  }
}
