/**
 * LoopBot — Loop Iteration Bot for DigitalGrid
 *
 * Identity:  NID-DIGITALGRID-LOOP
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    DigitalGridAI (AID-DIGITALGRID)
 *
 * Responsibilities:
 *   - Manage loop iteration state for workflow steps
 *   - Support loop types: count, while, for-each, do-while, until
 *   - Compute iteration progress, remaining, and completion status
 *   - Provide loop control decisions (continue, break, skip)
 */

import { Bot, Logger } from '../../../core/definitions';

// ─────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────

export interface LoopIterateInput {
  operation: 'ITERATE';
  loopType: 'count' | 'while' | 'for-each' | 'do-while' | 'until';
  config: Record<string, unknown>;
  iteration: number;
}

export type LoopInput = LoopIterateInput;

export interface LoopResult {
  continue: boolean;      // should the loop continue?
  iteration: number;       // current iteration (0-based)
  totalIterations: number | null; // total expected (null if unknown/unbounded)
  progress: number;        // 0..1 completion percentage
  currentItem: unknown;    // current item for for-each
  accumulator: Record<string, unknown>; // accumulated state
  action: 'continue' | 'break' | 'skip';
  reason: string;
  metadata: Record<string, unknown>;
}

// ─────────────────────────────────────────────────────────────
// LoopBot Implementation
// ─────────────────────────────────────────────────────────────

export class LoopBot extends Bot {
  private readonly log: Logger;

  constructor() {
    const handler = async (input: LoopInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-DIGITALGRID-LOOP',
      'Loop',
      handler,
      'Loop iteration (count, while, for-each, do-while, until)'
    );

    this.log = new Logger('LoopBot');
  }

  private async process(input: LoopInput): Promise<LoopResult> {
    switch (input.operation) {
      case 'ITERATE':
        return this.iterate(input);
      default:
        throw new Error(`LoopBot: Unknown operation "${(input as any).operation}"`);
    }
  }

  // ─────────────────────────────────────────────────────────────
  // ITERATE
  // ─────────────────────────────────────────────────────────────

  private iterate(input: LoopIterateInput): LoopResult {
    const { loopType, config, iteration } = input;

    switch (loopType) {
      case 'count':
        return this.iterateCount(config, iteration);
      case 'while':
        return this.iterateWhile(config, iteration);
      case 'for-each':
        return this.iterateForEach(config, iteration);
      case 'do-while':
        return this.iterateDoWhile(config, iteration);
      case 'until':
        return this.iterateUntil(config, iteration);
      default:
        this.log.warn('Unknown loop type', { loopType });
        return {
          continue: false,
          iteration,
          totalIterations: null,
          progress: 0,
          currentItem: null,
          accumulator: {},
          action: 'break',
          reason: `Unknown loop type: ${loopType}`,
          metadata: {},
        };
    }
  }

  // ─────────────────────────────────────────────────────────────
  // Count Loop
  // ─────────────────────────────────────────────────────────────

  /**
   * Count loop: iterates a fixed number of times.
   * Config: {
   *   count: number,                // total iterations
   *   startIndex?: number,          // default 0
   *   step?: number,                // increment per iteration, default 1
   *   maxIterations?: number,       // safety limit
   *   accumulator?: Record<string, unknown>  // carried state
   * }
   */
  private iterateCount(config: Record<string, unknown>, iteration: number): LoopResult {
    const count = (config.count as number) ?? 0;
    const startIndex = (config.startIndex as number) ?? 0;
    const step = (config.step as number) ?? 1;
    const maxIterations = (config.maxIterations as number) ?? 10000;
    const accumulator = (config.accumulator as Record<string, unknown>) ?? {};

    const currentIndex = startIndex + iteration * step;
    const shouldContinue = iteration < count && iteration < maxIterations;
    const progress = count > 0 ? Math.min(iteration / count, 1) : 0;

    const action: LoopResult['action'] = shouldContinue
      ? (iteration < count - 1 ? 'continue' : 'break')
      : 'break';

    const reason = iteration >= count
      ? `Completed ${count} iterations`
      : iteration >= maxIterations
        ? `Safety limit reached (${maxIterations})`
        : `Iteration ${iteration} of ${count}`;

    this.log.info('Count loop iterated', { iteration, count, shouldContinue });

    return {
      continue: shouldContinue,
      iteration,
      totalIterations: count,
      progress,
      currentItem: currentIndex,
      accumulator: {
        ...accumulator,
        index: iteration,
        current: currentIndex,
        remaining: Math.max(0, count - iteration - 1),
      },
      action,
      reason,
      metadata: {
        count,
        startIndex,
        step,
        currentIndex,
      },
    };
  }

  // ─────────────────────────────────────────────────────────────
  // While Loop
  // ─────────────────────────────────────────────────────────────

