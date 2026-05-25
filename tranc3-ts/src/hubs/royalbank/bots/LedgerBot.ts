/**
 * LedgerBot — Immutable Transaction Recording Bot for The Royal Bank of Arcadia
 *
 * Identity:  NID-ROYALBANK-LEDGER
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    RoyalBankOfArcadiaAI (AID-ROYALBANK)
 *
 * Responsibilities:
 *   - Record transactions in immutable double-entry ledger
 *   - Maintain debit/credit balance pairs for every transaction
 *   - Generate transaction IDs with sequential integrity
 *   - Compute running balances after each entry
 *   - Produce ledger proofs for audit verification
 *
 * "What is written in the ledger cannot be unwritten — only reversed with another entry."
 */

import { Bot, Logger, AuditLedger } from '../../../core/definitions'

const auditLedger = new AuditLedger();

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface LedgerInput {
  operation: 'RECORD';
  fromAccountId: string;
  toAccountId: string;
  amount: number;
  currency: 'credits' | 'tokens' | 'gold';
  type: 'transfer' | 'payment' | 'deposit' | 'withdrawal' | 'exchange' | 'escrow' | 'fee';
  description: string;
  reference?: string;
  metadata?: Record<string, unknown>;
}

export type CurrencyType = 'credits' | 'tokens' | 'gold';

export interface LedgerEntry {
  entryId: string;
  transactionId: string;
  accountId: string;
  side: 'debit' | 'credit';
  amount: number;
  currency: CurrencyType;
  runningBalance: number;
  timestamp: number;
  description: string;
  contraAccountId: string; // The other side of the double entry
  reference?: string;
}

export interface DoubleEntry {
  transactionId: string;
  debit: LedgerEntry;
  credit: LedgerEntry;
  balanced: boolean;
  recordedAt: number;
}

export interface LedgerProof {
  transactionId: string;
  debitHash: string;
  creditHash: string;
  combinedHash: string;
  previousProofHash: string | null;
  proofTimestamp: number;
  verified: boolean;
}

export interface RecordResult {
  success: boolean;
  transactionId: string;
  doubleEntry: DoubleEntry;
  proof: LedgerProof;
  fromAccountBalance: number;
  toAccountBalance: number;
  currency: CurrencyType;
  message: string;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Account Balance Tracker (Simulated)
// ─────────────────────────────────────────────────────────────────────────────

const accountBalances: Map<string, { balance: number; currency: CurrencyType }> = new Map([
  ['ACC-TREASURY', { balance: 10000000, currency: 'credits' }],
]);

// ─────────────────────────────────────────────────────────────────────────────
// LedgerBot Implementation
// ─────────────────────────────────────────────────────────────────────────────



export class LedgerBot extends Bot {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private transactionCounter: number;
  private readonly proofs: Map<string, LedgerProof>;
  private lastProofHash: string | null;

  constructor() {
    super(
      'NID-ROYALBANK-LEDGER',
      'Ledger',
      async (input: LedgerInput) => this.handle(input),
      'Immutable double-entry ledger recording for financial transactions'
    );

    this.log = new Logger('LedgerBot');
    this.audit = auditLedger;
    this.transactionCounter = 0;
    this.proofs = new Map();
    this.lastProofHash = null;
  }

  private async handle(input: LedgerInput): Promise<RecordResult> {
    if (input.operation !== 'RECORD') {
      return this.fail(`Unknown operation: ${input.operation}. LedgerBot only accepts RECORD.`);
    }
    return this.record(input);
  }

  // ─────────────────────────────────────────────────────────────────────────
  // RECORD — Create immutable double-entry
  // ─────────────────────────────────────────────────────────────────────────

  private record(input: LedgerInput): RecordResult {
    const { fromAccountId, toAccountId, amount, currency, type, description, reference, metadata } = input;

    // Validate inputs
    if (!fromAccountId || !toAccountId) {
      return this.fail('Both fromAccountId and toAccountId are required');
    }

    if (!amount || amount <= 0) {
      return this.fail('Amount must be a positive number');
    }

    // For deposits, fromAccountId is the system; for withdrawals, toAccountId is the system
    const effectiveFrom = type === 'deposit' ? 'ACC-SYSTEM' : fromAccountId;
    const effectiveTo = type === 'withdrawal' ? 'ACC-SYSTEM' : toAccountId;

    // Get or initialise account balances
    const fromAccount = this.getOrCreateAccount(effectiveFrom, currency);
    const toAccount = this.getOrCreateAccount(effectiveTo, currency);

    // Generate transaction ID
    this.transactionCounter++;
    const transactionId = `TXN-${this.transactionCounter.toString().padStart(6, '0')}`;

