/**
 * DustJacketBot — Volume Wrapping & Metadata Bot for The Library
 *
 * Identity:  NID-LIBRARY-DUSTJACKET
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TheLibraryAI (AID-LIBRARY)
 *
 * Responsibilities:
 *   - WRAP: Apply metadata, protective covers, seals, or restoration
 *           treatments to volumes
 *   - Manage wrap lifecycle (applied → maintained → expired → removed)
 *   - Track wrap history and integrity checks
 *   - Support metadata enrichment, protective layering, archival sealing,
 *     and restoration of damaged wraps
 */

import { Bot, Logger, AuditLedger } from '../../../core/definitions';

// ─────────────────────────────────────────────────────────────────────
// Input / Output Types
// ─────────────────────────────────────────────────────────────────────

export interface DustJacketInput {
  operation: 'WRAP';
  volumeId: string;
  wrapType: 'metadata' | 'protective' | 'seal' | 'restore';
  options?: Record<string, unknown>;
}

export interface WrapRecord {
  id: string;
  volumeId: string;
  wrapType: DustJacketInput['wrapType'];
  status: 'applied' | 'maintained' | 'compromised' | 'expired' | 'removed';
  appliedAt: number;
  lastCheckedAt: number;
  expiresAt?: number;
  integrity: number; // 0.0 - 1.0
  metadata?: Record<string, unknown>;
  appliedBy: string;
}

export interface WrapResult {
  success: boolean;
  volumeId: string;
  wrapType: DustJacketInput['wrapType'];
  wrapId?: string;
  status: WrapRecord['status'];
  integrity?: number;
  message: string;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────
// Wrap Type Configurations
// ─────────────────────────────────────────────────────────────────────

const WRAP_CONFIG: Record<DustJacketInput['wrapType'], {
  defaultIntegrity: number;
  defaultTTL: number; // milliseconds
  description: string;
}> = {
  metadata: {
    defaultIntegrity: 1.0,
    defaultTTL: 0, // never expires
    description: 'Enrichment metadata layer applied to volume',
  },
  protective: {
    defaultIntegrity: 0.98,
    defaultTTL: 365 * 24 * 60 * 60 * 1000, // 1 year
    description: 'Protective dust jacket applied to volume',
  },
  seal: {
    defaultIntegrity: 1.0,
    defaultTTL: 0, // never expires (archival)
    description: 'Archival seal applied — volume is now preserved',
  },
  restore: {
    defaultIntegrity: 0.85,
    defaultTTL: 0,
    description: 'Restoration treatment applied to volume',
  },
};

// ─────────────────────────────────────────────────────────────────────
// DustJacketBot Implementation
// ─────────────────────────────────────────────────────────────────────

export class DustJacketBot extends Bot {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private wraps: Map<string, WrapRecord>;
  private wrapCounter: number;

  constructor() {
    super(
      'NID-LIBRARY-DUSTJACKET',
      'DustJacket',
      async (input: DustJacketInput) => this.handleWrap(input),
      'Applies metadata, protective covers, archival seals, and restoration to volumes'
    );

    this.log = new Logger('DustJacketBot');
    this.audit = AuditLedger.getInstance();
    this.wraps = new Map();
    this.wrapCounter = 0;
  }

  // ───────────────────────────────────────────────────────────────
  // Main Handler
  // ───────────────────────────────────────────────────────────────

  private async handleWrap(input: DustJacketInput): Promise<WrapResult> {
    if (input.operation !== 'WRAP') {
      return {
        success: false,
        volumeId: input.volumeId,
        wrapType: input.wrapType,
        status: 'removed',
        message: `Invalid operation: ${input.operation}. Expected WRAP.`,
        timestamp: Date.now(),
      };
    }

    switch (input.wrapType) {
      case 'metadata':
        return this.applyMetadata(input.volumeId, input.options);
      case 'protective':
        return this.applyProtective(input.volumeId, input.options);
      case 'seal':
        return this.applySeal(input.volumeId, input.options);
      case 'restore':
        return this.applyRestore(input.volumeId, input.options);
      default:
        return {
          success: false,
          volumeId: input.volumeId,
          wrapType: input.wrapType,
          status: 'removed',
          message: `Unknown wrap type: ${input.wrapType}`,
          timestamp: Date.now(),
        };
    }
  }

  // ───────────────────────────────────────────────────────────────
  // Metadata Wrap — Enrich a volume with metadata
  // ───────────────────────────────────────────────────────────────

