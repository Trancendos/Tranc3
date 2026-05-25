/**
 * A2A (Agent-to-Agent) Protocol — Tranc3 Implementation
 *
 * Implements the Agent-to-Agent communication protocol for inter-hub
 * agent coordination. Based on Google's A2A specification concepts
 * adapted for the Tranc3 ecosystem's custom tier hierarchy.
 *
 * Key concepts:
 *   - AgentCard: Describes an agent's capabilities, skills, and endpoints
 *   - A2AMessage: Structured message envelope for inter-agent communication
 *   - A2ATransport: Pluggable transport layer (in-memory, HTTP, WebSocket, NATS)
 *   - A2ARouter: Routes messages between agents across hubs via the Nexus bridge
 *
 * This enables an agent in the Citadel to request a task from an agent
 * in the HIVE, or an agent in Infinity to verify a token through
 * the Lighthouse — all through a standardized protocol.
 */

import { Logger } from '../../core/logger';
import { AuditLedger } from '../../core/audit';
import { Agent, Bot, AI } from '../../core/definitions';

// ─────────────────────────────────────────────────────────────────────────────
// Agent Card — Capability Advertisement
// ─────────────────────────────────────────────────────────────────────────────

/** Describes a skill that an agent can perform */
export interface AgentSkill {
  id: string;
  name: string;
  description: string;
  inputSchema?: Record<string, unknown>;
  outputSchema?: Record<string, unknown>;
  tags?: string[];
}

/** Describes an agent's capabilities for discovery */
export interface AgentCard {
  /** Unique agent identifier (SID-XXX-NN format) */
  id: string;
  /** Human-readable name */
  name: string;
  /** Description of the agent's purpose */
  description: string;
  /** The hub this agent belongs to */
  hubId: string;
  /** The pillar this agent operates under */
  pillar: string;
  /** Tier level (always 4 for agents) */
  tier: number;
  /** Skills this agent can perform */
  skills: AgentSkill[];
  /** Supported message protocols */
  protocols: A2AProtocol[];
  /** Endpoint URL for direct communication (if available) */
  endpoint?: string;
  /** Current availability status */
  status: 'available' | 'busy' | 'offline';
  /** Load capacity (0.0 to 1.0) */
  load: number;
  /** Authentication requirements */
  authRequired: boolean;
  /** Metadata */
  metadata: Record<string, unknown>;
}

/** Supported A2A communication protocols */
export type A2AProtocol = 'json-rpc' | 'http-rest' | 'websocket' | 'nats' | 'grpc';

// ─────────────────────────────────────────────────────────────────────────────
// A2A Message — Communication Envelope
// ─────────────────────────────────────────────────────────────────────────────

/** Message priority levels */
export type A2APriority = 'critical' | 'high' | 'medium' | 'low';

/** Message types */
export type A2AMessageType =
  | 'request'       // Requesting another agent to perform a task
  | 'response'      // Responding to a request
  | 'notification'  // One-way notification (no response expected)
  | 'broadcast'     // Message to all agents in a hub or pillar
  | 'query'         // Querying an agent's capabilities or state
  | 'delegate'      // Delegating a task to another agent
  | 'escalate'      // Escalating to a higher tier (HIL-A integration)
  | 'heartbeat';    // Keep-alive signal

/** Structured message envelope for A2A communication */
export interface A2AMessage {
  /** Unique message ID */
  id: string;
  /** Message type */
  type: A2AMessageType;
  /** Sender agent ID */
  from: string;
  /** Recipient agent ID (or hub ID for broadcasts) */
  to: string;
  /** The skill being requested or notified about */
  skillId?: string;
  /** Message payload */
  payload: Record<string, unknown>;
  /** Priority level */
  priority: A2APriority;
  /** Protocol used for this message */
  protocol: A2AProtocol;
  /** Correlation ID for request/response pairing */
  correlationId?: string;
  /** Timestamp */
  timestamp: Date;
  /** Time-to-live in milliseconds (0 = no expiry) */
  ttl: number;
  /** Retry count */
  retryCount: number;
  /** Max retries */
  maxRetries: number;
  /** Security context */
  securityContext?: A2ASecurityContext;
}

