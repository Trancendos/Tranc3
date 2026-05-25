/**
 * WelderBot — Concept Joining Bot for Imaginarium
 *
 * Identity:  NID-IMAGINARIUM-WELDER
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    ImaginariumAI (AID-IMAGINARIUM)
 *
 * Responsibilities:
 *   - Weld (join) two concepts at a specified join point
 *   - Fuse concepts along shared dimensions
 *   - Bridge concepts with connecting elements
 *   - Test the strength of a weld between concepts
 */

import { Bot, Logger } from '../../../core/definitions';

// ───────────────────────────────────────────────────────
// Domain Types
// ───────────────────────────────────────────────────────

export interface WeldParams {
  operation: 'WELD';
  conceptA: {
    id: string;
    name: string;
    description: string;
    tags: string[];
    domain: string;
    attributes: Record<string, unknown>;
  };
  conceptB: {
    id: string;
    name: string;
    description: string;
    tags: string[];
    domain: string;
    attributes: Record<string, unknown>;
  };
  joinPoint: string; // description of where/how to join
}

export interface BridgeParams {
  operation: 'BRIDGE';
  conceptA: {
    id: string;
    name: string;
    tags: string[];
    attributes: Record<string, unknown>;
  };
  conceptB: {
    id: string;
    name: string;
    tags: string[];
    attributes: Record<string, unknown>;
  };
  bridgeType: 'sequential' | 'causal' | 'analogical' | 'complementary';
}

export interface StrengthParams {
  operation: 'STRENGTH';
  weldResult: {
    conceptAName: string;
    conceptBName: string;
    sharedTags: string[];
    mergedAttributes: Record<string, unknown>;
  };
}

export type WelderInput = WeldParams | BridgeParams | StrengthParams;

// ───────────────────────────────────────────────────────
// WelderBot Implementation
// ───────────────────────────────────────────────────────

export class WelderBot extends Bot {
  private readonly log: Logger;

  constructor() {
    const handler = async (input: WelderInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-IMAGINARIUM-WELDER',
      'Welder',
      handler,
      'Concept welding, bridging, and weld strength testing'
    );

    this.log = new Logger('WelderBot');
  }

  private async process(input: WelderInput): Promise<unknown> {
    switch (input.operation) {
      case 'WELD':
        return this.weldConcepts(input);
      case 'BRIDGE':
        return this.bridgeConcepts(input);
      case 'STRENGTH':
        return this.testStrength(input);
      default:
        throw new Error(`Unknown welder operation: ${(input as WelderInput).operation}`);
    }
  }

  // ───────────────────────────────────────────────────────
  // Concept Welding
  // ───────────────────────────────────────────────────────

  private weldConcepts(params: WeldParams): {
    name: string;
    description: string;
    tags: string[];
    domain: string;
    attributes: Record<string, unknown>;
    sharedTags: string[];
    weldPoint: string;
    strength: number;
  } {
    const { conceptA, conceptB, joinPoint } = params;

    // Find shared tags
    const sharedTags = conceptA.tags.filter((t) => conceptB.tags.includes(t));
    const combinedTags = [...new Set([...conceptA.tags, ...conceptB.tags])];

    // Merge attributes — shared keys get averaged (numeric) or combined
    const mergedAttributes: Record<string, unknown> = {};
    const allKeys = new Set([...Object.keys(conceptA.attributes), ...Object.keys(conceptB.attributes)]);

    for (const key of allKeys) {
      const valA = conceptA.attributes[key];
      const valB = conceptB.attributes[key];

      if (valA !== undefined && valB !== undefined) {
        if (typeof valA === 'number' && typeof valB === 'number') {
          mergedAttributes[key] = Math.round(((valA + valB) / 2) * 100) / 100;
        } else {
          mergedAttributes[key] = `${valA} + ${valB}`;
        }
      } else {
        mergedAttributes[key] = valA ?? valB;
      }
    }

    mergedAttributes['weldPoint'] = joinPoint;
    mergedAttributes['sourceA'] = conceptA.name;
    mergedAttributes['sourceB'] = conceptB.name;

    // Weld strength based on shared ground
    const tagOverlap = sharedTags.length / Math.max(1, combinedTags.length);
    const attrOverlap = [...Object.keys(conceptA.attributes)].filter((k) => conceptB.attributes[k] !== undefined).length
      / Math.max(1, allKeys.size);
    const domainMatch = conceptA.domain === conceptB.domain ? 0.3 : 0;
    const strength = Math.min(1, tagOverlap * 0.4 + attrOverlap * 0.3 + domainMatch);

    const name = `${conceptA.name}⇌${conceptB.name}`;

    this.log.info('Concepts welded', {
      conceptA: conceptA.name,
      conceptB: conceptB.name,
      joinPoint,
      sharedTags: sharedTags.length,
      strength: strength.toFixed(2),
    });

    return {
      name,
      description: `Welded at "${joinPoint}": ${conceptA.description} | ${conceptB.description}`,
      tags: combinedTags,
      domain: conceptA.domain === conceptB.domain ? conceptA.domain : 'hybrid',
      attributes: mergedAttributes,
      sharedTags,
      weldPoint: joinPoint,
      strength: Math.round(strength * 100) / 100,
    };
  }

