import React, { useEffect, useState, useCallback } from 'react'
import { Bell, RefreshCw, CheckCircle, XCircle, Mail, Zap, Radio } from 'lucide-react'
import useReactiveQuery from '../hooks/useReactiveQuery'
import { useNotificationsSSE, type LiveNotification } from '../hooks/useNotificationsSSE'
import { useAnalytics } from '../hooks/useAnalytics'

const API = (import.meta.env.VITE_API_URL as string | undefined) ?? ''
const NOTIFICATIONS_API = `${API}/notifications`

interface Channel {
  id: string
  name: string
  type: 'email' | 'webhook' | 'sms'
  status: 'active' | 'inactive' | 'error'
  provider?: string
  daily_used?: number
  daily_limit?: number
  last_sent?: string
}

interface ChannelsResponse {
  channels: Channel[]
}

const FALLBACK_CHANNELS: Channel[] = [
  { id: 'resend',      name: 'Resend',            type: 'email', status: 'active', provider: 'Resend',      daily_used: 0, daily_limit: 100  },
  { id: 'mailersend',  name: 'MailerSend',         type: 'email', status: 'active', provider: 'MailerSend',  daily_used: 0, daily_limit: 400  },
  { id: 'brevo',       name: 'Brevo',              type: 'email', status: 'active', provider: 'Brevo',       daily_used: 0, daily_limit: 1000 },
  { id: 'sendgrid',    name: 'SendGrid',           type: 'email', status: 'inactive', provider: 'SendGrid',  daily_used: 0, daily_limit: 100  },
]

function channelIcon(type: Channel['type']) {
  if (type === 'email')   return <Mail size={14} aria-hidden="true" />
  if (type === 'webhook') return <Zap  size={14} aria-hidden="true" />
  return                         <Bell size={14} aria-hidden="true" />
}

function statusColor(s: Channel['status']) {
  if (s === 'active')   return 'text-emerald-400'
  if (s === 'inactive') return 'text-slate-500'
  return 'text-red-400'
}

function notifBorder(type: LiveNotification['type']) {
  if (type === 'success') return 'border-emerald-600/60 bg-emerald-900/10'
  if (type === 'warning') return 'border-amber-600/60  bg-amber-900/10'
  if (type === 'error')   return 'border-red-600/60    bg-red-900/10'
  return 'border-indigo-600/60 bg-indigo-900/10'
}

function typeLabel(type: LiveNotification['type']) {
  const map = { success: 'Success', warning: 'Warning', error: 'Error', info: 'Info' }
  return map[type] ?? type
}

function typeChip(type: LiveNotification['type']) {
  const base = 'text-[10px] font-semibold px-1.5 py-0.5 rounded'
  if (type === 'success') return `${base} bg-emerald-900/60 text-emerald-300`
  if (type === 'warning') return `${base} bg-amber-900/60  text-amber-300`
  if (type === 'error')   return `${base} bg-red-900/60    text-red-300`
  return `${base} bg-indigo-900/60 text-indigo-300`
}

