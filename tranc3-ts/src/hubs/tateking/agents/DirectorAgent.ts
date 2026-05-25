/**
 * DirectorAgent — High-Level Video Direction Agent for TateKing
 *
 * Identity:  SID-TATEKING-DIRECTOR
 * Tier:      4 (Autonomous Microservice)
 * Parent:    TateKingAI (AID-TATEKING)
 *
 * Responsibilities:
 *   - Analyze video content and suggest creative direction
 *   - Evaluate pacing, rhythm, and narrative flow
 *   - Recommend cut points, transitions, and effects
 *   - Assess overall production quality and coherence
 *   - Generate shot lists and storyboards from scripts
 *   - Provide style and mood recommendations
 */

import { Agent, Logger, AuditLedger } from '../../../core/definitions'

const auditLedger = new AuditLedger();

// ───────────────────────────────────────────
// Domain Types
// ───────────────────────────────────────────

export interface DirectionInput {
  project: {
    id: string;
    name: string;
    duration: number;
    tracks: Array<{
      id: string;
      type: string;
      clips: Array<{
        id: string;
        startTime: number;
        endTime: number;
        duration: number;
        source: string;
        effects: Array<{ type: string; enabled: boolean }>;
        transitions: { in?: { type: string }; out?: { type: string } };
      }>;
    }>;
  };
  direction: string;
}

export interface PacingAnalysis {
  overallPace: 'slow' | 'moderate' | 'fast' | 'dynamic';
  averageClipDuration: number;
  shortestClip: number;
  longestClip: number;
  cutFrequency: number; // cuts per minute
  rhythmScore: number; // 0-1
  recommendation: string;
}

export interface StyleRecommendation {
  currentStyle: string;
  suggestedStyle: string;
  confidence: number;
  moodBoard: string[];
  colorGrading: string;
  aspectRatio: string;
}

export interface CutSuggestion {
  clipId: string;
  suggestedCutTime: number;
  reason: string;
  priority: 'low' | 'medium' | 'high';
  impact: string;
}

export interface DirectionResult {
  pacing: PacingAnalysis;
  style: StyleRecommendation;
  cutSuggestions: CutSuggestion[];
  overallScore: number;
  notes: string[];
}

type DirectorDecision =
  | 'ANALYZE_PACING'
  | 'SUGGEST_STYLE'
  | 'RECOMMEND_CUTS'
  | 'EVALUATE_FLOW'
  | 'GENERATE_STORYBOARD';

// ───────────────────────────────────────────
// DirectorAgent Implementation
// ───────────────────────────────────────────

export class DirectorAgent extends Agent {
  private readonly log: Logger;
  private readonly audit: AuditLedger;

  constructor() {
    super(
      'SID-TATEKING-DIRECTOR',
      'DirectorAgent',
      'TateKing'
    );

    this.log = new Logger('DirectorAgent');
    this.audit = auditLedger;

    this.registerTool('analyzePacing', this.analyzePacing.bind(this));
    this.registerTool('suggestStyle', this.suggestStyle.bind(this));
    this.registerTool('recommendCuts', this.recommendCuts.bind(this));
    this.registerTool('evaluateFlow', this.evaluateFlow.bind(this));
    this.registerTool('generateStoryboard', this.generateStoryboard.bind(this));

    this.log.info('DirectorAgent initialised');
  }

  // ───────────────────────────────────────
  // Abstract Implementations
  // ───────────────────────────────────────

