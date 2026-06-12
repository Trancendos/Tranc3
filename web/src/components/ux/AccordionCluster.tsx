/**
 * AccordionCluster — Cognitive Load + Hick's Law + Jakob's Law + ARIA
 *
 * Progressive disclosure via accordion. Shows one section expanded by
 * default (Serial Position: first item primed). Keyboard navigation
 * follows ARIA Authoring Practices Guide (APG) accordion pattern.
 * Chevron rotates on expand (conventional — Jakob's Law).
 */
import React, { useId } from 'react'
import { useCognitiveLoad } from '../../hooks/useUxLaws'

interface AccordionItem {
  id: string
  title: string
  badge?: string
  children: React.ReactNode
}

interface AccordionClusterProps {
  items: AccordionItem[]
  defaultOpen?: string | string[]
  className?: string
  label: string
}

export function AccordionCluster({ items, defaultOpen, className = '', label }: AccordionClusterProps) {
  const baseId = useId()
  const resolvedOpen = defaultOpen === undefined
    ? (items[0] ? [items[0].id] : [])
    : Array.isArray(defaultOpen) ? defaultOpen : [defaultOpen]
  const { isExpanded, toggle } = useCognitiveLoad(resolvedOpen)

  return (
    <div className={`ux-flex-col ux-gap-2 ${className}`} role="region" aria-label={label}>
      {items.map(item => {
        const expanded = isExpanded(item.id)
        const headerId  = `${baseId}-hdr-${item.id}`
        const panelId   = `${baseId}-pnl-${item.id}`

        return (
          <div key={item.id} className="ux-common-region" style={{ padding: 0, overflow: 'hidden' }}>
            <h3 style={{ margin: 0 }}>
              <button
                id={headerId}
                type="button"
                aria-expanded={expanded}
                aria-controls={panelId}
                onClick={() => toggle(item.id)}
                className="ux-jakob-nav-item ux-w-full ux-justify-between"
                style={{
                  borderRadius: 'var(--ux-radius-lg)',
                  padding: 'var(--ux-space-4) var(--ux-space-6)',
                  width: '100%',
                  textAlign: 'left',
                  background: 'none',
                  border: 'none',
                }}
              >
                <span className="ux-flex ux-items-center ux-gap-2">
                  {item.title}
                  {item.badge && (
                    <span
                      style={{
                        fontSize: 'var(--ux-text-xs)',
                        background: 'rgba(99,102,241,0.15)',
                        color: '#818cf8',
                        borderRadius: 'var(--ux-radius-pill)',
                        padding: '0 var(--ux-space-2)',
                      }}
                    >
                      {item.badge}
                    </span>
                  )}
                </span>
                <svg
                  className="ux-chevron"
                  aria-hidden="true"
                  width="16" height="16" viewBox="0 0 16 16"
                  fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                >
                  <polyline points="4 6 8 10 12 6" />
                </svg>
              </button>
            </h3>

            <div
              id={panelId}
              role="region"
              aria-labelledby={headerId}
              hidden={!expanded}
              style={{
                padding: expanded ? 'var(--ux-space-4) var(--ux-space-6) var(--ux-space-6)' : undefined,
              }}
            >
              {expanded && (
                <div className="ux-flow-prose">
                  {item.children}
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
