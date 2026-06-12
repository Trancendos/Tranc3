/**
 * AdaptiveButton — Fitts's Law + Aesthetic-Usability + Doherty + ARIA
 *
 * Adapts size to importance. Absorbs loading state (Tesler).
 * Touch target always ≥ 44px (WCAG 2.5.5).
 */
import React from 'react'
import { useFitts, useAesthetic, useDoherty } from '../../hooks/useUxLaws'

interface AdaptiveButtonProps {
  importance?: 'primary' | 'secondary' | 'tertiary'
  loading?: boolean
  icon?: React.ReactNode
  children: React.ReactNode
  disabled?: boolean
  className?: string
  onClick?: React.MouseEventHandler<HTMLButtonElement>
  type?: 'button' | 'submit' | 'reset'
  style?: React.CSSProperties
  'aria-label'?: string
}

export function AdaptiveButton({
  importance = 'secondary',
  loading = false,
  icon,
  children,
  disabled,
  className = '',
  style,
  ...rest
}: AdaptiveButtonProps) {
  const fitts = useFitts(importance)
  const { props: aestheticProps } = useAesthetic()
  const showSpinner = useDoherty(loading, 80)

  return (
    <button
      {...fitts}
      {...aestheticProps}
      {...rest}
      disabled={disabled || loading}
      aria-disabled={disabled || loading}
      aria-busy={loading}
      className={`${fitts.className} ${className}`}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--ux-space-2)', ...style }}
    >
      {icon && !showSpinner && <span aria-hidden="true">{icon}</span>}
      {showSpinner && (
        <span
          aria-hidden="true"
          style={{
            display: 'inline-block',
            width: '1em', height: '1em',
            border: '2px solid transparent',
            borderTopColor: 'currentColor',
            borderRadius: '50%',
            animation: 'ux-spin 0.6s linear infinite',
            flexShrink: 0,
          }}
        />
      )}
      <span>{children}</span>
      {loading && <span className="ux-sr-only">Loading…</span>}
    </button>
  )
}
