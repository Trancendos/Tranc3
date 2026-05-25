/**
 * DigitalGrid Hub — Barrel Exports
 *
 * Lead AI:    DigitalGridAI (AID-DIGITALGRID)
 * Pillar:     Voxx
 * Tier:       3 (Lead AI / Domain Orchestrator)
 * Domain:     Event-driven workflows, automation pipelines,
 *             trigger-action systems, conditional routing
 */

// ─── Lead AI ────────────────────────────────────────────────
export { DigitalGridAI } from './DigitalGridAI';
export type {
  GridEvent,
  WorkflowStep,
  Workflow,
  Execution,
  StepResult,
  EventSubscription,
} from './DigitalGridAI';

// ─── Agents ─────────────────────────────────────────────────
export { WeaverAgent } from './agents/WeaverAgent';
export type { WeaverInput, WeaverResult } from './agents/WeaverAgent';

export { EventBrokerAgent } from './agents/EventBrokerAgent';
export type {
  BrokerEvent,
  BrokerSubscription,
  BrokerInput,
  BrokerOutput,
  MatchResult,
} from './agents/EventBrokerAgent';

// ─── Bots ───────────────────────────────────────────────────
export { TriggerBot } from './bots/TriggerBot';
export type { TriggerEvaluateInput, TriggerInput, TriggerResult } from './bots/TriggerBot';

export { ActionBot } from './bots/ActionBot';
export type { ActionExecuteInput, ActionInput, ActionResult } from './bots/ActionBot';

export { ConditionBot } from './bots/ConditionBot';
export type { ConditionEvaluateInput, ConditionInput, ConditionResult } from './bots/ConditionBot';

export { LoopBot } from './bots/LoopBot';
export type { LoopIterateInput, LoopInput, LoopResult } from './bots/LoopBot';
