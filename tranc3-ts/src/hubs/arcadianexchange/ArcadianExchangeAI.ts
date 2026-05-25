/**
 * ArcadianExchangeAI — Lead AI for The Arcadian Exchange Hub
 *
 * Identity:  AID-ARCADIANEXCHANGE
 * Pillar:    Savania (The Merchant Queen)
 * Tier:      3 (Lead AI / Domain Orchestrator)
 * Domain:    Marketplace exchange, trading systems, order matching,
 *            market analytics, settlement clearing, price discovery
 *
 * Philosophy: The Exchange is the pulse of Arcadia's economy.
 *             Every bid meets its ask, every order finds its match,
 *             and the market always seeks equilibrium.
 *             Volatility is not chaos — it is opportunity.
 *
 * Pipeline:  OrderBookBot (match) → SettlementBot (clear) → TickerBot (quote)
 *            BrokerAgent manages trading and order lifecycle,
 *            AnalystAgent provides market intelligence and forecasting
 */

import { AI, Agent, Bot, Logger, AuditLedger } from '../../core/definitions'
import { BrokerAgent } from './agents/BrokerAgent';
import { AnalystAgent } from './agents/AnalystAgent';
import { OrderBookBot } from './bots/OrderBookBot';
import { TickerBot } from './bots/TickerBot';
import { SettlementBot } from './bots/SettlementBot';

const auditLedger = new AuditLedger();

// ─────────────────────────────────────────────────────────────────────────────
// Domain Interfaces
// ─────────────────────────────────────────────────────────────────────────────

export interface Order {
  id: string;
  accountId: string;
  type: 'buy' | 'sell';
  orderType: 'market' | 'limit' | 'stop' | 'stop_limit';
  asset: string;
  quantity: number;
  price?: number;       // Required for limit/stop_limit
  stopPrice?: number;   // Required for stop/stop_limit
  status: 'open' | 'partially_filled' | 'filled' | 'cancelled' | 'expired' | 'rejected';
  filledQuantity: number;
  averageFillPrice: number;
  createdAt: number;
  updatedAt: number;
  expiresAt?: number;
  timeInForce: 'GTC' | 'IOC' | 'FOK'; // Good-Till-Cancel, Immediate-Or-Cancel, Fill-Or-Kill
}

export interface Trade {
  id: string;
  buyOrderId: string;
  sellOrderId: string;
  asset: string;
  quantity: number;
  price: number;
  buyerAccountId: string;
  sellerAccountId: string;
  settledAt?: number;
  settlementStatus: 'pending' | 'settled' | 'failed';
  createdAt: number;
}

export interface MarketQuote {
  asset: string;
  bid: number;
  ask: number;
  last: number;
  high: number;
  low: number;
  open: number;
  volume: number;
  change: number;
  changePercent: number;
  timestamp: number;
}

export interface OrderBook {
  asset: string;
  bids: { price: number; quantity: number; orderCount: number }[];
  asks: { price: number; quantity: number; orderCount: number }[];
  spread: number;
  midPrice: number;
  timestamp: number;
}

export interface MarketIndex {
  name: string;
  value: number;
  change: number;
  changePercent: number;
  constituents: string[];
  lastRebalanced: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// ArcadianExchangeAI Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class ArcadianExchangeAI extends AI {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private orders: Map<string, Order>;
  private trades: Map<string, Trade>;
  private quotes: Map<string, MarketQuote>;
  private orderBooks: Map<string, OrderBook>;
  private indices: Map<string, MarketIndex>;

