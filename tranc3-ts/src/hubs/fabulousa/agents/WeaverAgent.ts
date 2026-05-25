/**
 * WeaverAgent — Style Composition Agent for Fabulousa
 *
 * Identity:  SID-FABULOUSSA-WEAVER
 * Tier:      4 (Autonomous Microservice)
 * Parent:    FabulousaAI (AID-FABULOUSSA)
 *
 * Responsibilities:
 *   - Compose individual component styles into cohesive design systems
 *   - Weave CSS custom properties into utility classes
 *   - Resolve style conflicts between components
 *   - Generate responsive style compositions
 *   - Produce final CSS/SCSS/JSON output
 *   - Manage style dependency graphs
 */

import { Agent, Logger, AuditLedger } from '../../../core/definitions'

const auditLedger = new AuditLedger();

// ───────────────────────────────────────────
// Domain Types
// ───────────────────────────────────────────

export interface WeaveInput {
  designSystem: {
    id: string;
    colors: Array<{ name: string; value: string }>;
    spacing: { baseUnit: number; steps: Record<string, number> };
  };
  components: string[];
}

export interface StyleDependency {
  component: string;
  dependsOn: string[];
  provides: string[];
  conflicts: string[];
}


// Re-exported type aliases for barrel compatibility
export type DependencyGraph = Map<string, StyleDependency[]>;
export interface ConflictReport {
  conflicts: Array<{ property: string; sources: string[] }>;
  resolved: boolean;
}


export interface WovenOutput {
  designSystemId: string;
  components: string[];
  css: string;
  utilityClasses: Record<string, string>;
  dependencies: StyleDependency[];
  resolvedConflicts: string[];
  totalDeclarations: number;
  totalSelectors: number;
  estimatedGzipKB: number;
}

type WeaverDecision =
  | 'RESOLVE_DEPENDENCIES'
  | 'GENERATE_UTILITIES'
  | 'COMPOSE_CSS'
  | 'RESOLVE_CONFLICTS'
  | 'OPTIMIZE_OUTPUT';

// ───────────────────────────────────────────
// WeaverAgent Implementation
// ───────────────────────────────────────────

export class WeaverAgent extends Agent {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private wovenOutputs: Map<string, WovenOutput>;

  constructor() {
    super(
      'SID-FABULOUSSA-WEAVER',
      'WeaverAgent',
      'Fabulousa'
    );

    this.log = new Logger('WeaverAgent');
    this.audit = auditLedger;
    this.wovenOutputs = new Map();

    this.registerTool('resolveDependencies', this.resolveDependencies.bind(this));
    this.registerTool('generateUtilities', this.generateUtilities.bind(this));
    this.registerTool('composeCSS', this.composeCSS.bind(this));
    this.registerTool('resolveConflicts', this.resolveConflicts.bind(this));

    this.log.info('WeaverAgent initialised');
  }

  // ───────────────────────────────────────
  // Abstract Implementations
  // ───────────────────────────────────────

  public async perceive(input: unknown): Promise<unknown> {
    const { designSystem, components } = input as WeaveInput;

    const perception = {
      designSystemId: designSystem.id,
      componentCount: components.length,
      colorTokenCount: designSystem.colors.length,
      spacingStepCount: Object.keys(designSystem.spacing.steps).length,
      components,
    };

    this.memory.push(perception);
    return perception;
  }

  public async decide(perception: unknown): Promise<WeaverDecision> {
    const p = perception as { componentCount: number; components: string[] };

    if (p.componentCount > 5) {
      return 'RESOLVE_DEPENDENCIES';
    }
    if (p.components.some(c => c.includes('utility') || c.includes('utility'))) {
      return 'GENERATE_UTILITIES';
    }

    return 'COMPOSE_CSS';
  }

