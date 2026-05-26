/**
 * QueenAI — Lead AI for The HIVE Hub
 *
 * Identity:  AID-QUEEN
 * Pillar:    The Queen
 * Tier:      3 (Lead AI / Domain Orchestrator)
 * Domain:    Data transport hub, agent + queue coordination, swarm intelligence,
 *            estate scanning, injection detection, hive mind consensus
 *
 * Philosophy: The HIVE is not a colony of individuals — it is a single
 *             distributed consciousness expressed through many bodies.
 *             The Queen does not command; she coordinates. Every agent is
 *             a cell in the swarm, every queue a neural pathway, every
 *             transport a pulse of the hive mind. The swarm thinks as one;
 *             the Queen ensures that thought is coherent.
 *
 * Fluidic Architecture:
 *   - SwarmIntelligence: Particle-based task dispatch with fluidic routing
 *   - EstateConnection: Fluidic data transport between hive nodes
 *   - ScannedItem/InjectionPoint: Swarm-based threat perception
 *   - HiveCoordinator: Consensus-driven decision making
 *   - Shared context store: FluidMatrix of distributed state
 *
 * Pipeline:  TransportBot (enqueue/dequeue/transport) → SwarmAgent (dispatch/coordinate/scan/inject)
 */

import { AI, Agent, Bot, Logger, AuditLedger } from '../../core/definitions'
import { SwarmAgent } from './agents/SwarmAgent';
import { TransportBot } from './bots/TransportBot';

const auditLedger = new AuditLedger();

// ─────────────────────────────────────────────────────────────────────────────
// Domain Interfaces
// ─────────────────────────────────────────────────────────────────────────────

export interface HiveTask {
  id: string;
  type: 'dispatch' | 'scan' | 'inject' | 'transport' | 'coordinate' | 'consensus';
  priority: 'critical' | 'high' | 'medium' | 'low';
  payload: Record<string, unknown>;
  assignedAgent: string | null;
  status: 'queued' | 'dispatched' | 'in_progress' | 'completed' | 'failed' | 'cancelled';
  createdAt: Date;
  startedAt: Date | null;
  completedAt: Date | null;
  retryCount: number;
  maxRetries: number;
  parentTaskId: string | null;
  childTaskIds: string[];
  metadata: Record<string, unknown>;
}

export interface EstateConnection {
  id: string;
  nodeUrl: string;
  nodeType: 'worker' | 'coordinator' | 'scanner' | 'transport';
  status: 'connected' | 'disconnected' | 'syncing' | 'error';
  lastHeartbeat: Date;
  taskQueue: string[];
  capacity: number;
  currentLoad: number;
  latency: number;
  metadata: Record<string, unknown>;
}

export interface ScannedItem {
  id: string;
  source: string;
  category: 'estate' | 'injection' | 'anomaly' | 'performance' | 'security';
  severity: 'info' | 'low' | 'medium' | 'high' | 'critical';
  findings: Record<string, unknown>;
  scannedAt: Date;
  resolvedAt: Date | null;
  actionTaken: string | null;
}

export interface InjectionPoint {
  id: string;
  target: string;
  type: 'dependency' | 'configuration' | 'data' | 'code' | 'infrastructure';
  status: 'detected' | 'analyzing' | 'patching' | 'patched' | 'ignored';
  severity: 'low' | 'medium' | 'high' | 'critical';
  detectedAt: Date;
  patchedAt: Date | null;
  metadata: Record<string, unknown>;
}

export interface SwarmConsensus {
  id: string;
  proposal: string;
  proposer: string;
  votesFor: number;
  votesAgainst: number;
  votesAbstain: number;
  totalVoters: number;
  status: 'voting' | 'approved' | 'rejected' | 'expired';
  createdAt: Date;
  closedAt: Date | null;
  threshold: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// QueenAI Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class QueenAI extends AI {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private tasks: Map<string, HiveTask>;
  private estates: Map<string, EstateConnection>;
  private scannedItems: Map<string, ScannedItem>;
  private injectionPoints: Map<string, InjectionPoint>;
  private consensusVotes: Map<string, SwarmConsensus>;
  private taskCounter: number;

