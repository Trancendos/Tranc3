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

/* ──────────────────────────────────────────────────────────────────────────
 * Audit
 * ────────────────────────────────────────────────────────────────────────── */

export interface AuditEntry {
  id?: string;
  timestamp?: Date;
  actor: string;
  action: string;
  entity: string;
  status?: 'SUCCESS' | 'FAILURE' | 'PENDING' | 'PARTIAL';
  details?: Record<string, any>;
  agentId?: string;
  botId?: string;
  meta?: Record<string, any>;
}

export interface IAuditableEntity {
  id: string;
}

/* ──────────────────────────────────────────────────────────────────────────
 * Bot — Tier 5 Nanoservice
 * ────────────────────────────────────────────────────────────────────────── */

export class Bot {
  public readonly id: string;
  public readonly name: string;
  private readonly func: (...args: any[]) => any;
  public readonly description: string;
  public callCount: number = 0;
  public lastCalled: Date | null = null;

  constructor(idOrName: string, nameOrFunc: string | ((...args: any[]) => any), funcOrDesc?: ((...args: any[]) => any) | string, description?: string) {
    // Support both 3-arg (name, func, desc) and 4-arg (id, name, func, desc) patterns
    if (typeof nameOrFunc === 'function') {
      // 3-arg: (name, func, description)
      this.id = `NID-${idOrName.toUpperCase().replace(/[^A-Z0-9]/g, '-')}`;
      this.name = idOrName;
      this.func = nameOrFunc as ((...args: any[]) => any);
      this.description = (funcOrDesc as string) ?? '';
    } else {
      // 4-arg: (id, name, func, description)
      this.id = idOrName;
      this.name = nameOrFunc;
      this.func = funcOrDesc as (...args: any[]) => any;
      this.description = description ?? '';
    }
  }

  async execute(...args: any[]): Promise<any> {
    const result = this.func(...args);
    this.callCount++;
    this.lastCalled = new Date();
    return Promise.resolve(result);
  }
}

/* ──────────────────────────────────────────────────────────────────────────
 * Agent — Tier 4 Microservice
 * ────────────────────────────────────────────────────────────────────────── */

export abstract class Agent {
  public readonly id: string;
  public readonly tools: Map<string, Bot> = new Map();
  public readonly memory: Array<Record<string, any>> = [];
  public state: Record<string, any> = {};
  public episodeCount: number = 0;

  constructor(id: string = '', _name?: string, _description?: string) {
    this.id = id;
  }

  /** Register a Tier 5 bot as a tool this agent can use */
  registerTool(botOrName: Bot | string, func?: (...args: any[]) => any): void {
    if (typeof botOrName === 'string' && func) {
      // Legacy pattern: registerTool(name, function)
      const bot = new Bot(botOrName, func, `Tool: ${botOrName}`);
      this.tools.set(botOrName, bot);
    } else if (botOrName instanceof Bot) {
      this.tools.set(botOrName.name, botOrName);
    }
  }

  /** Observe the environment / incoming data */
  abstract perceive(...args: any[]): Promise<any>;

  /** Decide on an action given current state + perception */
  abstract decide(...args: any[]): Promise<any>;

  /** Execute the decided action */
  abstract act(...args: any[]): Promise<any>;

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

/* ──────────────────────────────────────────────────────────────────────────
 * AI — Tier 3 Lead AI / Domain Orchestrator
 * ────────────────────────────────────────────────────────────────────────── */

export class AI {
  public readonly id: string;
  public readonly name: string;
  public readonly hub: string;
  public readonly pillar: string;
  public readonly prime: string | number;
  public readonly tier: number;

  private readonly _agents: Map<string, Agent> = new Map();
  private readonly _bots: Map<string, Bot> = new Map();

  constructor(id: string = '', name: string = '', hub: string = '', pillar: string = '', prime: string | number = '') {
    this.id = id;
    this.name = name;
    this.hub = hub;
    this.pillar = pillar;
    this.prime = prime;
    this.tier = 3;
  }

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

/* ──────────────────────────────────────────────────────────────────────────
 * Re-exports
 * ────────────────────────────────────────────────────────────────────────── */

export { Logger } from './logger';
export { AuditLedger } from './audit';
