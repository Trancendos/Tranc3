/**
 * TateKingAI — Lead AI for the TateKing Hub
 *
 * Identity:  AID-TATEKING
 * Pillar:    Savania
 * Tier:      3 (Lead AI / Domain Orchestrator)
 * Domain:    Video editing, timeline management, clip composition,
 *            rendering, scrubbing, and post-production
 *
 * Pipeline:  Scrubber → Cutter → Editor → Director → Renderer
 *            Splicer handles clip joining and transitions
 */

import { AI, Agent, Bot, Logger, AuditLedger } from '../../core/definitions'
import { DirectorAgent } from './agents/DirectorAgent';
import { EditorAgent } from './agents/EditorAgent';
import { CutterBot } from './bots/CutterBot';
import { SplicerBot } from './bots/SplicerBot';
import { RendererBot } from './bots/RendererBot';
import { ScrubberBot } from './bots/ScrubberBot';

const auditLedger = new AuditLedger();

// ───────────────────────────────────────────
// Domain Interfaces
// ───────────────────────────────────────────

export interface VideoProject {
  id: string;
  name: string;
  createdAt: number;
  modifiedAt: number;
  duration: number;
  resolution: { width: number; height: number };
  frameRate: number;
  timeline: Timeline;
  tracks: Track[];
  metadata: Record<string, unknown>;
}

export interface Timeline {
  id: string;
  duration: number;
  currentTime: number;
  tracks: string[]; // track IDs
  markers: Marker[];
}

export interface Track {
  id: string;
  name: string;
  type: 'video' | 'audio' | 'text' | 'effect';
  clips: Clip[];
  enabled: boolean;
  volume?: number;
  opacity?: number;
}

export interface Clip {
  id: string;
  source: string;
  startTime: number;
  endTime: number;
  trimStart: number;
  trimEnd: number;
  duration: number;
  transitions: {
    in?: Transition;
    out?: Transition;
  };
  effects: Effect[];
  speed: number;
  reversed: boolean;
}

export interface Transition {
  type: 'cut' | 'dissolve' | 'wipe' | 'fade' | 'slide' | 'zoom';
  duration: number;
  params?: Record<string, unknown>;
}

export interface Effect {
  id: string;
  type: string;
  name: string;
  params: Record<string, unknown>;
  enabled: boolean;
  keyframes?: Keyframe[];
}

export interface Keyframe {
  time: number;
  value: number;
  interpolation: 'linear' | 'bezier' | 'hold';
}

export interface Marker {
  id: string;
  time: number;
  label: string;
  color: string;
  duration: number;
}

export interface RenderConfig {
  format: 'mp4' | 'webm' | 'mov' | 'avi' | 'gif';
  codec: 'h264' | 'h265' | 'vp9' | 'av1';
  quality: 'draft' | 'standard' | 'high' | 'lossless';
  resolution: { width: number; height: number };
  frameRate: number;
  bitrate: number;
  audioCodec?: 'aac' | 'opus' | 'mp3';
  audioBitrate?: number;
}

// ───────────────────────────────────────────
// TateKingAI Implementation
// ───────────────────────────────────────────

export class TateKingAI extends AI {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private projects: Map<string, VideoProject>;

  constructor() {
    super(
      'AID-TATEKING',
      'TateKing',
      'tateking',
      'Savania',
      3
    );

    this.log = new Logger('TateKingAI');
    this.audit = auditLedger;
    this.projects = new Map();

    // Register Agents
    this.registerAgent(new DirectorAgent());
    this.registerAgent(new EditorAgent());

    // Register Bots
    this.registerBot(new CutterBot());
    this.registerBot(new SplicerBot());
    this.registerBot(new RendererBot());
    this.registerBot(new ScrubberBot());

    this.log.info('TateKingAI initialised', {
      agents: this.listAgentIds(),
      bots: this.listBotNames(),
    });
  }

  // ───────────────────────────────────────
  // Project Management
  // ───────────────────────────────────────

  /**
   * Create a new video project with a default timeline.
   */
  createProject(name: string, resolution: { width: number; height: number } = { width: 1920, height: 1080 }, frameRate: number = 30): VideoProject {
    const timelineId = `TL-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`.toUpperCase();
    const projectId = `PROJ-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`.toUpperCase();

    const project: VideoProject = {
      id: projectId,
      name,
      createdAt: Date.now(),
      modifiedAt: Date.now(),
      duration: 0,
      resolution,
      frameRate,
      timeline: {
        id: timelineId,
        duration: 0,
        currentTime: 0,
        tracks: [],
        markers: [],
      },
      tracks: [],
      metadata: {},
    };

    this.projects.set(projectId, project);

    this.audit.append({
      actor: this.id,
      action: 'PROJECT_CREATED',
      entity: projectId,
      details: { name, resolution, frameRate },
      timestamp: new Date(),
    });

    this.log.info('Video project created', { projectId, name });
    return project;
  }

  /**
   * Get a project by ID.
   */
  getProject(projectId: string): VideoProject | undefined {
    return this.projects.get(projectId);
  }

  // ───────────────────────────────────────
  // Timeline Operations
  // ───────────────────────────────────────

