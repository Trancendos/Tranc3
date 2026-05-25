/**
 * ArchitectAgent — Structural Design Agent for Imaginarium
 *
 * Identity:  SID-IMAGINARIUM-ARCHITECT
 * Tier:      4 (Autonomous Microservice)
 * Parent:    ImaginariumAI (AID-IMAGINARIUM)
 *
 * Responsibilities:
 *   - Design structural frameworks for concepts
 *   - Scaffold: create a skeleton/outline structure
 *   - Reinforce: strengthen weak points in concept structure
 *   - Expand: elaborate on concept dimensions
 *   - Compose: arrange multiple concepts into a coherent whole
 */

import { Agent, Bot, Logger } from '../../../core/definitions';

// ───────────────────────────────────────────────────────
// Domain Types
// ───────────────────────────────────────────────────────

export interface ArchitectInput {
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
  structureType: string;
}

export interface StructuralNode {
  id: string;
  label: string;
  type: 'root' | 'branch' | 'leaf' | 'connector';
  children: StructuralNode[];
  attributes: Record<string, unknown>;
  weight: number; // importance 0..1
}

export interface ArchitectResult {
  operation: string;
  input: { conceptId: string; conceptName: string };
  structure: StructuralNode;
  nodeCount: number;
  depth: number;
  balanceScore: number;     // how well-balanced the structure is 0..1
  completeness: number;    // how complete the structure is 0..1
  recommendations: string[];
}

// ───────────────────────────────────────────────────────
// ArchitectAgent Implementation
// ───────────────────────────────────────────────────────

export class ArchitectAgent extends Agent {
  private readonly log: Logger;

  constructor() {
    super('SID-IMAGINARIUM-ARCHITECT');
    this.log = new Logger('ArchitectAgent');
  }

  async perceive(observation: ArchitectInput): Promise<{
    concept: ArchitectInput['concept'];
    structureKind: string;
    depthHint: number;
  }> {
    const { concept, structureType } = observation;
    const sLower = structureType.toLowerCase();

    let structureKind = 'scaffold';
    if (sLower.includes('reinforce') || sLower.includes('strengthen') || sLower.includes('fortify')) {
      structureKind = 'reinforce';
    } else if (sLower.includes('expand') || sLower.includes('elaborate') || sLower.includes('grow')) {
      structureKind = 'expand';
    } else if (sLower.includes('compose') || sLower.includes('arrange') || sLower.includes('assemble')) {
      structureKind = 'compose';
    }

    // Estimate depth from complexity
    const depthHint = Math.max(2, Math.min(5, Math.ceil(concept.complexity / 2)));

    this.log.info('Perceived structure request', { conceptId: concept.id, structureKind, depthHint });

    return { concept, structureKind, depthHint };
  }

  async decide(perceived: Awaited<ReturnType<typeof this.perceive>>): Promise<{
    action: string;
    params: Record<string, unknown>;
  }> {
    const { structureKind, depthHint, concept } = perceived;

    this.log.info('Decided on architectural action', { structureKind, depthHint });

    return {
      action: structureKind,
      params: { concept, depthHint },
    };
  }

  async act(decision: Awaited<ReturnType<typeof this.decide>>): Promise<ArchitectResult> {
    const { action, params } = decision;
    const concept = params.concept as ArchitectInput['concept'];
    const depthHint = params.depthHint as number;

    let result: ArchitectResult;

    switch (action) {
      case 'reinforce':
        result = this.reinforce(concept, depthHint);
        break;
      case 'expand':
        result = this.expand(concept, depthHint);
        break;
      case 'compose':
        result = this.compose(concept, depthHint);
        break;
      default:
        result = this.scaffold(concept, depthHint);
        break;
    }

    this.log.info('Architectural operation complete', {
      operation: result.operation,
      nodeCount: result.nodeCount,
      depth: result.depth,
      balanceScore: result.balanceScore.toFixed(2),
    });

    return result;
  }

  // ───────────────────────────────────────────────────────
  // Architectural Operations
  // ───────────────────────────────────────────────────────

