/**
 * The Observatory — Barrel Exports
 *
 * Hub:      The Observatory
 * Pillar:   The Guardian
 * Identity: AID-OBSERVATORY
 *
 * All types, agents, bots, and the Lead AI are re-exported here
 * for clean upstream imports.
 */

// ─── Lead AI ──────────────────────────────────────────────────────────
export { TheObservatoryAI } from './TheObservatoryAI';
export type {
  Observation as AIObservation,
  Anomaly as AIAnomaly,
  CelestialPattern as AICelestialPattern,
  AlertSignal as AIAlertSignal,
  ObservationFilter as AIObservationFilter,
} from './TheObservatoryAI';

// ─── Agents ───────────────────────────────────────────────────────────
export { SentinelAgent } from './agents/SentinelAgent';
export type {
  SentinelInput,
  RawObservation,
  WatchResult,
  DetectionResult,
  AnomalyDetection,
  ClassificationResult,
  AnomalyCategory,
  EscalationResult,
  SentinelPerception,
  SentinelDecision,
  SentinelActionResult,
} from './agents/SentinelAgent';

export { AstrologerAgent } from './agents/AstrologerAgent';
export type {
  AstrologerInput,
  CelestialPatternType,
  CelestialReading,
  Interpretation,
  Prediction,
  PredictionEntry,
  Advice,
  AdvisedAction,
  AstrologerPerception,
  AstrologerDecision,
  AstrologerActionResult,
} from './agents/AstrologerAgent';

// ─── Bots ─────────────────────────────────────────────────────────────
export { TelescopeBot } from './bots/TelescopeBot';
export type {
  TelescopeInput,
  ScanDataPoint,
  ScanCoverage,
  ScanResult,
} from './bots/TelescopeBot';

export { StarMapBot } from './bots/StarMapBot';
export type {
  StarMapInput,
  CelestialCoordinate,
  ConstellationLink,
  PatternFormation,
  StarChart,
  PlotResult,
} from './bots/StarMapBot';

export { AlertBot } from './bots/AlertBot';
export type {
  AlertInput,
  AlertRecord,
  AlertSummary,
  SignalResult,
} from './bots/AlertBot';