  public async perceive(input: unknown): Promise<unknown> {
    const { project, direction } = input as DirectionInput;

    // Count all clips across tracks
    const allClips: Array<{ trackType: string; clip: DirectionInput['project']['tracks'][0]['clips'][0] }> = [];
    for (const track of project.tracks) {
      for (const clip of track.clips) {
        allClips.push({ trackType: track.type, clip });
      }
    }

    const perception = {
      projectId: project.id,
      totalClips: allClips.length,
      totalDuration: project.duration,
      direction: direction.toLowerCase(),
      hasVideoTracks: project.tracks.some(t => t.type === 'video'),
      hasAudioTracks: project.tracks.some(t => t.type === 'audio'),
      averageClipDuration: allClips.length > 0
        ? allClips.reduce((sum, c) => sum + c.clip.duration, 0) / allClips.length
        : 0,
      effectCount: allClips.reduce((sum, c) => sum + c.clip.effects.filter(e => e.enabled).length, 0),
      transitionCount: allClips.reduce((sum, c) => sum + (c.clip.transitions.in ? 1 : 0) + (c.clip.transitions.out ? 1 : 0), 0),
    };

    this.memory.push(perception);
    return perception;
  }

  public async decide(perception: unknown): Promise<DirectorDecision> {
    const p = perception as { direction: string; totalClips: number; totalDuration: number };

    // Decide based on the direction keyword and project state
    const dir = p.direction;

    if (dir.includes('pac') || dir.includes('rhythm') || dir.includes('tempo')) {
      return 'ANALYZE_PACING';
    }
    if (dir.includes('style') || dir.includes('mood') || dir.includes('look') || dir.includes('color')) {
      return 'SUGGEST_STYLE';
    }
    if (dir.includes('cut') || dir.includes('trim') || dir.includes('edit')) {
      return 'RECOMMEND_CUTS';
    }
    if (dir.includes('flow') || dir.includes('narrative') || dir.includes('story')) {
      return 'EVALUATE_FLOW';
    }
    if (dir.includes('storyboard') || dir.includes('shot') || dir.includes('plan')) {
      return 'GENERATE_STORYBOARD';
    }

    // Default: analyze pacing as the most common starting point
    return 'ANALYZE_PACING';
  }

  public async act(decision: DirectorDecision, perception: unknown): Promise<DirectionResult> {
    const p = perception as DirectionInput;
    this.log.info('Director acting on decision', { decision, projectId: p.project.id });

    let pacing: PacingAnalysis;
    let style: StyleRecommendation | undefined;
    let cutSuggestions: CutSuggestion[] = [];
    let overallScore = 0.5;
    const notes: string[] = [];

    // Always compute pacing analysis
    pacing = this.analyzePacing(p.project);

    switch (decision) {
      case 'ANALYZE_PACING':
        overallScore = pacing.rhythmScore;
        notes.push(`Overall pace: ${pacing.overallPace}`);
        notes.push(pacing.recommendation);
        break;

      case 'SUGGEST_STYLE':
        style = this.suggestStyle(p.project, p.direction);
        overallScore = style.confidence;
        notes.push(`Current style: ${style.currentStyle}`);
        notes.push(`Suggested style: ${style.suggestedStyle}`);
        notes.push(`Color grading: ${style.colorGrading}`);
        break;

      case 'RECOMMEND_CUTS':
        cutSuggestions = this.recommendCuts(p.project);
        overallScore = cutSuggestions.length > 0 ? 0.6 : 0.9;
        notes.push(`Found ${cutSuggestions.length} cut suggestions`);
        break;

      case 'EVALUATE_FLOW':
        const flowScore = this.evaluateFlow(p.project);
        overallScore = flowScore;
        notes.push(`Narrative flow score: ${flowScore.toFixed(2)}`);
        break;

      case 'GENERATE_STORYBOARD':
        const storyboard = this.generateStoryboard(p.project, p.direction);
        notes.push(`Generated storyboard with ${storyboard.shots.length} shots`);
        notes.push(`Estimated duration: ${storyboard.totalDuration.toFixed(1)}s`);
        overallScore = 0.7;
        break;
    }

    const result: DirectionResult = {
      pacing,
      style: style ?? {
        currentStyle: 'documentary',
        suggestedStyle: 'cinematic',
        confidence: 0.5,
        moodBoard: ['warm tones', 'shallow depth of field', 'natural lighting'],
        colorGrading: 'warm highlights, cool shadows',
        aspectRatio: '16:9',
      },
      cutSuggestions,
      overallScore,
      notes,
    };

    this.audit.append({
      actor: this.id,
      action: 'DIRECTION_APPLIED',
      entity: p.project.id,
      details: { decision, overallScore, noteCount: notes.length },
      timestamp: new Date(),
    });

    this.episodeCount++;
    return result;
  }

