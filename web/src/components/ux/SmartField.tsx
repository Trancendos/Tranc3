/**
 * SmartField — Tesler's Law + Postel's Law + ARIA
 *
 * Absorbs form complexity: floating label, inline validation,
 * normalisation, ARIA error/hint wiring — all automatic.
 */
import React, { useId } from 'react'
import { useTesler, usePostel } from '../../hooks/useUxLaws'

interface SmartFieldProps {
  label: string
  type?: string
  placeholder?: string
  hint?: string
  validate?: (v: string) => string | null
  normalise?: boolean
  onChange?: (value: string) => void
  className?: string
  required?: boolean
  autoComplete?: string
}

export function SmartField({
  label, type = 'text', placeholder = ' ', hint,
  validate, normalise = true, onChange, className = '',
  required = false, autoComplete,
}: SmartFieldProps) {
  const id = useId()
  const hintId = `${id}-hint`
  const errorId = `${id}-error`
  const { normalise: norm } = usePostel()
  const { value, dirty, error, valid, onChange: handleChange } = useTesler(validate)

  const handleInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value
    const cleaned = normalise && type !== 'password' ? norm(raw) : raw
    handleChange(raw) // validate against raw, normalise on blur
    onChange?.(cleaned)
  }

  const handleBlur = (e: React.FocusEvent<HTMLInputElement>) => {
    if (normalise && type !== 'password') {
      const cleaned = norm(e.target.value)
      handleChange(cleaned)
      onChange?.(cleaned)
    }
  }

  const showError = dirty && !!error
  const showSuccess = dirty && valid && value.length > 0

  return (
    <div className={`ux-tesler-field ${className}`}>
      <label htmlFor={id} className="ux-tesler-label">
        {label}
        {required && <span aria-hidden="true" style={{ color: 'var(--ux-danger)', marginLeft: '2px' }}>*</span>}
      </label>
      <input
        id={id}
        type={type}
        placeholder={placeholder}
        value={value}
        required={required}
        autoComplete={autoComplete}
        aria-describedby={[hint ? hintId : '', showError ? errorId : ''].filter(Boolean).join(' ') || undefined}
        aria-invalid={showError ? 'true' : undefined}
        aria-required={required}
        className="ux-tesler-input"
        onChange={handleInput}
        onBlur={handleBlur}
      />
      {hint && !showError && (
        <p id={hintId} className="ux-postel-hint">{hint}</p>
      )}
      {showError && (
        <p id={errorId} className="ux-postel-error" role="alert" aria-live="assertive">
          <span aria-hidden="true">⚠</span> {error}
        </p>
      )}
      {showSuccess && (
        <p className="ux-postel-success" aria-live="polite">✓</p>
      )}
    </div>
  )
}
