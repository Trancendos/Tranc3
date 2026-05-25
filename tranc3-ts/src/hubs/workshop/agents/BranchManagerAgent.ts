/**
 * BranchManagerAgent — Branch Lifecycle Management Agent for The Workshop
 *
 * Identity:  SID-WORKSHOP-BRANCHMANAGER
 * Tier:      4 (Autonomous Microservice)
 * Parent:    TheWorkshopAI (AID-WORKSHOP)
 *
 * Responsibilities:
 *   - Create, delete, list, and switch branches
 *   - Protect critical branches from force-push or deletion
 *   - Validate branch naming conventions
 *   - Track branch relationships and merge status
 *   - Enforce branching strategy rules (GitFlow, trunk-based, etc.)
 */

import { Agent, Logger, AuditLedger } from '../../../core/definitions'

const auditLedger = new AuditLedger();

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface BranchManagerInput {
  repository?: {
    id: string;
    name: string;
    path: string;
    currentBranch: string;
    branches: Array<{
      name: string;
      type: 'local' | 'remote' | 'tag';
      headCommit: string;
      upstream?: string;
      isMerged: boolean;
      isProtected: boolean;
      createdAt: number;
      author: string;
    }>;
    status: string;
  };
  operation: 'create' | 'delete' | 'list' | 'switch' | 'protect' | 'unprotect' | 'rename' | 'validate';
  branchName?: string;
  startPoint?: string;
  targetBranch?: string;
  newName?: string;
  author?: string;
  strategy?: 'gitflow' | 'trunk' | 'github-flow' | 'none';
}

export interface BranchInfo {
  name: string;
  type: 'local' | 'remote' | 'tag';
  headCommit: string;
  upstream?: string;
  isMerged: boolean;
  isProtected: boolean;
  createdAt: number;
  author: string;
  lastCommitMessage?: string;
  ahead?: number;
  behind?: number;
}

export interface BranchValidation {
  valid: boolean;
  errors: string[];
  warnings: string[];
  suggestion?: string;
}

export interface BranchManagerResult {
  success: boolean;
  operation: string;
  branch?: BranchInfo;
  branches?: BranchInfo[];
  validation?: BranchValidation;
  message: string;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// BranchManagerAgent Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class BranchManagerAgent extends Agent {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private readonly protectedBranches: Set<string>;
  private readonly branchHistory: Map<string, Array<{
    action: string;
    branch: string;
    author: string;
    timestamp: number;
  }>>;

