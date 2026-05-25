/**
 * DocUtari — Document Management Hub
 * Pillar: Knowledge
 * Lead AI: Fiddius (AID-DOCUTARI-FIDDIUS)
 * Prime: Norman Hawkins
 *
 * Power-Ups:
 *   • Intelligent Auto-Tagging  — categorises uploaded documents
 *   • Structured Foldering       — organises files dynamically
 *
 * Online:  live document uploading / tagging; real-time storage management
 * Offline: local document viewing; offline tagging syncs later
 */

import { AI, Agent, Bot, Logger, AuditLedger } from '../../core/definitions';

/* ───────── data models ───────── */

export interface DocumentMeta {
  docId: string;
  title: string;
  mimeType: string;
  sizeBytes: number;
  checksumSha256: string;
  tags: string[];
  folderPath: string;
  uploadedBy: string;
  createdAt: Date;
  updatedAt: Date;
  version: number;
  isArchived: boolean;
}

export interface TagSuggestion {
  tag: string;
  confidence: number;          // 0-1
  source: 'keyword' | 'ml' | 'rule' | 'user';
}

export interface FolderRule {
  ruleId: string;
  pattern: string;             // glob or regex
  targetFolder: string;
  priority: number;
  enabled: boolean;
}

export interface UploadRequest {
  fileName: string;
  contentBase64: string;
  mimeType: string;
  suggestedTags?: string[];
  overrideFolder?: string;
}

export interface UploadResult {
  docId: string;
  tags: string[];
  folderPath: string;
  checksumSha256: string;
}

/* ───────── Fiddius AI ───────── */

export class DocUtariAI extends AI {
  public readonly id = 'AID-DOCUTARI-FIDDIUS';
  public readonly name = 'Fiddius';
  public readonly hub = 'DocUtari';
  public readonly pillar = 'Knowledge';

  private documents: Map<string, DocumentMeta> = new Map();
  private folderRules: Map<string, FolderRule> = new Map();
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
    this.logger.info(`Fiddius: registered agent ${agent.id}`);
  }

  registerBot(bot: Bot): void {
    this.bots.set(bot.name, bot);
    this.logger.info(`Fiddius: registered bot ${bot.name}`);
  }

  /* ── core orchestration ── */

  async ingestDocument(req: UploadRequest, userId: string): Promise<UploadResult> {
    await this.audit.append({
      actor: this.id,
      action: 'ingest.start',
      entity: req.fileName,
      meta: { userId, sizeBytes: req.contentBase64.length },
    });

    // 1. Scan content (ScannerBot)
    const scanner = this.bots.get('Scanner');
    const scanResult: { checksumSha256: string; sizeBytes: number; extractedText: string } =
      scanner ? await scanner.execute(req.contentBase64, req.mimeType) : {
        checksumSha256: 'placeholder-sha256',
        sizeBytes: Buffer.byteLength(req.contentBase64, 'base64'),
        extractedText: '',
      };

    // 2. Auto-tag (TaggerAgent)
    const tagger = this.agents.get('SID-DOCUTARI-TAGGER');
    const suggestions: TagSuggestion[] = tagger
      ? await tagger.decide({ extractedText: scanResult.extractedText, fileName: req.fileName, mimeType: req.mimeType })
      : [];

    const mergedTags = this.mergeTags(suggestions, req.suggestedTags ?? []);

    // 3. Folder assignment (FilerAgent)
    const filer = this.agents.get('SID-DOCUTARI-FILER');
    const folderPath: string = filer
      ? await filer.decide({ tags: mergedTags, overrideFolder: req.overrideFolder, rules: Array.from(this.folderRules.values()) })
      : req.overrideFolder ?? '/unsorted';

    // 4. Staple meta record (StaplerBot)
    const stapler = this.bots.get('Stapler');
    const docId = stapler
      ? await stapler.execute({ title: req.fileName, tags: mergedTags, folderPath })
      : `doc-${Date.now()}`;

    // 5. Persist document meta
    const doc: DocumentMeta = {
      docId,
      title: req.fileName,
      mimeType: req.mimeType,
      sizeBytes: scanResult.sizeBytes,
      checksumSha256: scanResult.checksumSha256,
      tags: mergedTags,
      folderPath,
      uploadedBy: userId,
      createdAt: new Date(),
      updatedAt: new Date(),
      version: 1,
      isArchived: false,
    };
    this.documents.set(docId, doc);

    // 6. File to storage (FolderBot)
    const folder = this.bots.get('Folder');
    if (folder) {
      await folder.execute(doc);
    }

    await this.audit.append({
      actor: this.id,
      action: 'ingest.complete',
      entity: docId,
      meta: { tags: mergedTags, folderPath },
    });

    return { docId, tags: mergedTags, folderPath, checksumSha256: scanResult.checksumSha256 };
  }

  async deleteDocument(docId: string, userId: string): Promise<boolean> {
    const doc = this.documents.get(docId);
    if (!doc) return false;

    // 1. Shred (ShredderBot)
    const shredder = this.bots.get('Shredder');
    if (shredder) {
      await shredder.execute(docId, doc.folderPath);
    }

    doc.isArchived = true;
    this.documents.delete(docId);

    await this.audit.append({
      actor: this.id,
      action: 'document.delete',
      entity: docId,
      meta: { userId, title: doc.title },
    });

    return true;
  }

  async searchDocuments(query: { tags?: string[]; folderPath?: string; text?: string }): Promise<DocumentMeta[]> {
    const results: DocumentMeta[] = [];
    for (const doc of this.documents.values()) {
      if (doc.isArchived) continue;
      if (query.tags?.length && !query.tags.some(t => doc.tags.includes(t))) continue;
      if (query.folderPath && !doc.folderPath.startsWith(query.folderPath)) continue;
      if (query.text && !doc.title.toLowerCase().includes(query.text.toLowerCase())) continue;
      results.push(doc);
    }
    return results;
  }

  /* ── folder rule management ── */

  addFolderRule(rule: FolderRule): void {
    this.folderRules.set(rule.ruleId, rule);
  }

  removeFolderRule(ruleId: string): boolean {
    return this.folderRules.delete(ruleId);
  }

  /* ── helpers ── */

  private mergeTags(suggestions: TagSuggestion[], userTags: string[]): string[] {
    const highConfidence = suggestions
      .filter(s => s.confidence >= 0.7)
      .map(s => s.tag);
    const combined = new Set([...highConfidence, ...userTags]);
    return Array.from(combined);
  }

  getDocument(docId: string): DocumentMeta | undefined {
    return this.documents.get(docId);
  }

  listDocuments(): DocumentMeta[] {
    return Array.from(this.documents.values()).filter(d => !d.isArchived);
  }
}
