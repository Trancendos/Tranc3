/**
 * Trancendos ZFSProvider — Local filesystem storage provider
 *
 * Implements IStorageProvider for the TRUE_NAS topology mode.
 * Uses Node.js fs/promises for direct filesystem access on ZFS-backed mounts.
 *
 * Production notes:
 *   - In TRUE_NAS mode, this runs on the GEEKOM mini PC with ZFS pools
 *   - Uses ZFS snapshot/scrub capabilities via optional shell commands
 *   - The `rootDir` should map to a ZFS dataset mount point (e.g. /tank/tranc3)
 *   - For now, this uses local fs; a production version would call zfs CLI
 *     for snapshots, sends, and scrubs
 *
 * Candour:
 *   - This is a production-oriented scaffold. It will read/write real files
 *     but does NOT yet call `zfs snapshot`, `zfs scrub`, etc.
 *   - Checksums are computed in-application, not via ZFS native checksums
 *   - Quota management is not implemented — relies on ZFS dataset quotas
 */

import { promises as fs } from 'fs';
import { createHash } from 'crypto';
import { join, dirname, basename } from 'path';
import { IStorageProvider, FileMetadata, StorageHealth, StorageStats } from './IStorageProvider';
import { Logger } from '../core/logger';

const logger = new Logger('ZFSProvider');

export class ZFSProvider implements IStorageProvider {
  public readonly providerName: string = 'zfs-local';
  public readonly mode: 'TRUE_NAS' = 'TRUE_NAS';

  private readonly rootDir: string;
  private _operationsCount: number = 0;
  private _errorCount: number = 0;
  private readonly _startTime: Date = new Date();

  constructor(rootDir: string = process.env.ZFS_ROOT || '/tank/tranc3') {
    this.rootDir = rootDir;
    logger.info('ZFSProvider initialized', { rootDir });
  }

  /** Resolve a logical path to a physical path under rootDir */
  private resolve(path: string): string {
    // Prevent path traversal
    const resolved = join(this.rootDir, path);
    if (!resolved.startsWith(this.rootDir)) {
      throw new Error(`Path traversal detected: ${path}`);
    }
    return resolved;
  }

  /** Increment operation counter */
  private tick(): void {
    this._operationsCount++;
  }

  /** Read a file by logical path */
  async read(path: string): Promise<Buffer> {
    this.tick();
    try {
      const resolved = this.resolve(path);
      const data = await fs.readFile(resolved);
      logger.debug('File read', { path, size: data.length });
      return data;
    } catch (err: any) {
      this._errorCount++;
      if (err.code === 'ENOENT') {
        logger.warn('File not found', { path });
        throw new Error(`File not found: ${path}`);
      }
      logger.error('Read error', { path, error: err.message });
      throw err;
    }
  }

  /** Write a file at the given logical path */
  async write(path: string, data: Buffer): Promise<void> {
    this.tick();
    try {
      const resolved = this.resolve(path);
      // Ensure parent directory exists
      await fs.mkdir(dirname(resolved), { recursive: true });
      await fs.writeFile(resolved, data);
      logger.debug('File written', { path, size: data.length });
    } catch (err: any) {
      this._errorCount++;
      logger.error('Write error', { path, error: err.message });
      throw err;
    }
  }

  /** Delete a file at the given logical path */
  async delete(path: string): Promise<void> {
    this.tick();
    try {
      const resolved = this.resolve(path);
      await fs.unlink(resolved);
      logger.debug('File deleted', { path });
    } catch (err: any) {
      this._errorCount++;
      if (err.code === 'ENOENT') {
        logger.warn('File not found for deletion', { path });
        return; // idempotent delete
      }
      logger.error('Delete error', { path, error: err.message });
      throw err;
    }
  }

  /** List files under a logical path prefix */
  async list(path: string): Promise<string[]> {
    this.tick();
    try {
      const resolved = this.resolve(path);
      const entries = await fs.readdir(resolved, { withFileTypes: true });
      const files: string[] = [];
      for (const entry of entries) {
        const fullPath = join(path, entry.name);
        if (entry.isDirectory()) {
          // Recurse one level for simplicity; deep recursion available via helper
          const subFiles = await this.list(join(path, entry.name));
          files.push(...subFiles);
        } else {
          files.push(fullPath);
        }
      }
      return files;
    } catch (err: any) {
      this._errorCount++;
      if (err.code === 'ENOENT') return [];
      logger.error('List error', { path, error: err.message });
      throw err;
    }
  }

  /** Check if a file exists */
  async exists(path: string): Promise<boolean> {
    try {
      const resolved = this.resolve(path);
      await fs.access(resolved);
      return true;
    } catch {
      return false;
    }
  }

  /** Get metadata for a file */
  async getMetadata(path: string): Promise<FileMetadata> {
    this.tick();
    const resolved = this.resolve(path);
    let handle: fs.FileHandle | undefined;
    try {
      handle = await fs.open(resolved, 'r');
      const stat = await handle.stat();
      const data = await handle.readFile();
      const checksumSha256 = createHash('sha256').update(data).digest('hex');

      return {
        path,
        sizeBytes: stat.size,
        createdAt: stat.birthtime,
        updatedAt: stat.mtime,
        mimeType: this.inferMimeType(path),
        checksumSha256,
      };
    } catch (err: any) {
      this._errorCount++;
      logger.error('Metadata error', { path, error: err.message });
      throw err;
    } finally {
      await handle?.close();
    }
  }

  /** Check provider health */
  async healthCheck(): Promise<StorageHealth> {
    const start = Date.now();
    try {
      const stat = await fs.stat(this.rootDir);
      const latencyMs = Date.now() - start;
      return {
        healthy: true,
        latencyMs,
        availableBytes: 0, // Would use `df` or ZFS quota in production
        totalBytes: 0,
        mode: this.mode,
        provider: this.providerName,
        lastChecked: new Date(),
      };
    } catch (err: any) {
      return {
        healthy: false,
        latencyMs: Date.now() - start,
        availableBytes: 0,
        totalBytes: 0,
        mode: this.mode,
        provider: this.providerName,
        lastChecked: new Date(),
      };
    }
  }

  /** Get provider statistics */
  async getStats(): Promise<StorageStats> {
    try {
      const files = await this.list('/');
      let totalBytes = 0;
      for (const file of files) {
        try {
          const resolved = this.resolve(file);
          const stat = await fs.stat(resolved);
          totalBytes += stat.size;
        } catch {
          // Skip files that may have been deleted between list and stat
        }
      }
      return {
        totalFiles: files.length,
        totalBytes,
        availableBytes: 0, // Requires system-level query
        operationsCount: this._operationsCount,
        errorCount: this._errorCount,
        uptimeSeconds: (Date.now() - this._startTime.getTime()) / 1000,
      };
    } catch (err: any) {
      logger.error('Stats error', { error: err.message });
      return {
        totalFiles: 0,
        totalBytes: 0,
        availableBytes: 0,
        operationsCount: this._operationsCount,
        errorCount: this._errorCount,
        uptimeSeconds: (Date.now() - this._startTime.getTime()) / 1000,
      };
    }
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
      jpeg: 'image/jpeg',
      gif: 'image/gif',
      svg: 'image/svg+xml',
      pdf: 'application/pdf',
      zip: 'application/zip',
      gz: 'application/gzip',
      mp3: 'audio/mpeg',
      mp4: 'video/mp4',
      wav: 'audio/wav',
    };
    return mimeMap[ext] || 'application/octet-stream';
  }
}
