/**
 * TickerBot — Market Quote & Price Discovery Bot for The Arcadian Exchange
 *
 * Identity:  NID-ARCADIANEXCHANGE-TICKER
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    ArcadianExchangeAI (AID-ARCADIANEXCHANGE)
 *
 * Responsibilities:
 *   - Provide real-time and historical price quotes
 *   - Track OHLCV (Open, High, Low, Close, Volume) data
 *   - Calculate price changes, moving averages, and derived metrics
 *   - Support multiple quote formats and timeframes
 *   - Generate ticker tape summaries for market dashboards
 *
 * "The ticker tells the story of the market — one price at a time."
 */

import { Bot, Logger, AuditLedger } from '../../../core/definitions'

const auditLedger = new AuditLedger();

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface TickerInput {
  operation: 'QUOTE';
  asset: string;
  timeframe?: '1m' | '5m' | '15m' | '1h' | '4h' | '1d';
  includeHistory?: boolean;
  historyDepth?: number;
}

export interface OHLCV {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  vwap: number;
  tradeCount: number;
}

export interface QuoteDetail {
  asset: string;
  bid: number;
  ask: number;
  last: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  change: number;
  changePercent: number;
  bidSize: number;
  askSize: number;
  lastSize: number;
  previousClose: number;
  dayRange: string;
  yearRange: string;
  marketCap: number;
  fiftyDayAvg: number;
  twoHundredDayAvg: number;
  timestamp: number;
}

export interface TickerTape {
  asset: string;
  symbol: string;
  price: number;
  change: number;
  changePercent: number;
  volume: number;
  signal: '▲' | '▼' | '◆';
  timestamp: number;
}

export interface QuoteResult {
  success: boolean;
  quote: QuoteDetail;
  history: OHLCV[];
  tape: TickerTape;
  message: string;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Simulated Market Data
// ─────────────────────────────────────────────────────────────────────────────

const MARKET_QUOTES: Record<string, {
  bid: number; ask: number; last: number; open: number; high: number; low: number;
  volume: number; previousClose: number; marketCap: number;
  fiftyDayAvg: number; twoHundredDayAvg: number;
}> = {
  ARC: { bid: 100.00, ask: 100.50, last: 100.25, open: 99.00, high: 102.00, low: 98.50, volume: 1250000, previousClose: 99.00, marketCap: 5000000000, fiftyDayAvg: 98.50, twoHundredDayAvg: 95.00 },
  TKN: { bid: 1.000, ask: 1.005, last: 1.002, open: 0.998, high: 1.010, low: 0.995, volume: 5000000, previousClose: 0.998, marketCap: 10000000000, fiftyDayAvg: 0.999, twoHundredDayAvg: 0.985 },
  GLD: { bid: 1000.00, ask: 1015.00, last: 1007.50, open: 1000.00, high: 1020.00, low: 995.00, volume: 250000, previousClose: 1000.00, marketCap: 2500000000, fiftyDayAvg: 995.00, twoHundredDayAvg: 980.00 },
  NRG: { bid: 45.00, ask: 45.50, last: 45.25, open: 44.50, high: 46.00, low: 44.00, volume: 800000, previousClose: 44.50, marketCap: 1800000000, fiftyDayAvg: 44.00, twoHundredDayAvg: 42.00 },
  DAT: { bid: 22.00, ask: 22.25, last: 22.12, open: 21.80, high: 22.50, low: 21.75, volume: 3200000, previousClose: 21.80, marketCap: 2200000000, fiftyDayAvg: 21.50, twoHundredDayAvg: 20.50 },
  KNO: { bid: 150.00, ask: 151.00, last: 150.50, open: 149.00, high: 152.00, low: 148.00, volume: 600000, previousClose: 149.00, marketCap: 7500000000, fiftyDayAvg: 148.00, twoHundredDayAvg: 142.00 },
};

// ─────────────────────────────────────────────────────────────────────────────
// TickerBot Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class TickerBot extends Bot {
  private readonly log: Logger;
  private readonly audit: AuditLedger;

  constructor() {
    super(
      'NID-ARCADIANEXCHANGE-TICKER',
      'Ticker',
      async (input: TickerInput) => this.handle(input),
      'Real-time market quotes with OHLCV history and ticker tape summaries'
    );

    this.log = new Logger('TickerBot');
    this.audit = auditLedger;
  }

  private async handle(input: TickerInput): Promise<QuoteResult> {
    if (input.operation !== 'QUOTE') {
      return this.fail(`Unknown operation: ${input.operation}. TickerBot only accepts QUOTE.`);
    }
    return this.quote(input);
  }

  // ─────────────────────────────────────────────────────────────────────────
  // QUOTE — Generate market quote with history
  // ─────────────────────────────────────────────────────────────────────────