/** Security context for A2A messages */
export interface A2ASecurityContext {
  /** Token for authentication */
  authToken?: string;
  /** Permission scope */
  scope?: string[];
  /** Encryption status */
  encrypted: boolean;
  /** Signature for message integrity */
  signature?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// A2A Response
// ─────────────────────────────────────────────────────────────────────────────

/** Response to an A2A message */
export interface A2AResponse {
  /** ID of the original request message */
  requestId: string;
  /** Responder agent ID */
  from: string;
  /** Recipient of the response */
  to: string;
  /** Response status */
  status: 'success' | 'failure' | 'timeout' | 'refused' | 'delegated';
  /** Response payload */
  payload: Record<string, unknown>;
  /** Correlation ID matching the request */
  correlationId: string;
  /** Timestamp */
  timestamp: Date;
  /** Error details if status is failure */
  error?: { code: string; message: string; details?: Record<string, unknown> };
}

// ─────────────────────────────────────────────────────────────────────────────
// A2A Transport — Pluggable Transport Layer
// ─────────────────────────────────────────────────────────────────────────────

/** Interface for A2A transport implementations */
export interface IA2ATransport {
  /** Transport protocol */
  protocol: A2AProtocol;
  /** Initialize the transport */
  start(): Promise<void>;
  /** Send a message */
  send(message: A2AMessage): Promise<A2AResponse | void>;
  /** Register a message handler */
  onMessage(handler: (message: A2AMessage) => Promise<A2AResponse | void>): void;
  /** Stop the transport */
  stop(): Promise<void>;
}

/** In-memory A2A transport — for single-process deployments and testing */
export class InMemoryA2ATransport implements IA2ATransport {
  public readonly protocol: A2AProtocol = 'json-rpc';
  private handlers: Array<(message: A2AMessage) => Promise<A2AResponse | void>> = [];
  private readonly log = new Logger('InMemoryA2ATransport');

  async start(): Promise<void> {
    this.log.info('In-memory A2A transport started');
  }

  async send(message: A2AMessage): Promise<A2AResponse | void> {
    for (const handler of this.handlers) {
      const result = await handler(message);
      if (result) return result;
    }
    this.log.warn('No handler for A2A message', { messageId: message.id, type: message.type });
    return undefined;
  }

  onMessage(handler: (message: A2AMessage) => Promise<A2AResponse | void>): void {
    this.handlers.push(handler);
  }

  async stop(): Promise<void> {
    this.handlers = [];
    this.log.info('In-memory A2A transport stopped');
  }
}

/** HTTP REST A2A transport — for cross-process deployments */
export class HttpA2ATransport implements IA2ATransport {
  public readonly protocol: A2AProtocol = 'http-rest';
  private handlers: Array<(message: A2AMessage) => Promise<A2AResponse | void>> = [];
  private readonly baseUrl: string;
  private readonly log = new Logger('HttpA2ATransport');

  constructor(baseUrl: string = 'http://localhost:8001') {
    this.baseUrl = baseUrl;
  }

  async start(): Promise<void> {
    this.log.info('HTTP A2A transport started', { baseUrl: this.baseUrl });
  }

  async send(message: A2AMessage): Promise<A2AResponse | void> {
    // In a real implementation, this would make an HTTP POST to the target agent's endpoint
    // For now, route through local handlers (same-process fallback)
    for (const handler of this.handlers) {
      const result = await handler(message);
      if (result) return result;
    }
    return undefined;
  }

  onMessage(handler: (message: A2AMessage) => Promise<A2AResponse | void>): void {
    this.handlers.push(handler);
  }

