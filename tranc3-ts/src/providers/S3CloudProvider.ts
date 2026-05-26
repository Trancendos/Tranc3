/**
 * Trancendos S3CloudProvider — Emergency lightweight cloud-only mode
 *
 * Implements IStorageProvider for the CLOUD_ONLY topology mode.
 * Used when local TrueNAS hardware is unavailable (maintenance, migration, disaster).
 *
 * Architecture:
 *   - All reads/writes go directly to an S3-compatible endpoint
 *   - Supports AWS S3, MinIO, Oracle Cloud Object Storage, etc.
 *   - Minimal footprint — no local caching by default
 *   - Can be paired with TrueCloudProvider for hybrid sync
 *
 * Candour:
 *   - This is a scaffold. Real implementation requires:
 *     * @aws-sdk/client-s3 or equivalent
 *     * Proper credential rotation via VaultSecretLoader
 *     * Multipart upload for files > 5MB
 *     * Pre-signed URL generation for direct downloads
 *     * Bucket lifecycle policies
 *   - Currently uses in-memory Map as a stand-in for S3 operations
 *   - Zero-cost constraint: use Oracle Cloud free tier or MinIO self-hosted
 */

import { createHash } from 'crypto';
import { IStorageProvider, FileMetadata, StorageHealth, StorageStats } from './IStorageProvider';
import { Logger } from '../core/logger';

const logger = new Logger('S3CloudProvider');

/** In-memory stand-in for S3 objects during development */
interface CloudObject {
  data: Buffer;
  metadata: FileMetadata;
}

export class S3CloudProvider implements IStorageProvider {
  public readonly providerName: string = 's3-cloud';
  public readonly mode: 'CLOUD_ONLY' = 'CLOUD_ONLY';

  private readonly endpoint: string;
  private readonly bucket: string;
  private readonly region: string;

  /** In-memory object store (scaffold — replace with real S3 SDK calls) */
  private readonly store: Map<string, CloudObject> = new Map();

  private _operationsCount: number = 0;
  private _errorCount: number = 0;
  private readonly _startTime: Date = new Date();

  constructor(
    endpoint: string = process.env.S3_ENDPOINT || 'https://s3.us-east-1.oraclecloud.com',
    bucket: string = process.env.S3_BUCKET || 'tranc3-emergency',
    region: string = process.env.S3_REGION || 'us-east-1',
  ) {
    this.endpoint = endpoint;
    this.bucket = bucket;
    this.region = region;
    logger.info('S3CloudProvider initialized', { endpoint, bucket, region });
  }

  /** Read an object from cloud storage */
  async read(path: string): Promise<Buffer> {
    this._operationsCount++;
    const obj = this.store.get(path);
    if (!obj) {
      this._errorCount++;
      logger.warn('Object not found', { path });
      throw new Error(`Object not found: ${path}`);
    }
    logger.debug('Object read', { path, size: obj.data.length });
    return obj.data;
  }

  /** Write an object to cloud storage */
  async write(path: string, data: Buffer): Promise<void> {
    this._operationsCount++;
    const checksumSha256 = createHash('sha256').update(data).digest('hex');
    const now = new Date();
    this.store.set(path, {
      data,
      metadata: {
        path,
        sizeBytes: data.length,
        createdAt: now,
        updatedAt: now,
        mimeType: this.inferMimeType(path),
        checksumSha256,
      },
    });
    logger.debug('Object written', { path, size: data.length });
  }

  /** Delete an object from cloud storage */
  async delete(path: string): Promise<void> {
    this._operationsCount++;
    if (!this.store.has(path)) {
      logger.warn('Object not found for deletion', { path });
      return; // idempotent
    }
    this.store.delete(path);
    logger.debug('Object deleted', { path });
  }

  /** List objects under a prefix */
  async list(path: string): Promise<string[]> {
    this._operationsCount++;
    const prefix = path.endsWith('/') ? path : path + '/';
    const keys: string[] = [];
    for (const key of this.store.keys()) {
      if (key.startsWith(prefix) || key === path) {
        keys.push(key);
      }
    }
    return keys;
  }

  /** Check if an object exists */
  async exists(path: string): Promise<boolean> {
    return this.store.has(path);
  }

  /** Get metadata for an object */
  async getMetadata(path: string): Promise<FileMetadata> {
    this._operationsCount++;
    const obj = this.store.get(path);
    if (!obj) {
      this._errorCount++;
      throw new Error(`Object not found: ${path}`);
    }
    return obj.metadata;
  }

  /** Health check — verify cloud connectivity */
  async healthCheck(): Promise<StorageHealth> {
    const start = Date.now();
    // In production: use S3 HeadBucket or a lightweight ping
    const healthy = true; // scaffold assumption
    return {
      healthy,
      latencyMs: Date.now() - start,
      availableBytes: 0, // S3 is effectively unlimited
      totalBytes: 0,
      mode: this.mode,
      provider: this.providerName,
      lastChecked: new Date(),
    };
  }

  /** Get provider statistics */
  async getStats(): Promise<StorageStats> {
    let totalBytes = 0;
    for (const obj of this.store.values()) {
      totalBytes += obj.metadata.sizeBytes;
    }
    return {
      totalFiles: this.store.size,
      totalBytes,
      availableBytes: 0,
      operationsCount: this._operationsCount,
      errorCount: this._errorCount,
      uptimeSeconds: (Date.now() - this._startTime.getTime()) / 1000,
    };
  }

  /** Infer MIME type from file extension */
  private inferMimeType(path: string): string {
    const ext = path.split('.').pop()?.toLowerCase() || '';
    const mimeMap: Record<string, string> = {
      json: 'application/json',
      txt: 'text/plain',
      ts: 'text/typescript',
      js: 'text/javascript',
      py: 'text/x-python',
      md: 'text/markdown',
      html: 'text/html',
      css: 'text/css',
      png: 'image/png',
      jpg: 'image/jpeg',
      pdf: 'application/pdf',
    };
    return mimeMap[ext] || 'application/octet-stream';
  }
}
