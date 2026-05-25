/**
 * PackerBot — Artifact Packaging Bot for The Artifactory
 *
 * Identity:  NID-ARTIFACTORY-PACKER
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TheArtifactoryAI (AID-ARTIFACTORY)
 *
 * Responsibilities:
 *   - Package source files into artifact archives
 *   - Support multiple formats (tar.gz, zip, jar, wheel, npm, docker, etc.)
 *   - Apply compression levels with size/duration tradeoffs
 *   - Embed metadata into packaged artifacts
 *   - Apply file inclusion/exclusion patterns
 *   - Generate manifest and file listing for each package
 *
 * "Pack light, pack right, pack tight."
 */

import { Bot, Logger, AuditLedger } from '../../../core/definitions';

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface PackerInput {
  operation: 'PACK';
  name: string;
  format: 'tar.gz' | 'zip' | 'jar' | 'wheel' | 'npm' | 'docker' | 'raw' | 'deb' | 'rpm';
  sourcePath: string;
  metadata?: Record<string, unknown>;
  compressionLevel?: number;  // 0-9, 0=none, 9=max
  includePatterns?: string[];  // glob patterns to include
  excludePatterns?: string[];  // glob patterns to exclude
  outputDir?: string;
  overwrite?: boolean;
}

export interface PackManifest {
  artifactName: string;
  format: string;
  sourcePath: string;
  createdAt: number;
  compressionLevel: number;
  originalSize: number;
  compressedSize: number;
  compressionRatio: number;  // percentage 0-100
  fileCount: number;
  includedFiles: string[];
  excludedFiles: string[];
  checksum: string;
  checksumAlgorithm: string;
  metadata: Record<string, unknown>;
}

