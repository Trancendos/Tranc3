/**
 * HIL-A Protocol — Human-In-Loop-Action Chain
 * Tranc3 Ecosystem
 *
 * Implements the tier-by-tier approval escalation protocol:
 *
 *   Tier 5 (Bot)     → executes autonomously for routine tasks
 *   Tier 4 (Agent)   → executes autonomously within defined boundaries
 *   Tier 3 (AI)      → orchestrates agents, handles complex decisions
 *   Tier 2 (Prime)   → cross-domain coordination, policy enforcement
 *   Tier 1 (Sovereign) → system-wide authority, override capability
 *   Tier 0 (Human)   → final authority, required for high-impact actions
 *
 * The HIL-A chain ensures that actions requiring higher authority
 * are automatically escalated through the tier hierarchy until
 * a sufficiently authorized entity approves or rejects them.
 *
 * Key principles:
 *   - Every action has a minimum required tier
 *   - Actions can be escalated but never de-escalated
 *   - A human (Tier 0) can always override any decision
 *   - Timeouts at any tier auto-escalate to the next higher tier
 *   - All decisions are recorded in the audit trail
 *   - The chain is idempotent — re-escalating an already-pending action is safe
 */

import { Logger } from '../../core/logger';
import { AuditLedger } from '../../core/audit';

// ─────────────────────────────────────────────────────────────────────────────
// HIL-A Types
// ─────────────────────────────────────────────────────────────────────────────

/** The tier levels in the Tranc3 hierarchy. Lower number = higher authority. */
export type HILATier = 0 | 1 | 2 | 3 | 4 | 5;

/** Status of an action in the HIL-A chain */
export type HILAActionStatus =
  | 'pending'        // Awaiting approval at the current tier
  | 'approved'       // Approved at sufficient tier, ready to execute
  | 'rejected'       // Rejected at some tier
  | 'executing'      // Currently being executed
  | 'completed'      // Successfully completed
  | 'failed'         // Execution failed
  | 'timed_out'      // Approval timed out, auto-escalated
  | 'escalated'      // Escalated to next tier
  | 'cancelled';     // Cancelled before resolution

/** The type of action being requested — determines minimum tier */
export type HILAActionCategory =
  | 'read'             // Read-only access → Tier 5 autonomous
  | 'write'            // Write/create data → Tier 5 with constraints
  | 'update'           // Update existing data → Tier 4 autonomous
  | 'delete'           // Delete data → Tier 3 minimum
  | 'deploy'           // Deploy code/service → Tier 3 minimum
  | 'configure'        // Change configuration → Tier 3 minimum
  | 'security_modify'  // Modify security settings → Tier 2 minimum
  | 'system_override'  // Override system behavior → Tier 1 minimum
  | 'data_export'      // Export bulk data → Tier 2 minimum
  | 'credential_rotate' // Rotate credentials → Tier 2 minimum
  | 'emergency_stop'   // Emergency shutdown → Tier 3 (any AI can trigger)
  | 'cross_domain'     // Cross-domain coordination → Tier 2 minimum
  | 'sovereign_decree' // System-wide policy → Tier 1 minimum
  | 'human_required';  // Explicitly requires human approval → Tier 0 only

/** A decision made at a specific tier */
export interface HILADecision {
  /** Unique decision ID */
  id: string;
  /** The tier at which this decision was made */
  tier: HILATier;
  /** The entity that made the decision */
  decidedBy: string;
  /** The decision */
  decision: 'approve' | 'reject' | 'escalate' | 'delegate';
  /** Reason for the decision */
  reason: string;
  /** When the decision was made */
  timestamp: Date;
  /** Any conditions attached to approval */
  conditions?: string[];
  /** Time-to-live for this approval (ms) — after this, re-approval needed */
  ttlMs?: number;
}

