/**
 * TheLibraryAI — Lead AI for The Library Hub
 *
 * Identity:  AID-LIBRARY
 * Pillar:    Norman Hawkins
 * Tier:      3 (Lead AI / Domain Orchestrator)
 * Domain:    Knowledge management, information archival, cataloguing,
 *            scholarly research, cross-referencing, annotation,
 *            curated collections, wisdom preservation
 *
 * Philosophy: The Library holds all that Arcadia has ever known and all
 *             it has yet to learn. Norman Hawkins built these stacks
 *             so that no insight would ever be lost to time. Every volume
 *             is a voice; every index a promise that knowledge endures.
 *
 * Pipeline:  ShelfBot (stack) → CatalogAgent (index/search/retrieve/curate)
 *            → IndexBot (lookup) → ScholarAgent (research/crossref/summarize/annotate)
 *            → DustJacketBot (wrap)
 */

import { AI, Agent, Bot, Logger, AuditLedger } from '../../core/definitions';
import { CatalogAgent } from './agents/CatalogAgent';
import { ScholarAgent } from './agents/ScholarAgent';
import { ShelfBot } from './bots/ShelfBot';
import { IndexBot } from './bots/IndexBot';
import { DustJacketBot } from './bots/DustJacketBot';

// ─────────────────────────────────────────────────────────────────────
// Domain Interfaces
// ─────────────────────────────────────────────────────────────────────

export interface Volume {
  id: string;
  title: string;
  author: string;
  subject: string;
  dewey: string;
  tags: string[];
  status: 'available' | 'checked_out' | 'reserved' | 'restoring' | 'archived';
  location: string;
  acquiredAt: number;
  lastAccessedAt?: number;
  accessCount: number;
  metadata?: Record<string, unknown>;
}

export interface CatalogEntry {
  id: string;
  volumeId: string;
  subject: string;
  dewey: string;
  keywords: string[];
  abstract: string;
  crossReferences: string[];
  createdAt: number;
  updatedAt: number;
  curatedBy?: string;
}

export interface Annotation {
  id: string;
  volumeId: string;
  page?: number;
  section?: string;
  author: string;
  type: 'highlight' | 'footnote' | 'marginalia' | 'correction' | 'review';
  content: string;
  visibility: 'private' | 'shared' | 'public';
  createdAt: number;
  updatedAt: number;
}

export interface ResearchQuery {
  id: string;
  query: string;
  requester: string;
  scope: 'local' | 'regional' | 'global' | 'deep';
  subjects: string[];
  maxResults?: number;
  includeAnnotations?: boolean;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  results?: SearchResult[];
  submittedAt: number;
  completedAt?: number;
}

export interface SearchResult {
  volumeId: string;
  relevance: number;
  snippet: string;
  matchType: 'exact' | 'fuzzy' | 'semantic' | 'cross_reference';
  highlights: string[];
}

export interface CollectionFilter {
  subject?: string;
  deweyPrefix?: string;
  tags?: string[];
  status?: Volume['status'];
  author?: string;
  acquiredAfter?: number;
  acquiredBefore?: number;
  limit?: number;
}

// ─────────────────────────────────────────────────────────────────────
// TheLibraryAI Implementation
// ─────────────────────────────────────────────────────────────────────

export class TheLibraryAI extends AI {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private volumes: Map<string, Volume>;
  private catalog: Map<string, CatalogEntry>;
  private annotations: Map<string, Annotation>;
  private researchQueries: Map<string, ResearchQuery>;
  private volumeCounter: number;
  private catalogCounter: number;
  private annotationCounter: number;
  private queryCounter: number;

  constructor() {
    super(
      'AID-LIBRARY',
      'Library',
      'library',
      'Norman Hawkins',
      3
    );

    this.log = new Logger('TheLibraryAI');
    this.audit = AuditLedger.getInstance();
    this.volumes = new Map();
    this.catalog = new Map();
    this.annotations = new Map();
    this.researchQueries = new Map();
    this.volumeCounter = 0;
    this.catalogCounter = 0;
    this.annotationCounter = 0;
    this.queryCounter = 0;

    // Register Agents
    this.registerAgent(new CatalogAgent());
    this.registerAgent(new ScholarAgent());

    // Register Bots
    this.registerBot(new ShelfBot());
    this.registerBot(new IndexBot());
    this.registerBot(new DustJacketBot());

    this.log.info('TheLibraryAI initialised', {
      agents: this.listAgentIds(),
      bots: this.listBotNames(),
      message: 'The Library stands ready. Knowledge awaits. 📚',
    });
  }

