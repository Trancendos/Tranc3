/**
 * ChoiceGroup — Hick's Law + Choice Overload
 *
 * Limits visible choices to maxVisible (default 7). Hides the rest
 * behind a "Show X more" button to reduce decision paralysis.
 * Uses role="radiogroup" + arrow-key navigation (ARIA APG radio pattern).
 */
import React, { useRef } from 'react'
import { useHicks } from '../../hooks/useUxLaws'

interface Choice {
  id: string
  label: string
  description?: string
}

interface ChoiceGroupProps {
  choices: Choice[]
  selected: string | null
  onSelect: (id: string) => void
  maxVisible?: number
  label: string
  className?: string
}

export function ChoiceGroup({
  choices, selected, onSelect, maxVisible = 7, label, className = ''
}: ChoiceGroupProps) {
  const { visible, hasMore, expanded, toggle, hiddenCount } = useHicks(choices, maxVisible)
  const groupRef = useRef<HTMLDivElement>(null)

  const onKeyDown = (e: React.KeyboardEvent, currentIndex: number) => {
    const buttons = groupRef.current?.querySelectorAll<HTMLButtonElement>('[role="radio"]')
    if (!buttons) return
    const count = buttons.length
    let next = -1
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault(); next = (currentIndex + 1) % count
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault(); next = (currentIndex - 1 + count) % count
    } else if (e.key === 'Home') {
      e.preventDefault(); next = 0
    } else if (e.key === 'End') {
      e.preventDefault(); next = count - 1
    }
    if (next >= 0) {
      buttons[next].focus()
      onSelect(visible[next]?.id ?? '')
    }
  }

  return (
    <fieldset className={className} style={{ border: 'none', padding: 0, margin: 0 }}>
      <legend className="ux-tesler-label">{label}</legend>
      <div
        ref={groupRef}
        className={`ux-hicks-group ${expanded ? 'ux-hicks-expanded' : ''}`}
        role="radiogroup"
      >
        {visible.map((choice, index) => (
          <button
            key={choice.id}
            type="button"
            role="radio"
            aria-checked={selected === choice.id}
            data-selected={selected === choice.id ? 'true' : undefined}
            onClick={() => onSelect(choice.id)}
            onKeyDown={e => onKeyDown(e, index)}
            tabIndex={selected === choice.id || (!selected && index === 0) ? 0 : -1}
            className={`ux-fitts-secondary ${selected === choice.id ? 'ux-selected' : ''}`}
            style={selected === choice.id ? {
              borderColor: 'var(--ux-brand-primary)',
              color: 'var(--ux-brand-primary)',
              background: 'rgba(99,102,241,0.1)',
            } : undefined}
            title={choice.description}
          >
            {choice.label}
          </button>
        ))}
      </div>
      {hasMore && (
        <button
          type="button"
          className="ux-hicks-reveal"
          onClick={toggle}
          aria-expanded={expanded}
          aria-label={expanded ? 'Show fewer options' : `Show ${hiddenCount} more options`}
        >
          {expanded ? 'Show fewer' : `+${hiddenCount} more`}
        </button>
      )}
    </fieldset>
  )
}
