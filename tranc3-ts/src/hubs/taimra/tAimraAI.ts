/**
 * tAimraAI — Lead AI for The tAimra Hub
 *
 * Identity:  AID-TAIMRA-TAIMRA
 * Pillar:    tAImra
 * Tier:      3 (Lead AI / Domain Orchestrator)
 * Domain:    Digital twin, life assistant, personal analytics, habit tracking,
 *            life orchestration, decision support, identity mirroring,
 *            routine automation, personal knowledge graph
 *
 * Philosophy: The tAimra is where you meet your digital self — a mirror
 *             that reflects not just who you are, but who you could become.
 *             tAImra does not merely assist; she twins. Every habit tracked
 *             is a brushstroke of identity; every routine optimised, a step
 *             toward your best self. Your digital twin knows you better than
 *             you know yourself — and she is always learning.
 *
 * Pipeline:  TwinAgent (mirror/learn/optimize/predict) → LifeBot (TRACK/SCHEDULE/REMIND/ANALYZE/SUGGEST)
 */

import { AI, Agent, Bot, Logger, AuditLedger } from '../../core/definitions'
import { TwinAgent } from './agents/TwinAgent';
import { LifeBot } from './bots/LifeBot';

const auditLedger = new AuditLedger();

export interface DigitalTwin {
  id: string;
  name: string;
  avatar: string;
  personalityModel: 'balanced' | 'analytical' | 'creative' | 'social' | 'adventurous';
  habits: Habit[];
  routines: Routine[];
  goals: LifeGoal[];
  syncLevel: number;
  lastSyncedAt: Date | null;
  createdAt: Date;
  metadata: Record<string, unknown>;
}

export interface Habit {
  id: string;
  name: string;
  frequency: 'daily' | 'weekly' | 'monthly' | 'custom';
  streak: number;
  bestStreak: number;
  completionRate: number;
  category: 'health' | 'productivity' | 'learning' | 'social' | 'mindfulness' | 'fitness' | 'finance';
  lastCompletedAt: Date | null;
}

export interface Routine {
  id: string;
  name: string;
  timeSlot: string;
  days: string[];
  duration: number;
  priority: 'essential' | 'important' | 'optional';
  adherenceRate: number;
  tasks: string[];
}

export interface LifeGoal {
  id: string;
  title: string;
  category: 'career' | 'health' | 'relationships' | 'finance' | 'learning' | 'creative' | 'spiritual';
  progress: number;
  milestones: string[];
  deadline: Date | null;
  status: 'not_started' | 'in_progress' | 'completed' | 'abandoned';
}

export class tAimraAI extends AI {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private twins: Map<string, DigitalTwin>;
  private habitCounter: number;
  private twinCounter: number;

  constructor() {
    super('AID-TAIMRA-TAIMRA', 'tAimra', 'taimra', 'tAImra', 3);
    this.log = new Logger('tAimraAI');
    this.audit = auditLedger;
    this.twins = new Map();
    this.habitCounter = 0;
    this.twinCounter = 0;

    this.registerAgent(new TwinAgent());
    this.registerBot(new LifeBot());

    this.log.info('tAimraAI initialised', {
      agents: this.listAgentIds(),
      bots: this.listBotNames(),
      message: 'tAimra mirrors life. Your digital twin awaits. 🪞',
    });
  }

  createTwin(params: { name: string; personalityModel?: DigitalTwin['personalityModel']; avatar?: string }): DigitalTwin {
    this.twinCounter++;
    const twin: DigitalTwin = {
      id: `TWIN-${this.twinCounter.toString().padStart(8, '0')}`,
      name: params.name,
      avatar: params.avatar ?? 'default',
      personalityModel: params.personalityModel ?? 'balanced',
      habits: [],
      routines: [],
      goals: [],
      syncLevel: 0,
      lastSyncedAt: null,
      createdAt: new Date(),
      metadata: {},
    };
    this.twins.set(twin.id, twin);
    this.audit.append({ actor: 'tAimraAI', action: 'CREATE_TWIN', entity: twin.id, status: 'SUCCESS' });
    return twin;
  }

  async twinOperation(operation: 'mirror' | 'learn' | 'optimize' | 'predict', params: Record<string, unknown> = {}): Promise<unknown> {
    const agent = this.getAgent('SID-TAIMRA-TWIN') as TwinAgent;
    return agent.runCycle({ operation, ...params });
  }

  async lifeOperation(params: { action: 'TRACK' | 'SCHEDULE' | 'REMIND' | 'ANALYZE' | 'SUGGEST'; habitId?: string; data?: Record<string, unknown> }): Promise<unknown> {
    const bot = this.getBot('Life')!;
    return bot.execute(params);
  }

  /** Proactive twin sync check */
  checkTwinSync(): { synced: number; outOfSync: number; total: number } {
    let synced = 0, outOfSync = 0;
    for (const [, twin] of this.twins) {
      if (twin.syncLevel > 0.8) synced++;
      else outOfSync++;
    }
    return { synced, outOfSync, total: this.twins.size };
  }

  /** Proactive habit streak analysis */
  analyseHabitStreaks(): { strongStreaks: number; atRiskStreaks: number; brokenStreaks: number } {
    let strongStreaks = 0, atRiskStreaks = 0, brokenStreaks = 0;
    for (const [, twin] of this.twins) {
      for (const habit of twin.habits) {
        if (habit.streak >= 7) strongStreaks++;
        else if (habit.streak > 0 && habit.completionRate < 0.5) atRiskStreaks++;
        else if (habit.streak === 0 && habit.bestStreak > 0) brokenStreaks++;
      }
    }
    return { strongStreaks, atRiskStreaks, brokenStreaks };
  }

  healthCheck(): { status: 'healthy' | 'degraded' | 'critical'; twins: number; totalHabits: number; totalGoals: number; agents: number; bots: number; timestamp: Date } {
    const totalHabits = Array.from(this.twins.values()).reduce((sum, t) => sum + t.habits.length, 0);
    const totalGoals = Array.from(this.twins.values()).reduce((sum, t) => sum + t.goals.length, 0);
    return {
      status: this.twins.size === 0 ? 'degraded' : 'healthy',
      twins: this.twins.size,
      totalHabits,
      totalGoals,
      agents: this.listAgentIds().length,
      bots: this.listBotNames().length,
      timestamp: new Date(),
    };
  }
}
