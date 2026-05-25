/**
 * ChecksumBot — Artifact Integrity Verification Bot for The Artifactory
 *
 * Identity:  NID-ARTIFACTORY-CHECKSUM
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TheArtifactoryAI (AID-ARTIFACTORY)
 *
 * Responsibilities:
 *   - Generate checksums using multiple algorithms (sha256, sha512, md5, blake2b)
 *   - Verify artifact integrity against expected checksums
 *   - Produce integrity reports with detailed pass/fail analysis
 *   - Support batch verification of multiple artifacts
 *   - Track verification history and failure patterns
 *
 * "Trust, but verify. Then verify again."
 */

import { Bot, Logger, AuditLedger } from '../../../core/definitions';

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface ChecksumInput {
  operation: 'VERIFY';
  path: string;
  algorithm?: 'sha256' | 'sha512' | 'md5' | 'blake2b';
  expectedChecksum?: string;
  generateAll?: boolean;  // generate checksums in all algorithms
}

export interface ChecksumEntry {
  algorithm: string;
  hash: string;
  verified: boolean;
  expectedHash?: string;
  match?: boolean;
}

export interface IntegrityDetail {
  checksumValid: boolean;
  sizeValid: boolean;
  metadataIntact: boolean;
  signatureValid: boolean;
  overallIntegrity: 'intact' | 'degraded' | 'corrupted';
  issues: string[];
}

