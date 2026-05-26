/**
 * The HIVE — Barrel Exports
 *
 * Hub:      The HIVE
 * Pillar:   The Queen
 * Identity: AID-QUEEN
 *
 * All types, agents, bots, and the Lead AI are re-exported here
 * for clean upstream imports.
 */

// ──── Lead AI ────
export { QueenAI } from './QueenAI';
export type {
  HiveTask,
  EstateConnection,
  ScannedItem,
  InjectionPoint,
  SwarmConsensus,
} from './QueenAI';

// ──── Agents ────
export { SwarmAgent } from './agents/SwarmAgent';
export type {
  SwarmInput,
  DispatchResult,
  CoordinationPlan,
  CoordinationStep,
  ScanResult,
  ScanFinding,
  InjectionResult,
  ConsensusResult,
  SwarmPerception,
  SwarmDecision,
  SwarmActionResult,
} from './agents/SwarmAgent';

// ──── Bots ────
export { TransportBot } from './bots/TransportBot';
export type {
  TransportInput,
  TransportEntry,
  TransportStatus,
  TransportResult,
} from './bots/TransportBot';
