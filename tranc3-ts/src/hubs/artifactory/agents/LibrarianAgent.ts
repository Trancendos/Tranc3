/**
 * LibrarianAgent — Artifact Catalog & Search Agent for The Artifactory
 *
 * Identity:  SID-ARTIFACTORY-LIBRARIAN
 * Tier:      4 (Autonomous Microservice)
 * Parent:    TheArtifactoryAI (AID-ARTIFACTORY)
 *
 * Responsibilities:
 *   - Index artifacts into searchable catalog
 *   - Search artifacts by name, type, version, tags, metadata
 *   - Tag artifacts for categorisation and discovery
 *   - Deprecate artifacts that are no longer current
 *   - Maintain catalog integrity and cross-references
 *
 * "A library is not a luxury but one of the necessities of life."
 */

import { Agent, Logger, AuditLedger } from '../../../core/definitions'

const auditLedger = new AuditLedger();

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface LibrarianInput {
  operation: 'index' | 'search' | 'tag' | 'deprecate';
  artifactId?: string;
  artifactName?: string;
  artifactType?: string;
  version?: string;
  tags?: string[];
  searchQuery?: string;
  searchFilters?: {
    type?: string;
    status?: string;
    environment?: string;
    format?: string;
    publishedAfter?: number;
    publishedBefore?: number;
  };
  deprecationReason?: string;
  replacementArtifactId?: string;
}

export interface CatalogEntry {
  artifactId: string;
  name: string;
  type: string;
  version: string;
  tags: string[];
  status: string;
  environment: string;
  format: string;
  publishedAt?: number;
  indexedAt: number;
  references: string[];  // artifact IDs that depend on this
  dependencies: string[]; // artifact IDs this depends on
}

export interface SearchResult {
  query: string;
  totalMatches: number;
  entries: CatalogEntry[];
  facets: Record<string, Record<string, number>>;
  suggestions: string[];
  searchTime: number;
}

export interface DeprecationRecord {
  artifactId: string;
  reason: string;
  replacementId?: string;
  deprecatedAt: number;
  willBeRemovedAt?: number;
  migrationNotes?: string;
}

export interface LibrarianResult {
  success: boolean;
  operation: LibrarianInput['operation'];
  entry?: CatalogEntry;
  searchResult?: SearchResult;
  deprecation?: DeprecationRecord;
  message: string;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// LibrarianAgent Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class LibrarianAgent extends Agent {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private readonly catalog: Map<string, CatalogEntry>;
  private readonly deprecations: Map<string, DeprecationRecord>;
  private readonly tagIndex: Map<string, Set<string>>;  // tag → Set<artifactId>

