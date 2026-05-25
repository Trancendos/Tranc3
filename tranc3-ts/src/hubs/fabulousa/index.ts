/**
 * Fabulousa Hub — Barrel Exports
 */

export { FabulousaAI } from './FabulousaAI';
export type {
  DesignSystem,
  ColorToken,
  TypographyScale,
  FontFamily,
  SpacingScale,
  Breakpoint,
  ShadowToken,
  BorderRadiusToken,
  ComponentStyle,
  StyleVariant,
  ThemeExport,
} from './FabulousaAI';

export { TailorAgent } from './agents/TailorAgent';
export type {
  PacingAnalysis as TailorPacingAnalysis,
  VariantGeneration,
  ContrastCheckResult,
  ThemeAdaptation,
  TailorDecision,
} from './agents/TailorAgent';

export { WeaverAgent } from './agents/WeaverAgent';
export type {
  WovenOutput,
  DependencyGraph,
  ConflictReport,
} from './agents/WeaverAgent';

export { PixelPusherBot } from './bots/PixelPusherBot';
export type {
  PixelBuffer,
  GradientStop,
  GradientRenderParams,
  PatternRenderParams,
  BlendParams,
  RasterizeParams,
  PixelPusherInput,
} from './bots/PixelPusherBot';

export { HexCodeBot } from './bots/HexCodeBot';
export type {
  PaletteParams,
  ConvertParams,
  ParseParams,
  ShiftParams,
  DistanceParams,
  HexCodeInput,
  RGB,
  HSL,
  HSV,
  LAB,
} from './bots/HexCodeBot';

export { FontFetcherBot } from './bots/FontFetcherBot';
export type {
  FontEntry,
  SearchParams as FontSearchParams,
  PairParams as FontPairParams,
  MetricsParams as FontMetricsParams,
  FontFaceParams,
  FallbackParams as FontFallbackParams,
  FontFetcherInput,
} from './bots/FontFetcherBot';

export { PaddingBot } from './bots/PaddingBot';
export type {
  GridParams,
  SpacingParams,
  ResponsiveParams,
  TokenParams,
  BoxModelParams,
  PaddingInput,
} from './bots/PaddingBot';
