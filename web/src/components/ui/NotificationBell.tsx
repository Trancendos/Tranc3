import React, { useEffect, useRef, useState } from 'react'
import { Bell } from 'lucide-react'
import { useSSE, SSEEvent } from '../../hooks/useSSE'

const EVENT_LABELS: Record<string, string> = {
  mcp_tool_call: 'Tool Call',
  workflow_complete: 'Workflow',
  alert: 'Alert',
  health_change: 'Health',
  message: 'Message',
}

function eventLabel(type: string): string {
  return EVENT_LABELS[type] ?? type
}

function dataPreview(data: unknown): string {
  if (typeof data === 'string') return data.slice(0, 80)
  try { return JSON.stringify(data).slice(0, 80) } catch { return String(data) }
}

export default function NotificationBell() {
  const { events } = useSSE()
  const [open, setOpen] = useState(false)
  const [readCount, setReadCount] = useState(0)
  const panelRef = useRef<HTMLDivElement>(null)

  const unread = Math.max(0, events.length - readCount)
  const recent = events.slice(-10).reverse()

  // Close on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const markAllRead = () => {
    setReadCount(events.length)
    setOpen(false)
  }

  return (
    <div className="relative" ref={panelRef}>
      <button
        onClick={() => setOpen(o => !o)}
        aria-label={`Notifications${unread > 0 ? `, ${unread} unread` : ''}`}
        className="relative p-2 rounded-lg text-gray-400 hover:text-white hover:bg-gray-700 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-purple-500"
      >
        <Bell className="w-5 h-5" />
        {unread > 0 && (
          <span className="absolute top-1 right-1 min-w-[16px] h-4 flex items-center justify-center rounded-full bg-purple-600 text-white text-[10px] font-bold px-1 leading-none">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-80 bg-gray-800 border border-gray-700 rounded-xl shadow-2xl z-50 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
            <span className="text-white font-semibold text-sm">Notifications</span>
            {unread > 0 && (
              <button
                onClick={markAllRead}
                className="text-xs text-cyan-400 hover:text-cyan-300 transition-colors"
              >
                Mark all read
              </button>
            )}
          </div>

          <div className="max-h-80 overflow-y-auto divide-y divide-gray-700">
            {recent.length === 0 ? (
              <p className="text-gray-500 text-sm text-center py-6">No notifications yet</p>
            ) : (
              recent.map((evt: SSEEvent, idx: number) => (
                <div key={evt.id + idx} className="px-4 py-3 hover:bg-gray-750 transition-colors">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`text-xs font-semibold px-1.5 py-0.5 rounded ${
                      evt.type === 'alert' ? 'bg-red-900/60 text-red-300' :
                      evt.type === 'workflow_complete' ? 'bg-cyan-900/60 text-cyan-300' :
                      evt.type === 'mcp_tool_call' ? 'bg-purple-900/60 text-purple-300' :
                      'bg-gray-700 text-gray-300'
                    }`}>
                      {eventLabel(evt.type)}
                    </span>
                  </div>
                  <p className="text-gray-300 text-xs truncate">{dataPreview(evt.data)}</p>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}
