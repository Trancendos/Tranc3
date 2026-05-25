/**
 * AnalystAgent — Market Intelligence & Forecasting Agent for The Arcadian Exchange
 *
 * Identity:  SID-ARCADIANEXCHANGE-ANALYST
 * Tier:      4 (Autonomous Microservice)
 * Parent:    ArcadianExchangeAI (AID-ARCADIANEXCHANGE)
 *
 * Responsibilities:
 *   - Evaluate current market conditions and trend strength
 *   - Forecast future price movements using technical indicators
 *   - Compare assets across multiple performance dimensions
 *   - Generate alerts for significant market events
 *   - Produce market reports with actionable insights
 *
 * "The Analyst reads the market's pulse — past patterns illuminate future paths."
 */

import { Agent, Logger, AuditLedger } from '../../../core/definitions';

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface AnalystInput {
  operation: 'evaluate' | 'forecast' | 'compare' | 'alert';
  asset?: string;
  assets?: string[];
  timeframe?: '1h' | '4h' | '1d' | '1w' | '1m';
  indicators?: ('SMA' | 'EMA' | 'RSI' | 'MACD' | 'BB' | 'VWAP')[];
  thresholdPercent?: number;
  alertType?: 'price_breakout' | 'volume_spike' | 'trend_reversal' | 'support_breach' | 'resistance_breach';
}

export interface MarketEvaluation {
  asset: string;
  timestamp: number;
  currentPrice: number;
  trend: 'bullish' | 'bearish' | 'sideways';
  trendStrength: number; // 0-100
  momentum: 'accelerating' | 'decelerating' | 'stable';
  volatility: 'low' | 'moderate' | 'high' | 'extreme';
  volumeProfile: 'above_average' | 'average' | 'below_average';
  indicators: TechnicalIndicator[];
  signal: 'strong_buy' | 'buy' | 'hold' | 'sell' | 'strong_sell';
  confidence: number; // 0-100
}

export interface TechnicalIndicator {
  name: string;
  value: number;
  signal: 'bullish' | 'bearish' | 'neutral';
  interpretation: string;
}

export interface PriceForecast {
  asset: string;
  currentPrice: number;
  timeframe: AnalystInput['timeframe'];
  predictions: {
    period: string;
    predictedPrice: number;
    lowerBound: number;
    upperBound: number;
    confidence: number;
  }[];
  trendContinuation: number; // 0-100 probability
  keyLevels: {
    support: number[];
    resistance: number[];
  };
  riskLevel: 'low' | 'moderate' | 'high' | 'very_high';
  forecastedAt: number;
}

export interface AssetComparison {
  assets: string[];
  dimensions: {
    dimension: string;
    rankings: { asset: string; value: number; rank: number }[];
  }[];
  overallRanking: { asset: string; score: number; rank: number }[];
  correlationMatrix: Record<string, Record<string, number>>;
  comparedAt: number;
}

export interface MarketAlert {
  alertId: string;
  asset: string;
  alertType: AnalystInput['alertType'];
  severity: 'info' | 'warning' | 'critical';
  title: string;
  description: string;
  currentValue: number;
  thresholdValue: number;
  triggeredAt: number;
  recommendedAction: string;
}

