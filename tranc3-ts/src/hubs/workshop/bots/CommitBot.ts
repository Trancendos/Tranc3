/**
 * CommitBot — Git Commit Bot for The Workshop
 *
 * Identity:  NID-WORKSHOP-COMMIT
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TheWorkshopAI (AID-WORKSHOP)
 *
 * Responsibilities:
 *   - Create commits with validated messages
 *   - Stage files selectively or in bulk
 *   - Validate commit message conventions
 *   - Generate commit metadata (hash, stats, trailers)
 *   - Amend previous commits when requested
 */

import { Bot, Logger, AuditLedger } from '../../../core/definitions';

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface CommitInput {
  operation: 'CREATE' | 'AMEND' | 'VALIDATE';
  repoPath: string;
  message: string;
  files: string[];
  author: string;
  email: string;
  amendHash?: string;
  trailers?: Array<{ key: string; value: string }>;
  convention?: 'conventional' | 'angular' | 'none';
  allowEmpty?: boolean;
  gpgSign?: boolean;
}

export interface FileChange {
  path: string;
  status: 'added' | 'modified' | 'deleted' | 'renamed';
  additions: number;
  deletions: number;
  binary: boolean;
  oldPath?: string;
}

export interface CommitValidation {
  valid: boolean;
  errors: string[];
  warnings: string[];
  convention?: {
    type: string;
    scope?: string;
    description: string;
    breakingChange?: boolean;
    body?: string;
    footers?: Record<string, string>;
  };
}

export interface CommitResult {
  success: boolean;
  hash: string;
  shortHash: string;
  message: string;
  author: string;
  email: string;
  timestamp: number;
  filesChanged: FileChange[];
  stats: {
    totalFiles: number;
    additions: number;
    deletions: number;
    binaryFiles: number;
  };
  validation?: CommitValidation;
  amended: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// CommitBot Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class CommitBot extends Bot {
  private readonly log: Logger;
  private readonly audit: AuditLedger;

  constructor() {
    const handler = async (input: CommitInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-WORKSHOP-COMMIT',
      'Commit',
      handler,
      'Git commit creation with message validation and conventional commit support'
    );

    this.log = new Logger('CommitBot');
    this.audit = AuditLedger.getInstance();
  }

  private async process(input: CommitInput): Promise<CommitResult> {
    switch (input.operation) {
      case 'CREATE':
        return this.createCommit(input);
      case 'AMEND':
        return this.amendCommit(input);
      case 'VALIDATE':
        return this.validateCommit(input);
      default:
        throw new Error(`CommitBot: Unknown operation "${(input as any).operation}"`);
    }
  }

  // ───────────────────────────────────────────────────────────────────────────
  // CREATE
  // ───────────────────────────────────────────────────────────────────────────

  private createCommit(input: CommitInput): CommitResult {
    const { repoPath, message, files, author, email, convention, trailers, allowEmpty, gpgSign } = input;

    // Validate commit message
    const validation = this.validateMessage(message, convention ?? 'none');

    if (!validation.valid) {
      return {
        success: false,
        hash: '',
        shortHash: '',
        message,
        author,
        email,
        timestamp: Date.now(),
        filesChanged: [],
        stats: { totalFiles: 0, additions: 0, deletions: 0, binaryFiles: 0 },
        validation,
        amended: false,
      };
    }

    // Check for empty commit
    if (files.length === 0 && !allowEmpty) {
      return {
        success: false,
        hash: '',
        shortHash: '',
        message,
        author,
        email,
        timestamp: Date.now(),
        filesChanged: [],
        stats: { totalFiles: 0, additions: 0, deletions: 0, binaryFiles: 0 },
        validation: {
          valid: false,
          errors: ['No files staged for commit. Use allowEmpty for empty commits.'],
          warnings: [],
        },
        amended: false,
      };
    }

    // Build file changes
    const fileChanges = this.simulateFileChanges(files);

    // Generate commit hash
    const hash = this.generateHash();

    // Build full message with trailers
    let fullMessage = message;
    if (trailers && trailers.length > 0) {
      fullMessage += '\n\n';
      for (const trailer of trailers) {
        fullMessage += `${trailer.key}: ${trailer.value}\n`;
      }
    }

    const result: CommitResult = {
      success: true,
      hash,
      shortHash: hash.substring(0, 7),
      message: fullMessage,
      author,
      email,
      timestamp: Date.now(),
      filesChanged: fileChanges,
      stats: {
        totalFiles: fileChanges.length,
        additions: fileChanges.reduce((sum, f) => sum + f.additions, 0),
        deletions: fileChanges.reduce((sum, f) => sum + f.deletions, 0),
        binaryFiles: fileChanges.filter((f) => f.binary).length,
      },
      validation,
      amended: false,
    };

    this.audit.append({
      botId: 'NID-WORKSHOP-COMMIT',
      action: 'COMMIT_CREATE',
      details: { hash, message: message.substring(0, 80), files: files.length, author },
      timestamp: Date.now(),
    });

    this.log.info('Commit created', {
      hash: result.shortHash,
      files: result.stats.totalFiles,
      additions: result.stats.additions,
      deletions: result.stats.deletions,
    });

    return result;
  }

  // ───────────────────────────────────────────────────────────────────────────
  // AMEND
  // ───────────────────────────────────────────────────────────────────────────

