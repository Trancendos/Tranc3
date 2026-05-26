/**
 * Palette Bot — Studio Tier 5 Bot (NID-STUDIO-PALETTE)
 *
 * Color theory and palette generation.
 * Generates harmonious color palettes from a base color using
 * various color theory schemes (complementary, analogous, triadic, etc.)
 */

import { Bot, Logger } from '../../../core/definitions';

const logger = new Logger('PaletteBot');

export interface PaletteRequest {
  baseColor: string;
  scheme: 'complementary' | 'analogous' | 'triadic' | 'split-complementary' | 'tetradic' | 'monochromatic';
  count?: number;
}

export interface PaletteResult {
  baseColor: string;
  scheme: string;
  colors: string[];
  names: string[];
  harmony: number;
}

export class PaletteBot extends Bot {
  constructor() {
    super(
      'Palette',
      async (request: PaletteRequest): Promise<PaletteResult> => {
        const count = request.count || 5;
        const baseHue = hexToHue(request.baseColor);
        const colors = generatePalette(baseHue, request.scheme, count);
        const names = colors.map((_, i) => `${request.scheme}-${i + 1}`);
        const harmony = calculateHarmony(colors);

        logger.debug('Palette generated', { base: request.baseColor, scheme: request.scheme, count });

        return {
          baseColor: request.baseColor,
          scheme: request.scheme,
          colors,
          names,
          harmony,
        };
      },
      'Generates harmonious color palettes using color theory schemes',
    );
  }
}

/** Convert hex color to hue (0-360) */
function hexToHue(hex: string): number {
  const clean = hex.replace('#', '');
  const r = parseInt(clean.substring(0, 2), 16) / 255;
  const g = parseInt(clean.substring(2, 4), 16) / 255;
  const b = parseInt(clean.substring(4, 6), 16) / 255;

  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const d = max - min;

  if (d === 0) return 0;

  let h: number;
  if (max === r) h = ((g - b) / d) % 6;
  else if (max === g) h = (b - r) / d + 2;
  else h = (r - g) / d + 4;

  h = Math.round(h * 60);
  if (h < 0) h += 360;
  return h;
}

/** Generate palette based on scheme */
function generatePalette(baseHue: number, scheme: string, count: number): string[] {
  const hues: number[] = [];

  switch (scheme) {
    case 'complementary':
      hues.push(baseHue, (baseHue + 180) % 360);
      break;
    case 'analogous':
      for (let i = -2; i <= 2; i++) hues.push((baseHue + i * 30 + 360) % 360);
      break;
    case 'triadic':
      hues.push(baseHue, (baseHue + 120) % 360, (baseHue + 240) % 360);
      break;
    case 'split-complementary':
      hues.push(baseHue, (baseHue + 150) % 360, (baseHue + 210) % 360);
      break;
    case 'tetradic':
      hues.push(baseHue, (baseHue + 90) % 360, (baseHue + 180) % 360, (baseHue + 270) % 360);
      break;
    case 'monochromatic':
    default:
      for (let i = 0; i < count; i++) hues.push(baseHue);
      break;
  }

  // Pad to requested count with variations
  while (hues.length < count) {
    hues.push((hues[hues.length - 1] + 15) % 360);
  }

  // Convert hues to hex colors with varying saturation/lightness
  return hues.slice(0, count).map((hue, i) => {
    const saturation = 0.5 + (i / count) * 0.3;
    const lightness = 0.3 + (i / count) * 0.4;
    return hslToHex(hue, saturation, lightness);
  });
}

/** Convert HSL to hex */
function hslToHex(h: number, s: number, l: number): string {
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = l - c / 2;

  let r: number, g: number, b: number;
  if (h < 60) { r = c; g = x; b = 0; }
  else if (h < 120) { r = x; g = c; b = 0; }
  else if (h < 180) { r = 0; g = c; b = x; }
  else if (h < 240) { r = 0; g = x; b = c; }
  else if (h < 300) { r = x; g = 0; b = c; }
  else { r = c; g = 0; b = x; }

  const toHex = (v: number) => Math.round((v + m) * 255).toString(16).padStart(2, '0');
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

/** Calculate harmony score (0-1) */
function calculateHarmony(colors: string[]): number {
  // Simplified: more unique hues = higher harmony for non-monochromatic
  const hues = colors.map(hexToHue);
  const uniqueHues = new Set(hues.map(h => Math.round(h / 30)));
  return Math.min(uniqueHues.size / 6, 1.0);
}
