/**
 * TheLabAI — Lead AI for The Lab Hub
 *
 * Identity:  AID-LAB
 * Pillar:    Norman Hawkins
 * Tier:      3 (Lead AI / Domain Orchestrator)
 * Domain:    Code quality, testing, debugging, compilation,
 *            static analysis, error detection, verification
 *
 * Pipeline:  Lint → Compile → Test → Debug
 *            Hounds sniffs out issues, SyntaxSage analyses code structure
 */

import { AI, Agent, Bot, Logger, AuditLedger } from '../../core/definitions'
import { HoundsAgent } from './agents/HoundsAgent';
import { SyntaxSageAgent } from './agents/SyntaxSageAgent';
import { LintBot } from './bots/LintBot';
import { CompileBot } from './bots/CompileBot';
import { DebugBot } from './bots/DebugBot';
import { TestBot } from './bots/TestBot';

const auditLedger = new AuditLedger();

// ─────────────────────────────────────────────────────────────
// Domain Interfaces
// ─────────────────────────────────────────────────────────────

export interface CodeFile {
  path: string;
  language: string;
  content: string;
  lastModified: number;
  size: number;
  hash: string;
}

export interface Diagnostic {
  id: string;
  severity: 'error' | 'warning' | 'info' | 'hint';
  code: string;
  message: string;
  file: string;
  line: number;
  column: number;
  endLine?: number;
  endColumn?: number;
  source: string;
  fix?: {
    description: string;
    edits: Array<{
      file: string;
      line: number;
      column: number;
      newText: string;
    }>;
  };
}

export interface TestSuite {
  id: string;
  name: string;
  file: string;
  tests: TestCase[];
  status: 'pending' | 'running' | 'passed' | 'failed' | 'skipped';
  duration: number;
  startedAt?: number;
  completedAt?: number;
}

export interface TestCase {
  id: string;
  name: string;
  suiteId: string;
  status: 'pending' | 'running' | 'passed' | 'failed' | 'skipped' | 'timeout';
  duration: number;
  error?: string;
  assertions: number;
  file: string;
  line: number;
}

export interface DebugSession {
  id: string;
  file: string;
  breakpoints: Breakpoint[];
  callStack: StackFrame[];
  variables: Record<string, unknown>;
  status: 'created' | 'running' | 'paused' | 'terminated';
  currentLine?: number;
}

export interface Breakpoint {
  id: string;
  file: string;
  line: number;
  condition?: string;
  hitCount: number;
  enabled: boolean;
}

export interface StackFrame {
  id: number;
  name: string;
  file: string;
  line: number;
  column: number;
  locals: Record<string, unknown>;
}

export interface AnalysisReport {
  id: string;
  timestamp: number;
  files: number;
  diagnostics: Diagnostic[];
  summary: {
    errors: number;
    warnings: number;
    info: number;
    hints: number;
  };
  qualityScore: number; // 0..100
  suggestions: string[];
}

// ─────────────────────────────────────────────────────────────
// TheLabAI Implementation
// ─────────────────────────────────────────────────────────────

export class TheLabAI extends AI {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private codeFiles: Map<string, CodeFile>;
  private diagnostics: Map<string, Diagnostic>;
  private testSuites: Map<string, TestSuite>;
  private debugSessions: Map<string, DebugSession>;
  private analysisReports: Map<string, AnalysisReport>;

  constructor() {
    super(
      'AID-LAB',
      'TheLab',
      'lab',
      'Norman Hawkins',
      3
    );

    this.log = new Logger('TheLabAI');
    this.audit = auditLedger;
    this.codeFiles = new Map();
    this.diagnostics = new Map();
    this.testSuites = new Map();
    this.debugSessions = new Map();
    this.analysisReports = new Map();

    // Register Agents
    this.registerAgent(new HoundsAgent());
    this.registerAgent(new SyntaxSageAgent());

    // Register Bots
    this.registerBot(new LintBot());
    this.registerBot(new CompileBot());
    this.registerBot(new DebugBot());
    this.registerBot(new TestBot());

    this.log.info('TheLabAI initialised', {
      agents: this.listAgentIds(),
      bots: this.listBotNames(),
    });
  }

  // ─────────────────────────────────────────────────────────────
  // Code File Management
  // ─────────────────────────────────────────────────────────────

  /**
   * Register a code file for analysis.
   */
  registerCodeFile(file: Omit<CodeFile, 'hash'>): CodeFile {
    const hash = this.simpleHash(file.content);
    const codeFile: CodeFile = { ...file, hash };
    this.codeFiles.set(file.path, codeFile);

    this.log.info('Code file registered', { path: file.path, language: file.language });
    return codeFile;
  }

