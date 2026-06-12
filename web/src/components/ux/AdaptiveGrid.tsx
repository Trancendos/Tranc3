/**
 * AdaptiveGrid — Figma Design Basics: Grid Systems + Responsive Layout
 *
 * Liquid/responsive CSS Grid that automatically reflows columns based on
 * viewport width and content minimum size. Implements Figma's grid principles:
 * columns, gutters, margins, and responsive breakpoints.
 *
 * Modes:
 *   auto-fit  — fills available space, columns collapse when too narrow
 *   auto-fill — maintains column count, leaves empty slots
 *   fixed     — explicit column count at each breakpoint
 */
import React from 'react'

type GridMode = 'auto-fit' | 'auto-fill' | 'fixed'

interface FixedCols {
  xs?: number
  sm?: number
  md?: number
  lg?: number
  xl?: number
}

interface AdaptiveGridProps {
  children: React.ReactNode
  mode?: GridMode
  /** Minimum column width for auto-fit/auto-fill (px) */
  minColWidth?: number
  /** Column counts per breakpoint (mode=fixed) */
  cols?: FixedCols | number
  gap?: 'none' | 'xs' | 'sm' | 'md' | 'lg'
  /** Align cell content */
  align?: 'start' | 'center' | 'end' | 'stretch'
  className?: string
  style?: React.CSSProperties
  as?: keyof JSX.IntrinsicElements
}

const GAP_TOKEN: Record<string, string> = {
  none: '0',
  xs: 'var(--ux-space-1)',
  sm: 'var(--ux-space-2)',
  md: 'var(--ux-space-4)',
  lg: 'var(--ux-space-6)',
}

export function AdaptiveGrid({
  children,
  mode = 'auto-fit',
  minColWidth = 240,
  cols,
  gap = 'md',
  align = 'stretch',
  className = '',
  style,
  as: Tag = 'div',
}: AdaptiveGridProps) {
  const gapValue = GAP_TOKEN[gap]

  let gridTemplateColumns: string
  if (mode === 'fixed') {
    const count = typeof cols === 'number' ? cols : (cols?.md ?? cols?.sm ?? 1)
    gridTemplateColumns = `repeat(${count}, 1fr)`
  } else {
    gridTemplateColumns = `repeat(${mode}, minmax(${minColWidth}px, 1fr))`
  }

  return (
    <Tag
      className={`ux-adaptive-grid ${className}`}
      style={{
        display: 'grid',
        gridTemplateColumns,
        gap: gapValue,
        alignItems: align,
        width: '100%',
        ...style,
      }}
    >
      {children}
    </Tag>
  )
}

/** Spans a cell across multiple columns/rows */
interface GridCellProps {
  children: React.ReactNode
  colSpan?: number
  rowSpan?: number
  className?: string
  style?: React.CSSProperties
}

export function GridCell({ children, colSpan, rowSpan, className = '', style }: GridCellProps) {
  return (
    <div
      className={`ux-grid-cell ${className}`}
      style={{
        gridColumn: colSpan ? `span ${colSpan}` : undefined,
        gridRow: rowSpan ? `span ${rowSpan}` : undefined,
        minWidth: 0,
        ...style,
      }}
    >
      {children}
    </div>
  )
}
