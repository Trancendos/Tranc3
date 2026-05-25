/**
 * BlenderBot — Concept Blending Bot for Imaginarium
 *
 * Identity:  NID-IMAGINARIUM-BLENDER
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    ImaginariumAI (AID-IMAGINARIUM)
 *
 * Responsibilities:
 *   - Blend concepts using various methods (intersection, union, mutation, crossover, fusion)
 *   - Intersection: find common ground between concepts
 *   - Union: merge all aspects from all concepts
 *   - Mutation: introduce controlled randomness into concept blending
 *   - Crossover: exchange concept segments (genetic algorithm style)
 *   - Fusion: deeply integrate concepts into a new unified form
 */

import { Bot, Logger } from '../../../core/definitions';

// ───────────────────────────────────────────────────────
// Domain Types
// ───────────────────────────────────────────────────────

export interface BlendOperation {
  operation: 'BLEND';
  recipe: {
    sourceConcepts: string[];
    blendMethod: 'intersection' | 'union' | 'mutation' | 'crossover' | 'fusion';
    intensity: number;
    constraints: string[];
  };
}

export interface EvaluateParams {
  operation: 'EVALUATE';
  blendResult: {
    name: string;
    description: string;
    tags: string[];
    attributes: Record<string, unknown>;
  };
  criteria: string[];
}

export type BlenderInput = BlendOperation | EvaluateParams;

// ───────────────────────────────────────────────────────
// BlenderBot Implementation
// ───────────────────────────────────────────────────────

export class BlenderBot extends Bot {
  private readonly log: Logger;

  constructor() {
    const handler = async (input: BlenderInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-IMAGINARIUM-BLENDER',
      'Blender',
      handler,
      'Concept blending (intersection, union, mutation, crossover, fusion) and blend evaluation'
    );

    this.log = new Logger('BlenderBot');
  }

  private async process(input: BlenderInput): Promise<unknown> {
    switch (input.operation) {
      case 'BLEND':
        return this.blendConcepts(input);
      case 'EVALUATE':
        return this.evaluateBlend(input);
      default:
        throw new Error(`Unknown blender operation: ${(input as BlenderInput).operation}`);
    }
  }

  // ───────────────────────────────────────────────────────
  // Concept Blending
  // ───────────────────────────────────────────────────────

  private blendConcepts(params: BlendOperation): {
    method: string;
    sourceCount: number;
    intensity: number;
    result: {
      name: string;
      description: string;
      tags: string[];
      attributes: Record<string, unknown>;
      coherenceScore: number;
      noveltyScore: number;
    };
  } {
    const { recipe } = params;
    const { sourceConcepts, blendMethod, intensity, constraints } = recipe;

    // Simulated source concept data
    const sources = sourceConcepts.map((id, idx) => ({
      id,
      name: `Source-${idx + 1}`,
      description: `Description for concept ${idx + 1}`,
      tags: [`domain-${idx}`, `feature-${idx}-a`, `feature-${idx}-b`],
      attributes: {
        strength: (idx + 1) * 2,
        category: `cat-${idx}`,
        value: Math.random() * 10,
      },
    }));

    let result: { name: string; description: string; tags: string[]; attributes: Record<string, unknown>; coherenceScore: number; noveltyScore: number };

    switch (blendMethod) {
      case 'intersection':
        result = this.intersectionBlend(sources, intensity);
        break;
      case 'union':
        result = this.unionBlend(sources, intensity);
        break;
      case 'mutation':
        result = this.mutationBlend(sources, intensity);
        break;
      case 'crossover':
        result = this.crossoverBlend(sources, intensity);
        break;
      case 'fusion':
        result = this.fusionBlend(sources, intensity);
        break;
      default:
        result = this.unionBlend(sources, intensity);
    }

    // Apply constraints: filter out tags that match constraint patterns
    for (const constraint of constraints) {
      result.tags = result.tags.filter((t) => !t.includes(constraint.toLowerCase()));
    }

    this.log.info('Concepts blended', {
      method: blendMethod,
      sourceCount: sourceConcepts.length,
      coherenceScore: result.coherenceScore.toFixed(2),
      noveltyScore: result.noveltyScore.toFixed(2),
    });

    return { method: blendMethod, sourceCount: sourceConcepts.length, intensity, result };
  }

