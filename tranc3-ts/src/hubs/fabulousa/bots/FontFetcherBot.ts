/**
 * FontFetcherBot — Font Search & Retrieval Bot for Fabulousa
 *
 * Identity:  NID-FABULOUSSA-FONTFETCHER
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    FabulousaAI (AID-FABULOUSSA)
 *
 * Responsibilities:
 *   - Search available font catalogs by name, category, or characteristics
 *   - Pair fonts for complementary typography (heading + body)
 *   - Analyze font metrics (x-height, ascender, descender, weight range)
 *   - Generate @font-face CSS declarations
 *   - Recommend fallback font stacks
 */

import { Bot, Logger } from '../../../core/definitions';

// ───────────────────────────────────────────────────────
// Domain Types
// ───────────────────────────────────────────────────────

export interface FontEntry {
  family: string;
  category: 'serif' | 'sans-serif' | 'monospace' | 'display' | 'handwriting';
  weights: number[];
  styles: ('normal' | 'italic')[];
  xHeightRatio: number;   // ratio of x-height to em
  charWidth: number;       // average character width ratio
  fallbacks: string[];
  source: 'system' | 'google' | 'local';
  license: 'open' | 'free-for-use' | 'commercial' | 'unknown';
}

export interface SearchParams {
  operation: 'SEARCH';
  query: string;
  category?: 'serif' | 'sans-serif' | 'monospace' | 'display' | 'handwriting';
  weight?: number;
  source?: 'system' | 'google' | 'local';
}

export interface PairParams {
  operation: 'PAIR';
  headingFont: string;
  maxResults?: number;
}

export interface MetricsParams {
  operation: 'METRICS';
  fontFamily: string;
}

export interface FontFaceParams {
  operation: 'FONT_FACE';
  fontFamily: string;
  weight?: number;
  style?: 'normal' | 'italic';
  display?: 'auto' | 'block' | 'swap' | 'fallback' | 'optional';
  src?: string; // URL or local path
}

export interface FallbackParams {
  operation: 'FALLBACK';
  fontFamily: string;
  category?: 'serif' | 'sans-serif' | 'monospace' | 'display' | 'handwriting';
}

export type FontFetcherInput = SearchParams | PairParams | MetricsParams | FontFaceParams | FallbackParams;

// ───────────────────────────────────────────────────────
// In-Memory Font Catalog
// ───────────────────────────────────────────────────────

