/**
 * The Library — Barrel Exports
 *
 * Hub:      The Library
 * Pillar:   Norman Hawkins
 * Identity: AID-LIBRARY
 *
 * All types, agents, bots, and the Lead AI are re-exported here
 * for clean upstream imports.
 */

// ─── Lead AI ──────────────────────────────────────────────────────────
export { TheLibraryAI } from './TheLibraryAI';
export type {
  Volume as AIVolume,
  CatalogEntry as AICatalogEntry,
  Annotation as AIAnnotation,
  ResearchQuery as AIResearchQuery,
  SearchResult as AISearchResult,
  CollectionFilter as AICollectionFilter,
} from './TheLibraryAI';

// ─── Agents ───────────────────────────────────────────────────────────
export { CatalogAgent } from './agents/CatalogAgent';
export type {
  CatalogInput,
  IndexResult,
  SearchResult as CatalogSearchResult,
  RetrieveResult,
  CurationResult,
  CatalogPerception,
  CatalogDecision,
  CatalogActionResult,
} from './agents/CatalogAgent';

export { ScholarAgent } from './agents/ScholarAgent';
export type {
  ScholarInput,
  ResearchFinding,
  ResearchReport,
  CrossReference,
  Summary,
  AnnotationDraft,
  ScholarPerception,
  ScholarDecision,
  ScholarActionResult,
} from './agents/ScholarAgent';

// ─── Bots ─────────────────────────────────────────────────────────────
export { ShelfBot } from './bots/ShelfBot';
export type {
  ShelfInput,
  ShelfLocation,
  ShelfRecord,
  ShelfOccupancy,
  StackResult,
} from './bots/ShelfBot';

export { IndexBot } from './bots/IndexBot';
export type {
  IndexInput,
  IndexEntry,
  LookupResult,
  IndexMatch,
  IndexCoverage,
} from './bots/IndexBot';

export { DustJacketBot } from './bots/DustJacketBot';
export type {
  DustJacketInput,
  WrapRecord,
  WrapResult,
} from './bots/DustJacketBot';
