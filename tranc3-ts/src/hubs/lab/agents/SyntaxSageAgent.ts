/**
 * SyntaxSageAgent — Code Structure Analysis Agent for The Lab
 *
 * Identity:  SID-LAB-SYNTAXSAGE
 * Tier:      4 (Autonomous Microservice)
 * Parent:    TheLabAI (AID-LAB)
 *
 * Responsibilities:
 *   - Analyse code syntax and structure
 *   - Compute complexity metrics (cyclomatic, cognitive)
 *   - Detect structural patterns and anti-patterns
 *   - Suggest refactoring opportunities
 */

import { Agent, Logger } from '../../../core/definitions';

// ─────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────

export interface SyntaxSageInput {
  code: string;
  language: string;
  operation: 'analyse' | 'metrics' | 'refactor';
}

export interface ComplexityMetrics {
  cyclomaticComplexity: number;
  cognitiveComplexity: number;
  linesOfCode: number;
  linesOfComments: number;
  blankLines: number;
  functionCount: number;
  classCount: number;
  importCount: number;
  maxNestingDepth: number;
  averageFunctionLength: number;
  maintainabilityIndex: number; // 0..100
}

export interface StructureNode {
  type: 'module' | 'class' | 'function' | 'method' | 'interface' | 'enum' | 'variable' | 'import';
  name: string;
  line: number;
  endLine?: number;
  children: StructureNode[];
  modifiers: string[];
  complexity?: number;
}

export interface RefactorSuggestion {
  type: 'extract-function' | 'extract-variable' | 'simplify-condition' | 'replace-magic-number' | 'reduce-nesting' | 'split-class';
  description: string;
  file: string;
  line: number;
  effort: 'low' | 'medium' | 'high';
  impact: 'low' | 'medium' | 'high';
  before: string;
  after: string;
}

export interface SyntaxSageResult {
  operation: string;
  language: string;
  metrics: ComplexityMetrics;
  structure: StructureNode;
  refactorSuggestions: RefactorSuggestion[];
}

// ─────────────────────────────────────────────────────────────
// SyntaxSageAgent Implementation
// ─────────────────────────────────────────────────────────────

export class SyntaxSageAgent extends Agent {
  private readonly log: Logger;

  constructor() {
    super('SID-LAB-SYNTAXSAGE');
    this.log = new Logger('SyntaxSageAgent');
  }

  async perceive(observation: SyntaxSageInput): Promise<{
    code: string;
    language: string;
    operation: string;
    lines: string[];
  }> {
    const lines = observation.code.split('\n');
    this.log.info('Perceived code for analysis', {
      language: observation.language,
      lines: lines.length,
      operation: observation.operation,
    });

    return { ...observation, lines };
  }

  async decide(perceived: Awaited<ReturnType<typeof this.perceive>>): Promise<{
    action: string;
    code: string;
    language: string;
    lines: string[];
  }> {
    this.log.info('Decided on analysis action', { action: perceived.operation });
    return {
      action: perceived.operation,
      code: perceived.code,
      language: perceived.language,
      lines: perceived.lines,
    };
  }

  async act(decision: Awaited<ReturnType<typeof this.decide>>): Promise<SyntaxSageResult> {
    const { action, code, language, lines } = decision;

    // Compute metrics for all operations
    const metrics = this.computeMetrics(code, lines, language);
    const structure = this.parseStructure(code, lines, language);

    let refactorSuggestions: RefactorSuggestion[] = [];

    switch (action) {
      case 'metrics':
        // Focus on metrics only
        break;
      case 'refactor':
        refactorSuggestions = this.suggestRefactors(code, lines, language, structure);
        break;
      default:
        // Full analysis includes refactoring suggestions
        refactorSuggestions = this.suggestRefactors(code, lines, language, structure);
    }

    this.log.info('Analysis complete', {
      operation: action,
      cyclomaticComplexity: metrics.cyclomaticComplexity,
      functionCount: metrics.functionCount,
      refactorSuggestions: refactorSuggestions.length,
    });

    return {
      operation: action,
      language,
      metrics,
      structure,
      refactorSuggestions,
    };
  }

  // ─────────────────────────────────────────────────────────────
  // Complexity Metrics
  // ─────────────────────────────────────────────────────────────

  private computeMetrics(code: string, lines: string[], language: string): ComplexityMetrics {
    const nonBlankLines = lines.filter((l) => l.trim().length > 0);
    const commentLines = lines.filter((l) => {
      const trimmed = l.trim();
      return trimmed.startsWith('//') || trimmed.startsWith('/*') || trimmed.startsWith('*') || trimmed.startsWith('#');
    });
    const blankLines = lines.length - nonBlankLines.length;

    // Function detection
    const functionPattern = language === 'python'
      ? /^\s*def\s+\w+/
      : /(?:export\s+)?(?:async\s+)?(?:function\s+\w+|(?:const|let|var)\s+\w+\s*=\s*(?:async\s+)?(?:\([^)]*\)|[^=])\s*=>)/;
    const functionCount = lines.filter((l) => functionPattern.test(l)).length;

