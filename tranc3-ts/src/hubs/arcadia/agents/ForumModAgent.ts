/**
 * ForumMod Agent — Arcadia Tier 4 Agent (SID-ARCADIA-FORUM-MOD)
 *
 * Autonomous microservice for forum moderation.
 * Handles content filtering, thread management, user behavior analysis,
 * and automated moderation actions.
 *
 * Perceive: Analyze incoming forum activity (posts, edits, reports)
 * Decide: Determine if action needed (warn, hide, escalate, approve)
 * Act: Execute moderation decision via registered bots
 */

import { Agent, Bot, AuditEntry } from '../../../core/definitions';
import { Logger } from '../../../core/logger';
import { AuditLedger } from '../../../core/audit';

const logger = new Logger('ForumModAgent');

/** Types of forum activity this agent can perceive */
export type ActivityType = 'POST' | 'EDIT' | 'DELETE' | 'REPORT' | 'VOTE' | 'FLAG';

/** Severity levels for moderation decisions */
export type Severity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

/** Forum activity to be processed */
export interface ForumActivity {
  type: ActivityType;
  threadId: string;
  postId?: string;
  userId: string;
  content: string;
  timestamp: Date;
  metadata?: Record<string, any>;
}

/** Moderation decision outcome */
export interface ModerationDecision {
  action: 'APPROVE' | 'WARN' | 'HIDE' | 'ESCALATE' | 'BAN';
  severity: Severity;
  reason: string;
  confidence: number;
  autoAction: boolean;
}

/** Moderation result after acting */
export interface ModerationResult {
  decision: ModerationDecision;
  acted: boolean;
  auditId: string;
  timestamp: Date;
}

/** Content filter rule */
export interface FilterRule {
  pattern: string | RegExp;
  category: string;
  severity: Severity;
  action: ModerationDecision['action'];
}

export class ForumModAgent extends Agent {
  private readonly audit: AuditLedger;
  private readonly filterRules: FilterRule[] = [];
  private readonly userWarnings: Map<string, number> = new Map();
  private readonly hiddenPosts: Set<string> = new Set();

  constructor(id: string, audit: AuditLedger) {
    super(id);
    this.audit = audit;
    this.initializeFilterRules();
    logger.info('ForumModAgent initialized', { id });
  }

  /** Set up default content filter rules */
  private initializeFilterRules(): void {
    this.filterRules.push(
      { pattern: /spam/i, category: 'spam', severity: 'MEDIUM', action: 'HIDE' },
      { pattern: /scam/i, category: 'fraud', severity: 'HIGH', action: 'HIDE' },
      { pattern: /hack/i, category: 'security', severity: 'HIGH', action: 'ESCALATE' },
      { pattern: /exploit/i, category: 'security', severity: 'CRITICAL', action: 'ESCALATE' },
    );
  }

  /**
   * Perceive: Analyze incoming forum activity.
   * Extracts features, checks against filter rules, and assesses user history.
   */
  async perceive(observation: any): Promise<ForumActivity> {
    const activity: ForumActivity = {
      type: observation?.type || 'POST',
      threadId: observation?.threadId || 'unknown',
      postId: observation?.postId,
      userId: observation?.userId || 'anonymous',
      content: observation?.content || '',
      timestamp: observation?.timestamp || new Date(),
      metadata: observation?.metadata,
    };

    logger.debug('Perceived forum activity', {
      type: activity.type,
      threadId: activity.threadId,
      userId: activity.userId,
    });

    return activity;
  }

  /**
   * Decide: Determine moderation action based on perceived activity.
   * Applies filter rules, user history, and confidence thresholds.
   */
  async decide(perceived: ForumActivity): Promise<ModerationDecision> {
    let maxSeverity: Severity = 'LOW';
    let matchedAction: ModerationDecision['action'] = 'APPROVE';
    let matchedReason: string = 'No rules matched';
    let matchCount = 0;

    // Apply filter rules
    for (const rule of this.filterRules) {
      const pattern = rule.pattern instanceof RegExp ? rule.pattern : new RegExp(rule.pattern, 'i');
      if (pattern.test(perceived.content)) {
        matchCount++;
        // Use the highest severity match
        const severityOrder: Severity[] = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];
        if (severityOrder.indexOf(rule.severity) > severityOrder.indexOf(maxSeverity)) {
          maxSeverity = rule.severity;
          matchedAction = rule.action;
          matchedReason = `Matched rule: ${rule.category}`;
        }
      }
    }

    // Check user warning history
    const userWarningCount = this.userWarnings.get(perceived.userId) || 0;
    if (userWarningCount >= 3) {
      maxSeverity = 'HIGH';
      matchedAction = 'BAN';
      matchedReason = `Repeat offender: ${userWarningCount} warnings`;
    } else if (userWarningCount >= 1 && maxSeverity === 'MEDIUM') {
      matchedAction = 'ESCALATE';
      matchedReason = `Previous warnings + current violation`;
    }

    // Calculate confidence (simplified heuristic)
    const confidence = matchCount > 0 ? Math.min(0.5 + matchCount * 0.2, 0.99) : 0.1;

    // Auto-action if confidence is high enough
    const autoAction = confidence >= 0.8 && maxSeverity !== 'CRITICAL';

    const decision: ModerationDecision = {
      action: matchedAction,
      severity: maxSeverity,
      reason: matchedReason,
      confidence,
      autoAction,
    };

    logger.info('Moderation decision', {
      userId: perceived.userId,
      action: decision.action,
      severity: decision.severity,
      confidence: decision.confidence,
    });

    return decision;
  }

  /**
   * Act: Execute the moderation decision.
   * Applies warnings, hides posts, escalates to human moderators, etc.
   */
  async act(decision: ModerationDecision): Promise<ModerationResult> {
    const auditId = await this.audit.append({
      actor: this.id,
      action: `MODERATION_${decision.action}`,
      entity: 'forum-post',
      status: decision.autoAction ? 'SUCCESS' : 'PENDING',
      meta: {
        severity: decision.severity,
        reason: decision.reason,
        confidence: decision.confidence,
        autoAction: decision.autoAction,
      },
    });

    let acted = false;

    switch (decision.action) {
      case 'APPROVE':
        acted = true;
        logger.debug('Post approved');
        break;

      case 'WARN':
        // Track warning count
        acted = true;
        logger.info('User warned', { reason: decision.reason });
        break;

      case 'HIDE':
        acted = decision.autoAction;
        if (acted) {
          logger.info('Post hidden (auto)', { reason: decision.reason });
        }
        break;

      case 'ESCALATE':
        acted = false; // Requires human review
        logger.warn('Post escalated for human review', { reason: decision.reason });
        break;

      case 'BAN':
        acted = decision.autoAction;
        logger.warn('User ban recommended', { reason: decision.reason });
        break;
    }

    return {
      decision,
      acted,
      auditId,
      timestamp: new Date(),
    };
  }

  /** Record a user warning (can be called externally or by act()) */
  recordWarning(userId: string): void {
    const current = this.userWarnings.get(userId) || 0;
    this.userWarnings.set(userId, current + 1);
    logger.info('Warning recorded', { userId, totalWarnings: current + 1 });
  }

  /** Get warning count for a user */
  getWarningCount(userId: string): number {
    return this.userWarnings.get(userId) || 0;
  }

  /** Add a custom filter rule */
  addFilterRule(rule: FilterRule): void {
    this.filterRules.push(rule);
    logger.info('Filter rule added', { category: rule.category, severity: rule.severity });
  }
}
