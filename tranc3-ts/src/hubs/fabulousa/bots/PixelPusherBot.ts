/**
 * PixelPusherBot — Pixel-Level Manipulation Bot for Fabulousa
 *
 * Identity:  NID-FABULOUSSA-PIXELPUSHER
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    FabulousaAI (AID-FABULOUSSA)
 *
 * Responsibilities:
 *   - Render pixel-level gradients and patterns
 *   - Compose multi-layer pixel buffers with blend modes
 *   - Rasterize design tokens to pixel buffers
 *   - Apply pixel-level transformations and effects
 */

import { Bot, Logger } from '../../../core/definitions';

// ───────────────────────────────────────────────────────
// Domain Types
// ───────────────────────────────────────────────────────

export interface PixelBuffer {
  width: number;
  height: number;
  data: number[]; // RGBA flat array, length = width * height * 4
  format: 'rgba' | 'rgb' | 'gray';
}

export interface GradientStop {
  offset: number; // 0..1
  color: string;  // hex e.g. '#FF6B6B'
  opacity?: number;
}

export interface GradientRenderParams {
  operation: 'GRADIENT';
  width: number;
  height: number;
  type: 'linear' | 'radial' | 'conic';
  angle?: number;          // degrees, for linear
  centerX?: number;        // 0..1, for radial/conic
  centerY?: number;
  stops: GradientStop[];
}

export interface PatternRenderParams {
  operation: 'PATTERN';
  width: number;
  height: number;
  pattern: 'dots' | 'lines' | 'grid' | 'checkerboard' | 'diagonal' | 'crosshatch' | 'waves';
  scale: number;
  foreground: string;
  background: string;
  opacity?: number;
}

export interface BlendParams {
  operation: 'BLEND';
  layers: PixelBuffer[];
  mode: 'normal' | 'multiply' | 'screen' | 'overlay' | 'darken' | 'lighten' | 'color-dodge' | 'color-burn' | 'soft-light' | 'hard-light' | 'difference' | 'exclusion';
  opacity?: number; // master opacity 0..1
}

export interface RasterizeParams {
  operation: 'RASTERIZE';
  tokens: Array<{
    type: 'color' | 'shadow' | 'border-radius';
    name: string;
    value: string;
    width: number;
    height: number;
  }>;
  padding?: number;
  layout: 'grid' | 'row' | 'column';
  columns?: number;
}

export type PixelPusherInput = GradientRenderParams | PatternRenderParams | BlendParams | RasterizeParams;

// ───────────────────────────────────────────────────────
// PixelPusherBot Implementation
// ───────────────────────────────────────────────────────

export class PixelPusherBot extends Bot {
  private readonly log: Logger;

  constructor() {
    const handler = async (input: PixelPusherInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-FABULOUSSA-PIXELPUSHER',
      'PixelPusher',
      handler,
      'Pixel-level gradient rendering, pattern generation, buffer blending, and token rasterization'
    );

    this.log = new Logger('PixelPusherBot');
  }

  private async process(input: PixelPusherInput): Promise<unknown> {
    switch (input.operation) {
      case 'GRADIENT':
        return this.renderGradient(input);
      case 'PATTERN':
        return this.renderPattern(input);
      case 'BLEND':
        return this.blendBuffers(input);
      case 'RASTERIZE':
        return this.rasterizeTokens(input);
      default:
        throw new Error(`Unknown pixel pusher operation: ${(input as PixelPusherInput).operation}`);
    }
  }

  // ───────────────────────────────────────────────────────
  // Gradient Rendering
  // ───────────────────────────────────────────────────────