  async stop(): Promise<void> {
    this.handlers = [];
    this.log.info('HTTP A2A transport stopped');
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// A2A Router — Message Routing Between Agents
// ─────────────────────────────────────────────────────────────────────────────

/** Routing rule for directing A2A messages */
export interface A2ARouteRule {
  /** Source pattern (agent ID or hub ID) */
  from: string;
  /** Destination pattern (agent ID or hub ID) */
  to: string;
  /** Required skill (optional filter) */
  skillFilter?: string;
  /** Priority override */
  priorityOverride?: A2APriority;
  /** Enabled flag */
  enabled: boolean;
}

/** Router for directing A2A messages between agents and hubs */
export class A2ARouter {
  private readonly log = new Logger('A2ARouter');
  private readonly audit = new AuditLedger();
  private readonly agentCards: Map<string, AgentCard> = new Map();
  private readonly routeRules: A2ARouteRule[] = [];
  private readonly messageQueue: A2AMessage[] = [];
  private messageCounter: number = 0;

  /** Register an agent's capability card */
  registerAgentCard(card: AgentCard): void {
    this.agentCards.set(card.id, card);
    this.log.info('Agent card registered', { agentId: card.id, name: card.name, skills: card.skills.length });
    this.audit.append({
      actor: 'A2ARouter',
      action: 'REGISTER_AGENT_CARD',
      entity: card.id,
      status: 'SUCCESS',
      details: { name: card.name, hubId: card.hubId, skillCount: card.skills.length },
    });
  }

  /** Unregister an agent's card */
  unregisterAgentCard(agentId: string): boolean {
    const removed = this.agentCards.delete(agentId);
    if (removed) {
      this.log.info('Agent card unregistered', { agentId });
    }
    return removed;
  }

  /** Get an agent's card */
  getAgentCard(agentId: string): AgentCard | undefined {
    return this.agentCards.get(agentId);
  }

  /** Find agents that have a specific skill */
  findAgentsBySkill(skillId: string): AgentCard[] {
    return Array.from(this.agentCards.values())
      .filter(card => card.skills.some(s => s.id === skillId) && card.status === 'available');
  }

  /** Find agents in a specific hub */
  findAgentsByHub(hubId: string): AgentCard[] {
    return Array.from(this.agentCards.values())
      .filter(card => card.hubId === hubId);
  }

  /** Add a routing rule */
  addRouteRule(rule: A2ARouteRule): void {
    this.routeRules.push(rule);
    this.log.info('Route rule added', { from: rule.from, to: rule.to });
  }

  /** Route a message to the appropriate agent */
  route(message: A2AMessage): AgentCard | AgentCard[] | null {
    // Broadcast to all agents in a hub
    if (message.type === 'broadcast') {
      return this.findAgentsByHub(message.to);
    }

    // Direct message to a specific agent
    const targetCard = this.agentCards.get(message.to);
    if (targetCard) {
      // Check routing rules for any overrides
      for (const rule of this.routeRules) {
        if (rule.enabled && this.matchesRule(message, rule)) {
          this.log.info('Route rule matched', { from: rule.from, to: rule.to });
          if (rule.priorityOverride) {
            message.priority = rule.priorityOverride;
          }
        }
      }
      return targetCard;
    }

    // Skill-based routing — find an available agent with the requested skill
    if (message.skillId) {
      const candidates = this.findAgentsBySkill(message.skillId);
      if (candidates.length > 0) {
        // Select the least loaded agent
        candidates.sort((a, b) => a.load - b.load);
        return candidates[0];
      }
    }

    this.log.warn('No route found for A2A message', { messageId: message.id, to: message.to });
    return null;
  }

  /** Create a new A2A message with proper envelope */
  createMessage(params: {
    type: A2AMessageType;
    from: string;
    to: string;
    payload: Record<string, unknown>;
    skillId?: string;
    priority?: A2APriority;
    correlationId?: string;
    ttl?: number;
    maxRetries?: number;
  }): A2AMessage {
    this.messageCounter++;
    return {
      id: `A2A-${this.messageCounter.toString().padStart(8, '0')}`,
      type: params.type,
      from: params.from,
      to: params.to,
      skillId: params.skillId,
      payload: params.payload,
      priority: params.priority ?? 'medium',
      protocol: 'json-rpc',
      correlationId: params.correlationId,
      timestamp: new Date(),
      ttl: params.ttl ?? 30000,
      retryCount: 0,
      maxRetries: params.maxRetries ?? 3,
    };
  }

  /** Check if a message matches a routing rule */
  private matchesRule(message: A2AMessage, rule: A2ARouteRule): boolean {
    const fromMatch = rule.from === '*' || message.from === rule.from || message.from.startsWith(rule.from);
    const toMatch = rule.to === '*' || message.to === rule.to || message.to.startsWith(rule.to);
    const skillMatch = !rule.skillFilter || message.skillId === rule.skillFilter;
    return fromMatch && toMatch && skillMatch;
  }

  /** Get router statistics */
  getStats(): { registeredAgents: number; routeRules: number; messagesCreated: number } {
    return {
      registeredAgents: this.agentCards.size,
      routeRules: this.routeRules.filter(r => r.enabled).length,
      messagesCreated: this.messageCounter,
    };
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// A2A Client — Interface for Agents to Send/Receive A2A Messages
// ─────────────────────────────────────────────────────────────────────────────

/** Client that agents use to participate in the A2A network */
export class A2AClient {
  private readonly router: A2ARouter;
  private readonly transport: IA2ATransport;
  private readonly log = new Logger('A2AClient');
  private readonly pendingRequests: Map<string, { resolve: (response: A2AResponse) => void; reject: (error: Error) => void; timeout: NodeJS.Timeout }> = new Map();

  constructor(router: A2ARouter, transport: IA2ATransport) {
    this.router = router;
    this.transport = transport;

    // Register the message handler
    this.transport.onMessage(async (message: A2AMessage) => {
      return this.handleIncomingMessage(message);
    });
  }

  /** Send a request to another agent and wait for a response */
  async request(params: {
    from: string;
    to: string;
    skillId?: string;
    payload: Record<string, unknown>;
    priority?: A2APriority;
    timeoutMs?: number;
  }): Promise<A2AResponse> {
    const message = this.router.createMessage({
      type: 'request',
      from: params.from,
      to: params.to,
      skillId: params.skillId,
      payload: params.payload,
      priority: params.priority ?? 'medium',
    });

    // Route the message
    const target = this.router.route(message);
    if (!target) {
      return {
        requestId: message.id,
        from: 'a2a-router',
        to: params.from,
        status: 'refused',
        payload: { error: 'No route to target agent' },
        correlationId: message.id,
        timestamp: new Date(),
        error: { code: 'NO_ROUTE', message: `No agent found for ${params.to}` },
      };
    }

    // Set up response handler with timeout
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pendingRequests.delete(message.id);
        reject(new Error(`A2A request timeout: ${message.id}`));
      }, params.timeoutMs ?? 30000);

      this.pendingRequests.set(message.id, { resolve, reject, timeout });

      // Send via transport
      this.transport.send(message);
    });
  }

