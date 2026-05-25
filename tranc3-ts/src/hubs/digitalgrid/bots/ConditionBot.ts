/**
 * ConditionBot — Condition Evaluation Bot for DigitalGrid
 *
 * Identity:  NID-DIGITALGRID-CONDITION
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    DigitalGridAI (AID-DIGITALGRID)
 *
 * Responsibilities:
 *   - Evaluate conditional logic for workflow routing
 *   - Support condition types: comparison, logical, range, regex, type-check, custom
 *   - Return boolean result with evaluation details
 *   - Support nested data access via dot notation
 */

import { Bot, Logger } from '../../../core/definitions';

// ─────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────

export interface ConditionEvaluateInput {
  operation: 'EVALUATE';
  conditionType: 'comparison' | 'logical' | 'range' | 'regex' | 'type-check' | 'custom';
  config: Record<string, unknown>;
  data: Record<string, unknown>;
}

export type ConditionInput = ConditionEvaluateInput;

export interface ConditionResult {
  passed: boolean;
  conditionType: string;
  details: Record<string, unknown>;
  evaluatedAt: number;
}

// ─────────────────────────────────────────────────────────────
// ConditionBot Implementation
// ─────────────────────────────────────────────────────────────

export class ConditionBot extends Bot {
  private readonly log: Logger;

  constructor() {
    const handler = async (input: ConditionInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-DIGITALGRID-CONDITION',
      'Condition',
      handler,
      'Condition evaluation (comparison, logical, range, regex, type-check, custom)'
    );

    this.log = new Logger('ConditionBot');
  }

  private async process(input: ConditionInput): Promise<ConditionResult> {
    switch (input.operation) {
      case 'EVALUATE':
        return this.evaluate(input);
      default:
        throw new Error(`ConditionBot: Unknown operation "${(input as any).operation}"`);
    }
  }

  // ─────────────────────────────────────────────────────────────
  // EVALUATE
  // ─────────────────────────────────────────────────────────────

  private evaluate(input: ConditionEvaluateInput): ConditionResult {
    const { conditionType, config, data } = input;

    switch (conditionType) {
      case 'comparison':
        return this.evaluateComparison(config, data);
      case 'logical':
        return this.evaluateLogical(config, data);
      case 'range':
        return this.evaluateRange(config, data);
      case 'regex':
        return this.evaluateRegex(config, data);
      case 'type-check':
        return this.evaluateTypeCheck(config, data);
      case 'custom':
        return this.evaluateCustom(config, data);
      default:
        this.log.warn('Unknown condition type', { conditionType });
        return {
          passed: false,
          conditionType,
          details: { error: `Unknown condition type: ${conditionType}` },
          evaluatedAt: Date.now(),
        };
    }
  }

  // ─────────────────────────────────────────────────────────────
  // Comparison Condition
  // ─────────────────────────────────────────────────────────────

