/**
 * HoundsAgent — Issue Sniffing Agent for The Lab
 *
 * Identity:  SID-LAB-HOUNDS
 * Tier:      4 (Autonomous Microservice)
 * Parent:    TheLabAI (AID-LAB)
 *
 * Responsibilities:
 *   - Sniff out code issues (bugs, smells, anti-patterns)
 *   - Track issues across multiple files
 *   - Prioritise findings by severity and impact
 *   - Detect code smell patterns and suggest improvements
 */

import { Agent, Logger } from '../../../core/definitions';

// ─────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────

export interface HoundsInput {
  files: Array<{
    path: string;
    language: string;
    content: string;
  }>;
  operation: 'sniff' | 'prioritise' | 'track';
}

export interface IssueScent {
  id: string;
  type: 'bug' | 'smell' | 'anti-pattern' | 'security' | 'performance' | 'style';
  severity: 'critical' | 'high' | 'medium' | 'low';
  file: string;
  line: number;
  description: string;
  suggestion: string;
  confidence: number; // 0..1
  pattern: string; // the code pattern that triggered this
}

export interface HoundsResult {
  operation: string;
  totalFiles: number;
  issues: IssueScent[];
  summary: Record<IssueScent['type'], number>;
  priorityOrder: IssueScent[]; // sorted by severity + confidence
}

// ─────────────────────────────────────────────────────────────
// Code Smell & Bug Patterns
// ─────────────────────────────────────────────────────────────

interface SniffPattern {
  name: string;
  type: IssueScent['type'];
  severity: IssueScent['severity'];
  pattern: RegExp;
  description: string;
  suggestion: string;
  languages: string[]; // empty = all
}

