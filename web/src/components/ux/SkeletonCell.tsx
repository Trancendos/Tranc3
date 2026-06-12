/**
 * SkeletonCell — Doherty Threshold
 *
 * Only renders the skeleton after 100ms of loading to prevent flash
 * on fast responses. If content arrives quickly, user sees nothing.
 */
import React from 'react'
import { useDoherty } from '../../hooks/useUxLaws'

interface SkeletonCellProps {
  isLoading: boolean
  children: React.ReactNode
  variant?: 'card' | 'text' | 'list'
  rows?: number
  delayMs?: number
  className?: string
}

function SkeletonPlaceholder({ variant = 'card', rows = 3 }: { variant: string; rows: number }) {
  if (variant === 'text') {
    return (
      <div className="ux-flex-col ux-gap-2" aria-hidden="true">
        {Array.from({ length: rows }).map((_, i) => (
          <div
            key={i}
            className="ux-skeleton ux-skeleton-text"
            style={{ width: `${70 + (i % 3) * 10}%` }}
          />
        ))}
      </div>
    )
  }
  if (variant === 'list') {
    return (
      <div className="ux-flex-col ux-gap-4" aria-hidden="true">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="ux-flex ux-gap-4 ux-items-center">
            <div className="ux-skeleton ux-skeleton-avatar" />
            <div className="ux-flex-col ux-gap-2" style={{ flex: 1 }}>
              <div className="ux-skeleton ux-skeleton-text" style={{ width: '60%' }} />
              <div className="ux-skeleton ux-skeleton-text" style={{ width: '40%' }} />
            </div>
          </div>
        ))}
      </div>
    )
  }
  return (
    <div className="ux-surface-card ux-p-6" aria-hidden="true">
      <div className="ux-skeleton ux-skeleton-title ux-mb-4" />
      <div className="ux-flex-col ux-gap-2">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="ux-skeleton ux-skeleton-text" style={{ width: `${80 - i * 15}%` }} />
        ))}
      </div>
    </div>
  )
}

export function SkeletonCell({
  isLoading, children, variant = 'card', rows = 3, delayMs = 100, className = ''
}: SkeletonCellProps) {
  const showSkeleton = useDoherty(isLoading, delayMs)

  if (!isLoading) return <>{children}</>

  return (
    <div className={className} aria-busy="true" aria-live="polite">
      {showSkeleton
        ? <SkeletonPlaceholder variant={variant} rows={rows} />
        : <span className="ux-sr-only">Loading…</span>
      }
    </div>
  )
}
