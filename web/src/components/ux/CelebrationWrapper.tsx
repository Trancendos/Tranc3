/**
 * CelebrationWrapper — Peak-End Rule
 *
 * Wraps any content. When `celebrate` is called, plays a delight animation.
 * Use at task completion, onboarding finish, or first-value moments.
 */
import React from 'react'
import { usePeakEnd } from '../../hooks/useUxLaws'

interface CelebrationWrapperProps {
  children: React.ReactNode
  triggerOn?: boolean
  message?: string
  className?: string
}

export function CelebrationWrapper({ children, triggerOn, message, className = '' }: CelebrationWrapperProps) {
  const { celebrating, celebrate, celebrateClass } = usePeakEnd()

  React.useEffect(() => {
    if (triggerOn) celebrate()
  }, [triggerOn, celebrate])

  return (
    <div className={`${celebrateClass} ${className}`} aria-live="polite">
      {children}
      {celebrating && message && (
        <p className="ux-postel-success" role="status" style={{ marginTop: 'var(--ux-space-2)' }}>
          {message}
        </p>
      )}
    </div>
  )
}