/** An action requiring approval through the HIL-A chain */
export interface HILAAction {
  /** Unique action ID */
  id: string;
  /** Human-readable name */
  name: string;
  /** Category determines minimum required tier */
  category: HILAActionCategory;
  /** Description of what the action will do */
  description: string;
  /** The entity that requested the action */
  requestedBy: string;
  /** Tier of the requesting entity */
  requestedByTier: HILATier;
  /** Minimum tier required to approve this action */
  minimumApprovalTier: HILATier;
  /** Current tier where approval is pending */
  currentTier: HILATier;
  /** Status of the action */
  status: HILAActionStatus;
  /** All decisions made so far in the chain */
  decisions: HILADecision[];
  /** Payload for the action */
  payload: Record<string, unknown>;
  /** When the action was created */
  createdAt: Date;
  /** When the action was last updated */
  updatedAt: Date;
  /** Timeout for the current tier (ms) */
  tierTimeoutMs: number;
  /** When the current tier's timeout expires */
  tierTimeoutAt: Date | null;
  /** Priority — higher = more urgent */
  priority: number;
  /** Tags for categorization */
  tags: string[];
  /** Result of execution (if completed/failed) */
  result?: unknown;
  /** Error message (if failed) */
  error?: string;
}

/** Configuration for the HIL-A protocol */
export interface HILAConfig {
  /** Default timeout per tier level (key = tier, value = timeout in ms) */
  tierTimeouts: Partial<Record<HILATier, number>>;
  /** Whether to auto-escalate on timeout (default: true) */
  autoEscalateOnTimeout: boolean;
  /** Whether Tier 0 (Human) can override any decision (default: true) */
  humanOverrideEnabled: boolean;
  /** Maximum number of escalation hops before forcing Tier 0 (default: 5) */
  maxEscalationHops: number;
  /** Whether to audit all decisions (default: true) */
  auditEnabled: boolean;
  /** Action category → minimum tier mapping (overrides defaults) */
  categoryTierOverrides?: Partial<Record<HILAActionCategory, HILATier>>;
}

/** A handler that can approve/reject actions at a specific tier */
export interface HILATierHandler {
  /** The tier this handler operates at */
  tier: HILATier;
  /** The entity ID of this handler */
  entityId: string;
  /** Check if this handler can decide on the given action */
  canDecide(action: HILAAction): Promise<boolean>;
  /** Make a decision on the action */
  decide(action: HILAAction): Promise<HILADecision>;
}

// ─────────────────────────────────────────────────────────────────────────────
// Default Configuration
// ─────────────────────────────────────────────────────────────────────────────

/** Default minimum tier for each action category */
const DEFAULT_CATEGORY_TIERS: Record<HILAActionCategory, HILATier> = {
  read: 5,
  write: 5,
  update: 4,
  delete: 3,
  deploy: 3,
  configure: 3,
  security_modify: 2,
  system_override: 1,
  data_export: 2,
  credential_rotate: 2,
  emergency_stop: 3,
  cross_domain: 2,
  sovereign_decree: 1,
  human_required: 0,
};

/** Default timeout per tier (ms) — higher tiers get less time */
const DEFAULT_TIER_TIMEOUTS: Record<HILATier, number> = {
  0: 3600000,  // Tier 0 (Human): 1 hour
  1: 300000,   // Tier 1 (Sovereign): 5 minutes
  2: 120000,   // Tier 2 (Prime): 2 minutes
  3: 60000,    // Tier 3 (AI): 1 minute
  4: 30000,    // Tier 4 (Agent): 30 seconds
  5: 10000,    // Tier 5 (Bot): 10 seconds
};

const DEFAULT_CONFIG: HILAConfig = {
  tierTimeouts: DEFAULT_TIER_TIMEOUTS,
  autoEscalateOnTimeout: true,
  humanOverrideEnabled: true,
  maxEscalationHops: 5,
  auditEnabled: true,
};

// ─────────────────────────────────────────────────────────────────────────────
// HIL-A Chain Manager
// ─────────────────────────────────────────────────────────────────────────────

/**
 * HILAChain — The Human-In-Loop-Action Chain Manager
 *
 * Manages the lifecycle of actions requiring tier-based approval.
 * Each action enters the chain at the tier of the requesting entity
 * and escalates upward until it reaches a tier with sufficient authority.
 */
