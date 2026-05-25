/**
 * TheChaosPartyAI — Lead AI for The Chaos Party Hub
 *
 * Identity:  AID-CHAOSPARTY
 * Pillar:    MarchHare (with Dormouse)
 * Tier:      3 (Lead AI / Domain Orchestrator)
 * Domain:    Controlled chaos, randomization, entropy injection,
 *            stress testing, fuzzing, creative disruption,
 *            unpredictability as a design principle
 *
 * Philosophy: "In chaos, there is fertility." — Lao Tzu
 *             The Chaos Party ensures systems are resilient by
 *             deliberately introducing controlled disorder.
 *
 * Pipeline:  Teapot (brew chaos) → PocketWatch (time bombs)
 *            → SugarCube (sweet perturbations) → JamTart (chaos results)
 *            MarchHare orchestrates chaos scenarios,
 *            Dormouse monitors and calms the chaos
 */

import { AI, Agent, Bot, Logger, AuditLedger } from '../../core/definitions'
import { MarchHareAgent } from './agents/MarchHareAgent';
import { DormouseAgent } from './agents/DormouseAgent';
import { TeapotBot } from './bots/TeapotBot';
import { PocketWatchBot } from './bots/PocketWatchBot';
import { SugarCubeBot } from './bots/SugarCubeBot';
import { JamTartBot } from './bots/JamTartBot';

const auditLedger = new AuditLedger();

// ─────────────────────────────────────────────────────────────────────────────
// Domain Interfaces
// ─────────────────────────────────────────────────────────────────────────────

export interface ChaosScenario {
  id: string;
  name: string;
  type: 'fuzz' | 'stress' | 'fault-injection' | 'randomisation' | 'entropy-burst' | 'circuit-break';
  intensity: 'mild' | 'medium' | 'hot' | 'unleashed';
  target: string;
  parameters: Record<string, unknown>;
  duration: number;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'calmed';
  createdAt: number;
  startedAt?: number;
  completedAt?: number;
}

export interface ChaosEvent {
  id: string;
  scenarioId: string;
  timestamp: number;
  type: string;
  payload: Record<string, unknown>;
  effect: 'disruptive' | 'subtle' | 'catalytic' | 'nullifying';
  target: string;
  result: 'success' | 'partial' | 'failed' | 'unexpected';
}

export interface EntropyMetrics {
  totalScenarios: number;
  activeScenarios: number;
  totalEvents: number;
  disruptions: number;
  calmedEvents: number;
  chaosIndex: number;        // 0..100 — current chaos level
  resilienceScore: number;   // 0..100 — how well the system handled chaos
  entropyGenerated: number;  // bits of entropy
  lastChaosAt: number;
}

export interface TeaRecipe {
  name: string;
  ingredients: Array<{
    name: string;
    amount: number;
    unit: string;
    chaosContribution: number;
  }>;
  brewTime: number;
  temperature: number;
  effect: string;
  sideEffects: string[];
}

export interface TimeBomb {
  id: string;
  triggerAt: number;
  payload: Record<string, unknown>;
  armed: boolean;
  detonated: boolean;
  defused: boolean;
  type: 'delayed' | 'recurring' | 'conditional' | 'random';
}

