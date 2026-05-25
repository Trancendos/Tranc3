/**
 * VaultBot — Asset Security Bot for The Royal Bank of Arcadia
 *
 * Identity:  NID-ROYALBANK-VAULT
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    RoyalBankOfArcadiaAI (AID-ROYALBANK)
 *
 * Responsibilities:
 *   - Lock assets in secure vault (reserve funds, escrow holds)
 *   - Unlock previously locked assets (release holds, escrow release)
 *   - Verify vault integrity and locked asset balances
 *   - Track vault compartments per account
 *   - Generate vault audit reports with compartment details
 *
 * "The vault remembers every lock, every key, and every hand that turned it."
 */

import { Bot, Logger, AuditLedger } from '../../../core/definitions'

const auditLedger = new AuditLedger();

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface VaultInput {
  operation: 'SECURE';
  accountId: string;
  amount: number;
  action: 'lock' | 'unlock' | 'verify';
  currency?: 'credits' | 'tokens' | 'gold';
  reason?: string;
  compartmentId?: string; // Target specific compartment; auto-assigned if omitted
  releaseToAccountId?: string; // For unlock: destination account
}

export type CurrencyType = 'credits' | 'tokens' | 'gold';

export type CompartmentStatus = 'locked' | 'unlocked' | 'expired' | 'seized';

export interface VaultCompartment {
  compartmentId: string;
  accountId: string;
  amount: number;
  currency: CurrencyType;
  status: CompartmentStatus;
  reason: string;
  lockedAt: number;
  unlockedAt?: number;
  expiresAt?: number;
  accessLog: AccessRecord[];
}

export interface AccessRecord {
  action: 'lock' | 'unlock' | 'verify' | 'extend' | 'seize';
  performedBy: string;
  timestamp: number;
  amount?: number;
  notes?: string;
}

export interface VaultSummary {
  totalCompartments: number;
  activeLocks: number;
  totalLocked: number;
  totalLockedByCurrency: Record<CurrencyType, number>;
  totalUnlocked: number;
  totalExpired: number;
  totalSeized: number;
  lastVerification: number | null;
  vaultIntegrity: 'intact' | 'degraded' | 'compromised';
}

export interface SecureResult {
  success: boolean;
  action: VaultInput['action'];
  compartment?: VaultCompartment;
  vaultSummary?: VaultSummary;
  verificationDetails?: VerificationDetail;
  message: string;
  timestamp: number;
}

export interface VerificationDetail {
  verified: boolean;
  compartmentsChecked: number;
  discrepanciesFound: number;
  totalLockedVerified: number;
  integrityHash: string;
  verifiedAt: number;
  issues: string[];
}

// ─────────────────────────────────────────────────────────────────────────────
// Vault Store (Simulated In-Memory)
// ─────────────────────────────────────────────────────────────────────────────

const compartments: Map<string, VaultCompartment> = new Map();
let compartmentCounter = 0;