const SNIFF_PATTERNS: SniffPattern[] = [
  // Bug patterns
  {
    name: 'assignment-in-conditional',
    type: 'bug',
    severity: 'high',
    pattern: /if\s*\([^)]*[^=!<>]=[^=][^)]*\)/g,
    description: 'Assignment in conditional — likely intended comparison (==)',
    suggestion: 'Use === for comparison instead of = for assignment',
    languages: ['javascript', 'typescript', 'c', 'cpp', 'java'],
  },
  {
    name: 'empty-catch',
    type: 'bug',
    severity: 'high',
    pattern: /catch\s*\([^)]*\)\s*\{\s*\}/g,
    description: 'Empty catch block — swallowed error',
    suggestion: 'Handle the error or at least log it',
    languages: ['javascript', 'typescript', 'java', 'csharp'],
  },
  {
    name: 'console-log-leftover',
    type: 'style',
    severity: 'low',
    pattern: /console\.(log|debug|info|warn|error)\(/g,
    description: 'Console statement left in code',
    suggestion: 'Remove console statements before production',
    languages: ['javascript', 'typescript'],
  },
  {
    name: 'any-type',
    type: 'anti-pattern',
    severity: 'medium',
    pattern: /:\s*any\b/g,
    description: 'Usage of `any` type defeats type safety',
    suggestion: 'Replace with a specific type or unknown',
    languages: ['typescript'],
  },
  {
    name: 'todo-fixme',
    type: 'smell',
    severity: 'low',
    pattern: /(?:TODO|FIXME|HACK|XXX)\b/gi,
    description: 'Unresolved TODO/FIXME comment',
    suggestion: 'Resolve the TODO or create an issue to track it',
    languages: [],
  },
  {
    name: 'nested-callbacks',
    type: 'smell',
    severity: 'medium',
    pattern: /\)\s*\{\s*\n\s*(?:function|\(|async)/g,
    description: 'Deeply nested callbacks detected — callback hell',
    suggestion: 'Refactor to use async/await or Promises',
    languages: ['javascript', 'typescript'],
  },
  {
    name: 'hardcoded-secret',
    type: 'security',
    severity: 'critical',
    pattern: /(?:password|secret|api[_-]?key|token|credential)\s*[:=]\s*['"][^'"]{8,}['"]/gi,
    description: 'Hardcoded secret or credential',
    suggestion: 'Move secrets to environment variables or secret manager',
    languages: [],
  },
  {
    name: 'sql-concat',
    type: 'security',
    severity: 'critical',
    pattern: /(?:SELECT|INSERT|UPDATE|DELETE|DROP)\s+.*\+\s*(?:req|params|query|body)/gi,
    description: 'SQL injection via string concatenation',
    suggestion: 'Use parameterised queries',
    languages: ['javascript', 'typescript', 'python', 'java'],
  },
  {
    name: 'deep-nesting',
    type: 'smell',
    severity: 'medium',
    pattern: /\n(\s{12,})\S/g,
    description: 'Deeply nested code (4+ levels)',
    suggestion: 'Extract nested logic into separate functions',
    languages: [],
  },
  {
    name: 'magic-number',
    type: 'smell',
    severity: 'low',
    pattern: /(?:^|[=\(\[,]\s*)(\d{2,})(?:\.\d+)?[^:\w]/gm,
    description: 'Magic number without named constant',
    suggestion: 'Extract to a named constant for readability',
    languages: [],
  },
  {
    name: 'long-function',
    type: 'smell',
    severity: 'medium',
    pattern: null as any, // handled specially
    description: 'Function exceeds 50 lines',
    suggestion: 'Break into smaller, focused functions',
    languages: [],
  },
  {
    name: 'large-file',
    type: 'smell',
    severity: 'low',
    pattern: null as any, // handled specially
    description: 'File exceeds 300 lines',
    suggestion: 'Consider splitting into multiple modules',
    languages: [],
  },
  {
    name: 'var-declaration',
    type: 'anti-pattern',
    severity: 'medium',
    pattern: /\bvar\s+\w+/g,
    description: 'var declaration — use let or const instead',
    suggestion: 'Replace var with const (preferred) or let',
    languages: ['javascript', 'typescript'],
  },
  {
    name: 'equality-check',
    type: 'bug',
    severity: 'medium',
    pattern: /[^!=]==[^=]/g,
    description: 'Loose equality check (==) — use strict (===)',
    suggestion: 'Use === for strict equality comparison',
    languages: ['javascript', 'typescript'],
  },
  {
    name: 'eval-usage',
    type: 'security',
    severity: 'critical',
    pattern: /\beval\s*\(/g,
    description: 'Usage of eval() — code injection risk',
    suggestion: 'Avoid eval(); use safer alternatives',
    languages: ['javascript', 'typescript'],
  },
];

// ─────────────────────────────────────────────────────────────
// HoundsAgent Implementation
// ─────────────────────────────────────────────────────────────

export class HoundsAgent extends Agent {
  private readonly log: Logger;
  private issueHistory: Map<string, IssueScent[]>;

  constructor() {
    super('SID-LAB-HOUNDS');
    this.log = new Logger('HoundsAgent');
    this.issueHistory = new Map();
  }

  async perceive(observation: HoundsInput): Promise<{
    files: HoundsInput['files'];
    operation: string;
  }> {
    this.log.info('Perceived code for sniffing', {
      fileCount: observation.files.length,
      operation: observation.operation,
    });

    return { files: observation.files, operation: observation.operation };
  }

  async decide(perceived: Awaited<ReturnType<typeof this.perceive>>): Promise<{
    action: string;
    files: HoundsInput['files'];
  }> {
    this.log.info('Decided on sniffing action', { action: perceived.operation });
    return { action: perceived.operation, files: perceived.files };
  }

  async act(decision: Awaited<ReturnType<typeof this.decide>>): Promise<HoundsResult> {
    const { action, files } = decision;

    switch (action) {
      case 'prioritise':
        return this.prioritiseIssues(files);
      case 'track':
        return this.trackIssues(files);
      default:
        return this.sniffFiles(files);
    }
  }

  // ─────────────────────────────────────────────────────────────
  // Sniff Files
  // ─────────────────────────────────────────────────────────────

  private sniffFiles(files: HoundsInput['files']): HoundsResult {
    const allIssues: IssueScent[] = [];

    for (const file of files) {
      const lines = file.content.split('\n');
      const fileIssues = this.sniffFile(file, lines);
      allIssues.push(...fileIssues);
    }

    // Build summary
    const summary = this.buildSummary(allIssues);

    // Sort by priority
    const priorityOrder = this.sortByPriority(allIssues);

    // Store in history
    for (const file of files) {
      const fileIssues = allIssues.filter((i) => i.file === file.path);
      this.issueHistory.set(file.path, fileIssues);
    }

    this.log.info('Sniff complete', {
      totalFiles: files.length,
      issuesFound: allIssues.length,
      critical: summary.security ?? 0,
    });

    return {
      operation: 'sniff',
      totalFiles: files.length,
      issues: allIssues,
      summary,
      priorityOrder,
    };
  }

  private sniffFile(
    file: HoundsInput['files'][0],
    lines: string[]
  ): IssueScent[] {
    const issues: IssueScent[] = [];
    const lang = file.language.toLowerCase();

    // Pattern-based sniffing
    for (const pattern of SNIFF_PATTERNS) {
      // Skip if language doesn't match
      if (pattern.languages.length > 0 && !pattern.languages.includes(lang)) continue;
      if (!pattern.pattern) continue; // special patterns handled separately

      const content = file.content;
      let match: RegExpExecArray | null;

      // Reset regex state
      const regex = new RegExp(pattern.pattern.source, pattern.pattern.flags);
      while ((match = regex.exec(content)) !== null) {
        const line = this.getLineNumber(content, match.index);
        const matchedText = match[0].slice(0, 100); // truncate for storage

        issues.push({
          id: `ISS-${Date.now()}-${issues.length}`,
          type: pattern.type,
          severity: pattern.severity,
          file: file.path,
          line,
          description: pattern.description,
          suggestion: pattern.suggestion,
          confidence: 0.85, // pattern-based confidence
          pattern: matchedText,
        });
      }
    }

    // Structural checks
    // Long function detection
    this.detectLongFunctions(file, lines, issues);

    // Large file detection
    if (lines.length > 300) {
      issues.push({
        id: `ISS-${Date.now()}-${issues.length}`,
        type: 'smell',
        severity: 'low',
        file: file.path,
        line: 1,
        description: `Large file: ${lines.length} lines (threshold: 300)`,
        suggestion: 'Consider splitting into multiple modules',
        confidence: 0.95,
        pattern: `${lines.length} lines`,
      });
    }

    // Duplicate code detection (simple: repeated lines)
    this.detectDuplicateLines(file, lines, issues);

    return issues;
  }

  private detectLongFunctions(
    file: HoundsInput['files'][0],
    lines: string[],
    issues: IssueScent[]
  ): void {
    let functionStart = -1;
    let functionIndent = 0;
    let braceDepth = 0;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const indent = line.search(/\S/);
      const trimmed = line.trim();

      // Detect function start
      if (/^(export\s+)?(async\s+)?(function\s+\w+|const\s+\w+\s*=\s*(?:async\s+)?\(|\w+\s*\([^)]*\)\s*\{)/.test(trimmed)) {
        functionStart = i;
        functionIndent = indent >= 0 ? indent : 0;
        braceDepth = (trimmed.match(/\{/g) || []).length - (trimmed.match(/\}/g) || []).length;
        continue;
      }

      // Track brace depth
      if (functionStart >= 0) {
        braceDepth += (line.match(/\{/g) || []).length - (line.match(/\}/g) || []).length;

        if (braceDepth <= 0) {
          const functionLength = i - functionStart + 1;
          if (functionLength > 50) {
            issues.push({
              id: `ISS-${Date.now()}-${issues.length}`,
              type: 'smell',
              severity: 'medium',
              file: file.path,
              line: functionStart + 1,
              description: `Long function: ${functionLength} lines (threshold: 50)`,
              suggestion: 'Break into smaller, focused functions',
              confidence: 0.9,
              pattern: `${functionLength} lines`,
            });
          }
          functionStart = -1;
          braceDepth = 0;
        }
      }
    }
  }

  private detectDuplicateLines(
    file: HoundsInput['files'][0],
    lines: string[],
    issues: IssueScent[]
  ): void {
    const lineCounts = new Map<string, number[]>();
    const minDuplicateLength = 6; // ignore short lines

    for (let i = 0; i < lines.length; i++) {
      const trimmed = lines[i].trim();
      if (trimmed.length < minDuplicateLength) continue;
      if (/^[{}()\[\];,]*$/.test(trimmed)) continue; // ignore punctuation-only lines

      const existing = lineCounts.get(trimmed) ?? [];
      existing.push(i + 1);
      lineCounts.set(trimmed, existing);
    }

    for (const [line, lineNumbers] of lineCounts) {
      if (lineNumbers.length >= 3) {
        issues.push({
          id: `ISS-${Date.now()}-${issues.length}`,
          type: 'smell',
          severity: 'low',
          file: file.path,
          line: lineNumbers[0],
          description: `Duplicate line appears ${lineNumbers.length} times`,
          suggestion: 'Extract common logic into a shared function',
          confidence: 0.7,
          pattern: line.slice(0, 80),
        });
      }
    }
  }

  // ─────────────────────────────────────────────────────────────
  // Prioritise Issues
  // ─────────────────────────────────────────────────────────────

  private prioritiseIssues(files: HoundsInput['files']): HoundsResult {
    const allIssues: IssueScent[] = [];

    for (const file of files) {
      const history = this.issueHistory.get(file.path) ?? [];
      allIssues.push(...history);
    }

    const summary = this.buildSummary(allIssues);
    const priorityOrder = this.sortByPriority(allIssues);

    this.log.info('Issues prioritised', { total: allIssues.length });

    return {
      operation: 'prioritise',
      totalFiles: files.length,
      issues: allIssues,
      summary,
      priorityOrder,
    };
  }

  // ─────────────────────────────────────────────────────────────
  // Track Issues
  // ─────────────────────────────────────────────────────────────

  private trackIssues(files: HoundsInput['files']): HoundsResult {
    // Compare current state with history to find new/resolved issues
    const allIssues: IssueScent[] = [];

    for (const file of files) {
      const lines = file.content.split('\n');
      const currentIssues = this.sniffFile(file, lines);
      const previousIssues = this.issueHistory.get(file.path) ?? [];

      // Mark new issues
      for (const issue of currentIssues) {
        const isNew = !previousIssues.some(
          (prev) => prev.line === issue.line && prev.type === issue.type && prev.description === issue.description
        );
        if (isNew) {
          issue.confidence = Math.min(issue.confidence + 0.1, 1.0); // slight boost for new issues
        }
      }

      allIssues.push(...currentIssues);

      // Update history
      this.issueHistory.set(file.path, currentIssues);
    }

    const summary = this.buildSummary(allIssues);
    const priorityOrder = this.sortByPriority(allIssues);

    this.log.info('Issues tracked', { total: allIssues.length });

    return {
      operation: 'track',
      totalFiles: files.length,
      issues: allIssues,
      summary,
      priorityOrder,
    };
  }

  // ─────────────────────────────────────────────────────────────
  // Utilities
  // ─────────────────────────────────────────────────────────────

  private getLineNumber(content: string, index: number): number {
    let line = 1;
    for (let i = 0; i < index && i < content.length; i++) {
      if (content[i] === '\n') line++;
    }
    return line;
  }

  private buildSummary(issues: IssueScent[]): Record<IssueScent['type'], number> {
    const summary: Record<string, number> = {
      bug: 0, smell: 0, 'anti-pattern': 0, security: 0, performance: 0, style: 0,
    };
    for (const issue of issues) {
      summary[issue.type] = (summary[issue.type] ?? 0) + 1;
    }
    return summary as Record<IssueScent['type'], number>;
  }

  private sortByPriority(issues: IssueScent[]): IssueScent[] {
    const severityOrder: Record<IssueScent['severity'], number> = {
      critical: 0, high: 1, medium: 2, low: 3,
    };
    return [...issues].sort((a, b) => {
      const severityDiff = severityOrder[a.severity] - severityOrder[b.severity];
      if (severityDiff !== 0) return severityDiff;
      return b.confidence - a.confidence;
    });
  }
}
