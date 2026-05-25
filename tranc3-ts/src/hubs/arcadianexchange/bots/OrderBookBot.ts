/**
 * OrderBookBot — Order Matching Engine Bot for The Arcadian Exchange
 *
 * Identity:  NID-ARCADIANEXCHANGE-ORDERBOOK
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    ArcadianExchangeAI (AID-ARCADIANEXCHANGE)
 *
 * Responsibilities:
 *   - Match incoming buy/sell orders against the order book
 *   - Maintain price-time priority for order execution
 *   - Calculate spreads, mid-prices, and depth
 *   - Process market, limit, and stop orders
 *   - Generate order book snapshots and depth profiles
 *
 * "The book never lies — every order has its place in the queue."
 */

import { Bot, Logger, AuditLedger } from '../../../core/definitions';

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface OrderBookInput {
  operation: 'MATCH';
  asset: string;
  orderType: 'buy' | 'sell';
  quantity: number;
  price?: number;
  accountId?: string;
  orderKind?: 'market' | 'limit' | 'stop' | 'stop_limit';
  timeInForce?: 'GTC' | 'IOC' | 'FOK';
}

export interface BookLevel {
  price: number;
  quantity: number;
  orderCount: number;
}

export interface OrderBookSnapshot {
  asset: string;
  bids: BookLevel[];
  asks: BookLevel[];
  spread: number;
  midPrice: number;
  bestBid: number;
  bestAsk: number;
  totalBidDepth: number;
  totalAskDepth: number;
  imbalance: number; // -1 to 1 (negative = sell pressure, positive = buy pressure)
  timestamp: number;
}

export interface FillRecord {
  fillId: string;
  orderId: string;
  side: 'buy' | 'sell';
  asset: string;
  fillPrice: number;
  fillQuantity: number;
  remainingQuantity: number;
  fillType: 'complete' | 'partial';
  timestamp: number;
}

export interface MatchResult {
  success: boolean;
  asset: string;
  incomingSide: 'buy' | 'sell';
  fills: FillRecord[];
  orderBook: OrderBookSnapshot;
  totalFilled: number;
  averageFillPrice: number;
  unfilledQuantity: number;
  matchStatus: 'fully_filled' | 'partially_filled' | 'no_match';
  message: string;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Simulated Order Book Data
// ─────────────────────────────────────────────────────────────────────────────

const ORDER_BOOKS: Record<string, { bids: BookLevel[]; asks: BookLevel[] }> = {
  ARC: {
    bids: [
      { price: 100.00, quantity: 500, orderCount: 3 },
      { price: 99.75, quantity: 1200, orderCount: 5 },
      { price: 99.50, quantity: 800, orderCount: 4 },
      { price: 99.25, quantity: 1500, orderCount: 6 },
      { price: 99.00, quantity: 2000, orderCount: 8 },
    ],
    asks: [
      { price: 100.50, quantity: 400, orderCount: 2 },
      { price: 100.75, quantity: 1000, orderCount: 4 },
      { price: 101.00, quantity: 900, orderCount: 3 },
      { price: 101.25, quantity: 1200, orderCount: 5 },
      { price: 101.50, quantity: 1800, orderCount: 7 },
    ],
  },
  TKN: {
    bids: [
      { price: 1.000, quantity: 50000, orderCount: 12 },
      { price: 0.999, quantity: 80000, orderCount: 15 },
      { price: 0.998, quantity: 60000, orderCount: 10 },
    ],
    asks: [
      { price: 1.005, quantity: 45000, orderCount: 10 },
      { price: 1.006, quantity: 70000, orderCount: 14 },
      { price: 1.007, quantity: 55000, orderCount: 11 },
    ],
  },
  GLD: {
    bids: [
      { price: 1000.00, quantity: 50, orderCount: 2 },
      { price: 998.00, quantity: 80, orderCount: 3 },
      { price: 995.00, quantity: 100, orderCount: 4 },
    ],
    asks: [
      { price: 1015.00, quantity: 40, orderCount: 2 },
      { price: 1018.00, quantity: 70, orderCount: 3 },
      { price: 1020.00, quantity: 90, orderCount: 4 },
    ],
  },
};

let fillCounter = 0;

// ─────────────────────────────────────────────────────────────────────────────
// OrderBookBot Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class OrderBookBot extends Bot {
  private readonly log: Logger;
  private readonly audit: AuditLedger;