  /** Send a notification (fire-and-forget) */
  async notify(params: {
    from: string;
    to: string;
    payload: Record<string, unknown>;
    priority?: A2APriority;
  }): Promise<void> {
    const message = this.router.createMessage({
      type: 'notification',
      from: params.from,
      to: params.to,
      payload: params.payload,
      priority: params.priority ?? 'low',
    });

    this.transport.send(message);
  }

  /** Broadcast a message to all agents in a hub */
  async broadcast(params: {
    from: string;
    toHub: string;
    payload: Record<string, unknown>;
    priority?: A2APriority;
  }): Promise<void> {
    const message = this.router.createMessage({
      type: 'broadcast',
      from: params.from,
      to: params.toHub,
      payload: params.payload,
      priority: params.priority ?? 'low',
    });

    this.transport.send(message);
  }

  /** Handle an incoming A2A message */
  private async handleIncomingMessage(message: A2AMessage): Promise<A2AResponse | void> {
    // Check if this is a response to a pending request
    if (message.correlationId && this.pendingRequests.has(message.correlationId)) {
      const pending = this.pendingRequests.get(message.correlationId)!;
      clearTimeout(pending.timeout);
      this.pendingRequests.delete(message.correlationId);
      // The response would come as a separate A2AResponse, not an A2AMessage
      // This is handled by the transport layer
    }

    this.log.info('A2A message received', { messageId: message.id, type: message.type, from: message.from });
    return undefined;
  }

  /** Resolve a pending request with a response */
  resolveRequest(correlationId: string, response: A2AResponse): boolean {
    const pending = this.pendingRequests.get(correlationId);
    if (pending) {
      clearTimeout(pending.timeout);
      this.pendingRequests.delete(correlationId);
      pending.resolve(response);
      return true;
    }
    return false;
  }

  /** Start the A2A client */
  async start(): Promise<void> {
    await this.transport.start();
    this.log.info('A2A client started');
  }

