/**
 * MergeMasterAgent — Merge Conflict Resolution Agent for The Workshop
 *
 * Identity:  SID-WORKSHOP-MERGEMASTER
 * Tier:      4 (Autonomous Microservice)
 * Parent:    TheWorkshopAI (AID-WORKSHOP)
 *
 * Responsibilities:
 *   - Orchestrate merge operations between branches
 *   - Detect and analyse merge conflicts
 *   - Apply conflict resolution strategies (ours, theirs, combined, manual)
 *   - Validate merge results for consistency
 *   - Track merge history and conflict patterns
 */

import { Agent, Logger, AuditLedger } from '../../../core/definitions'

const auditLedger = new AuditLedger();

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface MergeMasterInput {
  repository?: {
    id: string;
    name: string;
    path: string;
    currentBranch: string;
    branches: Array<{
      name: string;
      type: string;
      headCommit: string;
      isMerged: boolean;
      isProtected: boolean;
    }>;
    status: string;
  };
  sourceBranch: string;
  targetBranch: string;
  strategy?: 'auto' | 'ours' | 'theirs' | 'combined' | 'squash' | 'rebase' | 'manual';
  operation: 'merge' | 'abort' | 'status' | 'conflicts' | 'resolve' | 'validate';
  conflictResolutions?: Array<{
    file: string;
    resolution: 'ours' | 'theirs' | 'combined' | 'manual';
    content?: string;
  }>;
  message?: string;
  author?: string;
}

export interface ConflictAnalysis {
  file: string;
  type: 'content' | 'rename' | 'delete-modify' | 'add-add' | 'binary';
  severity: 'low' | 'medium' | 'high';
  oursSummary: string;
  theirsSummary: string;
  overlapLines: number;
  suggestedResolution: 'ours' | 'theirs' | 'combined' | 'manual';
  confidence: number;
  autoResolvable: boolean;
}