  // ───────────────────────────────────────────────────────
  // Concept Bridging
  // ───────────────────────────────────────────────────────

  private bridgeConcepts(params: BridgeParams): {
    bridgeType: string;
    conceptA: string;
    conceptB: string;
    bridge: {
      name: string;
      description: string;
      connectingTags: string[];
      connectingAttributes: Record<string, unknown>;
    };
    bridgeStrength: number;
  } {
    const { conceptA, conceptB, bridgeType } = params;

    // Find potential connecting elements
    const tagsA = new Set(conceptA.tags);
    const tagsB = new Set(conceptB.tags);
    const sharedTags = [...tagsA].filter((t) => tagsB.has(t));

    // Generate bridge-specific connecting tags
    let connectingTags: string[];
    let description: string;

    switch (bridgeType) {
      case 'sequential':
        connectingTags = [...sharedTags, 'then', 'sequence', 'flow'];
        description = `Sequential bridge: ${conceptA.name} leads to ${conceptB.name}`;
        break;
      case 'causal':
        connectingTags = [...sharedTags, 'because', 'therefore', 'cause', 'effect'];
        description = `Causal bridge: ${conceptA.name} causes ${conceptB.name}`;
        break;
      case 'analogical':
        connectingTags = [...sharedTags, 'like', 'similar', 'analogy', 'parallel'];
        description = `Analogical bridge: ${conceptA.name} is like ${conceptB.name}`;
        break;
      case 'complementary':
        connectingTags = [...sharedTags, 'and', 'complement', 'together', 'synergy'];
        description = `Complementary bridge: ${conceptA.name} complements ${conceptB.name}`;
        break;
    }

    // Bridge attributes combine key aspects from both sides
    const connectingAttributes: Record<string, unknown> = {
      bridgeType,
      from: conceptA.name,
      to: conceptB.name,
      sharedTagCount: sharedTags.length,
    };

    // Take one attribute from each side for the bridge
    const keysA = Object.keys(conceptA.attributes);
    const keysB = Object.keys(conceptB.attributes);
    if (keysA.length > 0) connectingAttributes[`from_${keysA[0]}`] = conceptA.attributes[keysA[0]];
    if (keysB.length > 0) connectingAttributes[`to_${keysB[0]}`] = conceptB.attributes[keysB[0]];

    const bridgeStrength = Math.min(1, (sharedTags.length * 0.2) + (bridgeType === 'complementary' ? 0.3 : 0.1));

    this.log.info('Concepts bridged', { bridgeType, strength: bridgeStrength.toFixed(2) });

    return {
      bridgeType,
      conceptA: conceptA.name,
      conceptB: conceptB.name,
      bridge: {
        name: `Bridge-${bridgeType}-${Date.now().toString(36)}`,
        description,
        connectingTags: [...new Set(connectingTags)],
        connectingAttributes,
      },
      bridgeStrength: Math.round(bridgeStrength * 100) / 100,
    };
  }

  // ───────────────────────────────────────────────────────
  // Weld Strength Testing
  // ───────────────────────────────────────────────────────

  private testStrength(params: StrengthParams): {
    overallStrength: number;
    tagBond: number;
    attributeBond: number;
    semanticBond: number;
    verdict: 'strong' | 'moderate' | 'weak' | 'fragile';
    recommendations: string[];
  } {
    const { weldResult } = params;

    // Tag bond: shared tags vs total
    const tagBond = weldResult.sharedTags.length > 0
      ? Math.min(1, weldResult.sharedTags.length / 3)
      : 0;

    // Attribute bond: number of merged attributes
    const attrCount = Object.keys(weldResult.mergedAttributes).length;
    const attributeBond = Math.min(1, attrCount / 8);

    // Semantic bond: heuristic based on attribute consistency
    const numericValues = Object.values(weldResult.mergedAttributes)
      .filter((v) => typeof v === 'number') as number[];
    const semanticBond = numericValues.length > 0
      ? Math.min(1, 1 - Math.abs(numericValues[0] - numericValues[numericValues.length - 1]) / 20)
      : 0.3;

    const overallStrength = Math.round((tagBond * 0.4 + attributeBond * 0.35 + semanticBond * 0.25) * 100) / 100;

    let verdict: 'strong' | 'moderate' | 'weak' | 'fragile';
    if (overallStrength >= 0.7) verdict = 'strong';
    else if (overallStrength >= 0.5) verdict = 'moderate';
    else if (overallStrength >= 0.3) verdict = 'weak';
    else verdict = 'fragile';

    const recommendations: string[] = [];
    if (tagBond < 0.3) recommendations.push('Add shared tags to strengthen the bond');
    if (attributeBond < 0.3) recommendations.push('Add more common attributes for a stronger weld');
    if (semanticBond < 0.3) recommendations.push('Align attribute values for better semantic coherence');

    this.log.info('Weld strength tested', { overallStrength, verdict });

    return {
      overallStrength,
      tagBond: Math.round(tagBond * 100) / 100,
      attributeBond: Math.round(attributeBond * 100) / 100,
      semanticBond: Math.round(semanticBond * 100) / 100,
      verdict,
      recommendations,
    };
  }
}