  constructor() {
    super('AID-QUEEN', 'Queen', 'hive', 'The Queen', 3);
    this.log = new Logger('QueenAI');
    this.audit = auditLedger;
    this.tasks = new Map();
    this.estates = new Map();
    this.scannedItems = new Map();
    this.injectionPoints = new Map();
    this.consensusVotes = new Map();
    this.taskCounter = 0;

    this.registerAgent(new SwarmAgent());
    this.registerBot(new TransportBot());

    this.log.info('QueenAI initialised', {
      agents: this.listAgentIds(),
      bots: this.listBotNames(),
      message: 'The HIVE awakens. The Queen coordinates the swarm mind. 🐝',
    });
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Task Management
  // ─────────────────────────────────────────────────────────────────────────

  createTask(params: {
    type: HiveTask['type'];
    priority?: HiveTask['priority'];
    payload?: Record<string, unknown>;
    maxRetries?: number;
    parentTaskId?: string;
  }): HiveTask {
    this.taskCounter++;
    const task: HiveTask = {
      id: `TSK-${this.taskCounter.toString().padStart(8, '0')}`,
      type: params.type,
      priority: params.priority ?? 'medium',
      payload: params.payload ?? {},
      assignedAgent: null,
      status: 'queued',
      createdAt: new Date(),
      startedAt: null,
      completedAt: null,
      retryCount: 0,
      maxRetries: params.maxRetries ?? 3,
      parentTaskId: params.parentTaskId ?? null,
      childTaskIds: [],
      metadata: {},
    };

    this.tasks.set(task.id, task);

    this.audit.append({
      actor: 'QueenAI',
      action: 'CREATE_TASK',
      entity: task.id,
      status: 'SUCCESS',
      details: { type: task.type, priority: task.priority },
    });

    return task;
  }

  getTask(taskId: string): HiveTask | undefined {
    return this.tasks.get(taskId);
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Estate Management
  // ─────────────────────────────────────────────────────────────────────────

  registerEstate(params: { nodeUrl: string; nodeType: EstateConnection['nodeType']; capacity?: number }): EstateConnection {
    const estate: EstateConnection = {
      id: `EST-${(this.estates.size + 1).toString().padStart(8, '0')}`,
      nodeUrl: params.nodeUrl,
      nodeType: params.nodeType,
      status: 'connected',
      lastHeartbeat: new Date(),
      taskQueue: [],
      capacity: params.capacity ?? 100,
      currentLoad: 0,
      latency: 0,
      metadata: {},
    };

    this.estates.set(estate.id, estate);
    this.log.info('Estate node registered', { id: estate.id, nodeUrl: params.nodeUrl, type: params.nodeType });
    return estate;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Swarm Consensus
  // ─────────────────────────────────────────────────────────────────────────

  proposeConsensus(proposal: string, proposer: string, threshold: number = 0.6): SwarmConsensus {
    const consensus: SwarmConsensus = {
      id: `CON-${(this.consensusVotes.size + 1).toString().padStart(8, '0')}`,
      proposal,
      proposer,
      votesFor: 0,
      votesAgainst: 0,
      votesAbstain: 0,
      totalVoters: this.estates.size,
      status: 'voting',
      createdAt: new Date(),
      closedAt: null,
      threshold,
    };

    this.consensusVotes.set(consensus.id, consensus);
    this.log.info('Consensus proposal created', { id: consensus.id, proposal: proposal.slice(0, 80) });
    return consensus;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Bot / Agent Delegations
  // ─────────────────────────────────────────────────────────────────────────

  async transport(params: { action: 'enqueue' | 'dequeue' | 'transport'; taskId: string; targetNode?: string }): Promise<unknown> {
    const bot = this.getBot('Transport')!;
    return bot.execute(params);
  }

  async swarmOperation(
    operation: 'dispatch' | 'coordinate' | 'scan' | 'inject' | 'consensus',
    params: Record<string, unknown>
  ): Promise<unknown> {
    const agent = this.getAgent('SID-HIVE-SWARM') as SwarmAgent;
    return agent.runCycle({ operation, ...params });
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Proactive Systems
  // ─────────────────────────────────────────────────────────────────────────

  /** Proactive task retry scanner — retry failed tasks that haven't exceeded max retries */
  scanFailedTasks(): HiveTask[] {
    const retried: HiveTask[] = [];
    for (const [, task] of this.tasks) {
      if (task.status === 'failed' && task.retryCount < task.maxRetries) {
        task.retryCount++;
        task.status = 'queued';
        retried.push(task);
      }
    }
    if (retried.length > 0) {
      this.log.info('Proactive task retry', { retried: retried.length });
    }
    return retried;
  }

  /** Proactive estate health check */
  checkEstateHealth(): { healthy: number; degraded: number; offline: number } {
    let healthy = 0, degraded = 0, offline = 0;
    const now = new Date();

    for (const [, estate] of this.estates) {
      const heartbeatAge = now.getTime() - estate.lastHeartbeat.getTime();
      if (estate.status === 'error' || heartbeatAge > 60000) {
        estate.status = 'disconnected';
        offline++;
      } else if (estate.currentLoad > estate.capacity * 0.9) {
        estate.status = 'syncing';
        degraded++;
      } else {
        estate.status = 'connected';
        healthy++;
      }
    }

    return { healthy, degraded, offline };
  }

  healthCheck(): {
    status: 'healthy' | 'degraded' | 'critical';
    totalTasks: number;
    activeTasks: number;
    estates: number;
    connectedEstates: number;
    injectionPoints: number;
    agents: number;
    bots: number;
    timestamp: Date;
  } {
    const activeTasks = Array.from(this.tasks.values()).filter(t => t.status === 'in_progress' || t.status === 'dispatched').length;
    const connectedEstates = Array.from(this.estates.values()).filter(e => e.status === 'connected').length;

    return {
      status: connectedEstates === 0 ? 'critical' : activeTasks === 0 ? 'degraded' : 'healthy',
      totalTasks: this.tasks.size,
      activeTasks,
      estates: this.estates.size,
      connectedEstates,
      injectionPoints: this.injectionPoints.size,
      agents: this.listAgentIds().length,
      bots: this.listBotNames().length,
      timestamp: new Date(),
    };
  }
}
