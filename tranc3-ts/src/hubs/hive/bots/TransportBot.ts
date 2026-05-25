/**
 * TransportBot — Data Transport Bot for The HIVE
 *
 * Identity:  NID-HIVE-TRANSPORT
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    QueenAI (AID-QUEEN)
 *
 * Responsibilities:
 *   - ENQUEUE:   Add data payloads to the transport queue for delivery
 *   - DEQUEUE:   Remove and return the next payload from the transport queue
 *   - TRANSPORT: Execute the delivery of a payload to a target estate node
 *   - STATUS:    Query the current state of the transport pipeline
 *   - PURGE:     Clear stale or failed entries from the transport queue
 *
 * "Data flows through The HIVE like blood through a body. TransportBot
 *  is the circulatory system — every enqueue is a heartbeat, every
 *  transport a pulse, every delivery a breath of the swarm mind."
 */

import { Bot, Logger, AuditLedger } from '../../../core/definitions'

const auditLedger = new AuditLedger();

// ─────────────────────────────────────────────────────────────────────────────
// Input / Output Types
// ─────────────────────────────────────────────────────────────────────────────

export interface TransportInput {
  operation: 'ENQUEUE' | 'DEQUEUE' | 'TRANSPORT' | 'STATUS' | 'PURGE';
  taskId?: string;
  payload?: Record<string, unknown>;
  targetNode?: string;
  priority?: 'critical' | 'high' | 'medium' | 'low';
  maxRetries?: number;
  purgeAge?: number; // milliseconds
}

export interface TransportEntry {
  id: string;
  taskId: string;
  payload: Record<string, unknown>;
  targetNode: string;
  priority: TransportInput['priority'];
  status: 'queued' | 'in_transit' | 'delivered' | 'failed' | 'expired';
  retryCount: number;
  maxRetries: number;
  enqueuedAt: number;
  dispatchedAt: number | null;
  deliveredAt: number | null;
  error: string | null;
}

export interface TransportStatus {
  queueSize: number;
  inTransit: number;
  delivered: number;
  failed: number;
  expired: number;
  averageLatency: number;
  throughputPerMinute: number;
  timestamp: number;
}

export interface TransportResult {
  success: boolean;
  operation: TransportInput['operation'];
  entry?: TransportEntry;
  status?: TransportStatus;
  purgedCount?: number;
  message: string;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Queue Storage
// ─────────────────────────────────────────────────────────────────────────────

let entryCounter = 0;
const transportQueue: Map<string, TransportEntry> = new Map();
const PRIORITY_ORDER: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

// ─────────────────────────────────────────────────────────────────────────────
// TransportBot Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class TransportBot extends Bot {
  private readonly log: Logger;
  private readonly audit: AuditLedger;

