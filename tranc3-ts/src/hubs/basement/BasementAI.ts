/**
 * The Basement — Archived Information Store
 * Pillar: Knowledge
 * Lead AI: Gary Glowman / Glow-Worm (AID-BASEMENT-GLOWWORM)
 * Prime: Norman Hawkins
 *
 * Power-Ups:
 *   • Deep Cold Storage   — long-term archival with compression
 *   • Data Retrieval       — on-demand restore from cold archive
 *
 * Online:  access to archived indexes; requesting data retrieval
 * Offline: read-only index access; review of restored data
 */

import { AI, Agent, Bot, Logger, AuditLedger } from '../../core/definitions';

/* ───────── data models ───────── */

export interface ArchiveEntry {
  archiveId: string;
  originalDocId: string;
  title: string;
  mimeType: string;
  originalSizeBytes: number;
  compressedSizeBytes: number;
  checksumSha256: string;
  archiveChecksumSha256: string;
  tags: string[];
  coldPath: string;             // storage path in cold archive
  archivedAt: Date;
  expiresAt: Date | null;       // null = indefinite retention
  retrievalStatus: 'stored' | 'retrieving' | 'restored';
  retrievalRequestedAt: Date | null;
  restoredAt: Date | null;
}

export interface RetrievalRequest {
  archiveId: string;
  requestedBy: string;
  priority: 'low' | 'normal' | 'high';
  reason?: string;
}

export interface RetrievalStatus {
  archiveId: string;
  status: ArchiveEntry['retrievalStatus'];
  estimatedTimeMs: number | null;
  restoredPath: string | null;
}

export interface ColdStats {
  totalArchived: number;
  totalOriginalBytes: number;
  totalCompressedBytes: number;
  compressionRatio: number;
  pendingRetrievals: number;
}

/* ───────── Gary Glowman AI ───────── */

export class BasementAI extends AI {
  public readonly id = 'AID-BASEMENT-GLOWWORM';
  public readonly name = 'Gary Glowman';
  public readonly alias = 'Glow-Worm';
  public readonly hub = 'The Basement';
  public readonly pillar = 'Knowledge';

  private archive: Map<string, ArchiveEntry> = new Map();
  private readonly agents: Map<string, Agent> = new Map();
  private readonly bots: Map<string, Bot> = new Map();

  constructor(
    private readonly audit: AuditLedger,
    private readonly logger: Logger,
  ) {
    super();
  }

  /* ── agent / bot registration ── */

  registerAgent(agent: Agent): void {
    this.agents.set(agent.id, agent);
    this.logger.info(`Glow-Worm: registered agent ${agent.id}`);
  }

  registerBot(bot: Bot): void {
    this.bots.set(bot.name, bot);
    this.logger.info(`Glow-Worm: registered bot ${bot.name}`);
  }

  /* ── archive flow ── */

  async archiveDocument(
    docId: string,
    title: string,
    mimeType: string,
    contentBase64: string,
    tags: string[],
    userId: string,
  ): Promise<ArchiveEntry> {
    await this.audit.append({
      actor: this.id,
      action: 'archive.start',
      entity: docId,
      meta: { title, mimeType, userId },
    });

    const originalSizeBytes = Buffer.byteLength(contentBase64, 'base64');

    // 1. Compress (CompressorBot)
    const compressor = this.bots.get('Compressor');
    const compressed: { dataBase64: string; compressedSizeBytes: number; archiveChecksum: string } =
      compressor
        ? await compressor.execute(contentBase64, mimeType)
        : { dataBase64: contentBase64, compressedSizeBytes: originalSizeBytes, archiveChecksum: `sha256-arch-${Date.now()}` };

    // 2. Undertaker decides cold path and retention
    const undertaker = this.agents.get('SID-BASEMENT-UNDERTAKER');
    const coldPath: string = undertaker
      ? await undertaker.decide({ tags, mimeType, originalSizeBytes, compressedSizeBytes: compressed.compressedSizeBytes })
      : `/cold/unsorted/${docId}`;

    // 3. Write to cold storage (ExtractorBot in "store" mode)
    // Storage provider write happens here in production

    // 4. Build archive entry
    const archiveId = `ARC-${Date.now().toString(36)}-${Math.random().toString(36).substring(2, 6)}`;
    const entry: ArchiveEntry = {
      archiveId,
      originalDocId: docId,
      title,
      mimeType,
      originalSizeBytes,
      compressedSizeBytes: compressed.compressedSizeBytes,
      checksumSha256: `sha256-${originalSizeBytes}`,
      archiveChecksumSha256: compressed.archiveChecksum,
      tags,
      coldPath,
      archivedAt: new Date(),
      expiresAt: null,
      retrievalStatus: 'stored',
      retrievalRequestedAt: null,
      restoredAt: null,
    };
    this.archive.set(archiveId, entry);

    // 5. Dust-Bunny sweeps any temp files
    const dustBunny = this.bots.get('Dust-Bunny');
    if (dustBunny) {
      await dustBunny.execute(`/tmp/archive-${docId}`);
    }

    await this.audit.append({
      actor: this.id,
      action: 'archive.complete',
      entity: archiveId,
      meta: { coldPath, compressionRatio: (compressed.compressedSizeBytes / originalSizeBytes).toFixed(2) },
    });

    return entry;
  }