  private quote(input: TickerInput): QuoteResult {
    const { asset, timeframe, includeHistory, historyDepth } = input;

    if (!asset) {
      return this.fail('Asset symbol is required');
    }

    const data = MARKET_QUOTES[asset];
    if (!data) {
      return this.fail(`No quote data available for ${asset}. Valid assets: ${Object.keys(MARKET_QUOTES).join(', ')}`);
    }

    // Apply simulated market micro-movement
    const microVariation = 1 + (Math.random() - 0.5) * 0.002;
    const liveBid = Math.round(data.bid * microVariation * 100) / 100;
    const liveAsk = Math.round(data.ask * microVariation * 100) / 100;
    const liveLast = Math.round(((liveBid + liveAsk) / 2) * 100) / 100;

    const change = liveLast - data.previousClose;
    const changePercent = (change / data.previousClose) * 100;

    // Build quote detail
    const quote: QuoteDetail = {
      asset,
      bid: liveBid,
      ask: liveAsk,
      last: liveLast,
      open: data.open,
      high: Math.max(data.high, liveLast),
      low: Math.min(data.low, liveLast),
      close: liveLast,
      volume: data.volume + Math.floor(Math.random() * 10000),
      change: Math.round(change * 100) / 100,
      changePercent: Math.round(changePercent * 100) / 100,
      bidSize: Math.floor(Math.random() * 500) + 100,
      askSize: Math.floor(Math.random() * 500) + 100,
      lastSize: Math.floor(Math.random() * 200) + 50,
      previousClose: data.previousClose,
      dayRange: `${Math.min(data.low, liveLast)} - ${Math.max(data.high, liveLast)}`,
      yearRange: `${Math.round(data.twoHundredDayAvg * 0.85 * 100) / 100} - ${Math.round(data.high * 1.15 * 100) / 100}`,
      marketCap: data.marketCap,
      fiftyDayAvg: data.fiftyDayAvg,
      twoHundredDayAvg: data.twoHundredDayAvg,
      timestamp: Date.now(),
    };

    // Build ticker tape entry
    const tape: TickerTape = {
      asset,
      symbol: asset,
      price: liveLast,
      change: Math.round(change * 100) / 100,
      changePercent: Math.round(changePercent * 100) / 100,
      volume: quote.volume,
      signal: change > 0 ? '▲' : change < 0 ? '▼' : '◆',
      timestamp: Date.now(),
    };

    // Build OHLCV history if requested
    const history: OHLCV[] = [];
    if (includeHistory !== false) {
      const depth = historyDepth ?? 10;
      const tf = timeframe ?? '1d';
      const intervalMs = this.timeframeToMs(tf);

      for (let i = depth - 1; i >= 0; i--) {
        const ts = Date.now() - i * intervalMs;
        const volatility = (data.high - data.low) / data.open;
        const candleOpen = data.open + (Math.random() - 0.5) * volatility * data.open * 0.3;
        const candleRange = volatility * data.open * 0.2;
        const candleHigh = candleOpen + Math.abs(candleRange) * (0.5 + Math.random());
        const candleLow = candleOpen - Math.abs(candleRange) * (0.5 + Math.random());
        const candleClose = candleLow + Math.random() * (candleHigh - candleLow);

        history.push({
          timestamp: ts,
          open: Math.round(candleOpen * 100) / 100,
          high: Math.round(candleHigh * 100) / 100,
          low: Math.round(candleLow * 100) / 100,
          close: Math.round(candleClose * 100) / 100,
          volume: Math.floor(data.volume / depth * (0.5 + Math.random())),
          vwap: Math.round(((candleHigh + candleLow + candleClose) / 3) * 100) / 100,
          tradeCount: Math.floor(Math.random() * 500) + 100,
        });
      }
    }

    this.audit.append({
      actor: 'NID-ARCADIANEXCHANGE-TICKER',
      action: 'QUOTE_GENERATED',
      entity: asset,
      status: 'SUCCESS',
      meta: {
        lastPrice: liveLast,
        change: quote.change,
        changePercent: quote.changePercent,
        volume: quote.volume,
      },
    });

    this.log.info('Quote generated', {
      asset,
      last: liveLast,
      change: quote.change,
      changePercent: `${quote.changePercent}%`,
    });

    return {
      success: true,
      quote,
      history,
      tape,
      message: `${asset} @ ${liveLast} (${change >= 0 ? '+' : ''}${quote.change} / ${quote.changePercent}%) Vol: ${quote.volume.toLocaleString()}`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Helpers
  // ─────────────────────────────────────────────────────────────────────────

  private timeframeToMs(timeframe: string): number {
    switch (timeframe) {
      case '1m': return 60000;
      case '5m': return 300000;
      case '15m': return 900000;
      case '1h': return 3600000;
      case '4h': return 14400000;
      case '1d': return 86400000;
      default: return 86400000;
    }
  }

  private fail(message: string): QuoteResult {
    this.log.error('Quote generation failed', { message });
    return {
      success: false,
      quote: {
        asset: '', bid: 0, ask: 0, last: 0, open: 0, high: 0, low: 0, close: 0,
        volume: 0, change: 0, changePercent: 0, bidSize: 0, askSize: 0, lastSize: 0,
        previousClose: 0, dayRange: '', yearRange: '', marketCap: 0, fiftyDayAvg: 0,
        twoHundredDayAvg: 0, timestamp: 0,
      },
      history: [],
      tape: { asset: '', symbol: '', price: 0, change: 0, changePercent: 0, volume: 0, signal: '◆', timestamp: 0 },
      message,
      timestamp: Date.now(),
    };
  }
}
