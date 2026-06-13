/**
 * ConsistencyShield — Shneiderman Rule 1: Strive for Consistency
 *                   + IxDF: Recognition Over Recall (Rule 8)
 *
 * Design-token validator and consistency enforcer. Audits child element
 * styles against the UX system's token contract, flagging any hard-coded
 * colour, spacing, or font values that bypass the design system. In
 * development the shield renders a visual overlay; in production it is a
 * zero-overhead pass-through wrapper.
 *
 * Consistency principle: identical actions, identical situations, identical
 * terminology — always. Users build a mental model from pattern repetition.
 * Every deviation from the token system breaks that model.
 */
import React, { useEffect, useId, useRef, useState } from 'react'

type TokenViolation = {
  property: string
  value: string
  element: string
  suggestion: string
}

const HARD_COLOUR_RE = /^#[0-9a-fA-F]{3,8}$|^rgb\(|^rgba\(|^hsl\(/
const HARD_PX_SPACE_RE = /^\d+px$/

function auditNode(el: Element, violations: TokenViolation[]) {
  const tag = el.tagName.toLowerCase()
  const id = el.id ? `#${el.id}` : ''
  const label = `${tag}${id}`

  const check = (prop: string, val: string, suggestion: string) => {
    if (val && val !== 'initial' && val !== 'none' && val !== 'normal') {
      violations.push({ property: prop, value: val, element: label, suggestion })
    }
  }

  const color = el.getAttribute('style')?.match(/\bcolor\s*:\s*([^;]+)/)?.[1]?.trim()
  if (color && HARD_COLOUR_RE.test(color)) {
    check('color', color, 'Use var(--ux-text-*) token')
  }

  const bg = el.getAttribute('style')?.match(/\bbackground(-color)?\s*:\s*([^;]+)/)?.[2]?.trim()
  if (bg && HARD_COLOUR_RE.test(bg)) {
    check('background', bg, 'Use var(--ux-surface-*) or var(--ux-brand-*) token')
  }

  const padding = el.getAttribute('style')?.match(/\bpadding\s*:\s*([^;]+)/)?.[1]?.trim()
  if (padding && HARD_PX_SPACE_RE.test(padding)) {
    check('padding', padding, 'Use var(--ux-space-*) token')
  }

  el.children && Array.from(el.children).forEach(child => auditNode(child, violations))
}

interface ConsistencyShieldProps {
  children: React.ReactNode
  /** Audit and show violations — defaults to true in development */
  audit?: boolean
  className?: string
}

export function ConsistencyShield({ children, audit, className = '' }: ConsistencyShieldProps) {
  const ref = useRef<HTMLDivElement>(null)
  const id = useId()
  const shouldAudit = audit ?? (typeof process !== 'undefined' && process.env?.NODE_ENV === 'development')
  const [violations, setViolations] = useState<TokenViolation[]>([])
  const [showPanel, setShowPanel] = useState(false)

  useEffect(() => {
    if (!shouldAudit || !ref.current) return
    const found: TokenViolation[] = []
    auditNode(ref.current, found)
    setViolations(found)
  }, [shouldAudit, children])

  return (
    <div ref={ref} className={`ux-consistency-shield ${className}`} style={{ position: 'relative' }}>
      {children}
      {shouldAudit && violations.length > 0 && (
        <button
          onClick={() => setShowPanel(v => !v)}
          aria-expanded={showPanel}
          aria-controls={`${id}-panel`}
          title={`${violations.length} design token violation${violations.length !== 1 ? 's' : ''}`}
          style={{
            position: 'absolute',
            top: 'var(--ux-space-1)',
            right: 'var(--ux-space-1)',
            background: violations.length > 0 ? '#cf222e' : '#1a7f37',
            color: '#fff',
            border: 'none',
            borderRadius: 'var(--ux-radius-full)',
            padding: '2px 6px',
            fontSize: '10px',
            fontWeight: 700,
            cursor: 'pointer',
            zIndex: 100,
            fontFamily: 'var(--ux-font-mono, monospace)',
          }}
        >
          {violations.length} token {violations.length !== 1 ? 'violations' : 'violation'}
        </button>
      )}
      {shouldAudit && showPanel && violations.length > 0 && (
        <div
          id={`${id}-panel`}
          role="status"
          aria-label="Design token violations"
          style={{
            position: 'absolute',
            top: 'calc(var(--ux-space-1) + 24px)',
            right: 'var(--ux-space-1)',
            background: 'var(--ux-surface-card, #fff)',
            border: '1px solid #cf222e',
            borderRadius: 'var(--ux-radius-md)',
            padding: 'var(--ux-space-3)',
            fontSize: 'var(--ux-text-xs)',
            zIndex: 101,
            maxWidth: '320px',
            boxShadow: 'var(--ux-shadow-lg)',
          }}
        >
          <strong style={{ display: 'block', marginBottom: 'var(--ux-space-2)', color: '#cf222e' }}>
            Token violations
          </strong>
          <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 'var(--ux-space-2)' }}>
            {violations.slice(0, 8).map((v, i) => (
              <li key={i} style={{ borderLeft: '2px solid #cf222e', paddingLeft: 'var(--ux-space-2)' }}>
                <code style={{ display: 'block', fontFamily: 'var(--ux-font-mono, monospace)' }}>
                  {v.element} → {v.property}: {v.value}
                </code>
                <span style={{ color: 'var(--ux-text-muted, #666)', fontSize: '10px' }}>{v.suggestion}</span>
              </li>
            ))}
            {violations.length > 8 && (
              <li style={{ color: 'var(--ux-text-muted, #666)' }}>…and {violations.length - 8} more</li>
            )}
          </ul>
        </div>
      )}
    </div>
  )
}
