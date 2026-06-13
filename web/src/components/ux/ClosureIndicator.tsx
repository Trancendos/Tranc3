/**
 * ClosureIndicator — Shneiderman Rule 3: Offer Informative Feedback
 *                  + Rule 4: Design Dialogs to Yield Closure
 *                  + UpSlide: Micro-interaction Feedback Patterns
 *
 * Wraps multi-step processes with clear beginning / middle / end signalling.
 * Closure is the feeling that a task is complete — users need an unambiguous
 * "done" signal to release cognitive load and move on.
 *
 * Phases:
 *   idle      — not started
 *   active    — in progress (shows progress + contextual hint)
 *   success   — completed (celebratory closure signal, auto-dismisses)
 *   error     — failed (plain error + remediation)
 *
 * Implements the UpSlide principle: every action must have a visible reaction.
 * The stronger the action, the stronger the feedback. Closure feedback must
 * feel final — not just a colour change.
 */
import React, { useEffect, useRef, useState } from 'react'

type ClosurePhase = 'idle' | 'active' | 'success' | 'error'

interface ClosureIndicatorProps {
  phase: ClosurePhase
  /** Message shown during active phase */
  activeMessage?: string
  /** Message shown at success closure */
  successMessage?: string
  /** Message shown at error (plain language) */
  errorMessage?: string
  /** Remediation hint shown below error */
  errorRemedy?: string
  /** Auto-dismiss success signal after N ms (0 = manual) */
  autoDismiss?: number
  onDismiss?: () => void
  /** Progress 0–1 shown in active phase (optional) */
  progress?: number
  className?: string
  children?: React.ReactNode
}

const PHASE_CONFIG: Record<Exclude<ClosurePhase, 'idle'>, { icon: string; color: string; bg: string }> = {
  active:  { icon: '◌', color: 'var(--ux-accent)',   bg: 'rgba(var(--ux-brand-rgb, 37 99 235), 0.06)' },
  success: { icon: '✓', color: 'var(--ux-success)',  bg: 'rgba(var(--ux-success-rgb, 26 127 55), 0.08)' },
  error:   { icon: '✕', color: 'var(--ux-danger)',   bg: 'rgba(var(--ux-danger-rgb, 207 34 46), 0.06)' },
}

export function ClosureIndicator({
  phase,
  activeMessage = 'Working…',
  successMessage = 'Done',
  errorMessage = 'Something went wrong',
  errorRemedy,
  autoDismiss = 3000,
  onDismiss,
  progress,
  className = '',
  children,
}: ClosureIndicatorProps) {
  const [visible, setVisible] = useState(phase !== 'idle')
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    setVisible(phase !== 'idle')
    if (phase === 'success' && autoDismiss > 0) {
      timerRef.current = setTimeout(() => {
        setVisible(false)
        onDismiss?.()
      }, autoDismiss)
    }
    return () => { if (timerRef.current) clearTimeout(timerRef.current) }
  }, [phase, autoDismiss, onDismiss])

  if (phase === 'idle' || !visible) {
    return children ? <>{children}</> : null
  }

  const config = PHASE_CONFIG[phase]
  const message = phase === 'active' ? activeMessage : phase === 'success' ? successMessage : errorMessage

  return (
    <div className={`ux-closure-indicator ${className}`}>
      {children}
      <div
        role={phase === 'error' ? 'alert' : 'status'}
        aria-live={phase === 'error' ? 'assertive' : 'polite'}
        aria-label={message}
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--ux-space-2)',
          padding: 'var(--ux-space-3) var(--ux-space-4)',
          borderRadius: 'var(--ux-radius-md)',
          background: config.bg,
          border: `1px solid ${config.color}22`,
          marginTop: children ? 'var(--ux-space-3)' : 0,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--ux-space-2)' }}>
          <span
            aria-hidden="true"
            style={{
              fontSize: 'var(--ux-text-lg)',
              color: config.color,
              animation: phase === 'active' ? 'ux-spin 0.8s linear infinite' : undefined,
              display: 'inline-block',
            }}
          >
            {config.icon}
          </span>
          <span style={{ fontSize: 'var(--ux-text-sm)', fontWeight: 500, color: 'var(--ux-text-primary)' }}>
            {message}
          </span>
          {phase === 'success' && onDismiss && (
            <button
              onClick={() => { if (timerRef.current) clearTimeout(timerRef.current); setVisible(false); onDismiss() }}
              aria-label="Dismiss"
              style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ux-text-muted)', fontSize: 'var(--ux-text-sm)' }}
            >
              ✕
            </button>
          )}
        </div>

        {phase === 'active' && progress !== undefined && (
          <div
            role="progressbar"
            aria-label="Task progress"
            aria-valuenow={Math.round(progress * 100)}
            aria-valuemin={0}
            aria-valuemax={100}
            style={{
              height: '3px',
              borderRadius: '2px',
              background: 'var(--ux-border)',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                height: '100%',
                width: `${progress * 100}%`,
                background: config.color,
                transition: 'width 0.3s var(--ux-ease-out)',
                borderRadius: '2px',
              }}
            />
          </div>
        )}

        {phase === 'error' && errorRemedy && (
          <p style={{ margin: 0, fontSize: 'var(--ux-text-xs)', color: 'var(--ux-text-muted)' }}>
            {errorRemedy}
          </p>
        )}
      </div>
    </div>
  )
}
