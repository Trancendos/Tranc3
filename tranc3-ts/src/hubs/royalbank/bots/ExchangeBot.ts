/**
 * ExchangeBot — Currency Exchange Bot for The Royal Bank of Arcadia
 *
 * Identity:  NID-ROYALBANK-EXCHANGE
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    RoyalBankOfArcadiaAI (AID-ROYALBANK)
 *
 * Responsibilities:
 *   - Convert between Arcadian currencies (credits, tokens, gold)
 *   - Apply exchange rates with configurable spreads
 *   - Calculate conversion fees based on tier and volume
 *   - Track rate history and volatility indicators
 *   - Support forward rate quotes (rate locks for future settlement)
 *
 * "In the Arcadian economy, value is relative — but the exchange is always fair."
 */

import { Bot, Logger, AuditLedger } from '../../../core/definitions'

const auditLedger = new AuditLedger();

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface ExchangeInput {
  operation: 'CONVERT';
  fromCurrency: 'credits' | 'tokens' | 'gold';
  toCurrency: 'credits' | 'tokens' | 'gold';
  amount: number;
  accountTier?: 'personal' | 'business' | 'treasury';
  lockRate?: boolean; // Request rate lock for 60 seconds
  maxSlippage?: number; // Maximum acceptable slippage percentage (0-100)
}

export type CurrencyType = 'credits' | 'tokens' | 'gold';

export interface ExchangeRate {
  from: CurrencyType;
  to: CurrencyType;
  rate: number;
  spread: number; // Percentage spread (bid-ask)
  source: string;
  lastUpdated: number;
  volatility: 'stable' | 'normal' | 'volatile';
  dayHigh: number;
  dayLow: number;
  dayVolume: number;
}

export interface RateHistoryEntry {
  timestamp: number;
  from: CurrencyType;
  to: CurrencyType;
  rate: number;
  volume: number;
}

export interface ConversionDetail {
  grossAmount: number;
  exchangeRate: number;
  spreadAmount: number;
  feeAmount: number;
  feeRate: number;
  netAmount: number;
  slippage: number;
}

export interface RateLock {
  lockId: string;
  fromCurrency: CurrencyType;
  toCurrency: CurrencyType;
  lockedRate: number;
  amount: number;
  lockedAt: number;
  expiresAt: number;
  status: 'active' | 'expired' | 'executed';
}

