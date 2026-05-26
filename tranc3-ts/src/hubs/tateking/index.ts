/**
 * TateKing Hub — Barrel Exports
 */

export { TateKingAI } from './TateKingAI';
export type {
  VideoProject,
  Timeline,
  Track,
  Clip,
  Transition,
  Effect,
  Keyframe,
  Marker,
  RenderConfig,
} from './TateKingAI';

export { DirectorAgent } from './agents/DirectorAgent';
export type {
  PacingAnalysis,
  StyleRecommendation,
  CutSuggestion,
  DirectionResult,
} from './agents/DirectorAgent';

export { EditorAgent } from './agents/EditorAgent';
export type {
  EditInstruction,
  EditResult,
  AudioAnalysis,
  ColorCorrectionProfile,
} from './agents/EditorAgent';

export { CutterBot } from './bots/CutterBot';
export { SplicerBot } from './bots/SplicerBot';
export { RendererBot } from './bots/RendererBot';
export { ScrubberBot } from './bots/ScrubberBot';
