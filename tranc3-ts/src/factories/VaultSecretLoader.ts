/**
 * Trancendos VaultSecretLoader — AES-256-GCM secret management
 *
 * Provides encrypted storage and retrieval of sensitive configuration
 * such as API keys, database credentials, and cloud access tokens.
 *
 * Architecture:
 *   - Secrets are stored as encrypted files on the storage provider
 *   - AES-256-GCM provides authenticated encryption (confidentiality + integrity)
 *   - Master key derived from environment variable or TPM-protected key
 *   - Each secret gets a unique IV — never reused
 *   - Key rotation: new master key re-encrypts all secrets
 *
 * Security model:
 *   - Master key comes from: VAULT_MASTER_KEY env var (dev) or TPM/HSM (production)
 *   - Encrypted secret files stored at: .vault/secrets/<secret-name>.enc
 *   - Metadata (IV, authTag, version) stored alongside ciphertext
 *   - Audit log entry for every access (via AuditLedger)
 *
 * Candour:
 *   - This is a production-oriented scaffold. Real deployment needs:
 *     * TPM 2.0 or HSM for master key protection
 *     * HashiCorp Vault or similar for distributed secret management
 *     * Secret rotation policies
 *     * Access control lists per secret
 *   - The master key in env vars is a dev convenience only
 *   - No zero-knowledge proof implementation yet — future work
 *   - Key rotation re-encrypts but doesn't delete old versions (need garbage collection)
 */

import { randomBytes, createCipheriv, createDecipheriv, scryptSync } from 'crypto';
import { IStorageProvider } from '../providers/IStorageProvider';
import { StorageFactory } from './StorageFactory';
import { AuditLedger } from '../core/audit';
import { Logger } from '../core/logger';

const auditLedger = new AuditLedger();

const logger = new Logger('VaultSecretLoader');

/** Encrypted secret envelope */
interface SecretEnvelope {
  name: string;
  iv: string;           // Base64 IV (unique per encryption)
  authTag: string;      // Base64 GCM auth tag
  ciphertext: string;   // Base64 encrypted secret value
  version: number;      // Encryption version for key rotation
  createdAt: string;    // ISO timestamp
  updatedAt: string;    // ISO timestamp
  metadata?: Record<string, string>; // Optional tags/description
}

/** Options for storing a secret */
interface SecretOptions {
  metadata?: Record<string, string>;
  overwrite?: boolean;
}

export class VaultSecretLoader {
  private readonly masterKey: Buffer;
  private readonly storageProvider: IStorageProvider;
  private readonly auditLedger: AuditLedger;
  private readonly vaultPath: string;
  private readonly version: number = 1;
  private readonly cache: Map<string, string> = new Map();

  constructor(
    storageProvider?: IStorageProvider,
    auditLedger?: AuditLedger,
    vaultPath: string = '.vault/secrets',
    masterKeyPassword?: string,
  ) {
    this.storageProvider = storageProvider || StorageFactory.create();
    this.auditLedger = auditLedger || new AuditLedger();
    this.vaultPath = vaultPath;

    // Derive AES-256 key from password using scrypt
    const password = masterKeyPassword || process.env.VAULT_MASTER_KEY || 'dev-master-key-change-in-production';
    const salt = 'tranc3-vault-salt-v1'; // Production: unique salt per deployment, stored separately
    this.masterKey = scryptSync(password, salt, 32);

    logger.info('VaultSecretLoader initialized', { vaultPath });
  }

  /** Get the storage path for a named secret */
  private secretPath(name: string): string {
    // Sanitize name to prevent path traversal
    const sanitized = name.replace(/[^a-zA-Z0-9_-]/g, '_');
    return `${this.vaultPath}/${sanitized}.enc`;
  }

  /** Encrypt a plaintext string */
  private encrypt(plaintext: string): { iv: string; authTag: string; ciphertext: string } {
    const iv = randomBytes(16);
    const cipher = createCipheriv('aes-256-gcm', this.masterKey, iv);
    const encrypted = Buffer.concat([cipher.update(plaintext, 'utf8'), cipher.final()]);
    const authTag = cipher.getAuthTag();

    return {
      iv: iv.toString('base64'),
      authTag: authTag.toString('base64'),
      ciphertext: encrypted.toString('base64'),
    };
  }

  /** Decrypt a ciphertext using the stored envelope */
  private decrypt(envelope: SecretEnvelope): string {
    const iv = Buffer.from(envelope.iv, 'base64');
    const authTag = Buffer.from(envelope.authTag, 'base64');
    const ciphertext = Buffer.from(envelope.ciphertext, 'base64');

    const decipher = createDecipheriv('aes-256-gcm', this.masterKey, iv);
    decipher.setAuthTag(authTag);
    const decrypted = Buffer.concat([decipher.update(ciphertext), decipher.final()]);

    return decrypted.toString('utf8');
  }

  /**
   * Store a secret with AES-256-GCM encryption.
   *
   * @param name - Secret identifier (e.g., 'openrouter-api-key')
   * @param value - The plaintext value to encrypt and store
   * @param options - Optional metadata and overwrite behavior
   */
  async setSecret(name: string, value: string, options?: SecretOptions): Promise<void> {
    const path = this.secretPath(name);

    // Check if secret already exists
    const exists = await this.storageProvider.exists(path);
    if (exists && !options?.overwrite) {
      throw new Error(`Secret '${name}' already exists. Use overwrite: true to replace.`);
    }

    const encrypted = this.encrypt(value);
    const now = new Date().toISOString();

    const envelope: SecretEnvelope = {
      name,
      iv: encrypted.iv,
      authTag: encrypted.authTag,
      ciphertext: encrypted.ciphertext,
      version: this.version,
      createdAt: now,
      updatedAt: now,
      metadata: options?.metadata,
    };

    await this.storageProvider.write(path, Buffer.from(JSON.stringify(envelope), 'utf8'));

    // Update cache
    this.cache.set(name, value);

    // Audit log
    await this.auditLedger.append({
      actor: 'VaultSecretLoader',
      action: exists ? 'SECRET_UPDATED' : 'SECRET_CREATED',
      entity: name,
      status: 'SUCCESS',
      meta: { path, version: this.version },
    });

    logger.info('Secret stored', { name, path, updated: exists });
  }

