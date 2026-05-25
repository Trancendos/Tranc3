/**
 * Bailiff Agent — Town Hall Tier 4 Agent (SID-TOWNHALL-BAILIFF)
 *
 * Autonomous microservice for order maintenance and protocol enforcement.
 * Manages session lifecycle, enforces procedural rules, maintains
 * decorum, and ensures proper order of operations.
 *
 * Perceive: Analyze session state and procedural compliance
 * Decide: Determine if order is maintained or intervention needed
 * Act: Execute procedural enforcement actions
 */

import { Agent, Bot } from '../../../core/definitions';
import { Logger } from '../../../core/logger';
import { AuditLedger } from '../../../core/audit';

const logger = new Logger('BailiffAgent');

/** Session state */
export type SessionState = 'NOT_STARTED' | 'IN_SESSION' | 'RECESS' | 'ADJOURNED' | 'EMERGENCY';

/** Procedural violation types */
export type ViolationType = 'OUT_OF_ORDER' | 'DECORUM_BREACH' | 'UNAUTHORIZED_ACTION' | 'QUORUM_FAILURE' | 'TIMEOUT';

/** Session event */
export interface SessionEvent {
  type: 'ENTER' | 'LEAVE' | 'SPEAK' | 'VOTE' | 'OBJECT' | 'MOTION';
  participantId: string;
  timestamp: Date;
  data?: Record<string, any>;
}

/** Procedural violation */
export interface ProceduralViolation {
  type: ViolationType;
  participantId: string;
  description: string;
  severity: 'WARNING' | 'REPRIMAND' | 'EJECTION';
  timestamp: Date;
}

/** Bailiff perception */
export interface BailiffPerception {
  sessionState: SessionState;
  participantCount: number;
  recentEvents: SessionEvent[];
  activeViolations: ProceduralViolation[];
  quorumMet: boolean;
}

/** Bailiff decision */
export interface BailiffDecision {
  action: 'ALLOW' | 'WARN' | 'RECESS' | 'ADJOURN' | 'EJECT' | 'EMERGENCY_SESSION';
  reason: string;
  targetParticipant?: string;
  newSessionState?: SessionState;
}

/** Bailiff result */
export interface BailiffResult {
  decision: BailiffDecision;
  sessionState: SessionState;
  auditId: string;
}

export class BailiffAgent extends Agent {
  private readonly audit: AuditLedger;
  private readonly sessionTimeoutMinutes: number;
  private currentSessionState: SessionState = 'NOT_STARTED';
  private readonly participants: Set<string> = new Set();
  private readonly violations: ProceduralViolation[] = [];

  constructor(id: string, audit: AuditLedger, sessionTimeoutMinutes: number = 60) {
    super(id);
    this.audit = audit;
    this.sessionTimeoutMinutes = sessionTimeoutMinutes;
    logger.info('BailiffAgent initialized', { id, sessionTimeoutMinutes });
  }

  async perceive(observation: any): Promise<BailiffPerception> {
    const recentEvents: SessionEvent[] = observation?.events || [];
    const quorumMet = this.participants.size >= (observation?.quorumRequired || 3);

    logger.debug('Bailiff perceived', {
      sessionState: this.currentSessionState,
      participants: this.participants.size,
      quorumMet,
    });

    return {
      sessionState: this.currentSessionState,
      participantCount: this.participants.size,
      recentEvents,
      activeViolations: [...this.violations],
      quorumMet,
    };
  }

  async decide(perceived: BailiffPerception): Promise<BailiffDecision> {
    // Emergency: quorum lost during session
    if (perceived.sessionState === 'IN_SESSION' && !perceived.quorumMet) {
      return {
        action: 'RECESS',
        reason: 'Quorum no longer met — calling recess',
        newSessionState: 'RECESS',
      };
    }

    // Check for severe violations
    const severeViolations = perceived.activeViolations.filter(v => v.severity === 'EJECTION');
    if (severeViolations.length > 0) {
      return {
        action: 'EJECT',
        reason: `Severe violation by ${severeViolations[0].participantId}`,
        targetParticipant: severeViolations[0].participantId,
      };
    }

    // Check for moderate violations
    const moderateViolations = perceived.activeViolations.filter(v => v.severity === 'REPRIMAND');
    if (moderateViolations.length > 2) {
      return {
        action: 'WARN',
        reason: `${moderateViolations.length} reprimands issued — session decorum declining`,
      };
    }

    return {
      action: 'ALLOW',
      reason: 'Session proceeding within protocol',
    };
  }

  async act(decision: BailiffDecision): Promise<BailiffResult> {
    // Update session state if needed
    if (decision.newSessionState) {
      this.currentSessionState = decision.newSessionState;
    }

    // Handle ejection
    if (decision.action === 'EJECT' && decision.targetParticipant) {
      this.participants.delete(decision.targetParticipant);
    }

    const auditId = await this.audit.append({
      actor: this.id,
      action: `BAILIFF_${decision.action}`,
      entity: decision.targetParticipant || 'session',
      status: decision.action === 'ALLOW' ? 'SUCCESS' : 'PENDING',
      meta: { reason: decision.reason },
    });

    logger.info('Bailiff action', { action: decision.action, reason: decision.reason });

    return {
      decision,
      sessionState: this.currentSessionState,
      auditId,
    };
  }

  /** Register a participant */
  registerParticipant(id: string): void {
    this.participants.add(id);
  }

  /** Remove a participant */
  removeParticipant(id: string): void {
    this.participants.delete(id);
  }

  /** Record a procedural violation */
  recordViolation(violation: ProceduralViolation): void {
    this.violations.push(violation);
    logger.warn('Violation recorded', { type: violation.type, participant: violation.participantId });
  }

  /** Get current session state */
  getSessionState(): SessionState {
    return this.currentSessionState;
  }
}
