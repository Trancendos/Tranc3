/**
 * WeaverAgent — Workflow Composition Agent for DigitalGrid
 *
 * Identity:  SID-DIGITALGRID-WEAVER
 * Tier:      4 (Autonomous Microservice)
 * Parent:    DigitalGridAI (AID-DIGITALGRID)
 *
 * Responsibilities:
 *   - Compose workflows from step definitions
 *   - Validate workflow structure (DAG check, orphan detection)
 *   - Optimize workflow step ordering
 *   - Resolve workflow conflicts and circular dependencies
 */

import { Agent, Bot, Logger } from '../../../core/definitions';

// ───────────────────────────────────────────────────────
// Domain Types
// ───────────────────────────────────────────────────────

export interface WeaverInput {
  steps: Array<{
    id: string;
    type: string;
    config: Record<string, unknown>;
    nextSteps: string[];
    errorStep?: string;
  }>;
  operation: 'compose' | 'validate' | 'optimize';
}

export interface WeaverResult {
  operation: string;
  valid: boolean;
  stepCount: number;
  entryStepId: string;
  terminalSteps: string[];
  hasCycles: boolean;
  orphans: string[];
  depth: number;
  optimizationApplied: string[];
}

// ───────────────────────────────────────────────────────
// WeaverAgent Implementation
// ───────────────────────────────────────────────────────

export class WeaverAgent extends Agent {
  private readonly log: Logger;

  constructor() {
    super('SID-DIGITALGRID-WEAVER');
    this.log = new Logger('WeaverAgent');
  }

  async perceive(observation: WeaverInput): Promise<{
    steps: WeaverInput['steps'];
    operation: string;
    stepIds: Set<string>;
  }> {
    const { steps, operation } = observation;
    const stepIds = new Set(steps.map((s) => s.id));

    this.log.info('Perceived workflow request', { stepCount: steps.length, operation });
    return { steps, operation, stepIds };
  }

  async decide(perceived: Awaited<ReturnType<typeof this.perceive>>): Promise<{
    action: string;
    params: Record<string, unknown>;
  }> {
    const { operation, steps, stepIds } = perceived;

    this.log.info('Decided on weave action', { operation });
    return { action: operation, params: { steps, stepIds } };
  }

  async act(decision: Awaited<ReturnType<typeof this.decide>>): Promise<WeaverResult> {
    const { action, params } = decision;
    const steps = params.steps as WeaverInput['steps'];
    const stepIds = params.stepIds as Set<string>;

    switch (action) {
      case 'validate':
        return this.validateWorkflow(steps, stepIds);
      case 'optimize':
        return this.optimizeWorkflow(steps, stepIds);
      default:
        return this.composeWorkflow(steps, stepIds);
    }
  }

  // ───────────────────────────────────────────────────────
  // Workflow Composition
  // ───────────────────────────────────────────────────────

  private composeWorkflow(steps: WeaverInput['steps'], stepIds: Set<string>): WeaverResult {
    // Find entry step: step that is not referenced as nextStep of any other step
    const referencedSteps = new Set(steps.flatMap((s) => s.nextSteps));
    const entrySteps = steps.filter((s) => !referencedSteps.has(s.id));

    // Find terminal steps: steps with no next steps
    const terminalSteps = steps.filter((s) => s.nextSteps.length === 0).map((s) => s.id);

    // Detect cycles
    const hasCycles = this.detectCycles(steps);

    // Detect orphans: steps not reachable from any entry point
    const reachable = this.findReachable(entrySteps.map((s) => s.id), steps);
    const orphans = steps.filter((s) => !reachable.has(s.id)).map((s) => s.id);

    // Compute depth
    const depth = this.computeDepth(entrySteps.map((s) => s.id), steps);

    const valid = !hasCycles && orphans.length === 0 && entrySteps.length > 0;

    this.log.info('Workflow composed', {
      stepCount: steps.length,
      entrySteps: entrySteps.length,
      terminalSteps: terminalSteps.length,
      valid,
    });

    return {
      operation: 'compose',
      valid,
      stepCount: steps.length,
      entryStepId: entrySteps[0]?.id ?? '',
      terminalSteps,
      hasCycles,
      orphans,
      depth,
      optimizationApplied: [],
    };
  }

  // ───────────────────────────────────────────────────────
  // Workflow Validation
  // ───────────────────────────────────────────────────────

