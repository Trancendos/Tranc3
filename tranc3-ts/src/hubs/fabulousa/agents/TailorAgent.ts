/**
 * TailorAgent — Style Tailoring Agent for Fabulousa
 *
 * Identity:  SID-FABULOUSSA-TAILOR
 * Tier:      4 (Autonomous Microservice)
 * Parent:    FabulousaAI (AID-FABULOUSSA)
 *
 * Responsibilities:
 *   - Tailor design tokens to specific component requirements
 *   - Apply design constraints (accessibility, brand compliance)
 *   - Generate component-specific style variants
 *   - Ensure color contrast compliance (WCAG)
 *   - Adapt styles for different themes (light/dark/high-contrast)
 *   - Optimize style declarations for performance
 */

import { Agent, Logger, AuditLedger } from '../../../core/definitions';

// ───────────────────────────────────────────
// Domain Types
// ───────────────────────────────────────────

export interface TailorInput {
  designSystem: {
    id: string;
    colors: Array<{ name: string; value: string; variant: string; usage: string }>;
    typography: {
      baseFontSize: number;
      scaleRatio: number;
      fontFamilies: Array<{ name: string; category: string }>;
    };
    spacing: { baseUnit: number; steps: Record<string, number> };
  };
  requirements: Record<string, unknown>;
}

export interface ContrastCheckResult {
  foreground: string;
  background: string;
  ratio: number;
  aa: boolean;
  aaa: boolean;
  aaLarge: boolean;
  aaaLarge: boolean;
}

export interface ThemeAdaptation {
  theme: 'light' | 'dark' | 'high-contrast';
  colorMappings: Array<{ original: string; adapted: string; token: string }>;
  inversions: string[];
  adjustments: string[];
}

export interface TailoredStyleSet {
  component: string;
  base: Record<string, string>;
  variants: Record<string, Record<string, string>>;
  themes: Record<string, Record<string, string>>;
  contrastChecks: ContrastCheckResult[];
  warnings: string[];
}

type TailorDecision =
  | 'GENERATE_VARIANTS'
  | 'CHECK_CONTRAST'
  | 'ADAPT_THEME'
  | 'OPTIMIZE_DECLARATIONS'
  | 'APPLY_CONSTRAINTS';

// ───────────────────────────────────────────
// TailorAgent Implementation
// ───────────────────────────────────────────

export class TailorAgent extends Agent {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private tailoredStyles: Map<string, TailoredStyleSet>;

  constructor() {
    super(
      'SID-FABULOUSSA-TAILOR',
      'TailorAgent',
      'Fabulousa'
    );

    this.log = new Logger('TailorAgent');
    this.audit = AuditLedger.getInstance();
    this.tailoredStyles = new Map();

    this.registerTool('generateVariants', this.generateVariants.bind(this));
    this.registerTool('checkContrast', this.checkContrast.bind(this));
    this.registerTool('adaptTheme', this.adaptTheme.bind(this));
    this.registerTool('optimizeDeclarations', this.optimizeDeclarations.bind(this));

    this.log.info('TailorAgent initialised');
  }

  // ───────────────────────────────────────
  // Abstract Implementations
  // ───────────────────────────────────────

  protected async perceive(input: unknown): Promise<unknown> {
    const { designSystem, requirements } = input as TailorInput;

    const perception = {
      designSystemId: designSystem.id,
      colorCount: designSystem.colors.length,
      fontFamilyCount: designSystem.typography.fontFamilies.length,
      spacingSteps: Object.keys(designSystem.spacing.steps).length,
      requirements,
      requirementKeys: Object.keys(requirements),
    };

    this.memory.push(perception);
    return perception;
  }

  protected async decide(perception: unknown): Promise<TailorDecision> {
    const p = perception as { requirementKeys: string[] };

    if (p.requirementKeys.includes('variant') || p.requirementKeys.includes('variants')) {
      return 'GENERATE_VARIANTS';
    }
    if (p.requirementKeys.includes('contrast') || p.requirementKeys.includes('accessibility')) {
      return 'CHECK_CONTRAST';
    }
    if (p.requirementKeys.includes('theme') || p.requirementKeys.includes('darkMode')) {
      return 'ADAPT_THEME';
    }
    if (p.requirementKeys.includes('optimize') || p.requirementKeys.includes('performance')) {
      return 'OPTIMIZE_DECLARATIONS';
    }

    return 'APPLY_CONSTRAINTS';
  }