  /**
   * While loop: continues while a condition is true.
   * Config: {
   *   condition: {
   *     path: string,
   *     operator: string,
   *     value: unknown
   *   },
   *   data: Record<string, unknown>,     // current data to evaluate
   *   maxIterations?: number,             // safety limit
   *   accumulator?: Record<string, unknown>
   * }
   */
  private iterateWhile(config: Record<string, unknown>, iteration: number): LoopResult {
    const condition = config.condition as {
      path: string;
      operator: string;
      value: unknown;
    } | undefined;
    const data = (config.data as Record<string, unknown>) ?? {};
    const maxIterations = (config.maxIterations as number) ?? 10000;
    const accumulator = (config.accumulator as Record<string, unknown>) ?? {};

    // Evaluate condition
    let conditionMet = false;
    if (condition) {
      const actualValue = this.resolvePath(data, condition.path);
      conditionMet = this.evaluateOperator(actualValue, condition.operator, condition.value);
    }

    const shouldContinue = conditionMet && iteration < maxIterations;

    const action: LoopResult['action'] = shouldContinue ? 'continue' : 'break';
    const reason = !conditionMet
      ? 'Condition no longer met'
      : iteration >= maxIterations
        ? `Safety limit reached (${maxIterations})`
        : `Condition met at iteration ${iteration}`;

    this.log.info('While loop iterated', { iteration, conditionMet, shouldContinue });

    return {
      continue: shouldContinue,
      iteration,
      totalIterations: null, // unknown for while loops
      progress: 0, // cannot compute for unbounded loops
      currentItem: null,
      accumulator: {
        ...accumulator,
        iteration,
        conditionMet,
      },
      action,
      reason,
      metadata: {
        conditionMet,
        maxIterations,
      },
    };
  }

  // ─────────────────────────────────────────────────────────────
  // For-Each Loop
  // ─────────────────────────────────────────────────────────────

  /**
   * For-each loop: iterates over a collection of items.
   * Config: {
   *   items: unknown[],            // collection to iterate
   *   itemPath?: string,           // path to items in data (alternative to items)
   *   data?: Record<string, unknown>,
   *   accumulator?: Record<string, unknown>
   * }
   */
  private iterateForEach(config: Record<string, unknown>, iteration: number): LoopResult {
    let items = config.items as unknown[] | undefined;
    const itemPath = config.itemPath as string | undefined;
    const data = (config.data as Record<string, unknown>) ?? {};
    const accumulator = (config.accumulator as Record<string, unknown>) ?? {};

    // Resolve items from data path if not directly provided
    if (!items && itemPath) {
      const resolved = this.resolvePath(data, itemPath);
      items = Array.isArray(resolved) ? resolved : [];
    }

    if (!items) items = [];

    const shouldContinue = iteration < items.length;
    const currentItem = shouldContinue ? items[iteration] : null;
    const progress = items.length > 0 ? Math.min((iteration + 1) / items.length, 1) : 1;

    const action: LoopResult['action'] = shouldContinue
      ? (iteration < items.length - 1 ? 'continue' : 'break')
      : 'break';

    const reason = iteration >= items.length
      ? `Completed all ${items.length} items`
      : `Processing item ${iteration + 1} of ${items.length}`;

    this.log.info('For-each loop iterated', { iteration, totalItems: items.length, shouldContinue });

    return {
      continue: shouldContinue,
      iteration,
      totalIterations: items.length,
      progress,
      currentItem,
      accumulator: {
        ...accumulator,
        index: iteration,
        item: currentItem,
        remaining: Math.max(0, items.length - iteration - 1),
        processed: iteration + 1,
      },
      action,
      reason,
      metadata: {
        totalItems: items.length,
        itemType: currentItem !== null ? typeof currentItem : 'undefined',
      },
    };
  }

  // ─────────────────────────────────────────────────────────────
  // Do-While Loop
  // ─────────────────────────────────────────────────────────────