  /**
   * Get a registered code file.
   */
  getCodeFile(path: string): CodeFile | undefined {
    return this.codeFiles.get(path);
  }

  // ─────────────────────────────────────────────────────────────
  // Analysis Pipeline
  // ─────────────────────────────────────────────────────────────

  /**
   * Run lint analysis via LintBot.
   */
  async lint(filePath: string, rules?: Record<string, unknown>): Promise<unknown> {
    const file = this.codeFiles.get(filePath);
    if (!file) throw new Error(`File not registered: ${filePath}`);

    const lint = this.getBot('Lint')!;
    const result = await lint.execute({
      operation: 'ANALYZE',
      code: file.content,
      language: file.language,
      filePath: file.path,
      rules: rules ?? {},
    });
    return result;
  }

  /**
   * Compile code via CompileBot.
   */
  async compile(filePath: string, options?: Record<string, unknown>): Promise<unknown> {
    const file = this.codeFiles.get(filePath);
    if (!file) throw new Error(`File not registered: ${filePath}`);

    const compile = this.getBot('Compile')!;
    const result = await compile.execute({
      operation: 'COMPILE',
      code: file.content,
      language: file.language,
      filePath: file.path,
      options: options ?? {},
    });
    return result;
  }

  /**
   * Run tests via TestBot.
   */
  async test(suiteId: string, config?: Record<string, unknown>): Promise<unknown> {
    const test = this.getBot('Test')!;
    const result = await test.execute({
      operation: 'RUN',
      suiteId,
      config: config ?? {},
    });
    return result;
  }

  /**
   * Debug code via DebugBot.
   */
  async debug(filePath: string, errorContext: Record<string, unknown>): Promise<unknown> {
    const file = this.codeFiles.get(filePath);
    if (!file) throw new Error(`File not registered: ${filePath}`);

    const debug = this.getBot('Debug')!;
    const result = await debug.execute({
      operation: 'ANALYZE',
      code: file.content,
      language: file.language,
      filePath: file.path,
      errorContext,
    });
    return result;
  }

  // ─────────────────────────────────────────────────────────────
  // Agent Delegation
  // ─────────────────────────────────────────────────────────────

  /**
   * Sniff out issues using HoundsAgent.
   */
  async sniffIssues(files: CodeFile[]): Promise<unknown> {
    const hounds = this.getAgent('SID-LAB-HOUNDS') as HoundsAgent;
    const result = await hounds.runCycle({ files, operation: 'sniff' });
    return result;
  }

  /**
   * Analyse code structure using SyntaxSageAgent.
   */
  async analyseStructure(code: string, language: string): Promise<unknown> {
    const sage = this.getAgent('SID-LAB-SYNTAXSAGE') as SyntaxSageAgent;
    const result = await sage.runCycle({ code, language, operation: 'analyse' });
    return result;
  }

  // ─────────────────────────────────────────────────────────────
  // Diagnostics Management
  // ─────────────────────────────────────────────────────────────

  /**
   * Store diagnostics for a file.
   */
  storeDiagnostics(filePath: string, diags: Diagnostic[]): void {
    for (const diag of diags) {
      this.diagnostics.set(diag.id, diag);
    }
    this.log.info('Diagnostics stored', { filePath, count: diags.length });
  }

  /**
   * Get all diagnostics for a file.
   */
  getDiagnostics(filePath: string): Diagnostic[] {
    return Array.from(this.diagnostics.values()).filter((d) => d.file === filePath);
  }

  // ─────────────────────────────────────────────────────────────
  // Health & Diagnostics
  // ─────────────────────────────────────────────────────────────

  healthCheck(): {
    status: 'healthy' | 'degraded' | 'critical';
    files: number;
    diagnostics: number;
    errors: number;
    warnings: number;
    testSuites: number;
    debugSessions: number;
    agents: number;
    bots: number;
    timestamp: number;
  } {
    const allDiags = Array.from(this.diagnostics.values());
    const errors = allDiags.filter((d) => d.severity === 'error').length;
    const warnings = allDiags.filter((d) => d.severity === 'warning').length;

    return {
      status: errors > 0 ? 'critical' : warnings > 5 ? 'degraded' : 'healthy',
      files: this.codeFiles.size,
      diagnostics: allDiags.length,
      errors,
      warnings,
      testSuites: this.testSuites.size,
      debugSessions: this.debugSessions.size,
      agents: this.listAgentIds().length,
      bots: this.listBotNames().length,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────
  // Utilities
  // ─────────────────────────────────────────────────────────────

  private simpleHash(content: string): string {
    let hash = 0;
    for (let i = 0; i < content.length; i++) {
      const char = content.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash |= 0; // Convert to 32-bit integer
    }
    return `H-${Math.abs(hash).toString(36).toUpperCase()}`;
  }
}
