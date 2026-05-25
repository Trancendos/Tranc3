/**
 * TheAPIMarketplaceAI — Lead AI for The API Marketplace Hub
 *
 * Identity:  AID-APIMARKETPLACE
 * Pillar:    The Doctor (The Broker)
 * Tier:      3 (Lead AI / Domain Orchestrator)
 * Domain:    API lifecycle management, endpoint registration,
 *            rate limiting, versioning, contract enforcement,
 *            developer experience, API gateway orchestration
 *
 * Philosophy: APIs are the lingua franca of the digital realm.
 *             Every endpoint is a promise, every response a contract.
 *             The Marketplace ensures promises are kept.
 *
 * Pipeline:  Registrar (publish) → Validator (verify) → Router (direct)
 *            BrokerAgent manages API lifecycle and contracts,
 *            TollAgent manages rate limiting and billing
 */

import { AI, Agent, Bot, Logger, AuditLedger } from '../../core/definitions';
import { BrokerAgent } from './agents/BrokerAgent';
import { TollAgent } from './agents/TollAgent';
import { RegistrarBot } from './bots/RegistrarBot';
import { ValidatorBot } from './bots/ValidatorBot';
import { RouterBot } from './bots/RouterBot';

// ─────────────────────────────────────────────────────────────────────────────
// Domain Interfaces
// ─────────────────────────────────────────────────────────────────────────────

export interface APIEndpoint {
  id: string;
  name: string;
  version: string;
  basePath: string;
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'OPTIONS' | 'HEAD';
  path: string;
  description: string;
  status: 'draft' | 'published' | 'deprecated' | 'sunset' | 'retired';
  visibility: 'public' | 'internal' | 'partner';
  authentication: 'none' | 'apikey' | 'oauth2' | 'jwt' | 'mtls';
  rateLimit?: {
    requests: number;
    window: number; // seconds
  };
  contract: APIContract;
  tags: string[];
  createdAt: number;
  publishedAt?: number;
  deprecatedAt?: number;
  sunsetAt?: number;
}

export interface APIContract {
  requestSchema: Record<string, unknown>;
  responseSchema: Record<string, unknown>;
  errorSchemas: Record<string, Record<string, unknown>>;
  headers: Record<string, string>;
  queryParams?: Record<string, { type: string; required: boolean; description: string }>;
  deprecated?: boolean;
  breakingChange?: boolean;
}

export interface APIConsumer {
  id: string;
  name: string;
  apiKey: string;
  tier: 'free' | 'starter' | 'professional' | 'enterprise';
  rateLimits: Record<string, { requests: number; window: number }>;
  usageThisMonth: number;
  registeredAt: number;
  lastActivity: number;
}

export interface APIMetrics {
  endpointId: string;
  totalRequests: number;
  successfulRequests: number;
  failedRequests: number;
  averageLatency: number;
  p99Latency: number;
  errorRate: number;
  uptime: number;
  lastChecked: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// TheAPIMarketplaceAI Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class TheAPIMarketplaceAI extends AI {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private endpoints: Map<string, APIEndpoint>;
  private consumers: Map<string, APIConsumer>;
  private metrics: Map<string, APIMetrics>;

