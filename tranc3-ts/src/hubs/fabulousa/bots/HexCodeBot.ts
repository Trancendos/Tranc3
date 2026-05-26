/**
 * HexCodeBot — Color & Hex Code Management Bot for Fabulousa
 *
 * Identity:  NID-FABULOUSSA-HEXCODE
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    FabulousaAI (AID-FABULOUSSA)
 *
 * Responsibilities:
 *   - Generate color palettes from a base color (complementary, analogous, triadic, etc.)
 *   - Convert between color spaces (HEX, RGB, HSL, HSV)
 *   - Parse, validate, and manipulate hex color codes
 *   - Shift hue, adjust saturation/lightness
 *   - Compute perceptual color distances (CIE76 ΔE)
 */

import { Bot, Logger } from '../../../core/definitions';

// ───────────────────────────────────────────────────────
// Domain Types
// ───────────────────────────────────────────────────────

export interface PaletteParams {
  operation: 'PALETTE';
  baseColor: string;
  scheme: 'complementary' | 'analogous' | 'triadic' | 'split-complementary' | 'monochromatic' | 'tetradic';
  count?: number; // number of colors in output
}

export interface ConvertParams {
  operation: 'CONVERT';
  color: string;
  from: 'hex' | 'rgb' | 'hsl' | 'hsv';
  to: 'hex' | 'rgb' | 'hsl' | 'hsv';
}

export interface ParseParams {
  operation: 'PARSE';
  color: string;
}

export interface ShiftParams {
  operation: 'SHIFT';
  color: string;
  hue?: number;        // degrees shift
  saturation?: number; // percentage shift
  lightness?: number;  // percentage shift
}

export interface DistanceParams {
  operation: 'DISTANCE';
  colorA: string;
  colorB: string;
  metric?: 'euclidean' | 'cie76';
}

export type HexCodeInput = PaletteParams | ConvertParams | ParseParams | ShiftParams | DistanceParams;

export interface RGB { r: number; g: number; b: number; }
export interface HSL { h: number; s: number; l: number; }
export interface HSV { h: number; s: number; v: number; }
export interface LAB { l: number; a: number; b: number; }

// ───────────────────────────────────────────────────────
// HexCodeBot Implementation
// ───────────────────────────────────────────────────────

export class HexCodeBot extends Bot {
  private readonly log: Logger;

  constructor() {
    const handler = async (input: HexCodeInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-FABULOUSSA-HEXCODE',
      'HexCode',
      handler,
      'Color palette generation, color space conversion, hex parsing, hue shifting, perceptual distance'
    );

    this.log = new Logger('HexCodeBot');
  }

  private async process(input: HexCodeInput): Promise<unknown> {
    switch (input.operation) {
      case 'PALETTE':
        return this.generatePalette(input);
      case 'CONVERT':
        return this.convertColor(input);
      case 'PARSE':
        return this.parseColor(input);
      case 'SHIFT':
        return this.shiftColor(input);
      case 'DISTANCE':
        return this.colorDistance(input);
      default:
        throw new Error(`Unknown hex code operation: ${(input as HexCodeInput).operation}`);
    }
  }

  // ───────────────────────────────────────────────────────
  // Palette Generation
  // ───────────────────────────────────────────────────────