  private validateWorkflow(steps: WeaverInput['steps'], stepIds: Set<string>): WeaverResult {
    // Check that all nextSteps reference valid step IDs
    const invalidRefs: string[] = [];
    for (const step of steps) {
      for (const nextId of step.nextSteps) {
        if (!stepIds.has(nextId)) {
          invalidRefs.push(`${step.id} → ${nextId}`);
        }
      }
      if (step.errorStep && !stepIds.has(step.errorStep)) {
        invalidRefs.push(`${step.id}(error) → ${step.errorStep}`);
      }
    }

    const hasCycles = this.detectCycles(steps);
    const reachable = this.findReachable(
      steps.filter((s) => !steps.some((o) => o.nextSteps.includes(s.id))).map((s) => s.id),
      steps
    );
    const orphans = steps.filter((s) => !reachable.has(s.id)).map((s) => s.id);

    const valid = !hasCycles && orphans.length === 0 && invalidRefs.length === 0;

    this.log.info('Workflow validated', { valid, hasCycles, orphans: orphans.length, invalidRefs: invalidRefs.length });

    return {
      operation: 'validate',
      valid,
      stepCount: steps.length,
      entryStepId: '',
      terminalSteps: steps.filter((s) => s.nextSteps.length === 0).map((s) => s.id),
      hasCycles,
      orphans,
      depth: 0,
      optimizationApplied: invalidRefs.length > 0 ? [`Invalid references found: ${invalidRefs.join(', ')}`] : [],
    };
  }

  // ───────────────────────────────────────────────────────
  // Workflow Optimization
  // ───────────────────────────────────────────────────────

  private optimizeWorkflow(steps: WeaverInput['steps'], stepIds: Set<string>): WeaverResult {
    const result = this.composeWorkflow(steps, stepIds);
    const optimizations: string[] = [];

    // Optimization: detect sequential chains that could be parallelized
    const sequentialChains = this.findSequentialChains(steps);
    if (sequentialChains.length > 0) {
      optimizations.push(`Found ${sequentialChains.length} sequential chains that could be parallelized`);
    }

    // Optimization: detect redundant condition steps
    const conditionSteps = steps.filter((s) => s.type === 'condition');
    if (conditionSteps.length > 3) {
      optimizations.push(`${conditionSteps.length} condition steps detected — consider consolidating`);
    }

    // Optimization: missing error handling
    const stepsWithoutError = steps.filter((s) => !s.errorStep && s.type !== 'trigger');
    if (stepsWithoutError.length > 0) {
      optimizations.push(`${stepsWithoutError.length} steps lack error handling`);
    }

    this.log.info('Workflow optimized', { optimizations: optimizations.length });

    return {
      ...result,
      operation: 'optimize',
      optimizationApplied: optimizations,
    };
  }

  // ───────────────────────────────────────────────────────
  // Graph Utilities
  // ───────────────────────────────────────────────────────

  private detectCycles(steps: WeaverInput['steps']): boolean {
    const adjacency: Record<string, string[]> = {};
    for (const step of steps) {
      adjacency[step.id] = step.nextSteps;
    }

    const visited = new Set<string>();
    const recursionStack = new Set<string>();

    const dfs = (nodeId: string): boolean => {
      visited.add(nodeId);
      recursionStack.add(nodeId);

      for (const neighbor of (adjacency[nodeId] ?? [])) {
        if (!visited.has(neighbor)) {
          if (dfs(neighbor)) return true;
        } else if (recursionStack.has(neighbor)) {
          return true;
        }
      }

      recursionStack.delete(nodeId);
      return false;
    };

    for (const step of steps) {
      if (!visited.has(step.id)) {
        if (dfs(step.id)) return true;
      }
    }

    return false;
  }

  private findReachable(startIds: string[], steps: WeaverInput['steps']): Set<string> {
    const adjacency: Record<string, string[]> = {};
    for (const step of steps) {
      adjacency[step.id] = step.nextSteps;
    }

    const reachable = new Set<string>();
    const queue = [...startIds];

    while (queue.length > 0) {
      const current = queue.shift()!;
      if (reachable.has(current)) continue;
      reachable.add(current);

      for (const next of (adjacency[current] ?? [])) {
        if (!reachable.has(next)) {
          queue.push(next);
        }
      }
    }

    return reachable;
  }

  private computeDepth(startIds: string[], steps: WeaverInput['steps']): number {
    const adjacency: Record<string, string[]> = {};
    for (const step of steps) {
      adjacency[step.id] = step.nextSteps;
    }

    let maxDepth = 0;
    const visited = new Set<string>();

    const dfs = (nodeId: string, depth: number): void => {
      if (visited.has(nodeId)) return;
      visited.add(nodeId);
      maxDepth = Math.max(maxDepth, depth);

      for (const next of (adjacency[nodeId] ?? [])) {
        dfs(next, depth + 1);
      }
    };

    for (const startId of startIds) {
      dfs(startId, 1);
    }

    return maxDepth;
  }

  private findSequentialChains(steps: WeaverInput['steps']): string[][] {
    const stepMap = new Map(steps.map((s) => [s.id, s]));
    const chains: string[][] = [];

    for (const step of steps) {
      if (step.nextSteps.length === 1) {
        const nextStep = stepMap.get(step.nextSteps[0]);
        if (nextStep && nextStep.nextSteps.length === 1) {
          // Found a chain: step → nextStep → ...
          const chain = [step.id, step.nextSteps[0]];
          let current = nextStep;
          while (current.nextSteps.length === 1) {
            const next = stepMap.get(current.nextSteps[0]);
            if (!next || next.nextSteps.length !== 1) break;
            chain.push(current.nextSteps[0]);
            current = next;
          }
          if (chain.length >= 3) {
            chains.push(chain);
          }
        }
      }
    }

    return chains;
  }
}