  /**
   * Retrieve and decrypt a secret by name.
   *
   * @param name - Secret identifier
   * @returns The decrypted plaintext value
   */
  async getSecret(name: string): Promise<string> {
    // Check cache first
    if (this.cache.has(name)) {
      logger.debug('Secret from cache', { name });
      return this.cache.get(name)!;
    }

    const path = this.secretPath(name);

    try {
      const data = await this.storageProvider.read(path);
      const envelope: SecretEnvelope = JSON.parse(data.toString('utf8'));

      // Verify version compatibility
      if (envelope.version !== this.version) {
        logger.warn('Secret version mismatch', {
          name,
          storedVersion: envelope.version,
          currentVersion: this.version,
        });
        // In production: trigger re-encryption with current key
      }

      const plaintext = this.decrypt(envelope);
      this.cache.set(name, plaintext);

      // Audit log
      await this.auditLedger.append({
        actor: 'VaultSecretLoader',
        action: 'SECRET_ACCESSED',
        entity: name,
        status: 'SUCCESS',
      });

      logger.debug('Secret retrieved', { name });
      return plaintext;
    } catch (err: any) {
      // Audit log
      await this.auditLedger.append({
        actor: 'VaultSecretLoader',
        action: 'SECRET_ACCESS_FAILED',
        entity: name,
        status: 'FAILURE',
        meta: { error: err.message },
      });

      logger.error('Failed to retrieve secret', { name, error: err.message });
      throw new Error(`Failed to retrieve secret '${name}': ${err.message}`);
    }
  }

  /**
   * Delete a secret by name.
   *
   * @param name - Secret identifier
   */
  async deleteSecret(name: string): Promise<void> {
    const path = this.secretPath(name);
    await this.storageProvider.delete(path);
    this.cache.delete(name);

    await this.auditLedger.append({
      actor: 'VaultSecretLoader',
      action: 'SECRET_DELETED',
      entity: name,
      status: 'SUCCESS',
    });

    logger.info('Secret deleted', { name });
  }

  /**
   * Check if a secret exists.
   */
  async hasSecret(name: string): Promise<boolean> {
    if (this.cache.has(name)) return true;
    const path = this.secretPath(name);
    return this.storageProvider.exists(path);
  }

  /**
   * Rotate the master key by re-encrypting all secrets.
   *
   * This generates a new master key from a new password, reads all
   * existing secrets, decrypts them with the old key, and re-encrypts
   * with the new key.
   *
   * @param newPassword - New master key password
   */
  async rotateKey(newPassword: string): Promise<number> {
    logger.warn('Key rotation initiated — this is a critical operation');

    const oldKey = this.masterKey;
    const newSalt = `tranc3-vault-salt-v${this.version + 1}`;
    const newKey = scryptSync(newPassword, newSalt, 32);

    // List all secrets
    const secretFiles = await this.storageProvider.list(this.vaultPath);
    let rotatedCount = 0;

    for (const filePath of secretFiles) {
      try {
        const data = await this.storageProvider.read(filePath);
        const envelope: SecretEnvelope = JSON.parse(data.toString('utf8'));

        // Decrypt with old key
        const iv = Buffer.from(envelope.iv, 'base64');
        const authTag = Buffer.from(envelope.authTag, 'base64');
        const ciphertext = Buffer.from(envelope.ciphertext, 'base64');

        const decipher = createDecipheriv('aes-256-gcm', oldKey, iv);
        decipher.setAuthTag(authTag);
        const decrypted = Buffer.concat([decipher.update(ciphertext), decipher.final()]);
        const plaintext = decrypted.toString('utf8');

        // Re-encrypt with new key
        const newIv = randomBytes(16);
        const cipher = createCipheriv('aes-256-gcm', newKey, newIv);
        const newEncrypted = Buffer.concat([cipher.update(plaintext, 'utf8'), cipher.final()]);
        const newAuthTag = cipher.getAuthTag();

        const newEnvelope: SecretEnvelope = {
          ...envelope,
          iv: newIv.toString('base64'),
          authTag: newAuthTag.toString('base64'),
          ciphertext: newEncrypted.toString('base64'),
          version: this.version + 1,
          updatedAt: new Date().toISOString(),
        };

        await this.storageProvider.write(filePath, Buffer.from(JSON.stringify(newEnvelope), 'utf8'));
        rotatedCount++;
      } catch (err: any) {
        logger.error('Failed to rotate secret', { filePath, error: err.message });
      }
    }

    // Update master key reference (note: this.masterKey is readonly, so in production
    // this would trigger a reload of the VaultSecretLoader instance)
    logger.info('Key rotation complete', { rotatedCount, total: secretFiles.length });

    await this.auditLedger.append({
      actor: 'VaultSecretLoader',
      action: 'KEY_ROTATION',
      entity: 'master-key',
      status: rotatedCount === secretFiles.length ? 'SUCCESS' : 'FAILURE',
      meta: { rotatedCount, total: secretFiles.length },
    });

    return rotatedCount;
  }

  /** Clear the in-memory cache (useful for security hardening) */
  clearCache(): void {
    this.cache.clear();
    logger.debug('Secret cache cleared');
  }
}
