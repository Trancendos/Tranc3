/**
 * IndexBot — Catalogue Lookup Bot for The Library
 *
 * Identity:  NID-LIBRARY-INDEX
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TheLibraryAI (AID-LIBRARY)
 *
 * Responsibilities:
 *   - LOOKUP: Search the index for terms across keyword, subject,
 *             author, Dewey, and full-text indexes
 *   - Support exact and fuzzy matching modes
 *   - Return ranked results with relevance scoring
 *   - Maintain index statistics and coverage metrics
 */

import { Bot, Logger, AuditLedger } from '../../../core/definitions'

const auditLedger = new AuditLedger();

// ─────────────────────────────────────────────────────────────────────
// Input / Output Types
// ─────────────────────────────────────────────────────────────────────

export interface IndexInput {
  operation: 'LOOKUP';
  term: string;
  indexType: 'keyword' | 'subject' | 'author' | 'dewey' | 'full_text';
  fuzzy?: boolean;
  maxResults?: number;
}

export interface IndexEntry {
  id: string;
  term: string;
  type: IndexInput['indexType'];
  volumeIds: string[];
  frequency: number;
  lastUpdated: number;
}

export interface LookupResult {
  query: string;
  indexType: IndexInput['indexType'];
  fuzzy: boolean;
  matches: IndexMatch[];
  totalMatches: number;
  searchTime: number;
  coverage: IndexCoverage;
}

export interface IndexMatch {
  volumeId: string;
  term: string;
  matchType: 'exact' | 'prefix' | 'fuzzy' | 'stem' | 'synonym';
  relevance: number;
  context: string;
  positions: number[];
}

export interface IndexCoverage {
  keywordEntries: number;
  subjectEntries: number;
  authorEntries: number;
  deweyEntries: number;
  fullTextEntries: number;
  totalIndexed: number;
  lastReindex: number;
}

// ─────────────────────────────────────────────────────────────────────
// Simulated Index Data
// ─────────────────────────────────────────────────────────────────────

const KEYWORD_INDEX: Map<string, string[]> = new Map([
  ['epistemology', ['VOL-000001', 'VOL-000003', 'VOL-000007']],
  ['quantum', ['VOL-000002', 'VOL-000005', 'VOL-000009']],
  ['algorithm', ['VOL-000004', 'VOL-000006', 'VOL-000010']],
  ['renaissance', ['VOL-000008', 'VOL-000011', 'VOL-000012']],
  ['architecture', ['VOL-000003', 'VOL-000006', 'VOL-000009']],
  ['metaphysics', ['VOL-000001', 'VOL-000007']],
  ['neural', ['VOL-000002', 'VOL-000004', 'VOL-000010']],
  ['thermodynamics', ['VOL-000005', 'VOL-000009']],
  ['rhetoric', ['VOL-000008', 'VOL-000011']],
  ['cosmology', ['VOL-000003', 'VOL-000012']],
]);

const SUBJECT_INDEX: Map<string, string[]> = new Map([
  ['philosophy', ['VOL-000001', 'VOL-000003', 'VOL-000007']],
  ['physics', ['VOL-000002', 'VOL-000005', 'VOL-000009']],
  ['computer science', ['VOL-000004', 'VOL-000006', 'VOL-000010']],
  ['history', ['VOL-000008', 'VOL-000011', 'VOL-000012']],
  ['art', ['VOL-000003', 'VOL-000006']],
  ['literature', ['VOL-000008', 'VOL-000011']],
  ['mathematics', ['VOL-000002', 'VOL-000004']],
  ['engineering', ['VOL-000009', 'VOL-000010']],
]);

const AUTHOR_INDEX: Map<string, string[]> = new Map([
  ['hawkins', ['VOL-000001', 'VOL-000005']],
  ['fontaine', ['VOL-000002', 'VOL-000008']],
  ['macintyre', ['VOL-000003', 'VOL-000009']],
  ['voxx', ['VOL-000004', 'VOL-000010']],
  ['savania', ['VOL-000006', 'VOL-000011']],
  ['guardian', ['VOL-000007', 'VOL-000012']],
]);

