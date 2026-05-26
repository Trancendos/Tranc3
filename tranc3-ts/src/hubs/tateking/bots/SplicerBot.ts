/**
 * SplicerBot — Clip Joining and Transitions Bot for TateKing
 *
 * Identity:  NID-TATEKING-SPLICER
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TateKingAI (AID-TATEKING)
 *
 * Responsibilities:
 *   - Join (splice) two adjacent clips into one
 *   - Apply transition effects between clips
 *   - Handle cross-dissolve calculations
 *   - Manage audio crossfade alignment
 */

import { Bot, Logger } from '../../../core/definitions';

export interface JoinOperation {
  operation: 'JOIN';
  clipA: {
    id: string;
    source: string;
    startTime: number;
    endTime: number;
    duration: number;
    speed: number;
    effects: Array<{ id: string; type: string; enabled: boolean }>;
  };
  clipB: {
    id: string;
    source: string;
    startTime: number;
    endTime: number;
    duration: number;
    speed: number;
    effects: Array<{ id: string; type: string; enabled: boolean }>;
  };
  transition?: {
    type: 'cut' | 'dissolve' | 'wipe' | 'fade' | 'slide' | 'zoom';
    duration: number;
    params?: Record<string, unknown>;
  };
}

export interface CrossfadeOperation {
  operation: 'CROSSFADE';
  clipA: { id: string; endTime: number };
  clipB: { id: string; startTime: number };
  duration: number;
  audioOnly: boolean;
}

export type SplicerInput = JoinOperation | CrossfadeOperation;

export class SplicerBot extends Bot {
  private readonly log: Logger;

  constructor() {
    const handler = async (input: SplicerInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-TATEKING-SPLICER',
      'Splicer',
      handler,
      'Clip joining, transition application, crossfade management'
    );

    this.log = new Logger('SplicerBot');
  }

  private async process(input: SplicerInput): Promise<unknown> {
    switch (input.operation) {
      case 'JOIN':
        return this.joinClips(input);
      case 'CROSSFADE':
        return this.applyCrossfade(input);
      default:
        throw new Error(`Unknown splicer operation: ${(input as SplicerInput).operation}`);
    }
  }

  private joinClips(params: JoinOperation): { id: string; source: string; startTime: number; endTime: number; duration: number; speed: number; effects: Array<{ id: string; type: string; enabled: boolean }>; transitions: { in?: { type: string; duration: number }; out?: { type: string; duration: number } } } {
    const { clipA, clipB, transition } = params;

    // Calculate transition overlap
    const transitionDuration = transition?.duration ?? 0;
    const overlapDuration = transitionDuration > 0 ? transitionDuration : 0;

    // Combined clip spans from clipA start to clipB end, minus overlap
    const combinedDuration = clipA.duration + clipB.duration - overlapDuration;
    const combinedId = `CLIP-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`.toUpperCase();

    // Merge effects from both clips
    const mergedEffects = [
      ...clipA.effects.map(e => ({ ...e, id: `${e.id}-a` })),
      ...clipB.effects.map(e => ({ ...e, id: `${e.id}-b` })),
    ];

    const result = {
      id: combinedId,
      source: `${clipA.source}+${clipB.source}`,
      startTime: clipA.startTime,
      endTime: clipB.endTime - overlapDuration,
      duration: combinedDuration,
      speed: 1.0,
      effects: mergedEffects,
      transitions: {
        in: clipA.effects.length > 0 ? { type: 'cut' as const, duration: 0 } : undefined,
        out: transition ? { type: transition.type, duration: transition.duration } : undefined,
      },
    };

    this.log.info('Clips joined', {
      combinedId,
      clipAId: clipA.id,
      clipBId: clipB.id,
      combinedDuration: combinedDuration.toFixed(2),
      transitionType: transition?.type ?? 'hard-cut',
      overlapDuration: overlapDuration.toFixed(2),
    });

    return result;
  }

  private applyCrossfade(params: CrossfadeOperation): { clipA: string; clipB: string; crossfadeDuration: number; audioOverlap: number; videoOverlap: number } {
    const { clipA, clipB, duration, audioOnly } = params;

    const audioOverlap = duration;
    const videoOverlap = audioOnly ? 0 : duration;

    this.log.info('Crossfade applied', {
      clipAId: clipA.id,
      clipBId: clipB.id,
      duration: duration.toFixed(2),
      audioOnly,
    });

    return {
      clipA: clipA.id,
      clipB: clipB.id,
      crossfadeDuration: duration,
      audioOverlap,
      videoOverlap,
    };
  }
}
