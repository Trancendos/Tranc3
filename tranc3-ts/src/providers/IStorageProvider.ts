/**
 * Trancendos Storage Provider Interface
 *
 * All storage backends (ZFS, TrueCloud, S3, Oracle, Hetzner) must
 * implement this interface. The StorageFactory selects the appropriate
 * provider based on the current environment topology mode:
 *
 *   TRUE_NAS   — local ZFS primary (sovereign mode)
 *   HYBRID     — local ZFS + cloud proxy transition
 *   TRUECLOUD  — local primary + encrypted cloud replica
 *   CLOUD_ONLY — emergency lightweight cloud-only mode
 */

export interface FileMetadata {
  path: string;
  sizeBytes: number;
  createdAt: Date;
  updatedAt: Date;
  mimeType?: string;
  checksumSha256?: string;
  tags?: string[];
}

export interface StorageHealth {
  healthy: boolean;
  latencyMs: number;
  availableBytes: number;
  totalBytes: number;
  mode: 'TRUE_NAS' | 'HYBRID' | 'TRUECLOUD' | 'CLOUD_ONLY';
  provider: string;
  lastChecked: Date;
}

export interface StorageStats {
  totalFiles: number;
  totalBytes: number;
  availableBytes: number;
  operationsCount: number;
  errorCount: number;
  uptimeSeconds: number;
}

export interface IStorageProvider {
  /** Read a file by path, returning its content as a Buffer */
  read(path: string): Promise<Buffer>;

  /** Write a file at the given path */
  write(path: string, data: Buffer): Promise<void>;

  /** Delete a file at the given path */
  delete(path: string): Promise<void>;

  /** List files under a path prefix */
  list(path: string): Promise<string[]>;

  /** Check if a file exists */
  exists(path: string): Promise<boolean>;

  /** Get metadata for a file */
  getMetadata(path: string): Promise<FileMetadata>;

  /** Check provider health */
  healthCheck(): Promise<StorageHealth>;

  /** Get provider statistics */
  getStats(): Promise<StorageStats>;

  /** Provider name identifier */
  readonly providerName: string;

  /** Current topology mode */
  readonly mode: 'TRUE_NAS' | 'HYBRID' | 'TRUECLOUD' | 'CLOUD_ONLY';
}