  constructor() {
    super(
      'AID-APIMARKETPLACE',
      'TheAPIMarketplace',
      'apimarketplace',
      'The Doctor',
      3
    );

    this.log = new Logger('TheAPIMarketplaceAI');
    this.audit = AuditLedger.getInstance();
    this.endpoints = new Map();
    this.consumers = new Map();
    this.metrics = new Map();

    // Register Agents
    this.registerAgent(new BrokerAgent());
    this.registerAgent(new TollAgent());

    // Register Bots
    this.registerBot(new RegistrarBot());
    this.registerBot(new ValidatorBot());
    this.registerBot(new RouterBot());

    this.log.info('TheAPIMarketplaceAI initialised', {
      agents: this.listAgentIds(),
      bots: this.listBotNames(),
      message: 'Every endpoint is a promise. Every response a contract. 🏪',
    });
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Endpoint Management
  // ─────────────────────────────────────────────────────────────────────────

  /**
   * Register a new API endpoint.
   */
  registerEndpoint(endpoint: Omit<APIEndpoint, 'id' | 'createdAt'>): APIEndpoint {
    const id = `EP-${this.endpoints.size + 1}`;
    const newEndpoint: APIEndpoint = {
      ...endpoint,
      id,
      createdAt: Date.now(),
    };

    this.endpoints.set(id, newEndpoint);

    this.log.info('API endpoint registered', { id, name: endpoint.name, method: endpoint.method, path: endpoint.path });
    return newEndpoint;
  }

  /**
   * Get an endpoint by ID.
   */
  getEndpoint(id: string): APIEndpoint | undefined {
    return this.endpoints.get(id);
  }

  /**
   * Update endpoint status.
   */
  updateEndpointStatus(id: string, status: APIEndpoint['status']): boolean {
    const endpoint = this.endpoints.get(id);
    if (!endpoint) return false;

    endpoint.status = status;
    if (status === 'published') {
      endpoint.publishedAt = Date.now();
    } else if (status === 'deprecated') {
      endpoint.deprecatedAt = Date.now();
      endpoint.sunsetAt = Date.now() + 180 * 24 * 60 * 60 * 1000; // 180 days until sunset
    }

    this.log.info('Endpoint status updated', { id, status });
    return true;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Consumer Management
  // ─────────────────────────────────────────────────────────────────────────

  /**
   * Register a new API consumer.
   */
  registerConsumer(consumer: Omit<APIConsumer, 'id' | 'apiKey' | 'usageThisMonth' | 'registeredAt' | 'lastActivity'>): APIConsumer {
    const id = `CON-${this.consumers.size + 1}`;
    const apiKey = `ak_${Buffer.from(`${consumer.name}:${Date.now()}`).toString('base64url').slice(0, 32)}`;

    const newConsumer: APIConsumer = {
      ...consumer,
      id,
      apiKey,
      usageThisMonth: 0,
      registeredAt: Date.now(),
      lastActivity: Date.now(),
    };

    this.consumers.set(id, newConsumer);

    this.log.info('API consumer registered', { id, name: consumer.name, tier: consumer.tier });
    return newConsumer;
  }

  /**
   * Get all consumers.
   */
  getConsumers(): APIConsumer[] {
    return Array.from(this.consumers.values());
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Bot Delegations
  // ─────────────────────────────────────────────────────────────────────────

  /**
   * Publish an API endpoint via RegistrarBot.
   */
  async publishEndpoint(
    name: string,
    method: APIEndpoint['method'],
    path: string,
    basePath: string,
    version: string
  ): Promise<unknown> {
    const registrar = this.getBot('Registrar')!;
    const result = await registrar.execute({
      operation: 'PUBLISH',
      name,
      method,
      path,
      basePath,
      version,
      visibility: 'public',
      authentication: 'apikey',
    });
    return result;
  }

  /**
   * Validate an API contract via ValidatorBot.
   */
  async validateContract(
    endpointId: string,
    contract: APIContract
  ): Promise<unknown> {
    const validator = this.getBot('Validator')!;
    const result = await validator.execute({
      operation: 'VALIDATE',
      endpointId,
      contract,
    });
    return result;
  }

  /**
   * Route an API request via RouterBot.
   */
  async routeRequest(
    method: string,
    path: string,
    headers: Record<string, string>
  ): Promise<unknown> {
    const router = this.getBot('Router')!;
    const result = await router.execute({
      operation: 'ROUTE',
      method,
      path,
      headers,
      queryParams: {},
    });
    return result;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Agent Delegations
  // ─────────────────────────────────────────────────────────────────────────

  /**
   * Manage API lifecycle and contracts via BrokerAgent.
   */
  async manageAPIs(
    operation: 'publish' | 'deprecate' | 'sunset' | 'negotiate',
    params: Record<string, unknown>
  ): Promise<unknown> {
    const broker = this.getAgent('SID-APIMARKETPLACE-BROKER') as BrokerAgent;
    const result = await broker.runCycle({
      operation,
      ...params,
    });
    return result;
  }

  /**
   * Manage rate limiting and billing via TollAgent.
   */
  async manageTolls(
    operation: 'assess' | 'enforce' | 'report',
    params: Record<string, unknown>
  ): Promise<unknown> {
    const toll = this.getAgent('SID-APIMARKETPLACE-TOLL') as TollAgent;
    const result = await toll.runCycle({
      operation,
      ...params,
    });
    return result;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Health Check
  // ─────────────────────────────────────────────────────────────────────────

  healthCheck(): {
    status: 'healthy' | 'degraded' | 'critical';
    totalEndpoints: number;
    publishedEndpoints: number;
    totalConsumers: number;
    activeContracts: number;
    agents: number;
    bots: number;
    timestamp: number;
  } {
    const totalEndpoints = this.endpoints.size;
    const publishedEndpoints = Array.from(this.endpoints.values())
      .filter((e) => e.status === 'published').length;
    const totalConsumers = this.consumers.size;

    const status: 'healthy' | 'degraded' | 'critical' =
      publishedEndpoints === 0 && totalEndpoints > 0
        ? 'degraded'
        : totalEndpoints === 0
          ? 'critical'
          : 'healthy';

    return {
      status,
      totalEndpoints,
      publishedEndpoints,
      totalConsumers,
      activeContracts: publishedEndpoints,
      agents: this.listAgentIds().length,
      bots: this.listBotNames().length,
      timestamp: Date.now(),
    };
  }
}
