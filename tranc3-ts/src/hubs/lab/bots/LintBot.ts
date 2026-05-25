/**
 * LintBot — Static Analysis Bot for The Lab
 *
 * Identity:  NID-LAB-LINT
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TheLabAI (AID-LAB)
 *
 * Responsibilities:
 *   - Perform static analysis on code
 *   - Check against configurable lint rules
 *   - Report violations with severity and suggestions
 *   - Support auto-fix for safe transformations
 */

import { Bot, Logger } from '../../../core/definitions';

// ─────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────

export interface LintAnalyzeInput {
  operation: 'ANALYZE';
  code: string;
  language: string;
  filePath: string;
  rules: Record<string, unknown>;
}

export type LintInput = LintAnalyzeInput;

export interface LintViolation {
  ruleId: string;
  severity: 'error' | 'warning' | 'info';
  message: string;
  line: number;
  column: number;
  endLine?: number;
  endColumn?: number;
  fixable: boolean;
  fix?: {
    range: [number, number];
    text: string;
  };
}

export interface LintResult {
  filePath: string;
  language: string;
  violations: LintViolation[];
  summary: {
    errors: number;
    warnings: number;
    info: number;
    fixable: number;
  };
  rulesApplied: number;
  analysisTime: number;
}

// ─────────────────────────────────────────────────────────────
// Built-in Lint Rules
// ─────────────────────────────────────────────────────────────

interface LintRule {
  id: string;
  description: string;
  severity: 'error' | 'warning' | 'info';
  languages: string[];
  check: (code: string, lines: string[]) => LintViolation[];
  autoFix?: (code: string) => string;
}

// ─────────────────────────────────────────────────────────────
// LintBot Implementation
// ─────────────────────────────────────────────────────────────

export class LintBot extends Bot {
  private readonly log: Logger;
  private readonly rules: LintRule[];

  constructor() {
    const handler = async (input: LintInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-LAB-LINT',
      'Lint',
      handler,
      'Static analysis and lint checking with auto-fix support'
    );

    this.log = new Logger('LintBot');
    this.rules = this.buildRules();
  }

  private async process(input: LintInput): Promise<LintResult> {
    switch (input.operation) {
      case 'ANALYZE':
        return this.analyze(input);
      default:
        throw new Error(`LintBot: Unknown operation "${(input as any).operation}"`);
    }
  }

  // ─────────────────────────────────────────────────────────────
  // ANALYZE
  // ─────────────────────────────────────────────────────────────

  private analyze(input: LintAnalyzeInput): LintResult {
    const startTime = Date.now();
    const { code, language, filePath, rules: customRules } = input;
    const lines = code.split('\n');

    const allViolations: LintViolation[] = [];
    let rulesApplied = 0;

    // Determine which rules to apply
    const disabledRules = (customRules.disabled as string[]) ?? [];
    const severityOverrides = (customRules.severity as Record<string, 'error' | 'warning' | 'info'>) ?? {};

    for (const rule of this.rules) {
      // Skip disabled rules
      if (disabledRules.includes(rule.id)) continue;

      // Skip rules for other languages
      if (rule.languages.length > 0 && !rule.languages.includes(language.toLowerCase())) continue;

      rulesApplied++;
      const violations = rule.check(code, lines);

      // Apply severity overrides
      for (const violation of violations) {
        if (severityOverrides[rule.id]) {
          violation.severity = severityOverrides[rule.id];
        }
        violation.ruleId = rule.id;
      }

      allViolations.push(...violations);
    }

    // Sort by line number
    allViolations.sort((a, b) => a.line - b.line || a.column - b.column);

    const summary = {
      errors: allViolations.filter((v) => v.severity === 'error').length,
      warnings: allViolations.filter((v) => v.severity === 'warning').length,
      info: allViolations.filter((v) => v.severity === 'info').length,
      fixable: allViolations.filter((v) => v.fixable).length,
    };

    const analysisTime = Date.now() - startTime;

    this.log.info('Lint analysis complete', {
      filePath,
      violations: allViolations.length,
      errors: summary.errors,
      warnings: summary.warnings,
      analysisTime,
    });

    return {
      filePath,
      language,
      violations: allViolations,
      summary,
      rulesApplied,
      analysisTime,
    };
  }

