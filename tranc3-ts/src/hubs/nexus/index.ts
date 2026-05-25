/**
 * The Nexus — Barrel Exports
 */

// ──── Lead AI ────
export { NexusAI } from './NexusAI';
export type {
  MessageChannel,
  ConnectionNode,
  RouteEntry,
  ProtocolBridge,
} from './NexusAI';

// ──── Agents ────
export { RelayAgent } from './agents/RelayAgent';
export type {
  RelayInput,
  RelayPerception,
  RelayDecision,
  RelayActionResult,
} from './agents/RelayAgent';

// ──── Bots ────
export { SwitchBot } from './bots/SwitchBot';
export type {
  SwitchInput,
  SwitchResult,
} from './bots/SwitchBot';
