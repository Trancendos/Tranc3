/**
 * DebugBot — Debugging & Error Analysis Bot for The Lab
 *
 * Identity:  NID-LAB-DEBUG
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TheLabAI (AID-LAB)
 *
 * Responsibilities:
 *   - Analyse runtime errors and exceptions
 *   - Trace call stacks to root causes
 *   - Identify error patterns and common pitfalls
 *   - Suggest fixes with confidence ratings
 *   - Track debug session state and breakpoints
 */

import { Bot, Logger } from '../../../core/definitions';

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface DebugInput {
  operation: 'ANALYZE';
  code: string;
  language: string;
  filePath: string;
  errorContext: {
    errorType?: string;
    errorMessage?: string;
    stackTrace?: string[];
    line?: number;
    column?: number;
    input?: unknown;
    expectedOutput?: unknown;
    actualOutput?: unknown;
    runtime?: string;
    environment?: Record<string, string>;
  };
}

export interface ErrorPattern {
  id: string;
  name: string;
  category: 'syntax' | 'reference' | 'type' | 'logic' | 'runtime' | 'async' | 'memory' | 'security';
  languages: string[];
  pattern: RegExp;
  description: string;
  commonCause: string;
  suggestedFix: string;
  confidence: number; // 0..1
}

export interface DebugFinding {
  id: string;
  pattern: ErrorPattern;
  location: {
    line: number;
    column: number;
    endLine?: number;
    endColumn?: number;
  };
  matchedText: string;
  analysis: string;
  suggestedFix: string;
  confidence: number;
  severity: 'critical' | 'high' | 'medium' | 'low';
}

export interface StackAnalysis {
  frames: Array<{
    function: string;
    file: string;
    line: number;
    column: number;
    isUserCode: boolean;
    relevance: 'direct' | 'indirect' | 'framework' | 'external';
  }>;
  rootCause: {
    frame: number;
    reasoning: string;
  };
  relatedFrames: number[];
}

export interface DebugResult {
  findings: DebugFinding[];
  stackAnalysis: StackAnalysis | null;
  errorClassification: {
    type: string;
    category: string;
    severity: 'critical' | 'high' | 'medium' | 'low';
    isRecoverable: boolean;
  };
  suggestedActions: Array<{
    description: string;
    priority: number;
    estimatedEffort: 'trivial' | 'simple' | 'moderate' | 'complex';
    autoFixable: boolean;
  }>;
  relatedPatterns: string[];
  debugTips: string[];
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// DebugBot Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class DebugBot extends Bot {
  private readonly log: Logger;
  private readonly patterns: Map<string, ErrorPattern>;

  constructor() {
    const handler = async (input: DebugInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-LAB-DEBUG',
      'Debug',
      handler,
      'Error analysis, stack tracing, and debug suggestion engine'
    );

    this.log = new Logger('DebugBot');
    this.patterns = new Map();
    this.initPatterns();
  }

  private async process(input: DebugInput): Promise<DebugResult> {
    switch (input.operation) {
      case 'ANALYZE':
        return this.analyze(input);
      default:
        throw new Error(`DebugBot: Unknown operation "${(input as any).operation}"`);
    }
  }

  // ───────────────────────────────────────────────────────────────────────────
  // ANALYZE
  // ───────────────────────────────────────────────────────────────────────────