  private renderGradient(params: GradientRenderParams): PixelBuffer & { stops: number; type: string } {
    const { width, height, type, angle = 180, centerX = 0.5, centerY = 0.5, stops } = params;
    const data: number[] = new Array(width * height * 4).fill(0);

    // Sort stops by offset
    const sortedStops = [...stops].sort((a, b) => a.offset - b.offset);

    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const nx = x / width;   // normalized 0..1
        const ny = y / height;

        let t: number;
        if (type === 'linear') {
          const rad = (angle * Math.PI) / 180;
          const dx = Math.cos(rad);
          const dy = Math.sin(rad);
          t = Math.max(0, Math.min(1, nx * dx + ny * dy));
        } else if (type === 'radial') {
          const dx = nx - centerX;
          const dy = ny - centerY;
          t = Math.min(1, Math.sqrt(dx * dx + dy * dy) * 2);
        } else {
          // conic
          const dx = nx - centerX;
          const dy = ny - centerY;
          t = (Math.atan2(dy, dx) / (2 * Math.PI) + 0.5) % 1;
        }

        const color = this.interpolateStops(sortedStops, t);
        const idx = (y * width + x) * 4;
        data[idx] = color.r;
        data[idx + 1] = color.g;
        data[idx + 2] = color.b;
        data[idx + 3] = Math.round((color.a ?? 1) * 255);
      }
    }

    this.log.info('Gradient rendered', { width, height, type, stopCount: stops.length });

    return { width, height, data, format: 'rgba', stops: stops.length, type };
  }

  private interpolateStops(stops: GradientStop[], t: number): { r: number; g: number; b: number; a?: number } {
    if (stops.length === 0) return { r: 0, g: 0, b: 0, a: 1 };
    if (stops.length === 1 || t <= stops[0].offset) {
      return { ...this.hexToRgb(stops[0].color), a: stops[0].opacity };
    }
    if (t >= stops[stops.length - 1].offset) {
      return { ...this.hexToRgb(stops[stops.length - 1].color), a: stops[stops.length - 1].opacity };
    }

    // Find surrounding stops
    for (let i = 0; i < stops.length - 1; i++) {
      if (t >= stops[i].offset && t <= stops[i + 1].offset) {
        const range = stops[i + 1].offset - stops[i].offset;
        const localT = range === 0 ? 0 : (t - stops[i].offset) / range;
        const c0 = this.hexToRgb(stops[i].color);
        const c1 = this.hexToRgb(stops[i + 1].color);
        const a0 = stops[i].opacity ?? 1;
        const a1 = stops[i + 1].opacity ?? 1;

        return {
          r: Math.round(c0.r + (c1.r - c0.r) * localT),
          g: Math.round(c0.g + (c1.g - c0.g) * localT),
          b: Math.round(c0.b + (c1.b - c0.b) * localT),
          a: a0 + (a1 - a0) * localT,
        };
      }
    }

    return { ...this.hexToRgb(stops[stops.length - 1].color), a: stops[stops.length - 1].opacity };
  }

  // ───────────────────────────────────────────────────────
  // Pattern Rendering
  // ───────────────────────────────────────────────────────

  private renderPattern(params: PatternRenderParams): PixelBuffer & { pattern: string; pixelCount: number } {
    const { width, height, pattern, scale, foreground, background, opacity = 1.0 } = params;
    const data: number[] = new Array(width * height * 4).fill(0);

    const fg = this.hexToRgb(foreground);
    const bg = this.hexToRgb(background);

    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        let isForeground = false;

        switch (pattern) {
          case 'dots':
            isForeground = (Math.floor(x / scale) + Math.floor(y / scale)) % 2 === 0
              && (x % scale) < scale * 0.4
              && (y % scale) < scale * 0.4;
            break;
          case 'lines':
            isForeground = (y % scale) < Math.max(1, scale * 0.15);
            break;
          case 'grid':
            isForeground = (x % scale) < 1 || (y % scale) < 1;
            break;
          case 'checkerboard':
            isForeground = (Math.floor(x / scale) + Math.floor(y / scale)) % 2 === 0;
            break;
          case 'diagonal':
            isForeground = ((x + y) % scale) < Math.max(1, scale * 0.15);
            break;
          case 'crosshatch':
            isForeground = ((x + y) % scale) < Math.max(1, scale * 0.15)
              || ((x - y + height) % scale) < Math.max(1, scale * 0.15);
            break;
          case 'waves':
            isForeground = Math.sin((x / scale) * Math.PI * 2) * scale + y % (scale * 2) < scale * 0.5;
            break;
        }

        const color = isForeground ? fg : bg;
        const idx = (y * width + x) * 4;
        data[idx] = color.r;
        data[idx + 1] = color.g;
        data[idx + 2] = color.b;
        data[idx + 3] = Math.round(opacity * 255);
      }
    }

    this.log.info('Pattern rendered', { width, height, pattern, scale });

    return { width, height, data, format: 'rgba', pattern, pixelCount: width * height };
  }

  // ───────────────────────────────────────────────────────
  // Buffer Blending
  // ───────────────────────────────────────────────────────

  private blendBuffers(params: BlendParams): PixelBuffer & { layersBlended: number; mode: string } {
    const { layers, mode, opacity = 1.0 } = params;

    if (layers.length === 0) {
      throw new Error('No layers to blend');
    }

    // Use the first layer dimensions as base
    const width = layers[0].width;
    const height = layers[0].height;
    const data: number[] = new Array(width * height * 4).fill(0);

    // Start with the first layer
    for (let i = 0; i < width * height * 4; i++) {
      data[i] = layers[0].data[i] ?? 0;
    }

    // Blend subsequent layers
    for (let layerIdx = 1; layerIdx < layers.length; layerIdx++) {
      const layer = layers[layerIdx];
      for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
          if (x >= layer.width || y >= layer.height) continue;

          const baseIdx = (y * width + x) * 4;
          const layerIdx2 = (y * layer.width + x) * 4;

          const baseR = data[baseIdx] / 255;
          const baseG = data[baseIdx + 1] / 255;
          const baseB = data[baseIdx + 2] / 255;
          const baseA = data[baseIdx + 3] / 255;

          const layerR = (layer.data[layerIdx2] ?? 0) / 255;
          const layerG = (layer.data[layerIdx2 + 1] ?? 0) / 255;
          const layerB = (layer.data[layerIdx2 + 2] ?? 0) / 255;
          const layerA = (layer.data[layerIdx2 + 3] ?? 0) / 255;

          const blended = this.blendPixel(baseR, baseG, baseB, baseA, layerR, layerG, layerB, layerA, mode);

          data[baseIdx] = Math.round(blended.r * 255);
          data[baseIdx + 1] = Math.round(blended.g * 255);
          data[baseIdx + 2] = Math.round(blended.b * 255);
          data[baseIdx + 3] = Math.round(blended.a * 255 * opacity);
        }
      }
    }

    this.log.info('Buffers blended', { layersBlended: layers.length, mode, width, height });

    return { width, height, data, format: 'rgba', layersBlended: layers.length, mode };
  }

  private blendPixel(
    br: number, bg: number, bb: number, ba: number,
    lr: number, lg: number, lb: number, la: number,
    mode: string
  ): { r: number; g: number; b: number; a: number } {
    let r: number, g: number, b: number;

    switch (mode) {
      case 'multiply':
        r = br * lr; g = bg * lg; b = bb * lb;
        break;
      case 'screen':
        r = 1 - (1 - br) * (1 - lr); g = 1 - (1 - bg) * (1 - lg); b = 1 - (1 - bb) * (1 - lb);
        break;
      case 'overlay':
        r = br < 0.5 ? 2 * br * lr : 1 - 2 * (1 - br) * (1 - lr);
        g = bg < 0.5 ? 2 * bg * lg : 1 - 2 * (1 - bg) * (1 - lg);
        b = bb < 0.5 ? 2 * bb * lb : 1 - 2 * (1 - bb) * (1 - lb);
        break;
      case 'darken':
        r = Math.min(br, lr); g = Math.min(bg, lg); b = Math.min(bb, lb);
        break;
      case 'lighten':
        r = Math.max(br, lr); g = Math.max(bg, lg); b = Math.max(bb, lb);
        break;
      case 'color-dodge':
        r = lr === 1 ? 1 : Math.min(1, br / (1 - lr));
        g = lg === 1 ? 1 : Math.min(1, bg / (1 - lg));
        b = lb === 1 ? 1 : Math.min(1, bb / (1 - lb));
        break;
      case 'color-burn':
        r = lr === 0 ? 0 : Math.max(0, 1 - (1 - br) / lr);
        g = lg === 0 ? 0 : Math.max(0, 1 - (1 - bg) / lg);
        b = lb === 0 ? 0 : Math.max(0, 1 - (1 - bb) / lb);
        break;
      case 'soft-light':
        r = lr < 0.5 ? br - (1 - 2 * lr) * br * (1 - br) : br + (2 * lr - 1) * (Math.sqrt(br) - br);
        g = lg < 0.5 ? bg - (1 - 2 * lg) * bg * (1 - bg) : bg + (2 * lg - 1) * (Math.sqrt(bg) - bg);
        b = lb < 0.5 ? bb - (1 - 2 * lb) * bb * (1 - bb) : bb + (2 * lb - 1) * (Math.sqrt(bb) - bb);
        break;
      case 'hard-light':
        r = lr < 0.5 ? 2 * br * lr : 1 - 2 * (1 - br) * (1 - lr);
        g = lg < 0.5 ? 2 * bg * lg : 1 - 2 * (1 - bg) * (1 - lg);
        b = lb < 0.5 ? 2 * bb * lb : 1 - 2 * (1 - bb) * (1 - lb);
        break;
      case 'difference':
        r = Math.abs(br - lr); g = Math.abs(bg - lg); b = Math.abs(bb - lb);
        break;
      case 'exclusion':
        r = br + lr - 2 * br * lr; g = bg + lg - 2 * bg * lg; b = bb + lb - 2 * bb * lb;
        break;
      default: // 'normal'
        r = lr; g = lg; b = lb;
        break;
    }

    // Alpha compositing (Porter-Duff over)
    const a = la + ba * (1 - la);
    const aSafe = a === 0 ? 1 : a;
    const outR = (lr * la + br * ba * (1 - la)) / aSafe;
    const outG = (lg * la + bg * ba * (1 - la)) / aSafe;
    const outB = (lb * la + bb * ba * (1 - la)) / aSafe;

    return { r: Math.max(0, Math.min(1, outR)), g: Math.max(0, Math.min(1, outG)), b: Math.max(0, Math.min(1, outB)), a };
  }

  // ───────────────────────────────────────────────────────
  // Token Rasterization
  // ───────────────────────────────────────────────────────

  private rasterizeTokens(params: RasterizeParams): PixelBuffer & { tokenCount: number; layout: string } {
    const { tokens, padding = 8, layout, columns = 4 } = params;

    if (tokens.length === 0) {
      return { width: 0, height: 0, data: [], format: 'rgba', tokenCount: 0, layout };
    }

    // Calculate grid dimensions
    const tokenWidth = tokens[0].width;
    const tokenHeight = tokens[0].height;
    const effectiveCols = layout === 'column' ? 1 : layout === 'row' ? tokens.length : Math.min(columns, tokens.length);
    const rows = Math.ceil(tokens.length / effectiveCols);

    const totalWidth = effectiveCols * (tokenWidth + padding) + padding;
    const totalHeight = rows * (tokenHeight + padding) + padding;
    const data: number[] = new Array(totalWidth * totalHeight * 4).fill(0);

    // Fill background white
    for (let i = 0; i < data.length; i += 4) {
      data[i] = 255;     // R
      data[i + 1] = 255; // G
      data[i + 2] = 255; // B
      data[i + 3] = 255; // A
    }

    // Render each token swatch
    for (let ti = 0; ti < tokens.length; ti++) {
      const token = tokens[ti];
      const col = ti % effectiveCols;
      const row = Math.floor(ti / effectiveCols);
      const ox = padding + col * (tokenWidth + padding);
      const oy = padding + row * (tokenHeight + padding);

      const color = this.hexToRgb(token.value.startsWith('#') ? token.value : '#CCCCCC');

      for (let y = 0; y < tokenHeight; y++) {
        for (let x = 0; x < tokenWidth; x++) {
          const px = ox + x;
          const py = oy + y;
          if (px >= totalWidth || py >= totalHeight) continue;

          const idx = (py * totalWidth + px) * 4;
          if (token.type === 'color') {
            data[idx] = color.r;
            data[idx + 1] = color.g;
            data[idx + 2] = color.b;
            data[idx + 3] = 255;
          } else if (token.type === 'shadow') {
            // Shadow preview: darkened edges
            const edge = x < 2 || y < 2 || x >= tokenWidth - 2 || y >= tokenHeight - 2;
            if (edge) {
              data[idx] = Math.max(0, data[idx] - 60);
              data[idx + 1] = Math.max(0, data[idx + 1] - 60);
              data[idx + 2] = Math.max(0, data[idx + 2] - 60);
            }
          } else if (token.type === 'border-radius') {
            // Border-radius preview: circle approximation
            const cx = tokenWidth / 2;
            const cy = tokenHeight / 2;
            const radius = Math.min(cx, cy) * parseFloat(token.value);
            const dx = x - cx;
            const dy = y - cy;
            if (Math.sqrt(dx * dx + dy * dy) <= radius) {
              data[idx] = color.r;
              data[idx + 1] = color.g;
              data[idx + 2] = color.b;
              data[idx + 3] = 255;
            }
          }
        }
      }
    }

    this.log.info('Tokens rasterized', { tokenCount: tokens.length, layout, totalWidth, totalHeight });

    return { width: totalWidth, height: totalHeight, data, format: 'rgba', tokenCount: tokens.length, layout };
  }

  // ───────────────────────────────────────────────────────
  // Utility
  // ───────────────────────────────────────────────────────

  private hexToRgb(hex: string): { r: number; g: number; b: number } {
    const clean = hex.replace('#', '');
    const parsed = parseInt(clean.padEnd(6, '0').slice(0, 6), 16);
    return {
      r: (parsed >> 16) & 0xFF,
      g: (parsed >> 8) & 0xFF,
      b: parsed & 0xFF,
    };
  }
}
