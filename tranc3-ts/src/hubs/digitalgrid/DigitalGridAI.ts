/**
 * DigitalGridAI — Lead AI for the DigitalGrid Hub
 *
 * Identity:  AID-DIGITALGRID
 * Pillar:    Voxx
 * Tier:      3 (Lead AI / Domain Orchestrator)
 * Domain:    Event-driven workflows, automation pipelines,
 *            trigger-action systems, conditional routing,
 *            workflow orchestration
 *
 * Pipeline:  Trigger → Condition → Action → Loop
 *            Weaver composes workflows, EventBroker routes events
 */

import { AI, Agent, Bot, Logger, AuditLedger } from '../../core/definitions';
import { WeaverAgent } from './agents/WeaverAgent';
import { EventBrokerAgent } from './agents/EventBrokerAgent';
import { TriggerBot } from './bots/TriggerBot';
import { ActionBot } from './bots/ActionBot';
import { ConditionBot } from './bots/ConditionBot';
import { LoopBot } from './bots/LoopBot';

// ───────────────────────────────────────────────────────
// Domain Interfaces
// ───────────────────────────────────────────────────────

export interface GridEvent {
  id: string;
  type: string;
  source: string;
  timestamp: number;
  payload: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

export interface WorkflowStep {
  id: string;
  type: 'trigger' | 'condition' | 'action' | 'loop' | 'delay' | 'parallel' | 'subworkflow';
  config: Record<string, unknown>;
  nextSteps: string[];     // step IDs for branching
  errorStep?: string;      // fallback step on error
  timeout?: number;        // ms
  retryCount?: number;
}

export interface Workflow {
  id: string;
  name: string;
  description: string;
  version: number;
  steps: Map<string, WorkflowStep>;
  entryStep: string;
  status: 'draft' | 'active' | 'paused' | 'archived';
  executionCount: number;
  lastExecution?: number;
  createdAt: number;
  updatedAt: number;
}

export interface Execution {
  id: string;
  workflowId: string;
  status: 'running' | 'completed' | 'failed' | 'timed-out' | 'cancelled';
  currentStepId: string;
  startedAt: number;
  completedAt?: number;
  stepResults: Map<string, StepResult>;
  error?: string;
}

export interface StepResult {
  stepId: string;
  status: 'success' | 'skipped' | 'failed';
  output: Record<string, unknown>;
  duration: number; // ms
  retries: number;
}

export interface EventSubscription {
  id: string;
  eventType: string;
  workflowId: string;
  entryStepId: string;
  filter?: Record<string, unknown>;
  createdAt: number;
}

// ───────────────────────────────────────────────────────
// DigitalGridAI Implementation
// ───────────────────────────────────────────────────────

export class DigitalGridAI extends AI {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private workflows: Map<string, Workflow>;
  private executions: Map<string, Execution>;
  private subscriptions: Map<string, EventSubscription>;

  constructor() {
    super(
      'AID-DIGITALGRID',
      'DigitalGrid',
      'digitalgrid',
      'Voxx',
      3
    );

    this.log = new Logger('DigitalGridAI');
    this.audit = AuditLedger.getInstance();
    this.workflows = new Map();
    this.executions = new Map();
    this.subscriptions = new Map();

    // Register Agents
    this.registerAgent(new WeaverAgent());
    this.registerAgent(new EventBrokerAgent());

    // Register Bots
    this.registerBot(new TriggerBot());
    this.registerBot(new ActionBot());
    this.registerBot(new ConditionBot());
    this.registerBot(new LoopBot());

    this.log.info('DigitalGridAI initialised', {
      agents: this.listAgentIds(),
      bots: this.listBotNames(),
    });
  }

  // ───────────────────────────────────────────────────────
  // Workflow Management
  // ───────────────────────────────────────────────────────

  /**
   * Create a new workflow.
   */
  createWorkflow(name: string, description: string, steps: WorkflowStep[] = [], entryStepId: string = ''): Workflow {
    const id = `WF-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`.toUpperCase();
    const stepMap = new Map<string, WorkflowStep>();
    for (const step of steps) {
      stepMap.set(step.id, step);
    }

    const workflow: Workflow = {
      id,
      name,
      description,
      version: 1,
      steps: stepMap,
      entryStep: entryStepId || steps[0]?.id || '',
      status: 'draft',
      executionCount: 0,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };

    this.workflows.set(id, workflow);

    this.audit.append({
      actor: this.id,
      action: 'WORKFLOW_CREATED',
      entity: id,
      details: { name, stepCount: steps.length },
      timestamp: Date.now(),
    });

    this.log.info('Workflow created', { id, name, stepCount: steps.length });
    return workflow;
  }

