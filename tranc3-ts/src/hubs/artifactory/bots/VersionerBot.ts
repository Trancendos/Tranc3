/**
 * VersionerBot — Semantic Versioning Bot for The Artifactory
 *
 * Identity:  NID-ARTIFACTORY-VERSIONER
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TheArtifactoryAI (AID-ARTIFACTORY)
 *
 * Responsibilities:
 *   - Assign semantic versions to artifacts
 *   - Parse and validate semver strings (major.minor.patch[-prerelease][+build])
 *   - Track version history per artifact
 *   - Manage latest/stable version pointers
 *   - Support prerelease and build metadata tags
 *   - Generate changelog entries with version bumps
 *
 * "Version is truth. Every increment is a contract."
 */

import { Bot, Logger, AuditLedger } from '../../../core/definitions';

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface VersionerInput {
  operation: 'ASSIGN';
  artifactId: string;
  version: string;
  changelog?: string;
  prerelease?: boolean;
  prereleaseTag?: string;   // e.g. 'alpha', 'beta', 'rc'
  buildMetadata?: string;   // e.g. 'build.123'
  force?: boolean;          // force assign even if version exists
}

export interface SemverParts {
  major: number;
  minor: number;
  patch: number;
  prerelease?: string;
  buildMetadata?: string;
  raw: string;
  isPrerelease: boolean;
  isStable: boolean;
}

export interface VersionEntry {
  artifactId: string;
  version: SemverParts;
  changelog?: string;
  assignedAt: number;
  assignedBy: string;
  isLatest: boolean;
  isStable: boolean;
}

export interface VersionHistory {
  artifactId: string;
  versions: VersionEntry[];
  latest: string | null;
  latestStable: string | null;
  totalCount: number;
  prereleaseCount: number;
  stableCount: number;
}

export interface AssignResult {
  success: boolean;
  artifactId: string;
  version: SemverParts;
  changelog?: string;
  previousVersion: string | null;
  isLatest: boolean;
  isStable: boolean;
  versionHistory: VersionHistory;
  warnings: string[];
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// VersionerBot Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class VersionerBot extends Bot {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private readonly versionStore: Map<string, VersionEntry[]>;

  constructor() {
    const handler = async (input: VersionerInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-ARTIFACTORY-VERSIONER',
      'Versioner',
      handler,
      'Semantic version assignment with prerelease support, version history tracking, and latest/stable pointers'
    );

    this.log = new Logger('VersionerBot');
    this.audit = AuditLedger.getInstance();
    this.versionStore = new Map();
  }