  private intersectionBlend(sources: Array<{ name: string; tags: string[]; attributes: Record<string, unknown> }>, intensity: number): { name: string; description: string; tags: string[]; attributes: Record<string, unknown>; coherenceScore: number; noveltyScore: number } {
    // Find common tags across sources
    const tagCounts: Record<string, number> = {};
    for (const source of sources) {
      for (const tag of source.tags) {
        tagCounts[tag] = (tagCounts[tag] || 0) + 1;
      }
    }

    const threshold = Math.max(1, Math.ceil(sources.length * intensity));
    const commonTags = Object.entries(tagCounts)
      .filter(([, count]) => count >= threshold)
      .map(([tag]) => tag);

    // Common attributes
    const commonAttributes: Record<string, unknown> = {};
    const allKeys = new Set(sources.flatMap((s) => Object.keys(s.attributes)));
    for (const key of allKeys) {
      const values = sources.map((s) => s.attributes[key]).filter((v) => v !== undefined);
      if (values.length >= threshold) {
        commonAttributes[key] = values[0]; // take first matching value
      }
    }

    return {
      name: `Intersection-${Date.now().toString(36)}`,
      description: `Common ground of ${sources.length} concepts`,
      tags: commonTags.length > 0 ? commonTags : ['shared-ground'],
      attributes: commonAttributes,
      coherenceScore: 0.9, // intersection is highly coherent
      noveltyScore: 0.3,   // but not very novel
    };
  }

  private unionBlend(sources: Array<{ name: string; tags: string[]; attributes: Record<string, unknown> }>, intensity: number): { name: string; description: string; tags: string[]; attributes: Record<string, unknown>; coherenceScore: number; noveltyScore: number } {
    const allTags = [...new Set(sources.flatMap((s) => s.tags))];
    const allAttributes: Record<string, unknown> = {};
    for (const source of sources) {
      Object.assign(allAttributes, source.attributes);
    }

    return {
      name: `Union-${Date.now().toString(36)}`,
      description: `Unified blend of ${sources.length} concepts`,
      tags: allTags,
      attributes: allAttributes,
      coherenceScore: Math.max(0.3, 0.7 - sources.length * 0.05),
      noveltyScore: 0.6,
    };
  }

  private mutationBlend(sources: Array<{ name: string; tags: string[]; attributes: Record<string, unknown> }>, intensity: number): { name: string; description: string; tags: string[]; attributes: Record<string, unknown>; coherenceScore: number; noveltyScore: number } {
    // Start with union then introduce mutations
    const base = this.unionBlend(sources, intensity);

    // Mutate tags: add random variants, remove some
    const mutatedTags = base.tags.filter(() => Math.random() > intensity * 0.3);
    const mutationCount = Math.ceil(mutatedTags.length * intensity * 0.5);
    for (let i = 0; i < mutationCount; i++) {
      mutatedTags.push(`mutated-${Math.random().toString(36).slice(2, 6)}`);
    }

    // Mutate numeric attributes
    const mutatedAttrs = { ...base.attributes };
    for (const [key, value] of Object.entries(mutatedAttrs)) {
      if (typeof value === 'number') {
        mutatedAttrs[key] = Math.round((value * (1 + (Math.random() - 0.5) * intensity * 2)) * 100) / 100;
      }
    }

    return {
      name: `Mutation-${Date.now().toString(36)}`,
      description: `Mutated blend of ${sources.length} concepts`,
      tags: [...new Set(mutatedTags)],
      attributes: mutatedAttrs,
      coherenceScore: Math.max(0.2, 0.6 - intensity * 0.3),
      noveltyScore: Math.min(1, 0.5 + intensity * 0.4),
    };
  }

  private crossoverBlend(sources: Array<{ name: string; tags: string[]; attributes: Record<string, unknown> }>, intensity: number): { name: string; description: string; tags: string[]; attributes: Record<string, unknown>; coherenceScore: number; noveltyScore: number } {
    if (sources.length < 2) {
      return this.unionBlend(sources, intensity);
    }

    // Genetic crossover: take first half of tags from source A, second half from source B
    const sourceA = sources[0];
    const sourceB = sources[sources.length - 1];
    const splitPoint = Math.ceil(sourceA.tags.length * (0.3 + intensity * 0.4));

    const crossoverTags = [
      ...sourceA.tags.slice(0, splitPoint),
      ...sourceB.tags.slice(splitPoint),
    ];

    // Crossover attributes
    const keysA = Object.keys(sourceA.attributes);
    const keysB = Object.keys(sourceB.attributes);
    const attrSplit = Math.ceil(keysA.length / 2);
    const crossoverAttrs: Record<string, unknown> = {};
    for (let i = 0; i < attrSplit && i < keysA.length; i++) {
      crossoverAttrs[keysA[i]] = sourceA.attributes[keysA[i]];
    }
    for (let i = attrSplit; i < keysB.length; i++) {
      crossoverAttrs[keysB[i]] = sourceB.attributes[keysB[i]];
    }

    return {
      name: `Crossover-${Date.now().toString(36)}`,
      description: `Crossover of ${sourceA.name} × ${sourceB.name}`,
      tags: [...new Set(crossoverTags)],
      attributes: crossoverAttrs,
      coherenceScore: 0.65,
      noveltyScore: 0.7,
    };
  }

