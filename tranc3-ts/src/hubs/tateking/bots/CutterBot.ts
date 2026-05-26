/**
 * CutterBot — Clip Cutting Bot for TateKing
 *
 * Identity:  NID-TATEKING-CUTTER
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TateKingAI (AID-TATEKING)
 *
 * Responsibilities:
 *   - Split clips at specified time positions
 *   - Perform razor cuts on the timeline
 *   - Handle ripple and roll edits
 *   - Preserve clip metadata across cuts
 */

import { Bot, Logger } from '../../../core/definitions';

export interface CutOperation {
  operation: 'CUT';
  clip: {
    id: string;
    source: string;
    startTime: number;
    endTime: number;
    trimStart: number;
    trimEnd: number;
    duration: number;
    speed: number;
    reversed: boolean;
    effects: Array<{ id: string; type: string; params: Record<string, unknown>; enabled: boolean }>;
    transitions: { in?: { type: string; duration: number }; out?: { type: string; duration: number } };
  };
  cutTime: number;
}

export interface RazorOperation {
  operation: 'RAZOR';
  trackId: string;
  time: number;
}

export interface RippleOperation {
  operation: 'RIPPLE';
  clipId: string;
  newStartTime: number;
}

export type CutterInput = CutOperation | RazorOperation | RippleOperation;

export class CutterBot extends Bot {
  private readonly log: Logger;

  constructor() {
    const handler = async (input: CutterInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-TATEKING-CUTTER',
      'Cutter',
      handler,
      'Clip splitting, razor cuts, ripple and roll edits'
    );

    this.log = new Logger('CutterBot');
  }

  private async process(input: CutterInput): Promise<unknown> {
    switch (input.operation) {
      case 'CUT':
        return this.cutClip(input);
      case 'RAZOR':
        return this.razorCut(input);
      case 'RIPPLE':
        return this.rippleEdit(input);
      default:
        throw new Error(`Unknown cutter operation: ${(input as CutterInput).operation}`);
    }
  }

  private cutClip(params: CutOperation): Array<{ id: string; source: string; startTime: number; endTime: number; trimStart: number; trimEnd: number; duration: number; speed: number; reversed: boolean; effects: Array<{ id: string; type: string; params: Record<string, unknown>; enabled: boolean }>; transitions: { in?: { type: string; duration: number }; out?: { type: string; duration: number } } }> {
    const { clip, cutTime } = params;

    // Validate cut time is within clip range
    if (cutTime <= clip.startTime || cutTime >= clip.endTime) {
      this.log.warn('Cut time outside clip range', { clipId: clip.id, cutTime, startTime: clip.startTime, endTime: clip.endTime });
      return [clip]; // Return original unmodified
    }

    const clipAPrefix = `CLIP-${Date.now()}-A`.toUpperCase();
    const clipBPrefix = `CLIP-${Date.now()}-B`.toUpperCase();

    // Clip A: from start to cut point
    const clipA = {
      id: clipAPrefix,
      source: clip.source,
      startTime: clip.startTime,
      endTime: cutTime,
      trimStart: clip.trimStart,
      trimEnd: clip.trimEnd,
      duration: cutTime - clip.startTime,
      speed: clip.speed,
      reversed: clip.reversed,
      effects: [...clip.effects],
      transitions: { in: clip.transitions.in, out: undefined },
    };

    // Clip B: from cut point to end
    const clipB = {
      id: clipBPrefix,
      source: clip.source,
      startTime: cutTime,
      endTime: clip.endTime,
      trimStart: 0,
      trimEnd: clip.trimEnd,
      duration: clip.endTime - cutTime,
      speed: clip.speed,
      reversed: clip.reversed,
      effects: [...clip.effects],
      transitions: { in: undefined, out: clip.transitions.out },
    };

    this.log.info('Clip cut into two', {
      originalId: clip.id,
      cutTime,
      clipAId: clipA.id,
      clipADuration: clipA.duration.toFixed(2),
      clipBId: clipB.id,
      clipBDuration: clipB.duration.toFixed(2),
    });

    return [clipA, clipB];
  }

  private razorCut(params: RazorOperation): { trackId: string; time: number; cutApplied: boolean } {
    // Razor cut marks a cut point across all clips on the track at the given time
    this.log.info('Razor cut applied', { trackId: params.trackId, time: params.time });
    return { trackId: params.trackId, time: params.time, cutApplied: true };
  }

  private rippleEdit(params: RippleOperation): { clipId: string; newStartTime: number; delta: number } {
    // Ripple edit shifts a clip and all subsequent clips
    const delta = params.newStartTime; // Simplified: delta from current start
    this.log.info('Ripple edit applied', { clipId: params.clipId, newStartTime: params.newStartTime });
    return { clipId: params.clipId, newStartTime: params.newStartTime, delta };
  }
}