  // ───────────────────────────────────────
  // Tool Implementations
  // ───────────────────────────────────────

  private analyzePacing(project: DirectionInput['project']): PacingAnalysis {
    const videoClips: Array<{ duration: number }> = [];
    for (const track of project.tracks) {
      if (track.type === 'video') {
        for (const clip of track.clips) {
          videoClips.push({ duration: clip.duration });
        }
      }
    }

    if (videoClips.length === 0) {
      return {
        overallPace: 'slow',
        averageClipDuration: 0,
        shortestClip: 0,
        longestClip: 0,
        cutFrequency: 0,
        rhythmScore: 0,
        recommendation: 'No video clips found. Add clips to analyze pacing.',
      };
    }

    const durations = videoClips.map(c => c.duration);
    const avgDuration = durations.reduce((a, b) => a + b, 0) / durations.length;
    const shortest = Math.min(...durations);
    const longest = Math.max(...durations);
    const cutsPerMinute = project.duration > 0 ? (videoClips.length / project.duration) * 60 : 0;

    let pace: PacingAnalysis['overallPace'];
    let rhythmScore: number;

    if (cutsPerMinute > 20) {
      pace = 'fast';
      rhythmScore = 0.7;
    } else if (cutsPerMinute > 10) {
      pace = 'dynamic';
      rhythmScore = 0.85;
    } else if (cutsPerMinute > 5) {
      pace = 'moderate';
      rhythmScore = 0.75;
    } else {
      pace = 'slow';
      rhythmScore = 0.5;
    }

    // Adjust score based on consistency
    const variance = durations.reduce((sum, d) => sum + Math.pow(d - avgDuration, 2), 0) / durations.length;
    const consistencyBonus = Math.max(0, 0.2 - Math.sqrt(variance) / avgDuration);
    rhythmScore = Math.min(1, rhythmScore + consistencyBonus);

    let recommendation: string;
    if (pace === 'slow') {
      recommendation = 'Consider trimming longer clips to improve pacing. Try cutting to tighter shots for key moments.';
    } else if (pace === 'fast') {
      recommendation = 'The pace is very rapid. Consider letting some moments breathe with longer holds for emotional impact.';
    } else {
      recommendation = 'Pacing is well-balanced. Consider varying clip lengths to create rhythm and emphasis.';
    }

    return {
      overallPace: pace,
      averageClipDuration: avgDuration,
      shortestClip: shortest,
      longestClip: longest,
      cutFrequency: cutsPerMinute,
      rhythmScore,
      recommendation,
    };
  }