// ─────────────────────────────────────────────────────────────────────────────
// VaultBot Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class VaultBot extends Bot {
  private readonly log: Logger;
  private readonly audit: AuditLedger;

  constructor() {
    super(
      'NID-ROYALBANK-VAULT',
      'Vault',
      async (input: VaultInput) => this.handle(input),
      'Asset security vault with lock/unlock/verify for financial holds and escrow'
    );

    this.log = new Logger('VaultBot');
    this.audit = auditLedger;
  }

  private async handle(input: VaultInput): Promise<SecureResult> {
    if (input.operation !== 'SECURE') {
      return this.fail(`Unknown operation: ${input.operation}. VaultBot only accepts SECURE.`);
    }
    return this.secure(input);
  }

  // ─────────────────────────────────────────────────────────────────────────
  // SECURE — Lock, Unlock, or Verify vault assets
  // ─────────────────────────────────────────────────────────────────────────

  private secure(input: VaultInput): SecureResult {
    const { action } = input;

    switch (action) {
      case 'lock': return this.lockAssets(input);
      case 'unlock': return this.unlockAssets(input);
      case 'verify': return this.verifyVault(input);
      default:
        return this.fail(`Unknown vault action: ${action}. Valid actions: lock, unlock, verify.`);
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Lock — Reserve assets in a secure compartment
  // ─────────────────────────────────────────────────────────────────────────

  private lockAssets(input: VaultInput): SecureResult {
    const { accountId, amount, currency, reason, compartmentId } = input;

    if (!accountId || !amount || amount <= 0) {
      return this.fail('Account ID and positive amount are required for locking');
    }

    const resolvedCurrency = currency ?? 'credits';
    const resolvedReason = reason ?? 'Administrative hold';

    // Generate compartment ID
    compartmentCounter++;
    const resolvedCompartmentId = compartmentId ?? `VAULT-CMP-${compartmentCounter.toString().padStart(4, '0')}`;

    // Check if compartment already exists and is active
    const existing = compartments.get(resolvedCompartmentId);
    if (existing && existing.status === 'locked') {
      return this.fail(`Compartment ${resolvedCompartmentId} already has an active lock`);
    }

    // Create the compartment
    const accessRecord: AccessRecord = {
      action: 'lock',
      performedBy: 'NID-ROYALBANK-VAULT',
      timestamp: Date.now(),
      amount,
      notes: resolvedReason,
    };

    const compartment: VaultCompartment = {
      compartmentId: resolvedCompartmentId,
      accountId,
      amount,
      currency: resolvedCurrency,
      status: 'locked',
      reason: resolvedReason,
      lockedAt: Date.now(),
      expiresAt: Date.now() + 90 * 86400000, // 90-day default expiry
      accessLog: [accessRecord],
    };

    compartments.set(resolvedCompartmentId, compartment);

    this.audit.append({
      actor: 'NID-ROYALBANK-VAULT',
      action: 'ASSETS_LOCKED',
      entity: resolvedCompartmentId,
      status: 'SUCCESS',
      meta: {
        accountId,
        amount,
        currency: resolvedCurrency,
        reason: resolvedReason,
        expiresAt: compartment.expiresAt,
      },
    });

    this.log.info('Assets locked in vault', {
      compartmentId: resolvedCompartmentId,
      accountId,
      amount,
      currency: resolvedCurrency,
    });

    return {
      success: true,
      action: 'lock',
      compartment,
      message: `Locked ${amount} ${resolvedCurrency} in compartment ${resolvedCompartmentId} for account ${accountId} (${resolvedReason})`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Unlock — Release assets from a compartment
  // ─────────────────────────────────────────────────────────────────────────

  private unlockAssets(input: VaultInput): SecureResult {
    const { compartmentId, accountId, reason, releaseToAccountId } = input;

    if (!compartmentId) {
      return this.fail('Compartment ID is required for unlocking');
    }

    const compartment = compartments.get(compartmentId);
    if (!compartment) {
      return this.fail(`Compartment ${compartmentId} not found`);
    }

    if (compartment.status !== 'locked') {
      return this.fail(`Compartment ${compartmentId} is not locked (current status: ${compartment.status})`);
    }

    // Validate account ownership
    if (accountId && accountId !== compartment.accountId) {
      return this.fail(`Compartment ${compartmentId} belongs to account ${compartment.accountId}, not ${accountId}`);
    }

    const resolvedReason = reason ?? 'Administrative release';

    // Update compartment
    compartment.status = 'unlocked';
    compartment.unlockedAt = Date.now();

    const accessRecord: AccessRecord = {
      action: 'unlock',
      performedBy: 'NID-ROYALBANK-VAULT',
      timestamp: Date.now(),
      notes: resolvedReason,
    };
    compartment.accessLog.push(accessRecord);

    this.audit.append({
      actor: 'NID-ROYALBANK-VAULT',
      action: 'ASSETS_UNLOCKED',
      entity: compartmentId,
      status: 'SUCCESS',
      meta: {
        accountId: compartment.accountId,
        amount: compartment.amount,
        currency: compartment.currency,
        reason: resolvedReason,
        releaseTo: releaseToAccountId ?? compartment.accountId,
        lockedDuration: Date.now() - compartment.lockedAt,
      },
    });

    this.log.info('Assets unlocked from vault', {
      compartmentId,
      accountId: compartment.accountId,
      amount: compartment.amount,
      currency: compartment.currency,
      lockedDuration: `${Math.floor((Date.now() - compartment.lockedAt) / 86400000)} days`,
    });

    return {
      success: true,
      action: 'unlock',
      compartment,
      message: `Unlocked ${compartment.amount} ${compartment.currency} from compartment ${compartmentId} for account ${compartment.accountId} (${resolvedReason})`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Verify — Audit vault integrity
  // ─────────────────────────────────────────────────────────────────────────

  private verifyVault(input: VaultInput): SecureResult {
    const { accountId } = input;

    const allCompartments = Array.from(compartments.values());
    const targetCompartments = accountId
      ? allCompartments.filter(c => c.accountId === accountId)
      : allCompartments;

    const activeLocks = targetCompartments.filter(c => c.status === 'locked');
    const totalLocked = activeLocks.reduce((sum, c) => sum + c.amount, 0);

    const totalLockedByCurrency: Record<CurrencyType, number> = {
      credits: 0,
      tokens: 0,
      gold: 0,
    };
    for (const lock of activeLocks) {
      totalLockedByCurrency[lock.currency] += lock.amount;
    }

    // Check for discrepancies
    const issues: string[] = [];
    let discrepanciesFound = 0;

    for (const compartment of targetCompartments) {
      // Check for expired locks still showing as locked
      if (compartment.status === 'locked' && compartment.expiresAt && Date.now() > compartment.expiresAt) {
        issues.push(`Compartment ${compartment.compartmentId} has expired but is still locked (expired: ${new Date(compartment.expiresAt).toISOString()})`);
        discrepanciesFound++;
      }

      // Check for missing access log entries
      if (compartment.accessLog.length === 0) {
        issues.push(`Compartment ${compartment.compartmentId} has no access log entries — possible data corruption`);
        discrepanciesFound++;
      }

      // Check for inconsistent state
      if (compartment.status === 'unlocked' && !compartment.unlockedAt) {
        issues.push(`Compartment ${compartment.compartmentId} is unlocked but has no unlock timestamp`);
        discrepanciesFound++;
      }
    }

    // Generate integrity hash
    const hashData = targetCompartments
      .map(c => `${c.compartmentId}:${c.amount}:${c.status}:${c.lockedAt}`)
      .join('|');
    const integrityHash = this.simulateHash(hashData);

    const vaultIntegrity: VaultSummary['vaultIntegrity'] =
      discrepanciesFound === 0 ? 'intact' :
      discrepanciesFound < 3 ? 'degraded' : 'compromised';

    const verification: VerificationDetail = {
      verified: discrepanciesFound === 0,
      compartmentsChecked: targetCompartments.length,
      discrepanciesFound,
      totalLockedVerified: totalLocked,
      integrityHash,
      verifiedAt: Date.now(),
      issues,
    };

    const vaultSummary: VaultSummary = {
      totalCompartments: targetCompartments.length,
      activeLocks: activeLocks.length,
      totalLocked,
      totalLockedByCurrency,
      totalUnlocked: targetCompartments.filter(c => c.status === 'unlocked').length,
      totalExpired: targetCompartments.filter(c => c.status === 'expired').length,
      totalSeized: targetCompartments.filter(c => c.status === 'seized').length,
      lastVerification: Date.now(),
      vaultIntegrity,
    };

    this.audit.append({
      actor: 'NID-ROYALBANK-VAULT',
      action: 'VAULT_VERIFIED',
      entity: accountId ?? 'ALL',
      status: verification.verified ? 'SUCCESS' : 'FAILURE',
      meta: {
        compartmentsChecked: verification.compartmentsChecked,
        discrepanciesFound,
        totalLockedVerified: totalLocked,
        vaultIntegrity,
        integrityHash,
      },
    });

    this.log.info('Vault verification completed', {
      accountId: accountId ?? 'ALL',
      compartmentsChecked: verification.compartmentsChecked,
      discrepanciesFound,
      vaultIntegrity,
    });

    return {
      success: true,
      action: 'verify',
      compartment: undefined,
      vaultSummary,
      verificationDetails: verification,
      message: `Vault verification: ${verification.compartmentsChecked} compartments checked, ${discrepanciesFound} discrepancies, integrity ${vaultIntegrity}`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Helpers
  // ─────────────────────────────────────────────────────────────────────────

  private simulateHash(data: string): string {
    let hash = 0;
    for (let i = 0; i < data.length; i++) {
      const char = data.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash;
    }
    return 'vault-' + Math.abs(hash).toString(16).padStart(16, '0') +
           Math.abs(hash * 31).toString(16).padStart(16, '0');
  }

  private fail(message: string): SecureResult {
    this.log.error('Vault operation failed', { message });
    return {
      success: false,
      action: 'lock',
      message,
      timestamp: Date.now(),
    };
  }
}