  constructor() {
    super(
      'NID-ARCADIANEXCHANGE-ORDERBOOK',
      'OrderBook',
      async (input: OrderBookInput) => this.handle(input),
      'Order matching engine with price-time priority and depth tracking'
    );

    this.log = new Logger('OrderBookBot');
    this.audit = AuditLedger.getInstance();
  }

  private async handle(input: OrderBookInput): Promise<MatchResult> {
    if (input.operation !== 'MATCH') {
      return this.fail(`Unknown operation: ${input.operation}. OrderBookBot only accepts MATCH.`);
    }
    return this.match(input);
  }

  // ─────────────────────────────────────────────────────────────────────────
  // MATCH — Process incoming order against the book
  // ─────────────────────────────────────────────────────────────────────────

  private match(input: OrderBookInput): MatchResult {
    const { asset, orderType, quantity, price, accountId, orderKind } = input;

    if (!asset || !quantity || quantity <= 0) {
      return this.fail('Asset and positive quantity are required');
    }

    if (!orderType) {
      return this.fail('orderType (buy/sell) is required');
    }

    // Get or create order book
    let book = ORDER_BOOKS[asset];
    if (!book) {
      // Generate a simulated book for unknown assets
      const basePrice = price ?? 100;
      book = {
        bids: [
          { price: basePrice * 0.998, quantity: 100, orderCount: 1 },
          { price: basePrice * 0.995, quantity: 200, orderCount: 2 },
          { price: basePrice * 0.990, quantity: 300, orderCount: 3 },
        ],
        asks: [
          { price: basePrice * 1.002, quantity: 100, orderCount: 1 },
          { price: basePrice * 1.005, quantity: 200, orderCount: 2 },
          { price: basePrice * 1.010, quantity: 300, orderCount: 3 },
        ],
      };
      ORDER_BOOKS[asset] = book;
    }

    const fills: FillRecord[] = [];
    let remainingQty = quantity;

    // Match against opposite side of the book
    const oppositeLevels = orderType === 'buy'
      ? [...book.asks].sort((a, b) => a.price - b.price) // Buys match against asks (lowest first)
      : [...book.bids].sort((a, b) => b.price - a.price); // Sells match against bids (highest first)

    const resolvedKind = orderKind ?? 'limit';
    const limitPrice = price ?? (oppositeLevels[0]?.price ?? 0);

    for (const level of oppositeLevels) {
      if (remainingQty <= 0) break;

      // For limit orders, check price constraint
      if (resolvedKind === 'limit' || resolvedKind === 'stop_limit') {
        if (orderType === 'buy' && level.price > limitPrice) break;
        if (orderType === 'sell' && level.price < limitPrice) break;
      }

      // Calculate fill quantity at this level
      const fillQty = Math.min(remainingQty, level.quantity);
      fillCounter++;

      const fill: FillRecord = {
        fillId: `FILL-${fillCounter.toString().padStart(6, '0')}`,
        orderId: `ORD-MATCH-${fillCounter}`,
        side: orderType,
        asset,
        fillPrice: level.price,
        fillQuantity: fillQty,
        remainingQuantity: remainingQty - fillQty,
        fillType: fillQty === remainingQty && fillQty === level.quantity ? 'complete' : 'partial',
        timestamp: Date.now(),
      };

      fills.push(fill);

      // Update book level
      level.quantity -= fillQty;
      level.orderCount = Math.max(0, level.orderCount - 1);

      remainingQty -= fillQty;
    }

    // Remove empty levels
    book.asks = book.asks.filter(l => l.quantity > 0);
    book.bids = book.bids.filter(l => l.quantity > 0);

    // If it's a sell order that was filled, add remaining as new bid
    // If it's a buy order that was filled, add remaining as new ask
    if (remainingQty > 0 && resolvedKind === 'limit') {
      if (orderType === 'buy') {
        const existingLevel = book.bids.find(l => l.price === limitPrice);
        if (existingLevel) {
          existingLevel.quantity += remainingQty;
          existingLevel.orderCount++;
        } else {
          book.bids.push({ price: limitPrice, quantity: remainingQty, orderCount: 1 });
          book.bids.sort((a, b) => b.price - a.price);
        }
      } else {
        const existingLevel = book.asks.find(l => l.price === limitPrice);
        if (existingLevel) {
          existingLevel.quantity += remainingQty;
          existingLevel.orderCount++;
        } else {
          book.asks.push({ price: limitPrice, quantity: remainingQty, orderCount: 1 });
          book.asks.sort((a, b) => a.price - b.price);
        }
      }
    }

    // Build order book snapshot
    const snapshot = this.buildSnapshot(asset, book);

    const totalFilled = fills.reduce((sum, f) => sum + f.fillQuantity, 0);
    const totalValue = fills.reduce((sum, f) => sum + f.fillPrice * f.fillQuantity, 0);
    const avgFillPrice = totalFilled > 0 ? totalValue / totalFilled : 0;

    const matchStatus: MatchResult['matchStatus'] =
      remainingQty === 0 ? 'fully_filled' :
      totalFilled > 0 ? 'partially_filled' : 'no_match';

    this.audit.append({
      actor: 'NID-ARCADIANEXCHANGE-ORDERBOOK',
      action: 'ORDER_MATCHED',
      entity: asset,
      status: totalFilled > 0 ? 'SUCCESS' : 'FAILURE',
      meta: {
        orderType,
        asset,
        requestedQuantity: quantity,
        totalFilled,
        avgFillPrice,
        fillsCount: fills.length,
        matchStatus,
      },
    });

    this.log.info('Order matching completed', {
      asset,
      orderType,
      requestedQuantity: quantity,
      totalFilled,
      avgFillPrice,
      matchStatus,
    });

    return {
      success: totalFilled > 0,
      asset,
      incomingSide: orderType,
      fills,
      orderBook: snapshot,
      totalFilled,
      averageFillPrice: Math.round(avgFillPrice * 100) / 100,
      unfilledQuantity: remainingQty,
      matchStatus,
      message: `${orderType.toUpperCase()} ${quantity} ${asset}: ${totalFilled} filled @ avg ${avgFillPrice.toFixed(2)} (${matchStatus})`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Build Snapshot
  // ─────────────────────────────────────────────────────────────────────────

  private buildSnapshot(asset: string, book: { bids: BookLevel[]; asks: BookLevel[] }): OrderBookSnapshot {
    const bestBid = book.bids.length > 0 ? Math.max(...book.bids.map(b => b.price)) : 0;
    const bestAsk = book.asks.length > 0 ? Math.min(...book.asks.map(a => a.price)) : 0;
    const spread = bestBid > 0 && bestAsk > 0 ? bestAsk - bestBid : 0;
    const midPrice = bestBid > 0 && bestAsk > 0 ? (bestBid + bestAsk) / 2 : 0;

    const totalBidDepth = book.bids.reduce((sum, b) => sum + b.quantity, 0);
    const totalAskDepth = book.asks.reduce((sum, a) => sum + a.quantity, 0);
    const totalDepth = totalBidDepth + totalAskDepth;
    const imbalance = totalDepth > 0 ? (totalBidDepth - totalAskDepth) / totalDepth : 0;

    return {
      asset,
      bids: book.bids.sort((a, b) => b.price - a.price),
      asks: book.asks.sort((a, b) => a.price - b.price),
      spread: Math.round(spread * 100) / 100,
      midPrice: Math.round(midPrice * 100) / 100,
      bestBid,
      bestAsk,
      totalBidDepth,
      totalAskDepth,
      imbalance: Math.round(imbalance * 100) / 100,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Helpers
  // ─────────────────────────────────────────────────────────────────────────

  private fail(message: string): MatchResult {
    this.log.error('Order matching failed', { message });
    return {
      success: false,
      asset: '',
      incomingSide: 'buy',
      fills: [],
      orderBook: {
        asset: '', bids: [], asks: [], spread: 0, midPrice: 0,
        bestBid: 0, bestAsk: 0, totalBidDepth: 0, totalAskDepth: 0, imbalance: 0, timestamp: 0,
      },
      totalFilled: 0,
      averageFillPrice: 0,
      unfilledQuantity: 0,
      matchStatus: 'no_match',
      message,
      timestamp: Date.now(),
    };
  }
}