  // ───────────────────────────────────────────────────────────────
  // Volume Management
  // ───────────────────────────────────────────────────────────────

  addVolume(vol: Omit<Volume, 'id' | 'acquiredAt' | 'accessCount'>): Volume {
    this.volumeCounter++;
    const volume: Volume = {
      ...vol,
      id: `VOL-${this.volumeCounter.toString().padStart(6, '0')}`,
      acquiredAt: Date.now(),
      accessCount: 0,
    };
    this.volumes.set(volume.id, volume);

    this.audit.append({
      actor: 'TheLibraryAI',
      action: 'ADD_VOLUME',
      entity: volume.id,
      status: 'SUCCESS',
      meta: { title: volume.title, author: volume.author, dewey: volume.dewey },
    });

    this.log.info('Volume catalogued', {
      id: volume.id,
      title: volume.title,
      dewey: volume.dewey,
    });

    return volume;
  }

  getVolume(id: string): Volume | undefined {
    return this.volumes.get(id);
  }

  queryVolumes(filter?: CollectionFilter): Volume[] {
    let results = Array.from(this.volumes.values());

    if (filter) {
      if (filter.subject) results = results.filter(v => v.subject === filter.subject);
      if (filter.deweyPrefix) results = results.filter(v => v.dewey.startsWith(filter.deweyPrefix!));
      if (filter.tags && filter.tags.length > 0) {
        results = results.filter(v => filter.tags!.some(t => v.tags.includes(t)));
      }
      if (filter.status) results = results.filter(v => v.status === filter.status);
      if (filter.author) results = results.filter(v => v.author.toLowerCase().includes(filter.author!.toLowerCase()));
      if (filter.acquiredAfter) results = results.filter(v => v.acquiredAt >= filter.acquiredAfter!);
      if (filter.acquiredBefore) results = results.filter(v => v.acquiredAt <= filter.acquiredBefore!);
      if (filter.limit) results = results.slice(0, filter.limit);
    }

    return results.sort((a, b) => a.title.localeCompare(b.title));
  }

  updateVolumeStatus(id: string, status: Volume['status']): boolean {
    const vol = this.volumes.get(id);
    if (!vol) return false;

    vol.status = status;
    vol.lastAccessedAt = Date.now();
    vol.accessCount++;

    this.log.info('Volume status updated', { id, status, accessCount: vol.accessCount });
    return true;
  }

  // ───────────────────────────────────────────────────────────────
  // Catalog Management
  // ───────────────────────────────────────────────────────────────