  private scaffold(concept: ArchitectInput['concept'], depth: number): ArchitectResult {
    // Create a hierarchical skeleton based on concept tags and attributes
    const root: StructuralNode = {
      id: `NODE-${concept.id}-ROOT`,
      label: concept.name,
      type: 'root',
      children: [],
      attributes: { domain: concept.domain },
      weight: 1.0,
    };

    // Create branches from tags
    for (let i = 0; i < concept.tags.length; i++) {
      const tag = concept.tags[i];
      const branch: StructuralNode = {
        id: `NODE-${concept.id}-B${i}`,
        label: tag.charAt(0).toUpperCase() + tag.slice(1),
        type: 'branch',
        children: [],
        attributes: { tag, index: i },
        weight: 0.7,
      };

      // Add leaf nodes for depth
      if (depth > 2) {
        const leafCount = Math.min(3, depth);
        for (let j = 0; j < leafCount; j++) {
          branch.children.push({
            id: `NODE-${concept.id}-B${i}-L${j}`,
            label: `${tag} aspect ${j + 1}`,
            type: 'leaf',
            children: [],
            attributes: { aspectIndex: j },
            weight: 0.4,
          });
        }
      }

      root.children.push(branch);
    }

    // Add attribute branches
    const attrKeys = Object.keys(concept.attributes);
    if (attrKeys.length > 0) {
      const attrBranch: StructuralNode = {
        id: `NODE-${concept.id}-ATTRS`,
        label: 'Attributes',
        type: 'branch',
        children: attrKeys.map((key, idx) => ({
          id: `NODE-${concept.id}-A${idx}`,
          label: key,
          type: 'leaf' as const,
          children: [] as StructuralNode[],
          attributes: { value: concept.attributes[key] },
          weight: 0.3,
        })),
        attributes: { count: attrKeys.length },
        weight: 0.5,
      };
      root.children.push(attrBranch);
    }

    const nodeCount = this.countNodes(root);
    const actualDepth = this.measureDepth(root);
    const balanceScore = this.computeBalance(root);

    return {
      operation: 'scaffold',
      input: { conceptId: concept.id, conceptName: concept.name },
      structure: root,
      nodeCount,
      depth: actualDepth,
      balanceScore,
      completeness: Math.min(1, concept.tags.length / 5),
      recommendations: concept.tags.length < 3 ? ['Add more tags for richer scaffolding'] : [],
    };
  }

  private reinforce(concept: ArchitectInput['concept'], depth: number): ArchitectResult {
    // Build a scaffold then add connector nodes for reinforcement
    const base = this.scaffold(concept, depth);

    // Add cross-links as connector nodes between branches
    const branches = base.structure.children.filter((n) => n.type === 'branch');
    for (let i = 0; i < branches.length - 1; i++) {
      const connector: StructuralNode = {
        id: `NODE-${concept.id}-CONN${i}`,
        label: `${branches[i].label} ↔ ${branches[i + 1].label}`,
        type: 'connector',
        children: [],
        attributes: { connects: [branches[i].id, branches[i + 1].id] },
        weight: 0.6,
      };
      base.structure.children.push(connector);
    }

    const nodeCount = this.countNodes(base.structure);
    const balanceScore = this.computeBalance(base.structure);

    return {
      operation: 'reinforce',
      input: { conceptId: concept.id, conceptName: concept.name },
      structure: base.structure,
      nodeCount,
      depth: base.depth,
      balanceScore: Math.min(1, balanceScore + 0.15),
      completeness: Math.min(1, base.completeness + 0.2),
      recommendations: ['Cross-links added for structural reinforcement'],
    };
  }

  private expand(concept: ArchitectInput['concept'], depth: number): ArchitectResult {
    // Expand each branch with more granular leaves
    const base = this.scaffold(concept, depth + 1);

    // For each branch, expand leaves further
    for (const branch of base.structure.children) {
      if (branch.type === 'branch') {
        for (const leaf of branch.children) {
          if (leaf.type === 'leaf') {
            // Add sub-leaves
            for (let i = 0; i < 2; i++) {
              leaf.children.push({
                id: `${leaf.id}-SUB${i}`,
                label: `${leaf.label} detail ${i + 1}`,
                type: 'leaf',
                children: [],
                attributes: { expandedFrom: leaf.id, detailIndex: i },
                weight: 0.2,
              });
            }
          }
        }
      }
    }

    const nodeCount = this.countNodes(base.structure);
    const actualDepth = this.measureDepth(base.structure);
    const balanceScore = this.computeBalance(base.structure);

    return {
      operation: 'expand',
      input: { conceptId: concept.id, conceptName: concept.name },
      structure: base.structure,
      nodeCount,
      depth: actualDepth,
      balanceScore,
      completeness: Math.min(1, base.completeness + 0.3),
      recommendations: ['Structure expanded with additional detail nodes'],
    };
  }

