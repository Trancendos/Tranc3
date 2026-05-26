/**
 * The Void — Barrel Exports
 *
 * Hub:      The Void
 * Pillar:   Prometheus
 * Identity: AID-VOID
 *
 * All types, agents, bots, and the Lead AI are re-exported here
 * for clean upstream imports.
 */

// ── Lead AI ────────────────────────────────────────────────────────────────
export { PrometheusAI } from './PrometheusAI';
export type {
  VoidSecret,
  RotationPolicy,
  EntanglementPair,
  QuantumVaultStats,
  IsolationReport,
} from './PrometheusAI';

// ── Agents ─────────────────────────────────────────────────────────────────
export { VaultAgent } from './agents/VaultAgent';
export type {
  VaultInput,
  VaultPerception,
  VaultDecision,
  SealResult,
  UnsealResult,
  RotateResult,
  VaultAuditResult,
  VaultActionResult,
} from './agents/VaultAgent';

// ── Bots ───────────────────────────────────────────────────────────────────
export { IsolationBot } from './bots/IsolationBot';
export type {
  IsolationInput,
  ThreatSignature,
  ScanResult,
  QuarantineRecord,
  IsolationResult,
  IsolationStats,
} from './bots/IsolationBot';
