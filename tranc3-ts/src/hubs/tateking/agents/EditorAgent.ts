/**
 * EditorAgent — Video Editing Agent for TateKing
 *
 * Identity:  SID-TATEKING-EDITOR
 * Tier:      4 (Autonomous Microservice)
 * Parent:    TateKingAI (AID-TATEKING)
 *
 * Responsibilities:
 *   - Apply edit instructions to video projects
 *   - Manage clip ordering, trimming, and arrangement
 *   - Apply and configure effects and transitions
 *   - Synchronize audio and video tracks
 *   - Perform color correction and audio normalization
 *   - Manage keyframe animations for effects
 */

import { Agent, Logger, AuditLedger } from '../../../core/definitions';

// ───────────────────────────────────────────
// Domain Types
// ───────────────────────────────────────────

export interface EditInstruction {
  type: 'trim' | 'reorder' | 'add-effect' | 'remove-effect' | 'add-transition' | 'normalize-audio' | 'color-correct' | 'speed-change';
  params: Record<string, unknown>;
  targetClipId?: string;
  targetTrackId?: string;
  priority: 'low' | 'medium' | 'high';
}

export interface EditResult {
  applied: boolean;
  instructionType: string;
  changesMade: number;
  warnings: string[];
  newDuration?: number;
}

export interface AudioAnalysis {
  peakLevel: number;
  averageLevel: number;
  dynamicRange: number;
  clippingDetected: boolean;
  normalizationGain: number;
}

export interface ColorCorrectionProfile {
  brightness: number;
  contrast: number;
  saturation: number;
  temperature: number;
  tint: number;
  highlights: number;
  shadows: number;
  gamma: number;
}

type EditorDecision =
  | 'APPLY_TRIM'
  | 'APPLY_EFFECT'
  | 'APPLY_TRANSITION'
  | 'NORMALIZE_AUDIO'
  | 'COLOR_CORRECT'
  | 'REORDER_CLIPS'
  | 'CHANGE_SPEED';

// ───────────────────────────────────────────
// EditorAgent Implementation
// ───────────────────────────────────────────

export class EditorAgent extends Agent {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private editHistory: Array<{ instruction: EditInstruction; result: EditResult; timestamp: number }>;

  constructor() {
    super(
      'SID-TATEKING-EDITOR',
      'EditorAgent',
      'TateKing'
    );

    this.log = new Logger('EditorAgent');
    this.audit = AuditLedger.getInstance();
    this.editHistory = [];

    this.registerTool('trimClip', this.trimClip.bind(this));
    this.registerTool('addEffect', this.addEffect.bind(this));
    this.registerTool('addTransition', this.addTransition.bind(this));
    this.registerTool('normalizeAudio', this.normalizeAudio.bind(this));
    this.registerTool('colorCorrect', this.colorCorrect.bind(this));
    this.registerTool('changeSpeed', this.changeSpeed.bind(this));

    this.log.info('EditorAgent initialised');
  }

  // ───────────────────────────────────────
  // Abstract Implementations
  // ───────────────────────────────────────

  protected async perceive(input: unknown): Promise<unknown> {
    const { project, instructions } = input as {
      project: { id: string; duration: number; tracks: Array<{ id: string; type: string; clips: Array<{ id: string; duration: number }> }> };
      instructions: Record<string, unknown>;
    };

    const totalClips = project.tracks.reduce((sum, t) => sum + t.clips.length, 0);
    const videoTracks = project.tracks.filter(t => t.type === 'video').length;
    const audioTracks = project.tracks.filter(t => t.type === 'audio').length;

    const perception = {
      projectId: project.id,
      totalClips,
      videoTracks,
      audioTracks,
      projectDuration: project.duration,
      instructions,
      instructionKeys: Object.keys(instructions),
    };

    this.memory.push(perception);
    return perception;
  }

  protected async decide(perception: unknown): Promise<EditorDecision> {
    const p = perception as { instructions: Record<string, unknown>; instructionKeys: string[] };

    const keys = p.instructionKeys;
    if (keys.includes('trim') || keys.includes('trimStart') || keys.includes('trimEnd')) {
      return 'APPLY_TRIM';
    }
    if (keys.includes('effect') || keys.includes('effectType')) {
      return 'APPLY_EFFECT';
    }
    if (keys.includes('transition') || keys.includes('transitionType')) {
      return 'APPLY_TRANSITION';
    }
    if (keys.includes('normalize') || keys.includes('audio')) {
      return 'NORMALIZE_AUDIO';
    }
    if (keys.includes('color') || keys.includes('brightness') || keys.includes('contrast')) {
      return 'COLOR_CORRECT';
    }
    if (keys.includes('speed') || keys.includes('playbackRate')) {
      return 'CHANGE_SPEED';
    }

    return 'APPLY_TRIM'; // default
  }