export interface ConvertResult {
  success: boolean;
  fromCurrency: CurrencyType;
  toCurrency: CurrencyType;
  requestedAmount: number;
  conversion: ConversionDetail;
  rateLock?: RateLock;
  rateHistory: RateHistoryEntry[];
  message: string;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Exchange Rate Matrix (Simulated)
// ─────────────────────────────────────────────────────────────────────────────

const EXCHANGE_RATES: Record<string, Omit<ExchangeRate, 'lastUpdated'>> = {
  'credits→tokens': {
    from: 'credits',
    to: 'tokens',
    rate: 1.0,
    spread: 0.5,
    source: 'Arcadian Central Bank',
    volatility: 'stable',
    dayHigh: 1.002,
    dayLow: 0.998,
    dayVolume: 2500000,
  },
  'tokens→credits': {
    from: 'tokens',
    to: 'credits',
    rate: 1.0,
    spread: 0.5,
    source: 'Arcadian Central Bank',
    volatility: 'stable',
    dayHigh: 1.002,
    dayLow: 0.998,
    dayVolume: 2300000,
  },
  'credits→gold': {
    from: 'credits',
    to: 'gold',
    rate: 0.001,
    spread: 1.5,
    source: 'Arcadian Gold Reserve',
    volatility: 'normal',
    dayHigh: 0.00105,
    dayLow: 0.00095,
    dayVolume: 500000,
  },
  'gold→credits': {
    from: 'gold',
    to: 'credits',
    rate: 1000,
    spread: 1.5,
    source: 'Arcadian Gold Reserve',
    volatility: 'normal',
    dayHigh: 1050,
    dayLow: 950,
    dayVolume: 450000,
  },
  'tokens→gold': {
    from: 'tokens',
    to: 'gold',
    rate: 0.001,
    spread: 1.8,
    source: 'Arcadian Gold Reserve',
    volatility: 'normal',
    dayHigh: 0.00106,
    dayLow: 0.00094,
    dayVolume: 300000,
  },
  'gold→tokens': {
    from: 'gold',
    to: 'tokens',
    rate: 1000,
    spread: 1.8,
    source: 'Arcadian Gold Reserve',
    volatility: 'normal',
    dayHigh: 1060,
    dayLow: 940,
    dayVolume: 280000,
  },
};

// Fee schedule by account tier
const FEE_SCHEDULE: Record<string, { feeRate: number; minFee: number; maxFee: number }> = {
  personal: { feeRate: 0.002, minFee: 1, maxFee: 100 },    // 0.2% fee
  business: { feeRate: 0.001, minFee: 5, maxFee: 500 },    // 0.1% fee
  treasury: { feeRate: 0, minFee: 0, maxFee: 0 },          // No fee
};

// ─────────────────────────────────────────────────────────────────────────────
// Rate History (Simulated)
// ─────────────────────────────────────────────────────────────────────────────

const rateHistory: RateHistoryEntry[] = [];
let rateLockCounter = 0;
const activeRateLocks: Map<string, RateLock> = new Map();

// Seed some history
const now = Date.now();
for (let i = 23; i >= 0; i--) {
  rateHistory.push({
    timestamp: now - i * 3600000,
    from: 'credits',
    to: 'tokens',
    rate: 1.0 + (Math.random() - 0.5) * 0.004,
    volume: Math.floor(Math.random() * 200000) + 50000,
  });
  rateHistory.push({
    timestamp: now - i * 3600000,
    from: 'credits',
    to: 'gold',
    rate: 0.001 + (Math.random() - 0.5) * 0.0001,
    volume: Math.floor(Math.random() * 50000) + 10000,
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// ExchangeBot Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class ExchangeBot extends Bot {
  private readonly log: Logger;
  private readonly audit: AuditLedger;

  constructor() {
    super(
      'NID-ROYALBANK-EXCHANGE',
      'Exchange',
      async (input: ExchangeInput) => this.handle(input),
      'Currency exchange with rate tracking, spreads, and conversion fees'
    );

    this.log = new Logger('ExchangeBot');
    this.audit = auditLedger;
  }

  private async handle(input: ExchangeInput): Promise<ConvertResult> {
    if (input.operation !== 'CONVERT') {
      return this.fail(`Unknown operation: ${input.operation}. ExchangeBot only accepts CONVERT.`);
    }
    return this.convert(input);
  }

  // ─────────────────────────────────────────────────────────────────────────
  // CONVERT — Execute currency exchange
  // ─────────────────────────────────────────────────────────────────────────

  private convert(input: ExchangeInput): ConvertResult {
    const { fromCurrency, toCurrency, amount, accountTier, lockRate, maxSlippage } = input;

    // Validate inputs
    if (!fromCurrency || !toCurrency) {
      return this.fail('Both fromCurrency and toCurrency are required');
    }

    if (fromCurrency === toCurrency) {
      return this.fail(`Source and target currencies are the same (${fromCurrency}). No conversion needed.`);
    }

    if (!amount || amount <= 0) {
      return this.fail('Amount must be a positive number');
    }

    // Look up exchange rate
    const rateKey = `${fromCurrency}→${toCurrency}`;
    const rateData = EXCHANGE_RATES[rateKey];

    if (!rateData) {
      return this.fail(`No exchange rate available for ${fromCurrency} → ${toCurrency}`);
    }

    // Apply simulated market micro-variation (±0.05%)
    const marketVariation = 1 + (Math.random() - 0.5) * 0.001;
    const effectiveRate = rateData.rate * marketVariation;

    // Calculate slippage from base rate
    const slippage = Math.abs((effectiveRate - rateData.rate) / rateData.rate) * 100;

    // Check max slippage constraint
    if (maxSlippage !== undefined && slippage > maxSlippage) {
      return this.fail(`Current slippage ${slippage.toFixed(4)}% exceeds maximum allowed ${maxSlippage}%. Try again or increase maxSlippage.`);
    }

    // Calculate spread cost
    const spreadAmount = amount * (rateData.spread / 100);

    // Calculate conversion fee
    const tier = accountTier ?? 'personal';
    const feeConfig = FEE_SCHEDULE[tier] ?? FEE_SCHEDULE.personal;
    const rawFee = amount * feeConfig.feeRate;
    const feeAmount = Math.max(feeConfig.minFee, Math.min(feeConfig.maxFee, rawFee));

    // Calculate net conversion
    const grossAmount = (amount - spreadAmount) * effectiveRate;
    const netAmount = grossAmount - (feeAmount * effectiveRate);

    const conversion: ConversionDetail = {
      grossAmount,
      exchangeRate: effectiveRate,
      spreadAmount,
      feeAmount,
      feeRate: feeConfig.feeRate * 100,
      netAmount: Math.max(0, netAmount),
      slippage,
    };

    // Record in rate history
    const historyEntry: RateHistoryEntry = {
      timestamp: Date.now(),
      from: fromCurrency,
      to: toCurrency,
      rate: effectiveRate,
      volume: amount,
    };
    rateHistory.push(historyEntry);

    // Handle rate lock request
    let rateLock: RateLock | undefined;
    if (lockRate) {
      rateLockCounter++;
      const lockId = `RLOCK-${rateLockCounter.toString().padStart(4, '0')}`;
      rateLock = {
        lockId,
        fromCurrency,
        toCurrency,
        lockedRate: effectiveRate,
        amount,
        lockedAt: Date.now(),
        expiresAt: Date.now() + 60000, // 60-second lock
        status: 'active',
      };
      activeRateLocks.set(lockId, rateLock);
    }

    // Build relevant rate history for response
    const relevantHistory = rateHistory
      .filter(h => h.from === fromCurrency && h.to === toCurrency)
      .slice(-10); // Last 10 entries

    this.audit.append({
      actor: 'NID-ROYALBANK-EXCHANGE',
      action: 'CURRENCY_CONVERTED',
      entity: `${fromCurrency}→${toCurrency}`,
      status: 'SUCCESS',
      meta: {
        fromCurrency,
        toCurrency,
        requestedAmount: amount,
        effectiveRate,
        netAmount: conversion.netAmount,
        spreadAmount,
        feeAmount,
        feeRate: conversion.feeRate,
        slippage,
        tier,
        rateLockId: rateLock?.lockId,
      },
    });

    this.log.info('Currency conversion executed', {
      fromCurrency,
      toCurrency,
      amount,
      effectiveRate,
      netAmount: conversion.netAmount,
      feeAmount,
    });

    return {
      success: true,
      fromCurrency,
      toCurrency,
      requestedAmount: amount,
      conversion,
      rateLock,
      rateHistory: relevantHistory,
      message: `Converted ${amount} ${fromCurrency} to ${conversion.netAmount.toFixed(2)} ${toCurrency} at rate ${effectiveRate.toFixed(6)} (spread: ${spreadAmount.toFixed(2)}, fee: ${feeAmount.toFixed(2)} ${fromCurrency})`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Helpers
  // ─────────────────────────────────────────────────────────────────────────

  private fail(message: string): ConvertResult {
    this.log.error('Exchange conversion failed', { message });
    return {
      success: false,
      fromCurrency: 'credits',
      toCurrency: 'credits',
      requestedAmount: 0,
      conversion: {
        grossAmount: 0,
        exchangeRate: 0,
        spreadAmount: 0,
        feeAmount: 0,
        feeRate: 0,
        netAmount: 0,
        slippage: 0,
      },
      rateHistory: [],
      message,
      timestamp: Date.now(),
    };
  }
}
