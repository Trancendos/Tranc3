/**
 * VisualHierarchy — Figma Design Basics: Visual Hierarchy + Contrast Ratio
 *
 * Renders a content tree with automatic typographic scale assignment,
 * contrast-safe colour pairing, and spacing rhythm. Implements Figma's
 * principle that hierarchy is established through size, weight, colour, and
 * space — not decoration.
 *
 * Layers: primary → secondary → tertiary → meta
 * Each layer gets a computed token from the UX design system automatically.
 */
import React from 'react'

export type HierarchyLevel = 'primary' | 'secondary' | 'tertiary' | 'meta'

export interface HierarchyNode {
  id: string
  content: React.ReactNode
  level: HierarchyLevel
  children?: HierarchyNode[]
  tag?: keyof JSX.IntrinsicElements
}

interface VisualHierarchyProps {
  nodes: HierarchyNode[]
  gap?: 'compact' | 'normal' | 'loose'
  className?: string
}

const LEVEL_STYLES: Record<HierarchyLevel, React.CSSProperties> = {
  primary: {
    fontSize: 'var(--ux-text-2xl)',
    fontWeight: 700,
    color: 'var(--ux-text-primary)',
    lineHeight: 1.2,
    letterSpacing: '-0.02em',
  },
  secondary: {
    fontSize: 'var(--ux-text-lg)',
    fontWeight: 600,
    color: 'var(--ux-text-primary)',
    lineHeight: 1.35,
  },
  tertiary: {
    fontSize: 'var(--ux-text-base)',
    fontWeight: 400,
    color: 'var(--ux-text-secondary)',
    lineHeight: 1.5,
  },
  meta: {
    fontSize: 'var(--ux-text-xs)',
    fontWeight: 400,
    color: 'var(--ux-text-muted)',
    lineHeight: 1.4,
    letterSpacing: '0.02em',
    textTransform: 'uppercase' as const,
  },
}

const GAP_MAP = {
  compact: 'var(--ux-space-2)',
  normal: 'var(--ux-space-4)',
  loose: 'var(--ux-space-6)',
}

function HierarchyNodeItem({ node, gap }: { node: HierarchyNode; gap: string }) {
  const Tag = (node.tag ?? 'div') as React.ElementType
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap }}>
      <Tag style={LEVEL_STYLES[node.level]}>{node.content}</Tag>
      {node.children && node.children.length > 0 && (
        <ul
          role="list"
          style={{
            paddingLeft: 'var(--ux-space-4)',
            borderLeft: '2px solid var(--ux-border)',
            display: 'flex',
            flexDirection: 'column',
            gap,
            listStyle: 'none',
            margin: 0,
            padding: 0,
            paddingInlineStart: 'var(--ux-space-4)',
          }}
        >
          {node.children.map(child => (
            <li key={child.id} role="listitem">
              <HierarchyNodeItem node={child} gap={gap} />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function VisualHierarchy({ nodes, gap = 'normal', className = '' }: VisualHierarchyProps) {
  const gapValue = GAP_MAP[gap]
  return (
    <div
      className={className}
      style={{ display: 'flex', flexDirection: 'column', gap: gapValue }}
      role="list"
      aria-label="Content hierarchy"
    >
      {nodes.map(node => (
        <div key={node.id} role="listitem">
          <HierarchyNodeItem node={node} gap={gapValue} />
        </div>
      ))}
    </div>
  )
}
