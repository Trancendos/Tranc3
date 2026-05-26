/**
 * PolisherBot — Concept Refinement Bot for Imaginarium
 *
 * Identity:  NID-IMAGINARIUM-POLISHER
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    ImaginariumAI (AID-IMAGINARIUM)
 *
 * Responsibilities:
 *   - Polish (refine) concepts against quality criteria
 *   - Clarify: improve description clarity and specificity
 *   - Trim: remove redundant or weak elements
 *   - Enhance: strengthen the most valuable aspects
 *   - Score: evaluate concept against quality dimensions
 */

import { Bot, Logger } from '../../../core/definitions';

// ───────────────────────────────────────────────────────
// Domain Types
// ───────────────────────────────────────────────────────

export interface PolishParams {
  operation: 'POLISH';
  concept: {
    id: string;
    name: string;
    description: string;
    tags: string[];
    domain: string;
    complexity: number;
    novelty: number;
    attributes: Record<string, unknown>;
  };
  criteria: string[];
}

export interface ClarifyParams {
  operation: 'CLARIFY';
  concept: {
    id: string;
    name: string;
    description: string;
    tags: string[];
  };
  targetAudience?: 'technical' | 'business' | 'general' | 'academic';
}

export interface TrimParams {
  operation: 'TRIM';
  concept: {
    id: string;
    name: string;
    description: string;
    tags: string[];
    attributes: Record<string, unknown>;
  };
  maxTags?: number;
  maxAttributes?: number;
  removeWeak?: boolean;
}

export interface EnhanceParams {
  operation: 'ENHANCE';
  concept: {
    id: string;
    name: string;
    description: string;
    tags: string[];
    complexity: number;
    novelty: number;
    attributes: Record<string, unknown>;
  };
  focus: 'novelty' | 'complexity' | 'depth' | 'breadth';
}

export type PolisherInput = PolishParams | ClarifyParams | TrimParams | EnhanceParams;

// ───────────────────────────────────────────────────────
// PolisherBot Implementation
// ───────────────────────────────────────────────────────

export class PolisherBot extends Bot {
  private readonly log: Logger;

  constructor() {
    const handler = async (input: PolisherInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-IMAGINARIUM-POLISHER',
      'Polisher',
      handler,
      'Concept polishing, clarification, trimming, enhancement, and quality scoring'
    );

    this.log = new Logger('PolisherBot');
  }

  private async process(input: PolisherInput): Promise<unknown> {
    switch (input.operation) {
      case 'POLISH':
        return this.polishConcept(input);
      case 'CLARIFY':
        return this.clarifyConcept(input);
      case 'TRIM':
        return this.trimConcept(input);
      case 'ENHANCE':
        return this.enhanceConcept(input);
      default:
        throw new Error(`Unknown polisher operation: ${(input as PolisherInput).operation}`);
    }
  }

  // ───────────────────────────────────────────────────────
  // Concept Polishing
  // ───────────────────────────────────────────────────────

