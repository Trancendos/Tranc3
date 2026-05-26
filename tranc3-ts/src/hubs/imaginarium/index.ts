/**
 * Imaginarium Hub — Barrel Exports
 */

export { ImaginariumAI } from './ImaginariumAI';
export type {
  Concept,
  BlendRecipe,
  IdeaSpace,
  CreativeSession,
} from './ImaginariumAI';

export { AlchemistAgent } from './agents/AlchemistAgent';
export type {
  ConceptInput as AlchemistConceptInput,
  AlchemicalResult,
} from './agents/AlchemistAgent';

export { ArchitectAgent } from './agents/ArchitectAgent';
export type {
  ArchitectInput,
  StructuralNode,
  ArchitectResult,
} from './agents/ArchitectAgent';

export { MixerBot } from './bots/MixerBot';
export type {
  MixParams,
  ShuffleParams,
  MixerInput,
} from './bots/MixerBot';

export { BlenderBot } from './bots/BlenderBot';
export type {
  BlendOperation,
  EvaluateParams as BlendEvaluateParams,
  BlenderInput,
} from './bots/BlenderBot';

export { WelderBot } from './bots/WelderBot';
export type {
  WeldParams,
  BridgeParams,
  StrengthParams,
  WelderInput,
} from './bots/WelderBot';

export { PolisherBot } from './bots/PolisherBot';
export type {
  PolishParams,
  ClarifyParams,
  TrimParams,
  EnhanceParams,
  PolisherInput,
} from './bots/PolisherBot';
