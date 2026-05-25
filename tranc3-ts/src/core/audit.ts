/**
 * Trancendos AuditLedger — append-only audit ledger
 *
 * Design:
 *   - Append-only JSON records with SHA-256 hash chaining
 *   - Each entry links to the previous entry's hash (integrity chain)
 *   - RSA signature verification scaffold (production: use real key management)
 *   - The Observatory consumes this ledger for observability / anomaly detection
 *
 * Candour note:
 *   - RSA key generation here is a scaffold. Production must use VaultSecretLoader
 *     or HSM-backed keys. In-memory keys are ephemeral and not secure for real use.
 *   - The ledger is in-memory. Production must persist to ZFS / TrueCloud storage.
 */

import { createHash, createSign, createVerify, generateKeyPairSync } from 'crypto';
import { AuditEntry } from './definitions';
import { Logger } from './logger';

const logger = new Logger('AuditLedger');

interface SignedAuditEntry extends AuditEntry {
  id: string;
  timestamp: Date;
  previousHash: string;
  hash: string;
  signature?: string;
}

export class AuditLedger {
  private readonly ledger: SignedAuditEntry[] = [];
  private lastHash: string = 'GENESIS';
  private readonly privateKey: string;
  private readonly publicKey: string;
  private readonly signEntries: boolean;

  constructor(signEntries: boolean = false) {
    this.signEntries = signEntries;
    if (signEntries) {
      const keyPair = generateKeyPairSync('rsa', {
        modulusLength: 2048,
      });
      this.privateKey = keyPair.privateKey.export({ type: 'pkcs1', format: 'pem' }).toString();
      this.publicKey = keyPair.publicKey.export({ type: 'pkcs1', format: 'pem' }).toString();
    } else {
      this.privateKey = '';
      this.publicKey = '';
    }
  }

  /** Append an entry to the immutable ledger */
  async append(entry: AuditEntry): Promise<string> {
    const id = `AUD-${this.ledger.length.toString().padStart(8, '0')}-${Date.now()}`;
    const timestamp = new Date();

    const signedEntry: SignedAuditEntry = {
      ...entry,
      id,
      timestamp,
      previousHash: this.lastHash,
      hash: '', // computed below
    };

    // Compute SHA-256 hash of entry content
    const content = JSON.stringify({
      actor: signedEntry.actor,
      action: signedEntry.action,
      entity: signedEntry.entity,
      status: signedEntry.status,
      meta: signedEntry.meta,
      previousHash: signedEntry.previousHash,
      timestamp: signedEntry.timestamp.toISOString(),
    });
    signedEntry.hash = createHash('sha256').update(content).digest('hex');

    // RSA signature (if enabled)
    if (this.signEntries && this.privateKey) {
      const signer = createSign('RSA-SHA256');
      signer.update(signedEntry.hash);
      signer.end();
      signedEntry.signature = signer.sign(this.privateKey, 'hex');
    }

    this.lastHash = signedEntry.hash;
    this.ledger.push(signedEntry);

    logger.debug('Audit entry appended', { id, action: entry.action, entity: entry.entity });
    return id;
  }

  /** Verify the entire chain integrity */
  verifyChain(): { valid: boolean; brokenAt: number | null } {
    for (let i = 0; i < this.ledger.length; i++) {
      const entry = this.ledger[i];

      // Verify previous hash linkage
      const expectedPrevHash = i === 0 ? 'GENESIS' : this.ledger[i - 1].hash;
      if (entry.previousHash !== expectedPrevHash) {
        return { valid: false, brokenAt: i };
      }

      // Verify hash of content
      const content = JSON.stringify({
        actor: entry.actor,
        action: entry.action,
        entity: entry.entity,
        status: entry.status,
        meta: entry.meta,
        previousHash: entry.previousHash,
        timestamp: entry.timestamp.toISOString(),
      });
      const computedHash = createHash('sha256').update(content).digest('hex');
      if (entry.hash !== computedHash) {
        return { valid: false, brokenAt: i };
      }

      // Verify RSA signature (if present)
      if (entry.signature && this.publicKey) {
        const verifier = createVerify('RSA-SHA256');
        verifier.update(entry.hash);
        verifier.end();
        if (!verifier.verify(this.publicKey, entry.signature, 'hex')) {
          return { valid: false, brokenAt: i };
        }
      }
    }
    return { valid: true, brokenAt: null };
  }

  /** Query entries by actor, action, entity, or time range */
  query(filters: {
    actor?: string;
    action?: string;
    entity?: string;
    since?: Date;
    until?: Date;
    limit?: number;
  }): AuditEntry[] {
    let results = this.ledger;
    if (filters.actor) results = results.filter(e => e.actor === filters.actor);
    if (filters.action) results = results.filter(e => e.action === filters.action);
    if (filters.entity) results = results.filter(e => e.entity === filters.entity);
    if (filters.since) results = results.filter(e => e.timestamp >= filters.since!);
    if (filters.until) results = results.filter(e => e.timestamp <= filters.until!);
    if (filters.limit) results = results.slice(-filters.limit);
    return results;
  }

  /** Get total entry count */
  get length(): number {
    return this.ledger.length;
  }

  /** Get a specific entry by ID */
  getById(id: string): SignedAuditEntry | undefined {
    return this.ledger.find(e => e.id === id);
  }

  /** Get latest N entries */
  tail(n: number = 20): SignedAuditEntry[] {
    return this.ledger.slice(-n);
  }
}