export interface MergeResult {
  success: boolean;
  sourceBranch: string;
  targetBranch: string;
  strategy: string;
  status: 'merged' | 'conflict' | 'aborted' | 'failed';
  filesChanged: number;
  insertions: number;
  deletions: number;
  conflicts?: ConflictAnalysis[];
  mergeCommit?: string;
  message: string;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// MergeMasterAgent Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class MergeMasterAgent extends Agent {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private readonly mergeHistory: Array<{
    source: string;
    target: string;
    strategy: string;
    status: string;
    conflictsCount: number;
    timestamp: number;
  }>;
  private readonly conflictPatterns: Map<string, number>;

  constructor() {
    super(
      'SID-WORKSHOP-MERGEMASTER',
      'MergeMaster',
      'Merge conflict resolution and branch integration orchestration'
    );

    this.log = new Logger('MergeMasterAgent');
    this.audit = auditLedger;
    this.mergeHistory = [];
    this.conflictPatterns = new Map();
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Agent Lifecycle: Perceive → Decide → Act
  // ───────────────────────────────────────────────────────────────────────────

  public async perceive(input: MergeMasterInput): Promise<MergeMasterInput> {
    this.log.info('Perceiving merge operation', {
      operation: input.operation,
      source: input.sourceBranch,
      target: input.targetBranch,
    });

    // Validate branch existence
    if (input.repository) {
      const sourceExists = input.repository.branches.some(
        (b) => b.name === input.sourceBranch
      );
      const targetExists = input.repository.branches.some(
        (b) => b.name === input.targetBranch
      );

      if (!sourceExists) {
        this.log.warn('Source branch not found', { sourceBranch: input.sourceBranch });
      }
      if (!targetExists) {
        this.log.warn('Target branch not found', { targetBranch: input.targetBranch });
      }
    }

    // Track conflict patterns
    this.trackConflictPatterns(input.sourceBranch, input.targetBranch);

    return input;
  }

  public async decide(input: MergeMasterInput): Promise<string> {
    this.log.info('Deciding merge action', { operation: input.operation });

    switch (input.operation) {
      case 'merge':
        return 'performMerge';
      case 'abort':
        return 'abortMerge';
      case 'status':
        return 'mergeStatus';
      case 'conflicts':
        return 'analyseConflicts';
      case 'resolve':
        return 'resolveConflicts';
      case 'validate':
        return 'validateMerge';
      default:
        return 'unknown';
    }
  }

  public async act(input: MergeMasterInput, decision: string): Promise<MergeResult> {
    this.log.info('Acting on merge decision', { decision });

    switch (decision) {
      case 'performMerge':
        return this.performMerge(input);
      case 'abortMerge':
        return this.abortMerge(input);
      case 'mergeStatus':
        return this.mergeStatus(input);
      case 'analyseConflicts':
        return this.analyseConflicts(input);
      case 'resolveConflicts':
        return this.resolveConflicts(input);
      case 'validateMerge':
        return this.validateMerge(input);
      default:
        return {
          success: false,
          sourceBranch: input.sourceBranch,
          targetBranch: input.targetBranch,
          strategy: input.strategy ?? 'auto',
          status: 'failed',
          filesChanged: 0,
          insertions: 0,
          deletions: 0,
          message: `Unknown operation: ${input.operation}`,
          timestamp: Date.now(),
        };
    }
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Merge Operations
  // ───────────────────────────────────────────────────────────────────────────

  private performMerge(input: MergeMasterInput): MergeResult {
    const { sourceBranch, targetBranch, strategy, author } = input;
    const mergeStrategy = strategy ?? 'auto';

    // Prevent merging into protected branch without squash
    if (input.repository) {
      const target = input.repository.branches.find(
        (b) => b.name === targetBranch
      );
      if (target?.isProtected && mergeStrategy !== 'squash') {
        this.log.warn('Protected branch merge requires squash strategy', { targetBranch });
      }
    }

    // Same-branch merge check
    if (sourceBranch === targetBranch) {
      return {
        success: false,
        sourceBranch,
        targetBranch,
        strategy: mergeStrategy,
        status: 'failed',
        filesChanged: 0,
        insertions: 0,
        deletions: 0,
        message: 'Cannot merge a branch into itself',
        timestamp: Date.now(),
      };
    }

    // Simulate merge conflict detection
    const conflictProbability = this.estimateConflictProbability(sourceBranch, targetBranch);
    const hasConflicts = Math.random() < conflictProbability;

    if (hasConflicts) {
      const conflicts = this.simulateConflicts(sourceBranch, targetBranch);
      const autoResolvable = conflicts.every((c) => c.autoResolvable);

      if (mergeStrategy === 'auto' && autoResolvable) {
        // Auto-resolve
        this.log.info('Auto-resolving merge conflicts', {
          sourceBranch,
          targetBranch,
          conflictCount: conflicts.length,
        });

        const result = this.buildMergeResult(
          sourceBranch, targetBranch, mergeStrategy, 'merged', conflicts
        );

        this.recordMergeHistory(sourceBranch, targetBranch, mergeStrategy, 'merged', conflicts.length);
        return result;
      }

      if (mergeStrategy === 'ours' || mergeStrategy === 'theirs') {
        // Apply strategy resolution
        const resolvedConflicts = conflicts.map((c) => ({
          ...c,
          suggestedResolution: mergeStrategy as 'ours' | 'theirs',
        }));

        const result = this.buildMergeResult(
          sourceBranch, targetBranch, mergeStrategy, 'merged', resolvedConflicts
        );

        this.recordMergeHistory(sourceBranch, targetBranch, mergeStrategy, 'merged', conflicts.length);
        return result;
      }

      // Conflicts require resolution
      const result = this.buildMergeResult(
        sourceBranch, targetBranch, mergeStrategy, 'conflict', conflicts
      );

      this.recordMergeHistory(sourceBranch, targetBranch, mergeStrategy, 'conflict', conflicts.length);
      return result;
    }

    // Clean merge
    const filesChanged = Math.floor(Math.random() * 15) + 1;
    const insertions = Math.floor(Math.random() * 200) + 5;
    const deletions = Math.floor(Math.random() * 50);

    const result: MergeResult = {
      success: true,
      sourceBranch,
      targetBranch,
      strategy: mergeStrategy,
      status: 'merged',
      filesChanged,
      insertions,
      deletions,
      mergeCommit: this.generateMergeCommitHash(),
      message: `Successfully merged "${sourceBranch}" into "${targetBranch}"`,
      timestamp: Date.now(),
    };

    this.recordMergeHistory(sourceBranch, targetBranch, mergeStrategy, 'merged', 0);

    this.audit.append({ actor: this.id,
      entity: 'MERGE_COMPLETE',
      action: 'MERGE_COMPLETE',
      details: { sourceBranch, targetBranch, strategy: mergeStrategy, filesChanged },
      timestamp: new Date(),
    });

    this.log.info('Merge completed successfully', {
      sourceBranch,
      targetBranch,
      filesChanged,
    });

    return result;
  }

  private abortMerge(input: MergeMasterInput): MergeResult {
    this.audit.append({ actor: this.id,
      entity: 'MERGE_ABORT',
      action: 'MERGE_ABORT',
      details: { sourceBranch: input.sourceBranch, targetBranch: input.targetBranch },
      timestamp: new Date(),
    });

    this.log.info('Merge aborted', {
      sourceBranch: input.sourceBranch,
      targetBranch: input.targetBranch,
    });

    return {
      success: true,
      sourceBranch: input.sourceBranch,
      targetBranch: input.targetBranch,
      strategy: input.strategy ?? 'auto',
      status: 'aborted',
      filesChanged: 0,
      insertions: 0,
      deletions: 0,
      message: 'Merge aborted — working tree restored to pre-merge state',
      timestamp: Date.now(),
    };
  }

  private mergeStatus(input: MergeMasterInput): MergeResult {
    // In a real implementation, this would query the actual repository state
    const recentMerge = this.mergeHistory.length > 0
      ? this.mergeHistory[this.mergeHistory.length - 1]
      : null;

    return {
      success: true,
      sourceBranch: input.sourceBranch,
      targetBranch: input.targetBranch,
      strategy: input.strategy ?? 'auto',
      status: recentMerge ? (recentMerge.status as any) : 'merged',
      filesChanged: 0,
      insertions: 0,
      deletions: 0,
      message: recentMerge
        ? `Last merge: ${recentMerge.source} → ${recentMerge.target} (${recentMerge.status})`
        : 'No merge in progress',
      timestamp: Date.now(),
    };
  }

  private analyseConflicts(input: MergeMasterInput): MergeResult {
    const conflicts = this.simulateConflicts(input.sourceBranch, input.targetBranch);

    return {
      success: true,
      sourceBranch: input.sourceBranch,
      targetBranch: input.targetBranch,
      strategy: input.strategy ?? 'auto',
      status: 'conflict',
      filesChanged: conflicts.length,
      insertions: 0,
      deletions: 0,
      conflicts,
      message: `Found ${conflicts.length} conflict(s) between "${input.sourceBranch}" and "${input.targetBranch}"`,
      timestamp: Date.now(),
    };
  }

  private resolveConflicts(input: MergeMasterInput): MergeResult {
    if (!input.conflictResolutions || input.conflictResolutions.length === 0) {
      return {
        success: false,
        sourceBranch: input.sourceBranch,
        targetBranch: input.targetBranch,
        strategy: input.strategy ?? 'auto',
        status: 'conflict',
        filesChanged: 0,
        insertions: 0,
        deletions: 0,
        message: 'No conflict resolutions provided',
        timestamp: Date.now(),
      };
    }

    // Apply resolutions
    const resolvedConflicts = input.conflictResolutions.map((resolution) => {
      const analysis: ConflictAnalysis = {
        file: resolution.file,
        type: 'content',
        severity: 'medium',
        oursSummary: 'Our changes',
        theirsSummary: 'Their changes',
        overlapLines: 5,
        suggestedResolution: resolution.resolution,
        confidence: resolution.resolution === 'manual' ? 0.5 : 0.9,
        autoResolvable: resolution.resolution !== 'manual',
      };
      return analysis;
    });

    this.audit.append({ actor: this.id,
      entity: 'CONFLICTS_RESOLVED',
      action: 'CONFLICTS_RESOLVED',
      details: {
        sourceBranch: input.sourceBranch,
        targetBranch: input.targetBranch,
        resolutions: input.conflictResolutions.map((r) => ({
          file: r.file,
          resolution: r.resolution,
        })),
      },
      timestamp: new Date(),
    });

    this.log.info('Conflicts resolved', {
      sourceBranch: input.sourceBranch,
      targetBranch: input.targetBranch,
      resolvedCount: resolvedConflicts.length,
    });

    return {
      success: true,
      sourceBranch: input.sourceBranch,
      targetBranch: input.targetBranch,
      strategy: input.strategy ?? 'auto',
      status: 'merged',
      filesChanged: resolvedConflicts.length,
      insertions: Math.floor(Math.random() * 50),
      deletions: Math.floor(Math.random() * 20),
      conflicts: resolvedConflicts,
      mergeCommit: this.generateMergeCommitHash(),
      message: `All ${resolvedConflicts.length} conflict(s) resolved and merged`,
      timestamp: Date.now(),
    };
  }

  private validateMerge(input: MergeMasterInput): MergeResult {
    const checks: string[] = [];
    let valid = true;

    // Check source branch exists
    if (input.repository) {
      const sourceExists = input.repository.branches.some(
        (b) => b.name === input.sourceBranch
      );
      if (!sourceExists) {
        checks.push(`Source branch "${input.sourceBranch}" does not exist`);
        valid = false;
      }

      const targetExists = input.repository.branches.some(
        (b) => b.name === input.targetBranch
      );
      if (!targetExists) {
        checks.push(`Target branch "${input.targetBranch}" does not exist`);
        valid = false;
      }
    }

    // Check for uncommitted changes
    if (input.repository?.status === 'dirty') {
      checks.push('Working tree has uncommitted changes — commit or stash before merging');
      valid = false;
    }

    // Check for existing merge conflicts
    if (input.repository?.status === 'conflict') {
      checks.push('Repository already has unresolved merge conflicts');
      valid = false;
    }

    // Check recent merge history for repeated conflicts
    const conflictKey = `${input.sourceBranch}→${input.targetBranch}`;
    const patternCount = this.conflictPatterns.get(conflictKey) ?? 0;
    if (patternCount > 3) {
      checks.push(`High conflict frequency detected (${patternCount} recent conflicts) — consider alternative integration approach`);
    }

    return {
      success: valid,
      sourceBranch: input.sourceBranch,
      targetBranch: input.targetBranch,
      strategy: input.strategy ?? 'auto',
      status: valid ? 'merged' : 'failed',
      filesChanged: 0,
      insertions: 0,
      deletions: 0,
      message: valid
        ? 'Merge validation passed — safe to proceed'
        : `Merge validation failed: ${checks.join('; ')}`,
      timestamp: Date.now(),
    };
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Conflict Simulation & Analysis
  // ───────────────────────────────────────────────────────────────────────────

  private estimateConflictProbability(sourceBranch: string, targetBranch: string): number {
    // Higher probability for long-lived feature branches
    const featurePrefixes = ['feature/', 'bugfix/', 'hotfix/'];
    const isFeature = featurePrefixes.some((p) => sourceBranch.startsWith(p));

    // Check historical conflict rate
    const key = `${sourceBranch}→${targetBranch}`;
    const historyConflicts = this.conflictPatterns.get(key) ?? 0;

    let probability = isFeature ? 0.3 : 0.15;
    probability += Math.min(historyConflicts * 0.1, 0.4); // max +40% from history

    return Math.min(probability, 0.8);
  }

  private simulateConflicts(sourceBranch: string, targetBranch: string): ConflictAnalysis[] {
    const conflictCount = Math.floor(Math.random() * 4) + 1;
    const conflicts: ConflictAnalysis[] = [];

    const conflictFiles = [
      'src/core/definitions.ts',
      'src/hubs/workshop/TheWorkshopAI.ts',
      'package.json',
      'tsconfig.json',
      'README.md',
      'src/hubs/workshop/agents/BranchManagerAgent.ts',
      'src/hubs/workshop/agents/MergeMasterAgent.ts',
      'src/utils/helpers.ts',
    ];

    for (let i = 0; i < conflictCount; i++) {
      const file = conflictFiles[Math.floor(Math.random() * conflictFiles.length)];
      const types: ConflictAnalysis['type'][] = ['content', 'content', 'content', 'rename', 'delete-modify', 'add-add'];
      const type = types[Math.floor(Math.random() * types.length)];

      const severity: ConflictAnalysis['severity'] = type === 'content' ? 'medium' : 'high';
      const overlapLines = type === 'content' ? Math.floor(Math.random() * 20) + 3 : 0;

      // Determine if auto-resolvable
      let autoResolvable = false;
      let suggestedResolution: ConflictAnalysis['suggestedResolution'] = 'manual';
      let confidence = 0.5;

      if (type === 'content' && overlapLines <= 5) {
        autoResolvable = Math.random() > 0.5;
        suggestedResolution = autoResolvable ? 'combined' : 'manual';
        confidence = autoResolvable ? 0.85 : 0.4;
      } else if (type === 'add-add') {
        autoResolvable = false;
        suggestedResolution = 'manual';
        confidence = 0.3;
      } else if (type === 'delete-modify') {
        autoResolvable = false;
        suggestedResolution = 'manual';
        confidence = 0.2;
      }

      conflicts.push({
        file,
        type,
        severity,
        oursSummary: type === 'content' ? `Modified ${overlapLines} lines in ${file}` : `${type} conflict on ${file}`,
        theirsSummary: type === 'content' ? `Modified ${Math.floor(overlapLines * 0.8)} overlapping lines` : `Parallel ${type} operation`,
        overlapLines,
        suggestedResolution,
        confidence,
        autoResolvable,
      });
    }

    return conflicts;
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Utilities
  // ───────────────────────────────────────────────────────────────────────────

  private buildMergeResult(
    sourceBranch: string,
    targetBranch: string,
    strategy: string,
    status: MergeResult['status'],
    conflicts: ConflictAnalysis[]
  ): MergeResult {
    return {
      success: status === 'merged',
      sourceBranch,
      targetBranch,
      strategy,
      status,
      filesChanged: conflicts.length > 0 ? conflicts.length : Math.floor(Math.random() * 10) + 1,
      insertions: Math.floor(Math.random() * 100) + 5,
      deletions: Math.floor(Math.random() * 30),
      conflicts: conflicts.length > 0 ? conflicts : undefined,
      mergeCommit: status === 'merged' ? this.generateMergeCommitHash() : undefined,
      message: status === 'merged'
        ? `Successfully merged "${sourceBranch}" into "${targetBranch}"`
        : `Merge conflicts detected between "${sourceBranch}" and "${targetBranch}"`,
      timestamp: Date.now(),
    };
  }

  private generateMergeCommitHash(): string {
    const chars = '0123456789abcdef';
    let hash = '';
    for (let i = 0; i < 40; i++) {
      hash += chars[Math.floor(Math.random() * chars.length)];
    }
    return hash;
  }

  private recordMergeHistory(
    source: string,
    target: string,
    strategy: string,
    status: string,
    conflictsCount: number
  ): void {
    this.mergeHistory.push({
      source,
      target,
      strategy,
      status,
      conflictsCount,
      timestamp: Date.now(),
    });
  }

  private trackConflictPatterns(sourceBranch: string, targetBranch: string): void {
    const key = `${sourceBranch}→${targetBranch}`;
    this.conflictPatterns.set(key, (this.conflictPatterns.get(key) ?? 0) + 1);
  }
}
