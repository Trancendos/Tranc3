import React, { useEffect, useRef, useState, useMemo } from 'react'
import { Bell, Zap, Workflow, AlertTriangle, Activity, Mail } from 'lucide-react'
import { useSSE, SSEEvent } from '../../hooks/useSSE'
import { useNotificationsSSE, LiveNotification } from '../../hooks/useNotificationsSSE'

type BellItem =
  | { kind: 'sse';  id: string; type: string; preview: string; ts: number }
  | { kind: 'live'; id: string; type: string; title: string; message: string; ts: number; read: boolean }

function sseToItem(evt: SSEEvent, idx: number): BellItem {
  let preview = ''
  if (typeof evt.data === 'string') preview = evt.data.slice(0, 80)
  else { try { preview = JSON.stringify(evt.data).slice(0, 80) } catch { preview = '' } }
  return { kind: 'sse', id: `sse-${evt.id}-${idx}`, type: evt.type, preview, ts: Date.now() - idx * 100 }
}

function liveToItem(n: LiveNotification): BellItem {
  return { kind: 'live', id: n.id, type: n.type, title: n.title, message: n.message, ts: new Date(n.timestamp).getTime(), read: n.read }
}

const TYPE_STYLE: Record<string, { cls: string; icon: React.ReactNode }> = {
  alert:             { cls: 'bg-red-900/60 text-red-300',     icon: <AlertTriangle size={10} /> },
  error:             { cls: 'bg-red-900/60 text-red-300',     icon: <AlertTriangle size={10} /> },
  warning:           { cls: 'bg-amber-900/60 text-amber-300', icon: <AlertTriangle size={10} /> },
  workflow_complete: { cls: 'bg-cyan-900/60 text-cyan-300',   icon: <Workflow size={10} /> },
  mcp_tool_call:     { cls: 'bg-purple-900/60 text-purple-300', icon: <Zap size={10} /> },
  health_change:     { cls: 'bg-emerald-900/60 text-emerald-300', icon: <Activity size={10} /> },
  info:              { cls: 'bg-blue-900/60 text-blue-300',   icon: <Mail size={10} /> },
  success:           { cls: 'bg-emerald-900/60 text-emerald-300', icon: <Activity size={10} /> },
}
const DEFAULT_STYLE = { cls: 'bg-slate-700 text-slate-300', icon: <Mail size={10} /> }

function typeStyle(t: string) { return TYPE_STYLE[t] ?? DEFAULT_STYLE }

function typeLabel(t: string) {
  const MAP: Record<string, string> = {
    mcp_tool_call: 'Tool', workflow_complete: 'Workflow', alert: 'Alert',
    health_change: 'Health', message: 'Msg', info: 'Info', warning: 'Warn',
    error: 'Error', success: 'Done',
  }
  return MAP[t] ?? t
}

export default function NotificationBell() {
  const { events } = useSSE()
  const { notifications, unreadCount, markAllRead: markLiveAllRead, connected } = useNotificationsSSE()

  const [open, setOpen]         = useState(false)
  const [sseReadIdx, setSseReadIdx] = useState(0)
  const panelRef = useRef<HTMLDivElement>(null)

  const sseUnread = Math.max(0, events.length - sseReadIdx)
  const totalUnread = sseUnread + unreadCount

  const items = useMemo<BellItem[]>(() => {
    const sseItems = events.slice(-10).map(sseToItem)
    const liveItems = notifications.slice(0, 20).map(liveToItem)
    return [...sseItems, ...liveItems].sort((a, b) => b.ts - a.ts).slice(0, 15)
  }, [events, notifications])

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const handleMarkAllRead = () => {
    setSseReadIdx(events.length)
    markLiveAllRead()
    setOpen(false)
  }

  return (
    <div className="relative" ref={panelRef}>
      <button
        onClick={() => setOpen(o => !o)}
        aria-label={`Notifications${totalUnread > 0 ? `, ${totalUnread} unread` : ''}`}
        className="relative p-2 rounded-lg text-gray-400 hover:text-white hover:bg-gray-700 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-purple-500"
      >
        <Bell className="w-5 h-5" />
        {totalUnread > 0 && (
          <span className="absolute top-1 right-1 min-w-[16px] h-4 flex items-center justify-center rounded-full bg-purple-600 text-white text-[10px] font-bold px-1 leading-none">
            {totalUnread > 99 ? '99+' : totalUnread}
          </span>
        )}
        {connected && (
          <span className="absolute bottom-1 right-1 w-1.5 h-1.5 rounded-full bg-emerald-400" aria-hidden="true" />
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-80 bg-gray-800 border border-gray-700 rounded-xl shadow-2xl z-50 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
            <div className="flex items-center gap-2">
              <span className="text-white font-semibold text-sm">Notifications</span>
              {connected && <span className="ux-nano-dot ux-nano-dot--ok" aria-label="Live connected" />}
            </div>
            {totalUnread > 0 && (
              <button onClick={handleMarkAllRead} className="text-xs text-cyan-400 hover:text-cyan-300 transition-colors">
                Mark all read
              </button>
            )}
          </div>

          <div className="max-h-80 overflow-y-auto divide-y divide-gray-700/60">
            {items.length === 0 ? (
              <p className="text-gray-500 text-sm text-center py-6">No notifications yet</p>
            ) : (
              items.map(item => {
                const { cls, icon } = typeStyle(item.type)
                return (
                  <div
                    key={item.id}
                    className={`px-4 py-3 transition-colors hover:bg-slate-700/40 ${
                      item.kind === 'live' && !item.read ? 'border-l-2 border-purple-500' : ''
                    }`}
                  >
                    <div className="flex items-center gap-1.5 mb-1">
                      <span className={`inline-flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded ${cls}`}>
                        {icon}{typeLabel(item.type)}
                      </span>
                      <span className="text-slate-500 text-[10px] ml-auto">
                        {new Date(item.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                    {item.kind === 'live' ? (
                      <>
                        <p className="text-slate-200 text-xs font-medium truncate">{item.title}</p>
                        {item.message && <p className="text-slate-400 text-xs truncate">{item.message}</p>}
                      </>
                    ) : (
                      <p className="text-slate-300 text-xs truncate">{item.preview}</p>
                    )}
                  </div>
                )
              })
            )}
          </div>
        </div>
      )}
    </div>
  )
}