  /**
   * Add a new track to the project timeline.
   */
  addTrack(projectId: string, type: Track['type'], name?: string): Track | null {
    const project = this.projects.get(projectId);
    if (!project) return null;

    const track: Track = {
      id: `TRACK-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`.toUpperCase(),
      name: name ?? `${type} Track ${project.tracks.length + 1}`,
      type,
      clips: [],
      enabled: true,
      volume: 1.0,
      opacity: 1.0,
    };

    project.tracks.push(track);
    project.timeline.tracks.push(track.id);
    project.modifiedAt = Date.now();

    this.log.info('Track added', { projectId, trackId: track.id, type });
    return track;
  }

  /**
   * Scrub to a specific time position in the timeline.
   */
  async scrubTo(projectId: string, time: number): Promise<{ currentTime: number; frame: number } | null> {
    const project = this.projects.get(projectId);
    if (!project) return null;

    const scrubber = this.getBot('Scrubber')!;
    const result = await scrubber.execute({
      operation: 'SEEK',
      projectId,
      time,
      frameRate: project.frameRate,
    });

    project.timeline.currentTime = time;
    return result as { currentTime: number; frame: number };
  }

  // ───────────────────────────────────────
  // Clip Operations
  // ───────────────────────────────────────

  /**
   * Cut a clip at the specified time position, delegating to CutterBot.
   */
  async cutClip(projectId: string, trackId: string, clipIndex: number, cutTime: number): Promise<Clip[] | null> {
    const project = this.projects.get(projectId);
    if (!project) return null;

    const track = project.tracks.find(t => t.id === trackId);
    if (!track || clipIndex >= track.clips.length) return null;

    const cutter = this.getBot('Cutter')!;
    const result = await cutter.execute({
      operation: 'CUT',
      clip: track.clips[clipIndex],
      cutTime,
    });

    // Replace original clip with two new clips
    const newClips = result as Clip[];
    track.clips.splice(clipIndex, 1, ...newClips);
    project.modifiedAt = Date.now();

    this.log.info('Clip cut', { projectId, trackId, clipIndex, cutTime });
    return newClips;
  }

  /**
   * Splice (join) two adjacent clips, delegating to SplicerBot.
   */
  async spliceClips(projectId: string, trackId: string, clipIndexA: number, clipIndexB: number, transition?: Transition): Promise<Clip | null> {
    const project = this.projects.get(projectId);
    if (!project) return null;

    const track = project.tracks.find(t => t.id === trackId);
    if (!track) return null;

    const clipA = track.clips[clipIndexA];
    const clipB = track.clips[clipIndexB];
    if (!clipA || !clipB) return null;

    const splicer = this.getBot('Splicer')!;
    const result = await splicer.execute({
      operation: 'JOIN',
      clipA,
      clipB,
      transition,
    });

    const joinedClip = result as Clip;

    // Replace both clips with the joined one
    const minIdx = Math.min(clipIndexA, clipIndexB);
    const maxIdx = Math.max(clipIndexA, clipIndexB);
    track.clips.splice(minIdx, maxIdx - minIdx + 1, joinedClip);
    project.modifiedAt = Date.now();

    this.log.info('Clips spliced', { projectId, trackId, clipIndexA, clipIndexB });
    return joinedClip;
  }

  // ───────────────────────────────────────
  // Director & Editor Operations
  // ───────────────────────────────────────

  /**
   * Delegate editing decisions to EditorAgent.
   */
  async editProject(projectId: string, editInstructions: Record<string, unknown>): Promise<unknown> {
    const project = this.projects.get(projectId);
    if (!project) throw new Error(`Project not found: ${projectId}`);

    const editor = this.getAgent('SID-TATEKING-EDITOR') as EditorAgent;
    const result = await editor.runCycle({ project, instructions: editInstructions });

    project.modifiedAt = Date.now();
    this.log.info('Edit applied via EditorAgent', { projectId });
    return result;
  }

  /**
   * Delegate high-level direction to DirectorAgent.
   */
  async directProject(projectId: string, direction: string): Promise<unknown> {
    const project = this.projects.get(projectId);
    if (!project) throw new Error(`Project not found: ${projectId}`);

    const director = this.getAgent('SID-TATEKING-DIRECTOR') as DirectorAgent;
    const result = await director.runCycle({ project, direction });

    this.log.info('Direction applied via DirectorAgent', { projectId, direction });
    return result;
  }

  // ───────────────────────────────────────
  // Rendering
  // ───────────────────────────────────────

  /**
   * Render the project to output, delegating to RendererBot.
   */
  async renderProject(projectId: string, config: RenderConfig): Promise<{ renderId: string; status: string; estimatedTimeSeconds: number } | null> {
    const project = this.projects.get(projectId);
    if (!project) return null;

    const renderer = this.getBot('Renderer')!;
    const result = await renderer.execute({
      operation: 'RENDER',
      project,
      config,
    });

    this.audit.append({
      actor: this.id,
      action: 'PROJECT_RENDERED',
      entity: projectId,
      details: { format: config.format, codec: config.codec, quality: config.quality },
      timestamp: new Date(),
    });

    this.log.info('Project render initiated', { projectId, format: config.format });
    return result as { renderId: string; status: string; estimatedTimeSeconds: number };
  }

  // ───────────────────────────────────────
  // Health & Diagnostics
  // ───────────────────────────────────────

  healthCheck(): {
    status: 'healthy' | 'degraded' | 'critical';
    projects: number;
    agents: number;
    bots: number;
    timestamp: number;
  } {
    return {
      status: 'healthy',
      projects: this.projects.size,
      agents: this.listAgentIds().length,
      bots: this.listBotNames().length,
      timestamp: Date.now(),
    };
  }
}
