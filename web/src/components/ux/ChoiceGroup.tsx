/**
 * ChoiceGroup — Hick's Law + Choice Overload
 *
 * Limits visible choices to maxVisible (default 7). Hides the rest
 * behind a "Show X more" button to reduce decision paralysis.
 */
import React from 'react'
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

  return (
    <fieldset className={className} style={{ border: 'none', padding: 0, margin: 0 }}>
      <legend className="ux-tesler-label">{label}</legend>
      <div
        className={`ux-hicks-group ${expanded ? 'ux-hicks-expanded' : ''}`}
        role="group"
        aria-label={label}
      >
        {visible.map(choice => (
          <button
            key={choice.id}
            type="button"
            role="radio"
            aria-checked={selected === choice.id}
            onClick={() => onSelect(choice.id)}
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
