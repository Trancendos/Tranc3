/**
 * FabulousaAI — Lead AI for the Fabulousa Hub
 *
 * Identity:  AID-FABULOUSSA
 * Pillar:    Savania
 * Tier:      3 (Lead AI / Domain Orchestrator)
 * Domain:    Design systems, styling, UI/UX, theming,
 *            typography, color management, layout composition
 *
 * Pipeline:  FontFetcher → PixelPusher → Tailor → Weaver
 *            HexCode handles color management
 *            Padding handles spacing and layout
 */

import { AI, Agent, Bot, Logger, AuditLedger } from '../../core/definitions'
import { TailorAgent } from './agents/TailorAgent';
import { WeaverAgent } from './agents/WeaverAgent';
import { PixelPusherBot } from './bots/PixelPusherBot';
import { HexCodeBot } from './bots/HexCodeBot';
import { FontFetcherBot } from './bots/FontFetcherBot';
import { PaddingBot } from './bots/PaddingBot';

const auditLedger = new AuditLedger();

// ───────────────────────────────────────────
// Domain Interfaces
// ───────────────────────────────────────────

export interface DesignSystem {
  id: string;
  name: string;
  createdAt: number;
  colors: ColorToken[];
  typography: TypographyScale;
  spacing: SpacingScale;
  breakpoints: Breakpoint[];
  shadows: ShadowToken[];
  borderRadius: BorderRadiusToken[];
  metadata: Record<string, unknown>;
}

export interface ColorToken {
  name: string;
  value: string;
  variant: 'base' | 'light' | 'dark' | 'muted' | 'bright';
  usage: string;
}

export interface TypographyScale {
  baseFontSize: number;
  scaleRatio: number;
  fontFamilies: FontFamily[];
  weights: Record<string, number>;
  lineHeights: Record<string, number>;
}

export interface FontFamily {
  name: string;
  fallbacks: string[];
  category: 'serif' | 'sans-serif' | 'monospace' | 'display' | 'handwriting';
  weights: number[];
}

export interface SpacingScale {
  baseUnit: number;
  steps: Record<string, number>;
}

export interface Breakpoint {
  name: string;
  minWidth: number;
  maxWidth?: number;
  columns: number;
  gutter: number;
}

export interface ShadowToken {
  name: string;
  value: string;
  elevation: number;
}

export interface BorderRadiusToken {
  name: string;
  value: string;
  size: 'none' | 'sm' | 'md' | 'lg' | 'xl' | 'full';
}

export interface ComponentStyle {
  id: string;
  componentName: string;
  variants: Record<string, StyleVariant>;
  states: Record<string, Record<string, string>>;
  responsive: Record<string, Record<string, string>>;
}

export interface StyleVariant {
  base: Record<string, string>;
  modifiers: Record<string, Record<string, string>>;
}

export interface ThemeExport {
  format: 'css' | 'scss' | 'json' | 'tailwind';
  designSystemId: string;
  generatedAt: number;
  sizeBytes: number;
  tokenCount: number;
}

// ───────────────────────────────────────────
// FabulousaAI Implementation
// ───────────────────────────────────────────

export class FabulousaAI extends AI {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private designSystems: Map<string, DesignSystem>;
  private componentStyles: Map<string, ComponentStyle>;

  constructor() {
    super(
      'AID-FABULOUSSA',
      'Fabulousa',
      'fabulousa',
      'Savania',
      3
    );

    this.log = new Logger('FabulousaAI');
    this.audit = auditLedger;
    this.designSystems = new Map();
    this.componentStyles = new Map();

    // Register Agents
    this.registerAgent(new TailorAgent());
    this.registerAgent(new WeaverAgent());

    // Register Bots
    this.registerBot(new PixelPusherBot());
    this.registerBot(new HexCodeBot());
    this.registerBot(new FontFetcherBot());
    this.registerBot(new PaddingBot());

    this.log.info('FabulousaAI initialised', {
      agents: this.listAgentIds(),
      bots: this.listBotNames(),
    });
  }

  // ───────────────────────────────────────
  // Design System Management
  // ───────────────────────────────────────