  private generatePalette(params: PaletteParams): { colors: string[]; scheme: string; baseColor: string } {
    const { baseColor, scheme, count = 5 } = params;
    const hsl = this.hexToHsl(baseColor);
    const colors: string[] = [baseColor];

    switch (scheme) {
      case 'complementary':
        colors.push(this.hslToHex({ h: (hsl.h + 180) % 360, s: hsl.s, l: hsl.l }));
        // Add light and dark variants
        colors.push(this.hslToHex({ h: hsl.h, s: hsl.s, l: Math.min(90, hsl.l + 20) }));
        colors.push(this.hslToHex({ h: hsl.h, s: hsl.s, l: Math.max(10, hsl.l - 20) }));
        colors.push(this.hslToHex({ h: (hsl.h + 180) % 360, s: hsl.s, l: Math.min(90, hsl.l + 15) }));
        break;

      case 'analogous':
        for (let i = 1; i < count; i++) {
          const angleOffset = i * 30;
          colors.push(this.hslToHex({
            h: (hsl.h + angleOffset) % 360,
            s: hsl.s,
            l: hsl.l,
          }));
        }
        break;

      case 'triadic':
        colors.push(this.hslToHex({ h: (hsl.h + 120) % 360, s: hsl.s, l: hsl.l }));
        colors.push(this.hslToHex({ h: (hsl.h + 240) % 360, s: hsl.s, l: hsl.l }));
        // Add lighter variants
        colors.push(this.hslToHex({ h: hsl.h, s: hsl.s * 0.6, l: Math.min(85, hsl.l + 15) }));
        colors.push(this.hslToHex({ h: (hsl.h + 120) % 360, s: hsl.s * 0.6, l: Math.min(85, hsl.l + 15) }));
        break;

      case 'split-complementary':
        colors.push(this.hslToHex({ h: (hsl.h + 150) % 360, s: hsl.s, l: hsl.l }));
        colors.push(this.hslToHex({ h: (hsl.h + 210) % 360, s: hsl.s, l: hsl.l }));
        colors.push(this.hslToHex({ h: hsl.h, s: hsl.s * 0.5, l: Math.min(90, hsl.l + 20) }));
        colors.push(this.hslToHex({ h: (hsl.h + 180) % 360, s: hsl.s * 0.7, l: hsl.l }));
        break;

      case 'monochromatic':
        for (let i = 1; i < count; i++) {
          const lShift = ((i - count / 2) * 15);
          colors.push(this.hslToHex({
            h: hsl.h,
            s: Math.max(10, Math.min(100, hsl.s + (i % 2 === 0 ? 10 : -10))),
            l: Math.max(5, Math.min(95, hsl.l + lShift)),
          }));
        }
        break;

      case 'tetradic':
        colors.push(this.hslToHex({ h: (hsl.h + 90) % 360, s: hsl.s, l: hsl.l }));
        colors.push(this.hslToHex({ h: (hsl.h + 180) % 360, s: hsl.s, l: hsl.l }));
        colors.push(this.hslToHex({ h: (hsl.h + 270) % 360, s: hsl.s, l: hsl.l }));
        break;
    }

    this.log.info('Palette generated', { baseColor, scheme, colorCount: colors.length });

    return { colors: colors.slice(0, count), scheme, baseColor };
  }

  // ───────────────────────────────────────────────────────
  // Color Space Conversion
  // ───────────────────────────────────────────────────────

  private convertColor(params: ConvertParams): { input: string; from: string; to: string; result: string; components: Record<string, number> } {
    const { color, from, to } = params;

    // Normalize to RGB first
    let rgb: RGB;
    if (from === 'hex') {
      rgb = this.hexToRgb(color);
    } else if (from === 'rgb') {
      rgb = this.parseRgbString(color);
    } else if (from === 'hsl') {
      rgb = this.hslToRgb(this.parseHslString(color));
    } else {
      rgb = this.hsvToRgb(this.parseHsvString(color));
    }

    // Convert from RGB to target
    let result: string;
    let components: Record<string, number>;

    if (to === 'hex') {
      result = this.rgbToHex(rgb);
      components = { r: rgb.r, g: rgb.g, b: rgb.b };
    } else if (to === 'rgb') {
      result = `rgb(${rgb.r}, ${rgb.g}, ${rgb.b})`;
      components = { r: rgb.r, g: rgb.g, b: rgb.b };
    } else if (to === 'hsl') {
      const hsl = this.rgbToHsl(rgb);
      result = `hsl(${hsl.h.toFixed(1)}, ${hsl.s.toFixed(1)}%, ${hsl.l.toFixed(1)}%)`;
      components = { h: hsl.h, s: hsl.s, l: hsl.l };
    } else {
      const hsv = this.rgbToHsv(rgb);
      result = `hsv(${hsv.h.toFixed(1)}, ${hsv.s.toFixed(1)}%, ${hsv.v.toFixed(1)}%)`;
      components = { h: hsv.h, s: hsv.s, v: hsv.v };
    }

    this.log.info('Color converted', { from, to });

    return { input: color, from, to, result, components };
  }

