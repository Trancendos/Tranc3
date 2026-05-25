/**
 * TollAgent — Rate Limiting & Billing Agent for The API Marketplace
 *
 * Identity:  SID-APIMARKETPLACE-TOLL
 * Tier:      4 (Autonomous Microservice)
 * Parent:    TheAPIMarketplaceAI (AID-APIMARKETPLACE)
 *
 * Responsibilities:
 *   - Assess current rate limit usage for API consumers
 *   - Enforce rate limits with configurable policies
 *   - Report usage metrics and billing summaries
 *   - Manage tier-based access controls
 *   - Track rate limit violations and throttling events
 *
 * "The toll must be paid — but fairness governs the gate."
 */

import { Agent, Logger, AuditLedger } from '../../../core/definitions'

const auditLedger = new AuditLedger();

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface TollInput {
  operation: 'assess' | 'enforce' | 'report';
  consumerId?: string;
  endpointId?: string;
  requestCount?: number;
  windowSeconds?: number;
  tier?: 'free' | 'starter' | 'professional' | 'enterprise';
  action?: 'allow' | 'throttle' | 'reject';
  reportingPeriod?: 'hour' | 'day' | 'week' | 'month';
}

export interface RateLimitPolicy {
  tier: string;
  requestsPerMinute: number;
  requestsPerHour: number;
  requestsPerDay: number;
  burstAllowance: number;
  costPerRequest: number; // in Arcadian credits
}

export interface UsageAssessment {
  consumerId: string;
  currentUsage: number;
  limit: number;
  remaining: number;
  utilisationPercent: number;
  windowStart: number;
  windowEnd: number;
  isExceeded: boolean;
  recommendedAction: 'allow' | 'throttle' | 'reject';
}

export interface EnforcementResult {
  consumerId: string;
  action: 'allowed' | 'throttled' | 'rejected';
  currentUsage: number;
  limit: number;
  retryAfter?: number; // seconds
  penaltyCredits?: number;
  reason: string;
}

export interface UsageReport {
  consumerId: string;
  period: string;
  totalRequests: number;
  successfulRequests: number;
  failedRequests: number;
  throttledRequests: number;
  totalCredits: number;
  breakdownByEndpoint: Record<string, {
    requests: number;
    credits: number;
    averageLatency: number;
  }>;
  recommendations: string[];
}

