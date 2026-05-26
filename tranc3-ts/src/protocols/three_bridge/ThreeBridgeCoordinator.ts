/**
 * Three-Bridge Coordinator — Tranc3 Ecosystem
 *
 * Implements the Three-Bridge Architecture that separates traffic
 * into three distinct domains, all coordinated through Sentinel Station:
 *
 *   InfinityBridge — User/Human traffic
 *     Handles all human-facing requests: web UI, API calls,
 *     dashboard interactions, user authentication flows.
 *     Traffic origin: Browsers, mobile apps, API clients
 *
 *   Nexus — AI/Agent/Bot traffic
 *     Handles all inter-entity communication: agent requests,
 *     bot delegations, A2A protocol messages, agent discovery.
 *     Traffic origin: AI hubs, Agent instances, Bot executors
 *
 *   HIVE — Data movement / Swarm coordination
 *     Handles all data transport: queue operations, swarm task
 *     dispatch, estate scanning, consensus voting, bulk transfers.
 *     Traffic origin: Queue workers, transport bots, estate nodes
 *
 * Sentinel Station is the central coordination point that:
 *   - Routes traffic to the correct bridge
 *   - Monitors bridge health
 *   - Enforces traffic isolation rules
 *   - Provides cross-bridge escalation when needed
 *   - Aggregates health data from all bridges
 */

import { Logger } from '../../core/logger';
import { AuditLedger } from '../../core/audit';

// ─────────────────────────────────────────────────────────────────────────────
// Bridge Types
// ─────────────────────────────────────────────────────────────────────────────

/** The three bridge domains */
export type BridgeDomain = 'infinity' | 'nexus' | 'hive';

/** Bridge status */
export type BridgeStatus = 'active' | 'degraded' | 'offline' | 'maintenance';

/** Traffic classification for routing decisions */
export type TrafficClass =
  | 'user_request'       // Human-initiated request → InfinityBridge
  | 'user_auth'          // Authentication flow → InfinityBridge
  | 'user_dashboard'     // Dashboard/UI interaction → InfinityBridge
  | 'agent_request'      // Agent-to-agent request → Nexus
  | 'agent_broadcast'    // Agent broadcast → Nexus
  | 'agent_discovery'    // Agent capability query → Nexus
  | 'bot_delegation'     // Bot task delegation → Nexus
  | 'a2a_message'        // A2A protocol message → Nexus
  | 'data_queue'         // Queue enqueue/dequeue → HIVE
  | 'data_transport'     // Bulk data transfer → HIVE
  | 'swarm_dispatch'     // Swarm task assignment → HIVE
  | 'swarm_consensus'    // Consensus voting → HIVE
  | 'estate_scan'        // Estate scanning → HIVE
  | 'internal_health'    // Health check → Sentinel (handled internally)
  | 'cross_bridge'       // Cross-bridge escalation → Sentinel routes
  | 'unknown';           // Unknown traffic → Sentinel decides

// ─────────────────────────────────────────────────────────────────────────────
// Bridge Traffic Packet
// ─────────────────────────────────────────────────────────────────────────────

/** A packet of traffic flowing through the bridge system */
export interface BridgeTrafficPacket {
  /** Unique packet ID */
  id: string;
  /** Traffic classification */
  trafficClass: TrafficClass;
  /** Target bridge domain */
  targetBridge: BridgeDomain;
  /** Source identifier (user ID, agent ID, bot ID) */
  source: string;
  /** Destination identifier */
  destination: string;
  /** Payload */
  payload: Record<string, unknown>;
  /** Priority */
  priority: 'critical' | 'high' | 'medium' | 'low';
  /** Timestamp */
  timestamp: Date;
  /** Security context */
  securityToken?: string;
  /** Cross-bridge escalation flag */
  escalated: boolean;
  /** Original bridge if escalated */
  originalBridge?: BridgeDomain;
}

// ─────────────────────────────────────────────────────────────────────────────
// Bridge Health
// ─────────────────────────────────────────────────────────────────────────────

/** Health report from a single bridge */
export interface BridgeHealthReport {
  domain: BridgeDomain;
  status: BridgeStatus;
  packetsProcessed: number;
  packetsPending: number;
  averageLatencyMs: number;
  errorRate: number;
  lastPacketAt: Date | null;
  uptime: number;
  metadata: Record<string, unknown>;
}

// ─────────────────────────────────────────────────────────────────────────────
// Bridge Interface
// ─────────────────────────────────────────────────────────────────────────────