  private compose(concept: ArchitectInput['concept'], depth: number): ArchitectResult {
    // Compose a multi-layer structure: overview → details → specifics
    const root: StructuralNode = {
      id: `NODE-${concept.id}-COMPOSE`,
      label: `${concept.name} Composition`,
      type: 'root',
      children: [
        {
          id: `NODE-${concept.id}-OVERVIEW`,
          label: 'Overview',
          type: 'branch',
          children: [{
            id: `NODE-${concept.id}-SUMMARY`,
            label: concept.description.slice(0, 60),
            type: 'leaf',
            children: [],
            attributes: { fullDescription: concept.description },
            weight: 0.8,
          }],
          attributes: { layer: 'overview' },
          weight: 0.9,
        },
        {
          id: `NODE-${concept.id}-DETAILS`,
          label: 'Key Aspects',
          type: 'branch',
          children: concept.tags.map((tag, idx) => ({
            id: `NODE-${concept.id}-ASPECT${idx}`,
            label: tag,
            type: 'leaf' as const,
            children: [] as StructuralNode[],
            attributes: { tag },
            weight: 0.6,
          })),
          attributes: { layer: 'details', aspectCount: concept.tags.length },
          weight: 0.7,
        },
        {
          id: `NODE-${concept.id}-SPECIFICS`,
          label: 'Specifics',
          type: 'branch',
          children: Object.entries(concept.attributes).map(([key, value], idx) => ({
            id: `NODE-${concept.id}-SPEC${idx}`,
            label: `${key}: ${String(value).slice(0, 30)}`,
            type: 'leaf' as const,
            children: [] as StructuralNode[],
            attributes: { key, value },
            weight: 0.4,
          })),
          attributes: { layer: 'specifics', attributeCount: Object.keys(concept.attributes).length },
          weight: 0.5,
        },
      ],
      attributes: { domain: concept.domain, compositionType: 'layered' },
      weight: 1.0,
    };

    const nodeCount = this.countNodes(root);
    const actualDepth = this.measureDepth(root);
    const balanceScore = this.computeBalance(root);

    return {
      operation: 'compose',
      input: { conceptId: concept.id, conceptName: concept.name },
      structure: root,
      nodeCount,
      depth: actualDepth,
      balanceScore,
      completeness: Math.min(1, concept.tags.length / 3 + 0.3),
      recommendations: ['Layered composition created: overview → details → specifics'],
    };
  }

  // ───────────────────────────────────────────────────────
  // Tree Utilities
  // ───────────────────────────────────────────────────────

  private countNodes(node: StructuralNode): number {
    let count = 1;
    for (const child of node.children) {
      count += this.countNodes(child);
    }
    return count;
  }

  private measureDepth(node: StructuralNode): number {
    if (node.children.length === 0) return 1;
    return 1 + Math.max(...node.children.map((c) => this.measureDepth(c)));
  }

  private computeBalance(node: StructuralNode): number {
    if (node.children.length <= 1) return 1;

    const childDepths = node.children.map((c) => this.measureDepth(c));
    const maxDepth = Math.max(...childDepths);
    const minDepth = Math.min(...childDepths);

    // Perfect balance = all children same depth
    const depthBalance = maxDepth === 0 ? 1 : 1 - (maxDepth - minDepth) / maxDepth;

    // Child count balance (even distribution)
    const childCounts = node.children.map((c) => this.countNodes(c));
    const avgCount = childCounts.reduce((a, b) => a + b, 0) / childCounts.length;
    const countVariance = childCounts.reduce((sum, c) => sum + Math.pow(c - avgCount, 2), 0) / childCounts.length;
    const countBalance = avgCount === 0 ? 1 : Math.max(0, 1 - Math.sqrt(countVariance) / avgCount);

    // Weighted average of subtree balances
    const childBalances = node.children.map((c) => this.computeBalance(c));
    const avgChildBalance = childBalances.reduce((a, b) => a + b, 0) / childBalances.length;

    return Math.round((depthBalance * 0.3 + countBalance * 0.3 + avgChildBalance * 0.4) * 100) / 100;
  }
}
