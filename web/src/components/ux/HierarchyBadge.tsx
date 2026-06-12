/**
 * HierarchyBadge — Law of Similarity + Von Restorff + Gestalt
 *
 * Consistent badge styling per variant (Similarity).
 * A "new" or "hot" badge breaks the pattern on purpose (Von Restorff).
 */
import React from 'react'

type BadgeVariant = 'primary' | 'secondary' | 'success' | 'warning' | 'danger' | 'highlight' | 'muted'

interface HierarchyBadgeProps {
  label: string
  variant?: BadgeVariant
  dot?: boolean
  className?: string
}

const variantStyles: Record<BadgeVariant, React.CSSProperties> = {
  primary:   { background: 'rgba(99,102,241,0.15)',  color: '#818cf8', border: '1px solid rgba(99,102,241,0.3)'  },
  secondary: { background: 'rgba(139,92,246,0.15)', color: '#a78bfa', border: '1px solid rgba(139,92,246,0.3)' },
  success:   { background: 'rgba(34,197,94,0.15)',  color: '#4ade80', border: '1px solid rgba(34,197,94,0.3)'  },
  warning:   { background: 'rgba(245,158,11,0.15)', color: '#fbbf24', border: '1px solid rgba(245,158,11,0.3)' },
  danger:    { background: 'rgba(239,68,68,0.15)',  color: '#f87171', border: '1px solid rgba(239,68,68,0.3)'  },
  highlight: { background: 'var(--ux-highlight)',   color: 'var(--ux-highlight-text)', border: 'none', fontWeight: 700 },
  muted:     { background: 'rgba(75,85,99,0.2)',    color: '#9ca3af', border: '1px solid rgba(75,85,99,0.3)'   },
}

const dotColours: Record<BadgeVariant, string> = {
  primary: '#818cf8', secondary: '#a78bfa', success: '#4ade80',
  warning: '#fbbf24', danger: '#f87171',   highlight: '#111827', muted: '#9ca3af',
}

export function HierarchyBadge({ label, variant = 'muted', dot = false, className = '' }: HierarchyBadgeProps) {
  return (
    <span
      className={className}
      data-variant={variant}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 'var(--ux-space-1)',
        padding: 'var(--ux-space-1) var(--ux-space-3)',
        borderRadius: 'var(--ux-radius-pill)',
        fontSize: 'var(--ux-text-xs)',
        fontWeight: 500,
        letterSpacing: '0.02em',
        ...variantStyles[variant],
      }}
    >
      {dot && (
        <span
          aria-hidden="true"
          style={{
            display: 'inline-block',
            width: '6px',
            height: '6px',
            borderRadius: '50%',
            background: dotColours[variant],
            flexShrink: 0,
          }}
        />
      )}
      {label}
    </span>
  )
}
