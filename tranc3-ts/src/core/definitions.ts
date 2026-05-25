/**
 * Trancendos Ecosystem — Core Definitions
 *
 * Custom hierarchy (differs from conventional AI terms):
 *   Tier 1 — Sovereign  = "System-wide authority" — ultimate orchestrator, HIL-A Tier 0/1 approver
 *   Tier 2 — Prime      = "Executive AI authority" — cross-domain coordinator, HIL-A Tier 2 approver
 *   Tier 3 — AI         = "AI ML LLM Complex" — domain orchestrator, manages Agents & Bots
 *   Tier 4 — Agent      = "Lower Level AI" — autonomous microservice (perceive→decide→act)
 *   Tier 5 — Bot        = "Service Worker" — stateless nanoservice / function
 *
 * Universal ID taxonomy:
 *   PID-* = Product / Location / Application repo
 *   AID-* = AI entity repo
 *   SID-* = Tier 4 Agent / microservice repo
 *   NID-* = Tier 5 Bot / nanoservice repo
 *
 * Lifecycle hooks:
 *   onInit → onStart → (onCycle)* → onStop
 *   onError can fire at any point in the lifecycle
 */

import { EventEmitter } from 'events';

/* ─────────────────────────────────────────────────────────────────────────────
 * Lifecycle Types
 * ───────────────────────────────────────────────────────────────────────────── */

export type LifecycleEvent = 'init' | 'start' | 'stop' | 'error' | 'cycle' | 'toolCall' | 'toolResult';

export interface LifecycleContext {
  entity: string;
  tier: number;
  timestamp: Date;
  details?: Record<string, any>;
}

export type LifecycleListener = (ctx: LifecycleContext) => void | Promise<void>;

/* ─────────────────────────────────────────────────────────────────────────────
 * Typed EventEmitter for lifecycle hooks
 * ───────────────────────────────────────────────────────────────────────────── */

export class LifecycleEmitter extends EventEmitter {
  private readonly _ownerName: string;

  constructor(ownerName: string) {
    super();
    this._ownerName = ownerName;
    // Prevent memory leaks — default max listeners per entity
    this.setMaxListeners(50);
  }

  /** Emit a lifecycle event with standardised context */
  async emitLifecycle(event: LifecycleEvent, details?: Record<string, any>): Promise<void> {
    const ctx: LifecycleContext = {
      entity: this._ownerName,
      tier: -1, // overridden by each tier class
      timestamp: new Date(),
      details,
    };
    this.emit(event, ctx);
    // Also emit a wildcard '*' event for catch-all listeners
    this.emit('*', event, ctx);
  }

  /** Register a listener for a specific lifecycle event */
  onLifecycle(event: LifecycleEvent, listener: LifecycleListener): this {
    this.on(event, listener);
    return this;
  }

  /** Register a one-time listener for a specific lifecycle event */
  onceLifecycle(event: LifecycleEvent, listener: LifecycleListener): this {
    this.once(event, listener);
    return this;
  }

  /** Register a catch-all listener that receives (event, context) */
  onAny(listener: (event: string, ctx: LifecycleContext) => void | Promise<void>): this {
    this.on('*', listener);
    return this;
  }
}

/* ─────────────────────────────────────────────────────────────────────────────
 * Audit
 * ───────────────────────────────────────────────────────────────────────────── */

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

/* ─────────────────────────────────────────────────────────────────────────────
 * Ollama Tool-Calling Integration
 * ───────────────────────────────────────────────────────────────────────────── */

/** Schema for a tool that Ollama can call */
export interface OllamaToolSchema {
  name: string;
  description: string;
  parameters: {
    type: 'object';
    properties: Record<string, {
      type: string;
      description?: string;
      enum?: string[];
    }>;
    required?: string[];
  };
}

/** A single message in the Ollama conversation */
export interface OllamaMessage {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string;
  tool_calls?: OllamaToolCall[];
  tool_call_id?: string;
}

/** A tool call requested by Ollama */
export interface OllamaToolCall {
  function: {
    name: string;
    arguments: Record<string, any>;
  };
}

/** Ollama API response for chat completions */
export interface OllamaChatResponse {
  message: OllamaMessage;
  done: boolean;
  model: string;
  total_duration?: number;
  eval_count?: number;
}

