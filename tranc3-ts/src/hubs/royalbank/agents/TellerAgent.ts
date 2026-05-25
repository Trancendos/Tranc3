/**
 * TellerAgent — Transaction Processing Agent for The Royal Bank of Arcadia
 *
 * Identity:  SID-ROYALBANK-TELLER
 * Tier:      4 (Autonomous Microservice)
 * Parent:    RoyalBankOfArcadiaAI (AID-ROYALBANK)
 *
 * Responsibilities:
 *   - Process transfers between accounts with validation
 *   - Handle deposits and withdrawals
 *   - Check account balances and transaction history
 *   - Enforce transaction limits and fees
 *   - Track transaction volume and patterns
 *
 * "The teller's window never closes — but the vault has rules."
 */

import { Agent, Logger, AuditLedger } from '../../../core/definitions';

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface TellerInput {
  operation: 'transfer' | 'deposit' | 'withdraw' | 'balance';
  fromAccountId?: string;
  toAccountId?: string;
  accountId?: string;
  amount?: number;
  currency?: 'credits' | 'tokens' | 'gold';
  description?: string;
  reference?: string;
}

export interface AccountBalance {
  accountId: string;
  balance: number;
  currency: string;
  availableBalance: number;
  pendingTransactions: number;
  lastDeposit: number;
  lastWithdrawal: number;
}

export interface TransactionResult {
  transactionId: string;
  type: string;
  fromAccountId?: string;
  toAccountId?: string;
  amount: number;
  currency: string;
  fee: number;
  status: 'completed' | 'pending' | 'failed';
  description: string;
  processedAt: number;
}

export interface TellerResult {
  success: boolean;
  operation: TellerInput['operation'];
  transaction?: TransactionResult;
  balance?: AccountBalance;
  message: string;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Transaction Limits & Fees
// ─────────────────────────────────────────────────────────────────────────────

const TRANSACTION_LIMITS = {
  personal: { dailyMax: 10000, perTransactionMax: 5000, feeRate: 0.001 },
  business: { dailyMax: 100000, perTransactionMax: 50000, feeRate: 0.0005 },
  treasury: { dailyMax: Infinity, perTransactionMax: Infinity, feeRate: 0 },
  escrow:   { dailyMax: 50000, perTransactionMax: 25000, feeRate: 0.002 },
  system:   { dailyMax: Infinity, perTransactionMax: Infinity, feeRate: 0 },
};

// ─────────────────────────────────────────────────────────────────────────────
// TellerAgent Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class TellerAgent extends Agent {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private readonly accounts: Map<string, { balance: number; type: string; currency: string; dailyTotal: number; lastReset: number }>;
  private transactionCounter: number;