  addCatalogEntry(entry: Omit<CatalogEntry, 'id' | 'createdAt' | 'updatedAt'>): CatalogEntry {
    this.catalogCounter++;
    const catalogEntry: CatalogEntry = {
      ...entry,
      id: `CAT-${this.catalogCounter.toString().padStart(6, '0')}`,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
    this.catalog.set(catalogEntry.id, catalogEntry);

    this.log.info('Catalog entry created', {
      id: catalogEntry.id,
      volumeId: catalogEntry.volumeId,
      subject: catalogEntry.subject,
    });

    return catalogEntry;
  }

  getCatalogEntry(id: string): CatalogEntry | undefined {
    return this.catalog.get(id);
  }

  findCatalogByVolume(volumeId: string): CatalogEntry | undefined {
    return Array.from(this.catalog.values()).find(e => e.volumeId === volumeId);
  }

  // ───────────────────────────────────────────────────────────────
  // Annotation Management
  // ───────────────────────────────────────────────────────────────

  addAnnotation(ann: Omit<Annotation, 'id' | 'createdAt' | 'updatedAt'>): Annotation {
    this.annotationCounter++;
    const annotation: Annotation = {
      ...ann,
      id: `ANN-${this.annotationCounter.toString().padStart(6, '0')}`,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
    this.annotations.set(annotation.id, annotation);

    this.log.info('Annotation added', {
      id: annotation.id,
      volumeId: annotation.volumeId,
      type: annotation.type,
      author: annotation.author,
    });

    return annotation;
  }

  getAnnotationsForVolume(volumeId: string, visibility?: Annotation['visibility']): Annotation[] {
    let results = Array.from(this.annotations.values())
      .filter(a => a.volumeId === volumeId);
    if (visibility) results = results.filter(a => a.visibility === visibility);
    return results.sort((a, b) => b.createdAt - a.createdAt);
  }

  // ───────────────────────────────────────────────────────────────
  // Research Query Management
  // ───────────────────────────────────────────────────────────────

  submitResearchQuery(query: Omit<ResearchQuery, 'id' | 'status' | 'results' | 'submittedAt' | 'completedAt'>): ResearchQuery {
    this.queryCounter++;
    const researchQuery: ResearchQuery = {
      ...query,
      id: `REQ-${this.queryCounter.toString().padStart(6, '0')}`,
      status: 'pending',
      submittedAt: Date.now(),
    };
    this.researchQueries.set(researchQuery.id, researchQuery);

    this.log.info('Research query submitted', {
      id: researchQuery.id,
      query: researchQuery.query,
      scope: researchQuery.scope,
      requester: researchQuery.requester,
    });

    return researchQuery;
  }

  getResearchQuery(id: string): ResearchQuery | undefined {
    return this.researchQueries.get(id);
  }

  // ───────────────────────────────────────────────────────────────
  // Bot Delegations
  // ───────────────────────────────────────────────────────────────

  /**
   * Stack a volume onto the shelves via ShelfBot.
   */
  async stackVolume(
    volumeId: string,
    action: 'shelve' | 'retrieve' | 'transfer' | 'preserve',
    location?: string
  ): Promise<unknown> {
    const shelf = this.getBot('Shelf')!;
    const result = await shelf.execute({
      operation: 'STACK',
      volumeId,
      action,
      location,
    });
    return result;
  }

  /**
   * Look up index entries via IndexBot.
   */
  async lookupIndex(
    term: string,
    indexType: 'keyword' | 'subject' | 'author' | 'dewey' | 'full_text',
    fuzzy?: boolean
  ): Promise<unknown> {
    const index = this.getBot('Index')!;
    const result = await index.execute({
      operation: 'LOOKUP',
      term,
      indexType,
      fuzzy,
    });
    return result;
  }

  /**
   * Wrap a volume with metadata/protective cover via DustJacketBot.
   */
  async wrapVolume(
    volumeId: string,
    wrapType: 'metadata' | 'protective' | 'seal' | 'restore',
    options?: Record<string, unknown>
  ): Promise<unknown> {
    const dustJacket = this.getBot('DustJacket')!;
    const result = await dustJacket.execute({
      operation: 'WRAP',
      volumeId,
      wrapType,
      options,
    });
    return result;
  }

  // ───────────────────────────────────────────────────────────────
  // Agent Delegations
  // ───────────────────────────────────────────────────────────────

  /**
   * Catalog operations via CatalogAgent.
   */
  async catalogOperation(
    operation: 'index' | 'search' | 'retrieve' | 'curate',
    params: Record<string, unknown>
  ): Promise<unknown> {
    const catalog = this.getAgent('SID-LIBRARY-CATALOG') as CatalogAgent;
    const result = await catalog.runCycle({
      operation,
      ...params,
    });
    return result;
  }

  /**
   * Scholarly research via ScholarAgent.
   */
  async research(
    operation: 'research' | 'crossref' | 'summarize' | 'annotate',
    params: Record<string, unknown>
  ): Promise<unknown> {
    const scholar = this.getAgent('SID-LIBRARY-SCHOLAR') as ScholarAgent;
    const result = await scholar.runCycle({
      operation,
      ...params,
    });
    return result;
  }

  // ───────────────────────────────────────────────────────────────
  // Health Check
  // ───────────────────────────────────────────────────────────────

  healthCheck(): {
    status: 'healthy' | 'degraded' | 'critical';
    totalVolumes: number;
    catalogEntries: number;
    annotations: number;
    pendingQueries: number;
    checkedOut: number;
    agents: number;
    bots: number;
    timestamp: number;
  } {
    const checkedOut = Array.from(this.volumes.values())
      .filter(v => v.status === 'checked_out').length;
    const pendingQueries = Array.from(this.researchQueries.values())
      .filter(q => q.status === 'pending' || q.status === 'in_progress').length;

    const status: 'healthy' | 'degraded' | 'critical' =
      pendingQueries > 20 ? 'critical' :
      checkedOut > this.volumes.size * 0.5 ? 'degraded' :
      'healthy';

    return {
      status,
      totalVolumes: this.volumes.size,
      catalogEntries: this.catalog.size,
      annotations: this.annotations.size,
      pendingQueries,
      checkedOut,
      agents: this.listAgentIds().length,
      bots: this.listBotNames().length,
      timestamp: Date.now(),
    };
  }
}
