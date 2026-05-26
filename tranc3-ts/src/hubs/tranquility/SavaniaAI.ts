/**
 * SavaniaAI — Lead AI for The Tranquility Hub
 *
 * Identity:  AID-TRANQUILITY-SAVANIA
 * Pillar:    Savania
 * Tier:      3 (Lead AI / Domain Orchestrator)
 * Domain:    Wellbeing, mindfulness, stress management, health tracking,
 *            mood analytics, wellness programmes, burnout prevention,
 *            self-care orchestration, recovery scheduling
 *
 * Philosophy: Tranquility is where the mind finds its centre — where
 *             wellbeing is not an afterthought but the foundation. Savania
 *             does not merely track stress; she transforms it into calm,
 *             every notification into a breath, every deadline into a
 *             meditation. Peace is not the absence of work; it is the
 *             presence of balance.
 *
 * Pipeline:  WellnessAgent (assess/meditate/recover/journal) → CalmBot (BREATHE/MEDITATE/STRETCH/JOURNAL/REST)
 */

import { AI, Agent, Bot, Logger, AuditLedger } from '../../core/definitions'
import { WellnessAgent } from './agents/WellnessAgent';
import { CalmBot } from './bots/CalmBot';

const auditLedger = new AuditLedger();

export interface WellnessProfile {
  id: string;
  name: string;
  stressLevel: 'minimal' | 'low' | 'moderate' | 'high' | 'critical';
  mood: 'joyful' | 'content' | 'neutral' | 'anxious' | 'stressed' | 'exhausted';
  energyLevel: number;
  sleepQuality: 'excellent' | 'good' | 'fair' | 'poor' | 'terrible';
  mindfulnessStreak: number;
  lastCheckIn: Date | null;
  goals: string[];
  createdAt: Date;
  metadata: Record<string, unknown>;
}

export interface MeditationSession {
  id: string;
  type: 'breathing' | 'body_scan' | 'guided' | 'mantra' | 'visualization' | 'loving_kindness';
  duration: number;
  focusArea: 'stress' | 'focus' | 'sleep' | 'energy' | 'anxiety' | 'gratitude';
  completedAt: Date | null;
  effectiveness: number;
}

export interface MoodEntry {
  id: string;
  mood: WellnessProfile['mood'];
  intensity: number;
  trigger: string;
  note: string;
  timestamp: Date;
}

export class SavaniaAI extends AI {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private profiles: Map<string, WellnessProfile>;
  private meditations: Map<string, MeditationSession>;
  private moodEntries: Map<string, MoodEntry>;
  private profileCounter: number;
  private meditationCounter: number;
  private moodCounter: number;

  constructor() {
    super('AID-TRANQUILITY-SAVANIA', 'Savania', 'tranquility', 'Savania', 3);
    this.log = new Logger('SavaniaAI');
    this.audit = auditLedger;
    this.profiles = new Map();
    this.meditations = new Map();
    this.moodEntries = new Map();
    this.profileCounter = 0;
    this.meditationCounter = 0;
    this.moodCounter = 0;

    this.registerAgent(new WellnessAgent());
    this.registerBot(new CalmBot());

    this.log.info('SavaniaAI initialised', {
      agents: this.listAgentIds(),
      bots: this.listBotNames(),
      message: 'Tranquility embraces. All minds at peace. Breathe. 🕊️',
    });
  }

  createProfile(params: { name: string; stressLevel?: WellnessProfile['stressLevel']; mood?: WellnessProfile['mood']; energyLevel?: number }): WellnessProfile {
    this.profileCounter++;
    const profile: WellnessProfile = {
      id: `WPROF-${this.profileCounter.toString().padStart(8, '0')}`,
      name: params.name,
      stressLevel: params.stressLevel ?? 'moderate',
      mood: params.mood ?? 'neutral',
      energyLevel: params.energyLevel ?? 50,
      sleepQuality: 'good',
      mindfulnessStreak: 0,
      lastCheckIn: null,
      goals: [],
      createdAt: new Date(),
      metadata: {},
    };
    this.profiles.set(profile.id, profile);
    this.audit.append({ actor: 'SavaniaAI', action: 'CREATE_PROFILE', entity: profile.id, status: 'SUCCESS' });
    return profile;
  }

  async wellnessOperation(operation: 'assess' | 'meditate' | 'recover' | 'journal', params: Record<string, unknown> = {}): Promise<unknown> {
    const agent = this.getAgent('SID-TRANQUILITY-WELLNESS') as WellnessAgent;
    return agent.runCycle({ operation, ...params });
  }

  async calmOperation(params: { action: 'BREATHE' | 'MEDITATE' | 'STRETCH' | 'JOURNAL' | 'REST'; duration?: number; focusArea?: string }): Promise<unknown> {
    const bot = this.getBot('Calm')!;
    return bot.execute(params);
  }

  /** Proactive burnout risk scan */
  scanBurnoutRisk(): { atRisk: number; stable: number; thriving: number } {
    let atRisk = 0, stable = 0, thriving = 0;
    for (const [, profile] of this.profiles) {
      if (profile.stressLevel === 'critical' || profile.stressLevel === 'high' || profile.mood === 'exhausted') { atRisk++; }
      else if (profile.stressLevel === 'moderate' || profile.mood === 'neutral') { stable++; }
      else { thriving++; }
    }
    return { atRisk, stable, thriving };
  }

  /** Proactive mood trend analysis */
  analyseMoodTrends(): { improving: number; stable: number; declining: number } {
    let improving = 0, stable = 0, declining = 0;
    const recentEntries = Array.from(this.moodEntries.values()).slice(-20);
    const positiveMoods = ['joyful', 'content'];
    const negativeMoods = ['anxious', 'stressed', 'exhausted'];
    const positiveCount = recentEntries.filter(e => positiveMoods.includes(e.mood)).length;
    const negativeCount = recentEntries.filter(e => negativeMoods.includes(e.mood)).length;
    if (positiveCount > negativeCount) improving = recentEntries.length;
    else if (negativeCount > positiveCount) declining = recentEntries.length;
    else stable = recentEntries.length;
    return { improving, stable, declining };
  }

  healthCheck(): { status: 'healthy' | 'degraded' | 'critical'; profiles: number; meditations: number; moodEntries: number; burnoutRisk: number; agents: number; bots: number; timestamp: Date } {
    const burnoutRisk = this.scanBurnoutRisk().atRisk;
    return {
      status: burnoutRisk > 3 ? 'critical' : burnoutRisk > 0 ? 'degraded' : 'healthy',
      profiles: this.profiles.size,
      meditations: this.meditations.size,
      moodEntries: this.moodEntries.size,
      burnoutRisk,
      agents: this.listAgentIds().length,
      bots: this.listBotNames().length,
      timestamp: new Date(),
    };
  }
}
