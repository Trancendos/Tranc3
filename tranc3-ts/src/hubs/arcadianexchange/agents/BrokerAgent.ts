/**
 * BrokerAgent — Trading & Order Lifecycle Agent for The Arcadian Exchange
 *
 * Identity:  SID-ARCADIANEXCHANGE-BROKER
 * Tier:      4 (Autonomous Microservice)
 * Parent:    ArcadianExchangeAI (AID-ARCADIANEXCHANGE)
 *
 * Responsibilities:
 *   - List new orders on the exchange (buy/sell, market/limit/stop)
 *   - Match compatible buy and sell orders
 *   - Execute trades when orders are filled
 *   - Cancel open orders and manage order lifecycle
 *   - Track position summaries and order history
 *
 * "The broker's ledger never sleeps — every order finds its destiny."
 */

import { Agent, Logger, AuditLedger } from '../../../core/definitions';

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface BrokerInput {
  operation: 'list' | 'match' | 'execute' | 'cancel';
  accountId?: string;
  asset?: string;
  orderType?: 'buy' | 'sell';
  orderKind?: 'market' | 'limit' | 'stop' | 'stop_limit';
  quantity?: number;
  price?: number;
  stopPrice?: number;
  timeInForce?: 'GTC' | 'IOC' | 'FOK';
  orderId?: string;
  reason?: string;
}

export interface OrderRecord {
  id: string;
  accountId: string;
  side: 'buy' | 'sell';
  kind: 'market' | 'limit' | 'stop' | 'stop_limit';
  asset: string;
  quantity: number;
  price?: number;
  stopPrice?: number;
  timeInForce: 'GTC' | 'IOC' | 'FOK';
  status: 'open' | 'partially_filled' | 'filled' | 'cancelled' | 'expired' | 'rejected';
  filledQuantity: number;
  averageFillPrice: number;
  createdAt: number;
  updatedAt: number;
}

export interface MatchResult {
  matched: boolean;
  buyOrderId: string;
  sellOrderId: string;
  matchPrice: number;
  matchQuantity: number;
  matchId: string;
  timestamp: number;
}

export interface ExecutionResult {
  tradeId: string;
  buyOrderId: string;
  sellOrderId: string;
  asset: string;
  quantity: number;
  price: number;
  buyerAccountId: string;
  sellerAccountId: string;
  commission: number;
  executedAt: number;
}

export interface PositionSummary {
  accountId: string;
  asset: string;
  totalBought: number;
  totalSold: number;
  netPosition: number;
  averageBuyPrice: number;
  averageSellPrice: number;
  unrealisedPnL: number;
  openOrders: number;
}

export interface BrokerResult {
  success: boolean;
  operation: BrokerInput['operation'];
  order?: OrderRecord;
  match?: MatchResult;
  execution?: ExecutionResult;
  position?: PositionSummary;
  message: string;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Order Store (Simulated)
// ─────────────────────────────────────────────────────────────────────────────

const COMMISSION_RATE = 0.001; // 0.1% commission
const VALID_ASSETS = ['ARC', 'TKN', 'GLD', 'NRG', 'DAT', 'KNO'];

// ─────────────────────────────────────────────────────────────────────────────
// BrokerAgent Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class BrokerAgent extends Agent {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private readonly orders: Map<string, OrderRecord>;
  private readonly positions: Map<string, PositionSummary>;
  private orderCounter: number;
  private tradeCounter: number;

