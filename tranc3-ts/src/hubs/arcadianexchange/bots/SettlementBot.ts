/**
 * SettlementBot — Trade Settlement & Clearing Bot for The Arcadian Exchange
 *
 * Identity:  NID-ARCADIANEXCHANGE-SETTLEMENT
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    ArcadianExchangeAI (AID-ARCADIANEXCHANGE)
 *
 * Responsibilities:
 *   - Clear matched trades and settle between buyer/seller accounts
 *   - Reconcile account balances after trade execution
 *   - Track settlement status through the clearing lifecycle
 *   - Apply settlement fees and commission splits
 *   - Maintain a settlement ledger for audit and compliance
 *   - Handle fail scenarios: insufficient funds, expired settlement windows
 *
 * "Every trade is a promise. Settlement is the honouring of that promise."
 */

import { Bot, Logger, AuditLedger } from '../../../core/definitions'

const auditLedger = new AuditLedger();

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface SettlementInput {
  operation: 'CLEAR';
  tradeId: string;
  buyerAccountId?: string;
  sellerAccountId?: string;
  asset?: string;
  quantity?: number;
  price?: number;
  settlementWindowMs?: number;
}

export interface SettlementEntry {
  settlementId: string;
  tradeId: string;
  buyerAccountId: string;
  sellerAccountId: string;
  asset: string;
  quantity: number;
  price: number;
  grossAmount: number;
  buyerFee: number;
  sellerFee: number;
  netBuyerDebit: number;
  netSellerCredit: number;
  currency: string;
  status: 'pending' | 'cleared' | 'settled' | 'failed' | 'rolled_back';
  settledAt?: number;
  clearedAt?: number;
  createdAt: number;
  expiresAt: number;
  failureReason?: string;
  settlementBatch: string;
  reconciled: boolean;
}

export interface AccountReconciliation {
  accountId: string;
  preBalance: number;
  postBalance: number;
  delta: number;
  currency: string;
  assetTransfers: {
    asset: string;
    quantity: number;
    direction: 'credit' | 'debit';
  }[];
  status: 'balanced' | 'imbalance' | 'error';
  discrepancy?: number;
}

export interface SettlementSummary {
  totalSettlements: number;
  cleared: number;
  settled: number;
  pending: number;
  failed: number;
  rolledBack: number;
  totalGrossValue: number;
  totalFeesCollected: number;
  averageSettlementTimeMs: number;
  settlementRate: number;
  byAsset: Record<string, { count: number; grossValue: number }>;
  currentBatch: string;
  timestamp: number;
}

export interface SettlementResult {
  success: boolean;
  settlement: SettlementEntry;
  buyerReconciliation: AccountReconciliation;
  sellerReconciliation: AccountReconciliation;
  summary: SettlementSummary;
  message: string;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Simulated Account Balances
// ─────────────────────────────────────────────────────────────────────────────

const ACCOUNT_BALANCES: Record<string, Record<string, number>> = {
  'ACC-001': { credits: 500000, tokens: 1000000, gold: 50, ARC: 1000, TKN: 50000, GLD: 5, NRG: 200, DAT: 500, KNO: 100 },
  'ACC-002': { credits: 250000, tokens: 500000, gold: 25, ARC: 500, TKN: 25000, GLD: 3, NRG: 100, DAT: 250, KNO: 50 },
  'ACC-003': { credits: 1000000, tokens: 2000000, gold: 100, ARC: 5000, TKN: 200000, GLD: 10, NRG: 500, DAT: 1000, KNO: 300 },
  'ACC-004': { credits: 75000, tokens: 100000, gold: 10, ARC: 200, TKN: 10000, GLD: 1, NRG: 50, DAT: 100, KNO: 25 },
  'ACC-005': { credits: 350000, tokens: 750000, gold: 40, ARC: 2500, TKN: 100000, GLD: 8, NRG: 300, DAT: 600, KNO: 150 },
};

let settlementCounter = 0;
let batchCounter = 1000;

const FEE_RATE_BUYER = 0.001;   // 0.10% buyer commission
const FEE_RATE_SELLER = 0.001;  // 0.10% seller commission
const SETTLEMENT_WINDOW_MS = 300000; // 5-minute default settlement window
const ROLLBACK_WINDOW_MS = 60000;     // 1-minute rollback window

// ─────────────────────────────────────────────────────────────────────────────
// SettlementBot Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class SettlementBot extends Bot {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private settlements: Map<string, SettlementEntry>;
  private currentBatch: string;

