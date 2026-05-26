/**
 * The Workshop — Barrel Exports
 *
 * Hub:       The Workshop
 * Identity:  AID-WORKSHOP
 * Pillar:    Norman Hawkins
 * Domain:    Version control, Git operations, branching, merging
 */

// ── Lead AI ──────────────────────────────────────────────────────────────────
export { TheWorkshopAI } from './TheWorkshopAI';
export type {
  Repository,
  Branch,
  Commit,
  Conflict,
  ConflictSide,
  Stash,
  Tag,
  MergeRequest,
  DiffEntry,
} from './TheWorkshopAI';

// ── Agents ───────────────────────────────────────────────────────────────────
export { BranchManagerAgent } from './agents/BranchManagerAgent';
export type {
  BranchManagerInput,
  BranchInfo,
  BranchValidation,
  BranchManagerResult,
} from './agents/BranchManagerAgent';

export { MergeMasterAgent } from './agents/MergeMasterAgent';
export type {
  MergeMasterInput,
  ConflictAnalysis,
  MergeResult,
} from './agents/MergeMasterAgent';

// ── Bots ─────────────────────────────────────────────────────────────────────
export { CommitBot } from './bots/CommitBot';
export type {
  CommitInput,
  FileChange,
  CommitValidation,
  CommitResult,
} from './bots/CommitBot';

export { PushBot } from './bots/PushBot';
export type {
  PushInput,
  RefUpdate,
  PushRejection,
  PushResult,
} from './bots/PushBot';

export { PullBot } from './bots/PullBot';
export type {
  PullInput,
  RemoteChange,
  PullConflict,
  PullResult,
} from './bots/PullBot';

export { CloneBot } from './bots/CloneBot';
export type {
  CloneInput,
  CloneResult,
} from './bots/CloneBot';
