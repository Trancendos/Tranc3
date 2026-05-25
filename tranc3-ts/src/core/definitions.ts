/**
 * Trancendos Ecosystem — Core Definitions
 *
 * Custom hierarchy (differs from conventional AI terms):
 *   AI    = "AI ML LLM Complex" — Tier 3 Lead AI / domain orchestrator
 *   Agent = "Lower Level AI"    — Tier 4 autonomous microservice
 *   Bot   = "Service Worker"    — Tier 5 stateless nanoservice / function
 *
 * Universal ID taxonomy:
 *   PID-* = Product / Location / Application repo
 *   AID-* = AI entity repo
 *   SID-* = Tier 4 Agent / microservice repo
 *   NID-* = Tier 5 Bot / nanoservice repo
 */

/* ═══════════════════════════════════════════════════════════════════════════
 * Audit
 * ═══════════════════════════════════════════════════════════════════════════ */

export interface AuditEntry {
  id?: string;
  timestamp?: Date;
  actor: string;
  action: string;
  entity: string;
  status?: 'SUCCESS' | 'FAILURE' | 'PENDING';
  meta?: Record<string, any>;
}

export interface IAuditableEntity {
  id: string;
}

/* ═══════════════════════════════════════════════════════════════════════════
 * Bot — Tier 5 Nanoservice
 * ═══════════════════════════════════════════════════════════════════════════ */

export class Bot {
  public readonly id: string;
  public readonly name: string;
  private readonly func: (...args: any[]) => Promise<any>;
  public readonly description: string;
  public callCount: number = 0;
  public lastCalled: Date | null = null;

  constructor(name: string, func: (...args: any[]) => Promise<any>, description: string) {
    this.id = `NID-${name.toUpperCase().replace(/[^A-Z0-9]/g, '-')}`;
    this.name = name;
    this.func = func;
    this.description = description;
  }

  async execute(...args: any[]): Promise<any> {
    this.callCount++;
    this.lastCalled = new Date();
    const result = await this.func(...args);
    return result;
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
 * Agent — Tier 4 Microservice
 * ═══════════════════════════════════════════════════════════════════════════ */

export abstract class Agent {
  public readonly id: string;
  public readonly tools: Map<string, Bot> = new Map();
  public readonly memory: Array<Record<string, any>> = [];
  public state: Record<string, any> = {};
  public episodeCount: number = 0;

  constructor(id: string) {
    this.id = id;
  }

  /** Register a Tier 5 bot as a tool this agent can use */
  registerTool(bot: Bot): void {
    this.tools.set(bot.name, bot);
  }

  /** Observe the environment / incoming data */
  abstract perceive(observation: any): Promise<any>;

  /** Decide on an action given current state + perception */
  abstract decide(observation?: any): Promise<any>;

  /** Execute the decided action */
  abstract act(action: any): Promise<any>;

  /** Standard perceive-decide-act loop */
  async runCycle(observation: any): Promise<any> {
    this.episodeCount++;
    const perceived = await this.perceive(observation);
    const decision = await this.decide(perceived);
    const result = await this.act(decision);
    this.memory.push({ episode: this.episodeCount, perceived, decision, result, ts: new Date() });
    return result;
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
 * AI — Tier 3 Lead AI / Domain Orchestrator
 * ═══════════════════════════════════════════════════════════════════════════ */

export class AI {
  public readonly id: string = '';
  public readonly name: string = '';
  public readonly hub: string = '';
  public readonly pillar: string = '';
  public readonly prime: string = '';
  public readonly tier: number = 3;

  private readonly _agents: Map<string, Agent> = new Map();
  private readonly _bots: Map<string, Bot> = new Map();

  /** Register a Tier 4 agent */
  registerAgent(agent: Agent): void {
    this._agents.set(agent.id, agent);
  }

  /** Register a Tier 5 bot */
  registerBot(bot: Bot): void {
    this._bots.set(bot.name, bot);
  }

  /** Get a registered agent by SID */
  getAgent(agentId: string): Agent | undefined {
    return this._agents.get(agentId);
  }

  /** Get a registered bot by name */
  getBot(name: string): Bot | undefined {
    return this._bots.get(name);
  }

  /** List all registered agent IDs */
  listAgentIds(): string[] {
    return Array.from(this._agents.keys());
  }

  /** List all registered bot names */
  listBotNames(): string[] {
    return Array.from(this._bots.keys());
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
 * Re-exports
 * ═══════════════════════════════════════════════════════════════════════════ */

export { Logger } from './logger';
export { AuditLedger } from './audit';
