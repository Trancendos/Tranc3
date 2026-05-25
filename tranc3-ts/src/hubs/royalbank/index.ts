/**
 * Royal Bank of Arcadia — Barrel Exports
 *
 * Hub Identity: AID-ROYALBANK
 * Pillar:       Norman Hawkins (The Treasurer)
 * Domain:       Financial transactions, credit systems, treasury management,
 *               escrow services, audit trails, currency exchange
 *
 * Architecture:
 *   AI    → RoyalBankOfArcadiaAI (Tier 3 — Domain Orchestrator)
 *   Agent → TellerAgent, AuditorAgent (Tier 4 — Autonomous Microservices)
 *   Bot   → LedgerBot, VaultBot, ExchangeBot (Tier 5 — Stateless Nanoservices)
 */

// ─── Lead AI ────────────────────────────────────────────────────────────────
export { RoyalBankOfArcadiaAI } from './RoyalBankOfArcadiaAI';
export type { Account, Transaction, ExchangeRate as AIExchangeRate, FraudAlert } from './RoyalBankOfArcadiaAI';

// ─── Agents ─────────────────────────────────────────────────────────────────
export { TellerAgent } from './agents/TellerAgent';
export type { TellerInput, AccountBalance, TransactionResult, TellerResult } from './agents/TellerAgent';

export { AuditorAgent } from './agents/AuditorAgent';
export type {
  AuditorInput,
  FraudAlertRecord,
  InspectionResult,
  InspectionFinding,
  ComplianceReport,
  ComplianceViolation,
  SettlementResult,
  AuditorResult,
} from './agents/AuditorAgent';

// ─── Bots ───────────────────────────────────────────────────────────────────
export { LedgerBot } from './bots/LedgerBot';
export type {
  LedgerInput,
  LedgerEntry,
  DoubleEntry,
  LedgerProof,
  RecordResult as LedgerRecordResult,
} from './bots/LedgerBot';

export { VaultBot } from './bots/VaultBot';
export type {
  VaultInput,
  VaultCompartment,
  CompartmentStatus,
  AccessRecord,
  VaultSummary,
  SecureResult,
  VerificationDetail,
} from './bots/VaultBot';

export { ExchangeBot } from './bots/ExchangeBot';
export type {
  ExchangeInput,
  ExchangeRate as BotExchangeRate,
  RateHistoryEntry,
  ConversionDetail,
  RateLock,
  ConvertResult,
} from './bots/ExchangeBot';