  private amendCommit(input: CommitInput): CommitResult {
    const { amendHash, message, files, author, email } = input;

    if (!amendHash) {
      return {
        success: false,
        hash: '',
        shortHash: '',
        message,
        author,
        email,
        timestamp: Date.now(),
        filesChanged: [],
        stats: { totalFiles: 0, additions: 0, deletions: 0, binaryFiles: 0 },
        amended: false,
      };
    }

    // Validate new message
    const validation = this.validateMessage(message, input.convention ?? 'none');

    // Build amended commit
    const hash = this.generateHash();
    const fileChanges = this.simulateFileChanges(files);

    const result: CommitResult = {
      success: true,
      hash,
      shortHash: hash.substring(0, 7),
      message,
      author,
      email,
      timestamp: Date.now(),
      filesChanged: fileChanges,
      stats: {
        totalFiles: fileChanges.length,
        additions: fileChanges.reduce((sum, f) => sum + f.additions, 0),
        deletions: fileChanges.reduce((sum, f) => sum + f.deletions, 0),
        binaryFiles: fileChanges.filter((f) => f.binary).length,
      },
      validation,
      amended: true,
    };

    this.log.info('Commit amended', {
      originalHash: amendHash.substring(0, 7),
      newHash: result.shortHash,
    });

    return result;
  }

  // ───────────────────────────────────────────────────────────────────────────
  // VALIDATE
  // ───────────────────────────────────────────────────────────────────────────

  private validateCommit(input: CommitInput): CommitResult {
    const validation = this.validateMessage(input.message, input.convention ?? 'none');

    return {
      success: validation.valid,
      hash: '',
      shortHash: '',
      message: input.message,
      author: input.author,
      email: input.email,
      timestamp: Date.now(),
      filesChanged: [],
      stats: { totalFiles: 0, additions: 0, deletions: 0, binaryFiles: 0 },
      validation,
      amended: false,
    };
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Message Validation
  // ───────────────────────────────────────────────────────────────────────────

  private validateMessage(message: string, convention: string): CommitValidation {
    const errors: string[] = [];
    const warnings: string[] = [];

    // Basic checks
    if (!message || message.trim().length === 0) {
      errors.push('Commit message cannot be empty');
      return { valid: false, errors, warnings };
    }

    const lines = message.split('\n');
    const subjectLine = lines[0];

    // Subject line length
    if (subjectLine.length > 72) {
      errors.push(`Subject line is ${subjectLine.length} characters — keep under 72`);
    } else if (subjectLine.length > 50) {
      warnings.push(`Subject line is ${subjectLine.length} characters — consider keeping under 50`);
    }

    // Subject line should not end with period
    if (subjectLine.endsWith('.')) {
      warnings.push('Subject line should not end with a period');
    }

    // Blank line between subject and body
    if (lines.length > 1 && lines[1].trim() !== '') {
      errors.push('Separate subject from body with a blank line');
    }

    // Body line length
    for (let i = 2; i < lines.length; i++) {
      if (lines[i].length > 100) {
        warnings.push(`Body line ${i + 1} exceeds 100 characters`);
        break; // Only warn once
      }
    }

    // Convention-specific validation
    let conventionResult: CommitValidation['convention'];

    if (convention === 'conventional' || convention === 'angular') {
      conventionResult = this.parseConventionalCommit(subjectLine);
      if (!conventionResult) {
        const validTypes = convention === 'angular'
          ? 'build, ci, docs, feat, fix, perf, refactor, style, test'
          : 'feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert';
        errors.push(`Commit message does not follow conventional format: type(scope)!: description`);
        errors.push(`Valid types: ${validTypes}`);
      }
    }

    return {
      valid: errors.length === 0,
      errors,
      warnings,
      convention: conventionResult,
    };
  }

  private parseConventionalCommit(subjectLine: string): CommitValidation['convention'] {
    // Format: type(scope)!: description
    const match = subjectLine.match(/^(\w+)(?:\(([^)]+)\))?(!)?:\s+(.+)$/);
    if (!match) return undefined;

    const validTypes = new Set([
      'feat', 'fix', 'docs', 'style', 'refactor', 'perf', 'test',
      'build', 'ci', 'chore', 'revert', 'wip', 'bump',
    ]);

    const type = match[1].toLowerCase();
    if (!validTypes.has(type)) return undefined;

    return {
      type,
      scope: match[2] || undefined,
      description: match[4],
      breakingChange: match[3] === '!' || match[4].toLowerCase().includes('breaking change'),
    };
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Utilities
  // ───────────────────────────────────────────────────────────────────────────

  private generateHash(): string {
    const chars = '0123456789abcdef';
    let hash = '';
    for (let i = 0; i < 40; i++) {
      hash += chars[Math.floor(Math.random() * chars.length)];
    }
    return hash;
  }

  private simulateFileChanges(files: string[]): FileChange[] {
    return files.map((file) => {
      const isBinary = /\.(png|jpg|jpeg|gif|webp|ico|woff|woff2|ttf|eot|mp4|mp3|zip|tar|gz)$/i.test(file);
      const statuses: FileChange['status'][] = ['added', 'modified', 'modified', 'modified', 'deleted'];

      return {
        path: file,
        status: statuses[Math.floor(Math.random() * statuses.length)],
        additions: isBinary ? 0 : Math.floor(Math.random() * 30) + 1,
        deletions: isBinary ? 0 : Math.floor(Math.random() * 15),
        binary: isBinary,
      };
    });
  }
}