  /**
   * Create a new design system with default tokens.
   */
  createDesignSystem(name: string, options: { baseFontSize?: number; scaleRatio?: number; baseSpacing?: number } = {}): DesignSystem {
    const id = `DS-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`.toUpperCase();
    const { baseFontSize = 16, scaleRatio = 1.25, baseSpacing = 8 } = options;

    const designSystem: DesignSystem = {
      id,
      name,
      createdAt: Date.now(),
      colors: [
        { name: 'primary', value: '#6366F1', variant: 'base', usage: 'Primary brand color' },
        { name: 'primary-light', value: '#818CF8', variant: 'light', usage: 'Primary hover state' },
        { name: 'primary-dark', value: '#4F46E5', variant: 'dark', usage: 'Primary active state' },
        { name: 'secondary', value: '#EC4899', variant: 'base', usage: 'Secondary accent' },
        { name: 'surface', value: '#FFFFFF', variant: 'base', usage: 'Background surface' },
        { name: 'text', value: '#1F2937', variant: 'base', usage: 'Primary text' },
        { name: 'text-muted', value: '#6B7280', variant: 'muted', usage: 'Secondary text' },
        { name: 'success', value: '#10B981', variant: 'bright', usage: 'Success state' },
        { name: 'warning', value: '#F59E0B', variant: 'bright', usage: 'Warning state' },
        { name: 'error', value: '#EF4444', variant: 'bright', usage: 'Error state' },
      ],
      typography: {
        baseFontSize,
        scaleRatio,
        fontFamilies: [
          { name: 'Inter', fallbacks: ['system-ui', '-apple-system', 'sans-serif'], category: 'sans-serif', weights: [400, 500, 600, 700] },
          { name: 'Fira Code', fallbacks: ['monospace'], category: 'monospace', weights: [400, 500] },
        ],
        weights: { light: 300, regular: 400, medium: 500, semibold: 600, bold: 700 },
        lineHeights: { tight: 1.25, normal: 1.5, relaxed: 1.75 },
      },
      spacing: {
        baseUnit: baseSpacing,
        steps: {
          '0': 0, '1': baseSpacing * 0.25, '2': baseSpacing * 0.5, '3': baseSpacing * 0.75,
          '4': baseSpacing, '5': baseSpacing * 1.5, '6': baseSpacing * 2, '8': baseSpacing * 3,
          '10': baseSpacing * 4, '12': baseSpacing * 5, '16': baseSpacing * 8, '20': baseSpacing * 10,
        },
      },
      breakpoints: [
        { name: 'sm', minWidth: 640, columns: 4, gutter: 16 },
        { name: 'md', minWidth: 768, columns: 8, gutter: 24 },
        { name: 'lg', minWidth: 1024, columns: 12, gutter: 32 },
        { name: 'xl', minWidth: 1280, columns: 12, gutter: 40 },
      ],
      shadows: [
        { name: 'sm', value: '0 1px 2px rgba(0,0,0,0.05)', elevation: 1 },
        { name: 'md', value: '0 4px 6px rgba(0,0,0,0.1)', elevation: 2 },
        { name: 'lg', value: '0 10px 15px rgba(0,0,0,0.1)', elevation: 3 },
        { name: 'xl', value: '0 20px 25px rgba(0,0,0,0.15)', elevation: 4 },
      ],
      borderRadius: [
        { name: 'none', value: '0', size: 'none' },
        { name: 'sm', value: '2px', size: 'sm' },
        { name: 'md', value: '4px', size: 'md' },
        { name: 'lg', value: '8px', size: 'lg' },
        { name: 'xl', value: '16px', size: 'xl' },
        { name: 'full', value: '9999px', size: 'full' },
      ],
      metadata: {},
    };

    this.designSystems.set(id, designSystem);

    this.audit.append({
      actor: this.id,
      action: 'DESIGN_SYSTEM_CREATED',
      entity: id,
      details: { name, colorCount: designSystem.colors.length },
      timestamp: new Date(),
    });

    this.log.info('Design system created', { id, name });
    return designSystem;
  }

  /**
   * Get a design system by ID.
   */
  getDesignSystem(id: string): DesignSystem | undefined {
    return this.designSystems.get(id);
  }

  // ───────────────────────────────────────
  // Color Operations
  // ───────────────────────────────────────

  /**
   * Generate a color palette using HexCodeBot.
   */
  async generatePalette(baseColor: string, scheme: 'complementary' | 'analogous' | 'triadic' | 'split-complementary' | 'monochromatic' = 'analogous'): Promise<string[]> {
    const hexCode = this.getBot('HexCode')!;
    const result = await hexCode.execute({
      operation: 'PALETTE',
      baseColor,
      scheme,
    });

    this.log.info('Color palette generated', { baseColor, scheme });
    return result as string[];
  }

  // ───────────────────────────────────────
  // Typography Operations
  // ───────────────────────────────────────

