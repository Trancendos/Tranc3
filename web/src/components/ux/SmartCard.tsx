/**
 * SmartCard — Figma UI Principles: Consistency + Feedback + State Awareness
 *
 * Context-aware card with a built-in finite state machine:
 *   idle → loading → success | error → idle
 *
 * Implements Figma's card principles: contained surface, clear visual boundary,
 * depth via shadow, hover elevation, and interactive feedback. Also integrates
 * Nielsen Heuristic #1 (Visibility of System Status) via state-driven overlays.
 */
import React, { useCallback, useReducer } from 'react'

type CardState = 'idle' | 'loading' | 'success' | 'error'

interface SmartCardState {
  status: CardState
  message?: string
}

type CardAction =
  | { type: 'LOAD'; message?: string }
  | { type: 'SUCCEED'; message?: string }
  | { type: 'FAIL'; message: string }
  | { type: 'RESET' }

function cardReducer(state: SmartCardState, action: CardAction): SmartCardState {
  switch (action.type) {
    case 'LOAD':    return { status: 'loading', message: action.message }
    case 'SUCCEED': return { status: 'success', message: action.message }
    case 'FAIL':    return { status: 'error',   message: action.message }
    case 'RESET':   return { status: 'idle',    message: undefined }
    default:        return state
  }
}

type CardVariant = 'flat' | 'elevated' | 'outlined' | 'filled'

interface SmartCardProps {
  children: React.ReactNode | ((controls: SmartCardControls) => React.ReactNode)
  variant?: CardVariant
  /** Controlled status — overrides internal state machine */
  status?: CardState
  statusMessage?: string
  interactive?: boolean
  onClick?: () => void
  padding?: 'none' | 'sm' | 'md' | 'lg'
  className?: string
  style?: React.CSSProperties
  'aria-label'?: string
}

export interface SmartCardControls {
  load: (message?: string) => void
  succeed: (message?: string) => void
  fail: (message: string) => void
  reset: () => void
  status: CardState
}

const VARIANT_STYLES: Record<CardVariant, React.CSSProperties> = {
  flat:     { background: 'var(--ux-surface-card)', boxShadow: 'none' },
  elevated: { background: 'var(--ux-surface-card)', boxShadow: 'var(--ux-shadow-md)' },
  outlined: { background: 'transparent', boxShadow: 'none', border: '1px solid var(--ux-border)' },
  filled:   { background: 'var(--ux-surface-raised)', boxShadow: 'none' },
}

const PAD_MAP: Record<string, string> = {
  none: '0',
  sm: 'var(--ux-space-3)',
  md: 'var(--ux-space-6)',
  lg: 'var(--ux-space-8)',
}

const STATUS_OVERLAY: Record<Exclude<CardState, 'idle'>, { bg: string; icon: string; color: string }> = {
  loading: { bg: 'rgba(var(--ux-brand-rgb), 0.06)', icon: '◌', color: 'var(--ux-accent)' },
  success: { bg: 'rgba(var(--ux-success-rgb), 0.08)', icon: '✓', color: 'var(--ux-success)' },
  error:   { bg: 'rgba(var(--ux-danger-rgb), 0.08)', icon: '✕', color: 'var(--ux-danger)' },
}

export function SmartCard({
  children,
  variant = 'elevated',
  status: controlledStatus,
  statusMessage,
  interactive = false,
  onClick,
  padding = 'md',
  className = '',
  style,
  'aria-label': ariaLabel,
}: SmartCardProps) {
  const [state, dispatch] = useReducer(cardReducer, { status: 'idle' })
  const status = controlledStatus ?? state.status
  const message = statusMessage ?? state.message

  const controls: SmartCardControls = {
    load:    useCallback((msg?: string) => dispatch({ type: 'LOAD', message: msg }), []),
    succeed: useCallback((msg?: string) => dispatch({ type: 'SUCCEED', message: msg }), []),
    fail:    useCallback((msg: string)  => dispatch({ type: 'FAIL', message: msg }), []),
    reset:   useCallback(() => dispatch({ type: 'RESET' }), []),
    status,
  }

  const overlay = status !== 'idle' ? STATUS_OVERLAY[status] : null

  return (
    <div
      className={`ux-smart-card ${className}`}
      role={interactive && onClick ? 'button' : undefined}
      tabIndex={interactive && onClick ? 0 : undefined}
      aria-label={ariaLabel}
      aria-busy={status === 'loading'}
      onClick={interactive && onClick ? onClick : undefined}
      onKeyDown={interactive && onClick ? e => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick() }
      } : undefined}
      style={{
        position: 'relative',
        borderRadius: 'var(--ux-radius-lg)',
        padding: PAD_MAP[padding],
        transition: 'box-shadow var(--ux-dur-base) var(--ux-ease-out), transform var(--ux-dur-fast) var(--ux-ease-out)',
        cursor: interactive && onClick ? 'pointer' : 'default',
        outline: 'none',
        overflow: 'hidden',
        ...VARIANT_STYLES[variant],
        ...style,
      }}
    >
      {overlay && (
        <div
          role="status"
          aria-live="polite"
          aria-label={message ? `${status}: ${message}` : status}
          style={{
            position: 'absolute',
            inset: 0,
            background: overlay.bg,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 'var(--ux-space-2)',
            zIndex: 2,
            pointerEvents: 'none',
          }}
        >
          <span
            aria-hidden="true"
            style={{
              fontSize: 'var(--ux-text-2xl)',
              color: overlay.color,
              animation: status === 'loading' ? 'ux-spin 0.8s linear infinite' : undefined,
            }}
          >
            {overlay.icon}
          </span>
          {message && (
            <span style={{ fontSize: 'var(--ux-text-sm)', color: overlay.color }}>{message}</span>
          )}
        </div>
      )}
      {typeof children === 'function' ? children(controls) : children}
    </div>
  )
}