    // Class detection
    const classPattern = /^\s*(?:export\s+)?(?:abstract\s+)?class\s+\w+/;
    const classCount = lines.filter((l) => classPattern.test(l)).length;

    // Import detection
    const importPattern = /^\s*(?:import\s+|const\s+\w+\s*=\s*require\()/;
    const importCount = lines.filter((l) => importPattern.test(l)).length;

    // Cyclomatic complexity: count decision points
    const decisionPatterns = /\b(if|else\s+if|case|for|while|catch|&&|\|\||\.?\?)\b/g;
    const decisionMatches = code.match(decisionPatterns);
    const cyclomaticComplexity = (decisionMatches?.length ?? 0) + 1;

    // Cognitive complexity (simplified)
    const cognitiveComplexity = this.computeCognitiveComplexity(lines);

    // Max nesting depth
    const maxNestingDepth = this.computeMaxNesting(lines);

    // Average function length
    const averageFunctionLength = functionCount > 0
      ? Math.round(nonBlankLines.length / functionCount)
      : nonBlankLines.length;

    // Maintainability index (simplified Microsoft formula)
    const volume = nonBlankLines.length * Math.log2(Math.max(cyclomaticComplexity, 1));
    const maintainabilityIndex = Math.max(0, Math.min(100,
      171 - 5.2 * Math.log(Math.max(volume, 1)) - 0.23 * cyclomaticComplexity - 16.2 * Math.log(Math.max(nonBlankLines.length, 1))
    ));

    return {
      cyclomaticComplexity,
      cognitiveComplexity,
      linesOfCode: nonBlankLines.length - commentLines.length,
      linesOfComments: commentLines.length,
      blankLines,
      functionCount,
      classCount,
      importCount,
      maxNestingDepth,
      averageFunctionLength,
      maintainabilityIndex: Math.round(maintainabilityIndex),
    };
  }

  private computeCognitiveComplexity(lines: string[]): number {
    let complexity = 0;
    let nestingLevel = 0;

    for (const line of lines) {
      const trimmed = line.trim();

      // Increase nesting
      if (/\b(if|for|while|switch|try)\b/.test(trimmed)) {
        complexity += 1 + nestingLevel; // structural + nesting bonus
      }

      // Else is a structural increment but no nesting bonus
      if (/\belse\s+if\b/.test(trimmed)) {
        complexity += 1;
      } else if (/\belse\b/.test(trimmed)) {
        complexity += 1;
      }

      // Logical operators
      const logicalOps = trimmed.match(/&&|\|\|/g);
      if (logicalOps) {
        complexity += logicalOps.length;
      }

      // Track nesting
      nestingLevel += (line.match(/\{/g) || []).length - (line.match(/\}/g) || []).length;
      nestingLevel = Math.max(0, nestingLevel);
    }

    return complexity;
  }

  private computeMaxNesting(lines: string[]): number {
    let maxDepth = 0;
    let currentDepth = 0;

    for (const line of lines) {
      currentDepth += (line.match(/\{/g) || []).length - (line.match(/\}/g) || []).length;
      currentDepth = Math.max(0, currentDepth);
      maxDepth = Math.max(maxDepth, currentDepth);
    }

    return maxDepth;
  }

  // ─────────────────────────────────────────────────────────────
  // Structure Parsing
  // ─────────────────────────────────────────────────────────────