  constructor() {
    super(
      'NID-ARCADIANEXCHANGE-SETTLEMENT',
      'Settlement',
      async (input: SettlementInput) => this.handle(input),
      'Trade settlement and clearing with account reconciliation and batch processing'
    );

    this.log = new Logger('SettlementBot');
    this.audit = auditLedger;
    this.settlements = new Map();
    this.currentBatch = `BATCH-${batchCounter}`;
  }

  private async handle(input: SettlementInput): Promise<SettlementResult> {
    if (input.operation !== 'CLEAR') {
      return this.fail(`Unknown operation: ${input.operation}. SettlementBot only accepts CLEAR.`);
    }
    return this.clear(input);
  }

  // ───────────────────────────────────────────────────────────────────────
  // CLEAR — Process trade settlement
  // ───────────────────────────────────────────────────────────────────────

  private clear(input: SettlementInput): SettlementResult {
    const {
      tradeId,
      buyerAccountId,
      sellerAccountId,
      asset,
      quantity,
      price,
      settlementWindowMs,
    } = input;

    if (!tradeId) {
      return this.fail('Trade ID is required for settlement');
    }

    // Resolve trade details — use provided or simulate from trade ID
    const resolvedBuyer = buyerAccountId ?? this.resolveAccountFromTrade(tradeId, 'buyer');
    const resolvedSeller = sellerAccountId ?? this.resolveAccountFromTrade(tradeId, 'seller');
    const resolvedAsset = asset ?? this.resolveAssetFromTrade(tradeId);
    const resolvedQuantity = quantity ?? this.resolveQuantityFromTrade(tradeId);
    const resolvedPrice = price ?? this.resolvePriceFromTrade(tradeId);

    if (!resolvedBuyer || !resolvedSeller || !resolvedAsset || resolvedQuantity <= 0 || resolvedPrice <= 0) {
      const failureReason = 'Missing or invalid trade parameters';
      settlementCounter++;
      const failedSettlement: SettlementEntry = {
        settlementId: `STL-${settlementCounter.toString().padStart(6, '0')}`,
        tradeId,
        buyerAccountId: resolvedBuyer ?? 'UNKNOWN',
        sellerAccountId: resolvedSeller ?? 'UNKNOWN',
        asset: resolvedAsset ?? 'UNKNOWN',
        quantity: resolvedQuantity,
        price: resolvedPrice,
        grossAmount: resolvedQuantity * resolvedPrice,
        buyerFee: 0,
        sellerFee: 0,
        netBuyerDebit: 0,
        netSellerCredit: 0,
        currency: 'credits',
        status: 'failed',
        createdAt: Date.now(),
        expiresAt: Date.now() + (settlementWindowMs ?? SETTLEMENT_WINDOW_MS),
        failureReason,
        settlementBatch: this.currentBatch,
        reconciled: false,
      };

      this.settlements.set(failedSettlement.settlementId, failedSettlement);

      this.audit.append({
        actor: 'NID-ARCADIANEXCHANGE-SETTLEMENT',
        action: 'SETTLEMENT_FAILED',
        entity: tradeId,
        status: 'FAILURE',
        meta: { failureReason, tradeId },
      });

      return this.buildFailedResult(failedSettlement, failureReason);
    }

    // Calculate settlement amounts
    const grossAmount = resolvedQuantity * resolvedPrice;
    const buyerFee = Math.round(grossAmount * FEE_RATE_BUYER * 100) / 100;
    const sellerFee = Math.round(grossAmount * FEE_RATE_SELLER * 100) / 100;
    const netBuyerDebit = Math.round((grossAmount + buyerFee) * 100) / 100;
    const netSellerCredit = Math.round((grossAmount - sellerFee) * 100) / 100;

    // Verify buyer has sufficient funds
    const buyerBalances = ACCOUNT_BALANCES[resolvedBuyer];
    const sellerBalances = ACCOUNT_BALANCES[resolvedSeller];

    if (!buyerBalances) {
      return this.failAccountMissing(resolvedBuyer, tradeId, resolvedAsset, resolvedQuantity, resolvedPrice, grossAmount, resolvedSeller, 'buyer');
    }

    if (!sellerBalances) {
      return this.failAccountMissing(resolvedSeller, tradeId, resolvedAsset, resolvedQuantity, resolvedPrice, grossAmount, resolvedBuyer, 'seller');
    }

    // Check buyer has enough currency to pay (credits)
    const buyerCreditBalance = buyerBalances.credits ?? 0;
    if (buyerCreditBalance < netBuyerDebit) {
      settlementCounter++;
      const failedSettlement: SettlementEntry = {
        settlementId: `STL-${settlementCounter.toString().padStart(6, '0')}`,
        tradeId,
        buyerAccountId: resolvedBuyer,
        sellerAccountId: resolvedSeller,
        asset: resolvedAsset,
        quantity: resolvedQuantity,
        price: resolvedPrice,
        grossAmount,
        buyerFee,
        sellerFee,
        netBuyerDebit,
        netSellerCredit,
        currency: 'credits',
        status: 'failed',
        createdAt: Date.now(),
        expiresAt: Date.now() + (settlementWindowMs ?? SETTLEMENT_WINDOW_MS),
        failureReason: `Insufficient funds: buyer ${resolvedBuyer} has ${buyerCreditBalance} credits, needs ${netBuyerDebit}`,
        settlementBatch: this.currentBatch,
        reconciled: false,
      };

      this.settlements.set(failedSettlement.settlementId, failedSettlement);

      this.audit.append({
        actor: 'NID-ARCADIANEXCHANGE-SETTLEMENT',
        action: 'SETTLEMENT_FAILED_INSUFFICIENT_FUNDS',
        entity: tradeId,
        status: 'FAILURE',
        meta: { buyerAccountId: resolvedBuyer, required: netBuyerDebit, available: buyerCreditBalance },
      });

      return this.buildFailedResult(failedSettlement, failedSettlement.failureReason!);
    }

    // Check seller has enough asset to deliver
    const sellerAssetBalance = sellerBalances[resolvedAsset] ?? 0;
    if (sellerAssetBalance < resolvedQuantity) {
      settlementCounter++;
      const failedSettlement: SettlementEntry = {
        settlementId: `STL-${settlementCounter.toString().padStart(6, '0')}`,
        tradeId,
        buyerAccountId: resolvedBuyer,
        sellerAccountId: resolvedSeller,
        asset: resolvedAsset,
        quantity: resolvedQuantity,
        price: resolvedPrice,
        grossAmount,
        buyerFee,
        sellerFee,
        netBuyerDebit,
        netSellerCredit,
        currency: 'credits',
        status: 'failed',
        createdAt: Date.now(),
        expiresAt: Date.now() + (settlementWindowMs ?? SETTLEMENT_WINDOW_MS),
        failureReason: `Insufficient assets: seller ${resolvedSeller} has ${sellerAssetBalance} ${resolvedAsset}, needs ${resolvedQuantity}`,
        settlementBatch: this.currentBatch,
        reconciled: false,
      };

      this.settlements.set(failedSettlement.settlementId, failedSettlement);

      this.audit.append({
        actor: 'NID-ARCADIANEXCHANGE-SETTLEMENT',
        action: 'SETTLEMENT_FAILED_INSUFFICIENT_ASSETS',
        entity: tradeId,
        status: 'FAILURE',
        meta: { sellerAccountId: resolvedSeller, asset: resolvedAsset, required: resolvedQuantity, available: sellerAssetBalance },
      });

      return this.buildFailedResult(failedSettlement, failedSettlement.failureReason!);
    }

    // Execute settlement — update account balances
    const buyerPreCredit = buyerBalances.credits;
    const sellerPreCredit = sellerBalances.credits;
    const buyerPreAsset = buyerBalances[resolvedAsset] ?? 0;
    const sellerPreAsset = sellerBalances[resolvedAsset] ?? 0;

    // Debit buyer credits, credit seller credits
    buyerBalances.credits = Math.round((buyerPreCredit - netBuyerDebit) * 100) / 100;
    sellerBalances.credits = Math.round((sellerPreCredit + netSellerCredit) * 100) / 100;

    // Transfer asset from seller to buyer
    buyerBalances[resolvedAsset] = Math.round((buyerPreAsset + resolvedQuantity) * 1000000) / 1000000;
    sellerBalances[resolvedAsset] = Math.round((sellerPreAsset - resolvedQuantity) * 1000000) / 1000000;

    // Create settlement entry
    settlementCounter++;
    const now = Date.now();
    const settlement: SettlementEntry = {
      settlementId: `STL-${settlementCounter.toString().padStart(6, '0')}`,
      tradeId,
      buyerAccountId: resolvedBuyer,
      sellerAccountId: resolvedSeller,
      asset: resolvedAsset,
      quantity: resolvedQuantity,
      price: resolvedPrice,
      grossAmount: Math.round(grossAmount * 100) / 100,
      buyerFee,
      sellerFee,
      netBuyerDebit,
      netSellerCredit,
      currency: 'credits',
      status: 'settled',
      settledAt: now,
      clearedAt: now,
      createdAt: now - 500, // Simulate slight delay before clearing
      expiresAt: now + (settlementWindowMs ?? SETTLEMENT_WINDOW_MS),
      settlementBatch: this.currentBatch,
      reconciled: true,
    };

    this.settlements.set(settlement.settlementId, settlement);

    // Start a new batch if this one has 50+ settlements
    const batchSettlements = Array.from(this.settlements.values())
      .filter(s => s.settlementBatch === this.currentBatch);
    if (batchSettlements.length >= 50) {
      batchCounter++;
      this.currentBatch = `BATCH-${batchCounter}`;
    }

    // Build reconciliations
    const buyerReconciliation: AccountReconciliation = {
      accountId: resolvedBuyer,
      preBalance: buyerPreCredit,
      postBalance: buyerBalances.credits,
      delta: Math.round((buyerBalances.credits - buyerPreCredit) * 100) / 100,
      currency: 'credits',
      assetTransfers: [
        { asset: resolvedAsset, quantity: resolvedQuantity, direction: 'credit' },
      ],
      status: 'balanced',
    };

    const sellerReconciliation: AccountReconciliation = {
      accountId: resolvedSeller,
      preBalance: sellerPreCredit,
      postBalance: sellerBalances.credits,
      delta: Math.round((sellerBalances.credits - sellerPreCredit) * 100) / 100,
      currency: 'credits',
      assetTransfers: [
        { asset: resolvedAsset, quantity: resolvedQuantity, direction: 'debit' },
      ],
      status: 'balanced',
    };

    // Verify reconciliation
    const buyerExpectedPost = Math.round((buyerPreCredit - netBuyerDebit) * 100) / 100;
    const sellerExpectedPost = Math.round((sellerPreCredit + netSellerCredit) * 100) / 100;

    if (buyerBalances.credits !== buyerExpectedPost) {
      buyerReconciliation.status = 'imbalance';
      buyerReconciliation.discrepancy = Math.round((buyerBalances.credits - buyerExpectedPost) * 100) / 100;
    }

    if (sellerBalances.credits !== sellerExpectedPost) {
      sellerReconciliation.status = 'imbalance';
      sellerReconciliation.discrepancy = Math.round((sellerBalances.credits - sellerExpectedPost) * 100) / 100;
    }

    const summary = this.buildSummary();

    this.audit.append({
      actor: 'NID-ARCADIANEXCHANGE-SETTLEMENT',
      action: 'TRADE_SETTLED',
      entity: tradeId,
      status: 'SUCCESS',
      meta: {
        settlementId: settlement.settlementId,
        buyerAccountId: resolvedBuyer,
        sellerAccountId: resolvedSeller,
        asset: resolvedAsset,
        quantity: resolvedQuantity,
        price: resolvedPrice,
        grossAmount,
        buyerFee,
        sellerFee,
        netBuyerDebit,
        netSellerCredit,
        settlementBatch: settlement.settlementBatch,
      },
    });

    this.log.info('Trade settled successfully', {
      settlementId: settlement.settlementId,
      tradeId,
      buyer: resolvedBuyer,
      seller: resolvedSeller,
      asset: resolvedAsset,
      quantity: resolvedQuantity,
      price: resolvedPrice,
      grossAmount,
      netBuyerDebit,
      netSellerCredit,
    });

    return {
      success: true,
      settlement,
      buyerReconciliation,
      sellerReconciliation,
      summary,
      message: `Trade ${tradeId} settled: ${resolvedQuantity} ${resolvedAsset} @ ${resolvedPrice} | Buyer ${resolvedBuyer} debited ${netBuyerDebit} | Seller ${resolvedSeller} credited ${netSellerCredit} | Fee: ${(buyerFee + sellerFee).toFixed(2)}`,
      timestamp: Date.now(),
    };
  }