  constructor() {
    super('SID-ARTIFACTORY-LIBRARIAN');
    this.log = new Logger('LibrarianAgent');
    this.audit = auditLedger;
    this.catalog = new Map();
    this.deprecations = new Map();
    this.tagIndex = new Map();
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Agent Lifecycle: Perceive → Decide → Act
  // ─────────────────────────────────────────────────────────────────────────

  public async perceive(input: LibrarianInput): Promise<LibrarianInput> {
    this.log.info('Perceiving catalog operation', { operation: input.operation });

    // Validate artifact references
    if (input.artifactId && !this.catalog.has(input.artifactId)) {
      this.log.debug('Artifact not yet in catalog', { artifactId: input.artifactId });
    }

    // Validate search query
    if (input.operation === 'search' && !input.searchQuery && !input.searchFilters) {
      this.log.warn('Search operation without query or filters — will return all entries');
    }

    return input;
  }

  public async decide(input: LibrarianInput): Promise<string> {
    this.log.info('Deciding catalog action', { operation: input.operation });

    switch (input.operation) {
      case 'index': return 'indexArtifact';
      case 'search': return 'searchCatalog';
      case 'tag': return 'tagArtifact';
      case 'deprecate': return 'deprecateArtifact';
      default: return 'unknown';
    }
  }

  public async act(input: LibrarianInput, decision: string): Promise<LibrarianResult> {
    this.log.info('Acting on catalog decision', { decision });

    switch (decision) {
      case 'indexArtifact': return this.indexArtifact(input);
      case 'searchCatalog': return this.searchCatalog(input);
      case 'tagArtifact': return this.tagArtifact(input);
      case 'deprecateArtifact': return this.deprecateArtifact(input);
      default:
        return {
          success: false,
          operation: input.operation,
          message: `Unknown operation: ${input.operation}`,
          timestamp: Date.now(),
        };
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Index Artifact
  // ─────────────────────────────────────────────────────────────────────────

  private indexArtifact(input: LibrarianInput): LibrarianResult {
    const artifactId = input.artifactId ?? `ART-${this.catalog.size + 1}`;
    const name = input.artifactName ?? 'unnamed-artifact';
    const type = input.artifactType ?? 'binary';
    const version = input.version ?? '0.1.0';
    const tags = input.tags ?? [];

    const entry: CatalogEntry = {
      artifactId,
      name,
      type,
      version,
      tags,
      status: 'building',
      environment: 'development',
      format: 'raw',
      indexedAt: Date.now(),
      references: [],
      dependencies: [],
    };

    this.catalog.set(artifactId, entry);

    // Update tag index
    for (const tag of tags) {
      if (!this.tagIndex.has(tag)) {
        this.tagIndex.set(tag, new Set());
      }
      this.tagIndex.get(tag)!.add(artifactId);
    }

    this.audit.append({
      actor: this.id,
      action: 'ARTIFACT_INDEXED',
      entity: artifactId,
      status: 'SUCCESS',
      meta: { name, type, version, tags },
    });

    this.log.info('Artifact indexed', { artifactId, name, version });

    return {
      success: true,
      operation: 'index',
      entry,
      message: `Artifact "${name}" (${artifactId}) indexed successfully`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Search Catalog
  // ─────────────────────────────────────────────────────────────────────────

  private searchCatalog(input: LibrarianInput): LibrarianResult {
    const startTime = Date.now();
    const query = input.searchQuery ?? '';
    const filters = input.searchFilters;

    let results = Array.from(this.catalog.values());

    // Apply text search
    if (query) {
      const lowerQuery = query.toLowerCase();
      results = results.filter((entry) =>
        entry.name.toLowerCase().includes(lowerQuery) ||
        entry.type.toLowerCase().includes(lowerQuery) ||
        entry.tags.some((t) => t.toLowerCase().includes(lowerQuery))
      );
    }

    // Apply filters
    if (filters) {
      if (filters.type) {
        results = results.filter((e) => e.type === filters.type);
      }
      if (filters.status) {
        results = results.filter((e) => e.status === filters.status);
      }
      if (filters.environment) {
        results = results.filter((e) => e.environment === filters.environment);
      }
      if (filters.format) {
        results = results.filter((e) => e.format === filters.format);
      }
      if (filters.publishedAfter) {
        results = results.filter((e) => (e.publishedAt ?? 0) >= filters.publishedAfter!);
      }
      if (filters.publishedBefore) {
        results = results.filter((e) => (e.publishedAt ?? Infinity) <= filters.publishedBefore!);
      }
    }

    // Build facets
    const facets: Record<string, Record<string, number>> = {};
    for (const entry of results) {
      // Type facet
      if (!facets.type) facets.type = {};
      facets.type[entry.type] = (facets.type[entry.type] ?? 0) + 1;

      // Status facet
      if (!facets.status) facets.status = {};
      facets.status[entry.status] = (facets.status[entry.status] ?? 0) + 1;

      // Format facet
      if (!facets.format) facets.format = {};
      facets.format[entry.format] = (facets.format[entry.format] ?? 0) + 1;
    }

    // Generate suggestions based on available tags
    const suggestions: string[] = [];
    for (const tag of this.tagIndex.keys()) {
      if (query && tag.toLowerCase().includes(query.toLowerCase()) && !suggestions.includes(tag)) {
        suggestions.push(tag);
      }
    }
    if (suggestions.length === 0 && this.tagIndex.size > 0) {
      const allTags = Array.from(this.tagIndex.keys());
      suggestions.push(...allTags.slice(0, 5));
    }

    const searchResult: SearchResult = {
      query,
      totalMatches: results.length,
      entries: results,
      facets,
      suggestions: suggestions.slice(0, 10),
      searchTime: Date.now() - startTime,
    };

    this.log.info('Catalog searched', {
      query,
      matches: results.length,
      searchTime: searchResult.searchTime,
    });

    return {
      success: true,
      operation: 'search',
      searchResult,
      message: `Found ${results.length} artifact(s) matching "${query || '*'}"`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Tag Artifact
  // ─────────────────────────────────────────────────────────────────────────

  private tagArtifact(input: LibrarianInput): LibrarianResult {
    const { artifactId, tags } = input;

    if (!artifactId || !tags || tags.length === 0) {
      return {
        success: false,
        operation: 'tag',
        message: 'Artifact ID and tags are required for tagging',
        timestamp: Date.now(),
      };
    }

    const entry = this.catalog.get(artifactId);
    if (!entry) {
      return {
        success: false,
        operation: 'tag',
        message: `Artifact ${artifactId} not found in catalog`,
        timestamp: Date.now(),
      };
    }

    // Add new tags (deduplicated)
    const newTags = tags.filter((t) => !entry.tags.includes(t));
    entry.tags = [...entry.tags, ...newTags];

    // Update tag index
    for (const tag of newTags) {
      if (!this.tagIndex.has(tag)) {
        this.tagIndex.set(tag, new Set());
      }
      this.tagIndex.get(tag)!.add(artifactId);
    }

    this.audit.append({
      actor: this.id,
      action: 'ARTIFACT_TAGGED',
      entity: artifactId,
      status: 'SUCCESS',
      meta: { addedTags: newTags, totalTags: entry.tags.length },
    });

    this.log.info('Artifact tagged', { artifactId, newTags: newTags.length, totalTags: entry.tags.length });

    return {
      success: true,
      operation: 'tag',
      entry,
      message: `Added ${newTags.length} tag(s) to ${artifactId} — now has ${entry.tags.length} total`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Deprecate Artifact
  // ─────────────────────────────────────────────────────────────────────────

  private deprecateArtifact(input: LibrarianInput): LibrarianResult {
    const { artifactId, deprecationReason, replacementArtifactId } = input;

    if (!artifactId) {
      return {
        success: false,
        operation: 'deprecate',
        message: 'Artifact ID is required for deprecation',
        timestamp: Date.now(),
      };
    }

    const entry = this.catalog.get(artifactId);
    if (!entry) {
      return {
        success: false,
        operation: 'deprecate',
        message: `Artifact ${artifactId} not found in catalog`,
        timestamp: Date.now(),
      };
    }

    // Update catalog entry status
    entry.status = 'deprecated';

    // Create deprecation record
    const deprecation: DeprecationRecord = {
      artifactId,
      reason: deprecationReason ?? 'No reason provided',
      replacementId: replacementArtifactId,
      deprecatedAt: Date.now(),
      willBeRemovedAt: Date.now() + 90 * 24 * 60 * 60 * 1000, // 90 days
      migrationNotes: replacementArtifactId
        ? `Migrate to ${replacementArtifactId} before removal date`
        : undefined,
    };

    this.deprecations.set(artifactId, deprecation);

    this.audit.append({
      actor: this.id,
      action: 'ARTIFACT_DEPRECATED',
      entity: artifactId,
      status: 'SUCCESS',
      meta: {
        reason: deprecation.reason,
        replacement: replacementArtifactId,
        removalDate: deprecation.willBeRemovedAt,
      },
    });

    this.log.info('Artifact deprecated', {
      artifactId,
      reason: deprecation.reason,
      replacement: replacementArtifactId,
    });

    return {
      success: true,
      operation: 'deprecate',
      deprecation,
      message: `Artifact ${artifactId} deprecated — ${deprecation.reason}`,
      timestamp: Date.now(),
    };
  }
}
