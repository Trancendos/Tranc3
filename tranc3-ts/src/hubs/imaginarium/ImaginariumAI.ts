/**
 * ImaginariumAI — Lead AI for the Imaginarium Hub
 *
 * Identity:  AID-IMAGINARIUM
 * Pillar:    Voxx
 * Tier:      3 (Lead AI / Domain Orchestrator)
 * Domain:    Creative ideation, brainstorming, concept
 *            blending, idea generation, innovation sandbox
 *
 * Pipeline:  Mixer → Blender → Alchemist → Architect
 *            Welder joins concepts, Polisher refines output
 */

import { AI, Agent, Bot, Logger, AuditLedger } from '../../core/definitions'
import { AlchemistAgent } from './agents/AlchemistAgent';
import { ArchitectAgent } from './agents/ArchitectAgent';
import { MixerBot } from './bots/MixerBot';
import { BlenderBot } from './bots/BlenderBot';
import { WelderBot } from './bots/WelderBot';
import { PolisherBot } from './bots/PolisherBot';

const auditLedger = new AuditLedger();

// ───────────────────────────────────────────────────────
// Domain Interfaces
// ───────────────────────────────────────────────────────

export interface Concept {
  id: string;
  name: string;
  description: string;
  tags: string[];
  domain: string;
  complexity: number;       // 1-10
  novelty: number;          // 1-10
  relatedConcepts: string[];
  attributes: Record<string, unknown>;
  createdAt: number;
}

export interface BlendRecipe {
  id: string;
  sourceConcepts: string[];
  blendMethod: 'intersection' | 'union' | 'mutation' | 'crossover' | 'fusion';
  intensity: number;        // 0..1, how aggressively to blend
  constraints: string[];
  result?: Concept;
  score?: number;
}

export interface IdeaSpace {
  id: string;
  name: string;
  concepts: Map<string, Concept>;
  dimensions: string[];     // axes of the idea space
  bounds: Record<string, { min: number; max: number }>;
  density: number;          // concept density metric
}

export interface CreativeSession {
  id: string;
  prompt: string;
  ideaSpaceId: string;
  concepts: Concept[];
  blends: BlendRecipe[];
  iterations: number;
  bestScore: number;
  status: 'exploring' | 'synthesizing' | 'refining' | 'complete';
  createdAt: number;
}

// ───────────────────────────────────────────────────────
// ImaginariumAI Implementation
// ───────────────────────────────────────────────────────

export class ImaginariumAI extends AI {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private ideaSpaces: Map<string, IdeaSpace>;
  private sessions: Map<string, CreativeSession>;
  private concepts: Map<string, Concept>;

  constructor() {
    super(
      'AID-IMAGINARIUM',
      'Imaginarium',
      'imaginarium',
      'Voxx',
      3
    );

    this.log = new Logger('ImaginariumAI');
    this.audit = auditLedger;
    this.ideaSpaces = new Map();
    this.sessions = new Map();
    this.concepts = new Map();

    // Register Agents
    this.registerAgent(new AlchemistAgent());
    this.registerAgent(new ArchitectAgent());

    // Register Bots
    this.registerBot(new MixerBot());
    this.registerBot(new BlenderBot());
    this.registerBot(new WelderBot());
    this.registerBot(new PolisherBot());

    this.log.info('ImaginariumAI initialised', {
      agents: this.listAgentIds(),
      bots: this.listBotNames(),
    });
  }

  // ───────────────────────────────────────────────────────
  // Concept Management
  // ───────────────────────────────────────────────────────

  /**
   * Create a new concept in the idea space.
   */
  createConcept(name: string, description: string, tags: string[] = [], domain = 'general'): Concept {
    const id = `CONCEPT-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`.toUpperCase();
    const concept: Concept = {
      id,
      name,
      description,
      tags,
      domain,
      complexity: 5,
      novelty: 5,
      relatedConcepts: [],
      attributes: {},
      createdAt: Date.now(),
    };

    this.concepts.set(id, concept);

    this.audit.append({
      actor: this.id,
      action: 'CONCEPT_CREATED',
      entity: id,
      details: { name, domain, tagCount: tags.length },
      timestamp: new Date(),
    });

    this.log.info('Concept created', { id, name, domain });
    return concept;
  }

  /**
   * Retrieve a concept by ID.
   */
  getConcept(id: string): Concept | undefined {
    return this.concepts.get(id);
  }

  /**
   * List all concepts, optionally filtered by domain.
   */
  listConcepts(domain?: string): Concept[] {
    const all = Array.from(this.concepts.values());
    return domain ? all.filter((c) => c.domain === domain) : all;
  }

  // ───────────────────────────────────────────────────────
  // Idea Space Management
  // ───────────────────────────────────────────────────────