  protected async act(decision: TailorDecision, perception: unknown): Promise<TailoredStyleSet> {
    const p = perception as TailorInput;
    this.log.info('Tailor acting on decision', { decision, designSystemId: p.designSystem.id });

    const component = (p.requirements.component as string) ?? 'generic';
    const warnings: string[] = [];
    const contrastChecks: ContrastCheckResult[] = [];

    let base: Record<string, string> = {};
    let variants: Record<string, Record<string, string>> = {};
    let themes: Record<string, Record<string, string>> = {};

    switch (decision) {
      case 'GENERATE_VARIANTS': {
        variants = this.generateVariants(p.designSystem, p.requirements);
        base = this.buildBaseStyles(p.designSystem);
        break;
      }
      case 'CHECK_CONTRAST': {
        base = this.buildBaseStyles(p.designSystem);
        for (const color of p.designSystem.colors) {
          if (color.usage.includes('text') || color.usage.includes('Text')) {
            const check = this.checkContrast(color.value, '#FFFFFF');
            contrastChecks.push(check);
            const checkDark = this.checkContrast(color.value, '#1F2937');
            contrastChecks.push(checkDark);
          }
        }
        break;
      }
      case 'ADAPT_THEME': {
        base = this.buildBaseStyles(p.designSystem);
        const lightAdapt = this.adaptTheme(p.designSystem, 'light');
        const darkAdapt = this.adaptTheme(p.designSystem, 'dark');
        const hcAdapt = this.adaptTheme(p.designSystem, 'high-contrast');
        themes = {
          light: this.themeToStyles(lightAdapt),
          dark: this.themeToStyles(darkAdapt),
          'high-contrast': this.themeToStyles(hcAdapt),
        };
        break;
      }
      case 'OPTIMIZE_DECLARATIONS': {
        base = this.buildBaseStyles(p.designSystem);
        const optimized = this.optimizeDeclarations(base);
        base = optimized;
        break;
      }
      case 'APPLY_CONSTRAINTS': {
        base = this.buildBaseStyles(p.designSystem);
        break;
      }
    }

    const result: TailoredStyleSet = {
      component,
      base,
      variants,
      themes,
      contrastChecks,
      warnings,
    };

    this.tailoredStyles.set(`${p.designSystem.id}-${component}`, result);

    this.audit.append({
      actor: this.id,
      action: 'STYLES_TAILORED',
      entity: p.designSystem.id,
      details: { decision, component, contrastCheckCount: contrastChecks.length },
      timestamp: Date.now(),
    });

    this.episodeCount++;
    return result;
  }

  // ───────────────────────────────────────
  // Tool Implementations
  // ───────────────────────────────────────

  private buildBaseStyles(ds: TailorInput['designSystem']): Record<string, string> {
    const styles: Record<string, string> = {};

    // Map colors to CSS custom properties
    for (const color of ds.colors) {
      styles[`--color-${color.name}`] = color.value;
    }

    // Map typography
    const { baseFontSize, scaleRatio } = ds.typography;
    const sizes = ['xs', 'sm', 'base', 'lg', 'xl', '2xl', '3xl', '4xl'];
    sizes.forEach((size, i) => {
      const fontSize = Math.round(baseFontSize * Math.pow(scaleRatio, i - 2) * 100) / 100;
      styles[`--font-size-${size}`] = `${fontSize}px`;
    });

    // Map spacing
    for (const [step, value] of Object.entries(ds.spacing.steps)) {
      styles[`--spacing-${step}`] = `${value}px`;
    }

    return styles;
  }

  private generateVariants(ds: TailorInput['designSystem'], requirements: Record<string, unknown>): Record<string, Record<string, string>> {
    const variants: Record<string, Record<string, string>> = {};
    const variantTypes = ['outline', 'ghost', 'link', 'subtle'];

    for (const variant of variantTypes) {
      const variantStyles: Record<string, string> = {};

      switch (variant) {
        case 'outline':
          variantStyles['border'] = `1px solid var(--color-primary)`;
          variantStyles['background'] = 'transparent';
          variantStyles['color'] = 'var(--color-primary)';
          break;
        case 'ghost':
          variantStyles['background'] = 'transparent';
          variantStyles['color'] = 'var(--color-primary)';
          variantStyles['border'] = 'none';
          break;
        case 'link':
          variantStyles['background'] = 'transparent';
          variantStyles['color'] = 'var(--color-primary)';
          variantStyles['border'] = 'none';
          variantStyles['textDecoration'] = 'underline';
          break;
        case 'subtle':
          variantStyles['background'] = 'var(--color-primary-light)';
          variantStyles['color'] = 'var(--color-primary-dark)';
          variantStyles['border'] = 'none';
          break;
      }

      variants[variant] = variantStyles;
    }

    return variants;
  }

