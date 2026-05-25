/**
 * TheWorkshopAI — Lead AI for The Workshop Hub
 *
 * Identity:  AID-WORKSHOP
 * Pillar:    Norman Hawkins
 * Tier:      3 (Lead AI / Domain Orchestrator)
 * Domain:    Version control, Git operations, branching,
 *            merging, commit management, remote sync
 *
 * Pipeline:  Clone → Branch → Commit → Push → Pull → Merge
 *            BranchManager governs branch lifecycle,
 *            MergeMaster resolves conflicts and orchestrates merges
 */

import { AI, Agent, Bot, Logger, AuditLedger } from '../../core/definitions'
import { BranchManagerAgent } from './agents/BranchManagerAgent';
import { MergeMasterAgent } from './agents/MergeMasterAgent';
import { CommitBot } from './bots/CommitBot';
import { PushBot } from './bots/PushBot';
import { PullBot } from './bots/PullBot';
import { CloneBot } from './bots/CloneBot';

const auditLedger = new AuditLedger();

// ─────────────────────────────────────────────────────────────────────────────
// Domain Interfaces
// ─────────────────────────────────────────────────────────────────────────────

export interface Repository {
  id: string;
  name: string;
  path: string;
  remoteUrl?: string;
  currentBranch: string;
  branches: Branch[];
  headCommit: string;
  status: 'clean' | 'dirty' | 'conflict' | 'detached';
  stashes: Stash[];
  tags: Tag[];
  createdAt: number;
  lastModified: number;
}

export interface Branch {
  name: string;
  type: 'local' | 'remote' | 'tag';
  headCommit: string;
  upstream?: string;
  isMerged: boolean;
  isProtected: boolean;
  createdAt: number;
  author: string;
}

export interface Commit {
  hash: string;
  shortHash: string;
  message: string;
  author: string;
  email: string;
  timestamp: number;
  parentHashes: string[];
  filesChanged: number;
  insertions: number;
  deletions: number;
  tags?: string[];
}

export interface Conflict {
  file: string;
  type: 'content' | 'rename' | 'delete' | 'binary';
  ours: ConflictSide;
  theirs: ConflictSide;
  base?: ConflictSide;
  resolution?: 'ours' | 'theirs' | 'manual' | 'combined';
  resolvedContent?: string;
}

export interface ConflictSide {
  content: string;
  commit: string;
  author: string;
  timestamp: number;
}

export interface Stash {
  id: string;
  message: string;
  branch: string;
  commitHash: string;
  files: string[];
  timestamp: number;
}

export interface Tag {
  name: string;
  commitHash: string;
  message?: string;
  annotated: boolean;
  tagger?: string;
  timestamp: number;
}

export interface MergeRequest {
  id: string;
  sourceBranch: string;
  targetBranch: string;
  title: string;
  description: string;
  author: string;
  status: 'open' | 'merged' | 'closed' | 'conflict';
  commits: string[];
  conflicts: Conflict[];
  createdAt: number;
  updatedAt: number;
}

export interface DiffEntry {
  file: string;
  status: 'added' | 'modified' | 'deleted' | 'renamed' | 'copied';
  additions: number;
  deletions: number;
  oldPath?: string;
  binary: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// TheWorkshopAI Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class TheWorkshopAI extends AI {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private repositories: Map<string, Repository>;
  private commits: Map<string, Commit>;
  private mergeRequests: Map<string, MergeRequest>;
  private stashCounter: number;

