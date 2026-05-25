/**
 * MixerBot — Concept Mixing Bot for Imaginarium
 *
 * Identity:  NID-IMAGINARIUM-MIXER
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    ImaginariumAI (AID-IMAGINARIUM)
 *
 * Responsibilities:
 *   - Mix concepts together using various strategies
 *   - Random mix: randomly combine attributes from concepts
 *   - Weighted mix: combine with priority weighting
 *   - Stratified mix: preserve distinct layers from each concept
 *   - Shuffle: randomly redistribute concept elements
 */

import { Bot, Logger } from '../../../core/definitions';

// ───────────────────────────────────────────────────────
// Domain Types
// ───────────────────────────────────────────────────────

export interface MixParams {
  operation: 'MIX';
  conceptIds: string[];
  method: 'random' | 'weighted' | 'stratified';
  weights?: Record<string, number>; // conceptId → weight (for weighted mix)
}

export interface ShuffleParams {
  operation: 'SHUFFLE';
  concepts: Array<{
    id: string;
    name: string;
    tags: string[];
    attributes: Record<string, unknown>;
  }>;
  intensity: number; // 0..1, how much to shuffle
}

export type MixerInput = MixParams | ShuffleParams;

// ───────────────────────────────────────────────────────
// MixerBot Implementation
// ───────────────────────────────────────────────────────

export class MixerBot extends Bot {
  private readonly log: Logger;

  constructor() {
    const handler = async (input: MixerInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-IMAGINARIUM-MIXER',
      'Mixer',
      handler,
      'Concept mixing (random, weighted, stratified) and element shuffling'
    );

    this.log = new Logger('MixerBot');
  }

  private async process(input: MixerInput): Promise<unknown> {
    switch (input.operation) {
      case 'MIX':
        return this.mixConcepts(input);
      case 'SHUFFLE':
        return this.shuffleConcepts(input);
      default:
        throw new Error(`Unknown mixer operation: ${(input as MixerInput).operation}`);
    }
  }

  // ───────────────────────────────────────────────────────
  // Concept Mixing
  // ───────────────────────────────────────────────────────

  private mixConcepts(params: MixParams): {
    method: string;
    conceptCount: number;
    result: {
      name: string;
      tags: string[];
      attributes: Record<string, unknown>;
      diversityScore: number;
    };
  } {
    const { conceptIds, method, weights } = params;

    // Simulated concept data (in real implementation, fetched from AI's concept store)
    const simulatedConcepts = conceptIds.map((id, idx) => ({
      id,
      name: `Concept-${idx + 1}`,
      tags: [`tag-${idx}-a`, `tag-${idx}-b`, `tag-${idx}-c`],
      attributes: {
        quality: Math.random() * 10,
        category: `category-${idx}`,
        strength: 3 + idx,
      },
    }));

    let mixedTags: string[];
    let mixedAttributes: Record<string, unknown>;
    let diversityScore: number;

    switch (method) {
      case 'random':
        mixedTags = this.randomMix(simulatedConcepts.map((c) => c.tags));
        mixedAttributes = this.randomMixAttrs(simulatedConcepts.map((c) => c.attributes));
        diversityScore = this.computeDiversity(mixedTags);
        break;

      case 'weighted':
        mixedTags = this.weightedMix(
          simulatedConcepts.map((c) => c.tags),
          simulatedConcepts.map((c) => weights?.[c.id] ?? 1)
        );
        mixedAttributes = this.weightedMixAttrs(
          simulatedConcepts.map((c) => c.attributes),
          simulatedConcepts.map((c) => weights?.[c.id] ?? 1)
        );
        diversityScore = this.computeDiversity(mixedTags);
        break;

      case 'stratified':
        mixedTags = this.stratifiedMix(simulatedConcepts.map((c) => c.tags));
        mixedAttributes = this.stratifiedMixAttrs(simulatedConcepts.map((c) => c.attributes));
        diversityScore = this.computeDiversity(mixedTags);
        break;

      default:
        mixedTags = this.randomMix(simulatedConcepts.map((c) => c.tags));
        mixedAttributes = {};
        diversityScore = 0;
    }

    const resultName = `Mix-${method.charAt(0).toUpperCase() + method.slice(1)}-${Date.now().toString(36)}`;

    this.log.info('Concepts mixed', { method, conceptCount: conceptIds.length, diversityScore: diversityScore.toFixed(2) });

    return {
      method,
      conceptCount: conceptIds.length,
      result: {
        name: resultName,
        tags: mixedTags,
        attributes: mixedAttributes,
        diversityScore,
      },
    };
  }