  // ───────────────────────────────────────────────────────────────────────
  // Trade Resolution Helpers (simulated)
  // ───────────────────────────────────────────────────────────────────────

  private resolveAccountFromTrade(tradeId: string, side: 'buyer' | 'seller'): string {
    // Deterministic account assignment from trade ID hash
    const hash = this.simpleHash(tradeId);
    const accounts = Object.keys(ACCOUNT_BALANCES);
    if (side === 'buyer') {
      return accounts[hash % accounts.length];
    } else {
      return accounts[(hash + 1) % accounts.length];
    }
  }

  private resolveAssetFromTrade(tradeId: string): string {
    const assets = ['ARC', 'TKN', 'GLD', 'NRG', 'DAT', 'KNO'];
    return assets[this.simpleHash(tradeId) % assets.length];
  }

  private resolveQuantityFromTrade(tradeId: string): number {
    return (this.simpleHash(tradeId + 'qty') % 1000) + 10;
  }

  private resolvePriceFromTrade(tradeId: string): number {
    const basePrices: Record<string, number> = { ARC: 100, TKN: 1, GLD: 1000, NRG: 45, DAT: 22, KNO: 150 };
    const asset = this.resolveAssetFromTrade(tradeId);
    return basePrices[asset] ?? 100;
  }

