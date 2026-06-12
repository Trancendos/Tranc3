/**
 * ContrastBadge — Figma Design Basics: Color + Contrast Accessibility
 *
 * Auto-computes whether text on a given background meets WCAG 2.1
 * contrast ratio thresholds (AA: 4.5:1 normal, 3:1 large; AAA: 7:1).
 * Renders a badge indicating compliance level.
 *
 * Uses the WCAG relative luminance formula with sRGB gamma expansion.
 * Useful in design system documentation, token preview, and audit tools.
 */
import React, { useMemo } from 'react'

function sRGBtoLinear(c: number): number {
  const s = c / 255
  return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
}

function relativeLuminance(r: number, g: number, b: number): number {
  return 0.2126 * sRGBtoLinear(r) + 0.7152 * sRGBtoLinear(g) + 0.0722 * sRGBtoLinear(b)
}

function contrastRatio(l1: number, l2: number): number {
  const lighter = Math.max(l1, l2)
  const darker  = Math.min(l1, l2)
  return (lighter + 0.05) / (darker + 0.05)
}

/** Parse #rrggbb or #rgb hex to [r,g,b] */
function parseHex(hex: string): [number, number, number] | null {
  const clean = hex.replace('#', '')
  if (clean.length === 3) {
    const [r, g, b] = clean.split('').map(c => parseInt(c + c, 16))
    return [r, g, b]
  }
  if (clean.length === 6) {
    return [
      parseInt(clean.slice(0, 2), 16),
      parseInt(clean.slice(2, 4), 16),
      parseInt(clean.slice(4, 6), 16),
    ]
  }
  return null
}

type WCAGLevel = 'AAA' | 'AA' | 'AA Large' | 'Fail'

function wcagLevel(ratio: number, isLargeText: boolean): WCAGLevel {
  if (ratio >= 7)            return 'AAA'
  if (ratio >= 4.5)          return 'AA'
  if (isLargeText && ratio >= 3) return 'AA Large'
  return 'Fail'
}

const LEVEL_COLOR: Record<WCAGLevel, { bg: string; text: string }> = {
  AAA:       { bg: '#1a7f37', text: '#fff' },
  AA:        { bg: '#2e6da4', text: '#fff' },
  'AA Large':{ bg: '#9a6700', text: '#fff' },
  Fail:      { bg: '#cf222e', text: '#fff' },
}

interface ContrastBadgeProps {
  /** Foreground hex color */
  fg: string
  /** Background hex color */
  bg: string
  /** Whether the text is large (≥18pt or ≥14pt bold) */
  largeText?: boolean
  showRatio?: boolean
  className?: string
}

export function ContrastBadge({ fg, bg, largeText = false, showRatio = true, className = '' }: ContrastBadgeProps) {
  const result = useMemo(() => {
    const fgRGB = parseHex(fg)
    const bgRGB = parseHex(bg)
    if (!fgRGB || !bgRGB) return null
    const ratio = contrastRatio(
      relativeLuminance(...fgRGB),
      relativeLuminance(...bgRGB),
    )
    return { ratio, level: wcagLevel(ratio, largeText) }
  }, [fg, bg, largeText])

  if (!result) return null

  const { ratio, level } = result
  const colors = LEVEL_COLOR[level]

  return (
    <span
      className={`ux-contrast-badge ${className}`}
      title={`Contrast ratio ${ratio.toFixed(2)}:1 — WCAG ${level}`}
      aria-label={`WCAG contrast ${level}, ratio ${ratio.toFixed(2)} to 1`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 'var(--ux-space-1)',
        padding: '2px var(--ux-space-2)',
        borderRadius: 'var(--ux-radius-full)',
        background: colors.bg,
        color: colors.text,
        fontSize: 'var(--ux-text-xs)',
        fontWeight: 600,
        letterSpacing: '0.03em',
        fontFamily: 'var(--ux-font-mono, monospace)',
        whiteSpace: 'nowrap',
      }}
    >
      {level}
      {showRatio && <span style={{ opacity: 0.85 }}>{ratio.toFixed(1)}:1</span>}
    </span>
  )
}

interface ContrastPreviewProps {
  fg: string
  bg: string
  text?: string
  largeText?: boolean
  className?: string
}

/** Full preview swatch: colored block + text sample + badge */
export function ContrastPreview({ fg, bg, text = 'Aa', largeText = false, className = '' }: ContrastPreviewProps) {
  return (
    <div
      className={`ux-contrast-preview ${className}`}
      style={{
        display: 'inline-flex',
        flexDirection: 'column',
        gap: 'var(--ux-space-2)',
        padding: 'var(--ux-space-3)',
        borderRadius: 'var(--ux-radius-md)',
        border: '1px solid var(--ux-border)',
      }}
    >
      <div
        aria-hidden="true"
        style={{
          background: bg,
          color: fg,
          padding: 'var(--ux-space-2) var(--ux-space-3)',
          borderRadius: 'var(--ux-radius-sm)',
          fontSize: largeText ? 'var(--ux-text-lg)' : 'var(--ux-text-base)',
          fontWeight: largeText ? 700 : 400,
          minWidth: '80px',
          textAlign: 'center',
        }}
      >
        {text}
      </div>
      <ContrastBadge fg={fg} bg={bg} largeText={largeText} />
    </div>
  )
}
