/**
 * ProgressiveDisclosure — Figma UI Principles: Progressive Disclosure
 *
 * Reveals content in layers — only what the user needs now, with smart gates
 * that unlock deeper content based on interaction, scroll depth, or time.
 * Implements Figma's principle of reducing cognitive load by hiding complexity
 * until it is needed.
 *
 * Gate types:
 *   click  — standard expand on tap
 *   scroll — reveals when scrolled into view
 *   time   — auto-reveals after a delay (onboarding)
 *   hover  — reveals on pointer enter (desktop preview)
 */
import React, { useCallback, useEffect, useRef, useState } from 'react'

type GateType = 'click' | 'scroll' | 'time' | 'hover'

interface DisclosureLayer {
  id: string
  summary: React.ReactNode
  detail: React.ReactNode
  gate?: GateType
  /** For 'time' gate: ms until auto-reveal. Default 2000 */
  delay?: number
}

interface ProgressiveDisclosureProps {
  layers: DisclosureLayer[]
  /** Animate expansion */
  animate?: boolean
  className?: string
}

function useDisclosureGate(gate: GateType, delay: number) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const supportsHover = typeof window !== 'undefined' && window.matchMedia('(hover: hover)').matches
  const toggle = useCallback(() => {
    if (gate === 'click' || (gate === 'hover' && !supportsHover)) setOpen(o => !o)
  }, [gate, supportsHover])

  useEffect(() => {
    if (gate === 'time') {
      const id = setTimeout(() => setOpen(true), delay)
      return () => clearTimeout(id)
    }
    if (gate === 'scroll' && ref.current) {
      const observer = new IntersectionObserver(
        ([entry]) => { if (entry.isIntersecting) setOpen(true) },
        { threshold: 0.4 },
      )
      observer.observe(ref.current)
      return () => observer.disconnect()
    }
  }, [gate, delay])

  const hoverProps = gate === 'hover' && supportsHover
    ? {
        onMouseEnter: () => setOpen(true),
        onMouseLeave: () => setOpen(false),
        onFocus: () => setOpen(true),
        onBlur: () => setOpen(false),
      }
    : {}

  return { open, toggle, ref, hoverProps, supportsHover }
}

function DisclosureItem({ layer, animate }: { layer: DisclosureLayer; animate: boolean }) {
  const gate = layer.gate ?? 'click'
  const delay = layer.delay ?? 2000
  const { open, toggle, ref, hoverProps, supportsHover } = useDisclosureGate(gate, delay)
  const detailId = `pd-detail-${layer.id}`
  const isInteractive = gate === 'click' || (gate === 'hover' && supportsHover)

  return (
    <div
      ref={ref}
      {...hoverProps}
      style={{ display: 'flex', flexDirection: 'column', gap: 'var(--ux-space-2)' }}
    >
      <div
        role={isInteractive ? 'button' : undefined}
        tabIndex={isInteractive ? 0 : undefined}
        aria-expanded={isInteractive ? open : undefined}
        aria-controls={detailId}
        onClick={toggle}
        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle() } }}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          cursor: isInteractive ? 'pointer' : 'default',
          userSelect: 'none',
        }}
      >
        <div style={{ flex: 1 }}>{layer.summary}</div>
        {isInteractive && (
          <span
            aria-hidden="true"
            style={{
              display: 'inline-block',
              transition: animate ? 'transform var(--ux-dur-base) var(--ux-ease-out)' : undefined,
              transform: open ? 'rotate(180deg)' : 'rotate(0deg)',
              color: 'var(--ux-text-muted)',
              fontSize: 'var(--ux-text-sm)',
              marginLeft: 'var(--ux-space-2)',
            }}
          >
            ▾
          </span>
        )}
      </div>
      <div
        id={detailId}
        role="region"
        aria-hidden={!open}
        style={{
          overflow: 'hidden',
          maxHeight: open ? '2000px' : '0',
          opacity: open ? 1 : 0,
          transition: animate
            ? 'max-height var(--ux-dur-expand) var(--ux-ease-out), opacity var(--ux-dur-base) var(--ux-ease-out)'
            : undefined,
        }}
      >
        <div style={{ paddingTop: 'var(--ux-space-2)' }}>{layer.detail}</div>
      </div>
    </div>
  )
}

export function ProgressiveDisclosure({ layers, animate = true, className = '' }: ProgressiveDisclosureProps) {
  return (
    <div
      className={className}
      style={{ display: 'flex', flexDirection: 'column', gap: 'var(--ux-space-4)' }}
    >
      {layers.map(layer => (
        <DisclosureItem key={layer.id} layer={layer} animate={animate} />
      ))}
    </div>
  )
}