  // ───────────────────────────────────────────────────────
  // Color Parsing
  // ───────────────────────────────────────────────────────

  private parseColor(params: ParseParams): {
    original: string;
    valid: boolean;
    format: string;
    rgb: RGB | null;
    hsl: HSL | null;
    hex: string | null;
    luminance: number | null;
  } {
    const { color } = params;
    const trimmed = color.trim();

    // Try hex
    if (/^#?[0-9A-Fa-f]{3,8}$/.test(trimmed)) {
      const rgb = this.hexToRgb(trimmed);
      const hsl = this.rgbToHsl(rgb);
      const luminance = this.relativeLuminance(rgb);
      return {
        original: color,
        valid: true,
        format: 'hex',
        rgb,
        hsl,
        hex: this.rgbToHex(rgb),
        luminance,
      };
    }

    // Try rgb()
    const rgbMatch = trimmed.match(/^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/);
    if (rgbMatch) {
      const rgb: RGB = { r: parseInt(rgbMatch[1]), g: parseInt(rgbMatch[2]), b: parseInt(rgbMatch[3]) };
      const hsl = this.rgbToHsl(rgb);
      const luminance = this.relativeLuminance(rgb);
      return {
        original: color,
        valid: true,
        format: 'rgb',
        rgb,
        hsl,
        hex: this.rgbToHex(rgb),
        luminance,
      };
    }

    // Try hsl()
    const hslMatch = trimmed.match(/^hsla?\(\s*([\d.]+)\s*,\s*([\d.]+)%?\s*,\s*([\d.]+)%?/);
    if (hslMatch) {
      const hsl: HSL = { h: parseFloat(hslMatch[1]), s: parseFloat(hslMatch[2]), l: parseFloat(hslMatch[3]) };
      const rgb = this.hslToRgb(hsl);
      const luminance = this.relativeLuminance(rgb);
      return {
        original: color,
        valid: true,
        format: 'hsl',
        rgb,
        hsl,
        hex: this.rgbToHex(rgb),
        luminance,
      };
    }

    return { original: color, valid: false, format: 'unknown', rgb: null, hsl: null, hex: null, luminance: null };
  }

  // ───────────────────────────────────────────────────────
  // Color Shifting
  // ───────────────────────────────────────────────────────

  private shiftColor(params: ShiftParams): { original: string; shifted: string; hsl: HSL; changes: Record<string, number> } {
    const { color, hue = 0, saturation = 0, lightness = 0 } = params;
    const hsl = this.hexToHsl(color);

    const shifted: HSL = {
      h: (hsl.h + hue + 360) % 360,
      s: Math.max(0, Math.min(100, hsl.s + saturation)),
      l: Math.max(0, Math.min(100, hsl.l + lightness)),
    };

    const shiftedHex = this.hslToHex(shifted);

    this.log.info('Color shifted', {
      original: color,
      shifted: shiftedHex,
      hueShift: hue,
      satShift: saturation,
      lightShift: lightness,
    });

    return {
      original: color,
      shifted: shiftedHex,
      hsl: shifted,
      changes: { hue, saturation, lightness },
    };
  }

  // ───────────────────────────────────────────────────────
  // Color Distance
  // ───────────────────────────────────────────────────────

  private colorDistance(params: DistanceParams): { colorA: string; colorB: string; metric: string; distance: number; similar: boolean } {
    const { colorA, colorB, metric = 'cie76' } = params;

    const rgbA = this.hexToRgb(colorA);
    const rgbB = this.hexToRgb(colorB);

    let distance: number;

    if (metric === 'cie76') {
      // Convert to Lab via XYZ
      const labA = this.rgbToLab(rgbA);
      const labB = this.rgbToLab(rgbB);
      distance = Math.sqrt(
        Math.pow(labA.l - labB.l, 2) +
        Math.pow(labA.a - labB.a, 2) +
        Math.pow(labA.b - labB.b, 2)
      );
    } else {
      // Simple Euclidean in RGB space
      distance = Math.sqrt(
        Math.pow(rgbA.r - rgbB.r, 2) +
        Math.pow(rgbA.g - rgbB.g, 2) +
        Math.pow(rgbA.b - rgbB.b, 2)
      );
    }

    // CIE76 thresholds: ≤ 2.3 imperceptible, 2.3-5 noticeable, > 5 distinct
    const similar = metric === 'cie76' ? distance <= 5 : distance <= 30;

    this.log.info('Color distance computed', { colorA, colorB, metric, distance: distance.toFixed(2) });

    return { colorA, colorB, metric, distance: Math.round(distance * 100) / 100, similar };
  }

  // ───────────────────────────────────────────────────────
  // Color Space Math Utilities
  // ───────────────────────────────────────────────────────

  private hexToRgb(hex: string): RGB {
    const clean = hex.replace('#', '');
    const padded = clean.length === 3
      ? clean[0] + clean[0] + clean[1] + clean[1] + clean[2] + clean[2]
      : clean.padEnd(6, '0').slice(0, 6);
    const parsed = parseInt(padded, 16);
    return {
      r: (parsed >> 16) & 0xFF,
      g: (parsed >> 8) & 0xFF,
      b: parsed & 0xFF,
    };
  }

  private rgbToHex(rgb: RGB): string {
    const toHex = (n: number) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, '0');
    return `#${toHex(rgb.r)}${toHex(rgb.g)}${toHex(rgb.b)}`.toUpperCase();
  }