  constructor() {
    super('SID-ARCADIANEXCHANGE-BROKER');
    this.log = new Logger('BrokerAgent');
    this.audit = AuditLedger.getInstance();
    this.orders = new Map();
    this.positions = new Map();
    this.orderCounter = 0;
    this.tradeCounter = 0;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Agent Lifecycle: Perceive → Decide → Act
  // ─────────────────────────────────────────────────────────────────────────

  protected async perceive(input: BrokerInput): Promise<BrokerInput> {
    this.log.info('Perceiving broker operation', { operation: input.operation });

    if (input.operation === 'list') {
      if (!input.asset || !VALID_ASSETS.includes(input.asset)) {
        this.log.warn('Invalid or missing asset', { asset: input.asset });
      }
      if (!input.quantity || input.quantity <= 0) {
        this.log.warn('Invalid quantity', { quantity: input.quantity });
      }
    }

    if (input.operation === 'cancel' && !input.orderId) {
      this.log.warn('Cancel operation requires orderId');
    }

    return input;
  }

  protected async decide(input: BrokerInput): Promise<string> {
    this.log.info('Deciding broker action', { operation: input.operation });

    switch (input.operation) {
      case 'list': return 'listOrder';
      case 'match': return 'matchOrders';
      case 'execute': return 'executeTrade';
      case 'cancel': return 'cancelOrder';
      default: return 'unknown';
    }
  }

  protected async act(input: BrokerInput, decision: string): Promise<BrokerResult> {
    this.log.info('Acting on broker decision', { decision });

    switch (decision) {
      case 'listOrder': return this.listOrder(input);
      case 'matchOrders': return this.matchOrders(input);
      case 'executeTrade': return this.executeTrade(input);
      case 'cancelOrder': return this.cancelOrder(input);
      default:
        return {
          success: false,
          operation: input.operation,
          message: `Unknown broker operation: ${input.operation}`,
          timestamp: Date.now(),
        };
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // List — Create a new order
  // ─────────────────────────────────────────────────────────────────────────

  private listOrder(input: BrokerInput): BrokerResult {
    const { accountId, asset, orderType, orderKind, quantity, price, stopPrice, timeInForce } = input;

    if (!accountId || !asset || !quantity || quantity <= 0) {
      return {
        success: false,
        operation: 'list',
        message: 'accountId, asset, and positive quantity are required',
        timestamp: Date.now(),
      };
    }

    if (!VALID_ASSETS.includes(asset)) {
      return {
        success: false,
        operation: 'list',
        message: `Invalid asset: ${asset}. Valid assets: ${VALID_ASSETS.join(', ')}`,
        timestamp: Date.now(),
      };
    }

    const resolvedSide = orderType ?? 'buy';
    const resolvedKind = orderKind ?? 'limit';
    const resolvedTIF = timeInForce ?? 'GTC';

    // Validate price requirements
    if ((resolvedKind === 'limit' || resolvedKind === 'stop_limit') && !price) {
      return {
        success: false,
        operation: 'list',
        message: `Price is required for ${resolvedKind} orders`,
        timestamp: Date.now(),
      };
    }

    if ((resolvedKind === 'stop' || resolvedKind === 'stop_limit') && !stopPrice) {
      return {
        success: false,
        operation: 'list',
        message: `stopPrice is required for ${resolvedKind} orders`,
        timestamp: Date.now(),
      };
    }

    // Create order
    this.orderCounter++;
    const orderId = `ORD-${this.orderCounter.toString().padStart(6, '0')}`;

    const order: OrderRecord = {
      id: orderId,
      accountId,
      side: resolvedSide,
      kind: resolvedKind,
      asset,
      quantity,
      price,
      stopPrice,
      timeInForce: resolvedTIF,
      status: 'open',
      filledQuantity: 0,
      averageFillPrice: 0,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };

    this.orders.set(orderId, order);

    // Market orders attempt immediate fill
    if (resolvedKind === 'market') {
      order.status = 'filled';
      order.filledQuantity = quantity;
      order.averageFillPrice = price ?? 100; // Use provided price or simulated market price
      order.updatedAt = Date.now();
    }

    this.audit.append({
      actor: this.id,
      action: 'ORDER_LISTED',
      entity: orderId,
      status: 'SUCCESS',
      meta: {
        accountId,
        asset,
        side: resolvedSide,
        kind: resolvedKind,
        quantity,
        price,
        status: order.status,
      },
    });

    this.log.info('Order listed', {
      orderId,
      accountId,
      asset,
      side: resolvedSide,
      kind: resolvedKind,
      quantity,
      price,
    });

    return {
      success: true,
      operation: 'list',
      order,
      message: `${resolvedSide.toUpperCase()} ${resolvedKind} order ${orderId}: ${quantity} ${asset}${price ? ` @ ${price}` : ''} [${order.status}]`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Match — Find compatible buy/sell orders
  // ─────────────────────────────────────────────────────────────────────────

  private matchOrders(input: BrokerInput): BrokerResult {
    const { asset, quantity, price } = input;

    if (!asset) {
      return {
        success: false,
        operation: 'match',
        message: 'Asset is required for order matching',
        timestamp: Date.now(),
      };
    }

    // Find open buy and sell orders for this asset
    const openBuys = Array.from(this.orders.values())
      .filter(o => o.asset === asset && o.side === 'buy' && o.status === 'open')
      .sort((a, b) => (b.price ?? 0) - (a.price ?? 0)); // Highest bid first

    const openSells = Array.from(this.orders.values())
      .filter(o => o.asset === asset && o.side === 'sell' && o.status === 'open')
      .sort((a, b) => (a.price ?? Infinity) - (b.price ?? Infinity)); // Lowest ask first

    if (openBuys.length === 0 || openSells.length === 0) {
      return {
        success: false,
        operation: 'match',
        message: `No matching orders for ${asset}. ${openBuys.length} buys, ${openSells.length} sells available.`,
        timestamp: Date.now(),
      };
    }

    // Find best match
    const bestBuy = openBuys[0];
    const bestSell = openSells[0];

    // Check if prices cross (buy price >= sell price)
    const buyPrice = bestBuy.price ?? 0;
    const sellPrice = bestSell.price ?? Infinity;

    if (buyPrice < sellPrice) {
      return {
        success: false,
        operation: 'match',
        message: `No price overlap for ${asset}. Best bid: ${buyPrice}, Best ask: ${sellPrice}. Spread: ${(sellPrice - buyPrice).toFixed(2)}`,
        timestamp: Date.now(),
      };
    }

    // Determine match price and quantity
    const matchPrice = (buyPrice + sellPrice) / 2;
    const matchQuantity = Math.min(
      bestBuy.quantity - bestBuy.filledQuantity,
      bestSell.quantity - bestSell.filledQuantity,
      quantity ?? Infinity
    );

    const matchId = `MATCH-${this.orderCounter}`;

    const match: MatchResult = {
      matched: true,
      buyOrderId: bestBuy.id,
      sellOrderId: bestSell.id,
      matchPrice,
      matchQuantity,
      matchId,
      timestamp: Date.now(),
    };

    this.audit.append({
      actor: this.id,
      action: 'ORDERS_MATCHED',
      entity: matchId,
      status: 'SUCCESS',
      meta: {
        asset,
        buyOrderId: bestBuy.id,
        sellOrderId: bestSell.id,
        matchPrice,
        matchQuantity,
      },
    });

    this.log.info('Orders matched', {
      matchId,
      asset,
      buyOrderId: bestBuy.id,
      sellOrderId: bestSell.id,
      matchPrice,
      matchQuantity,
    });

    return {
      success: true,
      operation: 'match',
      match,
      message: `Matched ${matchQuantity} ${asset} @ ${matchPrice.toFixed(2)} (Buy: ${bestBuy.id}, Sell: ${bestSell.id})`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Execute — Execute a trade from matched orders
  // ─────────────────────────────────────────────────────────────────────────

  private executeTrade(input: BrokerInput): BrokerResult {
    const { asset, quantity, price, accountId } = input;

    if (!asset || !quantity || !price) {
      return {
        success: false,
        operation: 'execute',
        message: 'asset, quantity, and price are required for trade execution',
        timestamp: Date.now(),
      };
    }

    this.tradeCounter++;
    const tradeId = `TRD-${this.tradeCounter.toString().padStart(6, '0')}`;

    const commission = Math.round(quantity * price * COMMISSION_RATE * 100) / 100;

    const execution: ExecutionResult = {
      tradeId,
      buyOrderId: `ORD-EXEC-BUY-${this.tradeCounter}`,
      sellOrderId: `ORD-EXEC-SELL-${this.tradeCounter}`,
      asset,
      quantity,
      price,
      buyerAccountId: accountId ?? 'ACC-TRADER-1',
      sellerAccountId: 'ACC-TRADER-2',
      commission,
      executedAt: Date.now(),
    };

    // Update position
    this.updatePosition(execution.buyerAccountId, asset, quantity, price, 'buy');
    this.updatePosition(execution.sellerAccountId, asset, quantity, price, 'sell');

    this.audit.append({
      actor: this.id,
      action: 'TRADE_EXECUTED',
      entity: tradeId,
      status: 'SUCCESS',
      meta: {
        asset,
        quantity,
        price,
        commission,
        buyerAccountId: execution.buyerAccountId,
        sellerAccountId: execution.sellerAccountId,
      },
    });

    this.log.info('Trade executed', {
      tradeId,
      asset,
      quantity,
      price,
      commission,
    });

    return {
      success: true,
      operation: 'execute',
      execution,
      message: `Executed trade ${tradeId}: ${quantity} ${asset} @ ${price} (commission: ${commission})`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Cancel — Cancel an open order
  // ─────────────────────────────────────────────────────────────────────────

  private cancelOrder(input: BrokerInput): BrokerResult {
    const { orderId, reason } = input;

    if (!orderId) {
      return {
        success: false,
        operation: 'cancel',
        message: 'Order ID is required to cancel an order',
        timestamp: Date.now(),
      };
    }

    const order = this.orders.get(orderId);
    if (!order) {
      return {
        success: false,
        operation: 'cancel',
        message: `Order ${orderId} not found`,
        timestamp: Date.now(),
      };
    }

    if (order.status !== 'open' && order.status !== 'partially_filled') {
      return {
        success: false,
        operation: 'cancel',
        message: `Order ${orderId} cannot be cancelled (current status: ${order.status})`,
        timestamp: Date.now(),
      };
    }

    const resolvedReason = reason ?? 'User requested cancellation';

    order.status = 'cancelled';
    order.updatedAt = Date.now();

    this.audit.append({
      actor: this.id,
      action: 'ORDER_CANCELLED',
      entity: orderId,
      status: 'SUCCESS',
      meta: {
        accountId: order.accountId,
        asset: order.asset,
        side: order.side,
        unfilledQuantity: order.quantity - order.filledQuantity,
        reason: resolvedReason,
      },
    });

    this.log.info('Order cancelled', {
      orderId,
      accountId: order.accountId,
      asset: order.asset,
      reason: resolvedReason,
    });

    return {
      success: true,
      operation: 'cancel',
      order,
      message: `Order ${orderId} cancelled: ${order.side} ${order.quantity} ${order.asset} (${resolvedReason})`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Helpers
  // ─────────────────────────────────────────────────────────────────────────

  private updatePosition(
    accountId: string,
    asset: string,
    quantity: number,
    price: number,
    side: 'buy' | 'sell'
  ): void {
    const key = `${accountId}:${asset}`;
    let position = this.positions.get(key);

    if (!position) {
      position = {
        accountId,
        asset,
        totalBought: 0,
        totalSold: 0,
        netPosition: 0,
        averageBuyPrice: 0,
        averageSellPrice: 0,
        unrealisedPnL: 0,
        openOrders: 0,
      };
      this.positions.set(key, position);
    }

    if (side === 'buy') {
      const totalCost = position.averageBuyPrice * position.totalBought + price * quantity;
      position.totalBought += quantity;
      position.averageBuyPrice = totalCost / position.totalBought;
    } else {
      const totalRevenue = position.averageSellPrice * position.totalSold + price * quantity;
      position.totalSold += quantity;
      position.averageSellPrice = totalRevenue / position.totalSold;
    }

    position.netPosition = position.totalBought - position.totalSold;
    position.unrealisedPnL = (position.averageSellPrice * position.totalSold) -
      (position.averageBuyPrice * position.totalBought);
  }
}