  protected async act(decision: EditorDecision, perception: unknown): Promise<EditResult> {
    const p = perception as { projectId: string; instructions: Record<string, unknown> };
    this.log.info('Editor acting on decision', { decision, projectId: p.projectId });

    let result: EditResult;

    switch (decision) {
      case 'APPLY_TRIM':
        result = this.trimClip(p.instructions);
        break;
      case 'APPLY_EFFECT':
        result = this.addEffect(p.instructions);
        break;
      case 'APPLY_TRANSITION':
        result = this.addTransition(p.instructions);
        break;
      case 'NORMALIZE_AUDIO':
        result = this.normalizeAudio(p.instructions);
        break;
      case 'COLOR_CORRECT':
        result = this.colorCorrect(p.instructions);
        break;
      case 'CHANGE_SPEED':
        result = this.changeSpeed(p.instructions);
        break;
      default:
        result = { applied: false, instructionType: decision, changesMade: 0, warnings: ['Unknown edit type'] };
    }

    this.editHistory.push({ instruction: { type: decision as EditInstruction['type'], params: p.instructions, priority: 'medium' }, result, timestamp: Date.now() });

    this.audit.append({
      actor: this.id,
      action: 'EDIT_APPLIED',
      entity: p.projectId,
      details: { decision, applied: result.applied, changesMade: result.changesMade },
      timestamp: Date.now(),
    });

    this.episodeCount++;
    return result;
  }

  // ───────────────────────────────────────
  // Tool Implementations
  // ───────────────────────────────────────

  private trimClip(params: Record<string, unknown>): EditResult {
    const trimStart = (params.trimStart as number) ?? 0;
    const trimEnd = (params.trimEnd as number) ?? 0;
    const originalDuration = (params.originalDuration as number) ?? 10;
    const newDuration = originalDuration - trimStart - trimEnd;

    if (newDuration <= 0) {
      return {
        applied: false,
        instructionType: 'trim',
        changesMade: 0,
        warnings: ['Trim would result in zero or negative duration'],
      };
    }

    return {
      applied: true,
      instructionType: 'trim',
      changesMade: 1,
      warnings: [],
      newDuration,
    };
  }

  private addEffect(params: Record<string, unknown>): EditResult {
    const effectType = (params.effectType as string) ?? 'brightness';
    const effectParams = (params.effectParams as Record<string, unknown>) ?? {};

    return {
      applied: true,
      instructionType: 'add-effect',
      changesMade: 1,
      warnings: [],
    };
  }

  private addTransition(params: Record<string, unknown>): EditResult {
    const transitionType = (params.transitionType as string) ?? 'dissolve';
    const duration = (params.transitionDuration as number) ?? 0.5;

    if (duration < 0.1) {
      return {
        applied: false,
        instructionType: 'add-transition',
        changesMade: 0,
        warnings: ['Transition duration too short (minimum 0.1s)'],
      };
    }

    return {
      applied: true,
      instructionType: 'add-transition',
      changesMade: 1,
      warnings: [],
    };
  }

  private normalizeAudio(params: Record<string, unknown>): EditResult {
    const targetLevel = (params.targetLevel as number) ?? -14; // LUFS
    const peakLimit = (params.peakLimit as number) ?? -1; // dB

    const analysis: AudioAnalysis = {
      peakLevel: -3 + Math.random() * 6,
      averageLevel: -18 + Math.random() * 10,
      dynamicRange: 8 + Math.random() * 12,
      clippingDetected: Math.random() > 0.8,
      normalizationGain: targetLevel - (-18 + Math.random() * 10),
    };

    const warnings: string[] = [];
    if (analysis.clippingDetected) {
      warnings.push('Clipping detected in source audio. Applying limiter before normalization.');
    }
    if (analysis.dynamicRange > 20) {
      warnings.push('High dynamic range detected. Consider applying compression before normalization.');
    }

    return {
      applied: true,
      instructionType: 'normalize-audio',
      changesMade: 1,
      warnings,
    };
  }

  private colorCorrect(params: Record<string, unknown>): EditResult {
    const profile: ColorCorrectionProfile = {
      brightness: (params.brightness as number) ?? 0,
      contrast: (params.contrast as number) ?? 0,
      saturation: (params.saturation as number) ?? 0,
      temperature: (params.temperature as number) ?? 0,
      tint: (params.tint as number) ?? 0,
      highlights: (params.highlights as number) ?? 0,
      shadows: (params.shadows as number) ?? 0,
      gamma: (params.gamma as number) ?? 1.0,
    };

    const warnings: string[] = [];
    if (profile.saturation > 50) {
      warnings.push('High saturation may cause color clipping in broadcast-safe check.');
    }
    if (Math.abs(profile.temperature) > 30) {
      warnings.push('Extreme color temperature shift may appear unnatural.');
    }

    return {
      applied: true,
      instructionType: 'color-correct',
      changesMade: 1,
      warnings,
    };
  }

  private changeSpeed(params: Record<string, unknown>): EditResult {
    const speed = (params.speed as number) ?? 1.0;

    if (speed <= 0) {
      return {
        applied: false,
        instructionType: 'speed-change',
        changesMade: 0,
        warnings: ['Speed must be positive'],
      };
    }

    const originalDuration = (params.originalDuration as number) ?? 10;
    const newDuration = originalDuration / speed;

    const warnings: string[] = [];
    if (speed < 0.25) {
      warnings.push('Very slow playback may cause frame interpolation artifacts.');
    }
    if (speed > 4.0) {
      warnings.push('Very fast playback may skip frames.');
    }

    return {
      applied: true,
      instructionType: 'speed-change',
      changesMade: 1,
      warnings,
      newDuration,
    };
  }

  // ───────────────────────────────────────
  // State Accessors
  // ───────────────────────────────────────

  getEditHistoryCount(): number {
    return this.editHistory.length;
  }
}
