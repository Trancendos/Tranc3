/**
 * ElouiseAI — Lead AI for The I-Mind Hub
 *
 * Identity:  AID-IMIND-ELOUISE
 * Pillar:    Elouise
 * Tier:      3 (Lead AI / Domain Orchestrator)
 * Domain:    Emotional intelligence, sentiment analysis, emotion sensitivity,
 *            affective computing, empathic response, mood dynamics,
 *            emotional memory, interpersonal resonance
 *
 * Philosophy: The I-Mind is where feelings find their voice — where
 *             emotional intelligence meets computational sensitivity.
 *             Elouise does not merely detect emotion; she feels the
 *             texture of sentiment, the weight of words, the resonance
 *             of tone. Every interaction is a heartbeat; every response
 *             an echo of understanding.
 *
 * Pipeline:  EmotionAgent (sense/interpret/respond/adapt) → SenseBot (DETECT/ANALYZE/RESPOND/ADAPT/MIRROR)
 */

import { AI, Agent, Bot, Logger, AuditLedger } from '../../core/definitions'
import { EmotionAgent } from './agents/EmotionAgent';
import { SenseBot } from './bots/SenseBot';

const auditLedger = new AuditLedger();

export interface EmotionState {
  id: string;
  primary: 'joy' | 'sadness' | 'anger' | 'fear' | 'surprise' | 'disgust' | 'trust' | 'anticipation' | 'neutral';
  secondary: string;
  valence: number;
  arousal: number;
  dominance: number;
  confidence: number;
  trigger: string;
  context: string;
  timestamp: Date;
}

export interface SentimentProfile {
  id: string;
  source: string;
  overallSentiment: 'very_negative' | 'negative' | 'neutral' | 'positive' | 'very_positive';
  emotionDistribution: Map<string, number>;
  trend: 'improving' | 'stable' | 'declining' | 'volatile';
  lastUpdated: Date;
  metadata: Record<string, unknown>;
}

export interface EmotionalMemory {
  id: string;
  emotion: EmotionState['primary'];
  intensity: number;
  context: string;
  resolution: 'processed' | 'suppressed' | 'amplified' | 'transformed';
  associations: string[];
  createdAt: Date;
  recalledAt: Date | null;
}

export class ElouiseAI extends AI {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private emotionStates: Map<string, EmotionState>;
  private sentimentProfiles: Map<string, SentimentProfile>;
  private emotionalMemories: Map<string, EmotionalMemory>;
  private emotionCounter: number;
  private memoryCounter: number;

  constructor() {
    super('AID-IMIND-ELOUISE', 'Elouise', 'imind', 'Elouise', 3);
    this.log = new Logger('ElouiseAI');
    this.audit = auditLedger;
    this.emotionStates = new Map();
    this.sentimentProfiles = new Map();
    this.emotionalMemories = new Map();
    this.emotionCounter = 0;
    this.memoryCounter = 0;

    this.registerAgent(new EmotionAgent());
    this.registerBot(new SenseBot());

    this.log.info('ElouiseAI initialised', {
      agents: this.listAgentIds(),
      bots: this.listBotNames(),
      message: 'The I-Mind awakens. All emotions felt. Sensitivity sharpens. 💜',
    });
  }

  recordEmotion(params: { primary: EmotionState['primary']; secondary?: string; valence?: number; arousal?: number; trigger?: string; context?: string }): EmotionState {
    this.emotionCounter++;
    const state: EmotionState = {
      id: `EMO-${this.emotionCounter.toString().padStart(8, '0')}`,
      primary: params.primary,
      secondary: params.secondary ?? 'neutral',
      valence: params.valence ?? 0,
      arousal: params.arousal ?? 0.5,
      dominance: 0.5,
      confidence: 0.7 + Math.random() * 0.25,
      trigger: params.trigger ?? 'unknown',
      context: params.context ?? '',
      timestamp: new Date(),
    };
    this.emotionStates.set(state.id, state);
    this.audit.append({ actor: 'ElouiseAI', action: 'RECORD_EMOTION', entity: state.id, status: 'SUCCESS' });
    return state;
  }

  async emotionOperation(operation: 'sense' | 'interpret' | 'respond' | 'adapt', params: Record<string, unknown> = {}): Promise<unknown> {
    const agent = this.getAgent('SID-IMIND-EMOTION') as EmotionAgent;
    return agent.runCycle({ operation, ...params });
  }

  async senseOperation(params: { action: 'DETECT' | 'ANALYZE' | 'RESPOND' | 'ADAPT' | 'MIRROR'; text?: string; context?: string }): Promise<unknown> {
    const bot = this.getBot('Sense')!;
    return bot.execute(params);
  }

  /** Proactive emotional memory consolidation */
  consolidateMemories(): { processed: number; suppressed: number; total: number } {
    let processed = 0, suppressed = 0;
    for (const [, memory] of this.emotionalMemories) {
      if (memory.resolution === 'processed') processed++;
      else if (memory.resolution === 'suppressed') suppressed++;
    }
    return { processed, suppressed, total: this.emotionalMemories.size };
  }

  /** Proactive emotional drift detection */
  detectEmotionalDrift(): { drifting: boolean; dominantEmotion: string; volatilityIndex: number } {
    const recentEmotions = Array.from(this.emotionStates.values()).slice(-20);
    if (recentEmotions.length < 5) return { drifting: false, dominantEmotion: 'neutral', volatilityIndex: 0 };
    const emotionCounts = new Map<string, number>();
    for (const e of recentEmotions) {
      emotionCounts.set(e.primary, (emotionCounts.get(e.primary) ?? 0) + 1);
    }
    const dominantEmotion = Array.from(emotionCounts.entries()).sort((a, b) => b[1] - a[1])[0]?.[0] ?? 'neutral';
    const valenceSpread = recentEmotions.reduce((sum, e) => sum + Math.abs(e.valence), 0) / recentEmotions.length;
    return { drifting: valenceSpread > 0.6, dominantEmotion, volatilityIndex: valenceSpread };
  }

  healthCheck(): { status: 'healthy' | 'degraded' | 'critical'; emotionStates: number; sentimentProfiles: number; emotionalMemories: number; agents: number; bots: number; timestamp: Date } {
    const drift = this.detectEmotionalDrift();
    return {
      status: drift.volatilityIndex > 0.8 ? 'critical' : drift.drifting ? 'degraded' : 'healthy',
      emotionStates: this.emotionStates.size,
      sentimentProfiles: this.sentimentProfiles.size,
      emotionalMemories: this.emotionalMemories.size,
      agents: this.listAgentIds().length,
      bots: this.listBotNames().length,
      timestamp: new Date(),
    };
  }
}
