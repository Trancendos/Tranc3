/**
 * ErrorBoundaryCell — Shneiderman Rule 5: Prevent Errors
 *                   + Rule 9: Informative Error Messages (Nielsen Heuristic #9)
 *                   + IxDF: Error Prevention + Recovery UX
 *
 * Adaptive React error boundary with three recovery strategies:
 *   retry   — re-mounts the subtree (transient failures)
 *   fallback — renders a supplied recovery UI
 *   report  — surfaces structured error info for user reporting
 *
 * Implements UpSlide's principle that errors should be caught early, explained
 * plainly (no stack traces), and offer a clear exit. Error messages must:
 *   1. State the problem in plain language
 *   2. Explain consequences (if any)
 *   3. Offer a constructive remedy
 *
 * The cell tracks retry attempts and escalates to the fallback UI after
 * `maxRetries` consecutive failures — preventing infinite mount loops.
 */
import React from 'react'

type RecoveryStrategy = 'retry' | 'fallback' | 'report'

interface ErrorBoundaryCellProps {
  children: React.ReactNode
  fallback?: React.ReactNode
  strategy?: RecoveryStrategy
  maxRetries?: number
  onError?: (error: Error, info: React.ErrorInfo) => void
  /** Plain-language label shown in error UI */
  label?: string
  className?: string
  /** When any value in this array changes the boundary auto-resets */
  resetKeys?: unknown[]
}

interface ErrorBoundaryCellState {
  error: Error | null
  retryCount: number
  errorKey: number
  showFallback: boolean
}

export class ErrorBoundaryCell extends React.Component<ErrorBoundaryCellProps, ErrorBoundaryCellState> {
  constructor(props: ErrorBoundaryCellProps) {
    super(props)
    this.state = { error: null, retryCount: 0, errorKey: 0, showFallback: false }
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryCellState> {
    return { error }
  }

  override componentDidCatch(error: Error, info: React.ErrorInfo) {
    this.props.onError?.(error, info)
  }

  private retry = () => {
    const maxRetries = this.props.maxRetries ?? 3
    if (this.state.retryCount < maxRetries) {
      this.setState(s => ({ error: null, retryCount: s.retryCount + 1, errorKey: s.errorKey + 1 }))
    }
  }

  private reset = () => {
    this.setState({ error: null, retryCount: 0, errorKey: 0, showFallback: false })
  }

  override componentDidUpdate(prevProps: ErrorBoundaryCellProps, prevState: ErrorBoundaryCellState) {
    if (this.state.error && this.props.resetKeys && prevProps.resetKeys) {
      const prevKeys = prevProps.resetKeys ?? []
      const changed = this.props.resetKeys.length !== prevKeys.length || this.props.resetKeys.some((k, i) => k !== prevKeys[i])
      if (changed) this.reset()
    }
    if (prevState.error && !this.state.error && !this.state.showFallback && prevState.retryCount > 0) {
      this.setState({ retryCount: 0 })
    }
    if (this.state.showFallback && !this.props.fallback) {
      this.setState({ showFallback: false })
    }
  }

  override render() {
    const { error, retryCount, errorKey } = this.state
    const { children, fallback, strategy = 'retry', maxRetries = 3, label = 'This section', className = '' } = this.props

    if (!error && !this.state.showFallback) {
      return <React.Fragment key={errorKey}>{children}</React.Fragment>
    }

    if (this.state.showFallback) {
      if (fallback) return <div className={`ux-error-boundary-cell ${className}`}>{fallback}</div>
      return null
    }

    const exhausted = retryCount >= maxRetries

    if (strategy === 'fallback' && fallback) {
      return <div className={`ux-error-boundary-cell ${className}`}>{fallback}</div>
    }

    return (
      <div
        className={`ux-error-boundary-cell ${className}`}
        role="alert"
        aria-live="assertive"
        style={{
          padding: 'var(--ux-space-4)',
          borderRadius: 'var(--ux-radius-md)',
          border: '1px solid rgba(var(--ux-danger-rgb, 207 34 46), 0.3)',
          background: 'rgba(var(--ux-danger-rgb, 207 34 46), 0.04)',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--ux-space-3)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--ux-space-2)' }}>
          <span aria-hidden="true" style={{ fontSize: 'var(--ux-text-xl)', color: 'var(--ux-danger)' }}>⚠</span>
          <div>
            <div style={{ fontWeight: 600, fontSize: 'var(--ux-text-sm)', color: 'var(--ux-text-primary)' }}>
              {label} couldn't load
            </div>
            <div style={{ fontSize: 'var(--ux-text-xs)', color: 'var(--ux-text-muted)', marginTop: '2px' }}>
              {error.message || 'An unexpected error occurred'}
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 'var(--ux-space-2)', flexWrap: 'wrap' }}>
          {!exhausted && strategy === 'retry' && (
            <button
              onClick={this.retry}
              style={{
                padding: 'var(--ux-space-1) var(--ux-space-3)',
                borderRadius: 'var(--ux-radius-sm)',
                border: 'none',
                background: 'var(--ux-accent)',
                color: '#fff',
                fontSize: 'var(--ux-text-sm)',
                cursor: 'pointer',
                fontWeight: 500,
              }}
            >
              Try again {retryCount > 0 ? `(${maxRetries - retryCount} left)` : ''}
            </button>
          )}
          {(exhausted || strategy !== 'retry') && (
            <button
              onClick={this.reset}
              style={{
                padding: 'var(--ux-space-1) var(--ux-space-3)',
                borderRadius: 'var(--ux-radius-sm)',
                border: '1px solid var(--ux-border)',
                background: 'transparent',
                color: 'var(--ux-text-secondary)',
                fontSize: 'var(--ux-text-sm)',
                cursor: 'pointer',
              }}
            >
              Dismiss
            </button>
          )}
          {exhausted && fallback && (
            <button
              onClick={() => this.setState({ error: null, retryCount: 0, errorKey: 0, showFallback: true })}
              style={{
                padding: 'var(--ux-space-1) var(--ux-space-3)',
                borderRadius: 'var(--ux-radius-sm)',
                border: 'none',
                background: 'var(--ux-surface-raised)',
                color: 'var(--ux-text-primary)',
                fontSize: 'var(--ux-text-sm)',
                cursor: 'pointer',
              }}
            >
              Load simplified view
            </button>
          )}
        </div>

        {exhausted && (
          <p style={{ fontSize: 'var(--ux-text-xs)', color: 'var(--ux-text-muted)', margin: 0 }}>
            Still having trouble? Try refreshing the page or contact support.
          </p>
        )}
      </div>
    )
  }
}