export interface TollResult {
  success: boolean;
  operation: TollInput['operation'];
  assessment?: UsageAssessment;
  enforcement?: EnforcementResult;
  report?: UsageReport;
  message: string;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Default Rate Limit Policies
// ─────────────────────────────────────────────────────────────────────────────

const DEFAULT_POLICIES: Record<string, RateLimitPolicy> = {
  free: {
    tier: 'free',
    requestsPerMinute: 10,
    requestsPerHour: 100,
    requestsPerDay: 1000,
    burstAllowance: 5,
    costPerRequest: 0,
  },
  starter: {
    tier: 'starter',
    requestsPerMinute: 60,
    requestsPerHour: 1000,
    requestsPerDay: 25000,
    burstAllowance: 20,
    costPerRequest: 0.001,
  },
  professional: {
    tier: 'professional',
    requestsPerMinute: 300,
    requestsPerHour: 10000,
    requestsPerDay: 250000,
    burstAllowance: 100,
    costPerRequest: 0.0005,
  },
  enterprise: {
    tier: 'enterprise',
    requestsPerMinute: 3000,
    requestsPerHour: 100000,
    requestsPerDay: 2500000,
    burstAllowance: 500,
    costPerRequest: 0.0002,
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// TollAgent Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class TollAgent extends Agent {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private readonly policies: Map<string, RateLimitPolicy>;
  private readonly usageTracking: Map<string, { count: number; windowStart: number }>;
  private readonly violationHistory: Map<string, number>; // consumerId → violation count

  constructor() {
    super('SID-APIMARKETPLACE-TOLL');
    this.log = new Logger('TollAgent');
    this.audit = auditLedger;
    this.policies = new Map(Object.entries(DEFAULT_POLICIES));
    this.usageTracking = new Map();
    this.violationHistory = new Map();
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Agent Lifecycle: Perceive → Decide → Act
  // ─────────────────────────────────────────────────────────────────────────

  public async perceive(input: TollInput): Promise<TollInput> {
    this.log.info('Perceiving toll operation', { operation: input.operation });

    // Validate consumer reference
    if (input.consumerId) {
      const usage = this.usageTracking.get(input.consumerId);
      if (!usage) {
        this.log.debug('No prior usage record for consumer', { consumerId: input.consumerId });
      }
    }

    // Validate tier for assessment
    if (input.operation === 'assess' && input.tier && !this.policies.has(input.tier)) {
      this.log.warn('Unknown tier specified', { tier: input.tier });
    }

    return input;
  }

  public async decide(input: TollInput): Promise<string> {
    this.log.info('Deciding toll action', { operation: input.operation });

    switch (input.operation) {
      case 'assess': return 'assessUsage';
      case 'enforce': return 'enforceLimit';
      case 'report': return 'generateReport';
      default: return 'unknown';
    }
  }

  public async act(input: TollInput, decision: string): Promise<TollResult> {
    this.log.info('Acting on toll decision', { decision });

    switch (decision) {
      case 'assessUsage': return this.assessUsage(input);
      case 'enforceLimit': return this.enforceLimit(input);
      case 'generateReport': return this.generateReport(input);
      default:
        return {
          success: false,
          operation: input.operation,
          message: `Unknown operation: ${input.operation}`,
          timestamp: Date.now(),
        };
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Assess Usage
  // ─────────────────────────────────────────────────────────────────────────

  private assessUsage(input: TollInput): TollResult {
    const consumerId = input.consumerId ?? 'CON-UNKNOWN';
    const tier = input.tier ?? 'free';
    const policy = this.policies.get(tier) ?? DEFAULT_POLICIES.free;

    const currentUsage = this.usageTracking.get(consumerId)?.count ?? input.requestCount ?? 0;
    const limit = policy.requestsPerHour;
    const remaining = Math.max(0, limit - currentUsage);
    const utilisationPercent = Math.min(100, Math.floor((currentUsage / limit) * 100));

    let recommendedAction: UsageAssessment['recommendedAction'];
    if (utilisationPercent < 80) {
      recommendedAction = 'allow';
    } else if (utilisationPercent < 100) {
      recommendedAction = 'throttle';
    } else {
      recommendedAction = 'reject';
    }

    const assessment: UsageAssessment = {
      consumerId,
      currentUsage,
      limit,
      remaining,
      utilisationPercent,
      windowStart: Date.now() - 3600000, // 1 hour ago
      windowEnd: Date.now(),
      isExceeded: currentUsage >= limit,
      recommendedAction,
    };

    this.log.info('Usage assessed', {
      consumerId,
      currentUsage,
      limit,
      utilisationPercent,
      recommendedAction,
    });

    return {
      success: true,
      operation: 'assess',
      assessment,
      message: `Consumer ${consumerId} at ${utilisationPercent}% utilisation — ${recommendedAction}`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Enforce Limit
  // ─────────────────────────────────────────────────────────────────────────

  private enforceLimit(input: TollInput): TollResult {
    const consumerId = input.consumerId ?? 'CON-UNKNOWN';
    const tier = input.tier ?? 'free';
    const policy = this.policies.get(tier) ?? DEFAULT_POLICIES.free;

    const currentUsage = this.usageTracking.get(consumerId)?.count ?? input.requestCount ?? 0;
    const limit = policy.requestsPerHour;

    // Update usage tracking
    this.usageTracking.set(consumerId, { count: currentUsage + 1, windowStart: Date.now() });

    let enforcement: EnforcementResult;

    if (currentUsage < limit * 0.8) {
      // Under 80% — allow
      enforcement = {
        consumerId,
        action: 'allowed',
        currentUsage: currentUsage + 1,
        limit,
        reason: 'Within rate limit — request allowed',
      };
    } else if (currentUsage < limit) {
      // 80-100% — throttle
      enforcement = {
        consumerId,
        action: 'throttled',
        currentUsage: currentUsage + 1,
        limit,
        retryAfter: 60, // 60 seconds cooldown
        reason: 'Approaching rate limit — request throttled',
      };

      this.violationHistory.set(consumerId, (this.violationHistory.get(consumerId) ?? 0) + 1);
    } else {
      // Over limit — reject
      const penalty = (currentUsage - limit) * policy.costPerRequest * 10;

      enforcement = {
        consumerId,
        action: 'rejected',
        currentUsage,
        limit,
        retryAfter: 3600, // 1 hour
        penaltyCredits: Math.floor(penalty * 100) / 100,
        reason: `Rate limit exceeded (${currentUsage}/${limit}) — request rejected. ${penalty > 0 ? `Penalty: ${penalty.toFixed(2)} credits` : ''}`,
      };

      this.violationHistory.set(consumerId, (this.violationHistory.get(consumerId) ?? 0) + 1);
    }

    this.audit.append({
      actor: this.id,
      action: 'RATE_LIMIT_ENFORCED',
      entity: consumerId,
      status: enforcement.action === 'rejected' ? 'FAILURE' : 'SUCCESS',
      meta: {
        action: enforcement.action,
        currentUsage: enforcement.currentUsage,
        limit,
        tier,
      },
    });

    this.log.info('Rate limit enforced', {
      consumerId,
      action: enforcement.action,
      currentUsage: enforcement.currentUsage,
      limit,
    });

    return {
      success: enforcement.action !== 'rejected',
      operation: 'enforce',
      enforcement,
      message: `Consumer ${consumerId}: ${enforcement.action} — ${enforcement.reason}`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Generate Report
  // ─────────────────────────────────────────────────────────────────────────

  private generateReport(input: TollInput): TollResult {
    const consumerId = input.consumerId ?? 'CON-ALL';
    const period = input.reportingPeriod ?? 'month';
    const tier = input.tier ?? 'free';
    const policy = this.policies.get(tier) ?? DEFAULT_POLICIES.free;

    const currentUsage = this.usageTracking.get(consumerId)?.count ?? Math.floor(Math.random() * 10000);

    // Simulated report data
    const totalRequests = currentUsage;
    const successRate = 0.95 + Math.random() * 0.04;
    const successfulRequests = Math.floor(totalRequests * successRate);
    const failedRequests = Math.floor(totalRequests * (1 - successRate) * 0.3);
    const throttledRequests = totalRequests - successfulRequests - failedRequests;
    const totalCredits = Math.floor(totalRequests * policy.costPerRequest * 100) / 100;

    // Simulated endpoint breakdown
    const endpoints = ['/api/v1/users', '/api/v1/data', '/api/v1/reports', '/api/v1/auth'];
    const breakdownByEndpoint: UsageReport['breakdownByEndpoint'] = {};
    let remaining = totalRequests;
    for (let i = 0; i < endpoints.length; i++) {
      const share = i < endpoints.length - 1 ? Math.floor(remaining * (0.1 + Math.random() * 0.4)) : remaining;
      remaining -= share;
      breakdownByEndpoint[endpoints[i]] = {
        requests: share,
        credits: Math.floor(share * policy.costPerRequest * 100) / 100,
        averageLatency: Math.floor(20 + Math.random() * 200),
      };
    }

    // Recommendations
    const recommendations: string[] = [];
    if (throttledRequests > totalRequests * 0.05) {
      recommendations.push('High throttle rate detected — consider upgrading tier or optimizing request patterns');
    }
    if (tier === 'free' && totalRequests > 800) {
      recommendations.push('Approaching free tier limits — upgrade to starter tier for higher throughput');
    }
    if (failedRequests > totalRequests * 0.02) {
      recommendations.push('Elevated error rate — review error responses and implement retry logic');
    }

    const report: UsageReport = {
      consumerId,
      period,
      totalRequests,
      successfulRequests,
      failedRequests,
      throttledRequests,
      totalCredits,
      breakdownByEndpoint,
      recommendations,
    };

    this.log.info('Usage report generated', {
      consumerId,
      period,
      totalRequests,
      totalCredits,
    });

    return {
      success: true,
      operation: 'report',
      report,
      message: `Usage report for ${consumerId}: ${totalRequests} requests, ${totalCredits} credits in ${period}`,
      timestamp: Date.now(),
    };
  }
}
