/**
 * Auditor Agent — Town Hall Tier 4 Agent (SID-TOWNHALL-AUDITOR)
 *
 * Autonomous microservice for compliance checks and audit trails.
 * Performs automated compliance verification, detects violations,
 * and maintains the integrity of the audit trail.
 *
 * Perceive: Analyze compliance request and relevant records
 * Decide: Determine compliance status and required actions
 * Act: Execute audit findings and update compliance records
 */

import { Agent, Bot } from '../../../core/definitions';
import { Logger } from '../../../core/logger';
import { AuditLedger } from '../../../core/audit';

const logger = new Logger('AuditorAgent');

/** Compliance status */
export type ComplianceStatus = 'COMPLIANT' | 'WARNING' | 'VIOLATION' | 'CRITICAL';

/** Audit finding severity */
export type FindingSeverity = 'INFO' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

/** Compliance rule */
export interface ComplianceRule {
  id: string;
  name: string;
  description: string;
  category: string;
  check: (data: any) => boolean;
  severity: FindingSeverity;
}

/** Audit finding */
export interface AuditFinding {
  ruleId: string;
  ruleName: string;
  status: ComplianceStatus;
  severity: FindingSeverity;
  description: string;
  evidence: string;
  remediation?: string;
}

/** Audit perception */
export interface AuditPerception {
  requestType: string;
  targetEntity: string;
  records: any[];
  rulesApplicable: ComplianceRule[];
}

/** Audit decision */
export interface AuditDecision {
  overallStatus: ComplianceStatus;
  findings: AuditFinding[];
  requiresAction: boolean;
  escalateTo: string | null;
  confidence: number;
}

/** Audit result */
export interface AuditResult {
  decision: AuditDecision;
  auditId: string;
  timestamp: Date;
}

export class AuditorAgent extends Agent {
  private readonly audit: AuditLedger;
  private readonly complianceRules: ComplianceRule[] = [];
  private readonly findingHistory: AuditFinding[] = [];

  constructor(id: string, audit: AuditLedger) {
    super(id);
    this.audit = audit;
    this.initializeComplianceRules();
    logger.info('AuditorAgent initialized', { id });
  }

  private initializeComplianceRules(): void {
    this.complianceRules.push(
      {
        id: 'CR-001',
        name: 'Data Retention',
        description: 'Verify records are retained within policy limits',
        category: 'data-governance',
        check: (data) => data.retainedDays === undefined || data.retainedDays <= 365,
        severity: 'MEDIUM',
      },
      {
        id: 'CR-002',
        name: 'Access Authorization',
        description: 'Verify all access is authorized',
        category: 'access-control',
        check: (data) => data.authorized === true || data.authorized === undefined,
        severity: 'HIGH',
      },
      {
        id: 'CR-003',
        name: 'Audit Trail Integrity',
        description: 'Verify audit trail has not been tampered with',
        category: 'integrity',
        check: (data) => data.chainValid !== false,
        severity: 'CRITICAL',
      },
      {
        id: 'CR-004',
        name: 'Encryption at Rest',
        description: 'Verify sensitive data is encrypted',
        category: 'security',
        check: (data) => data.encrypted !== false,
        severity: 'HIGH',
      },
    );
  }

  async perceive(observation: any): Promise<AuditPerception> {
    const requestType = observation?.type || 'compliance-check';
    const targetEntity = observation?.entity || 'unknown';
    const records = observation?.records || [];

    const rulesApplicable = this.complianceRules.filter(rule =>
      observation?.categories ? observation.categories.includes(rule.category) : true
    );

    logger.debug('Audit perceived', { requestType, targetEntity, ruleCount: rulesApplicable.length });

    return { requestType, targetEntity, records, rulesApplicable };
  }

  async decide(perceived: AuditPerception): Promise<AuditDecision> {
    const findings: AuditFinding[] = [];
    let worstStatus: ComplianceStatus = 'COMPLIANT';

    for (const rule of perceived.rulesApplicable) {
      for (const record of perceived.records) {
        const passed = rule.check(record);
        const status: ComplianceStatus = passed ? 'COMPLIANT' : rule.severity === 'CRITICAL' ? 'CRITICAL' : 'VIOLATION';

        if (!passed) {
          const finding: AuditFinding = {
            ruleId: rule.id,
            ruleName: rule.name,
            status,
            severity: rule.severity,
            description: rule.description,
            evidence: `Record ${record.id || 'unknown'} failed check: ${rule.name}`,
            remediation: `Address ${rule.category} requirement: ${rule.description}`,
          };
          findings.push(finding);
          this.findingHistory.push(finding);

          // Update worst status
          const severityOrder: ComplianceStatus[] = ['COMPLIANT', 'WARNING', 'VIOLATION', 'CRITICAL'];
          if (severityOrder.indexOf(status) > severityOrder.indexOf(worstStatus)) {
            worstStatus = status;
          }
        }
      }
    }

    const requiresAction = worstStatus !== 'COMPLIANT';
    const escalateTo = worstStatus === 'CRITICAL' ? 'BailiffAgent' : null;
    const confidence = perceived.records.length > 0 ? 0.85 : 0.5;

    return {
      overallStatus: worstStatus,
      findings,
      requiresAction,
      escalateTo,
      confidence,
    };
  }

  async act(decision: AuditDecision): Promise<AuditResult> {
    const auditId = await this.audit.append({
      actor: this.id,
      action: 'AUDIT_COMPLETE',
      entity: 'compliance-check',
      status: decision.requiresAction ? 'FAILURE' : 'SUCCESS',
      meta: {
        overallStatus: decision.overallStatus,
        findingCount: decision.findings.length,
        escalateTo: decision.escalateTo,
      },
    });

    logger.info('Audit completed', {
      status: decision.overallStatus,
      findings: decision.findings.length,
      escalated: decision.escalateTo !== null,
    });

    return { decision, auditId, timestamp: new Date() };
  }

  /** Get finding history */
  getFindings(): AuditFinding[] {
    return [...this.findingHistory];
  }
}
