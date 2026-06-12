/**
 * ParetoInsight — Pareto Principle (80/20) + Von Restorff + Selective Attention
 *
 * Takes a list of items with a numeric metric, surfaces the top 20%
 * as "high impact" with a Von Restorff highlight, dims the rest.
 */
import React from 'react'
import { usePareto } from '../../hooks/useUxLaws'
import { HierarchyBadge } from './HierarchyBadge'

interface ParetoItem {
  id: string
  label: string
  value: number
  unit?: string
}

interface ParetoInsightProps {
  items: ParetoItem[]
  title?: string
  className?: string
}

export function ParetoInsight({ items, title, className = '' }: ParetoInsightProps) {
  const { top, rest } = usePareto(items, i => i.value)
  const topIds = new Set(top.map(i => i.id))
  const all = [...top, ...rest]

  return (
    <section className={`ux-surface-card ux-p-6 ${className}`} aria-label={title ?? 'Impact analysis'}>
      {title && <h2 className="ux-attention-primary" style={{ marginBottom: 'var(--ux-space-4)' }}>{title}</h2>}
      <p className="ux-attention-meta" style={{ marginBottom: 'var(--ux-space-4)' }}>
        Top {top.length} item{top.length !== 1 ? 's' : ''} drive most of the impact (Pareto 80/20)
      </p>
      <ul className="ux-proximity-group" role="list" aria-label="Items by impact">
        {all.map(item => {
          const isTop = topIds.has(item.id)
          const rawMax = all[0]?.value ?? 0
          const max    = rawMax > 0 ? rawMax : 1
          const pct   = Math.min(100, Math.max(0, Math.round((item.value / max) * 100)))

          return (
            <li
              key={item.id}
              role="listitem"
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: 'var(--ux-space-1)',
                opacity: isTop ? 1 : 0.55,
                transition: 'opacity var(--ux-dur-base) var(--ux-ease-out)',
              }}
            >
              <div className="ux-flex ux-items-center ux-justify-between">
                <span className="ux-attention-secondary">
                  {item.label}
                  {isTop && (
                    <HierarchyBadge
                      label="High Impact"
                      variant="highlight"
                      className=""
                      style={{ marginLeft: 'var(--ux-space-2)' } as React.CSSProperties}
                    />
                  )}
                </span>
                <span className="ux-attention-meta">
                  {item.value.toLocaleString()}{item.unit ? ` ${item.unit}` : ''}
                </span>
              </div>
              <div className="ux-progress-track" role="presentation">
                <div
                  className="ux-progress-fill"
                  style={{
                    width: `${pct}%`,
                    background: isTop ? 'var(--ux-brand-primary)' : 'var(--ux-border)',
                  }}
                />
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
