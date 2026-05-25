/**
 * UnpackerBot — Artifact Extraction Bot for The Artifactory
 *
 * Identity:  NID-ARTIFACTORY-UNPACKER
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TheArtifactoryAI (AID-ARTIFACTORY)
 *
 * Responsibilities:
 *   - Extract packaged artifacts to target directories
 *   - Auto-detect format from file extension and magic bytes
 *   - Support strip-components for nested archives
 *   - Overwrite protection with conflict resolution
 *   - Validate extracted contents against manifest
 *   - Track extraction metadata and file inventory
 *
 * "Unpack with care — every layer reveals truth."
 */

import { Bot, Logger, AuditLedger } from '../../../core/definitions';

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface UnpackerInput {
  operation: 'UNPACK';
  artifactPath: string;
  targetPath: string;
  format?: 'tar.gz' | 'zip' | 'jar' | 'wheel' | 'npm' | 'docker' | 'raw' | 'deb' | 'rpm';
  stripComponents?: number;  // remove N leading path components
  overwrite?: boolean;
  extractPatterns?: string[];  // only extract matching files
  verifyIntegrity?: boolean;
}

export interface ExtractedFile {
  path: string;
  originalPath: string;
  size: number;
  type: 'file' | 'directory' | 'symlink';
  permissions: string;
  checksum?: string;
}

export interface ConflictEntry {
  path: string;
  action: 'skipped' | 'overwritten' | 'renamed';
  originalSize: number;
  replacementSize: number;
}

export interface UnpackResult {
  success: boolean;
  artifactPath: string;
  targetPath: string;
  format: string;
  extractedFiles: ExtractedFile[];
  skippedFiles: string[];
  conflicts: ConflictEntry[];
  totalExtractedSize: number;
  stripComponents: number;
  integrityVerified: boolean;
  duration: number;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Format Detection
// ─────────────────────────────────────────────────────────────────────────────

const FORMAT_SIGNATURES: Record<string, {
  extensions: string[];
  magicBytes: string;
  description: string;
}> = {
  'tar.gz': { extensions: ['.tar.gz', '.tgz'], magicBytes: '1f8b', description: 'Gzip-compressed tar archive' },
  'zip': { extensions: ['.zip'], magicBytes: '504b0304', description: 'ZIP archive' },
  'jar': { extensions: ['.jar'], magicBytes: '504b0304', description: 'Java ARchive' },
  'wheel': { extensions: ['.whl'], magicBytes: '504b0304', description: 'Python wheel package' },
  'npm': { extensions: ['.tgz'], magicBytes: '1f8b', description: 'npm package tarball' },
  'docker': { extensions: ['.tar'], magicBytes: 'ustar', description: 'Docker image layers' },
  'raw': { extensions: ['.bin', '.raw', '.img'], magicBytes: '', description: 'Raw binary data' },
  'deb': { extensions: ['.deb'], magicBytes: '213c6172', description: 'Debian package' },
  'rpm': { extensions: ['.rpm'], magicBytes: 'edabeedb', description: 'RPM package' },
};

// ─────────────────────────────────────────────────────────────────────────────
// UnpackerBot Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class UnpackerBot extends Bot {
  private readonly log: Logger;
  private readonly audit: AuditLedger;

  constructor() {
    const handler = async (input: UnpackerInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-ARTIFACTORY-UNPACKER',
      'Unpacker',
      handler,
      'Artifact extraction with format detection, overwrite protection, and integrity verification'
    );

    this.log = new Logger('UnpackerBot');
    this.audit = AuditLedger.getInstance();
  }

