/**
 * AlchemistAgent — Concept Transformation Agent for Imaginarium
 *
 * Identity:  SID-IMAGINARIUM-ALCHEMIST
 * Tier:      4 (Autonomous Microservice)
 * Parent:    ImaginariumAI (AID-IMAGINARIUM)
 *
 * Responsibilities:
 *   - Transform concepts through alchemical operations
 *   - Sublimate: extract essence of a concept (reduce to core attributes)
 *   - Distill: purify and concentrate concept's most valuable aspects
 *   - Transmute: change a concept from one form/domain to another
 *   - Crystallize: solidify an abstract concept into concrete form
 */

import { Agent, Bot, Logger } from '../../../core/definitions';

// ───────────────────────────────────────────────────────
// Domain Types
// ───────────────────────────────────────────────────────

export interface ConceptInput {
  concept: {
    id: string;
    name: string;
    description: string;
    tags: string[];
    domain: string;
    complexity: number;
    novelty: number;
    relatedConcepts: string[];
    attributes: Record<string, unknown>;
  };
  transformation: string;
}

export interface AlchemicalResult {
  operation: string;
  input: { conceptId: string; conceptName: string };
  output: {
    name: string;
    description: string;
    tags: string[];
    domain: string;
    complexity: number;
    novelty: number;
    attributes: Record<string, unknown>;
  };
  changes: string[];
  qualityScore: number;
}

// ───────────────────────────────────────────────────────
// AlchemistAgent Implementation
// ───────────────────────────────────────────────────────

export class AlchemistAgent extends Agent {
  private readonly log: Logger;

  constructor() {
    super('SID-IMAGINARIUM-ALCHEMIST');
    this.log = new Logger('AlchemistAgent');
  }

  async perceive(observation: ConceptInput): Promise<{
    concept: ConceptInput['concept'];
    transformationType: string;
    intensity: number;
    constraints: string[];
  }> {
    const { concept, transformation } = observation;
    const tLower = transformation.toLowerCase();

    // Determine transformation type
    let transformationType = 'transmute';
    if (tLower.includes('sublime') || tLower.includes('extract') || tLower.includes('essence')) {
      transformationType = 'sublimate';
    } else if (tLower.includes('distill') || tLower.includes('purif') || tLower.includes('concentrate')) {
      transformationType = 'distill';
    } else if (tLower.includes('crystallize') || tLower.includes('solidify') || tLower.includes('concrete')) {
      transformationType = 'crystallize';
    }

    // Estimate intensity from language
    const intensityKeywords = ['deeply', 'thoroughly', 'radically', 'fundamentally', 'completely'];
    const intensity = intensityKeywords.some((kw) => tLower.includes(kw)) ? 0.9 : 0.5;

    this.log.info('Perceived transformation request', { conceptId: concept.id, transformationType, intensity });

    return { concept, transformationType, intensity, constraints: [] };
  }

  async decide(perceived: Awaited<ReturnType<typeof this.perceive>>): Promise<{
    action: string;
    params: Record<string, unknown>;
  }> {
    const { transformationType, intensity, concept } = perceived;

    this.log.info('Decided on alchemical action', { transformationType, intensity });

    return {
      action: transformationType,
      params: { concept, intensity, constraints: perceived.constraints },
    };
  }

  async act(decision: Awaited<ReturnType<typeof this.decide>>): Promise<AlchemicalResult> {
    const { action, params } = decision;
    const concept = params.concept as ConceptInput['concept'];
    const intensity = params.intensity as number;

    let result: AlchemicalResult;

    switch (action) {
      case 'sublimate':
        result = this.sublimate(concept, intensity);
        break;
      case 'distill':
        result = this.distill(concept, intensity);
        break;
      case 'crystallize':
        result = this.crystallize(concept, intensity);
        break;
      default:
        result = this.transmute(concept, intensity);
        break;
    }

    this.log.info('Alchemical operation complete', {
      operation: result.operation,
      inputConcept: concept.name,
      outputConcept: result.output.name,
      qualityScore: result.qualityScore.toFixed(2),
    });

    return result;
  }

  // ───────────────────────────────────────────────────────
  // Alchemical Operations
  // ───────────────────────────────────────────────────────

  private sublimate(concept: ConceptInput['concept'], intensity: number): AlchemicalResult {
    // Extract essence: reduce to core attributes, strip noise
    const coreTags = concept.tags.slice(0, Math.max(2, Math.ceil(concept.tags.length * (1 - intensity))));
    const coreAttributes: Record<string, unknown> = {};
    const attrKeys = Object.keys(concept.attributes);
    const keepCount = Math.max(1, Math.ceil(attrKeys.length * (1 - intensity * 0.5)));
    for (let i = 0; i < keepCount && i < attrKeys.length; i++) {
      coreAttributes[attrKeys[i]] = concept.attributes[attrKeys[i]];
    }

    const changes = [
      `Reduced tags from ${concept.tags.length} to ${coreTags.length}`,
      `Extracted ${keepCount} core attributes`,
      `Complexity reduced from ${concept.complexity} to ${Math.max(1, Math.round(concept.complexity * (1 - intensity * 0.4)))}`,
    ];

    return {
      operation: 'sublimate',
      input: { conceptId: concept.id, conceptName: concept.name },
      output: {
        name: `Essence of ${concept.name}`,
        description: `Core essence: ${concept.description.split('.').slice(0, 2).join('.')}`,
        tags: coreTags,
        domain: concept.domain,
        complexity: Math.max(1, Math.round(concept.complexity * (1 - intensity * 0.4))),
        novelty: Math.min(10, concept.novelty + 1),
        attributes: coreAttributes,
      },
      changes,
      qualityScore: 0.7 + intensity * 0.2,
    };
  }

