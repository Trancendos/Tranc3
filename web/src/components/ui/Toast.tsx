import React from 'react'
import { CheckCircle, XCircle, Info, X } from 'lucide-react'
import type { Toast, ToastType } from '../../hooks/useToast'

const STYLES: Record<ToastType, string> = {
  success: 'bg-green-900/90 border-green-700 text-green-200',
  error:   'bg-red-900/90 border-red-700 text-red-200',
  info:    'bg-indigo-900/90 border-indigo-700 text-indigo-200',
}

function ToastIcon({ type }: { type: ToastType }) {
  if (type === 'success') return <CheckCircle size={16} aria-hidden="true" />
  if (type === 'error')   return <XCircle     size={16} aria-hidden="true" />
  return                         <Info        size={16} aria-hidden="true" />
}

interface Props {
  toasts: Toast[]
  removeToast: (id: number) => void
}

export default function ToastContainer({ toasts, removeToast }: Props) {
  if (toasts.length === 0) return null
  return (
    <div
      aria-live="polite"
      aria-atomic="false"
      aria-label="Notifications"
      className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm w-full pointer-events-none"
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          role={t.type === 'error' ? 'alert' : 'status'}
          className={`flex items-center gap-3 px-4 py-3 rounded-lg border shadow-lg pointer-events-auto ${STYLES[t.type]}`}
        >
          <ToastIcon type={t.type} />
          <span className="flex-1 text-sm">{t.message}</span>
          <button
            onClick={() => removeToast(t.id)}
            aria-label="Dismiss notification"
            className="flex-shrink-0 opacity-70 hover:opacity-100 transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-current rounded"
          >
            <X size={14} aria-hidden="true" />
          </button>
        </div>
      ))}
    </div>
  )
}