  private applyMetadata(volumeId: string, options?: Record<string, unknown>): WrapResult {
    this.wrapCounter++;
    const now = Date.now();
    const config = WRAP_CONFIG.metadata;

    // Check for existing metadata wrap
    const existingWrap = this.findActiveWrap(volumeId, 'metadata');
    if (existingWrap) {
      // Update existing metadata
      existingWrap.metadata = {
        ...existingWrap.metadata,
        ...options,
        updated: true,
        updatedAt: now,
      };
      existingWrap.lastCheckedAt = now;

      this.log.info('Metadata wrap updated', { volumeId, wrapId: existingWrap.id });

      return {
        success: true,
        volumeId,
        wrapType: 'metadata',
        wrapId: existingWrap.id,
        status: 'maintained',
        integrity: existingWrap.integrity,
        message: `Metadata wrap updated for volume ${volumeId}`,
        timestamp: now,
      };
    }

    // Apply new metadata wrap
    const wrapRecord: WrapRecord = {
      id: `WRP-${this.wrapCounter.toString().padStart(6, '0')}`,
      volumeId,
      wrapType: 'metadata',
      status: 'applied',
      appliedAt: now,
      lastCheckedAt: now,
      integrity: config.defaultIntegrity,
      metadata: {
        enrichedFields: Object.keys(options ?? {}),
        source: options?.source ?? 'auto',
        confidence: options?.confidence ?? 0.85,
        ...options,
      },
      appliedBy: 'DustJacketBot',
    };

    this.wraps.set(wrapRecord.id, wrapRecord);

    this.audit.append({
      actor: 'DustJacketBot',
      action: 'WRAP_METADATA',
      entity: volumeId,
      status: 'SUCCESS',
      meta: { wrapId: wrapRecord.id },
    });

    this.log.info('Metadata wrap applied', { volumeId, wrapId: wrapRecord.id });

    return {
      success: true,
      volumeId,
      wrapType: 'metadata',
      wrapId: wrapRecord.id,
      status: 'applied',
      integrity: wrapRecord.integrity,
      message: `Metadata wrap applied to volume ${volumeId}`,
      timestamp: now,
    };
  }

  // ───────────────────────────────────────────────────────────────
  // Protective Wrap — Apply a protective dust jacket
  // ───────────────────────────────────────────────────────────────

  private applyProtective(volumeId: string, options?: Record<string, unknown>): WrapResult {
    this.wrapCounter++;
    const now = Date.now();
    const config = WRAP_CONFIG.protective;

    // Check for existing protective wrap
    const existingWrap = this.findActiveWrap(volumeId, 'protective');
    if (existingWrap) {
      // Check integrity — if compromised, replace
      if (existingWrap.integrity < 0.7) {
        existingWrap.status = 'removed';
        this.log.warn('Compromised protective wrap removed', {
          volumeId,
          wrapId: existingWrap.id,
          integrity: existingWrap.integrity,
        });
      } else {
        // Reinforce existing wrap
        existingWrap.integrity = Math.min(1.0, existingWrap.integrity + 0.05);
        existingWrap.lastCheckedAt = now;

        return {
          success: true,
          volumeId,
          wrapType: 'protective',
          wrapId: existingWrap.id,
          status: 'maintained',
          integrity: existingWrap.integrity,
          message: `Protective wrap reinforced for volume ${volumeId}`,
          timestamp: now,
        };
      }
    }

    // Apply new protective wrap
    const layerCount = (options?.layers as number) ?? 1;
    const wrapRecord: WrapRecord = {
      id: `WRP-${this.wrapCounter.toString().padStart(6, '0')}`,
      volumeId,
      wrapType: 'protective',
      status: 'applied',
      appliedAt: now,
      lastCheckedAt: now,
      expiresAt: now + config.defaultTTL,
      integrity: config.defaultIntegrity - (0.02 * (layerCount - 1)), // slightly lower for multi-layer
      metadata: {
        layers: layerCount,
        material: options?.material ?? 'standard-acid-free',
        uvProtection: options?.uvProtection ?? true,
        humidityBarrier: options?.humidityBarrier ?? true,
      },
      appliedBy: 'DustJacketBot',
    };

    this.wraps.set(wrapRecord.id, wrapRecord);

    this.audit.append({
      actor: 'DustJacketBot',
      action: 'WRAP_PROTECTIVE',
      entity: volumeId,
      status: 'SUCCESS',
      meta: { wrapId: wrapRecord.id, layers: layerCount },
    });

    this.log.info('Protective wrap applied', { volumeId, wrapId: wrapRecord.id, layers: layerCount });

    return {
      success: true,
      volumeId,
      wrapType: 'protective',
      wrapId: wrapRecord.id,
      status: 'applied',
      integrity: wrapRecord.integrity,
      message: `Protective wrap applied to volume ${volumeId} (${layerCount} layer${layerCount > 1 ? 's' : ''})`,
      timestamp: now,
    };
  }

  // ───────────────────────────────────────────────────────────────
  // Seal Wrap — Apply an archival seal for long-term preservation
  // ───────────────────────────────────────────────────────────────