    // Build double-entry: debit the receiver, credit the sender
    const debitEntry: LedgerEntry = {
      entryId: `E-${transactionId}-DR`,
      transactionId,
      accountId: effectiveTo,
      side: 'debit',
      amount,
      currency,
      runningBalance: toAccount.balance + amount,
      timestamp: Date.now(),
      description: `${type}: ${description}`,
      contraAccountId: effectiveFrom,
      reference,
    };

    const creditEntry: LedgerEntry = {
      entryId: `E-${transactionId}-CR`,
      transactionId,
      accountId: effectiveFrom,
      side: 'credit',
      amount,
      currency,
      runningBalance: fromAccount.balance - amount,
      timestamp: Date.now(),
      description: `${type}: ${description}`,
      contraAccountId: effectiveTo,
      reference,
    };

    // Update balances
    fromAccount.balance -= amount;
    toAccount.balance += amount;
    accountBalances.set(effectiveFrom, fromAccount);
    accountBalances.set(effectiveTo, toAccount);

    // Build double-entry record
    const doubleEntry: DoubleEntry = {
      transactionId,
      debit: debitEntry,
      credit: creditEntry,
      balanced: debitEntry.amount === creditEntry.amount, // Must always be true
      recordedAt: Date.now(),
    };

    // Generate ledger proof (hash chain)
    const proof = this.generateProof(transactionId, debitEntry, creditEntry);
    this.proofs.set(transactionId, proof);
    this.lastProofHash = proof.combinedHash;

    this.audit.append({
      actor: 'NID-ROYALBANK-LEDGER',
      action: 'LEDGER_ENTRY_RECORDED',
      entity: transactionId,
      status: 'SUCCESS',
      meta: {
        type,
        fromAccountId: effectiveFrom,
        toAccountId: effectiveTo,
        amount,
        currency,
        debitEntryId: debitEntry.entryId,
        creditEntryId: creditEntry.entryId,
        balanced: doubleEntry.balanced,
        proofHash: proof.combinedHash,
      },
    });

    this.log.info('Ledger entry recorded', {
      transactionId,
      type,
      fromAccountId: effectiveFrom,
      toAccountId: effectiveTo,
      amount,
      currency,
      balanced: doubleEntry.balanced,
    });

    return {
      success: true,
      transactionId,
      doubleEntry,
      proof,
      fromAccountBalance: fromAccount.balance,
      toAccountBalance: toAccount.balance,
      currency,
      message: `Recorded ${type} of ${amount} ${currency} from ${effectiveFrom} to ${effectiveTo} as ${transactionId}`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Proof Generation — Hash chain for integrity
  // ─────────────────────────────────────────────────────────────────────────

  private generateProof(
    transactionId: string,
    debit: LedgerEntry,
    credit: LedgerEntry
  ): LedgerProof {
    // Simulated hash generation (deterministic for same inputs)
    const debitData = `${debit.entryId}:${debit.accountId}:${debit.amount}:${debit.runningBalance}`;
    const creditData = `${credit.entryId}:${credit.accountId}:${credit.amount}:${credit.runningBalance}`;

    const debitHash = this.simulateHash(debitData);
    const creditHash = this.simulateHash(creditData);
    const combinedHash = this.simulateHash(`${debitHash}${creditHash}`);

    return {
      transactionId,
      debitHash,
      creditHash,
      combinedHash,
      previousProofHash: this.lastProofHash,
      proofTimestamp: Date.now(),
      verified: debit.amount === credit.amount, // Double-entry must balance
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Helpers
  // ─────────────────────────────────────────────────────────────────────────

  private getOrCreateAccount(accountId: string, currency: CurrencyType): { balance: number; currency: CurrencyType } {
    let account = accountBalances.get(accountId);
    if (!account) {
      account = { balance: 0, currency };
      accountBalances.set(accountId, account);
    }
    return account;
  }

  private simulateHash(data: string): string {
    // Deterministic pseudo-hash for simulation purposes
    let hash = 0;
    for (let i = 0; i < data.length; i++) {
      const char = data.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash; // Convert to 32-bit integer
    }
    return Math.abs(hash).toString(16).padStart(16, '0') +
           Math.abs(hash * 31).toString(16).padStart(16, '0') +
           Math.abs(hash * 37).toString(16).padStart(16, '0') +
           Math.abs(hash * 41).toString(16).padStart(16, '0');
  }

  private fail(message: string): RecordResult {
    this.log.error('Ledger recording failed', { message });
    return {
      success: false,
      transactionId: '',
      doubleEntry: {
        transactionId: '',
        debit: {} as LedgerEntry,
        credit: {} as LedgerEntry,
        balanced: false,
        recordedAt: 0,
      },
      proof: {} as LedgerProof,
      fromAccountBalance: 0,
      toAccountBalance: 0,
      currency: 'credits',
      message,
      timestamp: Date.now(),
    };
  }
}

// Singleton instance
export const ledgerBot = new LedgerBot();