  private async process(input: UnpackerInput): Promise<UnpackResult> {
    switch (input.operation) {
      case 'UNPACK':
        return this.unpack(input);
      default:
        throw new Error(`UnpackerBot: Unknown operation "${(input as any).operation}"`);
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // UNPACK
  // ─────────────────────────────────────────────────────────────────────────

  private unpack(input: UnpackerInput): UnpackResult {
    const startTime = Date.now();
    const {
      artifactPath,
      targetPath,
      format,
      stripComponents,
      overwrite,
      extractPatterns,
      verifyIntegrity,
    } = input;

    // Detect format if not specified
    const detectedFormat = format ?? this.detectFormat(artifactPath);

    // Strip components count
    const strip = stripComponents ?? 0;

    // Simulate extraction
    const rawFiles = this.simulateExtraction(artifactPath, detectedFormat);

    // Apply strip components
    const strippedFiles = rawFiles.map((file) => {
      if (strip === 0) return file;
      const parts = file.path.split('/');
      const stripped = parts.slice(strip).join('/');
      return {
        ...file,
        originalPath: file.path,
        path: stripped || file.path,
      };
    });

    // Apply extract patterns
    const filteredFiles = extractPatterns && extractPatterns.length > 0
      ? strippedFiles.filter((file) =>
          extractPatterns.some((pattern) => {
            if (pattern.startsWith('*.')) {
              return file.path.endsWith(pattern.slice(1));
            }
            return file.path.includes(pattern);
          })
        )
      : strippedFiles;

    const skippedFiles = strippedFiles
      .filter((f) => !filteredFiles.includes(f))
      .map((f) => f.path);

    // Simulate conflicts
    const conflicts: ConflictEntry[] = [];
    const extractedFiles: ExtractedFile[] = [];
    let totalExtractedSize = 0;

    for (const file of filteredFiles) {
      // Simulate existing file conflict
      const hasConflict = Math.random() < 0.15; // 15% chance of conflict

      if (hasConflict) {
        if (overwrite) {
          conflicts.push({
            path: file.path,
            action: 'overwritten',
            originalSize: Math.floor(file.size * 0.8),
            replacementSize: file.size,
          });
          extractedFiles.push(file);
          totalExtractedSize += file.size;
        } else {
          conflicts.push({
            path: file.path,
            action: 'renamed',
            originalSize: file.size,
            replacementSize: file.size,
          });
          const renamedFile = {
            ...file,
            path: `${file.path}.new`,
          };
          extractedFiles.push(renamedFile);
          totalExtractedSize += file.size;
        }
      } else {
        extractedFiles.push(file);
        totalExtractedSize += file.size;
      }
    }

    // Integrity verification
    let integrityVerified = false;
    if (verifyIntegrity ?? false) {
      // Simulate integrity check — 95% pass rate
      integrityVerified = Math.random() < 0.95;
    }

    const duration = Date.now() - startTime;

    const result: UnpackResult = {
      success: true,
      artifactPath,
      targetPath,
      format: detectedFormat,
      extractedFiles,
      skippedFiles,
      conflicts,
      totalExtractedSize,
      stripComponents: strip,
      integrityVerified,
      duration,
      timestamp: Date.now(),
    };

    this.audit.append({
      actor: 'NID-ARTIFACTORY-UNPACKER',
      action: 'ARTIFACT_UNPACKED',
      entity: artifactPath,
      status: 'SUCCESS',
      meta: {
        format: detectedFormat,
        extractedFileCount: extractedFiles.length,
        skippedFileCount: skippedFiles.length,
        conflictCount: conflicts.length,
        totalExtractedSize,
        integrityVerified,
      },
    });

    this.log.info('Artifact unpacked', {
      artifactPath,
      format: detectedFormat,
      extractedFiles: extractedFiles.length,
      conflicts: conflicts.length,
      integrityVerified,
    });

    return result;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Helpers
  // ─────────────────────────────────────────────────────────────────────────

  private detectFormat(artifactPath: string): string {
    // Check by extension first
    for (const [format, config] of Object.entries(FORMAT_SIGNATURES)) {
      for (const ext of config.extensions) {
        if (artifactPath.endsWith(ext)) {
          return format;
        }
      }
    }

    // Fallback: try to detect from common patterns
    if (artifactPath.includes('.tar.gz') || artifactPath.includes('.tgz')) return 'tar.gz';
    if (artifactPath.includes('.whl')) return 'wheel';
    if (artifactPath.includes('.jar')) return 'jar';
    if (artifactPath.includes('.deb')) return 'deb';
    if (artifactPath.includes('.rpm')) return 'rpm';

    // Default to raw if undetectable
    this.log.warn('Could not detect format from path, defaulting to raw', { artifactPath });
    return 'raw';
  }

  private simulateExtraction(artifactPath: string, format: string): ExtractedFile[] {
    // Simulated file tree for extraction
    const baseFiles: ExtractedFile[] = [
      { path: 'src/index.ts', originalPath: 'src/index.ts', size: 1024, type: 'file', permissions: '644' },
      { path: 'src/main.ts', originalPath: 'src/main.ts', size: 2048, type: 'file', permissions: '644' },
      { path: 'src/config.ts', originalPath: 'src/config.ts', size: 512, type: 'file', permissions: '644' },
      { path: 'src/types.ts', originalPath: 'src/types.ts', size: 768, type: 'file', permissions: '644' },
      { path: 'src/utils/', originalPath: 'src/utils/', size: 0, type: 'directory', permissions: '755' },
      { path: 'src/utils/helpers.ts', originalPath: 'src/utils/helpers.ts', size: 1536, type: 'file', permissions: '644' },
      { path: 'src/utils/constants.ts', originalPath: 'src/utils/constants.ts', size: 256, type: 'file', permissions: '644' },
      { path: 'src/core/', originalPath: 'src/core/', size: 0, type: 'directory', permissions: '755' },
      { path: 'src/core/definitions.ts', originalPath: 'src/core/definitions.ts', size: 3072, type: 'file', permissions: '644' },
      { path: 'src/core/logger.ts', originalPath: 'src/core/logger.ts', size: 1280, type: 'file', permissions: '644' },
      { path: 'src/core/audit.ts', originalPath: 'src/core/audit.ts', size: 1792, type: 'file', permissions: '644' },
      { path: 'package.json', originalPath: 'package.json', size: 1024, type: 'file', permissions: '644' },
      { path: 'tsconfig.json', originalPath: 'tsconfig.json', size: 512, type: 'file', permissions: '644' },
      { path: 'README.md', originalPath: 'README.md', size: 4096, type: 'file', permissions: '644' },
      { path: 'LICENSE', originalPath: 'LICENSE', size: 1100, type: 'file', permissions: '644' },
    ];

    // Format-specific additional files
    if (format === 'jar') {
      baseFiles.push(
        { path: 'META-INF/', originalPath: 'META-INF/', size: 0, type: 'directory', permissions: '755' },
        { path: 'META-INF/MANIFEST.MF', originalPath: 'META-INF/MANIFEST.MF', size: 256, type: 'file', permissions: '644' },
      );
    } else if (format === 'npm') {
      baseFiles.push(
        { path: 'package/package.json', originalPath: 'package/package.json', size: 1024, type: 'file', permissions: '644' },
      );
    } else if (format === 'docker') {
      baseFiles.push(
        { path: 'manifest.json', originalPath: 'manifest.json', size: 2048, type: 'file', permissions: '644' },
        { path: 'config.json', originalPath: 'config.json', size: 4096, type: 'file', permissions: '644' },
        { path: 'layer1/', originalPath: 'layer1/', size: 0, type: 'directory', permissions: '755' },
        { path: 'layer1/VERSION', originalPath: 'layer1/VERSION', size: 3, type: 'file', permissions: '644' },
      );
    } else if (format === 'wheel') {
      baseFiles.push(
        { path: `${artifactPath.split('/').pop()?.replace('.whl', '')}.dist-info/`, originalPath: '', size: 0, type: 'directory', permissions: '755' },
        { path: `${artifactPath.split('/').pop()?.replace('.whl', '')}.dist-info/METADATA`, originalPath: '', size: 512, type: 'file', permissions: '644' },
        { path: `${artifactPath.split('/').pop()?.replace('.whl', '')}.dist-info/WHEEL`, originalPath: '', size: 128, type: 'file', permissions: '644' },
      );
    }

    // Add simulated checksums
    return baseFiles.map((file) => ({
      ...file,
      checksum: file.type === 'file'
        ? Buffer.from(`${file.path}:${file.size}`).toString('hex').slice(0, 64)
        : undefined,
    }));
  }
}