  private distill(concept: ConceptInput['concept'], intensity: number): AlchemicalResult {
    // Purify: enhance the most valuable aspects, remove weak ones
    const sortedTags = [...concept.tags].sort(() => Math.random() - 0.5);
    const purifiedTags = sortedTags.slice(0, Math.max(2, Math.ceil(sortedTags.length * 0.7)));

    const distilledAttributes: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(concept.attributes)) {
      // "Amplify" numeric values
      if (typeof value === 'number') {
        distilledAttributes[key] = Math.round(value * (1 + intensity * 0.3) * 10) / 10;
      } else {
        distilledAttributes[key] = value;
      }
    }

    const changes = [
      `Purified tags: kept ${purifiedTags.length} of ${concept.tags.length}`,
      `Amplified ${Object.keys(distilledAttributes).length} attributes`,
      `Novelty increased from ${concept.novelty} to ${Math.min(10, concept.novelty + Math.round(intensity * 2))}`,
    ];

    return {
      operation: 'distill',
      input: { conceptId: concept.id, conceptName: concept.name },
      output: {
        name: `Pure ${concept.name}`,
        description: `Distilled form: ${concept.description}`,
        tags: purifiedTags,
        domain: concept.domain,
        complexity: Math.max(2, Math.round(concept.complexity * 0.8)),
        novelty: Math.min(10, concept.novelty + Math.round(intensity * 2)),
        attributes: distilledAttributes,
      },
      changes,
      qualityScore: 0.75 + intensity * 0.15,
    };
  }

  private transmute(concept: ConceptInput['concept'], intensity: number): AlchemicalResult {
    // Transform: change domain, alter fundamental properties
    const domains = ['technology', 'art', 'science', 'business', 'social', 'nature', 'philosophy'];
    const otherDomains = domains.filter((d) => d !== concept.domain);
    const newDomain = otherDomains[Math.floor(Math.random() * otherDomains.length)] || 'general';

    const domainMapping: Record<string, string[]> = {
      technology: ['algorithmic', 'digital', 'automated', 'scalable', 'distributed'],
      art: ['aesthetic', 'expressive', 'evocative', 'immersive', 'narrative'],
      science: ['empirical', 'hypothesis-driven', 'reproducible', 'measurable', 'systematic'],
      business: ['marketable', 'profitable', 'scalable', 'customer-centric', 'disruptive'],
      social: ['community-driven', 'collaborative', 'inclusive', 'impactful', 'grassroots'],
      nature: ['organic', 'sustainable', 'adaptive', 'resilient', 'biomimetic'],
      philosophy: ['existential', 'dialectical', 'normative', 'epistemic', 'teleological'],
    };

    const newTags = [...concept.tags.slice(0, 2), ...(domainMapping[newDomain]?.slice(0, 3) ?? [])];

    const changes = [
      `Domain transmuted from ${concept.domain} to ${newDomain}`,
      `Tags reshaped for new domain`,
      `Complexity shifted from ${concept.complexity} to ${Math.min(10, concept.complexity + Math.round(intensity * 3))}`,
    ];

    return {
      operation: 'transmute',
      input: { conceptId: concept.id, conceptName: concept.name },
      output: {
        name: `${newDomain.charAt(0).toUpperCase() + newDomain.slice(1)} ${concept.name}`,
        description: `Transmuted to ${newDomain}: ${concept.description}`,
        tags: newTags,
        domain: newDomain,
        complexity: Math.min(10, concept.complexity + Math.round(intensity * 3)),
        novelty: Math.min(10, concept.novelty + 2),
        attributes: { ...concept.attributes, transmutedDomain: newDomain },
      },
      changes,
      qualityScore: 0.6 + intensity * 0.2,
    };
  }

  private crystallize(concept: ConceptInput['concept'], intensity: number): AlchemicalResult {
    // Solidify: make abstract concept concrete with specific implementations
    const implementations: Record<string, string[]> = {
      general: ['prototype', 'MVP', 'specification', 'blueprint', 'roadmap'],
    };

    const implOptions = implementations['general'];
    const chosenImpl = implOptions[Math.floor(Math.random() * implOptions.length)];

    const changes = [
      `Crystallized as ${chosenImpl}`,
      `Complexity reduced from ${concept.complexity} to ${Math.max(2, Math.round(concept.complexity * 0.7))}`,
      `Added concrete attributes: form, specification, implementation`,
    ];

    return {
      operation: 'crystallize',
      input: { conceptId: concept.id, conceptName: concept.name },
      output: {
        name: `${concept.name} ${chosenImpl.charAt(0).toUpperCase() + chosenImpl.slice(1)}`,
        description: `Concrete form (${chosenImpl}): ${concept.description}`,
        tags: [...concept.tags, chosenImpl, 'concrete', 'implementable'],
        domain: concept.domain,
        complexity: Math.max(2, Math.round(concept.complexity * 0.7)),
        novelty: Math.max(3, concept.novelty - 1),
        attributes: {
          ...concept.attributes,
          form: chosenImpl,
          specification: `Concrete ${chosenImpl} for ${concept.name}`,
          implementation: `Step-by-step ${chosenImpl} plan`,
        },
      },
      changes,
      qualityScore: 0.8 + intensity * 0.1,
    };
  }
}