const FONT_CATALOG: FontEntry[] = [
  { family: 'Inter', category: 'sans-serif', weights: [100, 200, 300, 400, 500, 600, 700, 800, 900], styles: ['normal', 'italic'], xHeightRatio: 0.54, charWidth: 0.5, fallbacks: ['system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'sans-serif'], source: 'google', license: 'open' },
  { family: 'Roboto', category: 'sans-serif', weights: [100, 300, 400, 500, 700, 900], styles: ['normal', 'italic'], xHeightRatio: 0.52, charWidth: 0.5, fallbacks: ['Arial', 'Helvetica', 'sans-serif'], source: 'google', license: 'open' },
  { family: 'Open Sans', category: 'sans-serif', weights: [300, 400, 500, 600, 700, 800], styles: ['normal', 'italic'], xHeightRatio: 0.55, charWidth: 0.52, fallbacks: ['Helvetica', 'Arial', 'sans-serif'], source: 'google', license: 'open' },
  { family: 'Lato', category: 'sans-serif', weights: [100, 300, 400, 700, 900], styles: ['normal', 'italic'], xHeightRatio: 0.52, charWidth: 0.48, fallbacks: ['sans-serif'], source: 'google', license: 'open' },
  { family: 'Montserrat', category: 'sans-serif', weights: [100, 200, 300, 400, 500, 600, 700, 800, 900], styles: ['normal', 'italic'], xHeightRatio: 0.48, charWidth: 0.52, fallbacks: ['Helvetica', 'Arial', 'sans-serif'], source: 'google', license: 'open' },
  { family: 'Playfair Display', category: 'serif', weights: [400, 500, 600, 700, 800, 900], styles: ['normal', 'italic'], xHeightRatio: 0.46, charWidth: 0.55, fallbacks: ['Georgia', 'Times New Roman', 'serif'], source: 'google', license: 'open' },
  { family: 'Merriweather', category: 'serif', weights: [300, 400, 700, 900], styles: ['normal', 'italic'], xHeightRatio: 0.50, charWidth: 0.55, fallbacks: ['Georgia', 'Cambria', 'serif'], source: 'google', license: 'open' },
  { family: 'Lora', category: 'serif', weights: [400, 500, 600, 700], styles: ['normal', 'italic'], xHeightRatio: 0.49, charWidth: 0.52, fallbacks: ['Georgia', 'serif'], source: 'google', license: 'open' },
  { family: 'Fira Code', category: 'monospace', weights: [300, 400, 500, 600, 700], styles: ['normal'], xHeightRatio: 0.53, charWidth: 0.60, fallbacks: ['Consolas', 'Monaco', 'Courier New', 'monospace'], source: 'google', license: 'open' },
  { family: 'JetBrains Mono', category: 'monospace', weights: [100, 200, 300, 400, 500, 600, 700, 800], styles: ['normal', 'italic'], xHeightRatio: 0.54, charWidth: 0.60, fallbacks: ['Fira Code', 'Consolas', 'monospace'], source: 'google', license: 'open' },
  { family: 'Source Code Pro', category: 'monospace', weights: [200, 300, 400, 500, 600, 700, 900], styles: ['normal', 'italic'], xHeightRatio: 0.52, charWidth: 0.60, fallbacks: ['Consolas', 'monospace'], source: 'google', license: 'open' },
  { family: 'Poppins', category: 'sans-serif', weights: [100, 200, 300, 400, 500, 600, 700, 800, 900], styles: ['normal', 'italic'], xHeightRatio: 0.55, charWidth: 0.50, fallbacks: ['sans-serif'], source: 'google', license: 'open' },
  { family: 'Raleway', category: 'sans-serif', weights: [100, 200, 300, 400, 500, 600, 700, 800, 900], styles: ['normal', 'italic'], xHeightRatio: 0.50, charWidth: 0.48, fallbacks: ['sans-serif'], source: 'google', license: 'open' },
  { family: 'Bebas Neue', category: 'display', weights: [400], styles: ['normal'], xHeightRatio: 0.58, charWidth: 0.50, fallbacks: ['Impact', 'sans-serif'], source: 'google', license: 'open' },
  { family: 'Oswald', category: 'display', weights: [200, 300, 400, 500, 600, 700], styles: ['normal'], xHeightRatio: 0.55, charWidth: 0.48, fallbacks: ['Arial Narrow', 'sans-serif'], source: 'google', license: 'open' },
  { family: 'Pacifico', category: 'handwriting', weights: [400], styles: ['normal'], xHeightRatio: 0.50, charWidth: 0.52, fallbacks: ['cursive'], source: 'google', license: 'open' },
  { family: 'Dancing Script', category: 'handwriting', weights: [400, 500, 600, 700], styles: ['normal'], xHeightRatio: 0.52, charWidth: 0.50, fallbacks: ['cursive'], source: 'google', license: 'open' },
];

// ───────────────────────────────────────────────────────
// FontFetcherBot Implementation
// ───────────────────────────────────────────────────────

export class FontFetcherBot extends Bot {
  private readonly log: Logger;
  private readonly catalog: Map<string, FontEntry>;

  constructor() {
    const handler = async (input: FontFetcherInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-FABULOUSSA-FONTFETCHER',
      'FontFetcher',
      handler,
      'Font search, pairing, metrics analysis, @font-face generation, and fallback stack recommendations'
    );

    this.log = new Logger('FontFetcherBot');
    this.catalog = new Map();
    for (const font of FONT_CATALOG) {
      this.catalog.set(font.family.toLowerCase(), font);
    }
  }

  private async process(input: FontFetcherInput): Promise<unknown> {
    switch (input.operation) {
      case 'SEARCH':
        return this.searchFonts(input);
      case 'PAIR':
        return this.pairFonts(input);
      case 'METRICS':
        return this.getFontMetrics(input);
      case 'FONT_FACE':
        return this.generateFontFace(input);
      case 'FALLBACK':
        return this.generateFallback(input);
      default:
        throw new Error(`Unknown font fetcher operation: ${(input as FontFetcherInput).operation}`);
    }
  }

  // ───────────────────────────────────────────────────────
  // Font Search
  // ───────────────────────────────────────────────────────

  private searchFonts(params: SearchParams): { results: FontEntry[]; query: string; totalMatches: number } {
    const { query, category, weight, source } = params;
    const q = query.toLowerCase();

    let results = FONT_CATALOG.filter((font) => {
      // Name match
      const nameMatch = font.family.toLowerCase().includes(q);

      // Category filter
      const categoryMatch = !category || font.category === category;

      // Weight filter
      const weightMatch = !weight || font.weights.includes(weight);

      // Source filter
      const sourceMatch = !source || font.source === source;

      return (nameMatch || q.length === 0) && categoryMatch && weightMatch && sourceMatch;
    });

    // Sort by relevance: exact name match first, then by name similarity
    results.sort((a, b) => {
      const aExact = a.family.toLowerCase() === q ? 0 : a.family.toLowerCase().startsWith(q) ? 1 : 2;
      const bExact = b.family.toLowerCase() === q ? 0 : b.family.toLowerCase().startsWith(q) ? 1 : 2;
      return aExact - bExact;
    });

    this.log.info('Font search completed', { query, resultCount: results.length });

    return { results, query, totalMatches: results.length };
  }

  // ───────────────────────────────────────────────────────
  // Font Pairing
  // ───────────────────────────────────────────────────────

  private pairFonts(params: PairParams): { heading: FontEntry; pairs: Array<{ body: FontEntry; score: number; reason: string }> } {
    const { headingFont, maxResults = 3 } = params;
    const heading = this.catalog.get(headingFont.toLowerCase());

    if (!heading) {
      throw new Error(`Font not found in catalog: ${headingFont}`);
    }

    // Pairing rules:
    // 1. Contrast categories: serif heading → sans-serif body and vice versa
    // 2. Similar x-height ratios for visual rhythm
    // 3. Complementary weight ranges
    // 4. Avoid same family
    const complementaryCategory = heading.category === 'serif' ? 'sans-serif'
      : heading.category === 'sans-serif' ? 'serif'
      : 'sans-serif'; // display/handwriting → sans-serif body

    const candidates = FONT_CATALOG.filter((f) => f.family !== heading.family);

    const scored = candidates.map((bodyFont) => {
      let score = 50;
      let reason = '';

      // Category contrast bonus
      if (bodyFont.category === complementaryCategory) {
        score += 25;
        reason += 'Category contrast; ';
      }

      // X-height similarity (within 0.06 tolerance)
      const xHeightDiff = Math.abs(bodyFont.xHeightRatio - heading.xHeightRatio);
      if (xHeightDiff < 0.06) {
        score += 15;
        reason += 'Compatible x-height; ';
      }

      // Weight range complementarity
      const headingMaxWeight = Math.max(...heading.weights);
      const bodyMaxWeight = Math.max(...bodyFont.weights);
      if (headingMaxWeight >= 700 && bodyMaxWeight <= 600) {
        score += 10;
        reason += 'Weight complementarity; ';
      }

      // Monospace penalty for body text (unless display heading)
      if (bodyFont.category === 'monospace' && heading.category !== 'display') {
        score -= 20;
        reason += 'Monospace body penalty; ';
      }

      return { body: bodyFont, score: Math.max(0, Math.min(100, score)), reason: reason.trim() };
    });

    scored.sort((a, b) => b.score - a.score);

    this.log.info('Font pairing completed', { headingFont, pairCount: Math.min(maxResults, scored.length) });

    return { heading, pairs: scored.slice(0, maxResults) };
  }

  // ───────────────────────────────────────────────────────
  // Font Metrics
  // ───────────────────────────────────────────────────────

  private getFontMetrics(params: MetricsParams): {
    family: string;
    found: boolean;
    metrics: {
      xHeightRatio: number;
      charWidth: number;
      weights: number[];
      styles: string[];
      category: string;
      fallbacks: string[];
      source: string;
      license: string;
      ascenderRatio?: number;
      descenderRatio?: number;
      lineHeightRecommendation?: number;
    } | null;
  } {
    const { fontFamily } = params;
    const font = this.catalog.get(fontFamily.toLowerCase());

    if (!font) {
      this.log.warn('Font not found for metrics', { fontFamily });
      return { family: fontFamily, found: false, metrics: null };
    }

    // Derive additional metrics
    const ascenderRatio = font.xHeightRatio + 0.18; // estimate
    const descenderRatio = 0.22; // typical for Latin fonts
    const lineHeightRecommendation = font.category === 'display' ? 1.1
      : font.xHeightRatio > 0.52 ? 1.5
      : 1.6;

    this.log.info('Font metrics retrieved', { fontFamily });

    return {
      family: fontFamily,
      found: true,
      metrics: {
        xHeightRatio: font.xHeightRatio,
        charWidth: font.charWidth,
        weights: font.weights,
        styles: font.styles,
        category: font.category,
        fallbacks: font.fallbacks,
        source: font.source,
        license: font.license,
        ascenderRatio,
        descenderRatio,
        lineHeightRecommendation,
      },
    };
  }

  // ───────────────────────────────────────────────────────
  // @font-face CSS Generation
  // ───────────────────────────────────────────────────────

  private generateFontFace(params: FontFaceParams): { css: string; fontFamily: string; weight: number; style: string } {
    const { fontFamily, weight = 400, style = 'normal', display = 'swap', src } = params;
    const font = this.catalog.get(fontFamily.toLowerCase());

    const family = font?.family ?? fontFamily;
    const resolvedSrc = src ?? (font?.source === 'google'
      ? `url('https://fonts.googleapis.com/css2?family=${family.replace(/ /g, '+')}:wght@${weight}&display=swap')`
      : `local('${family}')`);

    const css = [
      `@font-face {`,
      `  font-family: '${family}';`,
      `  src: ${resolvedSrc};`,
      `  font-weight: ${weight};`,
      `  font-style: ${style};`,
      `  font-display: ${display};`,
      `}`,
    ].join('\n');

    this.log.info('@font-face CSS generated', { family, weight, style });

    return { css, fontFamily: family, weight, style };
  }

  // ───────────────────────────────────────────────────────
  // Fallback Stack Generation
  // ───────────────────────────────────────────────────────

  private generateFallback(params: FallbackParams): { fontFamily: string; stack: string; category: string; reason: string } {
    const { fontFamily, category } = params;
    const font = this.catalog.get(fontFamily.toLowerCase());
    const resolvedCategory = category ?? font?.category ?? 'sans-serif';

    const systemStacks: Record<string, string[]> = {
      'sans-serif': ['system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif'],
      'serif': ['Georgia', 'Cambria', 'Times New Roman', 'Times', 'serif'],
      'monospace': ['Fira Code', 'Consolas', 'Monaco', 'Andale Mono', 'Ubuntu Mono', 'monospace'],
      'display': ['Impact', 'Haettenschweiler', 'Arial Narrow Bold', 'sans-serif'],
      'handwriting': ['Brush Script MT', 'Comic Sans MS', 'cursive'],
    };

    const fontFallbacks = font?.fallbacks ?? [];
    const systemFallbacks = systemStacks[resolvedCategory] ?? systemStacks['sans-serif'];

    // Merge: font-specific fallbacks first, then system stack, dedup
    const merged = [...fontFallbacks];
    for (const f of systemFallbacks) {
      if (!merged.includes(f)) {
        merged.push(f);
      }
    }

    // Always end with generic family
    if (!merged.includes(resolvedCategory)) {
      merged.push(resolvedCategory);
    }

    const stack = merged.map((f) => f.includes(' ') ? `'${f}'` : f).join(', ');

    this.log.info('Fallback stack generated', { fontFamily, stackLength: merged.length });

    return {
      fontFamily: font?.family ?? fontFamily,
      stack,
      category: resolvedCategory,
      reason: font
        ? `Based on ${font.family} (${font.category}) with system fallbacks`
        : `Category-based fallback for ${resolvedCategory}`,
    };
  }
}
