/**
 * StatusIndicator — Nielsen Heuristic #1: Visibility of System Status
 *
 * Keeps users informed through immediate, continuous feedback.
 * Supports loading, success, error, warning, and info states
 * with live ARIA announcements and accessible icons.
 */
import React from 'react'

type StatusType = 'idle' | 'loading' | 'success' | 'error' | 'warning' | 'info'

interface StatusIndicatorProps {
  status: StatusType
  message?: string
  /** Whether to announce changes to screen readers */
  announce?: boolean
  className?: string
  compact?: boolean
}

const STATUS_CONFIG: Record<StatusType, { icon: string; label: string; color: string }> = {
  idle:    { icon: '○', label: 'Idle',    color: 'var(--ux-text-muted)' },
  loading: { icon: '◌', label: 'Loading', color: 'var(--ux-accent)' },
  success: { icon: '✓', label: 'Success', color: 'var(--ux-success)' },
  error:   { icon: '✕', label: 'Error',   color: 'var(--ux-danger)' },
  warning: { icon: '⚠', label: 'Warning', color: 'var(--ux-warning)' },
  info:    { icon: 'ℹ', label: 'Info',    color: 'var(--ux-accent)' },
}

export function StatusIndicator({
  status, message, announce = true, className = '', compact = false
}: StatusIndicatorProps) {
  const cfg = STATUS_CONFIG[status]
  const isLoading = status === 'loading'

  return (
    <span
      role={announce ? 'status' : undefined}
      aria-live={announce ? 'polite' : undefined}
      aria-busy={isLoading}
      aria-label={message ? `${cfg.label}: ${message}` : cfg.label}
      className={className}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 'var(--ux-space-2)',
        fontSize: compact ? 'var(--ux-text-xs)' : 'var(--ux-text-sm)',
        color: cfg.color,
        transition: 'color var(--ux-dur-base) var(--ux-ease-out)',
      }}
    >
      <span
        aria-hidden="true"
        style={{
          animation: isLoading ? 'ux-spin 0.8s linear infinite' : undefined,
          display: 'inline-block',
          lineHeight: 1,
        }}
      >
        {cfg.icon}
      </span>
      {!compact && message && (
        <span>{message}</span>
      )}
    </span>
  )
}