  constructor() {
    super(
      'SID-WORKSHOP-BRANCHMANAGER',
      'BranchManager',
      'Branch lifecycle management with protection and naming validation'
    );

    this.log = new Logger('BranchManagerAgent');
    this.audit = auditLedger;
    this.protectedBranches = new Set(['main', 'master', 'develop', 'release', 'production', 'staging']);
    this.branchHistory = new Map();
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Agent Lifecycle: Perceive → Decide → Act
  // ───────────────────────────────────────────────────────────────────────────

  public async perceive(input: BranchManagerInput): Promise<BranchManagerInput> {
    this.log.info('Perceiving branch operation', { operation: input.operation });

    // Enrich input with current state context
    if (input.repository) {
      this.log.debug('Repository context', {
        repo: input.repository.name,
        currentBranch: input.repository.currentBranch,
        branchCount: input.repository.branches.length,
      });
    }

    return input;
  }

  public async decide(input: BranchManagerInput): Promise<string> {
    this.log.info('Deciding branch action', { operation: input.operation });

    switch (input.operation) {
      case 'create':
        return 'createBranch';
      case 'delete':
        return 'deleteBranch';
      case 'list':
        return 'listBranches';
      case 'switch':
        return 'switchBranch';
      case 'protect':
        return 'protectBranch';
      case 'unprotect':
        return 'unprotectBranch';
      case 'rename':
        return 'renameBranch';
      case 'validate':
        return 'validateBranch';
      default:
        return 'unknown';
    }
  }

  public async act(input: BranchManagerInput, decision: string): Promise<BranchManagerResult> {
    this.log.info('Acting on branch decision', { decision });

    switch (decision) {
      case 'createBranch':
        return this.createBranch(input);
      case 'deleteBranch':
        return this.deleteBranch(input);
      case 'listBranches':
        return this.listBranches(input);
      case 'switchBranch':
        return this.switchBranch(input);
      case 'protectBranch':
        return this.protectBranch(input);
      case 'unprotectBranch':
        return this.unprotectBranch(input);
      case 'renameBranch':
        return this.renameBranch(input);
      case 'validateBranch':
        return this.validateBranch(input);
      default:
        return {
          success: false,
          operation: input.operation,
          message: `Unknown operation: ${input.operation}`,
          timestamp: Date.now(),
        };
    }
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Branch Operations
  // ───────────────────────────────────────────────────────────────────────────

  private createBranch(input: BranchManagerInput): BranchManagerResult {
    const branchName = input.branchName ?? '';
    const startPoint = input.startPoint ?? 'HEAD';
    const author = input.author ?? 'unknown';

    // Validate branch name
    const validation = this.validateBranchName(branchName, input.strategy);
    if (!validation.valid) {
      return {
        success: false,
        operation: 'create',
        validation,
        message: `Branch name validation failed: ${validation.errors.join(', ')}`,
        timestamp: Date.now(),
      };
    }

    // Check if branch already exists
    if (input.repository) {
      const exists = input.repository.branches.some(
        (b) => b.name === branchName && b.type === 'local'
      );
      if (exists) {
        return {
          success: false,
          operation: 'create',
          message: `Branch "${branchName}" already exists`,
          timestamp: Date.now(),
        };
      }
    }

    // Create the branch info
    const branch: BranchInfo = {
      name: branchName,
      type: 'local',
      headCommit: startPoint === 'HEAD' ? 'current' : startPoint,
      isMerged: false,
      isProtected: false,
      createdAt: Date.now(),
      author,
    };

    // Record in history
    this.recordHistory(input.repository?.name ?? 'unknown', 'create', branchName, author);

    this.audit.append({ actor: this.id,
      entity: 'BRANCH_CREATE',
      action: 'BRANCH_CREATE',
      details: { branchName, startPoint, author },
      timestamp: new Date(),
    });

    this.log.info('Branch created', { branchName, startPoint, author });

    return {
      success: true,
      operation: 'create',
      branch,
      message: `Branch "${branchName}" created from ${startPoint}`,
      timestamp: Date.now(),
    };
  }

  private deleteBranch(input: BranchManagerInput): BranchManagerResult {
    const branchName = input.branchName ?? '';
    const author = input.author ?? 'unknown';

    // Check protection
    if (this.protectedBranches.has(branchName)) {
      return {
        success: false,
        operation: 'delete',
        message: `Cannot delete protected branch "${branchName}"`,
        timestamp: Date.now(),
      };
    }

    // Cannot delete current branch
    if (input.repository && input.repository.currentBranch === branchName) {
      return {
        success: false,
        operation: 'delete',
        message: `Cannot delete the currently checked-out branch "${branchName}"`,
        timestamp: Date.now(),
      };
    }

    // Check if merged
    if (input.repository) {
      const branch = input.repository.branches.find((b) => b.name === branchName);
      if (branch && !branch.isMerged) {
        return {
          success: false,
          operation: 'delete',
          message: `Branch "${branchName}" is not fully merged. Use force delete if intentional.`,
          timestamp: Date.now(),
        };
      }
    }

    this.recordHistory(input.repository?.name ?? 'unknown', 'delete', branchName, author);

    this.audit.append({ actor: this.id,
      entity: 'BRANCH_DELETE',
      action: 'BRANCH_DELETE',
      details: { branchName, author },
      timestamp: new Date(),
    });

    this.log.info('Branch deleted', { branchName, author });

    return {
      success: true,
      operation: 'delete',
      message: `Branch "${branchName}" deleted`,
      timestamp: Date.now(),
    };
  }

  private listBranches(input: BranchManagerInput): BranchManagerResult {
    const branches: BranchInfo[] = [];

    if (input.repository) {
      for (const b of input.repository.branches) {
        branches.push({
          name: b.name,
          type: b.type,
          headCommit: b.headCommit,
          upstream: b.upstream,
          isMerged: b.isMerged,
          isProtected: b.isProtected || this.protectedBranches.has(b.name),
          createdAt: b.createdAt,
          author: b.author,
        });
      }
    }

    // Sort: protected first, then by name
    branches.sort((a, b) => {
      if (a.isProtected !== b.isProtected) return a.isProtected ? -1 : 1;
      return a.name.localeCompare(b.name);
    });

    return {
      success: true,
      operation: 'list',
      branches,
      message: `${branches.length} branch(es) found`,
      timestamp: Date.now(),
    };
  }

  private switchBranch(input: BranchManagerInput): BranchManagerResult {
    const branchName = input.branchName ?? '';
    const author = input.author ?? 'unknown';

    // Verify branch exists
    if (input.repository) {
      const exists = input.repository.branches.some(
        (b) => b.name === branchName && b.type === 'local'
      );
      if (!exists) {
        return {
          success: false,
          operation: 'switch',
          message: `Branch "${branchName}" does not exist locally`,
          timestamp: Date.now(),
        };
      }

      // Cannot switch if working tree is dirty
      if (input.repository.status === 'dirty') {
        return {
          success: false,
          operation: 'switch',
          message: 'Cannot switch branches with uncommitted changes. Stash or commit first.',
          timestamp: Date.now(),
        };
      }
    }

    this.recordHistory(input.repository?.name ?? 'unknown', 'switch', branchName, author);

    this.log.info('Switched to branch', { branchName, author });

    return {
      success: true,
      operation: 'switch',
      branch: {
        name: branchName,
        type: 'local',
        headCommit: 'current',
        isMerged: false,
        isProtected: this.protectedBranches.has(branchName),
        createdAt: Date.now(),
        author,
      },
      message: `Switched to branch "${branchName}"`,
      timestamp: Date.now(),
    };
  }

  private protectBranch(input: BranchManagerInput): BranchManagerResult {
    const branchName = input.branchName ?? '';

    this.protectedBranches.add(branchName);

    this.audit.append({ actor: this.id,
      entity: 'BRANCH_PROTECT',
      action: 'BRANCH_PROTECT',
      details: { branchName },
      timestamp: new Date(),
    });

    this.log.info('Branch protected', { branchName });

    return {
      success: true,
      operation: 'protect',
      message: `Branch "${branchName}" is now protected`,
      timestamp: Date.now(),
    };
  }

  private unprotectBranch(input: BranchManagerInput): BranchManagerResult {
    const branchName = input.branchName ?? '';

    // Never unprotect main/master
    if (branchName === 'main' || branchName === 'master') {
      return {
        success: false,
        operation: 'unprotect',
        message: `Cannot unprotect the primary branch "${branchName}"`,
        timestamp: Date.now(),
      };
    }

    this.protectedBranches.delete(branchName);

    this.log.info('Branch unprotected', { branchName });

    return {
      success: true,
      operation: 'unprotect',
      message: `Branch "${branchName}" is no longer protected`,
      timestamp: Date.now(),
    };
  }

  private renameBranch(input: BranchManagerInput): BranchManagerResult {
    const oldName = input.branchName ?? '';
    const newName = input.newName ?? '';
    const author = input.author ?? 'unknown';

    // Validate new name
    const validation = this.validateBranchName(newName, input.strategy);
    if (!validation.valid) {
      return {
        success: false,
        operation: 'rename',
        validation,
        message: `New branch name validation failed: ${validation.errors.join(', ')}`,
        timestamp: Date.now(),
      };
    }

    // Cannot rename protected branches
    if (this.protectedBranches.has(oldName)) {
      return {
        success: false,
        operation: 'rename',
        message: `Cannot rename protected branch "${oldName}"`,
        timestamp: Date.now(),
      };
    }

    this.recordHistory(input.repository?.name ?? 'unknown', 'rename', `${oldName}→${newName}`, author);

    this.log.info('Branch renamed', { oldName, newName, author });

    return {
      success: true,
      operation: 'rename',
      branch: {
        name: newName,
        type: 'local',
        headCommit: 'current',
        isMerged: false,
        isProtected: false,
        createdAt: Date.now(),
        author,
      },
      message: `Branch renamed from "${oldName}" to "${newName}"`,
      timestamp: Date.now(),
    };
  }

  private validateBranch(input: BranchManagerInput): BranchManagerResult {
    const branchName = input.branchName ?? '';
    const validation = this.validateBranchName(branchName, input.strategy);

    return {
      success: validation.valid,
      operation: 'validate',
      validation,
      message: validation.valid
        ? `Branch name "${branchName}" is valid`
        : `Branch name "${branchName}" has issues: ${validation.errors.join(', ')}`,
      timestamp: Date.now(),
    };
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Branch Name Validation
  // ───────────────────────────────────────────────────────────────────────────

  private validateBranchName(name: string, strategy?: string): BranchValidation {
    const errors: string[] = [];
    const warnings: string[] = [];
    let suggestion: string | undefined;

    // Empty name
    if (!name || name.trim().length === 0) {
      errors.push('Branch name cannot be empty');
      return { valid: false, errors, warnings, suggestion };
    }

    // Invalid characters
    if (/\s/.test(name)) {
      errors.push('Branch name cannot contain spaces — use hyphens instead');
      suggestion = name.replace(/\s+/g, '-');
    }

    if (/[~^:?*\[\\]/.test(name)) {
      errors.push('Branch name contains invalid characters: ~ ^ : ? * [ \\');
    }

    if (name.includes('..')) {
      errors.push('Branch name cannot contain consecutive dots (..)');
    }

    if (name.startsWith('-') || name.endsWith('-')) {
      errors.push('Branch name cannot start or end with a hyphen');
    }

    if (name.startsWith('.') || name.endsWith('.')) {
      errors.push('Branch name cannot start or end with a dot');
    }

    if (name.endsWith('.lock')) {
      errors.push('Branch name cannot end with .lock');
    }

    if (name.includes('@{')) {
      errors.push('Branch name cannot contain @{');
    }

    // Conventional naming warnings
    if (name !== name.toLowerCase() && !name.includes('/')) {
      warnings.push('Consider using lowercase branch names for consistency');
    }

    if (name.length > 63) {
      warnings.push('Branch name is very long — consider a shorter, descriptive name');
    }

    // Strategy-specific validation
    if (strategy === 'gitflow') {
      const validPrefixes = ['feature/', 'bugfix/', 'hotfix/', 'release/', 'support/'];
      const hasValidPrefix = validPrefixes.some((p) => name.startsWith(p)) ||
        ['main', 'master', 'develop'].includes(name);

      if (!hasValidPrefix) {
        warnings.push(`GitFlow strategy expects branches with prefixes: ${validPrefixes.join(', ')}`);
        if (!name.includes('/')) {
          suggestion = `feature/${name}`;
        }
      }
    } else if (strategy === 'github-flow') {
      if (!name.includes('/') && !['main', 'master'].includes(name)) {
        warnings.push('GitHub Flow convention uses slash-separated names (e.g., feature/xyz)');
        suggestion = `feature/${name}`;
      }
    }

    return {
      valid: errors.length === 0,
      errors,
      warnings,
      suggestion,
    };
  }

  // ───────────────────────────────────────────────────────────────────────────
  // History Tracking
  // ───────────────────────────────────────────────────────────────────────────

  private recordHistory(repoName: string, action: string, branch: string, author: string): void {
    if (!this.branchHistory.has(repoName)) {
      this.branchHistory.set(repoName, []);
    }
    this.branchHistory.get(repoName)!.push({
      action,
      branch,
      author,
      timestamp: Date.now(),
    });
  }
}
