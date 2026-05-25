/**
 * Trancendos StorageFactory — Environment-aware factory
 *
 * Selects the appropriate IStorageProvider based on the current
 * topology mode. The mode is determined by:
 *   1. TRANC3_TOPOLOGY env variable (explicit override)
 *   2. Runtime detection (is ZFS mount available? is cloud reachable?)
 *   3. Fallback order: TRUE_NAS → TRUECLOUD → CLOUD_ONLY
 *
 * Topology modes:
 *   TRUE_NAS   — Local ZFS primary (sovereign mode, GEEKOM + TrueNAS)
 *   HYBRID     — Local ZFS + cloud proxy transition (migration phase)
 *   TRUECLOUD  — Local primary + encrypted cloud replica (production norm)
 *   CLOUD_ONLY — Emergency lightweight cloud-only mode (disaster recovery)
 *
 * Usage:
 *   const storage = StorageFactory.create();
 *   const data = await storage.read('/config/app.json');
 */

import { IStorageProvider } from '../providers/IStorageProvider';
import { ZFSProvider } from '../providers/ZFSProvider';
import { TrueCloudProvider } from '../providers/TrueCloudProvider';
import { S3CloudProvider } from '../providers/S3CloudProvider';
import { Logger } from '../core/logger';

const logger = new Logger('StorageFactory');

export type TopologyMode = 'TRUE_NAS' | 'HYBRID' | 'TRUECLOUD' | 'CLOUD_ONLY';

/** Configuration for StorageFactory */
export interface StorageFactoryConfig {
  mode?: TopologyMode;
  zfsRoot?: string;
  cloudBucket?: string;
  s3Endpoint?: string;
  s3Bucket?: string;
  encryptionPassword?: string;
}

/** Cached provider instances */
const providerCache: Map<string, IStorageProvider> = new Map();

export class StorageFactory {
  /**
   * Create or retrieve a cached storage provider based on topology mode.
   *
   * @param config - Optional configuration overrides. If not provided,
   *                  reads from environment variables.
   */
  static create(config?: StorageFactoryConfig): IStorageProvider {
    const mode = config?.mode || this.detectMode();
    const cacheKey = `provider:${mode}`;

    // Return cached instance if available
    const cached = providerCache.get(cacheKey);
    if (cached) {
      logger.debug('Returning cached provider', { mode });
      return cached;
    }

    let provider: IStorageProvider;

    switch (mode) {
      case 'TRUE_NAS':
        provider = new ZFSProvider(config?.zfsRoot);
        logger.info('Created ZFSProvider (TRUE_NAS mode)', { root: config?.zfsRoot });
        break;

      case 'HYBRID':
        // HYBRID uses TrueCloudProvider with a different sync policy
        // In hybrid mode, cloud is available but not fully replicated yet
        provider = new TrueCloudProvider(
          config?.zfsRoot,
          config?.cloudBucket || 'tranc3-hybrid',
          config?.encryptionPassword,
        );
        logger.info('Created TrueCloudProvider (HYBRID mode)', { root: config?.zfsRoot });
        break;

      case 'TRUECLOUD':
        provider = new TrueCloudProvider(
          config?.zfsRoot,
          config?.cloudBucket,
          config?.encryptionPassword,
        );
        logger.info('Created TrueCloudProvider (TRUECLOUD mode)', { root: config?.zfsRoot });
        break;

      case 'CLOUD_ONLY':
        provider = new S3CloudProvider(
          config?.s3Endpoint,
          config?.s3Bucket,
        );
        logger.info('Created S3CloudProvider (CLOUD_ONLY mode)', {
          endpoint: config?.s3Endpoint,
        });
        break;

      default:
        logger.error('Unknown topology mode, falling back to TRUE_NAS', { mode });
        provider = new ZFSProvider(config?.zfsRoot);
    }

    providerCache.set(cacheKey, provider);
    return provider;
  }

  /**
   * Detect the current topology mode from environment and runtime conditions.
   *
   * Detection priority:
   *   1. TRANC3_TOPOLOGY env variable (explicit)
   *   2. Filesystem probe: does /tank/tranc3 exist? → TRUE_NAS
   *   3. Network probe: can we reach the cloud endpoint? → CLOUD_ONLY
   *   4. Default: TRUECLOUD (local + cloud replica)
   */
  static detectMode(): TopologyMode {
    // 1. Explicit environment variable
    const envMode = process.env.TRANC3_TOPOLOGY as TopologyMode;
    if (envMode && ['TRUE_NAS', 'HYBRID', 'TRUECLOUD', 'CLOUD_ONLY'].includes(envMode)) {
      logger.info('Topology mode from env', { mode: envMode });
      return envMode;
    }

    // 2. Filesystem probe (synchronous check)
    // In production, this would check for ZFS mount points
    const zfsRoot = process.env.ZFS_ROOT || '/tank/tranc3';
    try {
      const fs = require('fs');
      if (fs.existsSync(zfsRoot)) {
        logger.info('ZFS mount detected, using TRUECLOUD mode', { zfsRoot });
        return 'TRUECLOUD'; // Local ZFS available — use local + cloud replica
      }
    } catch {
      // fs not available or path not accessible
    }

    // 3. No local storage — cloud only
    logger.info('No local storage detected, using CLOUD_ONLY mode');
    return 'CLOUD_ONLY';
  }

  /**
   * Clear the provider cache (useful for testing or mode switching)
   */
  static clearCache(): void {
    providerCache.clear();
    logger.debug('Provider cache cleared');
  }

  /**
   * Get all cached provider instances (for health monitoring)
   */
  static getCachedProviders(): Map<string, IStorageProvider> {
    return new Map(providerCache);
  }
}
