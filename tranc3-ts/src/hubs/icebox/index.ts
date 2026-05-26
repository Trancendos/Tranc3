/**
 * The Ice Box — Barrel Exports
 */

export { NeonachAI } from './NeonachAI';
export type {
  Sandbox,
  FrozenSample,
  DetonationReport,
  ContainmentZone,
} from './NeonachAI';

export { FreezeAgent } from './agents/FreezeAgent';
export type {
  FreezeInput,
  FreezePerception,
  FreezeDecision,
  FreezeActionResult,
} from './agents/FreezeAgent';

export { CryoBot } from './bots/CryoBot';
export type {
  CryoInput,
  CryoResult,
} from './bots/CryoBot';