export interface AnalystResult {
  success: boolean;
  operation: AnalystInput['operation'];
  evaluation?: MarketEvaluation;
  forecast?: PriceForecast;
  comparison?: AssetComparison;
  alert?: MarketAlert;
  message: string;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Simulated Market Data
// ─────────────────────────────────────────────────────────────────────────────

const MARKET_DATA: Record<string, {
  price: number; volume: number; dayHigh: number; dayLow: number;
  sma20: number; ema12: number; rsi: number; macd: number; bbUpper: number; bbLower: number; vwap: number;
}> = {
  ARC: { price: 100.25, volume: 1250000, dayHigh: 102.00, dayLow: 98.50, sma20: 99.80, ema12: 100.10, rsi: 58.5, macd: 0.45, bbUpper: 103.50, bbLower: 96.10, vwap: 100.05 },
  TKN: { price: 1.002, volume: 5000000, dayHigh: 1.010, dayLow: 0.995, sma20: 1.001, ema12: 1.002, rsi: 52.1, macd: 0.001, bbUpper: 1.008, bbLower: 0.994, vwap: 1.003 },
  GLD: { price: 1007.50, volume: 250000, dayHigh: 1020.00, dayLow: 995.00, sma20: 1002.00, ema12: 1005.00, rsi: 61.3, macd: 5.50, bbUpper: 1030.00, bbLower: 974.00, vwap: 1008.00 },
  NRG: { price: 45.25, volume: 800000, dayHigh: 46.00, dayLow: 44.00, sma20: 44.80, ema12: 45.10, rsi: 64.2, macd: 0.85, bbUpper: 47.50, bbLower: 42.10, vwap: 45.00 },
  DAT: { price: 22.12, volume: 3200000, dayHigh: 22.50, dayLow: 21.75, sma20: 21.95, ema12: 22.05, rsi: 56.8, macd: 0.32, bbUpper: 23.00, bbLower: 20.90, vwap: 22.08 },
  KNO: { price: 150.50, volume: 600000, dayHigh: 152.00, dayLow: 148.00, sma20: 149.50, ema12: 150.10, rsi: 59.1, macd: 1.20, bbUpper: 154.00, bbLower: 145.00, vwap: 150.25 },
};

// ─────────────────────────────────────────────────────────────────────────────
// AnalystAgent Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class AnalystAgent extends Agent {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private alertCounter: number;

