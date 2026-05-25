/**
 * The Undertaker — The Basement Tier 4 Agent (SID-BASEMENT-UNDERTAKER)
 *
 * Decides where archived data is laid to rest: the cold storage
 * path, retention policy, and any access tier classification.
 */

import { Agent, Logger, AuditLedger } from '../../core/definitions';

export interface UndertakerInput {
  tags: string[];
  mimeType: string;
  originalSizeBytes: number;
  compressedSizeBytes: number;
}

export interface UndertakerDecision {
  coldPath: string;
  retentionDays: number | null;   // null = indefinite
  accessTier: 'glacier' | 'deep-freeze' | 'cold';
  reason: string;
}

const TAG_TIER_MAP: Record<string, { path: string; tier: UndertakerDecision['accessTier']; retention: number | null }> = {
  'legal':    { path: '/cold/legal',       tier: 'deep-freeze', retention: 2555 },   // 7 years
  'finance':  { path: '/cold/finance',     tier: 'deep-freeze', retention: 2555 },
  'contract': { path: '/cold/contracts',   tier: 'deep-freeze', retention: 3650 },   // 10 years
  'policy':   { path: '/cold/policy',      tier: 'glacier',     retention: 1825 },   // 5 years
  'report':   { path: '/cold/reports',     tier: 'cold',        retention: 1095 },   // 3 years
  'media':    { path: '/cold/media',       tier: 'cold',        retention: null },
  'image':    { path: '/cold/media/images', tier: 'cold',       retention: null },
  'invoice':  { path: '/cold/finance/invoices', tier: 'deep-freeze', retention: 2555 },
};

export class UndertakerAgent extends Agent {
  public readonly id = 'SID-BASEMENT-UNDERTAKER';
  public readonly name = 'The Undertaker';

  constructor(
    private readonly audit: AuditLedger,
    private readonly logger: Logger,
  ) {
    super();
  }

  async perceive(input: UndertakerInput): Promise<UndertakerInput> {
    return input;
  }

  async decide(input: UndertakerInput): Promise<string> {
    const perceived = await this.perceive(input);
    const result = await this.act(perceived);
    return result.coldPath;
  }

  async act(input: UndertakerInput): Promise<UndertakerDecision> {
    // Check tags against known tier map
    const tagLower = input.tags.map(t => t.toLowerCase());

    for (const tag of tagLower) {
      const mapping = TAG_TIER_MAP[tag];
      if (mapping) {
        await this.audit.append({
          actor: this.id,
          action: 'undertaker.classify',
          entity: mapping.path,
          meta: { tag, tier: mapping.tier, retention: mapping.retention },
        });
        return {
          coldPath: mapping.path,
          retentionDays: mapping.retention,
          accessTier: mapping.tier,
          reason: `Tag "${tag}" mapped to ${mapping.tier} storage with ${mapping.retention ?? 'indefinite'} day retention`,
        };
      }
    }

    // Large files default to deep-freeze
    if (input.originalSizeBytes > 100 * 1024 * 1024) {
      return {
        coldPath: '/cold/large-files',
        retentionDays: null,
        accessTier: 'deep-freeze',
        reason: 'File exceeds 100 MB; defaulting to deep-freeze tier',
      };
    }

    // Default: cold tier with indefinite retention
    return {
      coldPath: '/cold/unsorted',
      retentionDays: null,
      accessTier: 'cold',
      reason: 'No tag match; defaulting to cold tier with indefinite retention',
    };
  }
}
