/**
 * The Miner — The Basement Tier 4 Agent (SID-BASEMENT-MINER)
 *
 * Locates and validates archived data for retrieval.
 * Verifies integrity, checks access tier latency expectations,
 * and confirms the archive is ready for extraction.
 */

import { Agent, Logger, AuditLedger } from '../../core/definitions';

export interface MinerInput {
  archiveId: string;
  coldPath: string;
  archiveChecksum: string;
}

export interface MinerResult {
  found: boolean;
  coldPath: string;
  integrityOk: boolean;
  accessTier: string;
  estimatedRetrieveMs: number;
}

const TIER_LATENCY: Record<string, number> = {
  'cold': 5_000,          // ~5 seconds
  'glacier': 60_000,      // ~1 minute
  'deep-freeze': 300_000, // ~5 minutes
};

export class MinerAgent extends Agent {
  public readonly id = 'SID-BASEMENT-MINER';
  public readonly name = 'The Miner';

  constructor(
    private readonly audit: AuditLedger,
    private readonly logger: Logger,
  ) {
    super();
  }

  async perceive(input: MinerInput): Promise<MinerInput> {
    return input;
  }

  async decide(input: MinerInput): Promise<MinerResult> {
    return this.act(input);
  }

  async act(input: MinerInput): Promise<MinerResult> {
    // In production: check IStorageProvider.exists(coldPath),
    // read metadata, verify checksum against stored archive.
    // For now, simulate based on path convention.
    const found = input.coldPath.startsWith('/cold/');
    const accessTier = this.inferTierFromPath(input.coldPath);
    const integrityOk = found; // stub: would compare actual checksum

    if (!found) {
      this.logger.warn(`Miner: archive not found`, { archiveId: input.archiveId, coldPath: input.coldPath });
      await this.audit.append({
        actor: this.id,
        action: 'miner.miss',
        entity: input.archiveId,
        meta: { coldPath: input.coldPath },
      });
      return { found: false, coldPath: input.coldPath, integrityOk: false, accessTier, estimatedRetrieveMs: 0 };
    }

    const estimatedRetrieveMs = TIER_LATENCY[accessTier] ?? 30_000;

    await this.audit.append({
      actor: this.id,
      action: 'miner.locate',
      entity: input.archiveId,
      meta: { coldPath: input.coldPath, accessTier, integrityOk, estimatedRetrieveMs },
    });

    return {
      found: true,
      coldPath: input.coldPath,
      integrityOk,
      accessTier,
      estimatedRetrieveMs,
    };
  }

  private inferTierFromPath(coldPath: string): string {
    if (coldPath.includes('deep-freeze')) return 'deep-freeze';
    if (coldPath.includes('glacier')) return 'glacier';
    return 'cold';
  }
}