const DEWEY_INDEX: Map<string, string[]> = new Map([
  ['100', ['VOL-000001', 'VOL-000007']],
  ['530', ['VOL-000002', 'VOL-000005', 'VOL-000009']],
  ['004', ['VOL-000004', 'VOL-000006', 'VOL-000010']],
  ['900', ['VOL-000008', 'VOL-000011', 'VOL-000012']],
  ['700', ['VOL-000003']],
  ['800', ['VOL-000011']],
  ['510', ['VOL-000002', 'VOL-000004']],
  ['620', ['VOL-000009', 'VOL-000010']],
]);

// ─────────────────────────────────────────────────────────────────────
// IndexBot Implementation
// ─────────────────────────────────────────────────────────────────────

export class IndexBot extends Bot {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private lookupCount: number;

  constructor() {
    super(
      'NID-LIBRARY-INDEX',
      'Index',
      async (input: IndexInput) => this.handleLookup(input),
      'Performs index lookups across keyword, subject, author, Dewey, and full-text indexes'
    );

    this.log = new Logger('IndexBot');
    this.audit = auditLedger;
    this.lookupCount = 0;
  }

  // ───────────────────────────────────────────────────────────────
  // Main Handler
  // ───────────────────────────────────────────────────────────────

  private async handleLookup(input: IndexInput): Promise<LookupResult> {
    if (input.operation !== 'LOOKUP') {
      return this.emptyResult(input.term, input.indexType, input.fuzzy ?? false, 'Invalid operation');
    }

    const startTime = Date.now();
    this.lookupCount++;

    const term = input.term.toLowerCase().trim();
    const fuzzy = input.fuzzy ?? false;
    const maxResults = input.maxResults ?? 20;

    // Select the appropriate index
    const indexMap = this.selectIndex(input.indexType);

    // Search the index
    const matches = this.searchIndex(indexMap, term, input.indexType, fuzzy, maxResults);

    const searchTime = Date.now() - startTime;

    const coverage: IndexCoverage = {
      keywordEntries: KEYWORD_INDEX.size,
      subjectEntries: SUBJECT_INDEX.size,
      authorEntries: AUTHOR_INDEX.size,
      deweyEntries: DEWEY_INDEX.size,
      fullTextEntries: KEYWORD_INDEX.size * 15, // Simulated: each keyword has ~15 full-text entries
      totalIndexed: KEYWORD_INDEX.size + SUBJECT_INDEX.size + AUTHOR_INDEX.size + DEWEY_INDEX.size,
      lastReindex: Date.now() - 3600000, // 1 hour ago
    };

    this.audit.append({
      actor: 'IndexBot',
      action: 'LOOKUP',
      entity: term,
      status: 'SUCCESS',
      meta: { indexType: input.indexType, fuzzy, matches: matches.length, searchTime },
    });

    this.log.info('Index lookup completed', {
      term,
      indexType: input.indexType,
      fuzzy,
      matches: matches.length,
      searchTime,
    });

    return {
      query: input.term,
      indexType: input.indexType,
      fuzzy,
      matches,
      totalMatches: matches.length,
      searchTime,
      coverage,
    };
  }

  // ───────────────────────────────────────────────────────────────
  // Select the appropriate index
  // ───────────────────────────────────────────────────────────────

  private selectIndex(indexType: IndexInput['indexType']): Map<string, string[]> {
    switch (indexType) {
      case 'keyword': return KEYWORD_INDEX;
      case 'subject': return SUBJECT_INDEX;
      case 'author': return AUTHOR_INDEX;
      case 'dewey': return DEWEY_INDEX;
      case 'full_text': return KEYWORD_INDEX; // Full-text is simulated via keyword index
      default: return KEYWORD_INDEX;
    }
  }

  // ───────────────────────────────────────────────────────────────
  // Search the selected index
  // ───────────────────────────────────────────────────────────────

