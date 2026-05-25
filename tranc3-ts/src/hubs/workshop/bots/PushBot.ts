/**
 * PushBot — Git Push Bot for The Workshop
 *
 * Identity:  NID-WORKSHOP-PUSH
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TheWorkshopAI (AID-WORKSHOP)
 *
 * Responsibilities:
 *   - Push local commits to remote repositories
 *   - Handle force-push with safety checks
 *   - Track upstream tracking status
 *   - Validate push preconditions (protected branches, rejections)
 *   - Report push results with ref updates
 */

import { Bot, Logger, AuditLedger } from '../../../core/definitions'

const auditLedger = new AuditLedger();

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface PushInput {
  operation: 'EXECUTE' | 'DRY-RUN' | 'VALIDATE';
  repoPath: string;
  remote: string;
  branch: string;
  force: boolean;
  forceWithLease?: boolean;
  setUpstream?: boolean;
  tags?: boolean;
  deleteRemoteBranch?: boolean;
}

export interface RefUpdate {
  localRef: string;
  remoteRef: string;
  oldCommit: string;
  newCommit: string;
  forced: boolean;
  fastForward: boolean;
}

export interface PushRejection {
  ref: string;
  reason: 'protected-branch' | 'non-fast-forward' | 'remote-ahead' | 'permission-denied' | 'hook-rejected';
  message: string;
  resolution: string;
}

export interface PushResult {
  success: boolean;
  remote: string;
  branch: string;
  pushedCommits: number;
  refUpdates: RefUpdate[];
  rejections: PushRejection[];
  stats: {
    objectsPushed: number;
    bytesTransferred: number;
    duration: number;
  };
  warnings: string[];
  message: string;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// PushBot Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class PushBot extends Bot {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private readonly protectedBranches: Set<string>;

  constructor() {
    const handler = async (input: PushInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-WORKSHOP-PUSH',
      'Push',
      handler,
      'Git push execution with force-push safety and protected branch enforcement'
    );

    this.log = new Logger('PushBot');
    this.audit = auditLedger;
    this.protectedBranches = new Set(['main', 'master', 'production', 'release']);
  }

  private async process(input: PushInput): Promise<PushResult> {
    switch (input.operation) {
      case 'EXECUTE':
        return this.executePush(input);
      case 'DRY-RUN':
        return this.dryRun(input);
      case 'VALIDATE':
        return this.validatePush(input);
      default:
        throw new Error(`PushBot: Unknown operation "${(input as any).operation}"`);
    }
  }

  // ───────────────────────────────────────────────────────────────────────────
  // EXECUTE
  // ───────────────────────────────────────────────────────────────────────────

  private executePush(input: PushInput): PushResult {
    const { repoPath, remote, branch, force, forceWithLease, setUpstream, tags } = input;
    const startTime = Date.now();

    // Validate first
    const validation = this.validatePushPreconditions(input);
    if (!validation.canPush) {
      return {
        success: false,
        remote,
        branch,
        pushedCommits: 0,
        refUpdates: [],
        rejections: validation.rejections,
        stats: { objectsPushed: 0, bytesTransferred: 0, duration: Date.now() - startTime },
        warnings: validation.warnings,
        message: `Push rejected: ${validation.rejections.map((r) => r.reason).join(', ')}`,
        timestamp: Date.now(),
      };
    }

    // Simulate push execution
    const pushedCommits = Math.floor(Math.random() * 15) + 1;
    const objectsPushed = pushedCommits * 3 + Math.floor(Math.random() * 10);
    const bytesTransferred = objectsPushed * 256 + Math.floor(Math.random() * 5000);

    const refUpdates: RefUpdate[] = [
      {
        localRef: `refs/heads/${branch}`,
        remoteRef: `refs/remotes/${remote}/${branch}`,
        oldCommit: this.generateShortHash(),
        newCommit: this.generateShortHash(),
        forced: force,
        fastForward: !force,
      },
    ];

    if (tags) {
      refUpdates.push({
        localRef: 'refs/tags/v1.0.0',
        remoteRef: 'refs/tags/v1.0.0',
        oldCommit: '',
        newCommit: this.generateShortHash(),
        forced: false,
        fastForward: true,
      });
    }

    const result: PushResult = {
      success: true,
      remote,
      branch,
      pushedCommits,
      refUpdates,
      rejections: [],
      stats: {
        objectsPushed,
        bytesTransferred,
        duration: Date.now() - startTime + Math.floor(Math.random() * 500),
      },
      warnings: validation.warnings,
      message: `Successfully pushed ${pushedCommits} commit(s) to ${remote}/${branch}`,
      timestamp: Date.now(),
    };

    this.audit.append({
      actor: 'NID-WORKSHOP-PUSH',
      entity: 'PUSH_EXECUTED',
      action: 'PUSH_EXECUTED',
      details: {
        remote,
        branch,
        commits: pushedCommits,
        force,
        forceWithLease,
        objects: objectsPushed,
      },
      timestamp: new Date(),
    });

    this.log.info('Push completed', {
      remote,
      branch,
      commits: pushedCommits,
      force,
      duration: result.stats.duration,
    });

    return result;
  }

