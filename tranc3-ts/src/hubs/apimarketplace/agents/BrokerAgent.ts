/**
 * BrokerAgent — API Lifecycle & Contract Agent for The API Marketplace
 *
 * Identity:  SID-APIMARKETPLACE-BROKER
 * Tier:      4 (Autonomous Microservice)
 * Parent:    TheAPIMarketplaceAI (AID-APIMARKETPLACE)
 *
 * Responsibilities:
 *   - Publish new API endpoints to the marketplace
 *   - Deprecate endpoints with migration guidance
 *   - Sunset retired endpoints after grace periods
 *   - Negotiate API contracts between producers and consumers
 *   - Track lifecycle transitions and contract changes
 *
 * "A good broker makes both sides feel like they won."
 */

import { Agent, Logger, AuditLedger } from '../../../core/definitions';

// ─────────────────────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────────────────────

export interface BrokerInput {
  operation: 'publish' | 'deprecate' | 'sunset' | 'negotiate';
  endpointId?: string;
  endpointName?: string;
  method?: string;
  path?: string;
  basePath?: string;
  version?: string;
  visibility?: 'public' | 'internal' | 'partner';
  authentication?: 'none' | 'apikey' | 'oauth2' | 'jwt' | 'mtls';
  deprecationReason?: string;
  replacementEndpointId?: string;
  sunsetGraceDays?: number;
  contractChanges?: {
    field: string;
    changeType: 'added' | 'removed' | 'modified';
    breaking: boolean;
    description: string;
  }[];
  migrationGuide?: string;
}

export interface LifecycleRecord {
  endpointId: string;
  endpointName: string;
  fromStatus: string;
  toStatus: string;
  reason?: string;
  replacementId?: string;
  transitionAt: number;
  transitionBy: string;
}

export interface NegotiationResult {
  endpointId: string;
  accepted: boolean;
  contractVersion: string;
  changes: {
    field: string;
    changeType: 'added' | 'removed' | 'modified';
    breaking: boolean;
    description: string;
    consumerImpact: 'none' | 'low' | 'medium' | 'high' | 'critical';
    migrationRequired: boolean;
  }[];
  affectedConsumers: number;
  migrationDeadline?: number;
  notes: string;
}

export interface BrokerResult {
  success: boolean;
  operation: BrokerInput['operation'];
  lifecycle?: LifecycleRecord;
  negotiation?: NegotiationResult;
  message: string;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// BrokerAgent Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class BrokerAgent extends Agent {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private readonly lifecycles: LifecycleRecord[];
  private readonly contractRegistry: Map<string, NegotiationResult[]>;

