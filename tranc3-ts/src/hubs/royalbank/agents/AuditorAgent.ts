/**
 * AuditorAgent — Compliance & Fraud Detection Agent for The Royal Bank of Arcadia
 *
 * Identity:  SID-ROYALBANK-AUDITOR
 * Tier:      4 (Autonomous Microservice)
 * Parent:    RoyalBankOfArcadiaAI (AID-ROYALBANK)
 *
 * Responsibilities:
 *   - Inspect transactions and accounts for suspicious activity
 *   - Flag transactions that trigger fraud detection rules
 *   - Ensure compliance with Arcadian financial regulations
 *   - Settle disputes and resolve fraud alerts
 *   - Maintain audit trail integrity and evidence chains
 *
 * "The Auditor sees what the Teller overlooks. Trust is verified, not assumed."
 */

import { Agent, Logger, AuditLedger } from '../../../core/definitions';

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface AuditorInput {
  operation: 'inspect' | 'flag' | 'comply' | 'settle';
  transactionId?: string;
  accountId?: string;
  alertId?: string;
  alertType?: 'unusual_amount' | 'rapid_transactions' | 'new_recipient' | 'geographic_anomaly' | 'pattern_match';
  severity?: 'low' | 'medium' | 'high' | 'critical';
  resolution?: 'confirmed_fraud' | 'false_positive' | 'under_investigation';
  regulationCode?: string;
  timeWindow?: number; // milliseconds
  maxResults?: number;
}

export interface FraudAlertRecord {
  id: string;
  transactionId: string;
  accountId: string;
  alertType: AuditorInput['alertType'];
  severity: AuditorInput['severity'];
  description: string;
  detectedAt: number;
  reviewedAt?: number;
  resolution?: AuditorInput['resolution'];
  reviewedBy?: string;
  evidence: string[];
}

export interface InspectionResult {
  inspectedEntity: string;
  inspectionType: 'transaction' | 'account' | 'timeframe';
  riskScore: number; // 0-100
  riskLevel: 'minimal' | 'low' | 'medium' | 'high' | 'critical';
  findings: InspectionFinding[];
  anomaliesDetected: number;
  totalRecordsScanned: number;
  recommendations: string[];
  inspectedAt: number;
}

export interface InspectionFinding {
  type: 'amount_anomaly' | 'frequency_anomaly' | 'pattern_anomaly' | 'compliance_violation' | 'velocity_spike';
  severity: 'info' | 'warning' | 'critical';
  description: string;
  relatedTransactionId?: string;
  relatedAccountId?: string;
  riskContribution: number; // 0-100
}

export interface ComplianceReport {
  regulationCode: string;
  compliant: boolean;
  complianceScore: number; // 0-100
  violations: ComplianceViolation[];
  checkedAt: number;
  nextReviewDate: number;
}

export interface ComplianceViolation {
  code: string;
  description: string;
  severity: 'minor' | 'major' | 'critical';
  affectedEntity: string;
  remediation: string;
  deadline: number;
}

export interface SettlementResult {
  alertId: string;
  resolution: AuditorInput['resolution'];
  settledAt: number;
  settledBy: string;
  affectedTransactions: string[];
  recoveryAmount: number;
  accountActions: ('freeze' | 'unfreeze' | 'flag' | 'restrict')[];
  notes: string;
}