  /** Stop the A2A client */
  async stop(): Promise<void> {
    // Reject all pending requests
    for (const [id, pending] of this.pendingRequests) {
      clearTimeout(pending.timeout);
      pending.reject(new Error('A2A client shutting down'));
    }
    this.pendingRequests.clear();
    await this.transport.stop();
    this.log.info('A2A client stopped');
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// A2A Network — Top-Level Coordinator
// ─────────────────────────────────────────────────────────────────────────────

/** The A2A Network coordinates all agent-to-agent communication across the ecosystem */
export class A2ANetwork {
  private readonly router: A2ARouter;
  private readonly transports: Map<A2AProtocol, IA2ATransport> = new Map();
  private readonly clients: Map<string, A2AClient> = new Map();
  private readonly log = new Logger('A2ANetwork');
  private readonly audit = new AuditLedger();

  constructor() {
    this.router = new A2ARouter();
    // Default in-memory transport
    this.transports.set('json-rpc', new InMemoryA2ATransport());
  }

  /** Register a transport for a specific protocol */
  registerTransport(transport: IA2ATransport): void {
    this.transports.set(transport.protocol, transport);
    this.log.info('Transport registered', { protocol: transport.protocol });
  }

  /** Register a hub's agents into the A2A network */
  registerHub(hub: AI): void {
    const hubId = hub.hub;

    // Register each agent's card
    for (const agentId of hub.listAgentIds()) {
      const agent = hub.getAgent(agentId);
      if (agent) {
        const card = this.agentToCard(agent, hubId, hub.pillar);
        this.router.registerAgentCard(card);
      }
    }

    this.log.info('Hub registered with A2A network', {
      hubId,
      hubName: hub.name,
      agents: hub.listAgentIds().length,
      bots: hub.listBotNames().length,
    });

    this.audit.append({
      actor: 'A2ANetwork',
      action: 'REGISTER_HUB',
      entity: hubId,
      status: 'SUCCESS',
      details: { hubName: hub.name, agents: hub.listAgentIds() },
    });
  }

  /** Create a client for an agent to use the A2A network */
  createClient(agentId: string): A2AClient {
    const transport = this.transports.get('json-rpc') ?? new InMemoryA2ATransport();
    const client = new A2AClient(this.router, transport);
    this.clients.set(agentId, client);
    return client;
  }

  /** Get the router for direct access */
  getRouter(): A2ARouter {
    return this.router;
  }

  /** Start the A2A network */
  async start(): Promise<void> {
    for (const [, transport] of this.transports) {
      await transport.start();
    }
    this.log.info('A2A network started', {
      transports: Array.from(this.transports.keys()),
      registeredAgents: this.router.getStats().registeredAgents,
    });
  }

  /** Stop the A2A network */
  async stop(): Promise<void> {
    for (const [, client] of this.clients) {
      await client.stop();
    }
    for (const [, transport] of this.transports) {
      await transport.stop();
    }
    this.log.info('A2A network stopped');
  }

  /** Network health check */
  healthCheck(): {
    status: 'healthy' | 'degraded' | 'critical';
    registeredAgents: number;
    activeTransports: number;
    activeClients: number;
    routeRules: number;
  } {
    const stats = this.router.getStats();
    return {
      status: stats.registeredAgents === 0 ? 'critical' : this.transports.size === 0 ? 'degraded' : 'healthy',
      registeredAgents: stats.registeredAgents,
      activeTransports: this.transports.size,
      activeClients: this.clients.size,
      routeRules: stats.routeRules,
    };
  }

  /** Convert an Agent instance to an AgentCard */
  private agentToCard(agent: Agent, hubId: string, pillar: string): AgentCard {
    // Extract skills from registered tools
    const skills: AgentSkill[] = [];
    for (const [name, tool] of agent.tools) {
      skills.push({
        id: `${agent.id}-${name}`,
        name,
        description: tool.description || `Execute ${name}`,
      });
    }

    return {
      id: agent.id,
      name: agent.id, // Agent base class uses ID as name
      description: `Agent ${agent.id} in hub ${hubId}`,
      hubId,
      pillar,
      tier: 4,
      skills,
      protocols: ['json-rpc'],
      status: 'available',
      load: 0,
      authRequired: false,
      metadata: { episodeCount: agent.episodeCount },
    };
  }
}