  private parseStructure(code: string, lines: string[], language: string): StructureNode {
    const root: StructureNode = {
      type: 'module',
      name: 'root',
      line: 1,
      endLine: lines.length,
      children: [],
      modifiers: [],
    };

    let currentClass: StructureNode | null = null;

    for (let i = 0; i < lines.length; i++) {
      const trimmed = lines[i].trim();

      // Import
      const importMatch = trimmed.match(/^import\s+(?:.*?\s+from\s+)?['"](.+?)['"]/);
      if (importMatch) {
        root.children.push({
          type: 'import',
          name: importMatch[1],
          line: i + 1,
          modifiers: [],
          children: [],
        });
        continue;
      }

      // Class
      const classMatch = trimmed.match(/^(?:export\s+)?(?:abstract\s+)?class\s+(\w+)/);
      if (classMatch) {
        const modifiers: string[] = [];
        if (trimmed.includes('export')) modifiers.push('export');
        if (trimmed.includes('abstract')) modifiers.push('abstract');

        currentClass = {
          type: 'class',
          name: classMatch[1],
          line: i + 1,
          modifiers,
          children: [],
        };
        root.children.push(currentClass);
        continue;
      }

      // Interface
      const interfaceMatch = trimmed.match(/^(?:export\s+)?interface\s+(\w+)/);
      if (interfaceMatch) {
        root.children.push({
          type: 'interface',
          name: interfaceMatch[1],
          line: i + 1,
          modifiers: trimmed.includes('export') ? ['export'] : [],
          children: [],
        });
        continue;
      }

      // Enum
      const enumMatch = trimmed.match(/^(?:export\s+)?enum\s+(\w+)/);
      if (enumMatch) {
        root.children.push({
          type: 'enum',
          name: enumMatch[1],
          line: i + 1,
          modifiers: trimmed.includes('export') ? ['export'] : [],
          children: [],
        });
        continue;
      }

      // Function (top-level or method)
      const funcMatch = trimmed.match(/^(?:export\s+)?(?:async\s+)?function\s+(\w+)/);
      if (funcMatch) {
        const funcNode: StructureNode = {
          type: currentClass ? 'method' : 'function',
          name: funcMatch[1],
          line: i + 1,
          modifiers: trimmed.includes('export') ? ['export'] : [],
          children: [],
        };

        if (currentClass) {
          currentClass.children.push(funcNode);
        } else {
          root.children.push(funcNode);
        }
        continue;
      }

      // Arrow function / const function
      const arrowMatch = trimmed.match(/^(?:export\s+)?(?:const|let)\s+(\w+)\s*[=:]\s*(?:async\s*)?(?:\([^)]*\)|[^=])\s*=>/);
      if (arrowMatch) {
        const funcNode: StructureNode = {
          type: currentClass ? 'method' : 'function',
          name: arrowMatch[1],
          line: i + 1,
          modifiers: trimmed.includes('export') ? ['export'] : [],
          children: [],
        };

        if (currentClass) {
          currentClass.children.push(funcNode);
        } else {
          root.children.push(funcNode);
        }
        continue;
      }

      // Variable
      const varMatch = trimmed.match(/^(?:export\s+)?(?:const|let|var)\s+(\w+)/);
      if (varMatch && !trimmed.includes('=>') && !trimmed.includes('function')) {
        const varNode: StructureNode = {
          type: 'variable',
          name: varMatch[1],
          line: i + 1,
          modifiers: [],
          children: [],
        };

        if (currentClass) {
          currentClass.children.push(varNode);
        } else {
          root.children.push(varNode);
        }
      }
    }

    return root;
  }

  // ─────────────────────────────────────────────────────────────
  // Refactoring Suggestions
  // ─────────────────────────────────────────────────────────────

  private suggestRefactors(
    code: string,
    lines: string[],
    language: string,
    structure: StructureNode
  ): RefactorSuggestion[] {
    const suggestions: RefactorSuggestion[] = [];

    // Check for deep nesting
    for (let i = 0; i < lines.length; i++) {
      const indent = lines[i].search(/\S/);
      if (indent >= 12) { // 4 levels of 3-space indent
        suggestions.push({
          type: 'reduce-nesting',
          description: 'Deeply nested code — consider early returns or guard clauses',
          file: '',
          line: i + 1,
          effort: 'medium',
          impact: 'high',
          before: lines[i].trim().slice(0, 80),
          after: '// Refactor: use early return to reduce nesting',
        });
        break; // only suggest once
      }
    }

    // Check for complex conditions
    for (let i = 0; i < lines.length; i++) {
      const trimmed = lines[i].trim();
      if (trimmed.startsWith('if') && (trimmed.match(/&&|\|\|/g) || []).length >= 3) {
        suggestions.push({
          type: 'simplify-condition',
          description: 'Complex boolean expression — extract to a named variable',
          file: '',
          line: i + 1,
          effort: 'low',
          impact: 'medium',
          before: trimmed.slice(0, 80),
          after: `const is${this.guessConditionName(trimmed)} = ${trimmed.slice(3, Math.min(trimmed.length - 1, 80))};`,
        });
      }
    }

    // Check for magic numbers
    const magicNumberPattern = /(?:^|[=(:,]\s*)(\d{2,})(?:\.\d+)?(?!\s*[;:])/;
    for (let i = 0; i < lines.length; i++) {
      const trimmed = lines[i].trim();
      if (magicNumberPattern.test(trimmed) && !trimmed.includes('const ') && !trimmed.includes('MAX_') && !trimmed.includes('MIN_')) {
        const match = trimmed.match(magicNumberPattern);
        if (match) {
          suggestions.push({
            type: 'replace-magic-number',
            description: `Magic number ${match[1]} — extract to a named constant`,
            file: '',
            line: i + 1,
            effort: 'low',
            impact: 'low',
            before: trimmed.slice(0, 80),
            after: `const CONSTANT_NAME = ${match[1]}; // give a meaningful name`,
          });
        }
      }
    }

    // Check for large classes
    for (const child of structure.children) {
      if (child.type === 'class' && child.children.length > 15) {
        suggestions.push({
          type: 'split-class',
          description: `Class "${child.name}" has ${child.children.length} members — consider splitting responsibilities`,
          file: '',
          line: child.line,
          effort: 'high',
          impact: 'high',
          before: `class ${child.name} { /* ${child.children.length} members */ }`,
          after: `// Split ${child.name} into focused classes with single responsibilities`,
        });
      }
    }

    return suggestions;
  }

  private guessConditionName(condition: string): string {
    if (condition.includes('length')) return 'HasLength';
    if (condition.includes('type')) return 'IsType';
    if (condition.includes('status')) return 'HasStatus';
    if (condition.includes('null') || condition.includes('undefined')) return 'IsDefined';
    if (condition.includes('empty')) return 'IsNotEmpty';
    return 'IsConditionMet';
  }
}