  /**
   * Fetch available fonts via FontFetcherBot.
   */
  async fetchFonts(query: string, category?: string): Promise<unknown> {
    const fontFetcher = this.getBot('FontFetcher')!;
    const result = await fontFetcher.execute({
      operation: 'SEARCH',
      query,
      category,
    });

    this.log.info('Fonts fetched', { query, category });
    return result;
  }

  // ───────────────────────────────────────
  // Styling Operations
  // ───────────────────────────────────────

  /**
   * Delegate style tailoring to TailorAgent.
   */
  async tailorStyles(designSystemId: string, requirements: Record<string, unknown>): Promise<unknown> {
    const ds = this.designSystems.get(designSystemId);
    if (!ds) throw new Error(`Design system not found: ${designSystemId}`);

    const tailor = this.getAgent('SID-FABULOUSSA-TAILOR') as TailorAgent;
    const result = await tailor.runCycle({ designSystem: ds, requirements });

    this.log.info('Styles tailored', { designSystemId });
    return result;
  }

  /**
   * Delegate style weaving (composition) to WeaverAgent.
   */
  async weaveStyles(designSystemId: string, components: string[]): Promise<unknown> {
    const ds = this.designSystems.get(designSystemId);
    if (!ds) throw new Error(`Design system not found: ${designSystemId}`);

    const weaver = this.getAgent('SID-FABULOUSSA-WEAVER') as WeaverAgent;
    const result = await weaver.runCycle({ designSystem: ds, components });

    this.log.info('Styles woven', { designSystemId, componentCount: components.length });
    return result;
  }

  // ───────────────────────────────────────
  // Layout Operations
  // ───────────────────────────────────────

  /**
   * Compute layout spacing using PaddingBot.
   */
  async computeLayout(containerWidth: number, columns: number, gutter: number): Promise<unknown> {
    const padding = this.getBot('Padding')!;
    const result = await padding.execute({
      operation: 'GRID',
      containerWidth,
      columns,
      gutter,
    });

    return result;
  }

  // ───────────────────────────────────────
  // Pixel Operations
  // ───────────────────────────────────────

  /**
   * Push pixel-level adjustments via PixelPusherBot.
   */
  async pushPixels(operation: string, params: Record<string, unknown>): Promise<unknown> {
    const pixelPusher = this.getBot('PixelPusher')!;
    const result = await pixelPusher.execute({
      operation,
      ...params,
    });

    return result;
  }

  // ───────────────────────────────────────
  // Export
  // ───────────────────────────────────────

  /**
   * Export a design system to the specified format.
   */
  async exportDesignSystem(designSystemId: string, format: ThemeExport['format'] = 'css'): Promise<ThemeExport> {
    const ds = this.designSystems.get(designSystemId);
    if (!ds) throw new Error(`Design system not found: ${designSystemId}`);

    const tokenCount = ds.colors.length + ds.typography.fontFamilies.length + Object.keys(ds.spacing.steps).length + ds.shadows.length + ds.borderRadius.length;

    // Estimate output size
    let sizeBytes = 0;
    if (format === 'json') {
      sizeBytes = JSON.stringify(ds).length;
    } else if (format === 'css') {
      sizeBytes = ds.colors.length * 40 + ds.typography.fontFamilies.length * 60 + Object.keys(ds.spacing.steps).length * 30 + ds.shadows.length * 50;
    } else {
      sizeBytes = tokenCount * 50;
    }

    const exportResult: ThemeExport = {
      format,
      designSystemId,
      generatedAt: Date.now(),
      sizeBytes,
      tokenCount,
    };

    this.audit.append({
      actor: this.id,
      action: 'DESIGN_SYSTEM_EXPORTED',
      entity: designSystemId,
      details: { format, tokenCount, sizeBytes },
      timestamp: new Date(),
    });

    this.log.info('Design system exported', { designSystemId, format, tokenCount });
    return exportResult;
  }

  // ───────────────────────────────────────
  // Health & Diagnostics
  // ───────────────────────────────────────

  healthCheck(): {
    status: 'healthy' | 'degraded' | 'critical';
    designSystems: number;
    componentStyles: number;
    agents: number;
    bots: number;
    timestamp: number;
  } {
    return {
      status: 'healthy',
      designSystems: this.designSystems.size,
      componentStyles: this.componentStyles.size,
      agents: this.listAgentIds().length,
      bots: this.listBotNames().length,
      timestamp: Date.now(),
    };
  }
}