  /**
   * Comparison condition: compares a data value against a reference.
   * Config: {
   *   path: string,                  // dot-notation path in data
   *   operator: '==' | '!=' | '>' | '>=' | '<' | '<=' | '===' | '!==',
   *   value: unknown,                // reference value
   *   caseInsensitive?: boolean      // for string comparisons
   * }
   */
  private evaluateComparison(
    config: Record<string, unknown>,
    data: Record<string, unknown>
  ): ConditionResult {
    const path = config.path as string;
    const operator = (config.operator as string) ?? '==';
    const referenceValue = config.value;
    const caseInsensitive = (config.caseInsensitive as boolean) ?? false;

    const actualValue = this.resolvePath(data, path);

    let passed = false;
    let comparisonDetail: string;

    if (actualValue === undefined) {
      comparisonDetail = `path "${path}" resolved to undefined`;
    } else {
      let actual = actualValue;
      let expected = referenceValue;

      // Case-insensitive string comparison
      if (caseInsensitive && typeof actual === 'string' && typeof expected === 'string') {
        actual = actual.toLowerCase();
        expected = expected.toLowerCase();
      }

      switch (operator) {
        case '==':
          passed = actual == expected;
          break;
        case '!=':
          passed = actual != expected;
          break;
        case '===':
          passed = actual === expected;
          break;
        case '!==':
          passed = actual !== expected;
          break;
        case '>':
          passed = typeof actual === 'number' && typeof expected === 'number' && actual > expected;
          break;
        case '>=':
          passed = typeof actual === 'number' && typeof expected === 'number' && actual >= expected;
          break;
        case '<':
          passed = typeof actual === 'number' && typeof expected === 'number' && actual < expected;
          break;
        case '<=':
          passed = typeof actual === 'number' && typeof expected === 'number' && actual <= expected;
          break;
        default:
          comparisonDetail = `Unknown operator: ${operator}`;
      }

      comparisonDetail = `${JSON.stringify(actualValue)} ${operator} ${JSON.stringify(referenceValue)} → ${passed}`;
    }

    this.log.info('Comparison condition evaluated', { passed, path, operator });

    return {
      passed,
      conditionType: 'comparison',
      details: {
        path,
        operator,
        actualValue,
        referenceValue,
        comparisonDetail,
        caseInsensitive,
      },
      evaluatedAt: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────
  // Logical Condition
  // ─────────────────────────────────────────────────────────────

  /**
   * Logical condition: combines multiple sub-conditions with AND/OR/NOT/XOR.
   * Config: {
   *   operator: 'AND' | 'OR' | 'NOT' | 'XOR' | 'NAND' | 'NOR',
   *   conditions: Array<{
   *     conditionType: string,
   *     config: Record<string, unknown>
   *   }>
   * }
   */
  private evaluateLogical(
    config: Record<string, unknown>,
    data: Record<string, unknown>
  ): ConditionResult {
    const operator = (config.operator as string) ?? 'AND';
    const conditions = config.conditions as Array<{
      conditionType: ConditionEvaluateInput['conditionType'];
      config: Record<string, unknown>;
    }>;

    if (!conditions || conditions.length === 0) {
      return {
        passed: false,
        conditionType: 'logical',
        details: { error: 'No sub-conditions defined' },
        evaluatedAt: Date.now(),
      };
    }

    // Evaluate each sub-condition
    const subResults: Array<{ conditionType: string; passed: boolean; details: Record<string, unknown> }> = [];

    for (const cond of conditions) {
      const subInput: ConditionEvaluateInput = {
        operation: 'EVALUATE',
        conditionType: cond.conditionType,
        config: cond.config,
        data,
      };

      const result = this.evaluate(subInput);
      subResults.push({
        conditionType: result.conditionType,
        passed: result.passed,
        details: result.details,
      });
    }

    // Apply logical operator
    let passed = false;
    const passedCount = subResults.filter((r) => r.passed).length;
    const failedCount = subResults.length - passedCount;

    switch (operator) {
      case 'AND':
        passed = subResults.every((r) => r.passed);
        break;
      case 'OR':
        passed = subResults.some((r) => r.passed);
        break;
      case 'NOT':
        passed = !subResults.some((r) => r.passed);
        break;
      case 'XOR':
        passed = passedCount === 1;
        break;
      case 'NAND':
        passed = !subResults.every((r) => r.passed);
        break;
      case 'NOR':
        passed = !subResults.some((r) => r.passed);
        break;
    }

    this.log.info('Logical condition evaluated', { passed, operator, subCount: conditions.length });

    return {
      passed,
      conditionType: 'logical',
      details: {
        operator,
        totalConditions: conditions.length,
        passedCount,
        failedCount,
        subResults: subResults.map((r) => ({
          conditionType: r.conditionType,
          passed: r.passed,
        })),
      },
      evaluatedAt: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────
  // Range Condition
  // ─────────────────────────────────────────────────────────────

  /**
   * Range condition: checks if a value falls within a range.
   * Config: {
   *   path: string,
   *   min?: number,
   *   max?: number,
   *   inclusive?: boolean,      // default true, inclusive bounds
   *   minExclusive?: boolean,   // override for min bound
   *   maxExclusive?: boolean    // override for max bound
   * }
   */
  private evaluateRange(
    config: Record<string, unknown>,
    data: Record<string, unknown>
  ): ConditionResult {
    const path = config.path as string;
    const min = config.min as number | undefined;
    const max = config.max as number | undefined;
    const inclusive = (config.inclusive as boolean) ?? true;

    const value = this.resolvePath(data, path);

    if (typeof value !== 'number') {
      return {
        passed: false,
        conditionType: 'range',
        details: { path, value, error: 'Value is not a number' },
        evaluatedAt: Date.now(),
      };
    }

    let minPassed = true;
    let maxPassed = true;

    if (min !== undefined) {
      const minInclusive = config.minExclusive !== undefined ? !config.minExclusive : inclusive;
      minPassed = minInclusive ? value >= min : value > min;
    }

    if (max !== undefined) {
      const maxInclusive = config.maxExclusive !== undefined ? !config.maxExclusive : inclusive;
      maxPassed = maxInclusive ? value <= max : value < max;
    }

    const passed = minPassed && maxPassed;

    this.log.info('Range condition evaluated', { passed, path, value, min, max });

    return {
      passed,
      conditionType: 'range',
      details: {
        path,
        value,
        min,
        max,
        minPassed,
        maxPassed,
        inclusive,
      },
      evaluatedAt: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────
  // Regex Condition
  // ─────────────────────────────────────────────────────────────

  /**
   * Regex condition: tests a string value against a regular expression.
   * Config: {
   *   path: string,
   *   pattern: string,           // regex pattern
   *   flags?: string,            // regex flags (g, i, m, s, u)
   *   negate?: boolean           // pass if pattern does NOT match
   * }
   */
  private evaluateRegex(
    config: Record<string, unknown>,
    data: Record<string, unknown>
  ): ConditionResult {
    const path = config.path as string;
    const pattern = config.pattern as string;
    const flags = (config.flags as string) ?? '';
    const negate = (config.negate as boolean) ?? false;

    const value = this.resolvePath(data, path);
    const stringValue = value !== undefined && value !== null ? String(value) : '';

    let regex: RegExp;
    try {
      regex = new RegExp(pattern, flags);
    } catch (error) {
      return {
        passed: false,
        conditionType: 'regex',
        details: { path, pattern, error: `Invalid regex: ${String(error)}` },
        evaluatedAt: Date.now(),
      };
    }

    const matches = regex.test(stringValue);
    const passed = negate ? !matches : matches;

    this.log.info('Regex condition evaluated', { passed, path, pattern });

    return {
      passed,
      conditionType: 'regex',
      details: {
        path,
        value: stringValue,
        pattern,
        flags,
        negate,
        matches,
      },
      evaluatedAt: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────
  // Type Check Condition
  // ─────────────────────────────────────────────────────────────

  /**
   * Type-check condition: verifies the type of a data value.
   * Config: {
   *   path: string,
   *   expectedType: 'string' | 'number' | 'boolean' | 'object' | 'array' | 'null' | 'undefined' | 'function',
   *   nullable?: boolean        // allow null/undefined values to pass
   * }
   */
  private evaluateTypeCheck(
    config: Record<string, unknown>,
    data: Record<string, unknown>
  ): ConditionResult {
    const path = config.path as string;
    const expectedType = config.expectedType as string;
    const nullable = (config.nullable as boolean) ?? false;

    const value = this.resolvePath(data, path);
    const actualType = this.getTypeOf(value);

    // Null/undefined check
    if ((value === null || value === undefined) && nullable) {
      return {
        passed: true,
        conditionType: 'type-check',
        details: {
          path,
          value,
          actualType,
          expectedType,
          nullable: true,
          passedViaNullable: true,
        },
        evaluatedAt: Date.now(),
      };
    }

    const passed = actualType === expectedType;

    this.log.info('Type-check condition evaluated', { passed, path, actualType, expectedType });

    return {
      passed,
      conditionType: 'type-check',
      details: {
        path,
        value,
        actualType,
        expectedType,
        nullable,
      },
      evaluatedAt: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────
  // Custom Condition
  // ─────────────────────────────────────────────────────────────

  /**
   * Custom condition: evaluates a custom expression or function.
   * Config: {
   *   expression: string,        // JavaScript expression using $data variable
   *   variables?: Record<string, unknown>,  // additional variables
   *   timeout?: number           // evaluation timeout
   * }
   */
  private evaluateCustom(
    config: Record<string, unknown>,
    data: Record<string, unknown>
  ): ConditionResult {
    const expression = config.expression as string;
    const variables = (config.variables as Record<string, unknown>) ?? {};

    // Safe evaluation: support basic comparison and logical expressions
    // In production, would use a sandboxed evaluator
    // For now, we provide template-based evaluation
    let passed = false;
    let evaluationDetail = '';

    try {
      // Resolve variable references in expression: {{path}} → actual value
      const resolved = this.renderTemplate(expression, { ...data, ...variables });

      // Evaluate simple boolean expressions
      if (resolved === 'true') {
        passed = true;
      } else if (resolved === 'false') {
        passed = false;
      } else {
        // Try to evaluate as a comparison
        const comparisonMatch = resolved.match(/^(.+?)\s*(===|!==|==|!=|>=|<=|>|<)\s*(.+)$/);
        if (comparisonMatch) {
          const [, leftStr, op, rightStr] = comparisonMatch;
          const left = this.parseValue(leftStr.trim());
          const right = this.parseValue(rightStr.trim());

          switch (op) {
            case '===': passed = left === right; break;
            case '!==': passed = left !== right; break;
            case '==': passed = left == right; break;
            case '!=': passed = left != right; break;
            case '>=': passed = Number(left) >= Number(right); break;
            case '<=': passed = Number(left) <= Number(right); break;
            case '>': passed = Number(left) > Number(right); break;
            case '<': passed = Number(left) < Number(right); break;
          }
          evaluationDetail = `${leftStr} ${op} ${rightStr} → ${passed}`;
        } else {
          evaluationDetail = `Unable to evaluate expression: "${resolved}"`;
        }
      }
    } catch (error) {
      evaluationDetail = `Evaluation error: ${String(error)}`;
    }

    this.log.info('Custom condition evaluated', { passed, expression });

    return {
      passed,
      conditionType: 'custom',
      details: {
        expression,
        evaluationDetail,
        variables: Object.keys(variables),
      },
      evaluatedAt: Date.now(),
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

  private getTypeOf(value: unknown): string {
    if (value === null) return 'null';
    if (value === undefined) return 'undefined';
    if (Array.isArray(value)) return 'array';
    return typeof value;
  }

  private renderTemplate(template: string, data: Record<string, unknown>): string {
    return template.replace(/\{\{(\w+(?:\.\w+)*)\}\}/g, (match, path) => {
      const value = this.resolvePath(data, path);
      return value !== undefined ? String(value) : match;
    });
  }

  private parseValue(str: string): unknown {
    // Try to parse as number
    if (!isNaN(Number(str))) return Number(str);
    // Try to parse as boolean
    if (str === 'true') return true;
    if (str === 'false') return false;
    // Try to parse as null/undefined
    if (str === 'null') return null;
    if (str === 'undefined') return undefined;
    // Return as string (remove quotes if present)
    if ((str.startsWith('"') && str.endsWith('"')) || (str.startsWith("'") && str.endsWith("'"))) {
      return str.slice(1, -1);
    }
    return str;
  }
}