  constructor() {
    super(
      'AID-ARCADIANEXCHANGE',
      'ArcadianExchange',
      'arcadianexchange',
      'Savania',
      3
    );

    this.log = new Logger('ArcadianExchangeAI');
    this.audit = auditLedger;
    this.orders = new Map();
    this.trades = new Map();
    this.quotes = new Map();
    this.orderBooks = new Map();
    this.indices = new Map();

    // Register Agents
    this.registerAgent(new BrokerAgent());
    this.registerAgent(new AnalystAgent());

    // Register Bots
    this.registerBot(new OrderBookBot());
    this.registerBot(new TickerBot());
    this.registerBot(new SettlementBot());

    // Initialise market data with seed quotes
    this.initialiseMarket();

    this.log.info('ArcadianExchangeAI initialised', {
      agents: this.listAgentIds(),
      bots: this.listBotNames(),
      listedAssets: this.quotes.size,
      message: 'The Exchange is open. Every bid finds its ask. 📈',
    });
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Market Initialisation
  // ─────────────────────────────────────────────────────────────────────────

  private initialiseMarket(): void {
    const seedQuotes: MarketQuote[] = [
      { asset: 'ARC', bid: 100.00, ask: 100.50, last: 100.25, high: 102.00, low: 98.50, open: 99.00, volume: 1250000, change: 1.25, changePercent: 1.26, timestamp: Date.now() },
      { asset: 'TKN', bid: 1.000, ask: 1.005, last: 1.002, high: 1.010, low: 0.995, open: 0.998, volume: 5000000, change: 0.004, changePercent: 0.40, timestamp: Date.now() },
      { asset: 'GLD', bid: 1000.00, ask: 1015.00, last: 1007.50, high: 1020.00, low: 995.00, open: 1000.00, volume: 250000, change: 7.50, changePercent: 0.75, timestamp: Date.now() },
      { asset: 'NRG', bid: 45.00, ask: 45.50, last: 45.25, high: 46.00, low: 44.00, open: 44.50, volume: 800000, change: 0.75, changePercent: 1.69, timestamp: Date.now() },
      { asset: 'DAT', bid: 22.00, ask: 22.25, last: 22.12, high: 22.50, low: 21.75, open: 21.80, volume: 3200000, change: 0.32, changePercent: 1.47, timestamp: Date.now() },
      { asset: 'KNO', bid: 150.00, ask: 151.00, last: 150.50, high: 152.00, low: 148.00, open: 149.00, volume: 600000, change: 1.50, changePercent: 1.01, timestamp: Date.now() },
    ];

    for (const quote of seedQuotes) {
      this.quotes.set(quote.asset, quote);
    }

    // Initialise the Arcadian Composite Index
    this.indices.set('ACI', {
      name: 'Arcadian Composite Index',
      value: 5260.75,
      change: 42.30,
      changePercent: 0.81,
      constituents: ['ARC', 'TKN', 'GLD', 'NRG', 'DAT', 'KNO'],
      lastRebalanced: Date.now() - 30 * 86400000,
    });
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Order Management
  // ─────────────────────────────────────────────────────────────────────────

  getOrder(id: string): Order | undefined {
    return this.orders.get(id);
  }

  getOrders(): Order[] {
    return Array.from(this.orders.values());
  }

  getTrades(): Trade[] {
    return Array.from(this.trades.values());
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Market Data
  // ─────────────────────────────────────────────────────────────────────────

  getQuote(asset: string): MarketQuote | undefined {
    return this.quotes.get(asset);
  }

  getAllQuotes(): MarketQuote[] {
    return Array.from(this.quotes.values());
  }

  getOrderBook(asset: string): OrderBook | undefined {
    return this.orderBooks.get(asset);
  }

  getIndex(name: string): MarketIndex | undefined {
    return this.indices.get(name);
  }

  getIndices(): MarketIndex[] {
    return Array.from(this.indices.values());
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Bot Delegations
  // ─────────────────────────────────────────────────────────────────────────

  /**
   * Match orders via OrderBookBot.
   */
  async matchOrders(
    asset: string,
    orderType: 'buy' | 'sell',
    quantity: number,
    price?: number
  ): Promise<unknown> {
    const orderBook = this.getBot('OrderBook')!;
    const result = await orderBook.execute({
      operation: 'MATCH',
      asset,
      orderType,
      quantity,
      price,
    });
    return result;
  }

  /**
   * Get current quote via TickerBot.
   */
  async getTickerQuote(asset: string): Promise<unknown> {
    const ticker = this.getBot('Ticker')!;
    const result = await ticker.execute({
      operation: 'QUOTE',
      asset,
    });
    return result;
  }

  /**
   * Clear and settle trades via SettlementBot.
   */
  async settleTrade(tradeId: string): Promise<unknown> {
    const settlement = this.getBot('Settlement')!;
    const result = await settlement.execute({
      operation: 'CLEAR',
      tradeId,
    });
    return result;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Agent Delegations
  // ─────────────────────────────────────────────────────────────────────────

  /**
   * Manage trading orders via BrokerAgent.
   */
  async manageOrder(
    operation: 'list' | 'match' | 'execute' | 'cancel',
    params: Record<string, unknown>
  ): Promise<unknown> {
    const broker = this.getAgent('SID-ARCADIANEXCHANGE-BROKER') as BrokerAgent;
    const result = await broker.runCycle({
      operation,
      ...params,
    });
    return result;
  }

  /**
   * Analyse market conditions via AnalystAgent.
   */
  async analyseMarket(
    operation: 'evaluate' | 'forecast' | 'compare' | 'alert',
    params: Record<string, unknown>
  ): Promise<unknown> {
    const analyst = this.getAgent('SID-ARCADIANEXCHANGE-ANALYST') as AnalystAgent;
    const result = await analyst.runCycle({
      operation,
      ...params,
    });
    return result;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Health Check
  // ─────────────────────────────────────────────────────────────────────────

  healthCheck(): {
    status: 'healthy' | 'degraded' | 'critical';
    listedAssets: number;
    openOrders: number;
    completedTrades: number;
    marketOpen: boolean;
    indices: number;
    agents: number;
    bots: number;
    timestamp: number;
  } {
    const openOrders = Array.from(this.orders.values())
      .filter(o => o.status === 'open' || o.status === 'partially_filled').length;
    const completedTrades = Array.from(this.trades.values())
      .filter(t => t.settlementStatus === 'settled').length;

    return {
      status: 'healthy',
      listedAssets: this.quotes.size,
      openOrders,
      completedTrades,
      marketOpen: true,
      indices: this.indices.size,
      agents: this.listAgentIds().length,
      bots: this.listBotNames().length,
      timestamp: Date.now(),
    };
  }
}