  private analyze(input: DebugInput): DebugResult {
    const { code, language, filePath, errorContext } = input;
    const lines = code.split('\n');

    // Step 1: Match error against known patterns
    const findings = this.matchPatterns(code, lines, language, errorContext);

    // Step 2: Analyse stack trace if provided
    const stackAnalysis = errorContext.stackTrace
      ? this.analyseStackTrace(errorContext.stackTrace, filePath)
      : null;

    // Step 3: Classify the error
    const errorClassification = this.classifyError(errorContext, findings);

    // Step 4: Generate suggested actions
    const suggestedActions = this.generateActions(findings, errorClassification);

    // Step 5: Find related patterns
    const relatedPatterns = this.findRelatedPatterns(findings, language);

    // Step 6: Debug tips
    const debugTips = this.generateDebugTips(errorContext, errorClassification, language);

    const result: DebugResult = {
      findings,
      stackAnalysis,
      errorClassification,
      suggestedActions,
      relatedPatterns,
      debugTips,
      timestamp: Date.now(),
    };

    this.log.info('Debug analysis complete', {
      filePath,
      findingsCount: findings.length,
      severity: errorClassification.severity,
      category: errorClassification.category,
    });

    return result;
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Pattern Matching
  // ───────────────────────────────────────────────────────────────────────────

  private matchPatterns(
    code: string,
    lines: string[],
    language: string,
    errorContext: DebugInput['errorContext']
  ): DebugFinding[] {
    const findings: DebugFinding[] = [];
    let findingIndex = 0;

    for (const [id, pattern] of this.patterns) {
      // Skip patterns that don't apply to this language
      if (pattern.languages.length > 0 && !pattern.languages.includes(language.toLowerCase())) {
        continue;
      }

      for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const match = line.match(pattern.pattern);
        if (match) {
          findings.push({
            id: `DBG-${++findingIndex}`,
            pattern,
            location: {
              line: i + 1,
              column: match.index ? match.index + 1 : 1,
            },
            matchedText: match[0],
            analysis: pattern.description,
            suggestedFix: pattern.suggestedFix,
            confidence: pattern.confidence,
            severity: this.severityFromCategory(pattern.category),
          });
        }
      }
    }

    // Context-aware: if error line is known, boost findings near that line
    if (errorContext.line) {
      for (const finding of findings) {
        const distance = Math.abs(finding.location.line - errorContext.line);
        if (distance <= 3) {
          finding.confidence = Math.min(1, finding.confidence + 0.2);
          finding.severity = this.upgradeSeverity(finding.severity);
        }
      }
    }

    // Sort by confidence descending
    findings.sort((a, b) => b.confidence - a.confidence);

    return findings;
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Stack Trace Analysis
  // ───────────────────────────────────────────────────────────────────────────

  private analyseStackTrace(
    stackTrace: string[],
    primaryFile: string
  ): StackAnalysis {
    const frames: StackAnalysis['frames'] = [];
    let rootCauseIndex = 0;

    for (let i = 0; i < stackTrace.length; i++) {
      const frame = this.parseStackFrame(stackTrace[i]);
      frames.push({
        function: frame.functionName,
        file: frame.file,
        line: frame.line,
        column: frame.column,
        isUserCode: frame.file === primaryFile || frame.file.startsWith('./') || frame.file.startsWith('src/'),
        relevance: this.classifyFrameRelevance(frame, primaryFile),
      });
    }

    // Find the root cause: highest user-code frame or first frame if none
    const userCodeFrame = frames.findIndex((f) => f.isUserCode && f.relevance === 'direct');
    if (userCodeFrame >= 0) {
      rootCauseIndex = userCodeFrame;
    }

    // Find related frames (user code near the root cause)
    const relatedFrames = frames
      .map((f, idx) => idx)
      .filter((idx) => {
        const f = frames[idx];
        return f.isUserCode && idx !== rootCauseIndex;
      });

    return {
      frames,
      rootCause: {
        frame: rootCauseIndex,
        reasoning: frames[rootCauseIndex]?.isUserCode
          ? `Root cause is in user code at ${frames[rootCauseIndex].function}()`
          : 'Root cause appears to be in external/framework code — check the calling code',
      },
      relatedFrames,
    };
  }

  private parseStackFrame(frame: string): {
    functionName: string;
    file: string;
    line: number;
    column: number;
  } {
    // V8-style: "    at functionName (file:line:column)"
    const v8Match = frame.match(/at\s+(.+?)\s+\((.+?):(\d+):(\d+)\)/);
    if (v8Match) {
      return {
        functionName: v8Match[1],
        file: v8Match[2],
        line: parseInt(v8Match[3], 10),
        column: parseInt(v8Match[4], 10),
      };
    }

    // Anonymous: "    at file:line:column"
    const anonMatch = frame.match(/at\s+(.+?):(\d+):(\d+)/);
    if (anonMatch) {
      return {
        functionName: '<anonymous>',
        file: anonMatch[1],
        line: parseInt(anonMatch[2], 10),
        column: parseInt(anonMatch[3], 10),
      };
    }

    return {
      functionName: frame.trim(),
      file: '<unknown>',
      line: 0,
      column: 0,
    };
  }

  private classifyFrameRelevance(
    frame: { functionName: string; file: string },
    primaryFile: string
  ): StackAnalysis['frames'][0]['relevance'] {
    if (frame.file === primaryFile) return 'direct';
    if (frame.file.startsWith('./') || frame.file.startsWith('src/')) return 'indirect';

    const frameworkIndicators = ['node_modules', 'node:internal', 'internal/', 'core-js', 'tslib'];
    if (frameworkIndicators.some((ind) => frame.file.includes(ind))) return 'framework';

    return 'external';
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Error Classification
  // ───────────────────────────────────────────────────────────────────────────

  private classifyError(
    errorContext: DebugInput['errorContext'],
    findings: DebugFinding[]
  ): DebugResult['errorClassification'] {
    const errorType = errorContext.errorType ?? 'Unknown';
    const errorMessage = errorContext.errorMessage ?? '';

    // Determine category from error type name
    let category = 'unknown';
    let severity: DebugResult['errorClassification']['severity'] = 'medium';
    let isRecoverable = true;

    const errorTypeLower = errorType.toLowerCase();
    const messageLower = errorMessage.toLowerCase();

    // Reference errors
    if (errorTypeLower.includes('reference') || messageLower.includes('is not defined')) {
      category = 'reference';
      severity = 'high';
    }
    // Type errors
    else if (errorTypeLower.includes('type') || messageLower.includes('is not a function') || messageLower.includes('cannot read propert')) {
      category = 'type';
      severity = 'high';
    }
    // Syntax errors
    else if (errorTypeLower.includes('syntax') || messageLower.includes('unexpected token')) {
      category = 'syntax';
      severity = 'critical';
      isRecoverable = false;
    }
    // Range errors
    else if (errorTypeLower.includes('range') || messageLower.includes('out of range')) {
      category = 'runtime';
      severity = 'medium';
    }
    // Async errors
    else if (
      messageLower.includes('promise') ||
      messageLower.includes('await') ||
      messageLower.includes('unhandled') ||
      messageLower.includes('rejected')
    ) {
      category = 'async';
      severity = 'high';
    }
    // Memory errors
    else if (messageLower.includes('heap') || messageLower.includes('memory') || messageLower.includes('overflow')) {
      category = 'memory';
      severity = 'critical';
      isRecoverable = false;
    }
    // Security errors
    else if (messageLower.includes('permission') || messageLower.includes('unauthorized') || messageLower.includes('forbidden')) {
      category = 'security';
      severity = 'critical';
    }
    // Logic errors (no runtime crash but wrong results)
    else if (errorTypeLower === 'assertionerror' || messageLower.includes('assertion') || messageLower.includes('expected')) {
      category = 'logic';
      severity = 'medium';
    }

    // Upgrade severity based on findings
    if (findings.some((f) => f.severity === 'critical')) {
      severity = 'critical';
      isRecoverable = false;
    } else if (findings.some((f) => f.severity === 'high') && severity === 'medium') {
      severity = 'high';
    }

    return {
      type: errorType,
      category,
      severity,
      isRecoverable,
    };
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Suggested Actions
  // ───────────────────────────────────────────────────────────────────────────

  private generateActions(
    findings: DebugFinding[],
    classification: DebugResult['errorClassification']
  ): DebugResult['suggestedActions'] {
    const actions: DebugResult['suggestedActions'] = [];

    // Actions from findings
    for (const finding of findings) {
      actions.push({
        description: finding.suggestedFix,
        priority: finding.confidence > 0.8 ? 1 : finding.confidence > 0.5 ? 2 : 3,
        estimatedEffort: this.estimateEffort(finding.pattern.category),
        autoFixable: finding.pattern.category === 'syntax' || finding.pattern.category === 'reference',
      });
    }

    // Category-specific default actions
    switch (classification.category) {
      case 'reference':
        actions.push({
          description: 'Check import statements and ensure the referenced symbol is exported from its module',
          priority: 1,
          estimatedEffort: 'simple',
          autoFixable: false,
        });
        break;
      case 'type':
        actions.push({
          description: 'Add null/undefined checks before accessing properties or calling methods',
          priority: 1,
          estimatedEffort: 'simple',
          autoFixable: false,
        });
        break;
      case 'async':
        actions.push({
          description: 'Ensure all promises have proper .catch() handlers or are wrapped in try/catch with await',
          priority: 1,
          estimatedEffort: 'moderate',
          autoFixable: false,
        });
        break;
      case 'memory':
        actions.push({
          description: 'Review data structures for unbounded growth; add limits or streaming processing',
          priority: 1,
          estimatedEffort: 'complex',
          autoFixable: false,
        });
        break;
      case 'logic':
        actions.push({
          description: 'Add unit tests covering edge cases and verify expected vs actual output with assertions',
          priority: 2,
          estimatedEffort: 'moderate',
          autoFixable: false,
        });
        break;
    }

    // Sort by priority
    actions.sort((a, b) => a.priority - b.priority);

    return actions;
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Related Patterns & Debug Tips
  // ───────────────────────────────────────────────────────────────────────────

  private findRelatedPatterns(findings: DebugFinding[], language: string): string[] {
    const related = new Set<string>();

    for (const finding of findings) {
      // Add patterns from the same category
      for (const [id, pattern] of this.patterns) {
        if (
          pattern.category === finding.pattern.category &&
          pattern.id !== finding.pattern.id
        ) {
          related.add(`${pattern.name} (${pattern.category})`);
        }
      }
    }

    return Array.from(related).slice(0, 10);
  }

  private generateDebugTips(
    errorContext: DebugInput['errorContext'],
    classification: DebugResult['errorClassification'],
    language: string
  ): string[] {
    const tips: string[] = [];

    // General tips
    tips.push('Reproduce the error consistently before attempting a fix');
    tips.push('Check recent changes to the file for potential regressions');

    // Category-specific tips
    switch (classification.category) {
      case 'reference':
        tips.push('Verify the symbol exists in the scope where it is used');
        tips.push('Check for typos in variable names — JavaScript is case-sensitive');
        if (language === 'typescript') {
          tips.push('Run the TypeScript compiler to catch unresolved references at compile time');
        }
        break;
      case 'type':
        tips.push('Use optional chaining (?.) to safely access nested properties');
        tips.push('Add type guards to narrow types before calling methods');
        tips.push('Check if the variable could be null or undefined at runtime');
        break;
      case 'async':
        tips.push('Always handle promise rejections with .catch() or try/catch');
        tips.push('Verify that async functions are properly awaited');
        tips.push('Check for race conditions when multiple async operations share state');
        break;
      case 'memory':
        tips.push('Profile memory usage to identify growing data structures');
        tips.push('Look for event listeners or closures that prevent garbage collection');
        tips.push('Consider using streams or pagination for large datasets');
        break;
      case 'syntax':
        tips.push('Use a linter to catch syntax errors before runtime');
        tips.push('Check for mismatched brackets, parentheses, or quotes');
        break;
      case 'logic':
        tips.push('Write a minimal reproduction case to isolate the issue');
        tips.push('Add logging before and after the suspected logic');
        tips.push('Verify assumptions with assertions or type checks');
        break;
      case 'security':
        tips.push('Never trust user input — validate and sanitize all inputs');
        tips.push('Check file permissions and access controls');
        break;
    }

    // Line-specific tip
    if (errorContext.line) {
      tips.push(`Focus on line ${errorContext.line} — the error originated there`);
    }

    return tips;
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Built-in Error Patterns
  // ───────────────────────────────────────────────────────────────────────────

  private initPatterns(): void {
    const patterns: ErrorPattern[] = [
      {
        id: 'ERR-NULL-ACCESS',
        name: 'Null Property Access',
        category: 'type',
        languages: ['typescript', 'javascript'],
        pattern: /\.(\w+)\s*[=(]/,
        description: 'Potential null/undefined property access without null check',
        commonCause: 'Object may be null or undefined when the property is accessed',
        suggestedFix: 'Add null check: if (obj) { obj.property } or use optional chaining: obj?.property',
        confidence: 0.4,
      },
      {
        id: 'ERR-UNDEFINED-VAR',
        name: 'Undefined Variable Reference',
        category: 'reference',
        languages: ['typescript', 'javascript'],
        pattern: /\b(?!const|let|var|function|class|import|export|return|if|else|for|while|switch|case|break|continue|new|typeof|instanceof|void|this|super|try|catch|finally|throw|async|await|yield|default|true|false|null|undefined)\w+\s*[=();\]]/,
        description: 'Variable used without prior declaration in scope',
        commonCause: 'Variable is not declared or imported before use',
        suggestedFix: 'Declare the variable with const/let/var or add an import statement',
        confidence: 0.3,
      },
      {
        id: 'ERR-ASYNC-AWAIT-MISSING',
        name: 'Missing Await',
        category: 'async',
        languages: ['typescript', 'javascript'],
        pattern: /(?:const|let|var)\s+\w+\s*=\s*\w+\(/,
        description: 'Async function call without await — result may be a Promise instead of the resolved value',
        commonCause: 'Forgetting to await an async function call',
        suggestedFix: 'Add await before the async function call or handle the Promise explicitly',
        confidence: 0.35,
      },
      {
        id: 'ERR-CATCH-EMPTY',
        name: 'Empty Catch Block',
        category: 'logic',
        languages: ['typescript', 'javascript'],
        pattern: /catch\s*\([^)]*\)\s*\{\s*\}/,
        description: 'Empty catch block silently swallows errors',
        commonCause: 'Placeholder error handling that was never implemented',
        suggestedFix: 'Add proper error handling in the catch block or re-throw the error',
        confidence: 0.9,
      },
      {
        id: 'ERR-CONSOLE-EXCEPTION',
        name: 'Console in Exception Path',
        category: 'logic',
        languages: ['typescript', 'javascript'],
        pattern: /catch\s*\([^)]*\)\s*\{[^}]*console\.(log|error|warn)/,
        description: 'Using console.* in catch block instead of proper error handling',
        commonCause: 'Quick debugging left in production code',
        suggestedFix: 'Replace console.* with proper error logging or re-throw',
        confidence: 0.7,
      },
      {
        id: 'ERR-STRICT-EQUALITY',
        name: 'Loose Equality Check',
        category: 'logic',
        languages: ['typescript', 'javascript'],
        pattern: /[^!=]==[^=]|[^!]=\s*[^=]/,
        description: 'Loose equality (==) can cause unexpected type coercion',
        commonCause: 'Using == instead of === for comparison',
        suggestedFix: 'Use strict equality (===) to avoid type coercion surprises',
        confidence: 0.5,
      },
      {
        id: 'ERR-EVAL-USAGE',
        name: 'Eval Usage',
        category: 'security',
        languages: ['typescript', 'javascript'],
        pattern: /\beval\s*\(/,
        description: 'eval() is a security risk and performance concern',
        commonCause: 'Dynamic code execution requirement that could use safer alternatives',
        suggestedFix: 'Replace eval() with Function constructor, JSON.parse, or safer alternatives',
        confidence: 0.95,
      },
      {
        id: 'ERR-JSON-PARSE-UNSAFE',
        name: 'Unsafe JSON Parse',
        category: 'runtime',
        languages: ['typescript', 'javascript'],
        pattern: /JSON\.parse\s*\([^)]+\)(?!\s*\.\s*catch|\s*in\s*try)/,
        description: 'JSON.parse without try/catch can throw on malformed input',
        commonCause: 'Assuming external input is always valid JSON',
        suggestedFix: 'Wrap JSON.parse in a try/catch block to handle malformed input gracefully',
        confidence: 0.6,
      },
      {
        id: 'ERR-UNBOUNDED-RECURSION',
        name: 'Unbounded Recursion',
        category: 'memory',
        languages: ['typescript', 'javascript'],
        pattern: /function\s+(\w+)\s*\([^)]*\)\s*\{[^}]*\1\s*\(/,
        description: 'Recursive function without visible base case in immediate body',
        commonCause: 'Missing or unreachable termination condition',
        suggestedFix: 'Ensure the recursive function has a clear base case that terminates recursion',
        confidence: 0.45,
      },
      {
        id: 'ERR-ARRAY-MUTATION',
        name: 'Array Mutation in Iteration',
        category: 'logic',
        languages: ['typescript', 'javascript'],
        pattern: /\.forEach|\.map|\.filter|\.reduce|for\s*\(/,
        description: 'Potential array mutation during iteration (splice/push inside loop)',
        commonCause: 'Modifying array length while iterating over it',
        suggestedFix: 'Collect mutations and apply after iteration, or iterate over a copy of the array',
        confidence: 0.3,
      },
      {
        id: 'ERR-UNHANDLED-PROMISE',
        name: 'Unhandled Promise',
        category: 'async',
        languages: ['typescript', 'javascript'],
        pattern: /new\s+Promise\s*\(/,
        description: 'Promise creation without visible .catch() or await',
        commonCause: 'Fire-and-forget async operation without error handling',
        suggestedFix: 'Always chain .catch() on promises or await them in try/catch blocks',
        confidence: 0.4,
      },
      {
        id: 'ERR-CAST-WITHOUT-CHECK',
        name: 'Type Cast Without Check',
        category: 'type',
        languages: ['typescript'],
        pattern: /as\s+(?:string|number|boolean|any|unknown)\b/,
        description: 'Type assertion without runtime type check',
        commonCause: 'Assuming the value matches the asserted type without verification',
        suggestedFix: 'Add runtime type check before casting, or use type guards',
        confidence: 0.55,
      },
      {
        id: 'ERR-ANY-TYPE',
        name: 'Any Type Usage',
        category: 'type',
        languages: ['typescript'],
        pattern: /:\s*any\b/,
        description: 'Using "any" type defeats TypeScript type safety',
        commonCause: 'Quick workaround that bypasses type checking',
        suggestedFix: 'Replace "any" with a proper type or "unknown" for safer type narrowing',
        confidence: 0.85,
      },
      {
        id: 'ERR-EVENT-LISTENER-LEAK',
        name: 'Event Listener Leak',
        category: 'memory',
        languages: ['typescript', 'javascript'],
        pattern: /\.addEventListener\s*\(/,
        description: 'Event listener added without corresponding removeEventListener',
        commonCause: 'Forgetting to clean up event listeners when components unmount',
        suggestedFix: 'Store listener references and call removeEventListener in cleanup/dispose methods',
        confidence: 0.5,
      },
      {
        id: 'ERR-SETTIMEOUT-STRING',
        name: 'setTimeout with String',
        category: 'security',
        languages: ['typescript', 'javascript'],
        pattern: /setTimeout\s*\(\s*['"`]/,
        description: 'setTimeout/setInterval with string argument acts like eval',
        commonCause: 'Legacy pattern for delayed code execution',
        suggestedFix: 'Pass a function reference instead of a string to setTimeout/setInterval',
        confidence: 0.95,
      },
    ];

    for (const pattern of patterns) {
      this.patterns.set(pattern.id, pattern);
    }
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Utility Helpers
  // ───────────────────────────────────────────────────────────────────────────

  private severityFromCategory(category: ErrorPattern['category']): DebugFinding['severity'] {
    switch (category) {
      case 'security':
      case 'memory':
        return 'critical';
      case 'syntax':
      case 'reference':
      case 'type':
        return 'high';
      case 'async':
      case 'runtime':
        return 'medium';
      case 'logic':
        return 'low';
      default:
        return 'medium';
    }
  }

  private upgradeSeverity(severity: DebugFinding['severity']): DebugFinding['severity'] {
    switch (severity) {
      case 'low':
        return 'medium';
      case 'medium':
        return 'high';
      case 'high':
        return 'critical';
      case 'critical':
        return 'critical';
    }
  }

  private estimateEffort(category: ErrorPattern['category']): DebugResult['suggestedActions'][0]['estimatedEffort'] {
    switch (category) {
      case 'syntax':
        return 'trivial';
      case 'reference':
      case 'type':
        return 'simple';
      case 'logic':
      case 'async':
        return 'moderate';
      case 'memory':
      case 'security':
      case 'runtime':
        return 'complex';
      default:
        return 'moderate';
    }
  }
}
