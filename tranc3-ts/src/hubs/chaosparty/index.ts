/**
 * The Chaos Party Hub — Barrel Exports
 *
 * "We're all mad here. 🐰"
 */

// Lead AI
export { TheChaosPartyAI } from './TheChaosPartyAI';
export type {
  ChaosScenario,
  ChaosEvent,
  EntropyMetrics,
  TeaRecipe,
  TimeBomb,
} from './TheChaosPartyAI';

// Agents
export { MarchHareAgent } from './agents/MarchHareAgent';
export type {
  MarchHareInput,
  ChaosPlan,
  ChaosExecution,
  ChaosEscalation,
  MarchHareResult,
} from './agents/MarchHareAgent';

export { DormouseAgent } from './agents/DormouseAgent';
export type {
  DormouseInput,
  ChaosAssessment,
  CalmResult,
  StabilisationResult,
  DormouseResult,
} from './agents/DormouseAgent';

// Bots
export { TeapotBot } from './bots/TeapotBot';
export type {
  TeapotInput,
  TeaIngredient,
  BrewResult,
} from './bots/TeapotBot';

export { PocketWatchBot } from './bots/PocketWatchBot';
export type {
  PocketWatchInput,
  BombState,
  ArmResult,
} from './bots/PocketWatchBot';

export { SugarCubeBot } from './bots/SugarCubeBot';
export type {
  SugarCubeInput,
  PerturbationEffect,
  SweetenResult,
} from './bots/SugarCubeBot';

export { JamTartBot } from './bots/JamTartBot';
export type {
  JamTartInput,
  FlavourNote,
  ImpactMetric,
  ResilienceAssessment,
  TasteResult,
} from './bots/JamTartBot';
