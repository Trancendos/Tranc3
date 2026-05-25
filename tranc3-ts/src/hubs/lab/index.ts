/**
 * The Lab — Barrel Exports
 *
 * Hub:       The Lab
 * Identity:  AID-LAB
 * Pillar:    Norman Hawkins
 * Domain:    Code quality, testing, debugging, compilation
 */

// ── Lead AI ──────────────────────────────────────────────────────────────────
export { TheLabAI } from './TheLabAI';
export type {
  CodeFile,
  Diagnostic,
  TestSuite,
  TestCase,
  DebugSession,
  Breakpoint,
  StackFrame,
  AnalysisReport,
} from './TheLabAI';

// ── Agents ───────────────────────────────────────────────────────────────────
export { HoundsAgent } from './agents/HoundsAgent';
export { SyntaxSageAgent } from './agents/SyntaxSageAgent';

// ── Bots ─────────────────────────────────────────────────────────────────────
export { LintBot } from './bots/LintBot';
export type { LintInput, LintRule, LintResult } from './bots/LintBot';

export { CompileBot } from './bots/CompileBot';
export type { CompileInput, CompileError, CompileResult } from './bots/CompileBot';

export { DebugBot } from './bots/DebugBot';
export type {
  DebugInput,
  ErrorPattern,
  DebugFinding,
  StackAnalysis,
  DebugResult,
} from './bots/DebugBot';

export { TestBot } from './bots/TestBot';
export type {
  TestInput,
  TestResultCase,
  TestResultSuite,
  TestResult,
} from './bots/TestBot';