  constructor() {
    super('SID-APIMARKETPLACE-BROKER');
    this.log = new Logger('BrokerAgent');
    this.audit = AuditLedger.getInstance();
    this.lifecycles = [];
    this.contractRegistry = new Map();
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Agent Lifecycle: Perceive → Decide → Act
  // ─────────────────────────────────────────────────────────────────────────

  protected async perceive(input: BrokerInput): Promise<BrokerInput> {
    this.log.info('Perceiving broker operation', { operation: input.operation });

    // Validate endpoint references
    if (input.endpointId && input.operation !== 'publish') {
      this.log.debug('Endpoint reference provided', { endpointId: input.endpointId });
    }

    // Validate deprecation requirements
    if (input.operation === 'deprecate' && !input.deprecationReason) {
      this.log.warn('Deprecation without reason — best practice requires a reason');
    }

    // Validate negotiation requirements
    if (input.operation === 'negotiate' && (!input.contractChanges || input.contractChanges.length === 0)) {
      this.log.warn('Negotiation without contract changes — nothing to negotiate');
    }

    return input;
  }

  protected async decide(input: BrokerInput): Promise<string> {
    this.log.info('Deciding broker action', { operation: input.operation });

    switch (input.operation) {
      case 'publish': return 'publishEndpoint';
      case 'deprecate': return 'deprecateEndpoint';
      case 'sunset': return 'sunsetEndpoint';
      case 'negotiate': return 'negotiateContract';
      default: return 'unknown';
    }
  }

  protected async act(input: BrokerInput, decision: string): Promise<BrokerResult> {
    this.log.info('Acting on broker decision', { decision });

    switch (decision) {
      case 'publishEndpoint': return this.publishEndpoint(input);
      case 'deprecateEndpoint': return this.deprecateEndpoint(input);
      case 'sunsetEndpoint': return this.sunsetEndpoint(input);
      case 'negotiateContract': return this.negotiateContract(input);
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
  // Publish Endpoint
  // ─────────────────────────────────────────────────────────────────────────

  private publishEndpoint(input: BrokerInput): BrokerResult {
    const endpointId = input.endpointId ?? `EP-${this.lifecycles.length + 1}`;
    const endpointName = input.endpointName ?? 'unnamed-endpoint';

    const lifecycle: LifecycleRecord = {
      endpointId,
      endpointName,
      fromStatus: 'none',
      toStatus: 'published',
      transitionAt: Date.now(),
      transitionBy: this.id,
    };

    this.lifecycles.push(lifecycle);

    this.audit.append({
      actor: this.id,
      action: 'ENDPOINT_PUBLISHED',
      entity: endpointId,
      status: 'SUCCESS',
      meta: {
        endpointName,
        method: input.method,
        path: input.path,
        version: input.version,
        visibility: input.visibility,
        authentication: input.authentication,
      },
    });

    this.log.info('Endpoint published', { endpointId, endpointName, version: input.version });

    return {
      success: true,
      operation: 'publish',
      lifecycle,
      message: `Endpoint "${endpointName}" (${endpointId}) published successfully`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Deprecate Endpoint
  // ─────────────────────────────────────────────────────────────────────────

  private deprecateEndpoint(input: BrokerInput): BrokerResult {
    const { endpointId, deprecationReason, replacementEndpointId, sunsetGraceDays } = input;

    if (!endpointId) {
      return {
        success: false,
        operation: 'deprecate',
        message: 'Endpoint ID is required for deprecation',
        timestamp: Date.now(),
      };
    }

    const graceDays = sunsetGraceDays ?? 180;

    const lifecycle: LifecycleRecord = {
      endpointId,
      endpointName: input.endpointName ?? endpointId,
      fromStatus: 'published',
      toStatus: 'deprecated',
      reason: deprecationReason ?? 'No reason provided',
      replacementId: replacementEndpointId,
      transitionAt: Date.now(),
      transitionBy: this.id,
    };

    this.lifecycles.push(lifecycle);

    this.audit.append({
      actor: this.id,
      action: 'ENDPOINT_DEPRECATED',
      entity: endpointId,
      status: 'SUCCESS',
      meta: {
        reason: deprecationReason,
        replacement: replacementEndpointId,
        sunsetGraceDays: graceDays,
        sunsetDate: Date.now() + graceDays * 24 * 60 * 60 * 1000,
      },
    });

    this.log.info('Endpoint deprecated', {
      endpointId,
      reason: deprecationReason,
      replacement: replacementEndpointId,
      graceDays,
    });

    return {
      success: true,
      operation: 'deprecate',
      lifecycle,
      message: `Endpoint ${endpointId} deprecated — sunset in ${graceDays} days. ${replacementEndpointId ? `Migrate to ${replacementEndpointId}.` : 'No replacement specified.'}`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Sunset Endpoint
  // ─────────────────────────────────────────────────────────────────────────

  private sunsetEndpoint(input: BrokerInput): BrokerResult {
    const { endpointId } = input;

    if (!endpointId) {
      return {
        success: false,
        operation: 'sunset',
        message: 'Endpoint ID is required for sunset',
        timestamp: Date.now(),
      };
    }

    const lifecycle: LifecycleRecord = {
      endpointId,
      endpointName: input.endpointName ?? endpointId,
      fromStatus: 'deprecated',
      toStatus: 'sunset',
      reason: 'Sunset grace period expired',
      transitionAt: Date.now(),
      transitionBy: this.id,
    };

    this.lifecycles.push(lifecycle);

    this.audit.append({
      actor: this.id,
      action: 'ENDPOINT_SUNSET',
      entity: endpointId,
      status: 'SUCCESS',
      meta: { previousStatus: 'deprecated' },
    });

    this.log.info('Endpoint sunset', { endpointId });

    return {
      success: true,
      operation: 'sunset',
      lifecycle,
      message: `Endpoint ${endpointId} has been sunset — no longer accessible`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Negotiate Contract
  // ─────────────────────────────────────────────────────────────────────────

  private negotiateContract(input: BrokerInput): BrokerResult {
    const { endpointId, contractChanges, migrationGuide } = input;

    if (!endpointId || !contractChanges || contractChanges.length === 0) {
      return {
        success: false,
        operation: 'negotiate',
        message: 'Endpoint ID and contract changes are required for negotiation',
        timestamp: Date.now(),
      };
    }

    // Assess impact of each change
    const assessedChanges = contractChanges.map((change) => {
      let consumerImpact: NegotiationResult['changes'][0]['consumerImpact'];
      let migrationRequired = false;

      if (change.breaking) {
        consumerImpact = change.changeType === 'removed' ? 'critical' : 'high';
        migrationRequired = true;
      } else {
        consumerImpact = change.changeType === 'added' ? 'none' : 'low';
      }

      return {
        ...change,
        consumerImpact,
        migrationRequired,
      };
    });

    // Determine if the negotiation is accepted
    const hasCriticalChanges = assessedChanges.some((c) => c.consumerImpact === 'critical');
    const hasBreakingChanges = assessedChanges.some((c) => c.breaking);
    const accepted = !hasCriticalChanges;

    // Simulate affected consumers
    const affectedConsumers = hasBreakingChanges
      ? Math.floor(Math.random() * 50) + 10
      : Math.floor(Math.random() * 5);

    const contractVersion = `v${Date.now()}`;

    const negotiation: NegotiationResult = {
      endpointId,
      accepted,
      contractVersion,
      changes: assessedChanges,
      affectedConsumers,
      migrationDeadline: hasBreakingChanges
        ? Date.now() + 90 * 24 * 60 * 60 * 1000 // 90 days
        : undefined,
      notes: migrationGuide ?? (hasBreakingChanges
        ? 'Breaking changes detected — migration required before deadline'
        : 'Non-breaking changes — backward compatible'),
    };

    // Store negotiation
    const existing = this.contractRegistry.get(endpointId) ?? [];
    existing.push(negotiation);
    this.contractRegistry.set(endpointId, existing);

    this.audit.append({
      actor: this.id,
      action: 'CONTRACT_NEGOTIATED',
      entity: endpointId,
      status: accepted ? 'SUCCESS' : 'PENDING',
      meta: {
        contractVersion,
        changeCount: contractChanges.length,
        breakingChanges: assessedChanges.filter((c) => c.breaking).length,
        affectedConsumers,
        accepted,
      },
    });

    this.log.info('Contract negotiated', {
      endpointId,
      accepted,
      changeCount: contractChanges.length,
      breakingChanges: assessedChanges.filter((c) => c.breaking).length,
    });

    return {
      success: true,
      operation: 'negotiate',
      negotiation,
      message: accepted
        ? `Contract for ${endpointId} accepted — ${contractChanges.length} change(s), ${affectedConsumers} consumer(s) affected`
        : `Contract for ${endpointId} requires review — critical changes detected affecting ${affectedConsumers} consumer(s)`,
      timestamp: Date.now(),
    };
  }
}