  private fusionBlend(sources: Array<{ name: string; tags: string[]; attributes: Record<string, unknown> }>, intensity: number): { name: string; description: string; tags: string[]; attributes: Record<string, unknown>; coherenceScore: number; noveltyScore: number } {
    // Deep fusion: average numeric values, merge tag semantics, create unified identity
    const fusedTags: string[] = [];
    const tagFreq: Record<string, number> = {};
    for (const source of sources) {
      for (const tag of source.tags) {
        tagFreq[tag] = (tagFreq[tag] || 0) + 1;
      }
    }
    // Keep tags that appear in at least half the sources, plus top unique ones
    const halfThreshold = Math.ceil(sources.length / 2);
    for (const [tag, freq] of Object.entries(tagFreq)) {
      if (freq >= halfThreshold || Math.random() < intensity * 0.3) {
        fusedTags.push(tag);
      }
    }
    // Add fusion-specific tags
    fusedTags.push('fused', 'hybrid');

    // Average numeric attributes
    const fusedAttrs: Record<string, unknown> = {};
    const numericAttrs: Record<string, number[]> = {};
    for (const source of sources) {
      for (const [key, value] of Object.entries(source.attributes)) {
        if (typeof value === 'number') {
          if (!numericAttrs[key]) numericAttrs[key] = [];
          numericAttrs[key].push(value);
        }
      }
    }
    for (const [key, values] of Object.entries(numericAttrs)) {
      fusedAttrs[key] = Math.round((values.reduce((a, b) => a + b, 0) / values.length) * 100) / 100;
    }
    fusedAttrs['fusionSourceCount'] = sources.length;
    fusedAttrs['fusionIntensity'] = intensity;

    const sourceNames = sources.map((s) => s.name).join(' + ');

    return {
      name: `Fusion-${Date.now().toString(36)}`,
      description: `Deep fusion of ${sourceNames}`,
      tags: [...new Set(fusedTags)],
      attributes: fusedAttrs,
      coherenceScore: Math.min(0.9, 0.6 + intensity * 0.2),
      noveltyScore: Math.min(0.9, 0.5 + intensity * 0.3),
    };
  }

  // ───────────────────────────────────────────────────────
  // Blend Evaluation
  // ───────────────────────────────────────────────────────

  private evaluateBlend(params: EvaluateParams): {
    scores: Record<string, number>;
    overallScore: number;
    recommendations: string[];
  } {
    const { blendResult, criteria } = params;
    const scores: Record<string, number> = {};

    // Evaluate against each criterion
    for (const criterion of criteria) {
      const cLower = criterion.toLowerCase();
      if (cLower.includes('novel') || cLower.includes('original')) {
        scores[criterion] = blendResult.tags.length > 3 ? 0.7 + Math.random() * 0.2 : 0.4;
      } else if (cLower.includes('coheren') || cLower.includes('consistent')) {
        scores[criterion] = 0.6 + Math.random() * 0.3;
      } else if (cLower.includes('feasib') || cLower.includes('practical')) {
        scores[criterion] = 0.5 + Math.random() * 0.3;
      } else if (cLower.includes('impact') || cLower.includes('value')) {
        scores[criterion] = 0.5 + Math.random() * 0.4;
      } else {
        scores[criterion] = 0.5 + Math.random() * 0.3;
      }
      scores[criterion] = Math.round(scores[criterion] * 100) / 100;
    }

    const overallScore = Object.values(scores).length > 0
      ? Math.round((Object.values(scores).reduce((a, b) => a + b, 0) / Object.values(scores).length) * 100) / 100
      : 0.5;

    const recommendations: string[] = [];
    for (const [criterion, score] of Object.entries(scores)) {
      if (score < 0.5) {
        recommendations.push(`Improve ${criterion}: current score ${score.toFixed(2)}`);
      }
    }
    if (blendResult.tags.length < 3) {
      recommendations.push('Add more tags for richer concept identity');
    }

    this.log.info('Blend evaluated', { criteriaCount: criteria.length, overallScore: overallScore.toFixed(2) });

    return { scores, overallScore, recommendations };
  }
}
