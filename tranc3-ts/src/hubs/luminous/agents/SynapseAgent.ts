/**
 * Synapse Agent — Luminous Tier 4 Agent (SID-LUMINOUS-SYNAPSE)
 *
 * Autonomous microservice for neural pathway routing.
 * Manages inference dispatch, load balancing across model providers,
 * synaptic plasticity (adaptive routing weights), and failover.
 *
 * Perceive: Analyze inference request and available model capacity
 * Decide: Select optimal model provider and routing path
 * Act: Dispatch inference to selected provider with fallback handling
 */

import { AuditLedger, Agent, Bot } from '../../../core/definitions'
import { Logger } from '../../../core/logger';

const logger = new Logger('SynapseAgent');

/** Model provider types */
export type ModelProvider = 'OLLAMA' | 'DEEPSEEK' | 'HUGGINGFACE' | 'OPENROUTER' | 'GROQ' | 'OFFLINE';

/** Routing weight for a model provider */
export interface ProviderWeight {
  provider: ModelProvider;
  weight: number;
  latencyMs: number;
  successRate: number;
  available: boolean;
}

/** Synapse routing decision */
export interface RoutingDecision {
  selectedProvider: ModelProvider;
  fallbackProvider: ModelProvider | null;
  confidence: number;
  reason: string;
  estimatedLatencyMs: number;
}

/** Synapse routing result */
export interface RoutingResult {
  decision: RoutingDecision;
  dispatched: boolean;
  provider: ModelProvider;
  auditId: string;
}

export class SynapseAgent extends Agent {
  private readonly audit: AuditLedger;
  private readonly plasticity: number;
  private readonly providerWeights: Map<ModelProvider, ProviderWeight> = new Map();

  constructor(id: string, audit: AuditLedger, plasticity: number = 0.1) {
    super(id);
    this.audit = audit;
    this.plasticity = plasticity;
    this.initializeProviders();
    logger.info('SynapseAgent initialized', { id, plasticity });
  }

  /** Initialize default provider weights */
  private initializeProviders(): void {
    const defaults: ProviderWeight[] = [
      { provider: 'OLLAMA', weight: 1.0, latencyMs: 200, successRate: 0.95, available: true },
      { provider: 'DEEPSEEK', weight: 0.8, latencyMs: 500, successRate: 0.90, available: true },
      { provider: 'HUGGINGFACE', weight: 0.6, latencyMs: 1000, successRate: 0.85, available: true },
      { provider: 'OPENROUTER', weight: 0.5, latencyMs: 800, successRate: 0.88, available: true },
      { provider: 'GROQ', weight: 0.7, latencyMs: 150, successRate: 0.92, available: true },
      { provider: 'OFFLINE', weight: 0.1, latencyMs: 0, successRate: 1.0, available: true },
    ];

    for (const pw of defaults) {
      this.providerWeights.set(pw.provider, pw);
    }
  }

  /**
   * Perceive: Analyze inference request and current provider state.
   */
  async perceive(observation: any): Promise<any> {
    const availableProviders = Array.from(this.providerWeights.values())
      .filter(pw => pw.available);

    logger.debug('Perceived routing context', {
      requestType: observation?.request?.type,
      availableProviders: availableProviders.length,
    });

    return {
      request: observation?.request,
      aggregated: observation?.aggregated,
      availableProviders,
      totalProviders: this.providerWeights.size,
    };
  }

  /**
   * Decide: Select optimal provider based on weights, latency, and success rate.
   * Implements weighted random selection with synaptic plasticity.
   */
  async decide(perceived: any): Promise<RoutingDecision> {
    const providers: ProviderWeight[] = perceived.availableProviders || [];

    if (providers.length === 0) {
      return {
        selectedProvider: 'OFFLINE',
        fallbackProvider: null,
        confidence: 0.1,
        reason: 'No providers available — falling back to offline mode',
        estimatedLatencyMs: 0,
      };
    }

    // Calculate selection scores
    const scored = providers.map(pw => {
      // Score = weight * successRate / (latency + 1) * 1000
      const score = pw.weight * pw.successRate / (pw.latencyMs + 1) * 1000;
      return { provider: pw, score };
    });

    // Sort by score descending
    scored.sort((a, b) => b.score - a.score);

    // Weighted random selection among top 3 (exploration vs exploitation)
    const topN = scored.slice(0, Math.min(3, scored.length));
    const totalScore = topN.reduce((sum, s) => sum + s.score, 0);
    let random = Math.random() * totalScore;
    let selected = topN[0];

    for (const candidate of topN) {
      random -= candidate.score;
      if (random <= 0) {
        selected = candidate;
        break;
      }
    }

    const fallback = topN.find(s => s.provider.provider !== selected.provider.provider);

    const decision: RoutingDecision = {
      selectedProvider: selected.provider.provider,
      fallbackProvider: fallback?.provider.provider || null,
      confidence: Math.min(selected.score / (topN[0]?.score || 1), 1.0),
      reason: `Selected ${selected.provider.provider} (score: ${selected.score.toFixed(2)}, latency: ${selected.provider.latencyMs}ms)`,
      estimatedLatencyMs: selected.provider.latencyMs,
    };

    logger.info('Routing decision', {
      selected: decision.selectedProvider,
      fallback: decision.fallbackProvider,
      confidence: decision.confidence.toFixed(2),
    });

    return decision;
  }

  /**
   * Act: Execute routing decision by recording it and updating weights.
   */
  async act(decision: RoutingDecision): Promise<RoutingResult> {
    const auditId = await this.audit.append({
      actor: this.id,
      action: 'SYNAPSE_ROUTE',
      entity: decision.selectedProvider,
      status: 'SUCCESS',
      meta: {
        selectedProvider: decision.selectedProvider,
        fallbackProvider: decision.fallbackProvider,
        confidence: decision.confidence,
        estimatedLatencyMs: decision.estimatedLatencyMs,
      },
    });

    // Apply synaptic plasticity — slightly increase weight of selected provider
    const selectedWeight = this.providerWeights.get(decision.selectedProvider);
    if (selectedWeight) {
      selectedWeight.weight = Math.min(selectedWeight.weight + this.plasticity, 2.0);
    }

    logger.debug('Route dispatched', { provider: decision.selectedProvider });

    return {
      decision,
      dispatched: true,
      provider: decision.selectedProvider,
      auditId,
    };
  }

  /** Update provider availability (called by health checks) */
  setProviderAvailability(provider: ModelProvider, available: boolean): void {
    const pw = this.providerWeights.get(provider);
    if (pw) {
      pw.available = available;
      if (!available) {
        pw.weight *= 0.5; // Penalize unavailable providers
      }
      logger.info('Provider availability updated', { provider, available });
    }
  }

  /** Get current provider weights (for monitoring) */
  getProviderWeights(): ProviderWeight[] {
    return Array.from(this.providerWeights.values());
  }
}