export interface VerifyResult {
  success: boolean;
  path: string;
  checksums: ChecksumEntry[];
  integrity: IntegrityDetail;
  fileSize: number;
  verifiedAt: number;
  verificationDuration: number;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Algorithm Configuration
// ─────────────────────────────────────────────────────────────────────────────

const ALGORITHM_CONFIG: Record<string, {
  hashLength: number;
  description: string;
  securityLevel: 'deprecated' | 'acceptable' | 'recommended' | 'strong';
  speed: 'fast' | 'moderate' | 'slow';
}> = {
  sha256: {
    hashLength: 64,
    description: 'SHA-256 — NIST standard, widely adopted',
    securityLevel: 'recommended',
    speed: 'moderate',
  },
  sha512: {
    hashLength: 128,
    description: 'SHA-512 — NIST standard, high security',
    securityLevel: 'strong',
    speed: 'moderate',
  },
  md5: {
    hashLength: 32,
    description: 'MD5 — Legacy, collision-vulnerable, use only for compatibility',
    securityLevel: 'deprecated',
    speed: 'fast',
  },
  blake2b: {
    hashLength: 128,
    description: 'BLAKE2b — Modern, faster than SHA-3, highly secure',
    securityLevel: 'strong',
    speed: 'fast',
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// ChecksumBot Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class ChecksumBot extends Bot {
  private readonly log: Logger;
  private readonly audit: AuditLedger;

  constructor() {
    const handler = async (input: ChecksumInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-ARTIFACTORY-CHECKSUM',
      'Checksum',
      handler,
      'Artifact integrity verification with multi-algorithm checksum generation and comparison'
    );

    this.log = new Logger('ChecksumBot');
    this.audit = AuditLedger.getInstance();
  }

  private async process(input: ChecksumInput): Promise<VerifyResult> {
    switch (input.operation) {
      case 'VERIFY':
        return this.verify(input);
      default:
        throw new Error(`ChecksumBot: Unknown operation "${(input as any).operation}"`);
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // VERIFY
  // ─────────────────────────────────────────────────────────────────────────

  private verify(input: ChecksumInput): VerifyResult {
    const startTime = Date.now();
    const { path, algorithm, expectedChecksum, generateAll } = input;

    // Determine which algorithms to use
    const primaryAlgorithm = algorithm ?? 'sha256';
    const algorithms = generateAll
      ? Object.keys(ALGORITHM_CONFIG)
      : [primaryAlgorithm];

    // Generate checksums
    const checksums: ChecksumEntry[] = algorithms.map((algo) => {
      const config = ALGORITHM_CONFIG[algo];
      if (!config) {
        return {
          algorithm: algo,
          hash: 'unsupported',
          verified: false,
        };
      }

      const generatedHash = this.simulateHash(path, algo, config.hashLength);

      // If this is the primary algorithm and we have an expected checksum, verify
      if (algo === primaryAlgorithm && expectedChecksum) {
        const match = generatedHash === expectedChecksum;
        return {
          algorithm: algo,
          hash: generatedHash,
          verified: true,
          expectedHash: expectedChecksum,
          match,
        };
      }

      return {
        algorithm: algo,
        hash: generatedHash,
        verified: false,
      };
    });

    // Determine overall checksum validity
    const primaryChecksum = checksums.find((c) => c.algorithm === primaryAlgorithm);
    const checksumValid = primaryChecksum?.match ?? true; // If no expected, assume valid

    // Simulated file size
    const fileSize = this.simulateFileSize(path);

    // Integrity assessment
    const integrity = this.assessIntegrity(checksumValid, path, checksums);

    // Log deprecated algorithm usage
    const deprecatedAlgos = checksums.filter(
      (c) => ALGORITHM_CONFIG[c.algorithm]?.securityLevel === 'deprecated'
    );
    if (deprecatedAlgos.length > 0) {
      this.log.warn('Deprecated algorithm detected in verification', {
        algorithms: deprecatedAlgos.map((c) => c.algorithm),
        recommendation: 'Use sha256 or blake2b for production integrity checks',
      });
    }

    const verificationDuration = Date.now() - startTime;

    const result: VerifyResult = {
      success: checksumValid && integrity.overallIntegrity !== 'corrupted',
      path,
      checksums,
      integrity,
      fileSize,
      verifiedAt: Date.now(),
      verificationDuration,
      timestamp: Date.now(),
    };

    this.audit.append({
      actor: 'NID-ARTIFACTORY-CHECKSUM',
      action: 'ARTIFACT_VERIFIED',
      entity: path,
      status: checksumValid ? 'SUCCESS' : 'FAILURE',
      meta: {
        algorithm: primaryAlgorithm,
        checksumValid,
        overallIntegrity: integrity.overallIntegrity,
        issues: integrity.issues.length,
        verificationDuration,
      },
    });

    this.log.info('Artifact verified', {
      path,
      algorithm: primaryAlgorithm,
      valid: checksumValid,
      integrity: integrity.overallIntegrity,
    });

    return result;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Helpers
  // ─────────────────────────────────────────────────────────────────────────

  private simulateHash(path: string, algorithm: string, hashLength: number): string {
    // Deterministic simulated hash based on path and algorithm
    const seed = `${algorithm}:${path}:${path.length}`;
    let hash = '';
    for (let i = 0; i < hashLength; i++) {
      const charCode = (seed.charCodeAt(i % seed.length) + i * 7) % 16;
      hash += charCode.toString(16);
    }
    return hash;
  }

  private simulateFileSize(path: string): number {
    // Deterministic file size based on path
    let size = 0;
    for (let i = 0; i < path.length; i++) {
      size = (size * 31 + path.charCodeAt(i)) & 0x7FFFFFFF;
    }
    return Math.floor(size / 1000) + 1024; // Ensure minimum size
  }

  private assessIntegrity(
    checksumValid: boolean,
    path: string,
    checksums: ChecksumEntry[]
  ): IntegrityDetail {
    const issues: string[] = [];

    // Check checksum validity
    if (!checksumValid) {
      issues.push('Checksum mismatch — artifact may be corrupted or tampered with');
    }

    // Simulate metadata check (98% pass rate)
    const metadataIntact = Math.random() < 0.98;
    if (!metadataIntact) {
      issues.push('Metadata integrity check failed — metadata may be incomplete or damaged');
    }

    // Simulate signature check (99.5% pass rate)
    const signatureValid = Math.random() < 0.995;
    if (!signatureValid) {
      issues.push('Signature verification failed — artifact provenance cannot be confirmed');
    }

    // Size is always considered valid for simulation
    const sizeValid = true;

    // Determine overall integrity
    let overallIntegrity: IntegrityDetail['overallIntegrity'];
    if (!checksumValid) {
      overallIntegrity = 'corrupted';
    } else if (!metadataIntact || !signatureValid) {
      overallIntegrity = 'degraded';
    } else {
      overallIntegrity = 'intact';
    }

    // Add security recommendations for weak algorithms
    const weakAlgos = checksums.filter(
      (c) => ALGORITHM_CONFIG[c.algorithm]?.securityLevel === 'deprecated'
    );
    if (weakAlgos.length > 0) {
      issues.push(
        `Using deprecated algorithm(s): ${weakAlgos.map((c) => c.algorithm).join(', ')} — upgrade to sha256 or blake2b`
      );
    }

    return {
      checksumValid,
      sizeValid,
      metadataIntact,
      signatureValid,
      overallIntegrity,
      issues,
    };
  }
}
