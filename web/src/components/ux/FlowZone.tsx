/**
 * FlowZone — Flow State + Working Memory + Selective Attention
 *
 * Detects user idle state (3 s) and applies a "focus mode" that hides
 * secondary chrome, keeping only the content in view.
 * Working Memory: a sticky context bar persists on scroll.
 */
import React from 'react'
import { useFlow, useWorkingMemory } from '../../hooks/useUxLaws'

interface FlowZoneProps {
  children: React.ReactNode
  contextLabel?: string
  contextMeta?: React.ReactNode
  idleMs?: number
  className?: string
}

export function FlowZone({ children, contextLabel, contextMeta, idleMs = 3000, className = '' }: FlowZoneProps) {
  const inFlow = useFlow(idleMs)
  const anchored = useWorkingMemory(60)

  return (
    <div
      className={className}
      data-flow={inFlow ? 'active' : undefined}
      style={{ position: 'relative' }}
    >
      {/* Working Memory anchor — always-visible context */}
      {(contextLabel || contextMeta) && anchored && (
        <div className="ux-memory-anchor" aria-label="Current context" role="banner">
          {contextLabel && <span className="ux-attention-secondary">{contextLabel}</span>}
          {contextMeta && <span className="ux-attention-meta">{contextMeta}</span>}
        </div>
      )}

      {/* Content dims secondary elements in flow state */}
      <div
        style={{
          transition: 'opacity var(--ux-dur-moderate) var(--ux-ease-smooth)',
        }}
      >
        {children}
      </div>
    </div>
  )
}