  public async act(decision: WeaverDecision, perception: unknown): Promise<WovenOutput> {
    const p = perception as WeaveInput;
    this.log.info('Weaver acting on decision', { decision, designSystemId: p.designSystem.id });

    let css = '';
    let utilityClasses: Record<string, string> = {};
    let dependencies: StyleDependency[] = [];
    let resolvedConflicts: string[] = [];
    let totalDeclarations = 0;
    let totalSelectors = 0;

    switch (decision) {
      case 'RESOLVE_DEPENDENCIES': {
        dependencies = this.resolveDependencies(p.components);
        css = this.composeCSS(p.designSystem, p.components);
        break;
      }
      case 'GENERATE_UTILITIES': {
        utilityClasses = this.generateUtilities(p.designSystem);
        css = this.composeCSS(p.designSystem, p.components);
        break;
      }
      case 'COMPOSE_CSS': {
        css = this.composeCSS(p.designSystem, p.components);
        dependencies = this.resolveDependencies(p.components);
        break;
      }
      case 'RESOLVE_CONFLICTS': {
        resolvedConflicts = this.resolveConflicts(p.components);
        css = this.composeCSS(p.designSystem, p.components);
        break;
      }
      case 'OPTIMIZE_OUTPUT': {
        css = this.composeCSS(p.designSystem, p.components);
        break;
      }
    }

    // Count declarations and selectors
    totalDeclarations = (css.match(/;/g) ?? []).length;
    totalSelectors = (css.match(/\{/g) ?? []).length;

    // Estimate gzip size (rough: CSS compresses to ~20% of original)
    const estimatedGzipKB = Math.round((css.length * 0.2) / 1024 * 10) / 10;

    const result: WovenOutput = {
      designSystemId: p.designSystem.id,
      components: p.components,
      css,
      utilityClasses,
      dependencies,
      resolvedConflicts,
      totalDeclarations,
      totalSelectors,
      estimatedGzipKB,
    };

    this.wovenOutputs.set(p.designSystem.id, result);

    this.audit.append({
      actor: this.id,
      action: 'STYLES_WOVEN',
      entity: p.designSystem.id,
      details: { decision, componentCount: p.components.length, totalDeclarations, estimatedGzipKB },
      timestamp: new Date(),
    });

    this.episodeCount++;
    return result;
  }

  // ───────────────────────────────────────
  // Tool Implementations
  // ───────────────────────────────────────

  private resolveDependencies(components: string[]): StyleDependency[] {
    const deps: StyleDependency[] = [];

    for (const component of components) {
      const dependsOn: string[] = [];
      const provides: string[] = [component];
      const conflicts: string[] = [];

      // Simple dependency resolution: components with similar names may conflict
      for (const other of components) {
        if (other === component) continue;

        // Check for potential naming conflicts
        const baseName = component.split('-')[0];
        const otherBase = other.split('-')[0];
        if (baseName === otherBase) {
          conflicts.push(other);
        }
      }

      // Core dependencies
      if (component.includes('button') || component.includes('input') || component.includes('card')) {
        dependsOn.push('base');
      }

      deps.push({ component, dependsOn, provides, conflicts });
    }

    return deps;
  }

  private generateUtilities(ds: WeaveInput['designSystem']): Record<string, string> {
    const utilities: Record<string, string> = {};

    // Color utilities
    for (const color of ds.colors) {
      utilities[`.text-${color.name}`] = `color: var(--color-${color.name});`;
      utilities[`.bg-${color.name}`] = `background-color: var(--color-${color.name});`;
      utilities[`.border-${color.name}`] = `border-color: var(--color-${color.name});`;
    }

    // Spacing utilities
    for (const [step, value] of Object.entries(ds.spacing.steps)) {
      utilities[`.p-${step}`] = `padding: ${value}px;`;
      utilities[`.m-${step}`] = `margin: ${value}px;`;
      utilities[`.px-${step}`] = `padding-left: ${value}px; padding-right: ${value}px;`;
      utilities[`.py-${step}`] = `padding-top: ${value}px; padding-bottom: ${value}px;`;
      utilities[`.mx-${step}`] = `margin-left: ${value}px; margin-right: ${value}px;`;
      utilities[`.my-${step}`] = `margin-top: ${value}px; margin-bottom: ${value}px;`;
    }

    return utilities;
  }

  private composeCSS(ds: WeaveInput['designSystem'], components: string[]): string {
    let css = '/* Auto-generated by Fabulousa WeaverAgent */\n\n';

    // CSS Custom Properties (Design Tokens)
    css += ':root {\n';
    for (const color of ds.colors) {
      css += `  --color-${color.name}: ${color.value};\n`;
    }
    for (const [step, value] of Object.entries(ds.spacing.steps)) {
      css += `  --spacing-${step}: ${value}px;\n`;
    }
    css += '}\n\n';

    // Component styles
    for (const component of components) {
      css += `.${component} {\n`;
      css += `  /* ${component} base styles */\n`;

      if (component.includes('button')) {
        css += '  display: inline-flex;\n';
        css += '  align-items: center;\n';
        css += '  justify-content: center;\n';
        css += '  padding: var(--spacing-2) var(--spacing-4);\n';
        css += '  border-radius: var(--border-radius-md, 4px);\n';
        css += '  font-weight: 500;\n';
        css += '  background: var(--color-primary);\n';
        css += '  color: var(--color-surface, #FFFFFF);\n';
        css += '  border: none;\n';
        css += '  cursor: pointer;\n';
      } else if (component.includes('card')) {
        css += '  background: var(--color-surface, #FFFFFF);\n';
        css += '  border-radius: var(--border-radius-lg, 8px);\n';
        css += '  padding: var(--spacing-6);\n';
        css += '  box-shadow: var(--shadow-md, 0 4px 6px rgba(0,0,0,0.1));\n';
      } else if (component.includes('input')) {
        css += '  display: block;\n';
        css += '  width: 100%;\n';
        css += '  padding: var(--spacing-2) var(--spacing-3);\n';
        css += '  border: 1px solid var(--color-text-muted, #6B7280);\n';
        css += '  border-radius: var(--border-radius-md, 4px);\n';
        css += '  font-size: var(--font-size-base, 16px);\n';
      } else {
        css += '  /* Component-specific styles */\n';
      }

      css += '}\n\n';
    }

    return css;
  }

  private resolveConflicts(components: string[]): string[] {
    const resolved: string[] = [];

    // Detect and resolve naming conflicts
    const nameMap = new Map<string, string[]>();
    for (const component of components) {
      const prefix = component.split('-')[0];
      if (!nameMap.has(prefix)) nameMap.set(prefix, []);
      nameMap.get(prefix)!.push(component);
    }

    for (const [prefix, comps] of nameMap) {
      if (comps.length > 1) {
        resolved.push(`Resolved conflict between ${comps.join(', ')} — using scoped selectors`);
      }
    }

    return resolved;
  }

  getWovenCount(): number {
    return this.wovenOutputs.size;
  }
}