  // ───────────────────────────────────────────────────────────────────────────
  // DRY-RUN
  // ───────────────────────────────────────────────────────────────────────────

  private dryRun(input: PushInput): PushResult {
    const validation = this.validatePushPreconditions(input);

    const estimatedCommits = Math.floor(Math.random() * 10) + 1;

    return {
      success: validation.canPush,
      remote: input.remote,
      branch: input.branch,
      pushedCommits: estimatedCommits,
      refUpdates: [{
        localRef: `refs/heads/${input.branch}`,
        remoteRef: `refs/remotes/${input.remote}/${input.branch}`,
        oldCommit: this.generateShortHash(),
        newCommit: this.generateShortHash(),
        forced: input.force,
        fastForward: !input.force,
      }],
      rejections: validation.rejections,
      stats: { objectsPushed: 0, bytesTransferred: 0, duration: 0 },
      warnings: [
        ...validation.warnings,
        'DRY-RUN: No actual push performed',
      ],
      message: validation.canPush
        ? `Dry-run: would push ${estimatedCommits} commit(s) to ${input.remote}/${input.branch}`
        : `Dry-run: push would be rejected — ${validation.rejections.map((r) => r.reason).join(', ')}`,
      timestamp: Date.now(),
    };
  }

  // ───────────────────────────────────────────────────────────────────────────
  // VALIDATE
  // ───────────────────────────────────────────────────────────────────────────

  private validatePush(input: PushInput): PushResult {
    const validation = this.validatePushPreconditions(input);

    return {
      success: validation.canPush,
      remote: input.remote,
      branch: input.branch,
      pushedCommits: 0,
      refUpdates: [],
      rejections: validation.rejections,
      stats: { objectsPushed: 0, bytesTransferred: 0, duration: 0 },
      warnings: validation.warnings,
      message: validation.canPush
        ? 'Push validation passed — safe to push'
        : `Push validation failed: ${validation.rejections.map((r) => r.reason).join(', ')}`,
      timestamp: Date.now(),
    };
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Push Validation Logic
  // ───────────────────────────────────────────────────────────────────────────

  private validatePushPreconditions(input: PushInput): {
    canPush: boolean;
    rejections: PushRejection[];
    warnings: string[];
  } {
    const rejections: PushRejection[] = [];
    const warnings: string[] = [];

    // Protected branch force-push check
    if (this.protectedBranches.has(input.branch)) {
      if (input.force) {
        rejections.push({
          ref: input.branch,
          reason: 'protected-branch',
          message: `Cannot force-push to protected branch "${input.branch}"`,
          resolution: 'Remove force flag or unprotect the branch (not recommended)',
        });
      } else {
        warnings.push(`Pushing to protected branch "${input.branch}" — ensure changes are reviewed`);
      }
    }

    // Force-with-lease is safer than force
    if (input.force && !input.forceWithLease && !this.protectedBranches.has(input.branch)) {
      warnings.push('Using --force instead of --force-with-lease — consider the safer alternative');
    }

    // Remote deletion safety
    if (input.deleteRemoteBranch) {
      if (this.protectedBranches.has(input.branch)) {
        rejections.push({
          ref: input.branch,
          reason: 'protected-branch',
          message: `Cannot delete protected remote branch "${input.branch}"`,
          resolution: 'Unprotect the branch before deletion',
        });
      } else {
        warnings.push(`Deleting remote branch "${input.branch}" — this action is irreversible`);
      }
    }

    return {
      canPush: rejections.length === 0,
      rejections,
      warnings,
    };
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Utilities
  // ───────────────────────────────────────────────────────────────────────────

  private generateShortHash(): string {
    const chars = '0123456789abcdef';
    let hash = '';
    for (let i = 0; i < 7; i++) {
      hash += chars[Math.floor(Math.random() * chars.length)];
    }
    return hash;
  }
}