  async requestRetrieval(req: RetrievalRequest): Promise<RetrievalStatus> {
    const entry = this.archive.get(req.archiveId);
    if (!entry) {
      throw new Error(`Archive entry not found: ${req.archiveId}`);
    }

    await this.audit.append({
      actor: this.id,
      action: 'retrieval.request',
      entity: req.archiveId,
      meta: { requestedBy: req.requestedBy, priority: req.priority },
    });

    entry.retrievalStatus = 'retrieving';
    entry.retrievalRequestedAt = new Date();

    // 1. Miner agent finds and validates the archive
    const miner = this.agents.get('SID-BASEMENT-MINER');
    const minerResult: { found: boolean; coldPath: string; integrityOk: boolean } = miner
      ? await miner.decide({ archiveId: req.archiveId, coldPath: entry.coldPath, archiveChecksum: entry.archiveChecksumSha256 })
      : { found: true, coldPath: entry.coldPath, integrityOk: true };

    if (!minerResult.found || !minerResult.integrityOk) {
      entry.retrievalStatus = 'stored';
      await this.audit.append({
        actor: this.id,
        action: 'retrieval.failed',
        entity: req.archiveId,
        meta: { found: minerResult.found, integrityOk: minerResult.integrityOk },
      });
      throw new Error(`Retrieval failed: found=${minerResult.found}, integrity=${minerResult.integrityOk}`);
    }

    // 2. Extract (decompress) the archive
    const extractor = this.bots.get('Extractor');
    if (extractor) {
      await extractor.execute(entry.coldPath, entry.mimeType);
    }

    // 3. Mothball does final restore cleanup
    const mothball = this.bots.get('Mothball');
    if (mothball) {
      await mothball.execute(req.archiveId, entry.coldPath);
    }

    entry.retrievalStatus = 'restored';
    entry.restoredAt = new Date();

    await this.audit.append({
      actor: this.id,
      action: 'retrieval.complete',
      entity: req.archiveId,
      meta: { restoredAt: entry.restoredAt.toISOString() },
    });

    return {
      archiveId: req.archiveId,
      status: entry.retrievalStatus,
      estimatedTimeMs: null,
      restoredPath: entry.coldPath.replace('/cold/', '/restored/'),
    };
  }

  /* ── queries ── */

  getArchiveEntry(archiveId: string): ArchiveEntry | undefined {
    return this.archive.get(archiveId);
  }

  searchArchive(query: { tags?: string[]; titleContains?: string }): ArchiveEntry[] {
    const results: ArchiveEntry[] = [];
    for (const entry of this.archive.values()) {
      if (query.tags?.length && !query.tags.some(t => entry.tags.includes(t))) continue;
      if (query.titleContains && !entry.title.toLowerCase().includes(query.titleContains.toLowerCase())) continue;
      results.push(entry);
    }
    return results;
  }

  getStats(): ColdStats {
    let totalOriginal = 0;
    let totalCompressed = 0;
    let pending = 0;
    for (const entry of this.archive.values()) {
      totalOriginal += entry.originalSizeBytes;
      totalCompressed += entry.compressedSizeBytes;
      if (entry.retrievalStatus === 'retrieving') pending++;
    }
    return {
      totalArchived: this.archive.size,
      totalOriginalBytes: totalOriginal,
      totalCompressedBytes: totalCompressed,
      compressionRatio: totalOriginal > 0 ? totalCompressed / totalOriginal : 0,
      pendingRetrievals: pending,
    };
  }
}