  private async process(input: VersionerInput): Promise<AssignResult> {
    switch (input.operation) {
      case 'ASSIGN':
        return this.assign(input);
      default:
        throw new Error(`VersionerBot: Unknown operation "${(input as any).operation}"`);
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // ASSIGN
  // ─────────────────────────────────────────────────────────────────────────

  private assign(input: VersionerInput): AssignResult {
    const {
      artifactId,
      version,
      changelog,
      prerelease,
      prereleaseTag,
      buildMetadata,
      force,
    } = input;

    // Parse the version string
    const parsedVersion = this.parseSemver(version, prerelease, prereleaseTag, buildMetadata);

    if (!parsedVersion) {
      throw new Error(`VersionerBot: Invalid semantic version "${version}"`);
    }

    // Get or create version history for this artifact
    let history = this.versionStore.get(artifactId);
    if (!history) {
      history = [];
      this.versionStore.set(artifactId, history);
    }

    // Check for duplicate version
    const existing = history.find((entry) => entry.version.raw === parsedVersion.raw);
    if (existing && !force) {
      throw new Error(
        `VersionerBot: Version "${parsedVersion.raw}" already exists for artifact "${artifactId}". Use force=true to overwrite.`
      );
    }

    const warnings: string[] = [];

    // Validate version progression
    const previousVersion = this.getLatestVersion(artifactId);
    if (previousVersion) {
      const prevParsed = this.parseSemver(previousVersion);
      if (prevParsed && this.isVersionDowngrade(prevParsed, parsedVersion)) {
        warnings.push(
          `Version downgrade detected: ${prevParsed.raw} → ${parsedVersion.raw}. This may break consumers.`
        );
      }
    }

    // Validate major version 0
    if (parsedVersion.major === 0) {
      warnings.push('Major version 0 indicates initial development — API stability is not guaranteed');
    }

    // Validate prerelease
    if (parsedVersion.isPrerelease) {
      warnings.push(`Prerelease version "${parsedVersion.prerelease}" — not recommended for production use`);
    }

    // Determine if this is the latest/stable
    const isLatest = true; // New version is always latest
    const isStable = parsedVersion.isStable;

    // Update previous entries' isLatest flag
    for (const entry of history) {
      entry.isLatest = false;
    }

    // Create version entry
    const versionEntry: VersionEntry = {
      artifactId,
      version: parsedVersion,
      changelog,
      assignedAt: Date.now(),
      assignedBy: 'NID-ARTIFACTORY-VERSIONER',
      isLatest,
      isStable,
    };

    // If force-overwriting, remove the existing entry
    if (existing && force) {
      const idx = history.indexOf(existing);
      if (idx >= 0) {
        history.splice(idx, 1);
      }
    }

    history.push(versionEntry);

    // Build version history summary
    const versionHistory = this.buildVersionHistory(artifactId);

    const result: AssignResult = {
      success: true,
      artifactId,
      version: parsedVersion,
      changelog,
      previousVersion: previousVersion,
      isLatest,
      isStable,
      versionHistory,
      warnings,
      timestamp: Date.now(),
    };

    this.audit.append({
      actor: 'NID-ARTIFACTORY-VERSIONER',
      action: 'VERSION_ASSIGNED',
      entity: artifactId,
      status: 'SUCCESS',
      meta: {
        version: parsedVersion.raw,
        previousVersion,
        isPrerelease: parsedVersion.isPrerelease,
        isStable,
        warningsCount: warnings.length,
      },
    });

    this.log.info('Version assigned', {
      artifactId,
      version: parsedVersion.raw,
      previousVersion,
      isStable,
    });

    return result;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Semver Parsing
  // ─────────────────────────────────────────────────────────────────────────

  private parseSemver(
    version: string,
    prereleaseFlag?: boolean,
    prereleaseTag?: string,
    buildMetadata?: string
  ): SemverParts | null {
    // Standard semver regex: major.minor.patch[-prerelease][+build]
    const semverRegex = /^(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z0-9.]+))?(?:\+([a-zA-Z0-9.]+))?$/;
    const match = version.match(semverRegex);

    if (!match) {
      return null;
    }

    const major = parseInt(match[1], 10);
    const minor = parseInt(match[2], 10);
    const patch = parseInt(match[3], 10);

    // Determine prerelease string
    let prerelease: string | undefined = match[4];
    if (!prerelease && prereleaseFlag && prereleaseTag) {
      prerelease = prereleaseTag;
    } else if (!prerelease && prereleaseFlag) {
      prerelease = 'pre';
    }

    // Build metadata from input or regex
    const metadata = buildMetadata ?? match[5];

    // Reconstruct the raw version string
    let raw = `${major}.${minor}.${patch}`;
    if (prerelease) {
      raw += `-${prerelease}`;
    }
    if (metadata) {
      raw += `+${metadata}`;
    }

    return {
      major,
      minor,
      patch,
      prerelease,
      buildMetadata: metadata,
      raw,
      isPrerelease: !!prerelease,
      isStable: !prerelease && major > 0,
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Version Comparison
  // ─────────────────────────────────────────────────────────────────────────

  private isVersionDowngrade(previous: SemverParts, current: SemverParts): boolean {
    // Compare major.minor.patch numerically
    if (current.major < previous.major) return true;
    if (current.major > previous.major) return false;
    if (current.minor < previous.minor) return true;
    if (current.minor > previous.minor) return false;
    if (current.patch < previous.patch) return true;
    // Same version but new is prerelease while previous was not
    if (current.isPrerelease && !previous.isPrerelease) return true;
    return false;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Version History Management
  // ─────────────────────────────────────────────────────────────────────────

  private getLatestVersion(artifactId: string): string | null {
    const history = this.versionStore.get(artifactId);
    if (!history || history.length === 0) return null;
    return history[history.length - 1].version.raw;
  }

  private buildVersionHistory(artifactId: string): VersionHistory {
    const history = this.versionStore.get(artifactId) ?? [];

    // Sort by version (latest last)
    const sorted = [...history].sort((a, b) => {
      const va = a.version;
      const vb = b.version;
      if (va.major !== vb.major) return va.major - vb.major;
      if (va.minor !== vb.minor) return va.minor - vb.minor;
      return va.patch - vb.patch;
    });

    // Find latest stable
    const stableVersions = sorted.filter((v) => v.isStable);
    const latestStable = stableVersions.length > 0
      ? stableVersions[stableVersions.length - 1].version.raw
      : null;

    // Find latest (including prerelease)
    const latest = sorted.length > 0
      ? sorted[sorted.length - 1].version.raw
      : null;

    return {
      artifactId,
      versions: sorted,
      latest,
      latestStable,
      totalCount: sorted.length,
      prereleaseCount: sorted.filter((v) => v.version.isPrerelease).length,
      stableCount: stableVersions.length,
    };
  }
}