  // ─────────────────────────────────────────────────────────────
  // Built-in Rules
  // ─────────────────────────────────────────────────────────────

  private buildRules(): LintRule[] {
    return [
      // No var declarations
      {
        id: 'no-var',
        description: 'Disallow var declarations',
        severity: 'warning',
        languages: ['javascript', 'typescript'],
        check: (code, lines) => {
          const violations: LintViolation[] = [];
          for (let i = 0; i < lines.length; i++) {
            const match = lines[i].match(/\bvar\s+(\w+)/);
            if (match) {
              violations.push({
                ruleId: 'no-var',
                severity: 'warning',
                message: `Unexpected var, use let or const instead`,
                line: i + 1,
                column: lines[i].indexOf('var') + 1,
                fixable: true,
                fix: {
                  range: [lines[i].indexOf('var'), lines[i].indexOf('var') + 3],
                  text: 'const',
                },
              });
            }
          }
          return violations;
        },
        autoFix: (code) => code.replace(/\bvar\b/g, 'const'),
      },

      // No console statements
      {
        id: 'no-console',
        description: 'Disallow console statements',
        severity: 'warning',
        languages: ['javascript', 'typescript'],
        check: (code, lines) => {
          const violations: LintViolation[] = [];
          for (let i = 0; i < lines.length; i++) {
            const match = lines[i].match(/console\.\w+\(/);
            if (match) {
              violations.push({
                ruleId: 'no-console',
                severity: 'warning',
                message: 'Unexpected console statement',
                line: i + 1,
                column: lines[i].indexOf('console') + 1,
                fixable: true,
              });
            }
          }
          return violations;
        },
      },

      // Require semicolons
      {
        id: 'semi',
        description: 'Require semicolons',
        severity: 'error',
        languages: ['javascript', 'typescript'],
        check: (code, lines) => {
          const violations: LintViolation[] = [];
          for (let i = 0; i < lines.length; i++) {
            const trimmed = lines[i].trimEnd();
            if (trimmed.length > 0 &&
                !trimmed.endsWith(';') &&
                !trimmed.endsWith('{') &&
                !trimmed.endsWith('}') &&
                !trimmed.endsWith(',') &&
                !trimmed.endsWith('(') &&
                !trimmed.endsWith('\\') &&
                !trimmed.startsWith('//') &&
                !trimmed.startsWith('*') &&
                !trimmed.startsWith('import') &&
                !trimmed.includes('=>') &&
                !/^(if|else|for|while|switch|try|catch|finally|class|function|interface|enum)\b/.test(trimmed)) {
              violations.push({
                ruleId: 'semi',
                severity: 'error',
                message: 'Missing semicolon',
                line: i + 1,
                column: trimmed.length + 1,
                fixable: true,
                fix: {
                  range: [0, 0], // simplified
                  text: ';',
                },
              });
            }
          }
          return violations;
        },
      },

      // No unused variables (simplified)
      {
        id: 'no-unused-vars',
        description: 'Disallow unused variables',
        severity: 'warning',
        languages: ['javascript', 'typescript'],
        check: (code, lines) => {
          const violations: LintViolation[] = [];
          const declaredVars = new Map<string, { line: number; column: number }>();

          // Find all variable declarations
          for (let i = 0; i < lines.length; i++) {
            const matches = lines[i].matchAll(/(?:const|let|var)\s+(\w+)/g);
            for (const match of matches) {
              const varName = match[1];
              // Skip common patterns that may appear unused
              if (['_', 'exports', 'module'].includes(varName)) continue;
              declaredVars.set(varName, {
                line: i + 1,
                column: lines[i].indexOf(varName) + 1,
              });
            }
          }

          // Check if each declared variable is used elsewhere
          for (const [varName, location] of declaredVars) {
            const usagePattern = new RegExp(`\\b${varName}\\b`, 'g');
            const matches = code.match(usagePattern);
            // If only appears once (declaration only), it's unused
            // Subtract 1 for the declaration itself
            const useCount = (matches?.length ?? 0) - 1;

            // Check for destructuring, exports, etc.
            const isExported = code.includes(`export { ${varName} }`) ||
                              code.includes(`export default ${varName}`);
            const isDestructured = code.includes(`{ ${varName} }`) && code.includes('return');

            if (useCount <= 0 && !isExported && !isDestructured) {
              violations.push({
                ruleId: 'no-unused-vars',
                severity: 'warning',
                message: `'${varName}' is defined but never used`,
                line: location.line,
                column: location.column,
                fixable: false,
              });
            }
          }

          return violations;
        },
      },

      // Max line length
      {
        id: 'max-len',
        description: 'Enforce maximum line length',
        severity: 'info',
        languages: [],
        check: (code, lines) => {
          const violations: LintViolation[] = [];
          const maxLength = 120;

          for (let i = 0; i < lines.length; i++) {
            if (lines[i].length > maxLength) {
              violations.push({
                ruleId: 'max-len',
                severity: 'info',
                message: `Line exceeds maximum length of ${maxLength} (${lines[i].length} characters)`,
                line: i + 1,
                column: maxLength + 1,
                fixable: false,
              });
            }
          }
          return violations;
        },
      },

      // No any type
      {
        id: 'no-explicit-any',
        description: 'Disallow the any type',
        severity: 'warning',
        languages: ['typescript'],
        check: (code, lines) => {
          const violations: LintViolation[] = [];
          for (let i = 0; i < lines.length; i++) {
            if (/:\s*any\b/.test(lines[i])) {
              violations.push({
                ruleId: 'no-explicit-any',
                severity: 'warning',
                message: "Unexpected 'any'. Specify a different type",
                line: i + 1,
                column: lines[i].indexOf(': any') + 1,
                fixable: false,
              });
            }
          }
          return violations;
        },
      },

      // Prefer const
      {
        id: 'prefer-const',
        description: 'Prefer const over let for variables that are not reassigned',
        severity: 'info',
        languages: ['javascript', 'typescript'],
        check: (code, lines) => {
          const violations: LintViolation[] = [];
          const letVars = new Map<string, number>();

          for (let i = 0; i < lines.length; i++) {
            const match = lines[i].match(/\blet\s+(\w+)/);
            if (match) {
              letVars.set(match[1], i + 1);
            }
          }

          // Simple heuristic: if a let variable never appears on the left of an assignment after declaration
          for (const [varName, line] of letVars) {
            const reassigned = code.match(new RegExp(`\\b${varName}\\s*=[^=]`, 'g'));
            // Only the declaration counts as one, additional = assignment means reassignment
            if (!reassigned || reassigned.length <= 1) {
              violations.push({
                ruleId: 'prefer-const',
                severity: 'info',
                message: `'${varName}' is never reassigned. Use 'const' instead`,
                line,
                column: 1,
                fixable: true,
              });
            }
          }

          return violations;
        },
      },

      // No trailing whitespace
      {
        id: 'no-trailing-spaces',
        description: 'Disallow trailing whitespace',
        severity: 'info',
        languages: [],
        check: (code, lines) => {
          const violations: LintViolation[] = [];
          for (let i = 0; i < lines.length; i++) {
            if (lines[i] !== lines[i].trimEnd() && lines[i].trimEnd().length > 0) {
              violations.push({
                ruleId: 'no-trailing-spaces',
                severity: 'info',
                message: 'Trailing whitespace not allowed',
                line: i + 1,
                column: lines[i].trimEnd().length + 1,
                fixable: true,
              });
            }
          }
          return violations;
        },
        autoFix: (code) => code.replace(/[ \t]+$/gm, ''),
      },

      // No duplicate imports
      {
        id: 'no-duplicate-imports',
        description: 'Disallow duplicate import statements',
        severity: 'warning',
        languages: ['javascript', 'typescript'],
        check: (code, lines) => {
          const violations: LintViolation[] = [];
          const imports = new Map<string, number>();

          for (let i = 0; i < lines.length; i++) {
            const match = lines[i].match(/from\s+['"](.+?)['"]/);
            if (match) {
              const source = match[1];
              if (imports.has(source)) {
                violations.push({
                  ruleId: 'no-duplicate-imports',
                  severity: 'warning',
                  message: `'${source}' imported multiple times`,
                  line: i + 1,
                  column: lines[i].indexOf(source) + 1,
                  fixable: true,
                });
              }
              imports.set(source, i + 1);
            }
          }
          return violations;
        },
      },
    ];
  }
}