  private hexToHsl(hex: string): HSL {
    return this.rgbToHsl(this.hexToRgb(hex));
  }

  private hslToHex(hsl: HSL): string {
    return this.rgbToHex(this.hslToRgb(hsl));
  }

  private rgbToHsl(rgb: RGB): HSL {
    const r = rgb.r / 255;
    const g = rgb.g / 255;
    const b = rgb.b / 255;

    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    const l = (max + min) / 2;

    if (max === min) {
      return { h: 0, s: 0, l: l * 100 };
    }

    const d = max - min;
    const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);

    let h: number;
    if (max === r) {
      h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
    } else if (max === g) {
      h = ((b - r) / d + 2) / 6;
    } else {
      h = ((r - g) / d + 4) / 6;
    }

    return { h: h * 360, s: s * 100, l: l * 100 };
  }

  private hslToRgb(hsl: HSL): RGB {
    const h = hsl.h / 360;
    const s = hsl.s / 100;
    const l = hsl.l / 100;

    if (s === 0) {
      const v = Math.round(l * 255);
      return { r: v, g: v, b: v };
    }

    const hue2rgb = (p: number, q: number, t: number): number => {
      if (t < 0) t += 1;
      if (t > 1) t -= 1;
      if (t < 1 / 6) return p + (q - p) * 6 * t;
      if (t < 1 / 2) return q;
      if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
      return p;
    };

    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;

    return {
      r: Math.round(hue2rgb(p, q, h + 1 / 3) * 255),
      g: Math.round(hue2rgb(p, q, h) * 255),
      b: Math.round(hue2rgb(p, q, h - 1 / 3) * 255),
    };
  }

  private rgbToHsv(rgb: RGB): HSV {
    const r = rgb.r / 255;
    const g = rgb.g / 255;
    const b = rgb.b / 255;

    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    const d = max - min;

    let h: number;
    if (max === min) {
      h = 0;
    } else if (max === r) {
      h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
    } else if (max === g) {
      h = ((b - r) / d + 2) / 6;
    } else {
      h = ((r - g) / d + 4) / 6;
    }

    const s = max === 0 ? 0 : d / max;

    return { h: h * 360, s: s * 100, v: max * 100 };
  }

  private hsvToRgb(hsv: HSV): RGB {
    const h = hsv.h / 360;
    const s = hsv.s / 100;
    const v = hsv.v / 100;

    const i = Math.floor(h * 6);
    const f = h * 6 - i;
    const p = v * (1 - s);
    const q = v * (1 - f * s);
    const t = v * (1 - (1 - f) * s);

    let r: number, g: number, b: number;
    switch (i % 6) {
      case 0: r = v; g = t; b = p; break;
      case 1: r = q; g = v; b = p; break;
      case 2: r = p; g = v; b = t; break;
      case 3: r = p; g = q; b = v; break;
      case 4: r = t; g = p; b = v; break;
      default: r = v; g = p; b = q; break;
    }

    return { r: Math.round(r * 255), g: Math.round(g * 255), b: Math.round(b * 255) };
  }

  private rgbToLab(rgb: RGB): LAB {
    // RGB → XYZ (sRGB D65)
    let r = rgb.r / 255;
    let g = rgb.g / 255;
    let b = rgb.b / 255;

    r = r > 0.04045 ? Math.pow((r + 0.055) / 1.055, 2.4) : r / 12.92;
    g = g > 0.04045 ? Math.pow((g + 0.055) / 1.055, 2.4) : g / 12.92;
    b = b > 0.04045 ? Math.pow((b + 0.055) / 1.055, 2.4) : b / 12.92;

    let x = (r * 0.4124564 + g * 0.3575761 + b * 0.1804375) / 0.95047;
    let y = (r * 0.2126729 + g * 0.7151522 + b * 0.0721750) / 1.00000;
    let z = (r * 0.0193339 + g * 0.1191920 + b * 0.9503041) / 1.08883;

    // XYZ → Lab
    const epsilon = 0.008856;
    const kappa = 903.3;

    x = x > epsilon ? Math.cbrt(x) : (kappa * x + 16) / 116;
    y = y > epsilon ? Math.cbrt(y) : (kappa * y + 16) / 116;
    z = z > epsilon ? Math.cbrt(z) : (kappa * z + 16) / 116;

    return {
      l: 116 * y - 16,
      a: 500 * (x - y),
      b: 200 * (y - z),
    };
  }

  private relativeLuminance(rgb: RGB): number {
    const sRGB = (c: number) => {
      const normalized = c / 255;
      return normalized <= 0.03928
        ? normalized / 12.92
        : Math.pow((normalized + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * sRGB(rgb.r) + 0.7152 * sRGB(rgb.g) + 0.0722 * sRGB(rgb.b);
  }

  private parseRgbString(str: string): RGB {
    const match = str.match(/(\d+)/g);
    if (!match || match.length < 3) return { r: 0, g: 0, b: 0 };
    return { r: parseInt(match[0]), g: parseInt(match[1]), b: parseInt(match[2]) };
  }

  private parseHslString(str: string): HSL {
    const match = str.match(/([\d.]+)/g);
    if (!match || match.length < 3) return { h: 0, s: 0, l: 0 };
    return { h: parseFloat(match[0]), s: parseFloat(match[1]), l: parseFloat(match[2]) };
  }

  private parseHsvString(str: string): HSV {
    const match = str.match(/([\d.]+)/g);
    if (!match || match.length < 3) return { h: 0, s: 0, v: 0 };
    return { h: parseFloat(match[0]), s: parseFloat(match[1]), v: parseFloat(match[2]) };
  }
}
