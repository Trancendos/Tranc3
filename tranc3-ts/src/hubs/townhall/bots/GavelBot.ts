/**
 * Gavel Bot — Town Hall Tier 5 Bot (NID-TOWNHALL-GAVEL)
 *
 * Manages session lifecycle: start, end, voting calls, and adjournment.
 * The gavel is the symbol of authority — this bot enforces session boundaries.
 */

import { Bot, Logger } from '../../../core/definitions';

const logger = new Logger('GavelBot');

export interface GavelRequest {
  action: 'START_SESSION' | 'END_SESSION' | 'CALL_VOTE' | 'ADJOURN' | 'RECESS';
  sessionId?: string;
  motion?: string;
}

export interface GavelResult {
  action: string;
  sessionActive: boolean;
  sessionId: string;
  timestamp: Date;
  announcement: string;
}

export class GavelBot extends Bot {
  private sessionActive: boolean = false;
  private currentSessionId: string = '';

  constructor() {
    super(
      'Gavel',
      async (request: GavelRequest): Promise<GavelResult> => {
        const sessionId = request.sessionId || `SESSION-${Date.now()}`;

        switch (request.action) {
          case 'START_SESSION':
            this.sessionActive = true;
            this.currentSessionId = sessionId;
            logger.info('Session called to order', { sessionId });
            return {
              action: request.action,
              sessionActive: true,
              sessionId,
              timestamp: new Date(),
              announcement: `Hear ye! Session ${sessionId} is called to order.`,
            };

          case 'END_SESSION':
            this.sessionActive = false;
            logger.info('Session adjourned', { sessionId: this.currentSessionId });
            return {
              action: request.action,
              sessionActive: false,
              sessionId: this.currentSessionId,
              timestamp: new Date(),
              announcement: `Session ${this.currentSessionId} is adjourned. Good order prevailed.`,
            };

          case 'CALL_VOTE':
            logger.info('Vote called', { motion: request.motion });
            return {
              action: request.action,
              sessionActive: this.sessionActive,
              sessionId: this.currentSessionId,
              timestamp: new Date(),
              announcement: `The question is called: ${request.motion || 'the motion on the floor'}. All in favor?`,
            };

          case 'ADJOURN':
            this.sessionActive = false;
            return {
              action: request.action,
              sessionActive: false,
              sessionId: this.currentSessionId,
              timestamp: new Date(),
              announcement: `Session ${this.currentSessionId} stands adjourned until next called.`,
            };

          case 'RECESS':
            return {
              action: request.action,
              sessionActive: this.sessionActive,
              sessionId: this.currentSessionId,
              timestamp: new Date(),
              announcement: `Recess is called. Session ${this.currentSessionId} will resume shortly.`,
            };

          default:
            return {
              action: request.action,
              sessionActive: this.sessionActive,
              sessionId: this.currentSessionId,
              timestamp: new Date(),
              announcement: `Unknown gavel action: ${request.action}`,
            };
        }
      },
      'Manages Town Hall session lifecycle: calling to order, adjournment, and voting calls',
    );
  }
}