  constructor() {
    super(
      'AID-WORKSHOP',
      'TheWorkshop',
      'workshop',
      'Norman Hawkins',
      3
    );

    this.log = new Logger('TheWorkshopAI');
    this.audit = auditLedger;
    this.repositories = new Map();
    this.commits = new Map();
    this.mergeRequests = new Map();
    this.stashCounter = 0;

    // Register Agents
    this.registerAgent(new BranchManagerAgent());
    this.registerAgent(new MergeMasterAgent());

    // Register Bots
    this.registerBot(new CommitBot());
    this.registerBot(new PushBot());
    this.registerBot(new PullBot());
    this.registerBot(new CloneBot());

    this.log.info('TheWorkshopAI initialised', {
      agents: this.listAgentIds(),
      bots: this.listBotNames(),
    });
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Repository Management
  // ───────────────────────────────────────────────────────────────────────────

  /**
   * Register a repository for management.
   */
  registerRepository(repo: Omit<Repository, 'id' | 'createdAt' | 'lastModified'>): Repository {
    const id = `REPO-${this.repositories.size + 1}`;
    const now = Date.now();
    const repository: Repository = {
      ...repo,
      id,
      createdAt: now,
      lastModified: now,
    };

    this.repositories.set(id, repository);
    this.log.info('Repository registered', { id, name: repo.name, path: repo.path });
    return repository;
  }

  /**
   * Get a registered repository.
   */
  getRepository(id: string): Repository | undefined {
    return this.repositories.get(id);
  }

  /**
   * Update repository state.
   */
  updateRepository(id: string, updates: Partial<Repository>): Repository | undefined {
    const repo = this.repositories.get(id);
    if (!repo) return undefined;

    Object.assign(repo, updates, { lastModified: Date.now() });
    this.log.info('Repository updated', { id, updates: Object.keys(updates) });
    return repo;
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Bot Delegations
  // ───────────────────────────────────────────────────────────────────────────

  /**
   * Create a commit via CommitBot.
   */
  async commit(repoId: string, message: string, files: string[], author?: string): Promise<unknown> {
    const repo = this.repositories.get(repoId);
    if (!repo) throw new Error(`Repository not found: ${repoId}`);

    const commit = this.getBot('Commit')!;
    const result = await commit.execute({
      operation: 'CREATE',
      repoPath: repo.path,
      message,
      files,
      author: author ?? 'Norman Hawkins',
      email: 'norman@trancendos.local',
    });
    return result;
  }

  /**
   * Push to remote via PushBot.
   */
  async push(repoId: string, remote?: string, branch?: string): Promise<unknown> {
    const repo = this.repositories.get(repoId);
    if (!repo) throw new Error(`Repository not found: ${repoId}`);

    const push = this.getBot('Push')!;
    const result = await push.execute({
      operation: 'EXECUTE',
      repoPath: repo.path,
      remote: remote ?? 'origin',
      branch: branch ?? repo.currentBranch,
      force: false,
    });
    return result;
  }

  /**
   * Pull from remote via PullBot.
   */
  async pull(repoId: string, remote?: string, branch?: string): Promise<unknown> {
    const repo = this.repositories.get(repoId);
    if (!repo) throw new Error(`Repository not found: ${repoId}`);

    const pull = this.getBot('Pull')!;
    const result = await pull.execute({
      operation: 'EXECUTE',
      repoPath: repo.path,
      remote: remote ?? 'origin',
      branch: branch ?? repo.currentBranch,
      rebase: false,
    });
    return result;
  }

  /**
   * Clone a repository via CloneBot.
   */
  async clone(url: string, targetPath: string, options?: Record<string, unknown>): Promise<unknown> {
    const clone = this.getBot('Clone')!;
    const result = await clone.execute({
      operation: 'EXECUTE',
      url,
      targetPath,
      branch: options?.branch as string | undefined,
      depth: options?.depth as number | undefined,
      recursive: (options?.recursive as boolean) ?? false,
    });
    return result;
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Agent Delegations
  // ───────────────────────────────────────────────────────────────────────────

  /**
   * Manage branches via BranchManagerAgent.
   */
  async manageBranches(
    repoId: string,
    operation: 'create' | 'delete' | 'list' | 'switch' | 'protect',
    params: Record<string, unknown>
  ): Promise<unknown> {
    const branchManager = this.getAgent('SID-WORKSHOP-BRANCHMANAGER') as BranchManagerAgent;
    const result = await branchManager.runCycle({
      repository: this.repositories.get(repoId),
      operation,
      ...params,
    });
    return result;
  }

  /**
   * Resolve merge via MergeMasterAgent.
   */
  async resolveMerge(
    repoId: string,
    sourceBranch: string,
    targetBranch: string,
    strategy?: string
  ): Promise<unknown> {
    const mergeMaster = this.getAgent('SID-WORKSHOP-MERGEMASTER') as MergeMasterAgent;
    const result = await mergeMaster.runCycle({
      repository: this.repositories.get(repoId),
      sourceBranch,
      targetBranch,
      strategy: strategy ?? 'auto',
      operation: 'merge',
    });
    return result;
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Merge Request Management
  // ───────────────────────────────────────────────────────────────────────────

  /**
   * Create a merge request.
   */
  createMergeRequest(
    sourceBranch: string,
    targetBranch: string,
    title: string,
    author: string
  ): MergeRequest {
    const id = `MR-${this.mergeRequests.size + 1}`;
    const now = Date.now();
    const mr: MergeRequest = {
      id,
      sourceBranch,
      targetBranch,
      title,
      description: '',
      author,
      status: 'open',
      commits: [],
      conflicts: [],
      createdAt: now,
      updatedAt: now,
    };

    this.mergeRequests.set(id, mr);
    this.log.info('Merge request created', { id, sourceBranch, targetBranch, author });
    return mr;
  }

  /**
   * Get a merge request.
   */
  getMergeRequest(id: string): MergeRequest | undefined {
    return this.mergeRequests.get(id);
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Health Check
  // ───────────────────────────────────────────────────────────────────────────

  healthCheck(): {
    status: 'healthy' | 'degraded' | 'critical';
    repositories: number;
    activeBranches: number;
    openMergeRequests: number;
    agents: number;
    bots: number;
    timestamp: number;
  } {
    const repos = Array.from(this.repositories.values());
    const totalBranches = repos.reduce((sum, r) => sum + r.branches.length, 0);
    const openMRs = Array.from(this.mergeRequests.values()).filter(
      (mr) => mr.status === 'open'
    ).length;
    const conflictRepos = repos.filter((r) => r.status === 'conflict').length;

    return {
      status: conflictRepos > 0 ? 'critical' : openMRs > 10 ? 'degraded' : 'healthy',
      repositories: repos.length,
      activeBranches: totalBranches,
      openMergeRequests: openMRs,
      agents: this.listAgentIds().length,
      bots: this.listBotNames().length,
      timestamp: Date.now(),
    };
  }
}
