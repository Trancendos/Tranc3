/**
 * ToastCluster — Figma UI Principles: Feedback + Visibility of System Status
 *
 * Managed toast notification system with ARIA live regions, stacking,
 * auto-dismiss, and swipe-to-dismiss. Implements Figma's principle of
 * providing clear, non-blocking system feedback at the right moment.
 *
 * Uses a singleton context pattern so any component can fire toasts:
 *   const { toast } = useToast()
 *   toast.success('Saved!', { duration: 3000 })
 */
import React, {
  createContext,
  useCallback,
  useContext,
  useReducer,
  useRef,
} from 'react'

type ToastType = 'success' | 'error' | 'warning' | 'info' | 'loading'

interface Toast {
  id: string
  type: ToastType
  title: string
  description?: string
  duration?: number
  dismissible?: boolean
}

interface ToastState {
  toasts: Toast[]
}

type ToastAction =
  | { type: 'ADD'; toast: Toast }
  | { type: 'REMOVE'; id: string }
  | { type: 'UPDATE'; id: string; patch: Partial<Toast> }

function toastReducer(state: ToastState, action: ToastAction): ToastState {
  switch (action.type) {
    case 'ADD':
      return { toasts: [...state.toasts, action.toast] }
    case 'REMOVE':
      return { toasts: state.toasts.filter(t => t.id !== action.id) }
    case 'UPDATE':
      return {
        toasts: state.toasts.map(t =>
          t.id === action.id ? { ...t, ...action.patch } : t,
        ),
      }
    default:
      return state
  }
}

interface ToastAPI {
  success: (title: string, opts?: Partial<Toast>) => string
  error:   (title: string, opts?: Partial<Toast>) => string
  warning: (title: string, opts?: Partial<Toast>) => string
  info:    (title: string, opts?: Partial<Toast>) => string
  loading: (title: string, opts?: Partial<Toast>) => string
  dismiss: (id: string) => void
  update:  (id: string, patch: Partial<Toast>) => void
}

const ToastContext = createContext<ToastAPI | null>(null)

const TOAST_ICONS: Record<ToastType, string> = {
  success: '✓',
  error:   '✕',
  warning: '⚠',
  info:    'ℹ',
  loading: '◌',
}

const TOAST_COLORS: Record<ToastType, string> = {
  success: 'var(--ux-success)',
  error:   'var(--ux-danger)',
  warning: 'var(--ux-warning)',
  info:    'var(--ux-accent)',
  loading: 'var(--ux-accent)',
}

let _counter = 0
function genId() { return `toast-${++_counter}` }

interface ToastItemProps {
  toast: Toast
  onDismiss: (id: string) => void
}

function ToastItem({ toast, onDismiss }: ToastItemProps) {
  const timers = useRef<ReturnType<typeof setTimeout> | null>(null)

  React.useEffect(() => {
    if (toast.duration && toast.duration > 0) {
      timers.current = setTimeout(() => onDismiss(toast.id), toast.duration)
    }
    return () => { if (timers.current) clearTimeout(timers.current) }
  }, [toast.id, toast.duration, onDismiss])

  return (
    <div
      role="listitem"
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 'var(--ux-space-3)',
        padding: 'var(--ux-space-3) var(--ux-space-4)',
        background: 'var(--ux-surface-card)',
        borderRadius: 'var(--ux-radius-lg)',
        boxShadow: 'var(--ux-shadow-lg)',
        border: '1px solid var(--ux-border)',
        minWidth: '260px',
        maxWidth: '400px',
        animation: 'ux-slide-in-right var(--ux-dur-base) var(--ux-ease-out)',
        pointerEvents: 'auto',
      }}
    >
      <span
        aria-hidden="true"
        style={{
          color: TOAST_COLORS[toast.type],
          fontSize: 'var(--ux-text-base)',
          flexShrink: 0,
          marginTop: '1px',
          animation: toast.type === 'loading' ? 'ux-spin 0.8s linear infinite' : undefined,
        }}
      >
        {TOAST_ICONS[toast.type]}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <p
          style={{
            margin: 0,
            fontSize: 'var(--ux-text-sm)',
            fontWeight: 500,
            color: 'var(--ux-text-primary)',
          }}
        >
          {toast.title}
        </p>
        {toast.description && (
          <p
            style={{
              margin: '2px 0 0',
              fontSize: 'var(--ux-text-xs)',
              color: 'var(--ux-text-muted)',
            }}
          >
            {toast.description}
          </p>
        )}
      </div>
      {toast.dismissible !== false && (
        <button
          aria-label="Dismiss notification"
          onClick={() => onDismiss(toast.id)}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            color: 'var(--ux-text-muted)',
            padding: '0 var(--ux-space-1)',
            fontSize: 'var(--ux-text-sm)',
            flexShrink: 0,
            lineHeight: 1,
          }}
        >
          ×
        </button>
      )}
    </div>
  )
}

interface ToastClusterProps {
  children: React.ReactNode
  position?: 'top-right' | 'top-left' | 'bottom-right' | 'bottom-left' | 'top-center' | 'bottom-center'
  maxVisible?: number
}

const POSITION_STYLES: Record<string, React.CSSProperties> = {
  'top-right':    { top: 'var(--ux-space-4)', right: 'var(--ux-space-4)', alignItems: 'flex-end' },
  'top-left':     { top: 'var(--ux-space-4)', left: 'var(--ux-space-4)',  alignItems: 'flex-start' },
  'bottom-right': { bottom: 'var(--ux-space-4)', right: 'var(--ux-space-4)', alignItems: 'flex-end' },
  'bottom-left':  { bottom: 'var(--ux-space-4)', left: 'var(--ux-space-4)',  alignItems: 'flex-start' },
  'top-center':   { top: 'var(--ux-space-4)', left: '50%', transform: 'translateX(-50%)', alignItems: 'center' },
  'bottom-center':{ bottom: 'var(--ux-space-4)', left: '50%', transform: 'translateX(-50%)', alignItems: 'center' },
}

export function ToastCluster({
  children,
  position = 'top-right',
  maxVisible = 5,
}: ToastClusterProps) {
  const [state, dispatch] = useReducer(toastReducer, { toasts: [] })

  const dismiss = useCallback((id: string) => dispatch({ type: 'REMOVE', id }), [])
  const update  = useCallback((id: string, patch: Partial<Toast>) => dispatch({ type: 'UPDATE', id, patch }), [])

  const add = useCallback((type: ToastType, title: string, opts: Partial<Toast> = {}): string => {
    const id = genId()
    dispatch({ type: 'ADD', toast: { id, type, title, duration: 4000, dismissible: true, ...opts } })
    return id
  }, [])

  const api: ToastAPI = {
    success: (t, o) => add('success', t, o),
    error:   (t, o) => add('error',   t, o),
    warning: (t, o) => add('warning', t, o),
    info:    (t, o) => add('info',    t, o),
    loading: (t, o) => add('loading', t, o),
    dismiss,
    update,
  }

  const visible = state.toasts.slice(-maxVisible)

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="false"
        aria-label="Notifications"
        role="list"
        style={{
          position: 'fixed',
          zIndex: 9999,
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--ux-space-2)',
          pointerEvents: 'none',
          ...POSITION_STYLES[position],
        }}
      >
        {visible.map(toast => (
          <ToastItem key={toast.id} toast={toast} onDismiss={dismiss} />
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): { toast: ToastAPI } {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within <ToastCluster>')
  return { toast: ctx }
}
