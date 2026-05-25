/**
 * The API Marketplace — Barrel Exports
 *
 * Hub:       The API Marketplace
 * Identity:  AID-APIMARKETPLACE
 * Pillar:    The Doctor (The Broker)
 *
 * Pipeline:  Registrar (publish) → Validator (verify) → Router (direct)
 *            BrokerAgent manages API lifecycle and contracts,
 *            TollAgent manages rate limiting and billing
 */

// ─── Lead AI ─────────────────────────────────────────────────────────────────
export { TheAPIMarketplaceAI } from './TheAPIMarketplaceAI';
export type {
  APIEndpoint,
  APIContract,
  APIConsumer,
  APIMetrics,
} from './TheAPIMarketplaceAI';

// ─── Agents ──────────────────────────────────────────────────────────────────
export { BrokerAgent } from './agents/BrokerAgent';
export type {
  BrokerInput,
  LifecycleRecord,
  NegotiationResult,
  BrokerResult,
} from './agents/BrokerAgent';

export { TollAgent } from './agents/TollAgent';
export type {
  TollInput,
  RateLimitPolicy,
  UsageAssessment,
  EnforcementResult,
  UsageReport,
  TollResult,
} from './agents/TollAgent';

// ─── Bots ────────────────────────────────────────────────────────────────────
export { RegistrarBot } from './bots/RegistrarBot';
export type {
  RegistrarInput,
  OpenAPIStub,
  PublishResult,
} from './bots/RegistrarBot';

export { ValidatorBot } from './bots/ValidatorBot';
export type {
  ValidatorInput,
  ValidationItem,
  ValidationReport,
  ValidateResult,
} from './bots/ValidatorBot';

export { RouterBot } from './bots/RouterBot';
export type {
  RouterInput,
  RouteMatch,
  BackendInstance,
  RoutingDecision,
  RouteResult,
} from './bots/RouterBot';