  /**
   * Get a workflow by ID.
   */
  getWorkflow(id: string): Workflow | undefined {
    return this.workflows.get(id);
  }

  /**
   * Activate a workflow.
   */
  activateWorkflow(id: string): boolean {
    const wf = this.workflows.get(id);
    if (!wf) return false;
    wf.status = 'active';
    wf.updatedAt = Date.now();

    this.log.info('Workflow activated', { id });
    return true;
  }

  // ───────────────────────────────────────────────────────
  // Event Processing
  // ───────────────────────────────────────────────────────

  /**
   * Emit an event into the grid.
   */
  async emitEvent(event: Omit<GridEvent, 'id' | 'timestamp'>): Promise<GridEvent> {
    const gridEvent: GridEvent = {
      id: `EVT-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`.toUpperCase(),
      timestamp: Date.now(),
      ...event,
    };

    // Route event through EventBrokerAgent
    const broker = this.getAgent('SID-DIGITALGRID-EVENTBROKER') as EventBrokerAgent;
    await broker.runCycle({ event: gridEvent, subscriptions: Array.from(this.subscriptions.values()) });

    this.log.info('Event emitted', { id: gridEvent.id, type: gridEvent.type });
    return gridEvent;
  }

  /**
   * Subscribe a workflow to an event type.
   */
  subscribe(eventType: string, workflowId: string, entryStepId: string, filter?: Record<string, unknown>): EventSubscription {
    const id = `SUB-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`.toUpperCase();

    const subscription: EventSubscription = {
      id,
      eventType,
      workflowId,
      entryStepId,
      filter,
      createdAt: Date.now(),
    };

    this.subscriptions.set(id, subscription);

    this.log.info('Event subscription created', { id, eventType, workflowId });
    return subscription;
  }

  // ───────────────────────────────────────────────────────
  // Workflow Execution
  // ───────────────────────────────────────────────────────

  /**
   * Execute a trigger evaluation via TriggerBot.
   */
  async evaluateTrigger(triggerType: string, config: Record<string, unknown>, event?: GridEvent): Promise<unknown> {
    const trigger = this.getBot('Trigger')!;
    const result = await trigger.execute({
      operation: 'EVALUATE',
      triggerType,
      config,
      event: event ?? null,
    });
    return result;
  }

  /**
   * Execute an action via ActionBot.
   */
  async executeAction(actionType: string, config: Record<string, unknown>, input?: Record<string, unknown>): Promise<unknown> {
    const action = this.getBot('Action')!;
    const result = await action.execute({
      operation: 'EXECUTE',
      actionType,
      config,
      input: input ?? {},
    });
    return result;
  }

  /**
   * Evaluate a condition via ConditionBot.
   */
  async evaluateCondition(conditionType: string, config: Record<string, unknown>, data: Record<string, unknown>): Promise<unknown> {
    const condition = this.getBot('Condition')!;
    const result = await condition.execute({
      operation: 'EVALUATE',
      conditionType,
      config,
      data,
    });
    return result;
  }

  /**
   * Execute a loop iteration via LoopBot.
   */
  async executeLoop(loopType: string, config: Record<string, unknown>, iteration: number): Promise<unknown> {
    const loop = this.getBot('Loop')!;
    const result = await loop.execute({
      operation: 'ITERATE',
      loopType,
      config,
      iteration,
    });
    return result;
  }

  /**
   * Compose a workflow using WeaverAgent.
   */
  async composeWorkflow(steps: WorkflowStep[]): Promise<unknown> {
    const weaver = this.getAgent('SID-DIGITALGRID-WEAVER') as WeaverAgent;
    const result = await weaver.runCycle({ steps, operation: 'compose' });
    return result;
  }

  // ───────────────────────────────────────────────────────
  // Health & Diagnostics
  // ───────────────────────────────────────────────────────

  healthCheck(): {
    status: 'healthy' | 'degraded' | 'critical';
    workflows: number;
    activeWorkflows: number;
    executions: number;
    subscriptions: number;
    agents: number;
    bots: number;
    timestamp: number;
  } {
    const activeWorkflows = Array.from(this.workflows.values()).filter((w) => w.status === 'active').length;
    return {
      status: 'healthy',
      workflows: this.workflows.size,
      activeWorkflows,
      executions: this.executions.size,
      subscriptions: this.subscriptions.size,
      agents: this.listAgentIds().length,
      bots: this.listBotNames().length,
      timestamp: Date.now(),
    };
  }
}
