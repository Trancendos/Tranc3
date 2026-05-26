/**
 * ScrubberBot — Timeline Scrubbing Bot for TateKing
 *
 * Identity:  NID-TATEKING-SCRUBBER
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TateKingAI (AID-TATEKING)
 *
 * Responsibilities:
 *   - Navigate timeline to specific time positions
 *   - Compute frame numbers from time codes
 *   - Generate thumbnail previews at scrub positions
 *   - Support variable-speed scrubbing (jog, shuttle)
 *   - Provide timecode formatting and parsing
 */

import { Bot, Logger } from '../../../core/definitions';

export interface SeekOperation {
  operation: 'SEEK';
  projectId: string;
  time: number;
  frameRate: number;
}

export interface FrameOperation {
  operation: 'FRAME';
  frame: number;
  frameRate: number;
}

export interface ThumbnailOperation {
  operation: 'THUMBNAIL';
  projectId: string;
  interval: number; // seconds between thumbnails
  duration: number;
}

export interface ShuttleOperation {
  operation: 'SHUTTLE';
  currentTime: number;
  speed: number; // -10 to 10, negative = reverse
  deltaTime: number;
}

export type ScrubberInput = SeekOperation | FrameOperation | ThumbnailOperation | ShuttleOperation;

export class ScrubberBot extends Bot {
  private readonly log: Logger;

  constructor() {
    const handler = async (input: ScrubberInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-TATEKING-SCRUBBER',
      'Scrubber',
      handler,
      'Timeline navigation, frame computation, thumbnail generation, shuttle control'
    );

    this.log = new Logger('ScrubberBot');
  }

  private async process(input: ScrubberInput): Promise<unknown> {
    switch (input.operation) {
      case 'SEEK':
        return this.seek(input);
      case 'FRAME':
        return this.frameToTime(input);
      case 'THUMBNAIL':
        return this.generateThumbnails(input);
      case 'SHUTTLE':
        return this.shuttle(input);
      default:
        throw new Error(`Unknown scrubber operation: ${(input as ScrubberInput).operation}`);
    }
  }

  private seek(params: SeekOperation): { currentTime: number; frame: number; timecode: string } {
    const frame = Math.floor(params.time * params.frameRate);
    const timecode = this.frameToTimecode(frame, params.frameRate);

    this.log.debug('Seek completed', { time: params.time, frame, timecode });
    return { currentTime: params.time, frame, timecode };
  }

  private frameToTime(params: FrameOperation): { time: number; frame: number; timecode: string } {
    const time = params.frame / params.frameRate;
    const timecode = this.frameToTimecode(params.frame, params.frameRate);

    return { time, frame: params.frame, timecode };
  }

  private generateThumbnails(params: ThumbnailOperation): Array<{ time: number; frame: number; timecode: string }> {
    const thumbnails: Array<{ time: number; frame: number; timecode: string }> = [];
    const frameRate = 30; // default for thumbnails

    for (let t = 0; t < params.duration; t += params.interval) {
      const frame = Math.floor(t * frameRate);
      thumbnails.push({
        time: t,
        frame,
        timecode: this.frameToTimecode(frame, frameRate),
      });
    }

    this.log.info('Thumbnails generated', { projectId: params.projectId, count: thumbnails.length, interval: params.interval });
    return thumbnails;
  }

  private shuttle(params: ShuttleOperation): { currentTime: number; speed: number; direction: 'forward' | 'reverse' | 'stopped' } {
    const newTime = Math.max(0, params.currentTime + params.speed * params.deltaTime);
    const direction = params.speed > 0 ? 'forward' as const : params.speed < 0 ? 'reverse' as const : 'stopped' as const;

    this.log.debug('Shuttle move', { currentTime: newTime, speed: params.speed, direction });
    return { currentTime: newTime, speed: params.speed, direction };
  }

  // ───────────────────────────────────────
  // Helpers
  // ───────────────────────────────────────

  private frameToTimecode(frame: number, frameRate: number): string {
    const totalSeconds = Math.floor(frame / frameRate);
    const frames = frame % Math.round(frameRate);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;

    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}:${frames.toString().padStart(2, '0')}`;
  }
}
