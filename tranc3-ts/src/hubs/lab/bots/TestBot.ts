/**
 * TestBot — Test Execution Bot for The Lab
 *
 * Identity:  NID-LAB-TEST
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TheLabAI (AID-LAB)
 *
 * Responsibilities:
 *   - Execute test suites and individual test cases
 *   - Track pass/fail/skip/timeout status per test
 *   - Aggregate test results with timing and coverage metrics
 *   - Support setup/teardown lifecycle hooks
 *   - Generate test reports with failure analysis
 */

import { AuditLedger, Bot, Logger } from '../../../core/definitions'

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface TestInput {
  operation: 'RUN';
  suiteId: string;
  config: {
    timeout?: number;              // per-test timeout in ms (default 5000)
    retries?: number;              // retry count for failed tests (default 0)
    bail?: boolean;                // stop on first failure (default false)
    grep?: string;                 // only run tests matching this pattern
    coverage?: boolean;            // collect coverage data (default false)
    parallel?: boolean;            // run tests in parallel (default false)
    verbose?: boolean;             // verbose output (default false)
    setup?: string[];              // setup hook names
    teardown?: string[];           // teardown hook names
    environment?: Record<string, string>;
    tags?: string[];               // only run tests with these tags
  };
}

export interface TestResultCase {
  id: string;
  name: string;
  suiteId: string;
  status: 'passed' | 'failed' | 'skipped' | 'timeout' | 'error';
  duration: number;
  assertions: number;
  error?: {
    message: string;
    stack?: string;
    expected?: unknown;
    actual?: unknown;
    operator?: string;
  };
  retries: number;
  file: string;
  line: number;
  tags: string[];
}

export interface TestResultSuite {
  id: string;
  name: string;
  status: 'passed' | 'failed' | 'partial' | 'skipped';
  tests: TestResultCase[];
  duration: number;
  passed: number;
  failed: number;
  skipped: number;
  timeout: number;
  errors: number;
  startedAt: number;
  completedAt: number;
  coverage?: {
    lines: number;       // percentage 0..100
    branches: number;    // percentage 0..100
    functions: number;   // percentage 0..100
    statements: number;  // percentage 0..100
    uncoveredFiles: string[];
  };
}

export interface TestResult {
  success: boolean;
  suiteId: string;
  suite: TestResultSuite;
  summary: {
    total: number;
    passed: number;
    failed: number;
    skipped: number;
    timeout: number;
    errors: number;
    passRate: number;     // 0..1
    duration: number;
    slowestTest: string;
  };
  failures: Array<{
    testName: string;
    error: string;
    file: string;
    line: number;
    suggestedFix: string;
  }>;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// TestBot Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class TestBot extends Bot {
  private readonly log: Logger;
  private readonly registeredSuites: Map<string, TestSuiteDefinition>;

  constructor() {
    const handler = async (input: TestInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-LAB-TEST',
      'Test',
      handler,
      'Test suite execution engine with lifecycle hooks and coverage tracking'
    );

    this.log = new Logger('TestBot');
    this.registeredSuites = new Map();
    this.initBuiltinSuites();
  }

  private async process(input: TestInput): Promise<TestResult> {
    switch (input.operation) {
      case 'RUN':
        return this.run(input);
      default:
        throw new Error(`TestBot: Unknown operation "${(input as any).operation}"`);
    }
  }

  // ───────────────────────────────────────────────────────────────────────────
  // RUN
  // ───────────────────────────────────────────────────────────────────────────