export default function NotificationsPage() {
  const { data: channelData } = useReactiveQuery<ChannelsResponse>({
    url: `${NOTIFICATIONS_API}/channels`,
    intervalMs: 60_000,
    transform: (raw) => raw as ChannelsResponse,
  })

  const channels = channelData?.channels ?? FALLBACK_CHANNELS

  const { connected, notifications, unreadCount, markRead, markAllRead, clearAll } = useNotificationsSSE()
  const { trackNotificationRead } = useAnalytics()

  const handleMarkAllRead = useCallback(() => {
    trackNotificationRead(unreadCount)
    markAllRead()
  }, [markAllRead, trackNotificationRead, unreadCount])

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Bell size={22} className="text-indigo-400" aria-hidden="true" />
            Alerts &amp; Notifications
          </h1>
          <div className="flex items-center gap-2 mt-1">
            <span className={`ux-nano-dot ${connected ? 'ux-nano-dot--ok' : 'ux-nano-dot--warn'}`} />
            <p className="text-slate-400 text-sm">
              {connected ? 'Live stream connected' : 'Reconnecting…'}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          {unreadCount > 0 && (
            <button
              onClick={handleMarkAllRead}
              className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm text-slate-300 transition-colors"
            >
              Mark all read
            </button>
          )}
          {notifications.length > 0 && (
            <button
              onClick={clearAll}
              className="px-4 py-2 bg-slate-800 hover:bg-slate-700 rounded-lg text-sm text-slate-400 transition-colors"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Email Channels */}
      <div>
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-widest mb-3">
          Email Channels — Zero-Cost Rotation
        </h2>
        <div className="ux-cluster" style={{ '--ux-cluster-min': '200px' } as React.CSSProperties}>
          {channels.map((ch) => {
            const used = ch.daily_used ?? 0
            const limit = ch.daily_limit ?? 0
            const pct = limit > 0 ? Math.round((used / limit) * 100) : 0
            return (
              <div
                key={ch.id}
                aria-label={`${ch.name} — ${ch.status}`}
                className="ux-liquid rounded-xl border border-slate-700/60 bg-slate-900/70 p-4"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2 text-slate-200 text-sm font-medium">
                    {channelIcon(ch.type)}
                    {ch.name}
                  </div>
                  <span className={`text-xs flex items-center gap-1 ${statusColor(ch.status)}`}>
                    {ch.status === 'active'
                      ? <CheckCircle size={13} aria-hidden="true" />
                      : <XCircle    size={13} aria-hidden="true" />}
                  </span>
                </div>
                {limit > 0 && (
                  <>
                    <div
                      role="progressbar"
                      aria-valuenow={pct}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-label={`${ch.name}: ${pct}% of daily quota`}
                      className="h-1.5 bg-slate-700 rounded-full overflow-hidden mb-1"
                    >
                      <div
                        className={`h-full rounded-full transition-all ${pct > 90 ? 'bg-red-500' : pct > 70 ? 'bg-amber-500' : 'bg-emerald-500'}`}
                        style={{ width: `${Math.min(pct, 100)}%` }}
                      />
                    </div>
                    <p className="text-slate-500 text-xs">{used}/{limit} today ({pct}%)</p>
                  </>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Live Feed */}
      <div>
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-widest mb-3 flex items-center gap-2">
          <Radio size={14} className={connected ? 'text-emerald-400' : 'text-slate-500'} />
          Live Feed
          {unreadCount > 0 && (
            <span aria-label={`${unreadCount} unread`} className="text-xs bg-red-500 text-white rounded-full px-2 py-0.5 tabular-nums">
              {unreadCount}
            </span>
          )}
        </h2>

        {notifications.length === 0 ? (
          <div role="status" className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-8 text-center">
            <Bell size={32} aria-hidden="true" className="mx-auto mb-2 text-slate-600" />
            <p className="text-slate-500 text-sm">
              {connected ? 'Waiting for notifications…' : 'Connecting to live stream…'}
            </p>
          </div>
        ) : (
          <ol aria-label="Live notification feed" aria-live="polite" className="space-y-2 list-none">
            {notifications.map((n) => (
              <li
                key={n.id}
                aria-label={`${typeLabel(n.type)}: ${n.title}${n.read ? ', read' : ', unread'}`}
                className={`border rounded-xl p-4 transition-opacity ${notifBorder(n.type)} ${n.read ? 'opacity-50' : ''}`}
                onClick={() => markRead(n.id)}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className={typeChip(n.type)}>{typeLabel(n.type)}</span>
                      {!n.read && <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 shrink-0" aria-label="unread" />}
                    </div>
                    <p className="text-white text-sm font-medium truncate">{n.title}</p>
                    <p className="text-slate-400 text-xs mt-0.5 line-clamp-2">{n.message}</p>
                  </div>
                  <time dateTime={n.timestamp} className="text-slate-500 text-xs whitespace-nowrap shrink-0">
                    {new Date(n.timestamp).toLocaleTimeString()}
                  </time>
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  )
}