/** Interface for a bridge implementation */
export interface IBridge {
  /** The bridge domain */
  domain: BridgeDomain;
  /** Current status */
  status: BridgeStatus;
  /** Accept a traffic packet */
  accept(packet: BridgeTrafficPacket): Promise<BridgeTrafficPacket | null>;
  /** Get health report */
  healthCheck(): BridgeHealthReport;
  /** Start the bridge */
  start(): Promise<void>;
  /** Stop the bridge */
  stop(): Promise<void>;
}

// ─────────────────────────────────────────────────────────────────────────────
// InfinityBridge — User/Human Traffic
// ─────────────────────────────────────────────────────────────────────────────

/** Handles all human-facing traffic: web UI, API calls, authentication */
export class InfinityBridge implements IBridge {
  public readonly domain: BridgeDomain = 'infinity';
  public status: BridgeStatus = 'offline';
  private packetsProcessed: number = 0;
  private packetsPending: number = 0;
  private totalLatencyMs: number = 0;
  private errors: number = 0;
  private startTime: Date | null = null;
  private lastPacketAt: Date | null = null;
  private readonly log = new Logger('InfinityBridge');

  async accept(packet: BridgeTrafficPacket): Promise<BridgeTrafficPacket | null> {
    this.packetsPending++;
    const startMs = Date.now();

    try {
      // Route based on traffic class
      switch (packet.trafficClass) {
        case 'user_request':
          this.log.info('User request processed', { source: packet.source, destination: packet.destination });
          break;
        case 'user_auth':
          this.log.info('Auth flow processed', { source: packet.source });
          break;
        case 'user_dashboard':
          this.log.info('Dashboard interaction processed', { source: packet.source });
          break;
        default:
          this.log.warn('Unexpected traffic class on InfinityBridge', { trafficClass: packet.trafficClass });
      }

      this.packetsProcessed++;
      this.totalLatencyMs += Date.now() - startMs;
      this.lastPacketAt = new Date();
      this.packetsPending--;

      return { ...packet, payload: { ...packet.payload, _bridge: 'infinity', _processedAt: new Date() } };
    } catch (error) {
      this.errors++;
      this.packetsPending--;
      this.log.error('InfinityBridge processing error', { error });
      return null;
    }
  }

  healthCheck(): BridgeHealthReport {
    return {
      domain: this.domain,
      status: this.status,
      packetsProcessed: this.packetsProcessed,
      packetsPending: this.packetsPending,
      averageLatencyMs: this.packetsProcessed > 0 ? this.totalLatencyMs / this.packetsProcessed : 0,
      errorRate: this.packetsProcessed > 0 ? this.errors / this.packetsProcessed : 0,
      lastPacketAt: this.lastPacketAt,
      uptime: this.startTime ? Date.now() - this.startTime.getTime() : 0,
      metadata: {},
    };
  }

  async start(): Promise<void> {
    this.status = 'active';
    this.startTime = new Date();
    this.log.info('InfinityBridge started — user/human traffic domain active');
  }