  /**
   * Create a new idea space for exploration.
   */
  createIdeaSpace(name: string, dimensions: string[] = ['novelty', 'feasibility', 'impact']): IdeaSpace {
    const id = `SPACE-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`.toUpperCase();
    const bounds: Record<string, { min: number; max: number }> = {};
    for (const dim of dimensions) {
      bounds[dim] = { min: 0, max: 10 };
    }

    const space: IdeaSpace = {
      id,
      name,
      concepts: new Map(),
      dimensions,
      bounds,
      density: 0,
    };

    this.ideaSpaces.set(id, space);

    this.log.info('Idea space created', { id, name, dimensions });
    return space;
  }

  /**
   * Get an idea space by ID.
   */
  getIdeaSpace(id: string): IdeaSpace | undefined {
    return this.ideaSpaces.get(id);
  }

  // ───────────────────────────────────────────────────────
  // Creative Sessions
  // ───────────────────────────────────────────────────────

  /**
   * Start a new creative session.
   */
  startSession(prompt: string, ideaSpaceId: string): CreativeSession {
    const space = this.ideaSpaces.get(ideaSpaceId);
    if (!space) throw new Error(`Idea space not found: ${ideaSpaceId}`);

    const id = `SESSION-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`.toUpperCase();
    const session: CreativeSession = {
      id,
      prompt,
      ideaSpaceId,
      concepts: [],
      blends: [],
      iterations: 0,
      bestScore: 0,
      status: 'exploring',
      createdAt: Date.now(),
    };

    this.sessions.set(id, session);

    this.audit.append({
      actor: this.id,
      action: 'SESSION_STARTED',
      entity: id,
      details: { prompt: prompt.slice(0, 100), ideaSpaceId },
      timestamp: new Date(),
    });

    this.log.info('Creative session started', { id, prompt: prompt.slice(0, 50) });
    return session;
  }

  /**
   * Mix concepts using MixerBot.
   */
  async mixConcepts(conceptIds: string[], method: 'random' | 'weighted' | 'stratified' = 'weighted'): Promise<unknown> {
    const mixer = this.getBot('Mixer')!;
    const result = await mixer.execute({
      operation: 'MIX',
      conceptIds,
      method,
    });
    return result;
  }

  /**
   * Blend concepts using BlenderBot.
   */
  async blendConcepts(recipe: Omit<BlendRecipe, 'id' | 'result' | 'score'>): Promise<unknown> {
    const blender = this.getBot('Blender')!;
    const result = await blender.execute({
      operation: 'BLEND',
      recipe,
    });
    return result;
  }

  /**
   * Weld (join) concepts using WelderBot.
   */
  async weldConcepts(conceptA: Concept, conceptB: Concept, joinPoint: string): Promise<unknown> {
    const welder = this.getBot('Welder')!;
    const result = await welder.execute({
      operation: 'WELD',
      conceptA,
      conceptB,
      joinPoint,
    });
    return result;
  }

  /**
   * Polish (refine) a concept using PolisherBot.
   */
  async polishConcept(concept: Concept, criteria: string[] = ['clarity', 'coherence', 'completeness']): Promise<unknown> {
    const polisher = this.getBot('Polisher')!;
    const result = await polisher.execute({
      operation: 'POLISH',
      concept,
      criteria,
    });
    return result;
  }

  /**
   * Delegate alchemical concept transformation to AlchemistAgent.
   */
  async transmuteConcept(conceptId: string, transformation: string): Promise<unknown> {
    const concept = this.concepts.get(conceptId);
    if (!concept) throw new Error(`Concept not found: ${conceptId}`);

    const alchemist = this.getAgent('SID-IMAGINARIUM-ALCHEMIST') as AlchemistAgent;
    const result = await alchemist.runCycle({ concept, transformation });

    this.log.info('Concept transmuted', { conceptId, transformation });
    return result;
  }

  /**
   * Delegate structural design to ArchitectAgent.
   */
  async architectConcept(conceptId: string, structureType: string): Promise<unknown> {
    const concept = this.concepts.get(conceptId);
    if (!concept) throw new Error(`Concept not found: ${conceptId}`);

    const architect = this.getAgent('SID-IMAGINARIUM-ARCHITECT') as ArchitectAgent;
    const result = await architect.runCycle({ concept, structureType });

    this.log.info('Concept architected', { conceptId, structureType });
    return result;
  }

  // ───────────────────────────────────────────────────────
  // Health & Diagnostics
  // ───────────────────────────────────────────────────────

  healthCheck(): {
    status: 'healthy' | 'degraded' | 'critical';
    concepts: number;
    ideaSpaces: number;
    sessions: number;
    agents: number;
    bots: number;
    timestamp: number;
  } {
    return {
      status: 'healthy',
      concepts: this.concepts.size,
      ideaSpaces: this.ideaSpaces.size,
      sessions: this.sessions.size,
      agents: this.listAgentIds().length,
      bots: this.listBotNames().length,
      timestamp: Date.now(),
    };
  }
}