export interface AuditorResult {
  success: boolean;
  operation: AuditorInput['operation'];
  inspection?: InspectionResult;
  alert?: FraudAlertRecord;
  compliance?: ComplianceReport;
  settlement?: SettlementResult;
  message: string;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Fraud Detection Rules
// ─────────────────────────────────────────────────────────────────────────────

const FRAUD_RULES = {
  unusual_amount: {
    personalThreshold: 5000,
    businessThreshold: 50000,
    treasuryThreshold: 500000,
    description: 'Transaction amount exceeds typical range for account type',
  },
  rapid_transactions: {
    maxPerMinute: 10,
    maxPerHour: 50,
    description: 'Transaction frequency exceeds normal patterns',
  },
  new_recipient: {
    firstTransactionWeight: 0.3,
    description: 'Transfer to previously unseen account',
  },
  geographic_anomaly: {
    description: 'Transaction originates from unusual location or pattern',
  },
  pattern_match: {
    knownPatterns: ['structuring', 'layering', 'round_tripping', 'wash_trading'],
    description: 'Transaction matches known money laundering pattern',
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// Compliance Regulations
// ─────────────────────────────────────────────────────────────────────────────

const REGULATIONS: Record<string, {
  name: string;
  description: string;
  checks: { code: string; description: string; weight: number }[];
}> = {
  'ARC-KYC': {
    name: 'Arcadian Know Your Customer',
    description: 'Customer identification and verification requirements',
    checks: [
      { code: 'KYC-001', description: 'Account holder identity verified', weight: 25 },
      { code: 'KYC-002', description: 'Beneficial ownership declared', weight: 20 },
      { code: 'KYC-003', description: 'Source of funds documented', weight: 25 },
      { code: 'KYC-004', description: 'Risk assessment completed', weight: 15 },
      { code: 'KYC-005', description: 'Ongoing monitoring in place', weight: 15 },
    ],
  },
  'ARC-AML': {
    name: 'Arcadian Anti-Money Laundering',
    description: 'Anti-money laundering detection and reporting requirements',
    checks: [
      { code: 'AML-001', description: 'Suspicious activity monitoring active', weight: 30 },
      { code: 'AML-002', description: 'Currency transaction reporting threshold', weight: 25 },
      { code: 'AML-003', description: 'Structuring detection enabled', weight: 20 },
      { code: 'AML-004', description: 'Sanctions screening completed', weight: 25 },
    ],
  },
  'ARC-CTR': {
    name: 'Arcadian Currency Transaction Reporting',
    description: 'Reporting requirements for large currency transactions',
    checks: [
      { code: 'CTR-001', description: 'Transactions above threshold reported', weight: 35 },
      { code: 'CTR-002', description: 'Aggregation rules applied correctly', weight: 30 },
      { code: 'CTR-003', description: 'Filing deadlines met', weight: 35 },
    ],
  },
  'ARC-DATA': {
    name: 'Arcadian Data Protection',
    description: 'Financial data protection and privacy requirements',
    checks: [
      { code: 'DATA-001', description: 'Personal data encrypted at rest', weight: 20 },
      { code: 'DATA-002', description: 'Access controls properly configured', weight: 20 },
      { code: 'DATA-003', description: 'Data retention policies enforced', weight: 20 },
      { code: 'DATA-004', description: 'Audit logs immutable and complete', weight: 20 },
      { code: 'DATA-005', description: 'Right to erasure supported', weight: 20 },
    ],
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// AuditorAgent Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class AuditorAgent extends Agent {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private readonly fraudAlerts: Map<string, FraudAlertRecord>;
  private alertCounter: number;

  constructor() {
    super('SID-ROYALBANK-AUDITOR');
    this.log = new Logger('AuditorAgent');
    this.audit = AuditLedger.getInstance();
    this.fraudAlerts = new Map();
    this.alertCounter = 0;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Agent Lifecycle: Perceive → Decide → Act
  // ─────────────────────────────────────────────────────────────────────────

  protected async perceive(input: AuditorInput): Promise<AuditorInput> {
    this.log.info('Perceiving audit operation', { operation: input.operation });

    // Validate operation-specific requirements
    if (input.operation === 'flag' && !input.transactionId) {
      this.log.warn('Flag operation requires transactionId');
    }

    if (input.operation === 'comply' && !input.regulationCode) {
      this.log.warn('Comply operation requires regulationCode — defaulting to ARC-KYC');
      input.regulationCode = 'ARC-KYC';
    }

    if (input.operation === 'settle' && !input.alertId) {
      this.log.warn('Settle operation requires alertId');
    }

    return input;
  }

  protected async decide(input: AuditorInput): Promise<string> {
    this.log.info('Deciding audit action', { operation: input.operation });

    switch (input.operation) {
      case 'inspect': return 'runInspection';
      case 'flag': return 'flagTransaction';
      case 'comply': return 'checkCompliance';
      case 'settle': return 'settleAlert';
      default: return 'unknown';
    }
  }

  protected async act(input: AuditorInput, decision: string): Promise<AuditorResult> {
    this.log.info('Acting on audit decision', { decision });

    switch (decision) {
      case 'runInspection': return this.runInspection(input);
      case 'flagTransaction': return this.flagTransaction(input);
      case 'checkCompliance': return this.checkCompliance(input);
      case 'settleAlert': return this.settleAlert(input);
      default:
        return {
          success: false,
          operation: input.operation,
          message: `Unknown audit operation: ${input.operation}`,
          timestamp: Date.now(),
        };
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Inspect — Scan for anomalies and suspicious activity
  // ─────────────────────────────────────────────────────────────────────────

  private runInspection(input: AuditorInput): AuditorResult {
    const { transactionId, accountId, timeWindow } = input;
    const findings: InspectionFinding[] = [];
    let totalRecordsScanned = 0;
    let anomaliesDetected = 0;

    // Simulate inspection of a specific transaction
    if (transactionId) {
      totalRecordsScanned++;

      // Simulate amount anomaly detection
      const simulatedAmount = Math.floor(Math.random() * 100000);
      if (simulatedAmount > FRAUD_RULES.unusual_amount.personalThreshold) {
        findings.push({
          type: 'amount_anomaly',
          severity: simulatedAmount > FRAUD_RULES.unusual_amount.businessThreshold ? 'critical' : 'warning',
          description: `Transaction ${transactionId} involves ${simulatedAmount} credits — exceeds typical range`,
          relatedTransactionId: transactionId,
          riskContribution: Math.min(100, Math.floor(simulatedAmount / 100)),
        });
        anomaliesDetected++;
      }

      // Simulate velocity spike detection
      const simulatedFrequency = Math.floor(Math.random() * 15);
      if (simulatedFrequency > FRAUD_RULES.rapid_transactions.maxPerMinute) {
        findings.push({
          type: 'velocity_spike',
          severity: 'critical',
          description: `${simulatedFrequency} transactions in last minute from account associated with ${transactionId}`,
          relatedTransactionId: transactionId,
          riskContribution: 70,
        });
        anomaliesDetected++;
      }

      // Simulate pattern match
      if (Math.random() < 0.15) {
        const matchedPattern = FRAUD_RULES.pattern_match.knownPatterns[
          Math.floor(Math.random() * FRAUD_RULES.pattern_match.knownPatterns.length)
        ];
        findings.push({
          type: 'pattern_anomaly',
          severity: 'critical',
          description: `Transaction ${transactionId} matches known pattern: ${matchedPattern}`,
          relatedTransactionId: transactionId,
          riskContribution: 85,
        });
        anomaliesDetected++;
      }
    }

    // Simulate account-level inspection
    if (accountId) {
      totalRecordsScanned += 50; // Simulate scanning recent account activity

      // Check for new recipient anomaly
      if (Math.random() < 0.2) {
        findings.push({
          type: 'frequency_anomaly',
          severity: 'warning',
          description: `Account ${accountId} has multiple new recipients in recent transactions`,
          relatedAccountId: accountId,
          riskContribution: 35,
        });
        anomaliesDetected++;
      }
    }

    // Calculate overall risk score from findings
    const riskScore = findings.length > 0
      ? Math.min(100, findings.reduce((sum, f) => sum + f.riskContribution, 0) / findings.length + anomaliesDetected * 10)
      : Math.floor(Math.random() * 15); // Low baseline risk when no findings

    const riskLevel: InspectionResult['riskLevel'] =
      riskScore >= 80 ? 'critical' :
      riskScore >= 60 ? 'high' :
      riskScore >= 40 ? 'medium' :
      riskScore >= 20 ? 'low' : 'minimal';

    const recommendations: string[] = [];
    if (riskLevel === 'critical') {
      recommendations.push('Immediately freeze account and escalate to Norman Hawkins');
      recommendations.push('Preserve all transaction evidence for investigation');
    }
    if (riskLevel === 'high') {
      recommendations.push('Flag all recent transactions for manual review');
      recommendations.push('Restrict account to inbound transactions only');
    }
    if (riskLevel === 'medium') {
      recommendations.push('Increase monitoring frequency for this account');
      recommendations.push('Request additional verification from account holder');
    }
    if (findings.some(f => f.type === 'pattern_anomaly')) {
      recommendations.push('File Suspicious Activity Report (SAR) within 24 hours');
    }
    if (recommendations.length === 0) {
      recommendations.push('No immediate action required — continue standard monitoring');
    }

    const inspection: InspectionResult = {
      inspectedEntity: transactionId ?? accountId ?? 'unknown',
      inspectionType: transactionId ? 'transaction' : accountId ? 'account' : 'timeframe',
      riskScore,
      riskLevel,
      findings,
      anomaliesDetected,
      totalRecordsScanned,
      recommendations,
      inspectedAt: Date.now(),
    };

    this.audit.append({
      actor: this.id,
      action: 'INSPECTION_COMPLETED',
      entity: inspection.inspectedEntity,
      status: 'SUCCESS',
      meta: {
        riskScore,
        riskLevel,
        anomaliesDetected,
        findingsCount: findings.length,
      },
    });

    this.log.info('Inspection completed', {
      inspectedEntity: inspection.inspectedEntity,
      riskScore,
      riskLevel,
      anomaliesDetected,
    });

    return {
      success: true,
      operation: 'inspect',
      inspection,
      message: `Inspection of ${inspection.inspectedEntity}: risk score ${riskScore} (${riskLevel}), ${anomaliesDetected} anomalies detected`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Flag — Create a fraud alert for a transaction
  // ─────────────────────────────────────────────────────────────────────────

  private flagTransaction(input: AuditorInput): AuditorResult {
    const { transactionId, accountId, alertType, severity } = input;

    if (!transactionId) {
      return {
        success: false,
        operation: 'flag',
        message: 'Transaction ID is required to flag a transaction',
        timestamp: Date.now(),
      };
    }

    this.alertCounter++;
    const alertId = `FRAUD-${this.alertCounter}`;
    const resolvedAlertType = alertType ?? 'unusual_amount';
    const resolvedSeverity = severity ?? 'medium';

    // Build evidence chain
    const evidence: string[] = [
      `Transaction ${transactionId} flagged for ${resolvedAlertType}`,
      `Account ${accountId ?? 'unknown'} associated with flagged activity`,
      `Alert severity assessed as ${resolvedSeverity}`,
      `Detection timestamp: ${new Date().toISOString()}`,
    ];

    // Add type-specific evidence
    switch (resolvedAlertType) {
      case 'unusual_amount':
        evidence.push('Transaction amount exceeds statistical deviation from account baseline');
        break;
      case 'rapid_transactions':
        evidence.push('Transaction frequency exceeds configured rate thresholds');
        break;
      case 'new_recipient':
        evidence.push('Recipient account has no prior transaction history with sender');
        break;
      case 'geographic_anomaly':
        evidence.push('Transaction origin does not match account holder profile');
        break;
      case 'pattern_match':
        evidence.push('Transaction sequence matches known suspicious pattern signature');
        break;
    }

    const alert: FraudAlertRecord = {
      id: alertId,
      transactionId,
      accountId: accountId ?? 'unknown',
      alertType: resolvedAlertType,
      severity: resolvedSeverity,
      description: `Fraud alert ${alertId}: ${resolvedAlertType} detected on transaction ${transactionId}`,
      detectedAt: Date.now(),
      evidence,
    };

    this.fraudAlerts.set(alertId, alert);

    this.audit.append({
      actor: this.id,
      action: 'TRANSACTION_FLAGGED',
      entity: transactionId,
      status: 'PENDING',
      meta: {
        alertId,
        alertType: resolvedAlertType,
        severity: resolvedSeverity,
        accountId: accountId ?? 'unknown',
      },
    });

    this.log.warn('Transaction flagged for fraud', {
      alertId,
      transactionId,
      alertType: resolvedAlertType,
      severity: resolvedSeverity,
    });

    return {
      success: true,
      operation: 'flag',
      alert,
      message: `Fraud alert ${alertId} created for transaction ${transactionId} (${resolvedAlertType}, ${resolvedSeverity})`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Comply — Check regulatory compliance
  // ─────────────────────────────────────────────────────────────────────────

  private checkCompliance(input: AuditorInput): AuditorResult {
    const { regulationCode, accountId } = input;
    const resolvedCode = regulationCode ?? 'ARC-KYC';

    const regulation = REGULATIONS[resolvedCode];
    if (!regulation) {
      return {
        success: false,
        operation: 'comply',
        message: `Unknown regulation code: ${resolvedCode}. Valid codes: ${Object.keys(REGULATIONS).join(', ')}`,
        timestamp: Date.now(),
      };
    }

    // Simulate compliance checking
    const violations: ComplianceViolation[] = [];
    let complianceScore = 100;

    for (const check of regulation.checks) {
      // Simulate ~85% pass rate per check
      const passed = Math.random() < 0.85;
      if (!passed) {
        const severity: ComplianceViolation['severity'] =
          check.weight >= 30 ? 'critical' :
          check.weight >= 20 ? 'major' : 'minor';

        const violation: ComplianceViolation = {
          code: check.code,
          description: check.description,
          severity,
          affectedEntity: accountId ?? 'system',
          remediation: `Remediate ${check.code}: ${check.description}`,
          deadline: Date.now() + (severity === 'critical' ? 7 : severity === 'major' ? 30 : 90) * 86400000,
        };
        violations.push(violation);
        complianceScore -= check.weight;
      }
    }

    complianceScore = Math.max(0, complianceScore);
    const compliant = complianceScore >= 70;

    const compliance: ComplianceReport = {
      regulationCode: resolvedCode,
      compliant,
      complianceScore,
      violations,
      checkedAt: Date.now(),
      nextReviewDate: Date.now() + 90 * 86400000, // 90 days
    };

    this.audit.append({
      actor: this.id,
      action: 'COMPLIANCE_CHECK',
      entity: resolvedCode,
      status: compliant ? 'SUCCESS' : 'FAILURE',
      meta: {
        complianceScore,
        violationsCount: violations.length,
        accountId: accountId ?? 'system',
      },
    });

    this.log.info('Compliance check completed', {
      regulationCode: resolvedCode,
      complianceScore,
      compliant,
      violationsCount: violations.length,
    });

    return {
      success: true,
      operation: 'comply',
      compliance,
      message: `${regulation.name} compliance: ${complianceScore}/100 (${compliant ? 'COMPLIANT' : 'NON-COMPLIANT'}) — ${violations.length} violations found`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Settle — Resolve a fraud alert
  // ─────────────────────────────────────────────────────────────────────────

  private settleAlert(input: AuditorInput): AuditorResult {
    const { alertId, resolution } = input;

    if (!alertId) {
      return {
        success: false,
        operation: 'settle',
        message: 'Alert ID is required to settle a fraud alert',
        timestamp: Date.now(),
      };
    }

    const alert = this.fraudAlerts.get(alertId);
    if (!alert) {
      return {
        success: false,
        operation: 'settle',
        message: `Fraud alert ${alertId} not found`,
        timestamp: Date.now(),
      };
    }

    if (alert.resolution) {
      return {
        success: false,
        operation: 'settle',
        message: `Fraud alert ${alertId} already resolved as ${alert.resolution}`,
        timestamp: Date.now(),
      };
    }

    const resolvedAs = resolution ?? 'under_investigation';

    // Update the alert record
    alert.reviewedAt = Date.now();
    alert.resolution = resolvedAs;
    alert.reviewedBy = this.id;

    // Determine account actions based on resolution
    const accountActions: SettlementResult['accountActions'] = [];
    let recoveryAmount = 0;

    switch (resolvedAs) {
      case 'confirmed_fraud':
        accountActions.push('freeze', 'flag', 'restrict');
        recoveryAmount = Math.floor(Math.random() * 50000); // Simulated recovery
        break;
      case 'false_positive':
        accountActions.push('unfreeze');
        break;
      case 'under_investigation':
        accountActions.push('flag', 'restrict');
        break;
    }

    // Build affected transactions list
    const affectedTransactions = [alert.transactionId];
    if (resolvedAs === 'confirmed_fraud') {
      // Simulate discovering related transactions
      const relatedCount = Math.floor(Math.random() * 3) + 1;
      for (let i = 0; i < relatedCount; i++) {
        affectedTransactions.push(`TXN-RELATED-${alertId}-${i + 1}`);
      }
    }

    const settlement: SettlementResult = {
      alertId,
      resolution: resolvedAs,
      settledAt: Date.now(),
      settledBy: this.id,
      affectedTransactions,
      recoveryAmount,
      accountActions,
      notes: `Alert ${alertId} resolved as ${resolvedAs}. ${accountActions.length} account action(s) taken. ${affectedTransactions.length} transaction(s) affected.`,
    };

    this.audit.append({
      actor: this.id,
      action: 'ALERT_SETTLED',
      entity: alertId,
      status: 'SUCCESS',
      meta: {
        resolution: resolvedAs,
        accountActions,
        affectedTransactionsCount: affectedTransactions.length,
        recoveryAmount,
      },
    });

    this.log.info('Fraud alert settled', {
      alertId,
      resolution: resolvedAs,
      accountActions,
      recoveryAmount,
    });

    return {
      success: true,
      operation: 'settle',
      settlement,
      message: `Alert ${alertId} settled as ${resolvedAs}. Recovery: ${recoveryAmount} credits. Actions: ${accountActions.join(', ')}`,
      timestamp: Date.now(),
    };
  }
}
