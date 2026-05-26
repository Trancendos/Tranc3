/**
 * PaddingBot — Spacing & Layout Computation Bot for Fabulousa
 *
 * Identity:  NID-FABULOUSSA-PADDING
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    FabulousaAI (AID-FABULOUSSA)
 *
 * Responsibilities:
 *   - Compute grid column widths and gutters
 *   - Calculate spacing values from a base unit and scale steps
 *   - Resolve responsive breakpoint layouts
 *   - Generate spacing token CSS custom properties
 *   - Compute box model dimensions (content + padding + border + margin)
 */

import { Bot, Logger } from '../../../core/definitions';

// ───────────────────────────────────────────────────────
// Domain Types
// ───────────────────────────────────────────────────────

export interface GridParams {
  operation: 'GRID';
  containerWidth: number;
  columns: number;
  gutter: number;
  margin?: number;  // outer margin on each side
}

export interface SpacingParams {
  operation: 'SPACING';
  baseUnit: number;
  steps: string[];           // e.g. ['0','1','2','3','4','5','6','8','10','12','16','20']
  scaleType?: 'linear' | 'modular' | 'fibonacci';
  scaleRatio?: number;       // for modular scale
}

export interface ResponsiveParams {
  operation: 'RESPONSIVE';
  containerWidth: number;
  breakpoints: Array<{
    name: string;
    minWidth: number;
    columns: number;
    gutter: number;
  }>;
}

export interface TokenParams {
  operation: 'TOKENS';
  baseUnit: number;
  steps: Record<string, number>;  // name → multiplier
  prefix?: string;
  format?: 'css' | 'scss' | 'json';
}

export interface BoxModelParams {
  operation: 'BOX_MODEL';
  contentWidth: number;
  contentHeight: number;
  padding: { top: number; right: number; bottom: number; left: number };
  border: { top: number; right: number; bottom: number; left: number };
  margin: { top: number; right: number; bottom: number; left: number };
  boxSizing?: 'content-box' | 'border-box';
}

export type PaddingInput = GridParams | SpacingParams | ResponsiveParams | TokenParams | BoxModelParams;

// ───────────────────────────────────────────────────────
// PaddingBot Implementation
// ───────────────────────────────────────────────────────

export class PaddingBot extends Bot {
  private readonly log: Logger;

  constructor() {
    const handler = async (input: PaddingInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-FABULOUSSA-PADDING',
      'Padding',
      handler,
      'Grid computation, spacing scale generation, responsive layout resolution, spacing token CSS, box model calculation'
    );

    this.log = new Logger('PaddingBot');
  }

  private async process(input: PaddingInput): Promise<unknown> {
    switch (input.operation) {
      case 'GRID':
        return this.computeGrid(input);
      case 'SPACING':
        return this.computeSpacing(input);
      case 'RESPONSIVE':
        return this.computeResponsive(input);
      case 'TOKENS':
        return this.generateTokens(input);
      case 'BOX_MODEL':
        return this.computeBoxModel(input);
      default:
        throw new Error(`Unknown padding operation: ${(input as PaddingInput).operation}`);
    }
  }

  // ───────────────────────────────────────────────────────
  // Grid Computation
  // ───────────────────────────────────────────────────────

  private computeGrid(params: GridParams): {
    containerWidth: number;
    columns: number;
    gutter: number;
    margin: number;
    columnWidth: number;
    totalGutterWidth: number;
    totalMarginWidth: number;
    availableWidth: number;
    gridTemplate: string;
  } {
    const { containerWidth, columns, gutter, margin = 0 } = params;

    const totalGutterWidth = gutter * (columns - 1);
    const totalMarginWidth = margin * 2;
    const availableWidth = containerWidth - totalGutterWidth - totalMarginWidth;
    const columnWidth = availableWidth / columns;

    if (columnWidth <= 0) {
      this.log.warn('Grid computation results in negative column width', {
        containerWidth, columns, gutter, margin, availableWidth,
      });
    }

    // Generate CSS Grid template
    const gridTemplate = `repeat(${columns}, ${columnWidth.toFixed(2)}px)`;

    this.log.info('Grid computed', {
      containerWidth, columns, columnWidth: columnWidth.toFixed(2), gutter,
    });

    return {
      containerWidth,
      columns,
      gutter,
      margin,
      columnWidth: Math.round(columnWidth * 100) / 100,
      totalGutterWidth,
      totalMarginWidth,
      availableWidth: Math.round(availableWidth * 100) / 100,
      gridTemplate,
    };
  }