  constructor() {
    super('SID-ROYALBANK-TELLER');
    this.log = new Logger('TellerAgent');
    this.audit = AuditLedger.getInstance();
    this.accounts = new Map();
    this.transactionCounter = 0;

    // Initialize treasury account
    this.accounts.set('ACC-TREASURY', {
      balance: 10000000,
      type: 'treasury',
      currency: 'credits',
      dailyTotal: 0,
      lastReset: Date.now(),
    });
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Agent Lifecycle: Perceive → Decide → Act
  // ─────────────────────────────────────────────────────────────────────────

  protected async perceive(input: TellerInput): Promise<TellerInput> {
    this.log.info('Perceiving teller operation', { operation: input.operation });

    // Validate account references
    if (input.fromAccountId && !this.accounts.has(input.fromAccountId)) {
      this.log.debug('Source account not in local cache — will verify during processing', { fromAccountId: input.fromAccountId });
    }

    // Validate amount
    if (input.amount !== undefined && input.amount <= 0) {
      this.log.warn('Invalid amount specified', { amount: input.amount });
    }

    return input;
  }

  protected async decide(input: TellerInput): Promise<string> {
    this.log.info('Deciding teller action', { operation: input.operation });

    switch (input.operation) {
      case 'transfer': return 'processTransfer';
      case 'deposit': return 'processDeposit';
      case 'withdraw': return 'processWithdrawal';
      case 'balance': return 'checkBalance';
      default: return 'unknown';
    }
  }

  protected async act(input: TellerInput, decision: string): Promise<TellerResult> {
    this.log.info('Acting on teller decision', { decision });

    switch (decision) {
      case 'processTransfer': return this.processTransfer(input);
      case 'processDeposit': return this.processDeposit(input);
      case 'processWithdrawal': return this.processWithdrawal(input);
      case 'checkBalance': return this.checkBalance(input);
      default:
        return {
          success: false,
          operation: input.operation,
          message: `Unknown operation: ${input.operation}`,
          timestamp: Date.now(),
        };
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Transfer
  // ─────────────────────────────────────────────────────────────────────────

  private processTransfer(input: TellerInput): TellerResult {
    const { fromAccountId, toAccountId, amount, currency, description, reference } = input;

    if (!fromAccountId || !toAccountId || !amount || amount <= 0) {
      return {
        success: false,
        operation: 'transfer',
        message: 'Source account, destination account, and positive amount are required',
        timestamp: Date.now(),
      };
    }

    // Get or create account records
    const fromAccount = this.getOrCreateAccount(fromAccountId, 'personal');
    const toAccount = this.getOrCreateAccount(toAccountId, 'personal');

    // Check sufficient balance
    if (fromAccount.balance < amount) {
      return {
        success: false,
        operation: 'transfer',
        message: `Insufficient funds in ${fromAccountId}: balance ${fromAccount.balance}, requested ${amount}`,
        timestamp: Date.now(),
      };
    }

    // Check transaction limits
    const limits = TRANSACTION_LIMITS[fromAccount.type as keyof typeof TRANSACTION_LIMITS] ?? TRANSACTION_LIMITS.personal;
    if (amount > limits.perTransactionMax) {
      return {
        success: false,
        operation: 'transfer',
        message: `Amount ${amount} exceeds per-transaction limit of ${limits.perTransactionMax} for ${fromAccount.type} accounts`,
        timestamp: Date.now(),
      };
    }

    // Calculate fee
    const fee = Math.floor(amount * limits.feeRate * 100) / 100;

    // Process transfer
    fromAccount.balance -= (amount + fee);
    toAccount.balance += amount;
    fromAccount.dailyTotal += amount;

    this.transactionCounter++;
    const transactionId = `TXN-${this.transactionCounter}`;

    const transaction: TransactionResult = {
      transactionId,
      type: 'transfer',
      fromAccountId,
      toAccountId,
      amount,
      currency: currency ?? 'credits',
      fee,
      status: 'completed',
      description: description ?? `Transfer ${amount} ${currency ?? 'credits'} from ${fromAccountId} to ${toAccountId}`,
      processedAt: Date.now(),
    };

    this.audit.append({
      actor: this.id,
      action: 'TRANSFER_PROCESSED',
      entity: transactionId,
      status: 'SUCCESS',
      meta: {
        fromAccountId,
        toAccountId,
        amount,
        fee,
        currency: currency ?? 'credits',
        reference,
      },
    });

    this.log.info('Transfer processed', {
      transactionId,
      fromAccountId,
      toAccountId,
      amount,
      fee,
    });

    return {
      success: true,
      operation: 'transfer',
      transaction,
      message: `Transferred ${amount} ${currency ?? 'credits'} from ${fromAccountId} to ${toAccountId} (fee: ${fee})`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Deposit
  // ─────────────────────────────────────────────────────────────────────────

  private processDeposit(input: TellerInput): TellerResult {
    const { accountId, amount, currency, description } = input;

    if (!accountId || !amount || amount <= 0) {
      return {
        success: false,
        operation: 'deposit',
        message: 'Account ID and positive amount are required',
        timestamp: Date.now(),
      };
    }

    const account = this.getOrCreateAccount(accountId, 'personal');
    account.balance += amount;

    this.transactionCounter++;
    const transactionId = `TXN-${this.transactionCounter}`;

    const transaction: TransactionResult = {
      transactionId,
      type: 'deposit',
      toAccountId: accountId,
      amount,
      currency: currency ?? 'credits',
      fee: 0,
      status: 'completed',
      description: description ?? `Deposit ${amount} ${currency ?? 'credits'} to ${accountId}`,
      processedAt: Date.now(),
    };

    this.audit.append({
      actor: this.id,
      action: 'DEPOSIT_PROCESSED',
      entity: transactionId,
      status: 'SUCCESS',
      meta: { accountId, amount, currency: currency ?? 'credits' },
    });

    this.log.info('Deposit processed', { transactionId, accountId, amount });

    return {
      success: true,
      operation: 'deposit',
      transaction,
      message: `Deposited ${amount} ${currency ?? 'credits'} to ${accountId}. New balance: ${account.balance}`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Withdraw
  // ─────────────────────────────────────────────────────────────────────────

  private processWithdrawal(input: TellerInput): TellerResult {
    const { accountId, amount, currency, description } = input;

    if (!accountId || !amount || amount <= 0) {
      return {
        success: false,
        operation: 'withdraw',
        message: 'Account ID and positive amount are required',
        timestamp: Date.now(),
      };
    }

    const account = this.getOrCreateAccount(accountId, 'personal');

    if (account.balance < amount) {
      return {
        success: false,
        operation: 'withdraw',
        message: `Insufficient funds in ${accountId}: balance ${account.balance}, requested ${amount}`,
        timestamp: Date.now(),
      };
    }

    const limits = TRANSACTION_LIMITS[account.type as keyof typeof TRANSACTION_LIMITS] ?? TRANSACTION_LIMITS.personal;
    const fee = Math.floor(amount * limits.feeRate * 100) / 100;

    account.balance -= (amount + fee);

    this.transactionCounter++;
    const transactionId = `TXN-${this.transactionCounter}`;

    const transaction: TransactionResult = {
      transactionId,
      type: 'withdrawal',
      fromAccountId: accountId,
      amount,
      currency: currency ?? 'credits',
      fee,
      status: 'completed',
      description: description ?? `Withdrawal ${amount} ${currency ?? 'credits'} from ${accountId}`,
      processedAt: Date.now(),
    };

    this.audit.append({
      actor: this.id,
      action: 'WITHDRAWAL_PROCESSED',
      entity: transactionId,
      status: 'SUCCESS',
      meta: { accountId, amount, fee, currency: currency ?? 'credits' },
    });

    this.log.info('Withdrawal processed', { transactionId, accountId, amount, fee });

    return {
      success: true,
      operation: 'withdraw',
      transaction,
      message: `Withdrew ${amount} ${currency ?? 'credits'} from ${accountId} (fee: ${fee}). New balance: ${account.balance}`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Balance Check
  // ─────────────────────────────────────────────────────────────────────────

  private checkBalance(input: TellerInput): TellerResult {
    const accountId = input.accountId ?? input.fromAccountId;

    if (!accountId) {
      return {
        success: false,
        operation: 'balance',
        message: 'Account ID is required',
        timestamp: Date.now(),
      };
    }

    const account = this.accounts.get(accountId);

    if (!account) {
      return {
        success: false,
        operation: 'balance',
        message: `Account ${accountId} not found`,
        timestamp: Date.now(),
      };
    }

    const balance: AccountBalance = {
      accountId,
      balance: account.balance,
      currency: account.currency,
      availableBalance: account.balance, // No holds in simulation
      pendingTransactions: 0,
      lastDeposit: Date.now(),
      lastWithdrawal: Date.now(),
    };

    return {
      success: true,
      operation: 'balance',
      balance,
      message: `Account ${accountId}: ${account.balance} ${account.currency} available`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Helpers
  // ─────────────────────────────────────────────────────────────────────────

  private getOrCreateAccount(accountId: string, type: string): {
    balance: number; type: string; currency: string; dailyTotal: number; lastReset: number;
  } {
    let account = this.accounts.get(accountId);
    if (!account) {
      account = { balance: 0, type, currency: 'credits', dailyTotal: 0, lastReset: Date.now() };
      this.accounts.set(accountId, account);
    }
    return account;
  }
}