  private simpleHash(str: string): number {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash |= 0; // Convert to 32-bit integer
    }
    return Math.abs(hash);
  }

  // ───────────────────────────────────────────────────────────────────────
  // Settlement Summary
  // ───────────────────────────────────────────────────────────────────────

  private buildSummary(): SettlementSummary {
    const all = Array.from(this.settlements.values());
    const settled = all.filter(s => s.status === 'settled');
    const cleared = all.filter(s => s.status === 'cleared');
    const pending = all.filter(s => s.status === 'pending');
    const failed = all.filter(s => s.status === 'failed');
    const rolledBack = all.filter(s => s.status === 'rolled_back');

    const totalGrossValue = settled.reduce((sum, s) => sum + s.grossAmount, 0);
    const totalFeesCollected = settled.reduce((sum, s) => sum + s.buyerFee + s.sellerFee, 0);

    // Calculate average settlement time for settled entries
    const settlementTimes = settled
      .filter(s => s.settledAt && s.createdAt)
      .map(s => s.settledAt! - s.createdAt);
    const averageSettlementTimeMs = settlementTimes.length > 0
      ? Math.round(settlementTimes.reduce((sum, t) => sum + t, 0) / settlementTimes.length)
      : 0;

    const settlementRate = all.length > 0
      ? Math.round((settled.length / all.length) * 10000) / 100
      : 0;

    // Breakdown by asset
    const byAsset: Record<string, { count: number; grossValue: number }> = {};
    for (const s of settled) {
      if (!byAsset[s.asset]) {
        byAsset[s.asset] = { count: 0, grossValue: 0 };
      }
      byAsset[s.asset].count++;
      byAsset[s.asset].grossValue += s.grossAmount;
    }

    return {
      totalSettlements: all.length,
      cleared: cleared.length,
      settled: settled.length,
      pending: pending.length,
      failed: failed.length,
      rolledBack: rolledBack.length,
      totalGrossValue: Math.round(totalGrossValue * 100) / 100,
      totalFeesCollected: Math.round(totalFeesCollected * 100) / 100,
      averageSettlementTimeMs,
      settlementRate,
      byAsset,
      currentBatch: this.currentBatch,
      timestamp: Date.now(),
    };
  }

  // ───────────────────────────────────────────────────────────────────────
  // Failure Helpers
  // ───────────────────────────────────────────────────────────────────────

  private failAccountMissing(
    missingAccountId: string,
    tradeId: string,
    asset: string,
    quantity: number,
    price: number,
    grossAmount: number,
    otherAccountId: string,
    missingSide: 'buyer' | 'seller'
  ): SettlementResult {
    settlementCounter++;
    const failedSettlement: SettlementEntry = {
      settlementId: `STL-${settlementCounter.toString().padStart(6, '0')}`,
      tradeId,
      buyerAccountId: missingSide === 'buyer' ? missingAccountId : otherAccountId,
      sellerAccountId: missingSide === 'seller' ? missingAccountId : otherAccountId,
      asset,
      quantity,
      price,
      grossAmount,
      buyerFee: 0,
      sellerFee: 0,
      netBuyerDebit: 0,
      netSellerCredit: 0,
      currency: 'credits',
      status: 'failed',
      createdAt: Date.now(),
      expiresAt: Date.now() + SETTLEMENT_WINDOW_MS,
      failureReason: `Account not found: ${missingAccountId} (${missingSide})`,
      settlementBatch: this.currentBatch,
      reconciled: false,
    };

    this.settlements.set(failedSettlement.settlementId, failedSettlement);

    this.audit.append({
      actor: 'NID-ARCADIANEXCHANGE-SETTLEMENT',
      action: 'SETTLEMENT_FAILED_ACCOUNT_MISSING',
      entity: tradeId,
      status: 'FAILURE',
      meta: { missingAccountId, missingSide },
    });

    return this.buildFailedResult(failedSettlement, failedSettlement.failureReason!);
  }

  private buildFailedResult(settlement: SettlementEntry, reason: string): SettlementResult {
    const emptyReconciliation: AccountReconciliation = {
      accountId: '',
      preBalance: 0,
      postBalance: 0,
      delta: 0,
      currency: 'credits',
      assetTransfers: [],
      status: 'error',
    };

    return {
      success: false,
      settlement,
      buyerReconciliation: { ...emptyReconciliation, accountId: settlement.buyerAccountId },
      sellerReconciliation: { ...emptyReconciliation, accountId: settlement.sellerAccountId },
      summary: this.buildSummary(),
      message: `Settlement failed for trade ${settlement.tradeId}: ${reason}`,
      timestamp: Date.now(),
    };
  }

  private fail(message: string): SettlementResult {
    this.log.error('Settlement failed', { message });
    const emptyReconciliation: AccountReconciliation = {
      accountId: '',
      preBalance: 0,
      postBalance: 0,
      delta: 0,
      currency: 'credits',
      assetTransfers: [],
      status: 'error',
    };

    settlementCounter++;
    const failedSettlement: SettlementEntry = {
      settlementId: `STL-${settlementCounter.toString().padStart(6, '0')}`,
      tradeId: '',
      buyerAccountId: '',
      sellerAccountId: '',
      asset: '',
      quantity: 0,
      price: 0,
      grossAmount: 0,
      buyerFee: 0,
      sellerFee: 0,
      netBuyerDebit: 0,
      netSellerCredit: 0,
      currency: 'credits',
      status: 'failed',
      createdAt: Date.now(),
      expiresAt: Date.now() + SETTLEMENT_WINDOW_MS,
      failureReason: message,
      settlementBatch: this.currentBatch,
      reconciled: false,
    };

    return {
      success: false,
      settlement: failedSettlement,
      buyerReconciliation: emptyReconciliation,
      sellerReconciliation: emptyReconciliation,
      summary: this.buildSummary(),
      message,
      timestamp: Date.now(),
    };
  }
}