  // ───────────────────────────────────────────────────────
  // Spacing Scale Computation
  // ───────────────────────────────────────────────────────

  private computeSpacing(params: SpacingParams): {
    baseUnit: number;
    scaleType: string;
    steps: Record<string, { multiplier: number; value: number; px: string; rem: string }>;
  } {
    const { baseUnit, steps, scaleType = 'linear', scaleRatio = 1.25 } = params;

    const computedSteps: Record<string, { multiplier: number; value: number; px: string; rem: string }> = {};

    for (const step of steps) {
      let multiplier: number;

      if (scaleType === 'modular') {
        // Modular scale: based on powers of the ratio
        const stepNum = parseFloat(step) || 0;
        multiplier = Math.pow(scaleRatio, stepNum);
      } else if (scaleType === 'fibonacci') {
        // Fibonacci-inspired: step indices map to fibonacci numbers
        const fibSequence = this.fibonacci(steps.length);
        const stepIdx = steps.indexOf(step);
        multiplier = fibSequence[stepIdx] / fibSequence[0];
      } else {
        // Linear: step value × baseUnit
        multiplier = parseFloat(step) || 0;
      }

      const value = Math.round(baseUnit * multiplier * 100) / 100;
      const remValue = Math.round((value / 16) * 1000) / 1000; // assuming 16px base

      computedSteps[step] = {
        multiplier: Math.round(multiplier * 100) / 100,
        value,
        px: `${value}px`,
        rem: `${remValue}rem`,
      };
    }

    this.log.info('Spacing scale computed', { baseUnit, scaleType, stepCount: steps.length });

    return { baseUnit, scaleType, steps: computedSteps };
  }

  // ───────────────────────────────────────────────────────
  // Responsive Layout Resolution
  // ───────────────────────────────────────────────────────

  private computeResponsive(params: ResponsiveParams): {
    containerWidth: number;
    activeBreakpoint: string;
    layout: {
      breakpoint: string;
      columns: number;
      gutter: number;
      columnWidth: number;
      applicable: boolean;
    }[];
  } {
    const { containerWidth, breakpoints } = params;

    // Sort breakpoints by minWidth ascending
    const sorted = [...breakpoints].sort((a, b) => a.minWidth - b.minWidth);

    let activeBreakpoint = sorted[0]?.name ?? 'default';

    const layouts = sorted.map((bp) => {
      const applicable = containerWidth >= bp.minWidth;
      if (applicable) {
        activeBreakpoint = bp.name;
      }

      const totalGutterWidth = bp.gutter * (bp.columns - 1);
      const columnWidth = (containerWidth - totalGutterWidth) / bp.columns;

      return {
        breakpoint: bp.name,
        columns: bp.columns,
        gutter: bp.gutter,
        columnWidth: Math.round(columnWidth * 100) / 100,
        applicable,
      };
    });

    this.log.info('Responsive layout resolved', { containerWidth, activeBreakpoint });

    return { containerWidth, activeBreakpoint, layout: layouts };
  }

  // ───────────────────────────────────────────────────────
  // Spacing Token CSS Generation
  // ───────────────────────────────────────────────────────