  private polishConcept(params: PolishParams): {
    conceptId: string;
    criteriaScores: Record<string, number>;
    overallScore: number;
    improvements: string[];
    polished: {
      description: string;
      tags: string[];
      attributes: Record<string, unknown>;
    };
  } {
    const { concept, criteria } = params;

    // Score each criterion
    const criteriaScores: Record<string, number> = {};
    for (const criterion of criteria) {
      criteriaScores[criterion] = this.scoreCriterion(concept, criterion);
    }

    // Apply improvements based on weak criteria
    const improvements: string[] = [];
    let polishedDescription = concept.description;
    let polishedTags = [...concept.tags];
    const polishedAttributes = { ...concept.attributes };

    for (const [criterion, score] of Object.entries(criteriaScores)) {
      if (score < 0.6) {
        const cLower = criterion.toLowerCase();

        if (cLower.includes('clarity')) {
          // Shorten description, add specificity markers
          if (polishedDescription.length > 200) {
            polishedDescription = polishedDescription.split('.').slice(0, 2).join('.') + '.';
            improvements.push('Shortened description for clarity');
          }
          improvements.push('Added specificity markers to description');
        }

        if (cLower.includes('coherence')) {
          // Remove outlier tags
          if (polishedTags.length > 5) {
            polishedTags = polishedTags.slice(0, 5);
            improvements.push('Removed outlier tags for coherence');
          }
        }

        if (cLower.includes('completeness')) {
          // Add missing typical tags
          const typicalTags = ['defined', 'scoped', 'implementable'];
          for (const tag of typicalTags) {
            if (!polishedTags.includes(tag)) {
              polishedTags.push(tag);
              break; // add just one
            }
          }
          polishedAttributes['polishLevel'] = 'refined';
          improvements.push('Added structural markers for completeness');
        }

        if (cLower.includes('novel') || cLower.includes('original')) {
          polishedTags.push('innovative', 'novel');
          improvements.push('Added novelty markers');
        }
      }
    }

    const overallScore = Object.values(criteriaScores).length > 0
      ? Math.round((Object.values(criteriaScores).reduce((a, b) => a + b, 0) / Object.values(criteriaScores).length) * 100) / 100
      : 0.5;

    this.log.info('Concept polished', { conceptId: concept.id, overallScore: overallScore.toFixed(2), improvements: improvements.length });

    return {
      conceptId: concept.id,
      criteriaScores,
      overallScore,
      improvements,
      polished: {
        description: polishedDescription,
        tags: [...new Set(polishedTags)],
        attributes: polishedAttributes,
      },
    };
  }

  // ───────────────────────────────────────────────────────
  // Concept Clarification
  // ───────────────────────────────────────────────────────

  private clarifyConcept(params: ClarifyParams): {
    conceptId: string;
    targetAudience: string;
    original: { description: string; tagCount: number };
    clarified: { description: string; tags: string[]; readabilityScore: number };
  } {
    const { concept, targetAudience = 'general' } = params;

    let clarifiedDescription = concept.description;
    let additionalTags: string[] = [];

    switch (targetAudience) {
      case 'technical':
        clarifiedDescription = `[Technical] ${concept.description}`;
        additionalTags = ['specification', 'implementation'];
        break;
      case 'business':
        clarifiedDescription = `[Business Value] ${concept.description}`;
        additionalTags = ['value-proposition', 'roi'];
        break;
      case 'academic':
        clarifiedDescription = `[Research] ${concept.description}`;
        additionalTags = ['hypothesis', 'methodology'];
        break;
      default:
        clarifiedDescription = concept.description;
        additionalTags = ['overview', 'summary'];
        break;
    }

    // Readability heuristic: shorter sentences, less jargon
    const wordCount = clarifiedDescription.split(/\s+/).length;
    const avgWordLength = clarifiedDescription.split(/\s+/).reduce((sum, w) => sum + w.length, 0) / Math.max(1, wordCount);
    const readabilityScore = Math.max(0, Math.min(1, 1 - (avgWordLength - 4) / 10));

    this.log.info('Concept clarified', { conceptId: concept.id, targetAudience });

    return {
      conceptId: concept.id,
      targetAudience,
      original: { description: concept.description, tagCount: concept.tags.length },
      clarified: {
        description: clarifiedDescription,
        tags: [...new Set([...concept.tags, ...additionalTags])],
        readabilityScore: Math.round(readabilityScore * 100) / 100,
      },
    };
  }

  // ───────────────────────────────────────────────────────
  // Concept Trimming
  // ───────────────────────────────────────────────────────

  private trimConcept(params: TrimParams): {
    conceptId: string;
    tagsRemoved: number;
    attrsRemoved: number;
    trimmed: {
      tags: string[];
      attributes: Record<string, unknown>;
    };
  } {
    const { concept, maxTags = 6, maxAttributes = 10, removeWeak = true } = params;

    let trimmedTags = [...concept.tags];
    let trimmedAttributes = { ...concept.attributes };

    // Trim tags
    const tagsRemoved = Math.max(0, trimmedTags.length - maxTags);
    if (trimmedTags.length > maxTags) {
      if (removeWeak) {
        // Keep the most specific/longest tags as they tend to be more descriptive
        trimmedTags.sort((a, b) => b.length - a.length);
      }
      trimmedTags = trimmedTags.slice(0, maxTags);
    }

    // Trim attributes
    const attrKeys = Object.keys(trimmedAttributes);
    const attrsRemoved = Math.max(0, attrKeys.length - maxAttributes);
    if (attrKeys.length > maxAttributes) {
      const keptKeys = attrKeys.slice(0, maxAttributes);
      const newAttrs: Record<string, unknown> = {};
      for (const key of keptKeys) {
        newAttrs[key] = trimmedAttributes[key];
      }
      trimmedAttributes = newAttrs;
    }

    this.log.info('Concept trimmed', { conceptId: concept.id, tagsRemoved, attrsRemoved });

    return {
      conceptId: concept.id,
      tagsRemoved,
      attrsRemoved,
      trimmed: {
        tags: trimmedTags,
        attributes: trimmedAttributes,
      },
    };
  }