// ─────────────────────────────────────────────────────────────────────────────
// TheChaosPartyAI Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class TheChaosPartyAI extends AI {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private scenarios: Map<string, ChaosScenario>;
  private events: Map<string, ChaosEvent>;
  private timeBombs: Map<string, TimeBomb>;
  private teaRecipes: Map<string, TeaRecipe>;
  private chaosIndex: number;
  private resilienceScore: number;

  constructor() {
    super(
      'AID-CHAOSPARTY',
      'TheChaosParty',
      'chaosparty',
      'MarchHare',
      3
    );

    this.log = new Logger('TheChaosPartyAI');
    this.audit = auditLedger;
    this.scenarios = new Map();
    this.events = new Map();
    this.timeBombs = new Map();
    this.teaRecipes = new Map();
    this.chaosIndex = 0;
    this.resilienceScore = 100;

    // Register Agents
    this.registerAgent(new MarchHareAgent());
    this.registerAgent(new DormouseAgent());

    // Register Bots
    this.registerBot(new TeapotBot());
    this.registerBot(new PocketWatchBot());
    this.registerBot(new SugarCubeBot());
    this.registerBot(new JamTartBot());

    this.log.info('TheChaosPartyAI initialised', {
      agents: this.listAgentIds(),
      bots: this.listBotNames(),
      message: 'We\'re all mad here. 🐇',
    });
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Chaos Scenario Management
  // ───────────────────────────────────────────────────────────────────────────

  /**
   * Create a new chaos scenario.
   */
  createScenario(
    name: string,
    type: ChaosScenario['type'],
    intensity: ChaosScenario['intensity'],
    target: string,
    parameters: Record<string, unknown>,
    duration: number
  ): ChaosScenario {
    const id = `CHAOS-${this.scenarios.size + 1}`;
    const scenario: ChaosScenario = {
      id,
      name,
      type,
      intensity,
      target,
      parameters,
      duration,
      status: 'pending',
      createdAt: Date.now(),
    };

    this.scenarios.set(id, scenario);
    this.log.info('Chaos scenario created', { id, name, type, intensity });
    return scenario;
  }

  /**
   * Get a chaos scenario.
   */
  getScenario(id: string): ChaosScenario | undefined {
    return this.scenarios.get(id);
  }

  /**
   * Record a chaos event.
   */
  recordEvent(event: Omit<ChaosEvent, 'id'>): ChaosEvent {
    const id = `EVT-${this.events.size + 1}`;
    const chaosEvent: ChaosEvent = { ...event, id };
    this.events.set(id, chaosEvent);

    // Update chaos index
    this.updateChaosIndex();

    this.log.debug('Chaos event recorded', { id, type: event.type, result: event.result });
    return chaosEvent;
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Bot Delegations
  // ───────────────────────────────────────────────────────────────────────────

  /**
   * Brew chaos via TeapotBot.
   */
  async brewChaos(recipe: string, intensity?: string): Promise<unknown> {
    const teapot = this.getBot('Teapot')!;
    const result = await teapot.execute({
      operation: 'BREW',
      recipe,
      intensity: intensity ?? 'medium',
      servings: 1,
      sugarLevel: 50,
    });
    return result;
  }

  /**
   * Set a time bomb via PocketWatchBot.
   */
  async setTimeBomb(delay: number, payload: Record<string, unknown>, type?: string): Promise<unknown> {
    const pocketWatch = this.getBot('PocketWatch')!;
    const result = await pocketWatch.execute({
      operation: 'ARM',
      delay,
      payload,
      type: type ?? 'delayed',
      recurring: false,
    });
    return result;
  }

  /**
   * Add perturbation via SugarCubeBot.
   */
  async sweeten(target: string, perturbation: string, amount: number): Promise<unknown> {
    const sugarCube = this.getBot('SugarCube')!;
    const result = await sugarCube.execute({
      operation: 'SWEETEN',
      target,
      perturbation,
      amount,
      dissolveTime: 1000,
    });
    return result;
  }

  /**
   * Check chaos results via JamTartBot.
   */
  async tasteResults(scenarioId: string): Promise<unknown> {
    const jamTart = this.getBot('JamTart')!;
    const result = await jamTart.execute({
      operation: 'TASTE',
      scenarioId,
      flavour: 'mixed',
    });
    return result;
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Agent Delegations
  // ───────────────────────────────────────────────────────────────────────────

  /**
   * Orchestrate chaos via MarchHareAgent.
   */
  async orchestrateChaos(
    operation: 'plan' | 'execute' | 'escalate',
    params: Record<string, unknown>
  ): Promise<unknown> {
    const marchHare = this.getAgent('SID-CHAOSPARTY-MARCHHARE') as MarchHareAgent;
    const result = await marchHare.runCycle({
      operation,
      ...params,
    });
    return result;
  }

  /**
   * Calm chaos via DormouseAgent.
   */
  async calmChaos(
    operation: 'assess' | 'calm' | 'stabilise',
    params: Record<string, unknown>
  ): Promise<unknown> {
    const dormouse = this.getAgent('SID-CHAOSPARTY-DORMOUSE') as DormouseAgent;
    const result = await dormouse.runCycle({
      operation,
      ...params,
    });
    return result;
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Chaos Index & Metrics
  // ───────────────────────────────────────────────────────────────────────────

  private updateChaosIndex(): void {
    const activeScenarios = Array.from(this.scenarios.values())
      .filter((s) => s.status === 'running').length;
    const recentEvents = Array.from(this.events.values())
      .filter((e) => Date.now() - e.timestamp < 60000).length;
    const disruptiveEvents = Array.from(this.events.values())
      .filter((e) => e.effect === 'disruptive').length;

    this.chaosIndex = Math.min(100, Math.floor(
      activeScenarios * 15 + recentEvents * 5 + disruptiveEvents * 10
    ));

    // Resilience degrades with chaos, recovers when calm
    if (this.chaosIndex > 50) {
      this.resilienceScore = Math.max(0, this.resilienceScore - 2);
    } else {
      this.resilienceScore = Math.min(100, this.resilienceScore + 1);
    }
  }

  /**
   * Get current entropy metrics.
   */
  getMetrics(): EntropyMetrics {
    return {
      totalScenarios: this.scenarios.size,
      activeScenarios: Array.from(this.scenarios.values())
        .filter((s) => s.status === 'running').length,
      totalEvents: this.events.size,
      disruptions: Array.from(this.events.values())
        .filter((e) => e.effect === 'disruptive').length,
      calmedEvents: Array.from(this.events.values())
        .filter((e) => e.result === 'success' || e.result === 'unexpected').length,
      chaosIndex: this.chaosIndex,
      resilienceScore: this.resilienceScore,
      entropyGenerated: this.events.size * 128, // rough bits
      lastChaosAt: this.events.size > 0
        ? Math.max(...Array.from(this.events.values()).map((e) => e.timestamp))
        : 0,
    };
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Health Check
  // ───────────────────────────────────────────────────────────────────────────

  healthCheck(): {
    status: 'healthy' | 'degraded' | 'critical' | 'chaotic';
    chaosIndex: number;
    resilienceScore: number;
    activeScenarios: number;
    pendingTimeBombs: number;
    agents: number;
    bots: number;
    timestamp: number;
  } {
    const metrics = this.getMetrics();
    const activeBombs = Array.from(this.timeBombs.values())
      .filter((b) => b.armed && !b.detonated).length;

    let status: 'healthy' | 'degraded' | 'critical' | 'chaotic';
    if (metrics.chaosIndex > 75) status = 'chaotic';
    else if (metrics.chaosIndex > 50) status = 'critical';
    else if (metrics.chaosIndex > 25) status = 'degraded';
    else status = 'healthy';

    return {
      status,
      chaosIndex: metrics.chaosIndex,
      resilienceScore: metrics.resilienceScore,
      activeScenarios: metrics.activeScenarios,
      pendingTimeBombs: activeBombs,
      agents: this.listAgentIds().length,
      bots: this.listBotNames().length,
      timestamp: Date.now(),
    };
  }
}