  private checkContrast(fg: string, bg: string): ContrastCheckResult {
    const fgLuminance = this.relativeLuminance(fg);
    const bgLuminance = this.relativeLuminance(bg);

    const lighter = Math.max(fgLuminance, bgLuminance);
    const darker = Math.min(fgLuminance, bgLuminance);
    const ratio = (lighter + 0.05) / (darker + 0.05);

    return {
      foreground: fg,
      background: bg,
      ratio: Math.round(ratio * 100) / 100,
      aa: ratio >= 4.5,
      aaa: ratio >= 7,
      aaLarge: ratio >= 3,
      aaaLarge: ratio >= 4.5,
    };
  }

  private adaptTheme(ds: TailorInput['designSystem'], theme: 'light' | 'dark' | 'high-contrast'): ThemeAdaptation {
    const colorMappings: Array<{ original: string; adapted: string; token: string }> = [];
    const inversions: string[] = [];
    const adjustments: string[] = [];

    for (const color of ds.colors) {
      let adapted: string;

      switch (theme) {
        case 'dark':
          if (color.variant === 'base' && color.usage.includes('surface')) {
            adapted = '#1F2937';
            inversions.push(color.name);
          } else if (color.variant === 'base' && color.usage.includes('text')) {
            adapted = '#F9FAFB';
            inversions.push(color.name);
          } else {
            adapted = color.value;
            adjustments.push(color.name);
          }
          break;
        case 'high-contrast':
          if (color.usage.includes('text')) {
            adapted = '#000000';
          } else if (color.usage.includes('surface')) {
            adapted = '#FFFFFF';
          } else {
            adapted = color.value;
          }
          adjustments.push(color.name);
          break;
        default: // light
          adapted = color.value;
          break;
      }

      colorMappings.push({ original: color.value, adapted, token: color.name });
    }

    return { theme, colorMappings, inversions, adjustments };
  }

  private themeToStyles(adaptation: ThemeAdaptation): Record<string, string> {
    const styles: Record<string, string> = {};
    for (const mapping of adaptation.colorMappings) {
      styles[`--color-${mapping.token}`] = mapping.adapted;
    }
    return styles;
  }

  private optimizeDeclarations(styles: Record<string, string>): Record<string, string> {
    // Remove duplicate values, shorthand where possible
    const optimized = { ...styles };

    // Deduplicate values that map to the same CSS custom property
    const valueMap = new Map<string, string[]>();
    for (const [key, value] of Object.entries(optimized)) {
      if (!valueMap.has(value)) valueMap.set(value, []);
      valueMap.get(value)!.push(key);
    }

    // For duplicate values, keep only the first declaration
    const seen = new Set<string>();
    for (const [key, value] of Object.entries(optimized)) {
      if (seen.has(value) && key.startsWith('--')) {
        delete optimized[key];
      }
      seen.add(value);
    }

    return optimized;
  }

  // ───────────────────────────────────────
  // Helpers
  // ───────────────────────────────────────

  private relativeLuminance(hex: string): number {
    const rgb = this.hexToRgb(hex);
    if (!rgb) return 0;

    const [rs, gs, bs] = [rgb.r / 255, rgb.g / 255, rgb.b / 255];
    const r = rs <= 0.03928 ? rs / 12.92 : Math.pow((rs + 0.055) / 1.055, 2.4);
    const g = gs <= 0.03928 ? gs / 12.92 : Math.pow((gs + 0.055) / 1.055, 2.4);
    const b = bs <= 0.03928 ? bs / 12.92 : Math.pow((bs + 0.055) / 1.055, 2.4);

    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  }

  private hexToRgb(hex: string): { r: number; g: number; b: number } | null {
    const match = hex.replace('#', '').match(/^([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i);
    if (!match) return null;
    return { r: parseInt(match[1], 16), g: parseInt(match[2], 16), b: parseInt(match[3], 16) };
  }

  getTailoredCount(): number {
    return this.tailoredStyles.size;
  }
}