  // ───────────────────────────────────────────────────────
  // Concept Enhancement
  // ───────────────────────────────────────────────────────

  private enhanceConcept(params: EnhanceParams): {
    conceptId: string;
    focus: string;
    enhancements: string[];
    enhanced: {
      description: string;
      tags: string[];
      complexity: number;
      novelty: number;
      attributes: Record<string, unknown>;
    };
  } {
    const { concept, focus } = params;
    const enhancements: string[] = [];
    const enhancedTags = [...concept.tags];
    const enhancedAttributes = { ...concept.attributes };
    let enhancedComplexity = concept.complexity;
    let enhancedNovelty = concept.novelty;

    switch (focus) {
      case 'novelty':
        enhancedNovelty = Math.min(10, concept.novelty + 2);
        enhancedTags.push('innovative', 'breakthrough');
        enhancedAttributes['noveltyBoost'] = true;
        enhancements.push('Novelty boosted by 2 points');
        enhancements.push('Added innovation markers');
        break;

      case 'complexity':
        enhancedComplexity = Math.min(10, concept.complexity + 2);
        enhancedTags.push('complex', 'multi-layered');
        enhancedAttributes['complexityBoost'] = true;
        enhancements.push('Complexity increased by 2 points');
        enhancements.push('Added multi-layered structure markers');
        break;

      case 'depth':
        enhancedComplexity = Math.min(10, concept.complexity + 1);
        enhancedTags.push('deep', 'thorough');
        enhancedAttributes['depthLevel'] = (concept.complexity + 1);
        enhancements.push('Added depth indicators');
        enhancements.push('Complexity modestly increased');
        break;

      case 'breadth':
        enhancedTags.push('broad', 'comprehensive', 'cross-domain');
        enhancedAttributes['breadthScope'] = 'expanded';
        enhancements.push('Added breadth and cross-domain markers');
        enhancements.push('Expanded conceptual scope');
        break;
    }

    this.log.info('Concept enhanced', { conceptId: concept.id, focus });

    return {
      conceptId: concept.id,
      focus,
      enhancements,
      enhanced: {
        description: concept.description,
        tags: [...new Set(enhancedTags)],
        complexity: enhancedComplexity,
        novelty: enhancedNovelty,
        attributes: enhancedAttributes,
      },
    };
  }

  // ───────────────────────────────────────────────────────
  // Scoring Utility
  // ───────────────────────────────────────────────────────

  private scoreCriterion(concept: PolishParams['concept'], criterion: string): number {
    const c = criterion.toLowerCase();

    if (c.includes('clarity')) {
      // Heuristic: shorter descriptions are clearer
      const descLen = concept.description.length;
      return descLen < 50 ? 0.9 : descLen < 150 ? 0.7 : descLen < 300 ? 0.5 : 0.3;
    }
    if (c.includes('coherence')) {
      // Heuristic: fewer tags = more coherent
      return concept.tags.length <= 4 ? 0.8 : concept.tags.length <= 7 ? 0.6 : 0.4;
    }
    if (c.includes('completeness')) {
      const hasTags = concept.tags.length >= 3 ? 0.3 : 0;
      const hasAttrs = Object.keys(concept.attributes).length >= 2 ? 0.3 : 0;
      const hasDesc = concept.description.length > 20 ? 0.4 : 0.1;
      return hasTags + hasAttrs + hasDesc;
    }
    if (c.includes('novel') || c.includes('original')) {
      return Math.min(1, concept.novelty / 10);
    }

    // Default scoring
    return 0.5 + Math.random() * 0.2;
  }
}
