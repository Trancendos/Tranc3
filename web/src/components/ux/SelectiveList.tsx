/**
 * SelectiveList — Selective Attention + Serial Position Effect + Von Restorff
 *
 * A list that dims non-hovered siblings (Selective Attention), bolds
 * first/last items (Serial Position), and highlights a designated
 * "featured" item distinctly (Von Restorff).
 */
import React from 'react'
import { useSerialPosition, useSelectiveAttention } from '../../hooks/useUxLaws'

interface ListItem {
  id: string
  label: string
  meta?: string
  featured?: boolean
  onClick?: () => void
}

interface SelectiveListProps {
  items: ListItem[]
  className?: string
  label: string
}

export function SelectiveList({ items, className = '', label }: SelectiveListProps) {
  const positioned = useSerialPosition(items)
  const { getProps } = useSelectiveAttention()

  return (
    <ul
      className={`ux-proximity-group ${className}`}
      role="list"
      aria-label={label}
    >
      {positioned.map(({ item, isPrime }) => (
        <li
          key={item.id}
          role={item.onClick ? 'button' : 'listitem'}
          tabIndex={item.onClick ? 0 : undefined}
          onClick={item.onClick}
          onKeyDown={item.onClick ? e => {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); item.onClick?.() }
          } : undefined}
          {...getProps(item.id)}
          className="ux-jakob-nav-item"
          style={{
            fontWeight: isPrime ? 600 : 400,
            cursor: item.onClick ? 'pointer' : 'default',
          }}
          aria-label={item.featured ? `${item.label} — featured` : item.label}
        >
          <span style={{ flex: 1 }}>
            {item.label}
            {item.featured && (
              <span className="ux-restorff-highlight" style={{ marginLeft: 'var(--ux-space-2)' }}>
                Featured
              </span>
            )}
          </span>
          {item.meta && (
            <span className="ux-attention-meta">{item.meta}</span>
          )}
        </li>
      ))}
    </ul>
  )
}