  private applySeal(volumeId: string, options?: Record<string, unknown>): WrapResult {
    this.wrapCounter++;
    const now = Date.now();
    const config = WRAP_CONFIG.seal;

    // Seals are permanent — check if already sealed
    const existingSeal = this.findActiveWrap(volumeId, 'seal');
    if (existingSeal) {
      return {
        success: false,
        volumeId,
        wrapType: 'seal',
        wrapId: existingSeal.id,
        status: 'applied',
        integrity: existingSeal.integrity,
        message: `Volume ${volumeId} is already sealed (${existingSeal.id}). Seals are permanent.`,
        timestamp: now,
      };
    }

    const sealLevel = (options?.level as string) ?? 'standard';
    const wrapRecord: WrapRecord = {
      id: `WRP-${this.wrapCounter.toString().padStart(6, '0')}`,
      volumeId,
      wrapType: 'seal',
      status: 'applied',
      appliedAt: now,
      lastCheckedAt: now,
      integrity: config.defaultIntegrity,
      metadata: {
        sealLevel,
        sealedBy: options?.sealedBy ?? 'DustJacketBot',
        reason: options?.reason ?? 'Archival preservation',
        accessRestriction: options?.accessRestriction ?? 'restricted',
        classification: options?.classification ?? 'standard',
      },
      appliedBy: 'DustJacketBot',
    };

    this.wraps.set(wrapRecord.id, wrapRecord);

    this.audit.append({
      actor: 'DustJacketBot',
      action: 'WRAP_SEAL',
      entity: volumeId,
      status: 'SUCCESS',
      meta: { wrapId: wrapRecord.id, sealLevel },
    });

    this.log.info('Archival seal applied', { volumeId, wrapId: wrapRecord.id, sealLevel });

    return {
      success: true,
      volumeId,
      wrapType: 'seal',
      wrapId: wrapRecord.id,
      status: 'applied',
      integrity: wrapRecord.integrity,
      message: `Archival seal applied to volume ${volumeId} (level: ${sealLevel}). This volume is now preserved.`,
      timestamp: now,
    };
  }

  // ───────────────────────────────────────────────────────────────
  // Restore Wrap — Restore a damaged or compromised wrap
  // ───────────────────────────────────────────────────────────────

  private applyRestore(volumeId: string, options?: Record<string, unknown>): WrapResult {
    this.wrapCounter++;
    const now = Date.now();

    // Find the most recent wrap that needs restoration
    const damagedWraps = Array.from(this.wraps.values())
      .filter(w => w.volumeId === volumeId && (w.status === 'compromised' || w.integrity < 0.7))
      .sort((a, b) => b.appliedAt - a.appliedAt);

    if (damagedWraps.length === 0) {
      // No damaged wraps found — apply a fresh protective wrap instead
      return this.applyProtective(volumeId, { ...options, reason: 'restoration — no prior damage found' });
    }

    const targetWrap = damagedWraps[0];
    const previousIntegrity = targetWrap.integrity;
    const restoreBoost = (options?.boost as number) ?? 0.3;

    targetWrap.integrity = Math.min(1.0, targetWrap.integrity + restoreBoost);
    targetWrap.status = 'maintained';
    targetWrap.lastCheckedAt = now;

    const wrapRecord: WrapRecord = {
      id: `WRP-${this.wrapCounter.toString().padStart(6, '0')}`,
      volumeId,
      wrapType: 'restore',
      status: 'applied',
      appliedAt: now,
      lastCheckedAt: now,
      integrity: targetWrap.integrity,
      metadata: {
        restoredWrapId: targetWrap.id,
        previousIntegrity,
        newIntegrity: targetWrap.integrity,
        restoreBoost,
        technique: options?.technique ?? 'standard-restoration',
      },
      appliedBy: 'DustJacketBot',
    };

    this.wraps.set(wrapRecord.id, wrapRecord);

    this.audit.append({
      actor: 'DustJacketBot',
      action: 'WRAP_RESTORE',
      entity: volumeId,
      status: 'SUCCESS',
      meta: {
        wrapId: wrapRecord.id,
        restoredWrapId: targetWrap.id,
        integrityChange: `${previousIntegrity.toFixed(2)} → ${targetWrap.integrity.toFixed(2)}`,
      },
    });

    this.log.info('Wrap restored', {
      volumeId,
      wrapId: wrapRecord.id,
      restoredWrap: targetWrap.id,
      integrity: `${previousIntegrity.toFixed(2)} → ${targetWrap.integrity.toFixed(2)}`,
    });

    return {
      success: true,
      volumeId,
      wrapType: 'restore',
      wrapId: wrapRecord.id,
      status: 'applied',
      integrity: targetWrap.integrity,
      message: `Restoration applied to volume ${volumeId}. Integrity: ${previousIntegrity.toFixed(2)} → ${targetWrap.integrity.toFixed(2)}`,
      timestamp: now,
    };
  }

  // ───────────────────────────────────────────────────────────────
  // Helper: Find active wrap for a volume
  // ───────────────────────────────────────────────────────────────

  private findActiveWrap(volumeId: string, wrapType?: DustJacketInput['wrapType']): WrapRecord | undefined {
    return Array.from(this.wraps.values())
      .filter(w =>
        w.volumeId === volumeId &&
        (w.status === 'applied' || w.status === 'maintained') &&
        (!wrapType || w.wrapType === wrapType)
      )
      .sort((a, b) => b.appliedAt - a.appliedAt)[0];
  }
}
