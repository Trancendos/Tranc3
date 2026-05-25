/**
 * The Artifactory — Barrel Exports
 *
 * Hub:       The Artifactory
 * Identity:  AID-ARTIFACTORY
 * Pillar:    Voxx (Keeper of the Archives)
 *
 * Pipeline:  Packer (create) → Checksum (verify) → Versioner (tag)
 *            → Unpacker (extract)
 *            Librarian manages the catalog,
 *            Archivist ensures long-term integrity
 */

// ─── Lead AI ─────────────────────────────────────────────────────────────────
export { TheArtifactoryAI } from './TheArtifactoryAI';
export type {
  Artifact,
  ArtifactMetadata,
  ArtifactVersion,
  PackageRegistry,
  IntegrityReport,
} from './TheArtifactoryAI';

// ─── Agents ──────────────────────────────────────────────────────────────────
export { LibrarianAgent } from './agents/LibrarianAgent';
export type {
  LibrarianInput,
  CatalogEntry,
  SearchResult,
  DeprecationRecord,
  LibrarianResult,
} from './agents/LibrarianAgent';

export { ArchivistAgent } from './agents/ArchivistAgent';
export type {
  ArchivistInput,
  RetentionPolicy,
  ArchiveRecord,
  RestoreRecord,
  AuditReport,
} from './agents/ArchivistAgent';

// ─── Bots ────────────────────────────────────────────────────────────────────
export { PackerBot } from './bots/PackerBot';
export type {
  PackerInput,
  PackManifest,
  PackResult,
} from './bots/PackerBot';

export { UnpackerBot } from './bots/UnpackerBot';
export type {
  UnpackerInput,
  ExtractedFile,
  ConflictEntry,
  UnpackResult,
} from './bots/UnpackerBot';

export { ChecksumBot } from './bots/ChecksumBot';
export type {
  ChecksumInput,
  ChecksumEntry,
  IntegrityDetail,
  VerifyResult,
} from './bots/ChecksumBot';

export { VersionerBot } from './bots/VersionerBot';
export type {
  VersionerInput,
  SemverParts,
  VersionEntry,
  VersionHistory,
  AssignResult,
} from './bots/VersionerBot';