  async stop(): Promise<void> {
    this.status = 'offline';
    this.log.info('InfinityBridge stopped');
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// NexusBridge — AI/Agent/Bot Traffic
// ─────────────────────────────────────────────────────────────────────────────

/** Handles all AI/Agent/Bot inter-entity communication */
export class NexusBridge implements IBridge {
  public readonly domain: BridgeDomain = 'nexus';
  public status: BridgeStatus = 'offline';
  private packetsProcessed: number = 0;
  private packetsPending: number = 0;
  private totalLatencyMs: number = 0;
  private errors: number = 0;
  private startTime: Date | null = null;
  private lastPacketAt: Date | null = null;
  private readonly log = new Logger('NexusBridge');

  async accept(packet: BridgeTrafficPacket): Promise<BridgeTrafficPacket | null> {
    this.packetsPending++;
    const startMs = Date.now();

    try {
      switch (packet.trafficClass) {
        case 'agent_request':
          this.log.info('Agent request routed', { from: packet.source, to: packet.destination });
          break;
        case 'agent_broadcast':
          this.log.info('Agent broadcast routed', { from: packet.source });
          break;
        case 'agent_discovery':
          this.log.info('Agent discovery query', { from: packet.source });
          break;
        case 'bot_delegation':
          this.log.info('Bot delegation routed', { from: packet.source, to: packet.destination });
          break;
        case 'a2a_message':
          this.log.info('A2A message routed', { from: packet.source, to: packet.destination });
          break;
        default:
          this.log.warn('Unexpected traffic class on NexusBridge', { trafficClass: packet.trafficClass });
      }

      this.packetsProcessed++;
      this.totalLatencyMs += Date.now() - startMs;
      this.lastPacketAt = new Date();
      this.packetsPending--;

      return { ...packet, payload: { ...packet.payload, _bridge: 'nexus', _processedAt: new Date() } };
    } catch (error) {
      this.errors++;
      this.packetsPending--;
      this.log.error('NexusBridge processing error', { error });
      return null;
    }
  }

  healthCheck(): BridgeHealthReport {
    return {
      domain: this.domain,
      status: this.status,
      packetsProcessed: this.packetsProcessed,
      packetsPending: this.packetsPending,
      averageLatencyMs: this.packetsProcessed > 0 ? this.totalLatencyMs / this.packetsProcessed : 0,
      errorRate: this.packetsProcessed > 0 ? this.errors / this.packetsProcessed : 0,
      lastPacketAt: this.lastPacketAt,
      uptime: this.startTime ? Date.now() - this.startTime.getTime() : 0,
      metadata: {},
    };
  }

  async start(): Promise<void> {
    this.status = 'active';
    this.startTime = new Date();
    this.log.info('NexusBridge started — AI/Agent/Bot traffic domain active');
  }

  async stop(): Promise<void> {
    this.status = 'offline';
    this.log.info('NexusBridge stopped');
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// HIVEBridge — Data Movement / Swarm Coordination
// ─────────────────────────────────────────────────────────────────────────────

/** Handles all data transport and swarm coordination */
export class HIVEBridge implements IBridge {
  public readonly domain: BridgeDomain = 'hive';
  public status: BridgeStatus = 'offline';
  private packetsProcessed: number = 0;
  private packetsPending: number = 0;
  private totalLatencyMs: number = 0;
  private errors: number = 0;
  private startTime: Date | null = null;
  private lastPacketAt: Date | null = null;
  private readonly log = new Logger('HIVEBridge');

  async accept(packet: BridgeTrafficPacket): Promise<BridgeTrafficPacket | null> {
    this.packetsPending++;
    const startMs = Date.now();

    try {
      switch (packet.trafficClass) {
        case 'data_queue':
          this.log.info('Queue operation processed', { source: packet.source });
          break;
        case 'data_transport':
          this.log.info('Data transport processed', { source: packet.source, destination: packet.destination });
          break;
        case 'swarm_dispatch':
          this.log.info('Swarm dispatch processed', { from: packet.source });
          break;
        case 'swarm_consensus':
          this.log.info('Consensus vote processed', { from: packet.source });
          break;
        case 'estate_scan':
          this.log.info('Estate scan processed', { source: packet.source });
          break;
        default:
          this.log.warn('Unexpected traffic class on HIVEBridge', { trafficClass: packet.trafficClass });
      }

      this.packetsProcessed++;
      this.totalLatencyMs += Date.now() - startMs;
      this.lastPacketAt = new Date();
      this.packetsPending--;

      return { ...packet, payload: { ...packet.payload, _bridge: 'hive', _processedAt: new Date() } };
    } catch (error) {
      this.errors++;
      this.packetsPending--;
      this.log.error('HIVEBridge processing error', { error });
      return null;
    }
  }

  healthCheck(): BridgeHealthReport {
    return {
      domain: this.domain,
      status: this.status,
      packetsProcessed: this.packetsProcessed,
      packetsPending: this.packetsPending,
      averageLatencyMs: this.packetsProcessed > 0 ? this.totalLatencyMs / this.packetsProcessed : 0,
      errorRate: this.packetsProcessed > 0 ? this.errors / this.packetsProcessed : 0,
      lastPacketAt: this.lastPacketAt,
      uptime: this.startTime ? Date.now() - this.startTime.getTime() : 0,
      metadata: {},
    };
  }

  async start(): Promise<void> {
    this.status = 'active';
    this.startTime = new Date();
    this.log.info('HIVEBridge started — data/swarm traffic domain active');
  }

  async stop(): Promise<void> {
    this.status = 'offline';
    this.log.info('HIVEBridge stopped');
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Sentinel Station — Central Coordinator
// ─────────────────────────────────────────────────────────────────────────────

/** Traffic routing rules */
export interface TrafficRoutingRule {
  trafficClass: TrafficClass;
  targetBridge: BridgeDomain;
  priority: 'critical' | 'high' | 'medium' | 'low';
  description: string;
}

/** Sentinel Station — the central coordination point for the Three-Bridge system */
export class SentinelStation {
  private readonly log = new Logger('SentinelStation');
  private readonly audit = new AuditLedger();

  private readonly infinityBridge: InfinityBridge;
  private readonly nexusBridge: NexusBridge;
  private readonly hiveBridge: HIVEBridge;
  private readonly bridges: Map<BridgeDomain, IBridge>;

  private readonly routingRules: TrafficRoutingRule[];
  private packetCounter: number = 0;
  private readonly crossBridgeQueue: BridgeTrafficPacket[] = [];

  constructor() {
    this.infinityBridge = new InfinityBridge();
    this.nexusBridge = new NexusBridge();
    this.hiveBridge = new HIVEBridge();

    this.bridges = new Map<BridgeDomain, IBridge>([
      ['infinity', this.infinityBridge],
      ['nexus', this.nexusBridge],
      ['hive', this.hiveBridge],
    ]);

    // Default routing rules based on architecture specification
    this.routingRules = [
      // InfinityBridge — User/Human traffic
      { trafficClass: 'user_request', targetBridge: 'infinity', priority: 'high', description: 'Human-initiated API requests' },
      { trafficClass: 'user_auth', targetBridge: 'infinity', priority: 'critical', description: 'Authentication flows' },
      { trafficClass: 'user_dashboard', targetBridge: 'infinity', priority: 'medium', description: 'Dashboard/UI interactions' },

      // Nexus — AI/Agent/Bot traffic
      { trafficClass: 'agent_request', targetBridge: 'nexus', priority: 'high', description: 'Agent-to-agent requests' },
      { trafficClass: 'agent_broadcast', targetBridge: 'nexus', priority: 'medium', description: 'Agent broadcasts' },
      { trafficClass: 'agent_discovery', targetBridge: 'nexus', priority: 'low', description: 'Agent capability queries' },
      { trafficClass: 'bot_delegation', targetBridge: 'nexus', priority: 'medium', description: 'Bot task delegations' },
      { trafficClass: 'a2a_message', targetBridge: 'nexus', priority: 'high', description: 'A2A protocol messages' },

      // HIVE — Data movement / Swarm coordination
      { trafficClass: 'data_queue', targetBridge: 'hive', priority: 'high', description: 'Queue operations' },
      { trafficClass: 'data_transport', targetBridge: 'hive', priority: 'medium', description: 'Bulk data transfers' },
      { trafficClass: 'swarm_dispatch', targetBridge: 'hive', priority: 'high', description: 'Swarm task dispatch' },
      { trafficClass: 'swarm_consensus', targetBridge: 'hive', priority: 'medium', description: 'Consensus voting' },
      { trafficClass: 'estate_scan', targetBridge: 'hive', priority: 'low', description: 'Estate scanning' },
    ];
  }

  /** Classify and route traffic to the correct bridge */
  async routeTraffic(trafficClass: TrafficClass, packet: Omit<BridgeTrafficPacket, 'id' | 'targetBridge' | 'timestamp' | 'escalated'>): Promise<BridgeTrafficPacket | null> {
    this.packetCounter++;

    const fullPacket: BridgeTrafficPacket = {
      ...packet,
      id: `PKT-${this.packetCounter.toString().padStart(8, '0')}`,
      targetBridge: this.classifyTraffic(trafficClass),
      trafficClass,
      timestamp: new Date(),
      escalated: false,
    };

    // Find the target bridge
    const bridge = this.bridges.get(fullPacket.targetBridge);
    if (!bridge || bridge.status !== 'active') {
      this.log.error('Target bridge unavailable', { targetBridge: fullPacket.targetBridge, status: bridge?.status });
      this.audit.append({
        actor: 'SentinelStation',
        action: 'ROUTE_FAILED',
        entity: fullPacket.id,
        status: 'FAILURE',
        details: { reason: 'bridge_unavailable', targetBridge: fullPacket.targetBridge },
      });
      return null;
    }

    // Route to the bridge
    const result = await bridge.accept(fullPacket);

    this.audit.append({
      actor: 'SentinelStation',
      action: 'ROUTE_TRAFFIC',
      entity: fullPacket.id,
      status: result ? 'SUCCESS' : 'FAILURE',
      details: { trafficClass, targetBridge: fullPacket.targetBridge, source: packet.source },
    });

    return result;
  }

  /** Cross-bridge escalation — route a packet from one bridge to another */
  async escalate(packet: BridgeTrafficPacket, targetBridge: BridgeDomain): Promise<BridgeTrafficPacket | null> {
    const bridge = this.bridges.get(targetBridge);
    if (!bridge || bridge.status !== 'active') {
      this.log.error('Escalation target bridge unavailable', { targetBridge });
      return null;
    }

    const escalatedPacket: BridgeTrafficPacket = {
      ...packet,
      targetBridge,
      escalated: true,
      originalBridge: packet.targetBridge,
    };

    this.log.info('Cross-bridge escalation', {
      packetId: packet.id,
      fromBridge: packet.targetBridge,
      toBridge: targetBridge,
    });

    this.audit.append({
      actor: 'SentinelStation',
      action: 'ESCALATE',
      entity: packet.id,
      status: 'SUCCESS',
      details: { fromBridge: packet.targetBridge, toBridge: targetBridge },
    });

    return bridge.accept(escalatedPacket);
  }

  /** Classify traffic to determine target bridge */
  classifyTraffic(trafficClass: TrafficClass): BridgeDomain {
    const rule = this.routingRules.find(r => r.trafficClass === trafficClass);
    if (rule) return rule.targetBridge;

    // Default routing for unknown traffic classes
    switch (trafficClass) {
      case 'internal_health':
      case 'cross_bridge':
      case 'unknown':
        return 'nexus'; // Route unknowns through Nexus for safety
      default:
        return 'nexus';
    }
  }

  /** Start all bridges */
  async start(): Promise<void> {
    await this.infinityBridge.start();
    await this.nexusBridge.start();
    await this.hiveBridge.start();
    this.log.info('Sentinel Station online — all three bridges active', {
      bridges: Array.from(this.bridges.values()).map(b => ({ domain: b.domain, status: b.status })),
    });
  }

  /** Stop all bridges */
  async stop(): Promise<void> {
    await this.infinityBridge.stop();
    await this.nexusBridge.stop();
    await this.hiveBridge.stop();
    this.log.info('Sentinel Station offline — all bridges stopped');
  }

  /** Get aggregated health from all bridges */
  aggregateHealth(): {
    overallStatus: BridgeStatus;
    bridges: BridgeHealthReport[];
    totalPacketsProcessed: number;
    totalPacketsPending: number;
    routingRules: number;
  } {
    const reports: BridgeHealthReport[] = [];
    let totalProcessed = 0;
    let totalPending = 0;
    let anyOffline = false;
    let anyDegraded = false;

    for (const [, bridge] of this.bridges) {
      const health = bridge.healthCheck();
      reports.push(health);
      totalProcessed += health.packetsProcessed;
      totalPending += health.packetsPending;
      if (health.status === 'offline') anyOffline = true;
      if (health.status === 'degraded') anyDegraded = true;
    }

    let overallStatus: BridgeStatus = 'active';
    if (anyOffline) overallStatus = 'offline';
    else if (anyDegraded) overallStatus = 'degraded';

    // If any bridge is offline, the overall status is at least degraded
    if (overallStatus === 'active' && reports.some(r => r.status === 'offline')) {
      overallStatus = 'degraded';
    }

    return {
      overallStatus: anyOffline ? 'degraded' : anyDegraded ? 'degraded' : 'active',
      bridges: reports,
      totalPacketsProcessed: totalProcessed,
      totalPacketsPending: totalPending,
      routingRules: this.routingRules.length,
    };
  }

  /** Get a specific bridge by domain */
  getBridge(domain: BridgeDomain): IBridge | undefined {
    return this.bridges.get(domain);
  }

  /** Proactive: check all bridges and report anomalies */
  scanBridgeHealth(): { anomalies: string[]; recommendations: string[] } {
    const anomalies: string[] = [];
    const recommendations: string[] = [];

    for (const [, bridge] of this.bridges) {
      const health = bridge.healthCheck();

      if (health.status === 'offline') {
        anomalies.push(`${bridge.domain} bridge is offline`);
        recommendations.push(`Restart ${bridge.domain} bridge`);
      }

      if (health.errorRate > 0.1) {
        anomalies.push(`${bridge.domain} bridge has high error rate: ${(health.errorRate * 100).toFixed(1)}%`);
        recommendations.push(`Investigate ${bridge.domain} bridge error patterns`);
      }

      if (health.packetsPending > 100) {
        anomalies.push(`${bridge.domain} bridge has ${health.packetsPending} pending packets`);
        recommendations.push(`Scale ${bridge.domain} bridge capacity`);
      }

      if (health.averageLatencyMs > 1000) {
        anomalies.push(`${bridge.domain} bridge has high latency: ${health.averageLatencyMs.toFixed(0)}ms`);
        recommendations.push(`Optimize ${bridge.domain} bridge processing`);
      }
    }

    return { anomalies, recommendations };
  }
}