/** Configuration for Ollama integration */
export interface OllamaConfig {
  baseUrl: string;
  model: string;
  systemPrompt?: string;
  temperature?: number;
  maxTokens?: number;
  requestTimeoutMs?: number;
}

const DEFAULT_OLLAMA_CONFIG: OllamaConfig = {
  baseUrl: 'http://localhost:11434',
  model: 'llama3.2',
  temperature: 0.7,
  maxTokens: 4096,
  requestTimeoutMs: 30_000,
};

/** Ollama client — lightweight wrapper over the Ollama REST API */
export class OllamaClient {
  public readonly config: OllamaConfig;

  constructor(config?: Partial<OllamaConfig>) {
    this.config = { ...DEFAULT_OLLAMA_CONFIG, ...config };
  }

  /** Send a chat request with optional tool schemas */
  async chat(
    messages: OllamaMessage[],
    tools?: OllamaToolSchema[],
  ): Promise<OllamaChatResponse> {
    const body: Record<string, any> = {
      model: this.config.model,
      messages,
      stream: false,
      options: {
        temperature: this.config.temperature,
        num_predict: this.config.maxTokens,
      },
    };

    if (tools && tools.length > 0) {
      body.tools = tools;
    }

    const controller = new AbortController();
    const timeout = setTimeout(
      () => controller.abort(),
      this.config.requestTimeoutMs,
    );

    try {
      const response = await fetch(`${this.config.baseUrl}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!response.ok) {
        const text = await response.text();
        throw new Error(`Ollama API error ${response.status}: ${text}`);
      }

      return (await response.json()) as OllamaChatResponse;
    } finally {
      clearTimeout(timeout);
    }
  }

  /** Check if Ollama is reachable */
  async isAvailable(): Promise<boolean> {
    try {
      const response = await fetch(`${this.config.baseUrl}/api/tags`, {
        method: 'GET',
        signal: AbortSignal.timeout(3000),
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  /** List available models */
  async listModels(): Promise<string[]> {
    try {
      const response = await fetch(`${this.config.baseUrl}/api/tags`, {
        signal: AbortSignal.timeout(5000),
      });
      if (!response.ok) return [];
      const data = await response.json() as { models: Array<{ name: string }> };
      return data.models?.map((m) => m.name) ?? [];
    } catch {
      return [];
    }
  }
}

/* ─────────────────────────────────────────────────────────────────────────────
 * Bot — Tier 5 Nanoservice
 * ───────────────────────────────────────────────────────────────────────────── */

export class Bot {
  public readonly id: string;
  public readonly name: string;
  private readonly func: (...args: any[]) => any;
  public readonly description: string;
  public callCount: number = 0;
  public lastCalled: Date | null = null;
  public readonly lifecycle: LifecycleEmitter;
  public readonly createdAt: Date;

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
    this.createdAt = new Date();
    this.lifecycle = new LifecycleEmitter(this.name);
    // Fire init synchronously — construction is part of the lifecycle
    this.lifecycle.emitLifecycle('init', { id: this.id, tier: 5 });
  }

  async execute(...args: any[]): Promise<any> {
    try {
      await this.lifecycle.emitLifecycle('toolCall', { args: args.length });
      const result = this.func(...args);
      const resolved = await Promise.resolve(result);
      this.callCount++;
      this.lastCalled = new Date();
      await this.lifecycle.emitLifecycle('toolResult', {
        success: true,
        callCount: this.callCount,
      });
      return resolved;
    } catch (error) {
      await this.lifecycle.emitLifecycle('error', {
        phase: 'execute',
        error: error instanceof Error ? error.message : String(error),
      });
      throw error;
    }
  }
}

/* ─────────────────────────────────────────────────────────────────────────────
 * Agent — Tier 4 Microservice
 * ───────────────────────────────────────────────────────────────────────────── */

export abstract class Agent {
  public readonly id: string;
  public readonly name: string;
  public readonly description: string;
  public readonly tools: Map<string, Bot> = new Map();
  public readonly memory: Array<Record<string, any>> = [];
  public state: Record<string, any> = {};
  public episodeCount: number = 0;
  public readonly lifecycle: LifecycleEmitter;
  public readonly createdAt: Date;

  /** Ollama client — set via enableOllama() or constructed directly */
  private _ollama: OllamaClient | null = null;
  private _ollamaSystemPrompt: string = '';
  private _ollamaConversationHistory: OllamaMessage[] = [];

  constructor(id: string = '', name: string = '', description: string = '') {
    this.id = id;
    this.name = name || id;
    this.description = description;
    this.createdAt = new Date();
    this.lifecycle = new LifecycleEmitter(this.name || id);
    this.lifecycle.emitLifecycle('init', { id: this.id, tier: 4 });
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

  /** Standard perceive-decide-act loop with lifecycle hooks */
  async runCycle(observation: any): Promise<any> {
    this.episodeCount++;
    try {
      await this.lifecycle.emitLifecycle('cycle', {
        episode: this.episodeCount,
        phase: 'start',
      });

      const perceived = await this.perceive(observation);
      const decision = await this.decide(perceived);
      const result = await this.act(decision);

      this.memory.push({
        episode: this.episodeCount,
        perceived,
        decision,
        result,
        ts: new Date(),
      });

      await this.lifecycle.emitLifecycle('cycle', {
        episode: this.episodeCount,
        phase: 'complete',
      });

      return result;
    } catch (error) {
      await this.lifecycle.emitLifecycle('error', {
        episode: this.episodeCount,
        phase: 'runCycle',
        error: error instanceof Error ? error.message : String(error),
      });
      throw error;
    }
  }

  /* ── Ollama Integration ────────────────────────────────────────────────── */

  /** Enable Ollama-based tool-calling for this agent */
  enableOllama(config?: Partial<OllamaConfig>, systemPrompt?: string): OllamaClient {
    this._ollama = new OllamaClient(config);
    this._ollamaSystemPrompt = systemPrompt ?? `You are ${this.name}, an autonomous agent in the Tranc3 ecosystem. ${this.description}`;
    this._ollamaConversationHistory = [
      { role: 'system', content: this._ollamaSystemPrompt },
    ];
    return this._ollama;
  }

  /** Get the Ollama client (null if not enabled) */
  get ollama(): OllamaClient | null {
    return this._ollama;
  }

  /** Build Ollama tool schemas from registered Bot tools */
  buildOllamaTools(): OllamaToolSchema[] {
    const schemas: OllamaToolSchema[] = [];
    for (const [name, bot] of this.tools) {
      schemas.push({
        name,
        description: bot.description || `Execute the ${name} tool`,
        parameters: {
          type: 'object',
          properties: {
            input: {
              type: 'string',
              description: `Input for ${name}`,
            },
          },
          required: ['input'],
        },
      });
    }
    return schemas;
  }

  /** Run a perceive-decide-act cycle powered by Ollama LLM */
  async ollamaCycle(
    userMessage: string,
    maxToolRounds: number = 5,
  ): Promise<{ response: string; toolCalls: Array<{ tool: string; result: any }> }> {
    if (!this._ollama) {
      throw new Error('Ollama not enabled — call enableOllama() first');
    }

    this.episodeCount++;
    const toolCallLog: Array<{ tool: string; result: any }> = [];

    await this.lifecycle.emitLifecycle('cycle', {
      episode: this.episodeCount,
      phase: 'ollama-start',
    });

    // Add user message to conversation
    this._ollamaConversationHistory.push({
      role: 'user',
      content: userMessage,
    });

    let round = 0;
    let finalResponse = '';

    try {
      while (round < maxToolRounds) {
        round++;
        const tools = this.buildOllamaTools();
        const response = await this._ollama.chat(
          this._ollamaConversationHistory,
          tools.length > 0 ? tools : undefined,
        );

        const assistantMessage = response.message;

        // If the model wants to call tools, execute them
        if (assistantMessage.tool_calls && assistantMessage.tool_calls.length > 0) {
          // Record the assistant's message with tool calls
          this._ollamaConversationHistory.push(assistantMessage);

          for (const toolCall of assistantMessage.tool_calls) {
            const toolName = toolCall.function.name;
            const toolArgs = toolCall.function.arguments;
            const bot = this.tools.get(toolName);

            await this.lifecycle.emitLifecycle('toolCall', {
              tool: toolName,
              args: toolArgs,
              round,
            });

            let toolResult: any;
            if (bot) {
              try {
                toolResult = await bot.execute(toolArgs.input ?? JSON.stringify(toolArgs));
              } catch (err) {
                toolResult = { error: err instanceof Error ? err.message : String(err) };
              }
            } else {
              toolResult = { error: `Unknown tool: ${toolName}` };
            }

            toolCallLog.push({ tool: toolName, result: toolResult });

            await this.lifecycle.emitLifecycle('toolResult', {
              tool: toolName,
              success: !toolResult?.error,
              round,
            });

            // Add tool result to conversation
            this._ollamaConversationHistory.push({
              role: 'tool',
              content: JSON.stringify(toolResult),
              tool_call_id: toolName,
            });
          }
          // Continue the loop — let the model process tool results
        } else {
          // No tool calls — the model is done, return its response
          finalResponse = assistantMessage.content || '';
          this._ollamaConversationHistory.push(assistantMessage);
          break;
        }
      }

      // If we exhausted rounds without a final response
      if (!finalResponse && round >= maxToolRounds) {
        finalResponse = 'Maximum tool-calling rounds reached. Processing may be incomplete.';
      }

      // Store in memory
      this.memory.push({
        episode: this.episodeCount,
        type: 'ollama',
        userMessage,
        toolCalls: toolCallLog,
        response: finalResponse,
        rounds: round,
        ts: new Date(),
      });

      await this.lifecycle.emitLifecycle('cycle', {
        episode: this.episodeCount,
        phase: 'ollama-complete',
        rounds: round,
      });

      return { response: finalResponse, toolCalls: toolCallLog };
    } catch (error) {
      await this.lifecycle.emitLifecycle('error', {
        episode: this.episodeCount,
        phase: 'ollamaCycle',
        round,
        error: error instanceof Error ? error.message : String(error),
      });
      throw error;
    }
  }

  /** Clear Ollama conversation history (keep system prompt) */
  clearOllamaHistory(): void {
    this._ollamaConversationHistory = [
      { role: 'system', content: this._ollamaSystemPrompt },
    ];
  }

  /** Get current Ollama conversation history length (excluding system) */
  get ollamaHistoryLength(): number {
    return Math.max(0, this._ollamaConversationHistory.length - 1);
  }
}

/* ─────────────────────────────────────────────────────────────────────────────
 * AI — Tier 3 Lead AI / Domain Orchestrator
 * ───────────────────────────────────────────────────────────────────────────── */

export class AI {
  public readonly id: string;
  public readonly name: string;
  public readonly hub: string;
  public readonly pillar: string;
  public readonly prime: string | number;
  public readonly tier: number;
  public readonly lifecycle: LifecycleEmitter;
  public readonly createdAt: Date;

  private readonly _agents: Map<string, Agent> = new Map();
  private readonly _bots: Map<string, Bot> = new Map();
  private _running: boolean = false;

  constructor(id: string = '', name: string = '', hub: string = '', pillar: string = '', prime: string | number = '') {
    this.id = id;
    this.name = name;
    this.hub = hub;
    this.pillar = pillar;
    this.prime = prime;
    this.tier = 3;
    this.createdAt = new Date();
    this.lifecycle = new LifecycleEmitter(name || id);
    this.lifecycle.emitLifecycle('init', { id: this.id, tier: 3, hub, pillar });
  }

  /** Start this AI and all registered agents/bots */
  async start(): Promise<void> {
    if (this._running) return;
    this._running = true;
    await this.lifecycle.emitLifecycle('start', {
      agents: this._agents.size,
      bots: this._bots.size,
    });
  }

  /** Stop this AI gracefully */
  async stop(): Promise<void> {
    if (!this._running) return;
    this._running = false;
    await this.lifecycle.emitLifecycle('stop', {
      agents: this._agents.size,
      bots: this._bots.size,
    });
  }

  /** Whether this AI is currently running */
  get running(): boolean {
    return this._running;
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

  /** Run a single cycle across all agents */
  async runAllAgentCycles(observation: any): Promise<Map<string, any>> {
    const results = new Map<string, any>();
    for (const [id, agent] of this._agents) {
      try {
        const result = await agent.runCycle(observation);
        results.set(id, result);
      } catch (error) {
        await this.lifecycle.emitLifecycle('error', {
          agentId: id,
          phase: 'runAllAgentCycles',
          error: error instanceof Error ? error.message : String(error),
        });
        results.set(id, { error: String(error) });
      }
    }
    return results;
  }
}

/* ─────────────────────────────────────────────────────────────────────────────
 * Prime — Tier 2 Executive AI Authority
 * ───────────────────────────────────────────────────────────────────────────── */

export class Prime {
  public readonly id: string;
  public readonly name: string;
  public readonly pillar: string;
  public readonly tier: number;
  public readonly lifecycle: LifecycleEmitter;
  public readonly createdAt: Date;

  /** AIs that this Prime coordinates across its domain */
  private readonly _ais: Map<string, AI> = new Map();
  private _running: boolean = false;

  /** HIL-A approval authority — Tier 2 can approve Tier 3+ actions */
  public readonly canApproveTiers: number[] = [3, 4, 5];

  constructor(id: string = '', name: string = '', pillar: string = '') {
    this.id = id;
    this.name = name;
    this.pillar = pillar;
    this.tier = 2;
    this.createdAt = new Date();
    this.lifecycle = new LifecycleEmitter(name || id);
    this.lifecycle.emitLifecycle('init', { id: this.id, tier: 2, pillar });
  }

  /** Start this Prime and all managed AIs */
  async start(): Promise<void> {
    if (this._running) return;
    this._running = true;
    await this.lifecycle.emitLifecycle('start', {
      managedAIs: this._ais.size,
    });
    // Start all managed AIs
    for (const [, ai] of this._ais) {
      try {
        await ai.start();
      } catch (error) {
        await this.lifecycle.emitLifecycle('error', {
          aiId: ai.id,
          phase: 'start',
          error: error instanceof Error ? error.message : String(error),
        });
      }
    }
  }

  /** Stop this Prime and all managed AIs */
  async stop(): Promise<void> {
    if (!this._running) return;
    this._running = false;
    // Stop all managed AIs
    for (const [, ai] of this._ais) {
      try {
        await ai.stop();
      } catch (error) {
        await this.lifecycle.emitLifecycle('error', {
          aiId: ai.id,
          phase: 'stop',
          error: error instanceof Error ? error.message : String(error),
        });
      }
    }
    await this.lifecycle.emitLifecycle('stop', {
      managedAIs: this._ais.size,
    });
  }

  /** Whether this Prime is currently running */
  get running(): boolean {
    return this._running;
  }

  /** Register a Tier 3 AI under this Prime's domain */
  registerAI(ai: AI): void {
    this._ais.set(ai.id, ai);
  }

  /** Get a managed AI by AID */
  getAI(aiId: string): AI | undefined {
    return this._ais.get(aiId);
  }

  /** List all managed AI IDs */
  listAIIds(): string[] {
    return Array.from(this._ais.keys());
  }

  /** List all agents across all managed AIs */
  listAllAgentIds(): string[] {
    const agents: string[] = [];
    for (const [, ai] of this._ais) {
      agents.push(...ai.listAgentIds());
    }
    return agents;
  }

  /** Run a coordinated cycle across all managed AIs */
  async runCoordinatedCycle(observation: any): Promise<Map<string, Map<string, any>>> {
    const results = new Map<string, Map<string, any>>();
    for (const [aiId, ai] of this._ais) {
      try {
        const aiResults = await ai.runAllAgentCycles(observation);
        results.set(aiId, aiResults);
      } catch (error) {
        await this.lifecycle.emitLifecycle('error', {
          aiId,
          phase: 'runCoordinatedCycle',
          error: error instanceof Error ? error.message : String(error),
        });
      }
    }
    await this.lifecycle.emitLifecycle('cycle', {
      aisProcessed: results.size,
    });
    return results;
  }

  /** HIL-A: Approve an action on behalf of this Prime (Tier 2 authority) */
  approveAction(actionId: string, reason: string = 'Approved by Prime'): {
    actionId: string;
    approvedBy: string;
    tier: number;
    reason: string;
    timestamp: Date;
  } {
    return {
      actionId,
      approvedBy: this.id,
      tier: this.tier,
      reason,
      timestamp: new Date(),
    };
  }

  /** HIL-A: Reject an action on behalf of this Prime */
  rejectAction(actionId: string, reason: string): {
    actionId: string;
    rejectedBy: string;
    tier: number;
    reason: string;
    timestamp: Date;
  } {
    return {
      actionId,
      rejectedBy: this.id,
      tier: this.tier,
      reason,
      timestamp: new Date(),
    };
  }

  /** Get health summary of all managed AIs */
  healthCheck(): {
    prime: string;
    tier: number;
    running: boolean;
    managedAIs: number;
    totalAgents: number;
    totalBots: number;
    aiStatuses: Array<{ id: string; running: boolean; agents: number; bots: number }>;
  } {
    const aiStatuses = Array.from(this._ais.values()).map((ai) => ({
      id: ai.id,
      running: ai.running,
      agents: ai.listAgentIds().length,
      bots: ai.listBotNames().length,
    }));

    return {
      prime: this.name,
      tier: this.tier,
      running: this._running,
      managedAIs: this._ais.size,
      totalAgents: aiStatuses.reduce((sum, s) => sum + s.agents, 0),
      totalBots: aiStatuses.reduce((sum, s) => sum + s.bots, 0),
      aiStatuses,
    };
  }
}

/* ─────────────────────────────────────────────────────────────────────────────
 * Sovereign — Tier 1 System-Wide Authority
 * ───────────────────────────────────────────────────────────────────────────── */

export class Sovereign {
  public readonly id: string;
  public readonly name: string;
  public readonly tier: number;
  public readonly lifecycle: LifecycleEmitter;
  public readonly createdAt: Date;

  /** Primes that this Sovereign oversees */
  private readonly _primes: Map<string, Prime> = new Map();

  /** Direct AI references for emergency override */
  private readonly _ais: Map<string, AI> = new Map();

  private _running: boolean = false;

  /** HIL-A: Sovereign is the ultimate authority — can approve Tier 0+ actions */
  public readonly canApproveTiers: number[] = [0, 1, 2, 3, 4, 5];

  /** Emergency stop flag — when true, all cycles are halted */
  private _emergencyStop: boolean = false;

  constructor(id: string = 'SOVEREIGN-001', name: string = 'The Sovereign') {
    this.id = id;
    this.name = name;
    this.tier = 1;
    this.createdAt = new Date();
    this.lifecycle = new LifecycleEmitter(name);
    this.lifecycle.emitLifecycle('init', { id: this.id, tier: 1 });
  }

  /** Start the Sovereign and all managed Primes */
  async start(): Promise<void> {
    if (this._running) return;
    this._running = true;
    this._emergencyStop = false;
    await this.lifecycle.emitLifecycle('start', {
      managedPrimes: this._primes.size,
    });
    for (const [, prime] of this._primes) {
      try {
        await prime.start();
      } catch (error) {
        await this.lifecycle.emitLifecycle('error', {
          primeId: prime.id,
          phase: 'start',
          error: error instanceof Error ? error.message : String(error),
        });
      }
    }
  }

  /** Stop the Sovereign and all managed Primes */
  async stop(): Promise<void> {
    if (!this._running) return;
    this._running = false;
    for (const [, prime] of this._primes) {
      try {
        await prime.stop();
      } catch (error) {
        await this.lifecycle.emitLifecycle('error', {
          primeId: prime.id,
          phase: 'stop',
          error: error instanceof Error ? error.message : String(error),
        });
      }
    }
    await this.lifecycle.emitLifecycle('stop', {
      managedPrimes: this._primes.size,
    });
  }

  /** Whether the Sovereign is currently running */
  get running(): boolean {
    return this._running;
  }

  /** Whether emergency stop is active */
  get emergencyStopped(): boolean {
    return this._emergencyStop;
  }

  /** Register a Tier 2 Prime under this Sovereign */
  registerPrime(prime: Prime): void {
    this._primes.set(prime.id, prime);
  }

  /** Register a Tier 3 AI for direct emergency access */
  registerAI(ai: AI): void {
    this._ais.set(ai.id, ai);
  }

  /** Get a managed Prime by ID */
  getPrime(primeId: string): Prime | undefined {
    return this._primes.get(primeId);
  }

  /** Get a directly registered AI by AID */
  getAI(aiId: string): AI | undefined {
    return this._ais.get(aiId);
  }

  /** List all managed Prime IDs */
  listPrimeIds(): string[] {
    return Array.from(this._primes.keys());
  }

  /** List all AIs across all managed Primes */
  listAllAIIds(): string[] {
    const ais: string[] = [];
    for (const [, prime] of this._primes) {
      ais.push(...prime.listAIIds());
    }
    // Include directly registered AIs
    for (const [aiId] of this._ais) {
      if (!ais.includes(aiId)) ais.push(aiId);
    }
    return ais;
  }

  /** HIL-A: Sovereign approval — the highest authority in the system */
  approveAction(actionId: string, reason: string = 'Sovereign decree'): {
    actionId: string;
    approvedBy: string;
    tier: number;
    reason: string;
    timestamp: Date;
  } {
    return {
      actionId,
      approvedBy: this.id,
      tier: this.tier,
      reason,
      timestamp: new Date(),
    };
  }

  /** HIL-A: Sovereign rejection — cannot be overridden */
  rejectAction(actionId: string, reason: string): {
    actionId: string;
    rejectedBy: string;
    tier: number;
    reason: string;
    timestamp: Date;
    final: true;
  } {
    return {
      actionId,
      rejectedBy: this.id,
      tier: this.tier,
      reason,
      timestamp: new Date(),
      final: true,
    };
  }

  /** EMERGENCY STOP — halts all cycles across the entire ecosystem */
  async emergencyStop(reason: string = 'Manual emergency stop'): Promise<void> {
    this._emergencyStop = true;
    await this.lifecycle.emitLifecycle('error', {
      type: 'emergency_stop',
      reason,
    });
    // Stop all Primes
    for (const [, prime] of this._primes) {
      try {
        await prime.stop();
      } catch { /* best-effort stop */ }
    }
    // Stop all directly registered AIs
    for (const [, ai] of this._ais) {
      try {
        await ai.stop();
      } catch { /* best-effort stop */ }
    }
  }

  /** Resume from emergency stop */
  async resumeFromEmergency(): Promise<void> {
    this._emergencyStop = false;
    await this.start();
  }

  /** Run a full ecosystem cycle through all Primes */
  async runEcosystemCycle(observation: any): Promise<Map<string, Map<string, Map<string, any>>>> {
    if (this._emergencyStop) {
      throw new Error('Cannot run ecosystem cycle — emergency stop is active');
    }

    const results = new Map<string, Map<string, Map<string, any>>>();
    for (const [primeId, prime] of this._primes) {
      try {
        const primeResults = await prime.runCoordinatedCycle(observation);
        results.set(primeId, primeResults);
      } catch (error) {
        await this.lifecycle.emitLifecycle('error', {
          primeId,
          phase: 'runEcosystemCycle',
          error: error instanceof Error ? error.message : String(error),
        });
      }
    }
    await this.lifecycle.emitLifecycle('cycle', {
      primesProcessed: results.size,
    });
    return results;
  }

  /** Full ecosystem health check */
  healthCheck(): {
    sovereign: string;
    tier: number;
    running: boolean;
    emergencyStopped: boolean;
    managedPrimes: number;
    totalAIs: number;
    totalAgents: number;
    totalBots: number;
    primeHealths: ReturnType<Prime['healthCheck']>[];
  } {
    const primeHealths = Array.from(this._primes.values()).map((p) => p.healthCheck());
    return {
      sovereign: this.name,
      tier: this.tier,
      running: this._running,
      emergencyStopped: this._emergencyStop,
      managedPrimes: this._primes.size,
      totalAIs: primeHealths.reduce((sum, h) => sum + h.managedAIs, 0),
      totalAgents: primeHealths.reduce((sum, h) => sum + h.totalAgents, 0),
      totalBots: primeHealths.reduce((sum, h) => sum + h.totalBots, 0),
      primeHealths,
    };
  }
}

/* ─────────────────────────────────────────────────────────────────────────────
 * Re-exports
 * ───────────────────────────────────────────────────────────────────────────── */

export { Logger } from './logger';
export { AuditLedger } from './audit';