  private suggestStyle(project: DirectionInput['project'], direction: string): StyleRecommendation {
    // Determine current style based on effects and transitions
    const effectTypes = new Set<string>();
    for (const track of project.tracks) {
      for (const clip of track.clips) {
        for (const effect of clip.effects) {
          if (effect.enabled) effectTypes.add(effect.type);
        }
      }
    }

    let currentStyle = 'raw';
    if (effectTypes.has('color-grade')) currentStyle = 'graded';
    if (effectTypes.has('film-grain')) currentStyle = 'cinematic';
    if (effectTypes.has('vhs')) currentStyle = 'retro';

    // Determine suggested style from direction
    let suggestedStyle = 'cinematic';
    let moodBoard = ['dramatic lighting', 'shallow depth of field', 'anamorphic flare'];
    let colorGrading = 'teal and orange';
    let aspectRatio = '2.39:1';

    if (direction.includes('documentary') || direction.includes('natural')) {
      suggestedStyle = 'documentary';
      moodBoard = ['natural lighting', 'handheld movement', 'environmental sound'];
      colorGrading = 'neutral with warm skin tones';
      aspectRatio = '16:9';
    } else if (direction.includes('retro') || direction.includes('vintage') || direction.includes('nostalgic')) {
      suggestedStyle = 'retro';
      moodBoard = ['film grain', 'desaturated colors', 'vignette'];
      colorGrading = 'faded warm tones, lifted blacks';
      aspectRatio = '4:3';
    } else if (direction.includes('modern') || direction.includes('clean') || direction.includes('minimal')) {
      suggestedStyle = 'modern';
      moodBoard = ['clean lines', 'high contrast', 'geometric composition'];
      colorGrading = 'cool tones, crushed blacks';
      aspectRatio = '16:9';
    }

    const confidence = currentStyle === suggestedStyle ? 0.3 : 0.7;

    return { currentStyle, suggestedStyle, confidence, moodBoard, colorGrading, aspectRatio };
  }

  private recommendCuts(project: DirectionInput['project']): CutSuggestion[] {
    const suggestions: CutSuggestion[] = [];

    for (const track of project.tracks) {
      if (track.type !== 'video') continue;

      for (const clip of track.clips) {
        // Suggest cutting overly long clips
        if (clip.duration > 10) {
          const cutPoint = clip.startTime + clip.duration * 0.4;
          suggestions.push({
            clipId: clip.id,
            suggestedCutTime: cutPoint,
            reason: 'Long clip may benefit from a cut to maintain viewer engagement',
            priority: clip.duration > 30 ? 'high' : 'medium',
            impact: 'Improved pacing and rhythm',
          });
        }

        // Suggest cutting at low-motion points
        if (clip.duration > 5) {
          suggestions.push({
            clipId: clip.id,
            suggestedCutTime: clip.startTime + clip.duration * 0.6,
            reason: 'Potential natural break point for transition',
            priority: 'low',
            impact: 'Smoother transition to next clip',
          });
        }
      }
    }

    return suggestions;
  }

  private evaluateFlow(project: DirectionInput['project']): number {
    if (project.tracks.length === 0) return 0;

    // Score based on: track count, clip distribution, transition usage
    let score = 0.5;

    // Bonus for having both video and audio tracks
    const trackTypes = new Set(project.tracks.map(t => t.type));
    if (trackTypes.has('video') && trackTypes.has('audio')) score += 0.1;

    // Bonus for transitions
    let transitionCount = 0;
    for (const track of project.tracks) {
      for (const clip of track.clips) {
        if (clip.transitions.in) transitionCount++;
        if (clip.transitions.out) transitionCount++;
      }
    }
    if (transitionCount > 0) score += 0.1;

    // Penalty for very long clips without cuts
    const longClips = project.tracks
      .flatMap(t => t.clips)
      .filter(c => c.duration > 15).length;
    if (longClips > 3) score -= 0.1;

    return Math.max(0, Math.min(1, score));
  }

  private generateStoryboard(project: DirectionInput['project'], direction: string): { shots: Array<{ shotNumber: number; description: string; duration: number; type: string }>; totalDuration: number } {
    const shots: Array<{ shotNumber: number; description: string; duration: number; type: string }> = [];

    // Generate shots based on direction and existing clips
    const shotTypes = ['wide', 'medium', 'close-up', 'establishing', 'cutaway', 'insert'];
    const totalDuration = project.duration || 60;
    const shotCount = Math.max(5, Math.floor(totalDuration / 4));

    for (let i = 0; i < shotCount; i++) {
      shots.push({
        shotNumber: i + 1,
        description: `${shotTypes[i % shotTypes.length]} shot for "${direction}" segment ${i + 1}`,
        duration: totalDuration / shotCount,
        type: shotTypes[i % shotTypes.length],
      });
    }

    return { shots, totalDuration };
  }
}