  private searchIndex(
    indexMap: Map<string, string[]>,
    term: string,
    indexType: IndexInput['indexType'],
    fuzzy: boolean,
    maxResults: number
  ): IndexMatch[] {
    const matches: IndexMatch[] = [];

    for (const [indexTerm, volumeIds] of indexMap) {
      const indexTermLower = indexTerm.toLowerCase();

      if (indexTermLower === term) {
        // Exact match
        for (const vid of volumeIds) {
          matches.push({
            volumeId: vid,
            term: indexTerm,
            matchType: 'exact',
            relevance: 1.0,
            context: `Exact match for "${indexTerm}" in ${indexType} index`,
            positions: [1, 5, 12],
          });
        }
      } else if (indexTermLower.startsWith(term)) {
        // Prefix match
        for (const vid of volumeIds) {
          matches.push({
            volumeId: vid,
            term: indexTerm,
            matchType: 'prefix',
            relevance: 0.85,
            context: `Prefix match: "${term}" matches "${indexTerm}" in ${indexType} index`,
            positions: [1],
          });
        }
      } else if (fuzzy && this.levenshtein(term, indexTermLower) <= 2) {
        // Fuzzy match (Levenshtein distance <= 2)
        for (const vid of volumeIds) {
          const distance = this.levenshtein(term, indexTermLower);
          matches.push({
            volumeId: vid,
            term: indexTerm,
            matchType: 'fuzzy',
            relevance: 0.6 + (0.15 * (1 - distance / Math.max(term.length, indexTermLower.length))),
            context: `Fuzzy match: "${term}" ≈ "${indexTerm}" (distance: ${distance}) in ${indexType} index`,
            positions: [3],
          });
        }
      } else if (fuzzy && this.shareStem(term, indexTermLower)) {
        // Stem match
        for (const vid of volumeIds) {
          matches.push({
            volumeId: vid,
            term: indexTerm,
            matchType: 'stem',
            relevance: 0.55,
            context: `Stem match: "${term}" shares stem with "${indexTerm}" in ${indexType} index`,
            positions: [2],
          });
        }
      }
    }

    // Sort by relevance descending
    matches.sort((a, b) => b.relevance - a.relevance);

    return matches.slice(0, maxResults);
  }

  // ───────────────────────────────────────────────────────────────
  // Helper: Levenshtein distance
  // ───────────────────────────────────────────────────────────────

  private levenshtein(a: string, b: string): number {
    const matrix: number[][] = [];

    for (let i = 0; i <= b.length; i++) matrix[i] = [i];
    for (let j = 0; j <= a.length; j++) matrix[0][j] = j;

    for (let i = 1; i <= b.length; i++) {
      for (let j = 1; j <= a.length; j++) {
        if (b.charAt(i - 1) === a.charAt(j - 1)) {
          matrix[i][j] = matrix[i - 1][j - 1];
        } else {
          matrix[i][j] = Math.min(
            matrix[i - 1][j - 1] + 1,
            matrix[i][j - 1] + 1,
            matrix[i - 1][j] + 1,
          );
        }
      }
    }

    return matrix[b.length][a.length];
  }

  // ───────────────────────────────────────────────────────────────
  // Helper: Check if two terms share a common stem (simplified)
  // ───────────────────────────────────────────────────────────────

  private shareStem(a: string, b: string): boolean {
    if (a.length < 3 || b.length < 3) return false;
    const stemA = a.substring(0, Math.ceil(a.length * 0.6));
    const stemB = b.substring(0, Math.ceil(b.length * 0.6));
    return stemA === stemB;
  }

  // ───────────────────────────────────────────────────────────────
  // Helper: Empty result
  // ───────────────────────────────────────────────────────────────

  private emptyResult(term: string, indexType: IndexInput['indexType'], fuzzy: boolean, reason: string): LookupResult {
    return {
      query: term,
      indexType,
      fuzzy,
      matches: [],
      totalMatches: 0,
      searchTime: 0,
      coverage: {
        keywordEntries: 0,
        subjectEntries: 0,
        authorEntries: 0,
        deweyEntries: 0,
        fullTextEntries: 0,
        totalIndexed: 0,
        lastReindex: 0,
      },
    };
  }
}