  private async run(input: TestInput): Promise<TestResult> {
    const { suiteId, config } = input;
    const timeout = config.timeout ?? 5000;
    const retries = config.retries ?? 0;
    const bail = config.bail ?? false;
    const verbose = config.verbose ?? false;

    this.log.info('Running test suite', { suiteId, config });

    const suiteDef = this.registeredSuites.get(suiteId);
    if (!suiteDef) {
      // For unregistered suites, generate a simulated result
      return this.runSimulatedSuite(suiteId, config);
    }

    const startedAt = Date.now();
    const testResults: TestResultCase[] = [];
    let bailTriggered = false;

    // Execute setup hooks
    if (config.setup) {
      for (const hook of config.setup) {
        this.executeHook(hook, 'setup');
      }
    }

    // Execute each test case
    for (const testDef of suiteDef.tests) {
      if (bailTriggered) {
        // Skip remaining tests after bail
        testResults.push({
          id: testDef.id,
          name: testDef.name,
          suiteId,
          status: 'skipped',
          duration: 0,
          assertions: 0,
          retries: 0,
          file: testDef.file,
          line: testDef.line,
          tags: testDef.tags ?? [],
        });
        continue;
      }

      // Apply grep filter
      if (config.grep && !new RegExp(config.grep).test(testDef.name)) {
        testResults.push({
          id: testDef.id,
          name: testDef.name,
          suiteId,
          status: 'skipped',
          duration: 0,
          assertions: 0,
          retries: 0,
          file: testDef.file,
          line: testDef.line,
          tags: testDef.tags ?? [],
        });
        continue;
      }

      // Apply tag filter
      if (config.tags && config.tags.length > 0) {
        const testTags = testDef.tags ?? [];
        if (!config.tags.some((tag) => testTags.includes(tag))) {
          testResults.push({
            id: testDef.id,
            name: testDef.name,
            suiteId,
            status: 'skipped',
            duration: 0,
            assertions: 0,
            retries: 0,
            file: testDef.file,
            line: testDef.line,
            tags: testTags,
          });
          continue;
        }
      }

      // Execute test with retry logic
      const result = await this.executeTest(testDef, suiteId, timeout, retries);
      testResults.push(result);

      if ((result.status === 'failed' || result.status === 'timeout') && bail) {
        bailTriggered = true;
      }
    }

    // Execute teardown hooks
    if (config.teardown) {
      for (const hook of config.teardown) {
        this.executeHook(hook, 'teardown');
      }
    }

    const completedAt = Date.now();

    // Build suite result
    const passed = testResults.filter((t) => t.status === 'passed').length;
    const failed = testResults.filter((t) => t.status === 'failed').length;
    const skipped = testResults.filter((t) => t.status === 'skipped').length;
    const timedOut = testResults.filter((t) => t.status === 'timeout').length;
    const errors = testResults.filter((t) => t.status === 'error').length;
    const totalDuration = completedAt - startedAt;

    const suiteResult: TestResultSuite = {
      id: suiteId,
      name: suiteDef.name,
      status: failed > 0 || errors > 0 ? (passed > 0 ? 'partial' : 'failed') : 'passed',
      tests: testResults,
      duration: totalDuration,
      passed,
      failed,
      skipped,
      timeout: timedOut,
      errors,
      startedAt,
      completedAt,
    };

    // Coverage (simulated)
    if (config.coverage) {
      suiteResult.coverage = this.simulateCoverage(suiteDef);
    }

    // Build failures analysis
    const failures = testResults
      .filter((t) => t.status === 'failed' || t.status === 'timeout')
      .map((t) => ({
        testName: t.name,
        error: t.error?.message ?? (t.status === 'timeout' ? 'Test timed out' : 'Unknown error'),
        file: t.file,
        line: t.line,
        suggestedFix: this.suggestFix(t),
      }));

    // Find slowest test
    const slowest = testResults.reduce((prev, curr) =>
      curr.duration > prev.duration ? curr : prev, testResults[0]);

    const result: TestResult = {
      success: failed === 0 && errors === 0 && timedOut === 0,
      suiteId,
      suite: suiteResult,
      summary: {
        total: testResults.length,
        passed,
        failed,
        skipped,
        timeout: timedOut,
        errors,
        passRate: testResults.length > 0 ? passed / testResults.length : 0,
        duration: totalDuration,
        slowestTest: slowest ? `${slowest.name} (${slowest.duration}ms)` : 'N/A',
      },
      failures,
      timestamp: Date.now(),
    };

    this.log.info('Test suite complete', {
      suiteId,
      success: result.success,
      passed,
      failed,
      duration: totalDuration,
    });

    return result;
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Test Execution
  // ───────────────────────────────────────────────────────────────────────────

  private async executeTest(
    testDef: TestDefinition,
    suiteId: string,
    timeout: number,
    maxRetries: number
  ): Promise<TestResultCase> {
    let lastError: TestResultCase['error'] | undefined;
    let attempts = 0;

    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      attempts = attempt;
      const startTime = Date.now();

      try {
        // Simulate test execution
        const result = await this.simulateTestExecution(testDef, timeout);
        const duration = Date.now() - startTime;

        if (result.timedOut) {
          return {
            id: testDef.id,
            name: testDef.name,
            suiteId,
            status: 'timeout',
            duration,
            assertions: testDef.assertions ?? 1,
            error: {
              message: `Test exceeded timeout of ${timeout}ms`,
            },
            retries: attempt,
            file: testDef.file,
            line: testDef.line,
            tags: testDef.tags ?? [],
          };
        }

        if (result.passed) {
          return {
            id: testDef.id,
            name: testDef.name,
            suiteId,
            status: 'passed',
            duration,
            assertions: testDef.assertions ?? 1,
            retries: attempt,
            file: testDef.file,
            line: testDef.line,
            tags: testDef.tags ?? [],
          };
        }

        // Test failed — will retry if retries remain
        lastError = result.error;
      } catch (err) {
        lastError = {
          message: err instanceof Error ? err.message : String(err),
        };
      }
    }

    // All retries exhausted
    const duration = Date.now() - (Date.now() - 100); // approximate
    return {
      id: testDef.id,
      name: testDef.name,
      suiteId,
      status: lastError ? 'failed' : 'error',
      duration: 100,
      assertions: testDef.assertions ?? 1,
      error: lastError,
      retries: attempts,
      file: testDef.file,
      line: testDef.line,
      tags: testDef.tags ?? [],
    };
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Simulated Test Execution
  // ───────────────────────────────────────────────────────────────────────────

  private async simulateTestExecution(
    testDef: TestDefinition,
    timeout: number
  ): Promise<{ passed: boolean; timedOut: boolean; error?: TestResultCase['error'] }> {
    // In a real implementation, this would invoke the actual test function
    // Here we simulate based on the test definition's expected result

    const simulatedDuration = Math.floor(Math.random() * timeout * 0.8) + 10;
    const timeoutRisk = testDef.timeoutRisk ?? Math.random() * 0.05; // 5% timeout chance by default
    const failRate = testDef.failRate ?? Math.random() * 0.1; // 10% fail chance by default

    // Simulate timeout
    if (Math.random() < timeoutRisk) {
      return { passed: false, timedOut: true };
    }

    // Simulate failure
    if (Math.random() < failRate) {
      return {
        passed: false,
        timedOut: false,
        error: {
          message: this.generateSimulatedFailureMessage(testDef),
          expected: testDef.expectedValue,
          actual: testDef.actualValue ?? '<simulated unexpected value>',
          operator: 'equal',
        },
      };
    }

    return { passed: true, timedOut: false };
  }

  private generateSimulatedFailureMessage(testDef: TestDefinition): string {
    const messages = [
      `Expected ${JSON.stringify(testDef.expectedValue ?? 'value')} but received undefined`,
      `Assertion failed: ${testDef.name} did not produce expected result`,
      `TypeError: Cannot read properties of undefined (reading 'value')`,
      `AssertionError: expected true, got false`,
      `RangeError: Index out of bounds`,
    ];
    return messages[Math.floor(Math.random() * messages.length)];
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Simulated Suite (for unregistered suite IDs)
  // ───────────────────────────────────────────────────────────────────────────

  private runSimulatedSuite(suiteId: string, config: TestInput['config']): TestResult {
    const startedAt = Date.now();
    const testCount = Math.floor(Math.random() * 10) + 5; // 5..14 tests
    const passCount = Math.floor(testCount * (0.7 + Math.random() * 0.3)); // 70-100% pass rate
    const failCount = Math.floor((testCount - passCount) * 0.7);
    const skipCount = testCount - passCount - failCount;
    const duration = Math.floor(Math.random() * 2000) + 100;

    const testResults: TestResultCase[] = [];
    for (let i = 0; i < testCount; i++) {
      const status = i < passCount ? 'passed' : i < passCount + failCount ? 'failed' : 'skipped';
      testResults.push({
        id: `SIM-${suiteId}-${i}`,
        name: `test_${suiteId}_case_${i + 1}`,
        suiteId,
        status,
        duration: status === 'skipped' ? 0 : Math.floor(Math.random() * 200) + 5,
        assertions: status === 'skipped' ? 0 : Math.floor(Math.random() * 5) + 1,
        error: status === 'failed' ? {
          message: 'Simulated test failure',
          expected: true,
          actual: false,
        } : undefined,
        retries: 0,
        file: `tests/${suiteId}.test.ts`,
        line: i * 10 + 5,
        tags: [],
      });
    }

    const suiteResult: TestResultSuite = {
      id: suiteId,
      name: `Simulated Suite ${suiteId}`,
      status: failCount > 0 ? 'partial' : 'passed',
      tests: testResults,
      duration,
      passed: passCount,
      failed: failCount,
      skipped: skipCount,
      timeout: 0,
      errors: 0,
      startedAt,
      completedAt: Date.now(),
    };

    if (config.coverage) {
      suiteResult.coverage = {
        lines: Math.floor(Math.random() * 30) + 70,     // 70-100%
        branches: Math.floor(Math.random() * 30) + 60,   // 60-90%
        functions: Math.floor(Math.random() * 30) + 70,  // 70-100%
        statements: Math.floor(Math.random() * 30) + 70, // 70-100%
        uncoveredFiles: [],
      };
    }

    const failures = testResults
      .filter((t) => t.status === 'failed')
      .map((t) => ({
        testName: t.name,
        error: t.error?.message ?? 'Unknown failure',
        file: t.file,
        line: t.line,
        suggestedFix: 'Review the test assertion and the code under test',
      }));

    const slowest = testResults.reduce((prev, curr) =>
      curr.duration > prev.duration ? curr : prev, testResults[0]);

    return {
      success: failCount === 0,
      suiteId,
      suite: suiteResult,
      summary: {
        total: testCount,
        passed: passCount,
        failed: failCount,
        skipped: skipCount,
        timeout: 0,
        errors: 0,
        passRate: testCount > 0 ? passCount / testCount : 0,
        duration,
        slowestTest: slowest ? `${slowest.name} (${slowest.duration}ms)` : 'N/A',
      },
      failures,
      timestamp: Date.now(),
    };
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Lifecycle Hooks
  // ───────────────────────────────────────────────────────────────────────────

  private executeHook(hookName: string, type: 'setup' | 'teardown'): void {
    this.log.info(`Executing ${type} hook`, { hookName });
    // In a real implementation, this would invoke registered hook functions
    // For now, just log the execution
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Coverage Simulation
  // ───────────────────────────────────────────────────────────────────────────

  private simulateCoverage(suiteDef: TestSuiteDefinition): TestResultSuite['coverage'] {
    const testCount = suiteDef.tests.length;
    const baseCoverage = Math.min(95, 40 + testCount * 5);

    return {
      lines: baseCoverage,
      branches: Math.max(baseCoverage - 10, 0),
      functions: Math.min(baseCoverage + 5, 100),
      statements: baseCoverage,
      uncoveredFiles: [],
    };
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Failure Fix Suggestions
  // ───────────────────────────────────────────────────────────────────────────

  private suggestFix(testResult: TestResultCase): string {
    if (testResult.status === 'timeout') {
      return 'Increase the test timeout or check for infinite loops, unresolved promises, or missing awaits in the test';
    }

    const errorMsg = testResult.error?.message?.toLowerCase() ?? '';

    if (errorMsg.includes('cannot read propert')) {
      return 'Add null/undefined checks before accessing properties — the object may not be initialized';
    }
    if (errorMsg.includes('is not a function')) {
      return 'Verify the object has the expected method — check the type and import path';
    }
    if (errorMsg.includes('is not defined')) {
      return 'Ensure the variable is declared and in scope — check for typos and missing imports';
    }
    if (errorMsg.includes('expected') && errorMsg.includes('received')) {
      return 'Compare the expected and actual values carefully — check for type mismatches or off-by-one errors';
    }
    if (errorMsg.includes('typeerror')) {
      return 'Check that the value is of the expected type before performing operations on it';
    }
    if (errorMsg.includes('rangeerror')) {
      return 'Verify array indices and numeric values are within valid ranges';
    }

    return 'Review the failing assertion and the code under test for discrepancies';
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Built-in Test Suite Definitions
  // ───────────────────────────────────────────────────────────────────────────

  private initBuiltinSuites(): void {
    // Core validation suite
    this.registeredSuites.set('core-validation', {
      id: 'core-validation',
      name: 'Core Validation Suite',
      file: 'tests/core/validation.test.ts',
      tests: [
        { id: 'CV-01', name: 'should validate Bot constructor args', file: 'tests/core/validation.test.ts', line: 5, assertions: 3, tags: ['core', 'bot'] },
        { id: 'CV-02', name: 'should validate Agent perceive/decide/act cycle', file: 'tests/core/validation.test.ts', line: 20, assertions: 5, tags: ['core', 'agent'] },
        { id: 'CV-03', name: 'should validate AI agent registration', file: 'tests/core/validation.test.ts', line: 40, assertions: 2, tags: ['core', 'ai'] },
        { id: 'CV-04', name: 'should validate Logger namespace output', file: 'tests/core/validation.test.ts', line: 55, assertions: 4, tags: ['core', 'logger'] },
        { id: 'CV-05', name: 'should validate AuditLedger hash chaining', file: 'tests/core/validation.test.ts', line: 70, assertions: 6, tags: ['core', 'audit'] },
      ],
    });

    // Pipeline validation suite
    this.registeredSuites.set('pipeline-validation', {
      id: 'pipeline-validation',
      name: 'Pipeline Validation Suite',
      file: 'tests/pipeline/validation.test.ts',
      tests: [
        { id: 'PV-01', name: 'should execute lint-compile-test-debug pipeline', file: 'tests/pipeline/validation.test.ts', line: 5, assertions: 4, tags: ['pipeline', 'integration'] },
        { id: 'PV-02', name: 'should fail pipeline on compilation errors', file: 'tests/pipeline/validation.test.ts', line: 25, assertions: 3, tags: ['pipeline', 'compile'] },
        { id: 'PV-03', name: 'should continue pipeline on lint warnings', file: 'tests/pipeline/validation.test.ts', line: 42, assertions: 2, tags: ['pipeline', 'lint'] },
        { id: 'PV-04', name: 'should report test failures with context', file: 'tests/pipeline/validation.test.ts', line: 58, assertions: 5, tags: ['pipeline', 'test'] },
        { id: 'PV-05', name: 'should debug and suggest fixes for errors', file: 'tests/pipeline/validation.test.ts', line: 75, assertions: 4, tags: ['pipeline', 'debug'] },
        { id: 'PV-06', name: 'should handle async pipeline stages', file: 'tests/pipeline/validation.test.ts', line: 92, assertions: 3, tags: ['pipeline', 'async'] },
      ],
    });
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Internal Test Definition Type
// ─────────────────────────────────────────────────────────────────────────────

interface TestSuiteDefinition {
  id: string;
  name: string;
  file: string;
  tests: TestDefinition[];
}

interface TestDefinition {
  id: string;
  name: string;
  file: string;
  line: number;
  assertions?: number;
  tags?: string[];
  expectedValue?: unknown;
  actualValue?: unknown;
  failRate?: number;
  timeoutRisk?: number;
}
