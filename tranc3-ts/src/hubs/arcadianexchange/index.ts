/**
 * Arcadian Exchange — Barrel Exports
 *
 * Hub:      The Arcadian Exchange
 * Pillar:   Savania (The Merchant Queen)
 * Identity: AID-ARCADIANEXCHANGE
 *
 * All types, agents, bots, and the Lead AI are re-exported here
 * for clean upstream imports.
 */

// ─── Lead AI ─────────────────────────────────────────────────────────────────
export { ArcadianExchangeAI } from './ArcadianExchangeAI';
export type {
  Order as AIOrder,
  Trade as AITrade,
  MarketQuote as AIMarketQuote,
  OrderBook as AIOrderBook,
  MarketIndex as AIMarketIndex,
} from './ArcadianExchangeAI';

// ─── Agents ──────────────────────────────────────────────────────────────────
export { BrokerAgent } from './agents/BrokerAgent';
export type {
  BrokerInput,
  BrokerPerception,
  BrokerDecision,
  BrokerActionResult,
  OrderCreation,
  OrderMatch,
  TradeExecution,
  OrderCancellation,
  PositionRecord,
} from './agents/BrokerAgent';

export { AnalystAgent } from './agents/AnalystAgent';
export type {
  AnalystInput,
  AnalystPerception,
  AnalystDecision,
  AnalystActionResult,
  MarketEvaluation,
  TechnicalIndicators,
  PriceForecast,
  AssetComparison,
  MarketAlert,
} from './agents/AnalystAgent';

// ─── Bots ────────────────────────────────────────────────────────────────────
export { OrderBookBot } from './bots/OrderBookBot';
export type {
  OrderBookInput,
  BookLevel,
  OrderBookSnapshot,
  FillRecord,
  MatchResult,
} from './bots/OrderBookBot';

export { TickerBot } from './bots/TickerBot';
export type {
  TickerInput,
  OHLCV,
  QuoteDetail,
  TickerTape,
  QuoteResult,
} from './bots/TickerBot';

export { SettlementBot } from './bots/SettlementBot';
export type {
  SettlementInput,
  SettlementEntry,
  AccountReconciliation,
  SettlementSummary,
  SettlementResult,
} from './bots/SettlementBot';