  constructor() {
    super(
      'NID-HIVE-TRANSPORT',
      'Transport',
      async (input: TransportInput) => this.handleOperation(input),
      'Manages data transport queue: enqueue, dequeue, transport, status, and purge operations'
    );

    this.log = new Logger('TransportBot');
    this.audit = auditLedger;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Main Handler
  // ─────────────────────────────────────────────────────────────────────────

  private async handleOperation(input: TransportInput): Promise<TransportResult> {
    switch (input.operation) {
      case 'ENQUEUE':
        return this.enqueue(input);
      case 'DEQUEUE':
        return this.dequeue(input);
      case 'TRANSPORT':
        return this.transport(input);
      case 'STATUS':
        return this.status();
      case 'PURGE':
        return this.purge(input.purgeAge);
      default:
        return this.fail(`Unknown operation: ${input.operation}`);
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // ENQUEUE — Add entry to the transport queue
  // ─────────────────────────────────────────────────────────────────────────

  private enqueue(input: TransportInput): TransportResult {
    if (!input.payload && !input.taskId) {
      return this.fail('ENQUEUE requires either a taskId or payload');
    }

    entryCounter++;
    const entry: TransportEntry = {
      id: `TRN-${entryCounter.toString().padStart(8, '0')}`,
      taskId: input.taskId ?? `TSK-${entryCounter.toString().padStart(8, '0')}`,
      payload: input.payload ?? {},
      targetNode: input.targetNode ?? 'EST-00000001',
      priority: input.priority ?? 'medium',
      status: 'queued',
      retryCount: 0,
      maxRetries: input.maxRetries ?? 3,
      enqueuedAt: Date.now(),
      dispatchedAt: null,
      deliveredAt: null,
      error: null,
    };

    transportQueue.set(entry.id, entry);

    this.audit.append({
      actor: 'NID-HIVE-TRANSPORT',
      action: 'ENQUEUE',
      entity: entry.id,
      status: 'SUCCESS',
      meta: { taskId: entry.taskId, targetNode: entry.targetNode, priority: entry.priority },
    });

    this.log.info('Entry enqueued', { id: entry.id, taskId: entry.taskId, priority: entry.priority });

    return {
      success: true,
      operation: 'ENQUEUE',
      entry,
      message: `Transport entry ${entry.id} enqueued for ${entry.targetNode} (${entry.priority} priority)`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // DEQUEUE — Remove and return the highest-priority entry
  // ─────────────────────────────────────────────────────────────────────────

  private dequeue(_input: TransportInput): TransportResult {
    // Find the highest-priority queued entry
    let bestEntry: TransportEntry | null = null;
    let bestPriority = Infinity;

    for (const [, entry] of transportQueue) {
      if (entry.status === 'queued') {
        const priorityNum = PRIORITY_ORDER[entry.priority ?? 'medium'] ?? 2;
        if (priorityNum < bestPriority || (priorityNum === bestPriority && bestEntry && entry.enqueuedAt < bestEntry.enqueuedAt)) {
          bestEntry = entry;
          bestPriority = priorityNum;
        }
      }
    }

    if (!bestEntry) {
      return {
        success: false,
        operation: 'DEQUEUE',
        message: 'No queued entries available for dequeue',
        timestamp: Date.now(),
      };
    }

    bestEntry.status = 'in_transit';
    bestEntry.dispatchedAt = Date.now();

    return {
      success: true,
      operation: 'DEQUEUE',
      entry: bestEntry,
      message: `Dequeued entry ${bestEntry.id} for transport to ${bestEntry.targetNode}`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // TRANSPORT — Execute delivery of a payload
  // ─────────────────────────────────────────────────────────────────────────

  private transport(input: TransportInput): TransportResult {
    const entryId = input.taskId;
    if (!entryId) {
      return this.fail('TRANSPORT requires a taskId or entryId');
    }

    // Find entry by id or taskId
    let entry: TransportEntry | undefined;
    for (const [, e] of transportQueue) {
      if (e.id === entryId || e.taskId === entryId) {
        entry = e;
        break;
      }
    }

    if (!entry) {
      return this.fail(`Transport entry not found: ${entryId}`);
    }

    if (entry.targetNode && input.targetNode) {
      entry.targetNode = input.targetNode;
    }

    entry.status = 'delivered';
    entry.dispatchedAt = entry.dispatchedAt ?? Date.now();
    entry.deliveredAt = Date.now();

    this.audit.append({
      actor: 'NID-HIVE-TRANSPORT',
      action: 'TRANSPORT',
      entity: entry.id,
      status: 'SUCCESS',
      meta: { taskId: entry.taskId, targetNode: entry.targetNode },
    });

    this.log.info('Entry transported', { id: entry.id, targetNode: entry.targetNode });

    return {
      success: true,
      operation: 'TRANSPORT',
      entry,
      message: `Transport entry ${entry.id} delivered to ${entry.targetNode}`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // STATUS — Query transport pipeline state
  // ─────────────────────────────────────────────────────────────────────────

  private status(): TransportResult {
    const entries = Array.from(transportQueue.values());
    const queued = entries.filter(e => e.status === 'queued').length;
    const inTransit = entries.filter(e => e.status === 'in_transit').length;
    const delivered = entries.filter(e => e.status === 'delivered').length;
    const failed = entries.filter(e => e.status === 'failed').length;
    const expired = entries.filter(e => e.status === 'expired').length;

    const deliveredEntries = entries.filter(e => e.status === 'delivered' && e.dispatchedAt && e.deliveredAt);
    const averageLatency = deliveredEntries.length > 0
      ? deliveredEntries.reduce((sum, e) => sum + (e.deliveredAt! - e.dispatchedAt!), 0) / deliveredEntries.length
      : 0;

    const oneMinuteAgo = Date.now() - 60000;
    const recentDeliveries = entries.filter(e => e.deliveredAt && e.deliveredAt >= oneMinuteAgo).length;

    const statusResult: TransportStatus = {
      queueSize: queued,
      inTransit,
      delivered,
      failed,
      expired,
      averageLatency: Math.round(averageLatency),
      throughputPerMinute: recentDeliveries,
      timestamp: Date.now(),
    };

    return {
      success: true,
      operation: 'STATUS',
      status: statusResult,
      message: `Transport pipeline: ${queued} queued, ${inTransit} in-transit, ${delivered} delivered, ${failed} failed`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // PURGE — Remove stale or failed entries
  // ─────────────────────────────────────────────────────────────────────────

  private purge(maxAge?: number): TransportResult {
    const cutoff = Date.now() - (maxAge ?? 3600000); // default 1 hour
    let purgedCount = 0;

    for (const [id, entry] of transportQueue) {
      if (
        (entry.status === 'delivered' && entry.deliveredAt && entry.deliveredAt < cutoff) ||
        (entry.status === 'failed' && entry.enqueuedAt < cutoff) ||
        (entry.status === 'expired')
      ) {
        transportQueue.delete(id);
        purgedCount++;
      }
    }

    this.log.info('Queue purged', { purgedCount, maxAge: maxAge ?? 3600000 });

    return {
      success: true,
      operation: 'PURGE',
      purgedCount,
      message: `Purged ${purgedCount} stale/failed/expired entries from transport queue`,
      timestamp: Date.now(),
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Failure Helper
  // ─────────────────────────────────────────────────────────────────────────

  private fail(message: string): TransportResult {
    this.log.error('Transport operation failed', { message });
    return {
      success: false,
      operation: 'ENQUEUE',
      message,
      timestamp: Date.now(),
    };
  }
}