export interface PackResult {
  success: boolean;
  artifactName: string;
  artifactPath: string;
  format: string;
  manifest: PackManifest;
  warnings: string[];
  duration: number;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Format Configuration
// ─────────────────────────────────────────────────────────────────────────────

const FORMAT_CONFIG: Record<string, {
  defaultCompression: number;
  supportsCompression: boolean;
  maxCompression: number;
  extension: string;
  mimeType: string;
  defaultExcludePatterns: string[];
}> = {
  'tar.gz': {
    defaultCompression: 6,
    supportsCompression: true,
    maxCompression: 9,
    extension: '.tar.gz',
    mimeType: 'application/gzip',
    defaultExcludePatterns: ['.git', 'node_modules', '__pycache__', '.DS_Store', '*.pyc'],
  },
  'zip': {
    defaultCompression: 6,
    supportsCompression: true,
    maxCompression: 9,
    extension: '.zip',
    mimeType: 'application/zip',
    defaultExcludePatterns: ['.git', 'node_modules', '__pycache__', '.DS_Store'],
  },
  'jar': {
    defaultCompression: 6,
    supportsCompression: true,
    maxCompression: 9,
    extension: '.jar',
    mimeType: 'application/java-archive',
    defaultExcludePatterns: ['.git', 'target', '*.class'],
  },
  'wheel': {
    defaultCompression: 6,
    supportsCompression: true,
    maxCompression: 9,
    extension: '.whl',
    mimeType: 'application/zip',
    defaultExcludePatterns: ['.git', '__pycache__', '*.pyc', '.eggs', '*.egg-info'],
  },
  'npm': {
    defaultCompression: 6,
    supportsCompression: true,
    maxCompression: 9,
    extension: '.tgz',
    mimeType: 'application/gzip',
    defaultExcludePatterns: ['.git', 'node_modules', 'test', '__tests__', '*.spec.ts'],
  },
  'docker': {
    defaultCompression: 0,
    supportsCompression: false,
    maxCompression: 0,
    extension: '.tar',
    mimeType: 'application/x-tar',
    defaultExcludePatterns: ['.git', 'node_modules', '.dockerignore'],
  },
  'raw': {
    defaultCompression: 0,
    supportsCompression: false,
    maxCompression: 0,
    extension: '.bin',
    mimeType: 'application/octet-stream',
    defaultExcludePatterns: [],
  },
  'deb': {
    defaultCompression: 6,
    supportsCompression: true,
    maxCompression: 9,
    extension: '.deb',
    mimeType: 'application/vnd.debian.binary-package',
    defaultExcludePatterns: ['.git', 'debian/.debhelper'],
  },
  'rpm': {
    defaultCompression: 6,
    supportsCompression: true,
    maxCompression: 9,
    extension: '.rpm',
    mimeType: 'application/x-rpm',
    defaultExcludePatterns: ['.git', 'BUILDROOT'],
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// PackerBot Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class PackerBot extends Bot {
  private readonly log: Logger;
  private readonly audit: AuditLedger;

  constructor() {
    const handler = async (input: PackerInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-ARTIFACTORY-PACKER',
      'Packer',
      handler,
      'Artifact packaging with multi-format support, compression control, and manifest generation'
    );

    this.log = new Logger('PackerBot');
    this.audit = AuditLedger.getInstance();
  }

  private async process(input: PackerInput): Promise<PackResult> {
    switch (input.operation) {
      case 'PACK':
        return this.pack(input);
      default:
        throw new Error(`PackerBot: Unknown operation "${(input as any).operation}"`);
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // PACK
  // ─────────────────────────────────────────────────────────────────────────

  private pack(input: PackerInput): PackResult {
    const startTime = Date.now();
    const {
      name,
      format,
      sourcePath,
      metadata,
      compressionLevel,
      includePatterns,
      excludePatterns,
      outputDir,
      overwrite,
    } = input;

    const config = FORMAT_CONFIG[format];
    if (!config) {
      throw new Error(`PackerBot: Unsupported format "${format}"`);
    }

    // Determine compression level
    const effectiveCompression = config.supportsCompression
      ? Math.min(compressionLevel ?? config.defaultCompression, config.maxCompression)
      : 0;

    // Merge exclusion patterns
    const allExcludePatterns = [
      ...config.defaultExcludePatterns,
      ...(excludePatterns ?? []),
    ];

    // Simulate file discovery
    const discoveredFiles = this.simulateFileDiscovery(sourcePath, includePatterns, allExcludePatterns);

    // Separate included and excluded
    const includedFiles = discoveredFiles.included;
    const excludedFiles = discoveredFiles.excluded;

    // Simulate compression
    const originalSize = this.estimateSize(includedFiles.length, format);
    const compressionRatio = this.calculateCompressionRatio(effectiveCompression, format);
    const compressedSize = Math.floor(originalSize * (1 - compressionRatio / 100));

    // Simulate checksum
    const checksum = this.simulateChecksum(name, compressedSize);
    const checksumAlgorithm = 'sha256';

    // Determine output path
    const artifactName = `${name}${config.extension}`;
    const outputPath = outputDir
      ? `${outputDir}/${artifactName}`
      : `./artifacts/${artifactName}`;

    // Warnings
    const warnings: string[] = [];
    if (excludedFiles.length > 50) {
      warnings.push(`${excludedFiles.length} files excluded by patterns — verify inclusion rules`);
    }
    if (effectiveCompression === 0 && config.supportsCompression) {
      warnings.push('Compression disabled — artifact size will be larger');
    }
    if (!overwrite && Math.random() > 0.95) {
      warnings.push(`Artifact already exists at ${outputPath} — use overwrite=true to replace`);
    }

    // Build manifest
    const manifest: PackManifest = {
      artifactName,
      format,
      sourcePath,
      createdAt: Date.now(),
      compressionLevel: effectiveCompression,
      originalSize,
      compressedSize,
      compressionRatio,
      fileCount: includedFiles.length,
      includedFiles: includedFiles.slice(0, 100), // Cap at 100 for display
      excludedFiles: excludedFiles.slice(0, 50),
      checksum,
      checksumAlgorithm,
      metadata: metadata ?? {},
    };

    const duration = Date.now() - startTime;

    const result: PackResult = {
      success: true,
      artifactName,
      artifactPath: outputPath,
      format,
      manifest,
      warnings,
      duration,
      timestamp: Date.now(),
    };

    this.audit.append({
      actor: 'NID-ARTIFACTORY-PACKER',
      action: 'ARTIFACT_PACKED',
      entity: artifactName,
      status: 'SUCCESS',
      meta: {
        format,
        compressionLevel: effectiveCompression,
        originalSize,
        compressedSize,
        compressionRatio,
        fileCount: includedFiles.length,
        duration,
      },
    });

    this.log.info('Artifact packed', {
      artifactName,
      format,
      compression: effectiveCompression,
      originalSize,
      compressedSize,
      fileCount: includedFiles.length,
    });

    return result;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Helpers
  // ─────────────────────────────────────────────────────────────────────────

  private simulateFileDiscovery(
    sourcePath: string,
    includePatterns?: string[],
    excludePatterns?: string[]
  ): { included: string[]; excluded: string[] } {
    // Simulated file discovery based on source path
    const baseFiles = [
      'src/index.ts',
      'src/main.ts',
      'src/config.ts',
      'src/types.ts',
      'src/utils/helpers.ts',
      'src/utils/constants.ts',
      'src/core/definitions.ts',
      'src/core/logger.ts',
      'src/core/audit.ts',
      'package.json',
      'tsconfig.json',
      'README.md',
      'LICENSE',
      '.gitignore',
      'docs/api.md',
      'docs/setup.md',
      'tests/unit/main.test.ts',
      'tests/integration/api.test.ts',
    ];

    const excluded: string[] = [];

    // Filter by exclude patterns
    const included = baseFiles.filter((file) => {
      const isExcluded = (excludePatterns ?? []).some((pattern) => {
        if (pattern.startsWith('*.')) {
          return file.endsWith(pattern.slice(1));
        }
        return file.includes(pattern);
      });

      if (isExcluded) {
        excluded.push(file);
        return false;
      }
      return true;
    });

    // Apply include patterns if specified
    const finalIncluded = includePatterns && includePatterns.length > 0
      ? included.filter((file) =>
          includePatterns.some((pattern) => {
            if (pattern.startsWith('*.')) {
              return file.endsWith(pattern.slice(1));
            }
            return file.includes(pattern);
          })
        )
      : included;

    // Move any filtered-out files to excluded
    const filteredOut = included.filter((f) => !finalIncluded.includes(f));
    excluded.push(...filteredOut);

    return { included: finalIncluded, excluded };
  }

  private estimateSize(fileCount: number, format: string): number {
    // Base size per file + format overhead
    const basePerFile = 2048; // 2KB average per source file
    const formatOverhead: Record<string, number> = {
      'tar.gz': 5120,
      'zip': 4096,
      'jar': 8192,
      'wheel': 6144,
      'npm': 10240,
      'docker': 51200,
      'raw': 0,
      'deb': 12288,
      'rpm': 10240,
    };

    return fileCount * basePerFile + (formatOverhead[format] ?? 4096);
  }

  private calculateCompressionRatio(compressionLevel: number, format: string): number {
    if (compressionLevel === 0) return 0;

    // Base compression ratios by format
    const baseRatios: Record<string, number> = {
      'tar.gz': 65,
      'zip': 60,
      'jar': 58,
      'wheel': 55,
      'npm': 62,
      'docker': 35,
      'raw': 0,
      'deb': 60,
      'rpm': 58,
    };

    const baseRatio = baseRatios[format] ?? 50;

    // Scale by compression level (1-9 → 40%-100% of base ratio)
    const levelFactor = 0.4 + (compressionLevel / 9) * 0.6;

    return Math.floor(baseRatio * levelFactor);
  }

  private simulateChecksum(name: string, size: number): string {
    // Simulated SHA-256 checksum
    const hash = Buffer.from(`${name}:${size}:${Date.now()}`).toString('base64');
    return hash.replace(/[^a-f0-9]/g, '').padEnd(64, '0').slice(0, 64);
  }
}