  // ───────────────────────────────────────────────────────
  // Concept Shuffling
  // ───────────────────────────────────────────────────────

  private shuffleConcepts(params: ShuffleParams): {
    intensity: number;
    results: Array<{
      id: string;
      originalTags: string[];
      shuffledTags: string[];
      tagChanges: number;
    }>;
  } {
    const { concepts, intensity } = params;

    const results = concepts.map((concept) => {
      const allTags = concepts.flatMap((c) => c.tags);
      const shuffleCount = Math.ceil(concept.tags.length * intensity);

      // Swap some tags with tags from other concepts
      const shuffledTags = [...concept.tags];
      for (let i = 0; i < shuffleCount; i++) {
        const randomTag = allTags[Math.floor(Math.random() * allTags.length)];
        if (!shuffledTags.includes(randomTag)) {
          shuffledTags[Math.floor(Math.random() * shuffledTags.length)] = randomTag;
        }
      }

      const tagChanges = concept.tags.reduce((count, tag, idx) => count + (tag !== shuffledTags[idx] ? 1 : 0), 0);

      return {
        id: concept.id,
        originalTags: concept.tags,
        shuffledTags,
        tagChanges,
      };
    });

    this.log.info('Concepts shuffled', { conceptCount: concepts.length, intensity });

    return { intensity, results };
  }

  // ───────────────────────────────────────────────────────
  // Mixing Strategies
  // ───────────────────────────────────────────────────────

  private randomMix(tagSets: string[][]): string[] {
    const allTags = tagSets.flat();
    const uniqueTags = [...new Set(allTags)];
    // Randomly select tags from the combined pool
    const count = Math.max(2, Math.ceil(uniqueTags.length * 0.6));
    const selected: string[] = [];
    const available = [...uniqueTags];
    for (let i = 0; i < count && available.length > 0; i++) {
      const idx = Math.floor(Math.random() * available.length);
      selected.push(available.splice(idx, 1)[0]);
    }
    return selected;
  }

  private weightedMix(tagSets: string[][], weights: number[]): string[] {
    const totalWeight = weights.reduce((a, b) => a + b, 0);
    const result: string[] = [];

    for (let i = 0; i < tagSets.length; i++) {
      const proportion = weights[i] / totalWeight;
      const tagCount = Math.max(1, Math.round(tagSets[i].length * proportion));
      result.push(...tagSets[i].slice(0, tagCount));
    }

    return [...new Set(result)];
  }

  private stratifiedMix(tagSets: string[][]): string[] {
    // Take one tag from each stratum (concept) to ensure representation
    const result: string[] = [];
    for (const tags of tagSets) {
      if (tags.length > 0) {
        result.push(tags[Math.floor(Math.random() * tags.length)]);
      }
    }
    return result;
  }

  private randomMixAttrs(attrSets: Record<string, unknown>[]): Record<string, unknown> {
    const result: Record<string, unknown> = {};
    for (const attrs of attrSets) {
      for (const [key, value] of Object.entries(attrs)) {
        if (!result[key] || Math.random() > 0.5) {
          result[key] = value;
        }
      }
    }
    return result;
  }

  private weightedMixAttrs(attrSets: Record<string, unknown>[], weights: number[]): Record<string, unknown> {
    const result: Record<string, unknown> = {};
    const maxWeight = Math.max(...weights);

    for (let i = 0; i < attrSets.length; i++) {
      if (weights[i] === maxWeight) {
        for (const [key, value] of Object.entries(attrSets[i])) {
          if (!result[key]) {
            result[key] = value;
          }
        }
      }
    }
    // Fill gaps from lower-weighted sets
    for (const attrs of attrSets) {
      for (const [key, value] of Object.entries(attrs)) {
        if (!result[key]) {
          result[key] = value;
        }
      }
    }
    return result;
  }

  private stratifiedMixAttrs(attrSets: Record<string, unknown>[]): Record<string, unknown> {
    const result: Record<string, unknown> = {};
    // Take one attribute from each concept's attributes
    for (const attrs of attrSets) {
      const keys = Object.keys(attrs);
      if (keys.length > 0) {
        const key = keys[Math.floor(Math.random() * keys.length)];
        result[key] = attrs[key];
      }
    }
    // Fill remaining
    for (const attrs of attrSets) {
      for (const [key, value] of Object.entries(attrs)) {
        if (!result[key]) {
          result[key] = value;
        }
      }
    }
    return result;
  }

  private computeDiversity(tags: string[]): number {
    if (tags.length === 0) return 0;
    const unique = new Set(tags).size;
    return Math.round((unique / tags.length) * 100) / 100;
  }
}
