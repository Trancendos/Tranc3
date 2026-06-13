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
      style={{ listStyle: 'none', padding: 0, margin: 0 }}
    >
      {positioned.map(({ item, isPrime }) => {
        const attentionProps = getProps(item.id)
        const itemStyle: React.CSSProperties = {
          fontWeight: isPrime ? 600 : 400,
          ...(attentionProps.style ?? {}),
        }

        return (
          <li
            key={item.id}
            data-focused={attentionProps['data-focused']}
            onMouseEnter={attentionProps.onMouseEnter}
            onMouseLeave={attentionProps.onMouseLeave}
            onFocus={attentionProps.onFocus}
            onBlur={attentionProps.onBlur}
            style={itemStyle}
          >
            {item.onClick ? (
              <button
                type="button"
                onClick={item.onClick}
                className="ux-jakob-nav-item"
                aria-label={item.featured ? `${item.label} — featured` : undefined}
                style={{
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  textAlign: 'left',
                  padding: 0,
                  font: 'inherit',
                  color: 'inherit',
                }}
              >
                <span style={{ flex: 1 }}>
                  {item.label}
                  {item.featured && (
                    <span className="ux-restorff-highlight" style={{ marginLeft: 'var(--ux-space-2)' }}>
                      Featured
                    </span>
                  )}
                </span>
                {item.meta && <span className="ux-attention-meta">{item.meta}</span>}
              </button>
            ) : (
              <div
                className="ux-jakob-nav-item"
                aria-label={item.featured ? `${item.label} — featured` : undefined}
                style={{ display: 'flex', alignItems: 'center' }}
              >
                <span style={{ flex: 1 }}>
                  {item.label}
                  {item.featured && (
                    <span className="ux-restorff-highlight" style={{ marginLeft: 'var(--ux-space-2)' }}>
                      Featured
                    </span>
                  )}
                </span>
                {item.meta && <span className="ux-attention-meta">{item.meta}</span>}
              </div>
            )}
          </li>
        )
      })}
    </ul>
  )
}