  private generateTokens(params: TokenParams): {
    format: string;
    tokenCount: number;
    output: string;
    tokens: Record<string, { name: string; value: number; css: string }>;
  } {
    const { baseUnit, steps, prefix = 'space', format = 'css' } = params;

    const tokens: Record<string, { name: string; value: number; css: string }> = {};
    const lines: string[] = [];

    for (const [name, multiplier] of Object.entries(steps)) {
      const value = Math.round(baseUnit * multiplier * 100) / 100;
      const cssName = `--${prefix}-${name}`;
      const cssValue = `${value}px`;

      tokens[name] = { name: cssName, value, css: `${cssName}: ${cssValue};` };

      if (format === 'scss') {
        lines.push(`$${prefix}-${name}: ${value}px;`);
      } else if (format === 'json') {
        // Collected below
      } else {
        lines.push(`  ${cssName}: ${cssValue};`);
      }
    }

    let output: string;
    if (format === 'scss') {
      output = lines.join('\n');
    } else if (format === 'json') {
      const jsonObj: Record<string, number> = {};
      for (const [name, data] of Object.entries(tokens)) {
        jsonObj[name] = data.value;
      }
      output = JSON.stringify(jsonObj, null, 2);
    } else {
      output = `:root {\n${lines.join('\n')}\n}`;
    }

    this.log.info('Spacing tokens generated', { format, tokenCount: Object.keys(steps).length });

    return { format, tokenCount: Object.keys(steps).length, output, tokens };
  }

  // ───────────────────────────────────────────────────────
  // Box Model Computation
  // ───────────────────────────────────────────────────────

  private computeBoxModel(params: BoxModelParams): {
    content: { width: number; height: number };
    paddingBox: { width: number; height: number };
    borderBox: { width: number; height: number };
    marginBox: { width: number; height: number };
    boxSizing: string;
    summary: string;
  } {
    const { contentWidth, contentHeight, padding, border, margin, boxSizing = 'content-box' } = params;

    // Padding box = content + padding
    const paddingBoxWidth = contentWidth + padding.left + padding.right;
    const paddingBoxHeight = contentHeight + padding.top + padding.bottom;

    // Border box = padding box + border
    const borderBoxWidth = paddingBoxWidth + border.left + border.right;
    const borderBoxHeight = paddingBoxHeight + border.top + border.bottom;

    // Margin box = border box + margin
    const marginBoxWidth = borderBoxWidth + margin.left + margin.right;
    const marginBoxHeight = borderBoxHeight + margin.top + margin.bottom;

    const summary = [
      `Content: ${contentWidth}×${contentHeight}`,
      `Padding: ${padding.top}/${padding.right}/${padding.bottom}/${padding.left}`,
      `Border: ${border.top}/${border.right}/${border.bottom}/${border.left}`,
      `Margin: ${margin.top}/${margin.right}/${margin.bottom}/${margin.left}`,
      boxSizing === 'border-box'
        ? `Border-box total: ${contentWidth}×${contentHeight} (content reduced)`
        : `Content-box total: ${marginBoxWidth}×${marginBoxHeight}`,
    ].join(' | ');

    this.log.info('Box model computed', {
      contentBox: `${contentWidth}×${contentHeight}`,
      marginBox: `${marginBoxWidth}×${marginBoxHeight}`,
      boxSizing,
    });

    return {
      content: { width: contentWidth, height: contentHeight },
      paddingBox: { width: paddingBoxWidth, height: paddingBoxHeight },
      borderBox: { width: borderBoxWidth, height: borderBoxHeight },
      marginBox: { width: marginBoxWidth, height: marginBoxHeight },
      boxSizing,
      summary,
    };
  }

  // ───────────────────────────────────────────────────────
  // Utility
  // ───────────────────────────────────────────────────────

  private fibonacci(count: number): number[] {
    const seq: number[] = [1, 1];
    for (let i = 2; i < Math.max(count, 2); i++) {
      seq.push(seq[i - 1] + seq[i - 2]);
    }
    return seq.slice(0, Math.max(count, 2));
  }
}