export class HILAChain {
  private readonly actions: Map<string, HILAAction> = new Map();
  private readonly handlers: Map<HILATier, HILATierHandler[]> = new Map();
  private readonly timers: Map<string, ReturnType<typeof setTimeout>> = new Map();
  private readonly config: HILAConfig;
  private readonly categoryTiers: Record<HILAActionCategory, HILATier>;
  private readonly logger: Logger;
  private readonly audit: AuditLedger;

  /** Event listeners for action state changes */
  private readonly listeners: Map<string, Array<(action: HILAAction, event: string) => void>> = new Map();

  constructor(config?: Partial<HILAConfig>) {
    this.config = { ...DEFAULT_CONFIG, ...config };
    this.categoryTiers = {
      ...DEFAULT_CATEGORY_TIERS,
      ...(this.config.categoryTierOverrides ?? {}),
    };
    this.logger = new Logger('HILAChain');
    this.audit = new AuditLedger();

    // Initialize handler maps for all tiers
    for (let tier = 0; tier <= 5; tier++) {
      this.handlers.set(tier as HILATier, []);
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Action Lifecycle
  // ─────────────────────────────────────────────────────────────────────────

  /**
   * Submit a new action into the HIL-A chain.
   * The action starts at the tier of the requesting entity and
   * escalates upward if needed.
   */
  submitAction(params: {
    name: string;
    category: HILAActionCategory;
    description: string;
    requestedBy: string;
    requestedByTier: HILATier;
    payload?: Record<string, unknown>;
    priority?: number;
    tags?: string[];
  }): HILAAction {
    const minimumTier = this.categoryTiers[params.category];
    const now = new Date();
    const tierTimeout = this.config.tierTimeouts[params.requestedByTier] ?? DEFAULT_TIER_TIMEOUTS[params.requestedByTier];
    const tierTimeoutAt = new Date(now.getTime() + tierTimeout);

    const action: HILAAction = {
      id: `HILA-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      name: params.name,
      category: params.category,
      description: params.description,
      requestedBy: params.requestedBy,
      requestedByTier: params.requestedByTier,
      minimumApprovalTier: minimumTier,
      currentTier: params.requestedByTier,
      status: 'pending',
      decisions: [],
      payload: params.payload ?? {},
      createdAt: now,
      updatedAt: now,
      tierTimeoutMs: tierTimeout,
      tierTimeoutAt,
      priority: params.priority ?? 5,
      tags: params.tags ?? [],
    };

    this.actions.set(action.id, action);
    this.logger.info(`Action submitted: ${action.id} "${action.name}" (category=${action.category}, minTier=${minimumTier}, currentTier=${action.currentTier})`);

    // If the requesting tier already meets the minimum, auto-approve
    if (params.requestedByTier <= minimumTier) {
      this.autoApprove(action.id, params.requestedBy, params.requestedByTier);
    } else {
      // Start the timeout timer for the current tier
      this.startTierTimer(action.id);
    }

    // Audit
    if (this.config.auditEnabled) {
      void this.audit.append({
        actor: params.requestedBy,
        action: 'HILA_ACTION_SUBMITTED',
        entity: action.id,
        details: { category: params.category, minTier: minimumTier, currentTier: action.currentTier },
      });
    }

    this.emit(action.id, 'submitted');
    return action;
  }

  /**
   * Approve an action at the specified tier.
   * Only valid if the tier is at or below the minimum required tier.
   */
  approve(actionId: string, approvedBy: string, tier: HILATier, reason: string, conditions?: string[]): HILAAction | null {
    const action = this.actions.get(actionId);
    if (!action) {
      this.logger.warn(`Action not found: ${actionId}`);
      return null;
    }

    if (action.status !== 'pending' && action.status !== 'escalated') {
      this.logger.warn(`Action ${actionId} is not pending (status: ${action.status})`);
      return action;
    }

    // Check if the approving tier meets the minimum
    if (tier > action.minimumApprovalTier) {
      this.logger.warn(`Tier ${tier} insufficient for action ${actionId} (requires tier ${action.minimumApprovalTier})`);
      // Record the insufficient decision and auto-escalate
      const decision: HILADecision = {
        id: `DEC-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        tier,
        decidedBy: approvedBy,
        decision: 'escalate',
        reason: `Tier ${tier} insufficient for approval (requires tier ${action.minimumApprovalTier})`,
        timestamp: new Date(),
      };
      action.decisions.push(decision);
      this.escalate(actionId);
      return action;
    }

    // Tier is sufficient — approve
    const decision: HILADecision = {
      id: `DEC-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      tier,
      decidedBy: approvedBy,
      decision: 'approve',
      reason,
      timestamp: new Date(),
      conditions,
    };
    action.decisions.push(decision);
    action.status = 'approved';
    action.currentTier = tier;
    action.updatedAt = new Date();
    this.clearTierTimer(actionId);

    this.logger.info(`Action approved: ${actionId} at tier ${tier} by ${approvedBy}`);

    if (this.config.auditEnabled) {
      void this.audit.append({
        actor: approvedBy,
        action: 'HILA_ACTION_APPROVED',
        entity: actionId,
        status: 'SUCCESS',
        details: { tier, reason, conditions },
      });
    }

    this.emit(actionId, 'approved');
    return action;
  }

  /**
   * Reject an action at the specified tier.
   * A rejection at any tier stops the chain.
   */
  reject(actionId: string, rejectedBy: string, tier: HILATier, reason: string): HILAAction | null {
    const action = this.actions.get(actionId);
    if (!action) {
      this.logger.warn(`Action not found: ${actionId}`);
      return null;
    }

    if (action.status !== 'pending' && action.status !== 'escalated') {
      this.logger.warn(`Action ${actionId} is not pending (status: ${action.status})`);
      return action;
    }

    const decision: HILADecision = {
      id: `DEC-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      tier,
      decidedBy: rejectedBy,
      decision: 'reject',
      reason,
      timestamp: new Date(),
    };
    action.decisions.push(decision);
    action.status = 'rejected';
    action.currentTier = tier;
    action.updatedAt = new Date();
    this.clearTierTimer(actionId);

    this.logger.info(`Action rejected: ${actionId} at tier ${tier} by ${rejectedBy}`);

    if (this.config.auditEnabled) {
      void this.audit.append({
        actor: rejectedBy,
        action: 'HILA_ACTION_REJECTED',
        entity: actionId,
        status: 'FAILURE',
        details: { tier, reason },
      });
    }

    this.emit(actionId, 'rejected');
    return action;
  }

  /**
   * Escalate an action to the next higher tier.
   * This happens automatically on timeout or when a tier defers.
   */
  escalate(actionId: string, reason?: string): HILAAction | null {
    const action = this.actions.get(actionId);
    if (!action) {
      this.logger.warn(`Action not found: ${actionId}`);
      return null;
    }

    if (action.currentTier === 0) {
      this.logger.warn(`Action ${actionId} already at Tier 0 — cannot escalate further`);
      return action;
    }

    // Check max escalation hops
    const escalationCount = action.decisions.filter(d => d.decision === 'escalate').length;
    if (escalationCount >= this.config.maxEscalationHops) {
      this.logger.warn(`Action ${actionId} exceeded max escalation hops (${this.config.maxEscalationHops}) — forcing to Tier 0`);
      action.currentTier = 0;
      action.status = 'escalated';
      action.updatedAt = new Date();
      this.clearTierTimer(actionId);
      this.startTierTimer(actionId);

      if (this.config.auditEnabled) {
        void this.audit.append({
          actor: 'HILAChain',
          action: 'HILA_FORCED_ESCALATION',
          entity: actionId,
          details: { reason: 'max_hops_exceeded', newTier: 0 },
        });
      }

      this.emit(actionId, 'escalated');
      return action;
    }

    const nextTier = (action.currentTier - 1) as HILATier;
    action.currentTier = nextTier;
    action.status = 'escalated';
    action.updatedAt = new Date();

    const tierTimeout = this.config.tierTimeouts[nextTier] ?? DEFAULT_TIER_TIMEOUTS[nextTier];
    action.tierTimeoutMs = tierTimeout;
    action.tierTimeoutAt = new Date(Date.now() + tierTimeout);

    this.clearTierTimer(actionId);
    this.startTierTimer(actionId);

    this.logger.info(`Action escalated: ${actionId} → Tier ${nextTier}${reason ? ` (${reason})` : ''}`);

    if (this.config.auditEnabled) {
      void this.audit.append({
        actor: 'HILAChain',
        action: 'HILA_ACTION_ESCALATED',
        entity: actionId,
        details: { fromTier: nextTier + 1, toTier: nextTier, reason },
      });
    }

    this.emit(actionId, 'escalated');
    return action;
  }

  /**
   * Delegate an action to a specific entity at the current or higher tier.
   * Unlike escalation (which goes up one tier), delegation targets a specific entity.
   */
  delegate(actionId: string, delegatedBy: string, delegateTo: string, targetTier: HILATier, reason: string): HILAAction | null {
    const action = this.actions.get(actionId);
    if (!action) {
      this.logger.warn(`Action not found: ${actionId}`);
      return null;
    }

    // Delegation can only go to equal or higher tier
    if (targetTier > action.currentTier) {
      this.logger.warn(`Cannot delegate to lower tier: ${targetTier} < current ${action.currentTier}`);
      return action;
    }

    const decision: HILADecision = {
      id: `DEC-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      tier: action.currentTier,
      decidedBy: delegatedBy,
      decision: 'delegate',
      reason: `Delegated to ${delegateTo} at Tier ${targetTier}: ${reason}`,
      timestamp: new Date(),
    };
    action.decisions.push(decision);
    action.currentTier = targetTier;
    action.updatedAt = new Date();

    const tierTimeout = this.config.tierTimeouts[targetTier] ?? DEFAULT_TIER_TIMEOUTS[targetTier];
    action.tierTimeoutMs = tierTimeout;
    action.tierTimeoutAt = new Date(Date.now() + tierTimeout);

    this.clearTierTimer(actionId);
    this.startTierTimer(actionId);

    this.logger.info(`Action delegated: ${actionId} → ${delegateTo} at Tier ${targetTier}`);

    if (this.config.auditEnabled) {
      void this.audit.append({
        actor: delegatedBy,
        action: 'HILA_ACTION_DELEGATED',
        entity: actionId,
        details: { delegateTo, targetTier, reason },
      });
    }

    this.emit(actionId, 'delegated');
    return action;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Execution
  // ─────────────────────────────────────────────────────────────────────────

  /**
   * Execute an approved action.
   * The caller provides the execution function.
   */
  async executeAction(actionId: string, executor: (action: HILAAction) => Promise<unknown>): Promise<HILAAction | null> {
    const action = this.actions.get(actionId);
    if (!action) {
      this.logger.warn(`Action not found: ${actionId}`);
      return null;
    }

    if (action.status !== 'approved') {
      this.logger.warn(`Action ${actionId} is not approved (status: ${action.status})`);
      return action;
    }

    action.status = 'executing';
    action.updatedAt = new Date();
    this.emit(actionId, 'executing');

    try {
      const result = await executor(action);
      action.status = 'completed';
      action.result = result;
      action.updatedAt = new Date();
      this.logger.info(`Action completed: ${actionId}`);

      if (this.config.auditEnabled) {
        void this.audit.append({
          actor: 'HILAChain',
          action: 'HILA_ACTION_EXECUTED',
          entity: actionId,
          status: 'SUCCESS',
        });
      }

      this.emit(actionId, 'completed');
    } catch (err) {
      action.status = 'failed';
      action.error = err instanceof Error ? err.message : String(err);
      action.updatedAt = new Date();
      this.logger.error(`Action failed: ${actionId} — ${action.error}`);

      if (this.config.auditEnabled) {
        void this.audit.append({
          actor: 'HILAChain',
          action: 'HILA_ACTION_EXECUTED',
          entity: actionId,
          status: 'FAILURE',
          details: { error: action.error },
        });
      }

      this.emit(actionId, 'failed');
    }

    return action;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Human Override
  // ─────────────────────────────────────────────────────────────────────────

  /**
   * Human override — a Tier 0 (Human) can approve or reject any action
   * regardless of its current status or required tier.
   */
  humanOverride(actionId: string, humanId: string, decision: 'approve' | 'reject', reason: string): HILAAction | null {
    if (!this.config.humanOverrideEnabled) {
      this.logger.warn('Human override is disabled in HIL-A config');
      return null;
    }

    const action = this.actions.get(actionId);
    if (!action) {
      this.logger.warn(`Action not found: ${actionId}`);
      return null;
    }

    this.clearTierTimer(actionId);

    const hilDecision: HILADecision = {
      id: `DEC-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      tier: 0,
      decidedBy: humanId,
      decision: decision === 'approve' ? 'approve' : 'reject',
      reason: `[HUMAN OVERRIDE] ${reason}`,
      timestamp: new Date(),
    };
    action.decisions.push(hilDecision);
    action.currentTier = 0;
    action.status = decision === 'approve' ? 'approved' : 'rejected';
    action.updatedAt = new Date();

    this.logger.info(`Human override on action ${actionId}: ${decision} by ${humanId}`);

    if (this.config.auditEnabled) {
      void this.audit.append({
        actor: humanId,
        action: 'HILA_HUMAN_OVERRIDE',
        entity: actionId,
        status: decision === 'approve' ? 'SUCCESS' : 'FAILURE',
        details: { decision, reason },
      });
    }

    this.emit(actionId, decision === 'approve' ? 'approved' : 'rejected');
    return action;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Handler Registration
  // ─────────────────────────────────────────────────────────────────────────

  /** Register a handler for a specific tier */
  registerHandler(handler: HILATierHandler): void {
    const handlers = this.handlers.get(handler.tier) ?? [];
    handlers.push(handler);
    this.handlers.set(handler.tier, handlers);
    this.logger.info(`Registered handler for Tier ${handler.tier}: ${handler.entityId}`);
  }

  /** Get all handlers for a specific tier */
  getHandlers(tier: HILATier): HILATierHandler[] {
    return this.handlers.get(tier) ?? [];
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Query & Inspection
  // ─────────────────────────────────────────────────────────────────────────

  /** Get an action by ID */
  getAction(actionId: string): HILAAction | undefined {
    return this.actions.get(actionId);
  }

  /** Get all actions with optional filtering */
  queryActions(filter?: {
    status?: HILAActionStatus;
    category?: HILAActionCategory;
    requestedBy?: string;
    currentTier?: HILATier;
    minTier?: HILATier;
    tags?: string[];
  }): HILAAction[] {
    let results = Array.from(this.actions.values());

    if (filter) {
      if (filter.status) results = results.filter(a => a.status === filter.status);
      if (filter.category) results = results.filter(a => a.category === filter.category);
      if (filter.requestedBy) results = results.filter(a => a.requestedBy === filter.requestedBy);
      if (filter.currentTier !== undefined) results = results.filter(a => a.currentTier === filter.currentTier);
      if (filter.minTier !== undefined) results = results.filter(a => a.minimumApprovalTier >= filter.minTier!);
      if (filter.tags?.length) results = results.filter(a => filter.tags!.some(t => a.tags.includes(t)));
    }

    return results.sort((a, b) => b.priority - a.priority);
  }

  /** Get the minimum approval tier for an action category */
  getMinimumTier(category: HILAActionCategory): HILATier {
    return this.categoryTiers[category];
  }

  /** Get the full decision chain for an action */
  getDecisionChain(actionId: string): HILADecision[] {
    return this.actions.get(actionId)?.decisions ?? [];
  }

  /** Get statistics about the HIL-A chain */
  getStats(): {
    totalActions: number;
    byStatus: Record<HILAActionStatus, number>;
    byCategory: Record<string, number>;
    averageEscalations: number;
    averageTimeToApprovalMs: number;
  } {
    const all = Array.from(this.actions.values());
    const byStatus: Record<string, number> = {};
    const byCategory: Record<string, number> = {};

    for (const action of all) {
      byStatus[action.status] = (byStatus[action.status] ?? 0) + 1;
      byCategory[action.category] = (byCategory[action.category] ?? 0) + 1;
    }

    const approved = all.filter(a => a.status === 'approved' || a.status === 'completed');
    const averageTimeToApprovalMs = approved.length > 0
      ? approved.reduce((sum, a) => {
          const firstDecision = a.decisions.find(d => d.decision === 'approve');
          if (!firstDecision) return sum;
          return sum + (firstDecision.timestamp.getTime() - a.createdAt.getTime());
        }, 0) / approved.length
      : 0;

    return {
      totalActions: all.length,
      byStatus: byStatus as Record<HILAActionStatus, number>,
      byCategory,
      averageEscalations: all.reduce((sum, a) => sum + a.decisions.filter(d => d.decision === 'escalate').length, 0) / (all.length || 1),
      averageTimeToApprovalMs,
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Proactive & Health
  // ─────────────────────────────────────────────────────────────────────────

  /** Check for timed-out actions and escalate them */
  checkTimeouts(): HILAAction[] {
    const now = new Date();
    const timedOut: HILAAction[] = [];

    for (const [, action] of this.actions) {
      if ((action.status === 'pending' || action.status === 'escalated') && action.tierTimeoutAt && now > action.tierTimeoutAt) {
        this.logger.warn(`Action timed out at Tier ${action.currentTier}: ${action.id}`);

        const decision: HILADecision = {
          id: `DEC-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          tier: action.currentTier,
          decidedBy: 'HILAChain',
          decision: 'escalate',
          reason: `Tier ${action.currentTier} timeout (${action.tierTimeoutMs}ms)`,
          timestamp: new Date(),
        };
        action.decisions.push(decision);

        if (this.config.autoEscalateOnTimeout) {
          this.escalate(action.id, 'timeout');
        } else {
          action.status = 'timed_out';
          action.updatedAt = new Date();
          this.clearTierTimer(action.id);
        }

        timedOut.push(action);
      }
    }

    return timedOut;
  }

  /** Proactive: scan for stuck actions and report anomalies */
  scanForAnomalies(): { anomalies: string[]; recommendations: string[] } {
    const anomalies: string[] = [];
    const recommendations: string[] = [];
    const now = new Date();

    for (const [, action] of this.actions) {
      // Stuck pending actions
      if (action.status === 'pending' || action.status === 'escalated') {
        const ageMs = now.getTime() - action.createdAt.getTime();
        if (ageMs > 300000) { // 5 minutes
          anomalies.push(`Action ${action.id} has been pending for ${(ageMs / 1000).toFixed(0)}s`);
          recommendations.push(`Review and manually resolve action ${action.id}`);
        }
      }

      // Actions that have been escalated many times
      const escalationCount = action.decisions.filter(d => d.decision === 'escalate').length;
      if (escalationCount >= 3) {
        anomalies.push(`Action ${action.id} has been escalated ${escalationCount} times`);
        recommendations.push(`Consider human review of action ${action.id}`);
      }

      // Actions rejected multiple times and resubmitted
      if (action.status === 'rejected' && action.decisions.filter(d => d.decision === 'reject').length > 1) {
        anomalies.push(`Action ${action.id} has been rejected multiple times`);
        recommendations.push(`Review the action's requirements and category assignment`);
      }
    }

    return { anomalies, recommendations };
  }

  /** Health check for the HIL-A chain */
  healthCheck(): {
    status: 'healthy' | 'degraded' | 'critical';
    pendingActions: number;
    activeTimers: number;
    registeredHandlers: number;
    anomalies: string[];
  } {
    const anomalies = this.scanForAnomalies();
    const pending = this.queryActions({ status: 'pending' }).length + this.queryActions({ status: 'escalated' }).length;
    const handlerCount = Array.from(this.handlers.values()).reduce((sum, h) => sum + h.length, 0);

    let status: 'healthy' | 'degraded' | 'critical' = 'healthy';
    if (anomalies.anomalies.length > 5) status = 'critical';
    else if (anomalies.anomalies.length > 0 || pending > 20) status = 'degraded';

    return {
      status,
      pendingActions: pending,
      activeTimers: this.timers.size,
      registeredHandlers: handlerCount,
      anomalies: anomalies.anomalies,
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Event System
  // ─────────────────────────────────────────────────────────────────────────

  /** Subscribe to events for a specific action */
  on(actionId: string, listener: (action: HILAAction, event: string) => void): void {
    const listeners = this.listeners.get(actionId) ?? [];
    listeners.push(listener);
    this.listeners.set(actionId, listeners);
  }

  /** Subscribe to all action events */
  onAny(listener: (action: HILAAction, event: string) => void): void {
    const listeners = this.listeners.get('*') ?? [];
    listeners.push(listener);
    this.listeners.set('*', listeners);
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Internal Helpers
  // ─────────────────────────────────────────────────────────────────────────

  private autoApprove(actionId: string, approvedBy: string, tier: HILATier): void {
    const action = this.actions.get(actionId);
    if (!action) return;

    const decision: HILADecision = {
      id: `DEC-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      tier,
      decidedBy: approvedBy,
      decision: 'approve',
      reason: `Auto-approved: requesting tier ${tier} meets minimum tier ${action.minimumApprovalTier}`,
      timestamp: new Date(),
    };
    action.decisions.push(decision);
    action.status = 'approved';
    action.updatedAt = new Date();
    this.clearTierTimer(actionId);

    this.logger.info(`Action auto-approved: ${actionId} (tier ${tier} ≥ minimum ${action.minimumApprovalTier})`);

    if (this.config.auditEnabled) {
      void this.audit.append({
        actor: approvedBy,
        action: 'HILA_AUTO_APPROVED',
        entity: actionId,
        status: 'SUCCESS',
        details: { tier, minimumTier: action.minimumApprovalTier },
      });
    }

    this.emit(actionId, 'approved');
  }

  private startTierTimer(actionId: string): void {
    const action = this.actions.get(actionId);
    if (!action || !action.tierTimeoutAt) return;

    const delay = action.tierTimeoutAt.getTime() - Date.now();
    if (delay <= 0) {
      // Already timed out
      this.checkTimeouts();
      return;
    }

    const timer = setTimeout(() => {
      this.checkTimeouts();
    }, delay);

    this.timers.set(actionId, timer);
  }

  private clearTierTimer(actionId: string): void {
    const timer = this.timers.get(actionId);
    if (timer) {
      clearTimeout(timer);
      this.timers.delete(actionId);
    }
  }

  private emit(actionId: string, event: string): void {
    const action = this.actions.get(actionId);
    if (!action) return;

    // Action-specific listeners
    const listeners = this.listeners.get(actionId) ?? [];
    for (const listener of listeners) {
      try { listener(action, event); } catch { /* swallow */ }
    }

    // Global listeners
    const globalListeners = this.listeners.get('*') ?? [];
    for (const listener of globalListeners) {
      try { listener(action, event); } catch { /* swallow */ }
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Convenience: Auto-Chain — Submit + Execute in one call
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Convenience function that submits an action, waits for approval,
 * and executes it. Returns the final action state.
 */
export async function submitAndWait(
  chain: HILAChain,
  params: Parameters<HILAChain['submitAction']>[0],
  executor: (action: HILAAction) => Promise<unknown>,
  maxWaitMs: number = 300000, // 5 minutes default
): Promise<HILAAction | null> {
  const action = chain.submitAction(params);

  return new Promise((resolve) => {
    const timeout = setTimeout(() => {
      chain.onAny(() => {}); // no-op to keep alive
      resolve(null);
    }, maxWaitMs);

    chain.on(action.id, (updatedAction, event) => {
      if (event === 'approved') {
        clearTimeout(timeout);
        chain.executeAction(action.id, executor).then(resolve);
      } else if (event === 'rejected') {
        clearTimeout(timeout);
        resolve(updatedAction);
      }
    });
  });
}