  /**
   * Do-while loop: executes at least once, then continues while condition is true.
   * Same config as while loop, but first iteration always executes.
   * Config: {
   *   condition: { path, operator, value },
   *   data: Record<string, unknown>,
   *   maxIterations?: number,
   *   accumulator?: Record<string, unknown>
   * }
   */
  private iterateDoWhile(config: Record<string, unknown>, iteration: number): LoopResult {
    const condition = config.condition as {
      path: string;
      operator: string;
      value: unknown;
    } | undefined;
    const data = (config.data as Record<string, unknown>) ?? {};
    const maxIterations = (config.maxIterations as number) ?? 10000;
    const accumulator = (config.accumulator as Record<string, unknown>) ?? {};

    // First iteration always executes (do-while semantics)
    if (iteration === 0) {
      this.log.info('Do-while loop: first iteration (always executes)');

      return {
        continue: true,
        iteration: 0,
        totalIterations: null,
        progress: 0,
        currentItem: null,
        accumulator: {
          ...accumulator,
          iteration: 0,
          conditionMet: true, // hasn't been checked yet
          firstIteration: true,
        },
        action: 'continue',
        reason: 'Do-while: first iteration always executes',
        metadata: {
          conditionChecked: false,
          maxIterations,
        },
      };
    }

    // Subsequent iterations: check condition
    let conditionMet = false;
    if (condition) {
      const actualValue = this.resolvePath(data, condition.path);
      conditionMet = this.evaluateOperator(actualValue, condition.operator, condition.value);
    }

    const shouldContinue = conditionMet && iteration < maxIterations;

    const action: LoopResult['action'] = shouldContinue ? 'continue' : 'break';
    const reason = !conditionMet
      ? 'Condition no longer met (do-while terminating)'
      : iteration >= maxIterations
        ? `Safety limit reached (${maxIterations})`
        : `Condition met at iteration ${iteration}`;

    this.log.info('Do-while loop iterated', { iteration, conditionMet, shouldContinue });

    return {
      continue: shouldContinue,
      iteration,
      totalIterations: null,
      progress: 0,
      currentItem: null,
      accumulator: {
        ...accumulator,
        iteration,
        conditionMet,
      },
      action,
      reason,
      metadata: {
        conditionMet,
        conditionChecked: true,
        maxIterations,
      },
    };
  }

  // ─────────────────────────────────────────────────────────────
  // Until Loop
  // ─────────────────────────────────────────────────────────────

  /**
   * Until loop: continues until a condition becomes true (opposite of while).
   * Config: {
   *   condition: { path, operator, value },
   *   data: Record<string, unknown>,
   *   maxIterations?: number,
   *   accumulator?: Record<string, unknown>
   * }
   */
  private iterateUntil(config: Record<string, unknown>, iteration: number): LoopResult {
    const condition = config.condition as {
      path: string;
      operator: string;
      value: unknown;
    } | undefined;
    const data = (config.data as Record<string, unknown>) ?? {};
    const maxIterations = (config.maxIterations as number) ?? 10000;
    const accumulator = (config.accumulator as Record<string, unknown>) ?? {};

    // Evaluate condition — loop continues until it's TRUE
    let conditionMet = false;
    if (condition) {
      const actualValue = this.resolvePath(data, condition.path);
      conditionMet = this.evaluateOperator(actualValue, condition.operator, condition.value);
    }

    // Until: continue while condition is NOT met
    const shouldContinue = !conditionMet && iteration < maxIterations;

    const action: LoopResult['action'] = shouldContinue ? 'continue' : 'break';
    const reason = conditionMet
      ? 'Target condition reached (until satisfied)'
      : iteration >= maxIterations
        ? `Safety limit reached (${maxIterations})`
        : `Condition not yet met at iteration ${iteration}`;

    this.log.info('Until loop iterated', { iteration, conditionMet, shouldContinue });

    return {
      continue: shouldContinue,
      iteration,
      totalIterations: null,
      progress: 0,
      currentItem: null,
      accumulator: {
        ...accumulator,
        iteration,
        conditionMet,
      },
      action,
      reason,
      metadata: {
        conditionMet,
        maxIterations,
      },
    };
  }

  // ─────────────────────────────────────────────────────────────
  // Utilities
  // ─────────────────────────────────────────────────────────────

  private resolvePath(obj: Record<string, unknown>, path: string): unknown {
    const parts = path.split('.');
    let current: unknown = obj;
    for (const part of parts) {
      if (current === null || current === undefined || typeof current !== 'object') return undefined;
      current = (current as Record<string, unknown>)[part];
    }
    return current;
  }

  private evaluateOperator(actual: unknown, operator: string, expected: unknown): boolean {
    switch (operator) {
      case '==':  return actual == expected;
      case '===': return actual === expected;
      case '!=':  return actual != expected;
      case '!==': return actual !== expected;
      case '>':   return typeof actual === 'number' && typeof expected === 'number' && actual > expected;
      case '>=':  return typeof actual === 'number' && typeof expected === 'number' && actual >= expected;
      case '<':   return typeof actual === 'number' && typeof expected === 'number' && actual < expected;
      case '<=':  return typeof actual === 'number' && typeof expected === 'number' && actual <= expected;
      case 'contains': return typeof actual === 'string' && typeof expected === 'string' && actual.includes(expected);
      case 'startsWith': return typeof actual === 'string' && typeof expected === 'string' && actual.startsWith(expected);
      case 'endsWith': return typeof actual === 'string' && typeof expected === 'string' && actual.endsWith(expected);
      case 'exists': return actual !== undefined && actual !== null;
      case 'empty': return actual === undefined || actual === null || actual === '' || (Array.isArray(actual) && actual.length === 0);
      default: return false;
    }
  }
}