  constructor() {
    super('SID-ARCADIANEXCHANGE-ANALYST');
    this.log = new Logger('AnalystAgent');
    this.audit = AuditLedger.getInstance();
    this.alertCounter = 0;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Agent Lifecycle: Perceive → Decide → Act
  // ─────────────────────────────────────────────────────────────────────────

  protected async perceive(input: AnalystInput): Promise<AnalystInput> {
    this.log.info('Perceiving analyst operation', { operation: input.operation });

    if (input.operation === 'evaluate' && !input.asset) {
      this.log.warn('Evaluate operation requires asset — defaulting to ARC');
      input.asset = 'ARC';
    }

    if (input.operation === 'compare' && (!input.assets || input.assets.length < 2)) {
      this.log.warn('Compare operation requires at least 2 assets — defaulting to all');
      input.assets = Object.keys(MARKET_DATA);
    }

    if (input.operation === 'forecast' && !input.asset) {
      this.log.warn('Forecast operation requires asset — defaulting to ARC');
      input.asset = 'ARC';
    }

    return input;
  }

  protected async decide(input: AnalystInput): Promise<string> {
    this.log.info('Deciding analyst action', { operation: input.operation });

    switch (input.operation) {
      case 'evaluate': return 'evaluateMarket';
      case 'forecast': return 'forecastPrice';
      case 'compare': return 'compareAssets';
      case 'alert': return 'generateAlert';
      default: return 'unknown';
    }
  }

  protected async act(input: AnalystInput, decision: string): Promise<AnalystResult> {
    this.log.info('Acting on analyst decision', { decision });

    switch (decision) {
      case 'evaluateMarket': return this.evaluateMarket(input);
      case 'forecastPrice': return this.forecastPrice(input);
      case 'compareAssets': return this.compareAssets(input);
      case 'generateAlert': return this.generateAlert(input);
      default:
        return {
          success: false,
          operation: input.operation,
          message: `Unknown analyst operation: ${input.operation}`,
          timestamp: Date.now(),
        };
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Evaluate — Assess current market conditions
  // ─────────────────────────────────────────────────────────────────────────

  private evaluateMarket(input: AnalystInput): AnalystResult {
    const { asset, indicators } = input;
    const resolvedAsset = asset ?? 'ARC';

    const data = MARKET_DATA[resolvedAsset];
    if (!data) {
      return {
        success: false,
        operation: 'evaluate',
        message: `No market data available for ${resolvedAsset}`,
        timestamp: Date.now(),
      };
    }

    // Calculate technical indicators
    const requestedIndicators = indicators ?? ['SMA', 'EMA', 'RSI', 'MACD', 'BB', 'VWAP'];
    const techIndicators: TechnicalIndicator[] = [];

    if (requestedIndicators.includes('SMA')) {
      techIndicators.push({
        name: 'SMA(20)',
        value: data.sma20,
        signal: data.price > data.sma20 ? 'bullish' : 'bearish',
        interpretation: data.price > data.sma20
          ? `Price ${data.price} above SMA(20) ${data.sma20} — bullish trend`
          : `Price ${data.price} below SMA(20) ${data.sma20} — bearish trend`,
      });
    }

    if (requestedIndicators.includes('EMA')) {
      techIndicators.push({
        name: 'EMA(12)',
        value: data.ema12,
        signal: data.price > data.ema12 ? 'bullish' : 'bearish',
        interpretation: `EMA(12) at ${data.ema12} — ${data.price > data.ema12 ? 'supporting uptrend' : 'indicating downtrend'}`,
      });
    }

    if (requestedIndicators.includes('RSI')) {
      const rsiSignal: TechnicalIndicator['signal'] =
        data.rsi > 70 ? 'bearish' : data.rsi < 30 ? 'bullish' : 'neutral';
      techIndicators.push({
        name: 'RSI(14)',
        value: data.rsi,
        signal: rsiSignal,
        interpretation: data.rsi > 70 ? 'Overbought — potential reversal' :
          data.rsi < 30 ? 'Oversold — potential bounce' : 'Neutral range',
      });
    }

    if (requestedIndicators.includes('MACD')) {
      techIndicators.push({
        name: 'MACD',
        value: data.macd,
        signal: data.macd > 0 ? 'bullish' : 'bearish',
        interpretation: `MACD at ${data.macd} — ${data.macd > 0 ? 'bullish momentum' : 'bearish momentum'}`,
      });
    }

    if (requestedIndicators.includes('BB')) {
      const bbPosition = (data.price - data.bbLower) / (data.bbUpper - data.bbLower);
      techIndicators.push({
        name: 'Bollinger Bands',
        value: bbPosition * 100,
        signal: bbPosition > 0.8 ? 'bearish' : bbPosition < 0.2 ? 'bullish' : 'neutral',
        interpretation: `Price at ${(bbPosition * 100).toFixed(1)}% of BB range — ${bbPosition > 0.8 ? 'near upper band' : bbPosition < 0.2 ? 'near lower band' : 'mid-range'}`,
      });
    }

    if (requestedIndicators.includes('VWAP')) {
      techIndicators.push({
        name: 'VWAP',
        value: data.vwap,
        signal: data.price > data.vwap ? 'bullish' : 'bearish',
        interpretation: `VWAP at ${data.vwap} — ${data.price > data.vwap ? 'buyers in control' : 'sellers in control'}`,
      });
    }

    // Determine overall trend
    const bullishCount = techIndicators.filter(i => i.signal === 'bullish').length;
    const bearishCount = techIndicators.filter(i => i.signal === 'bearish').length;
    const trend: MarketEvaluation['trend'] =
      bullishCount > bearishCount + 1 ? 'bullish' :
      bearishCount > bullishCount + 1 ? 'bearish' : 'sideways';

    const trendStrength = Math.abs(bullishCount - bearishCount) / techIndicators.length * 100;

    // Determine signal
    const signalScore = (bullishCount - bearishCount) / techIndicators.length;
    const signal: MarketEvaluation['signal'] =
      signalScore > 0.5 ? 'strong_buy' :
      signalScore > 0.15 ? 'buy' :
      signalScore < -0.5 ? 'strong_sell' :
      signalScore < -0.15 ? 'sell' : 'hold';

    // Volatility assessment
    const dayRange = (data.dayHigh - data.dayLow) / data.price * 100;
    const volatility: MarketEvaluation['volatility'] =
      dayRange > 5 ? 'extreme' :
      dayRange > 3 ? 'high' :
      dayRange > 1.5 ? 'moderate' : 'low';

    // Momentum
    const momentum: MarketEvaluation['momentum'] =
      trendStrength > 60 ? 'accelerating' :
      trendStrength < 20 ? 'stable' : 'decelerating';

    const evaluation: MarketEvaluation = {
      asset: resolvedAsset,
      timestamp: Date.now(),
      currentPrice: data.price,
      trend,
      trendStrength: Math.round(trendStrength),
      momentum,
      volatility,
      volumeProfile: data.volume > 1000000 ? 'above_average' : data.volume > 500000 ? 'average' : 'below_average',
      indicators: techIndicators,
      signal,
      confidence: Math.round(50 + trendStrength * 0.5),
    };

    this.audit.append({
      actor: this.id,
      action: 'MARKET_EVALUATED',
      entity: resolvedAsset,
      status: 'SUCCESS',
      meta: {
        trend,
        trendStrength,
        signal,
        confidence: evaluation.confidence,
      },
    });

    this.log.info('Market evaluated', {
      asset: resolvedAsset,
      trend,
      signal,
      confidence: evaluation.confidence,
    });

    return {
      success: true,
      operation: 'evaluate',
      evaluation,
      message: `${resolvedAsset} evaluation: ${trend} trend (strength: ${Math.round(trendStrength)}%), signal: ${signal}, confidence: ${evaluation.confidence}%`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Forecast — Predict future price movements
  // ─────────────────────────────────────────────────────────────────────────

  private forecastPrice(input: AnalystInput): AnalystResult {
    const { asset, timeframe } = input;
    const resolvedAsset = asset ?? 'ARC';
    const resolvedTimeframe = timeframe ?? '1d';

    const data = MARKET_DATA[resolvedAsset];
    if (!data) {
      return {
        success: false,
        operation: 'forecast',
        message: `No market data available for ${resolvedAsset}`,
        timestamp: Date.now(),
      };
    }

    // Generate simulated predictions for 3 periods
    const periods = this.getPeriods(resolvedTimeframe);
    const predictions = periods.map((period, i) => {
      const drift = (data.macd > 0 ? 1 : -1) * (i + 1) * 0.005 * data.price;
      const predictedPrice = data.price + drift;
      const uncertainty = (i + 1) * 0.01 * data.price;

      return {
        period,
        predictedPrice: Math.round(predictedPrice * 100) / 100,
        lowerBound: Math.round((predictedPrice - uncertainty) * 100) / 100,
        upperBound: Math.round((predictedPrice + uncertainty) * 100) / 100,
        confidence: Math.max(20, 90 - i * 20),
      };
    });

    // Calculate key levels
    const support = [
      Math.round(data.bbLower * 100) / 100,
      Math.round((data.bbLower - (data.dayHigh - data.dayLow) * 0.5) * 100) / 100,
    ];
    const resistance = [
      Math.round(data.bbUpper * 100) / 100,
      Math.round((data.bbUpper + (data.dayHigh - data.dayLow) * 0.5) * 100) / 100,
    ];

    const trendContinuation = data.rsi > 50
      ? Math.round(50 + (data.rsi - 50))
      : Math.round(50 - (50 - data.rsi));

    const riskLevel: PriceForecast['riskLevel'] =
      Math.abs(data.rsi - 50) > 30 ? 'very_high' :
      Math.abs(data.rsi - 50) > 20 ? 'high' :
      Math.abs(data.rsi - 50) > 10 ? 'moderate' : 'low';

    const forecast: PriceForecast = {
      asset: resolvedAsset,
      currentPrice: data.price,
      timeframe: resolvedTimeframe,
      predictions,
      trendContinuation,
      keyLevels: { support, resistance },
      riskLevel,
      forecastedAt: Date.now(),
    };

    this.audit.append({
      actor: this.id,
      action: 'PRICE_FORECAST',
      entity: resolvedAsset,
      status: 'SUCCESS',
      meta: {
        timeframe: resolvedTimeframe,
        currentPrice: data.price,
        predictedPrice: predictions[0]?.predictedPrice,
        riskLevel,
        trendContinuation,
      },
    });

    this.log.info('Price forecast generated', {
      asset: resolvedAsset,
      timeframe: resolvedTimeframe,
      predictedPrice: predictions[0]?.predictedPrice,
      riskLevel,
    });

    return {
      success: true,
      operation: 'forecast',
      forecast,
      message: `${resolvedAsset} forecast (${resolvedTimeframe}): ${predictions[0]?.predictedPrice} (range: ${predictions[0]?.lowerBound}-${predictions[0]?.upperBound}), trend continuation: ${trendContinuation}%`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Compare — Compare multiple assets
  // ─────────────────────────────────────────────────────────────────────────

  private compareAssets(input: AnalystInput): AnalystResult {
    const assets = input.assets ?? Object.keys(MARKET_DATA);
    const resolvedAssets = assets.filter(a => MARKET_DATA[a]);

    if (resolvedAssets.length < 2) {
      return {
        success: false,
        operation: 'compare',
        message: 'At least 2 valid assets are required for comparison',
        timestamp: Date.now(),
      };
    }

    // Comparison dimensions
    const dimensions: AssetComparison['dimensions'] = [
      { dimension: 'Price Performance', rankings: resolvedAssets.map(a => {
        const d = MARKET_DATA[a];
        const perf = ((d.price - d.sma20) / d.sma20) * 100;
        return { asset: a, value: Math.round(perf * 100) / 100, rank: 0 };
      }).sort((a, b) => b.value - a.value) },
      { dimension: 'Momentum (RSI)', rankings: resolvedAssets.map(a => {
        const d = MARKET_DATA[a];
        return { asset: a, value: d.rsi, rank: 0 };
      }).sort((a, b) => b.value - a.value) },
      { dimension: 'Volume', rankings: resolvedAssets.map(a => {
        const d = MARKET_DATA[a];
        return { asset: a, value: d.volume, rank: 0 };
      }).sort((a, b) => b.value - a.value) },
      { dimension: 'Volatility', rankings: resolvedAssets.map(a => {
        const d = MARKET_DATA[a];
        const vol = (d.dayHigh - d.dayLow) / d.price * 100;
        return { asset: a, value: Math.round(vol * 100) / 100, rank: 0 };
      }).sort((a, b) => a.value - b.value) }, // Lower volatility = better rank
    ];

    // Assign ranks within each dimension
    for (const dim of dimensions) {
      dim.rankings.forEach((r, i) => { r.rank = i + 1; });
    }

    // Overall ranking (average rank across dimensions)
    const overallRanking = resolvedAssets.map(a => {
      const totalRank = dimensions.reduce((sum, dim) => {
        const entry = dim.rankings.find(r => r.asset === a);
        return sum + (entry?.rank ?? 0);
      }, 0);
      return { asset: a, score: Math.round((totalRank / dimensions.length) * 100) / 100, rank: 0 };
    }).sort((a, b) => a.score - b.score);
    overallRanking.forEach((r, i) => { r.rank = i + 1; });

    // Correlation matrix (simulated)
    const correlationMatrix: Record<string, Record<string, number>> = {};
    for (const a of resolvedAssets) {
      correlationMatrix[a] = {};
      for (const b of resolvedAssets) {
        if (a === b) {
          correlationMatrix[a][b] = 1.0;
        } else if (correlationMatrix[b]?.[a] !== undefined) {
          correlationMatrix[a][b] = correlationMatrix[b][a];
        } else {
          correlationMatrix[a][b] = Math.round((0.3 + Math.random() * 0.5) * 100) / 100;
        }
      }
    }

    const comparison: AssetComparison = {
      assets: resolvedAssets,
      dimensions,
      overallRanking,
      correlationMatrix,
      comparedAt: Date.now(),
    };

    this.log.info('Assets compared', { assets: resolvedAssets, topRanked: overallRanking[0]?.asset });

    return {
      success: true,
      operation: 'compare',
      comparison,
      message: `Compared ${resolvedAssets.length} assets across ${dimensions.length} dimensions. Top ranked: ${overallRanking[0]?.asset}`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Alert — Generate market event alerts
  // ─────────────────────────────────────────────────────────────────────────

  private generateAlert(input: AnalystInput): AnalystResult {
    const { asset, alertType, thresholdPercent } = input;
    const resolvedAsset = asset ?? 'ARC';
    const resolvedAlertType = alertType ?? 'price_breakout';

    const data = MARKET_DATA[resolvedAsset];
    if (!data) {
      return {
        success: false,
        operation: 'alert',
        message: `No market data available for ${resolvedAsset}`,
        timestamp: Date.now(),
      };
    }

    this.alertCounter++;
    const alertId = `ALRT-${this.alertCounter.toString().padStart(4, '0')}`;

    // Generate alert based on type
    let title: string;
    let description: string;
    let currentValue: number;
    let thresholdValue: number;
    let severity: MarketAlert['severity'];
    let recommendedAction: string;

    switch (resolvedAlertType) {
      case 'price_breakout':
        currentValue = data.price;
        thresholdValue = thresholdPercent ? data.price * (1 + thresholdPercent / 100) : data.bbUpper;
        title = `${resolvedAsset} Price Breakout`;
        description = `${resolvedAsset} trading at ${data.price}, approaching upper Bollinger Band at ${data.bbUpper}`;
        severity = data.price > data.bbUpper ? 'critical' : 'warning';
        recommendedAction = data.price > data.bbUpper ? 'Consider taking profits on long positions' : 'Monitor for breakout confirmation';
        break;
      case 'volume_spike':
        currentValue = data.volume;
        thresholdValue = data.volume * 1.5; // 50% above current volume
        title = `${resolvedAsset} Volume Spike`;
        description = `${resolvedAsset} volume at ${data.volume.toLocaleString()} — significantly above average`;
        severity = data.volume > 2000000 ? 'critical' : 'warning';
        recommendedAction = 'High volume often precedes significant price movement — monitor closely';
        break;
      case 'trend_reversal':
        currentValue = data.rsi;
        thresholdValue = data.rsi > 70 ? 70 : 30;
        title = `${resolvedAsset} Trend Reversal Signal`;
        description = `RSI at ${data.rsi} — ${data.rsi > 70 ? 'overbought, potential bearish reversal' : data.rsi < 30 ? 'oversold, potential bullish reversal' : 'neutral zone'}`;
        severity = data.rsi > 75 || data.rsi < 25 ? 'critical' : 'info';
        recommendedAction = data.rsi > 70 ? 'Consider reducing long exposure' : data.rsi < 30 ? 'Watch for buying opportunity' : 'No action needed';
        break;
      case 'support_breach':
        currentValue = data.price;
        thresholdValue = data.bbLower;
        title = `${resolvedAsset} Support Level Breach`;
        description = `${resolvedAsset} price ${data.price} ${data.price < data.bbLower ? 'below' : 'approaching'} support at ${data.bbLower}`;
        severity = data.price < data.bbLower ? 'critical' : 'warning';
        recommendedAction = data.price < data.bbLower ? 'Consider stop-loss activation' : 'Monitor support level';
        break;
      case 'resistance_breach':
        currentValue = data.price;
        thresholdValue = data.bbUpper;
        title = `${resolvedAsset} Resistance Level Breach`;
        description = `${resolvedAsset} price ${data.price} ${data.price > data.bbUpper ? 'above' : 'approaching'} resistance at ${data.bbUpper}`;
        severity = data.price > data.bbUpper ? 'critical' : 'warning';
        recommendedAction = data.price > data.bbUpper ? 'Breakout confirmed — consider momentum entry' : 'Watch for resistance test';
        break;
      default:
        title = `${resolvedAsset} Market Alert`;
        description = `Unknown alert type: ${resolvedAlertType}`;
        currentValue = data.price;
        thresholdValue = 0;
        severity = 'info';
        recommendedAction = 'Review alert configuration';
    }

    const alert: MarketAlert = {
      alertId,
      asset: resolvedAsset,
      alertType: resolvedAlertType,
      severity,
      title,
      description,
      currentValue,
      thresholdValue,
      triggeredAt: Date.now(),
      recommendedAction,
    };

    this.audit.append({
      actor: this.id,
      action: 'MARKET_ALERT_GENERATED',
      entity: alertId,
      status: 'SUCCESS',
      meta: {
        asset: resolvedAsset,
        alertType: resolvedAlertType,
        severity,
      },
    });

    this.log.info('Market alert generated', {
      alertId,
      asset: resolvedAsset,
      alertType: resolvedAlertType,
      severity,
    });

    return {
      success: true,
      operation: 'alert',
      alert,
      message: `${severity.toUpperCase()}: ${title} — ${description}`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Helpers
  // ─────────────────────────────────────────────────────────────────────────

  private getPeriods(timeframe: AnalystInput['timeframe']): string[] {
    switch (timeframe) {
      case '1h': return ['1h', '2h', '4h'];
      case '4h': return ['4h', '8h', '12h'];
      case '1d': return ['1d', '3d', '1w'];
      case '1w': return ['1w', '2w', '1m'];
      case '1m': return ['1m', '2m', '3m'];
      default: return ['1d', '3d', '1w'];
    }
  }
}
