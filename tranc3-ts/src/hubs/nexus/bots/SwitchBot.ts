/**
 * SwitchBot — Message Switching Bot for The Nexus
 *
 * Identity:  NID-NEXUS-SWITCH
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    NexusAI (AID-NEXUS)
 *
 * Responsibilities:
 *   - SEND:       Deliver a message to a specific channel/subscriber
 *   - BROADCAST:  Fan-out a message to all subscribers of a channel
 *   - SUBSCRIBE:  Register a connection to receive channel messages
 *   - UNSUBSCRIBE: Remove a connection from a channel's subscriber list
 */

import { Bot, Logger, AuditLedger } from '../../../core/definitions'

const auditLedger = new AuditLedger();

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

export interface SwitchInput {
  operation: 'SEND' | 'BROADCAST' | 'SUBSCRIBE' | 'UNSUBSCRIBE';
  channelId?: string;
  connectionId?: string;
  message?: string;
  targetConnectionId?: string;
}

export interface SwitchResult {
  success: boolean;
  operation: SwitchInput['operation'];
  messageId: string;
  recipients: number;
  message: string;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Subscription Store
// ─────────────────────────────────────────────────────────────────────────────

let messageCounter = 0;
const subscriptions: Map<string, Set<string>> = new Map();

// ─────────────────────────────────────────────────────────────────────────────
// SwitchBot Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class SwitchBot extends Bot {
  private readonly log: Logger;
  private readonly audit: AuditLedger;

  constructor() {
    super(
      'NID-NEXUS-SWITCH',
      'Switch',
      async (input: SwitchInput) => this.handleOperation(input),
      'Message switching bot: send, broadcast, subscribe, and unsubscribe operations for channel-based communication'
    );

    this.log = new Logger('SwitchBot');
    this.audit = auditLedger;
  }

  private async handleOperation(input: SwitchInput): Promise<SwitchResult> {
    messageCounter++;
    const messageId = `MSG-${messageCounter.toString().padStart(8, '0')}`;

    switch (input.operation) {
      case 'SEND': {
        const channelId = input.channelId ?? 'CH-00000000';
        if (!subscriptions.has(channelId)) subscriptions.set(channelId, new Set());
        const subs = subscriptions.get(channelId)!;
        const target = input.targetConnectionId ?? input.connectionId ?? 'CONN-00000000';
        return {
          success: true,
          operation: 'SEND',
          messageId,
          recipients: subs.has(target) ? 1 : 0,
          message: `Message ${messageId} sent to ${target} on channel ${channelId}`,
          timestamp: Date.now(),
        };
      }
      case 'BROADCAST': {
        const channelId = input.channelId ?? 'CH-00000000';
        if (!subscriptions.has(channelId)) subscriptions.set(channelId, new Set());
        const subs = subscriptions.get(channelId)!;
        return {
          success: true,
          operation: 'BROADCAST',
          messageId,
          recipients: subs.size,
          message: `Message ${messageId} broadcast to ${subs.size} subscribers on channel ${channelId}`,
          timestamp: Date.now(),
        };
      }
      case 'SUBSCRIBE': {
        const channelId = input.channelId ?? 'CH-00000000';
        const connId = input.connectionId ?? 'CONN-00000000';
        if (!subscriptions.has(channelId)) subscriptions.set(channelId, new Set());
        subscriptions.get(channelId)!.add(connId);
        this.log.info('Subscription added', { channelId, connectionId: connId });
        return {
          success: true,
          operation: 'SUBSCRIBE',
          messageId,
          recipients: subscriptions.get(channelId)!.size,
          message: `Connection ${connId} subscribed to channel ${channelId}`,
          timestamp: Date.now(),
        };
      }
      case 'UNSUBSCRIBE': {
        const channelId = input.channelId ?? 'CH-00000000';
        const connId = input.connectionId ?? 'CONN-00000000';
        if (subscriptions.has(channelId)) {
          subscriptions.get(channelId)!.delete(connId);
        }
        return {
          success: true,
          operation: 'UNSUBSCRIBE',
          messageId,
          recipients: subscriptions.get(channelId)?.size ?? 0,
          message: `Connection ${connId} unsubscribed from channel ${channelId}`,
          timestamp: Date.now(),
        };
      }
      default:
        return {
          success: false,
          operation: input.operation,
          messageId,
          recipients: 0,
          message: `Unknown operation: ${input.operation}`,
          timestamp: Date.now(),
        };
    }
  }
}
