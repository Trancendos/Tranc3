import React, { useEffect, useState, useCallback } from 'react'
import { Bell, RefreshCw, CheckCircle, XCircle, AlertCircle, Mail, Zap } from 'lucide-react'

const CF_NOTIFICATIONS_URL = 'https://tranc3-notifications.luminous-aimastermind.workers.dev'

interface Channel {
  id: string
  name: string
  type: 'email' | 'webhook' | 'sms'
  status: 'active' | 'inactive' | 'error'
  provider?: string
  dailyUsed?: number
  dailyLimit?: number
  lastSent?: string
}

interface Notification {
  id: string
  title: string
  message: string
  type: 'info' | 'warning' | 'error' | 'success'
  timestamp: string
  read: boolean
  channel?: string
}

const MOCK_CHANNELS: Channel[] = [
  { id: 'resend', name: 'Resend', type: 'email', status: 'active', provider: 'Resend', dailyUsed: 12, dailyLimit: 100, lastSent: new Date(Date.now() - 3600000).toISOString() },
  { id: 'mailersend', name: 'MailerSend', type: 'email', status: 'active', provider: 'MailerSend', dailyUsed: 0, dailyLimit: 400, lastSent: undefined },
  { id: 'brevo', name: 'Brevo (Sendinblue)', type: 'email', status: 'active', provider: 'Brevo', dailyUsed: 5, dailyLimit: 1000, lastSent: new Date(Date.now() - 7200000).toISOString() },
]

function channelIcon(type: Channel['type']) {
  if (type === 'email') return <Mail size={14} />
  if (type === 'webhook') return <Zap size={14} />
  return <Bell size={14} />
}

function statusColor(s: Channel['status']) {
  if (s === 'active') return 'text-green-400'
  if (s === 'inactive') return 'text-gray-500'
  return 'text-red-400'
}

function notifColor(type: Notification['type']) {
  if (type === 'success') return 'border-green-600 bg-green-900/20'
  if (type === 'warning') return 'border-yellow-600 bg-yellow-900/20'
  if (type === 'error') return 'border-red-600 bg-red-900/20'
  return 'border-indigo-600 bg-indigo-900/20'
}

export default function NotificationsPage() {
  const [channels, setChannels] = useState<Channel[]>(MOCK_CHANNELS)
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [loading, setLoading] = useState(false)
  const [lastRun, setLastRun] = useState<string | null>(null)

  const fetchStatus = useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetch(`${CF_NOTIFICATIONS_URL}/health`, { signal: AbortSignal.timeout(5000) })
      if (r.ok) {
        const body = await r.json().catch(() => ({}))
        if (body.channels) setChannels(body.channels)
        if (body.recent) setNotifications(body.recent)
      }
    } catch { /* use mock data */ }
    setLastRun(new Date().toLocaleTimeString())
    setLoading(false)
  }, [])

  useEffect(() => {
    fetchStatus()
    const iv = setInterval(fetchStatus, 60_000)
    return () => clearInterval(iv)
  }, [fetchStatus])

  const markAllRead = () =>
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })))

  const unread = notifications.filter((n) => !n.read).length

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Bell size={22} className="text-indigo-400" />
            Alerts &amp; Notifications
          </h1>
          <p className="text-gray-400 text-sm mt-1">
            {lastRun ? `Last updated: ${lastRun}` : 'Loading…'}
          </p>
        </div>
        <div className="flex gap-2">
          {unread > 0 && (
            <button
              onClick={markAllRead}
              className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm text-gray-300 transition-colors"
            >
              Mark all read
            </button>
          )}
          <button
            onClick={fetchStatus}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg text-sm text-white transition-colors"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {/* Email Channels */}
      <div className="mb-6">
        <h2 className="text-white font-semibold mb-3">Email Channels (Zero-Cost Rotation)</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {channels.map((ch) => {
            const pct = ch.dailyLimit ? Math.round((ch.dailyUsed ?? 0) / ch.dailyLimit * 100) : 0
            return (
              <div key={ch.id} className="bg-gray-900 border border-gray-700 rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2 text-gray-200 text-sm font-medium">
                    {channelIcon(ch.type)}
                    {ch.name}
                  </div>
                  <span className={`text-xs ${statusColor(ch.status)}`}>
                    {ch.status === 'active' ? <CheckCircle size={14} /> : <XCircle size={14} />}
                  </span>
                </div>
                {ch.dailyLimit != null && (
                  <>
                    <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden mb-1">
                      <div
                        className={`h-full rounded-full transition-all ${
                          pct > 90 ? 'bg-red-500' : pct > 70 ? 'bg-yellow-500' : 'bg-green-500'
                        }`}
                        style={{ width: `${Math.min(pct, 100)}%` }}
                      />
                    </div>
                    <p className="text-gray-500 text-xs">
                      {ch.dailyUsed ?? 0} / {ch.dailyLimit} today ({pct}%)
                    </p>
                  </>
                )}
                {ch.lastSent && (
                  <p className="text-gray-600 text-xs mt-1">
                    Last: {new Date(ch.lastSent).toLocaleTimeString()}
                  </p>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Notification Feed */}
      <div>
        <h2 className="text-white font-semibold mb-3 flex items-center gap-2">
          Recent Alerts
          {unread > 0 && (
            <span className="text-xs bg-red-500 text-white rounded-full px-2 py-0.5">{unread}</span>
          )}
        </h2>
        {notifications.length === 0 ? (
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-8 text-center text-gray-500">
            <Bell size={32} className="mx-auto mb-2 opacity-30" />
            <p>No notifications yet.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {notifications.map((n) => (
              <div
                key={n.id}
                className={`border rounded-lg p-4 ${notifColor(n.type)} ${n.read ? 'opacity-60' : ''}`}
              >
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-white text-sm font-medium">{n.title}</p>
                    <p className="text-gray-400 text-xs mt-0.5">{n.message}</p>
                  </div>
                  <span className="text-gray-500 text-xs whitespace-nowrap ml-4">
                    {new Date(n.timestamp).toLocaleTimeString()}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
