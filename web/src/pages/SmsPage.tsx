import React, { useCallback, useEffect, useState } from 'react'
import { MessageSquare, RefreshCw, RotateCcw, CheckCircle, XCircle, Clock } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const SMS_API = '/sms-svc'
const INTERNAL = { 'X-Internal-Secret': 'dev-secret' }

interface SmsMessage {
  id: number
  to_number: string
  message: string
  status: string
  provider: string
  retry_count: number
  queued_at: number
  sent_at: number | null
  error: string | null
}

export default function SmsPage() {
  const { trackPageView } = useAnalytics()
  const [pending, setPending] = useState(0)
  const [sent, setSent] = useState(0)
  const [failed, setFailed] = useState(0)
  const [provider, setProvider] = useState('')
  const [messages, setMessages] = useState<SmsMessage[]>([])
  const [total, setTotal] = useState(0)
  const [byProvider, setByProvider] = useState<{ provider: string; c: number }[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState('')

  useEffect(() => { trackPageView('/sms') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = statusFilter ? `?status=${statusFilter}&limit=50` : '?limit=50'
      const [hRes, oRes, sRes] = await Promise.all([
        fetch(`${SMS_API}/health`),
        fetch(`${SMS_API}/outbox${params}`, { headers: INTERNAL }),
        fetch(`${SMS_API}/stats`, { headers: INTERNAL }),
      ])
      if (!hRes.ok) throw new Error('Service unavailable')
      const [h, o, s] = await Promise.all([hRes.json(), oRes.ok ? oRes.json() : null, sRes.ok ? sRes.json() : null])
      setPending(h.pending ?? 0)
      setSent(h.sent ?? 0)
      setFailed(h.failed ?? 0)
      setProvider(h.provider ?? '')
      if (o) { setMessages(o.messages ?? []); setTotal(o.total ?? 0) }
      if (s) setByProvider(s.by_provider ?? [])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => { loadData() }, [loadData])

  const retrySms = async (id: number) => {
    try {
      await fetch(`${SMS_API}/outbox/${id}/retry`, { method: 'POST', headers: INTERNAL })
      loadData()
    } catch { /* ignore */ }
  }

  const fmt = (ts: number) => {
    try { return new Date(ts * 1000).toLocaleString() } catch { return String(ts) }
  }

  const STATUS_STYLE: Record<string, string> = {
    sent:    'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
    pending: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
    failed:  'bg-red-500/20 text-red-300 border-red-500/30',
  }

  const STATUS_ICON: Record<string, React.ReactNode> = {
    sent:    <CheckCircle size={13} className="text-emerald-400" />,
    pending: <Clock size={13} className="text-amber-400" />,
    failed:  <XCircle size={13} className="text-red-400" />,
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <MessageSquare size={22} className="text-slate-400" /> SMS Gateway
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">SMS outbox with multi-provider routing and delivery tracking</p>
        </div>
        <button
          onClick={loadData}
          disabled={loading}
          className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-300 hover:text-white disabled:opacity-50 transition-colors"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-lg bg-red-500/10 border border-red-500/30 px-4 py-3 text-sm text-red-300">
          {error} — is sms-service running on port 8019?
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-4 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Provider</p>
          <p className="text-lg font-bold text-slate-200 truncate">{provider || '—'}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Pending</p>
          <p className="text-2xl font-bold text-amber-400">{pending}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Sent</p>
          <p className="text-2xl font-bold text-emerald-400">{sent}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Failed</p>
          <p className={`text-2xl font-bold ${failed > 0 ? 'text-red-400' : 'text-slate-300'}`}>{failed}</p>
        </div>
      </div>

      {/* Provider breakdown */}
      {byProvider.length > 0 && (
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <h2 className="text-sm font-semibold text-white mb-3">By Provider</h2>
          <div className="flex flex-wrap gap-2">
            {byProvider.map(({ provider: p, c }) => (
              <span key={p} className="text-xs px-2 py-1 rounded bg-slate-800 text-slate-300 border border-slate-700/60">
                {p}: <span className="font-bold text-white">{c}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Filter */}
      <div className="flex items-center gap-3">
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:outline-none"
        >
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="sent">Sent</option>
          <option value="failed">Failed</option>
        </select>
        <span className="text-xs text-slate-500">{total} total</span>
      </div>

      {/* Outbox table */}
      <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-slate-500 text-sm">Loading…</div>
        ) : messages.length === 0 ? (
          <div className="p-8 text-center text-slate-500 text-sm">No messages in outbox.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700/60 text-xs text-slate-500 uppercase tracking-wider">
                  <th className="text-left px-4 py-2">Status</th>
                  <th className="text-left px-4 py-2">To</th>
                  <th className="text-left px-4 py-2">Message</th>
                  <th className="text-left px-4 py-2">Provider</th>
                  <th className="text-right px-4 py-2">Queued</th>
                  <th className="text-right px-4 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {messages.map(m => (
                  <tr key={m.id} className="border-b border-slate-800 hover:bg-slate-800/30 transition-colors">
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-1.5">
                        {STATUS_ICON[m.status] ?? null}
                        <span className={`text-xs px-1.5 py-0.5 rounded border ${STATUS_STYLE[m.status] ?? 'bg-slate-700/40 text-slate-400 border-slate-600/30'}`}>
                          {m.status}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-slate-300 font-mono">{m.to_number}</td>
                    <td className="px-4 py-2.5 text-xs text-slate-400 max-w-xs truncate">{m.message}</td>
                    <td className="px-4 py-2.5 text-xs text-indigo-300">{m.provider}</td>
                    <td className="px-4 py-2.5 text-right text-xs text-slate-500 whitespace-nowrap">{fmt(m.queued_at)}</td>
                    <td className="px-4 py-2.5 text-right">
                      {m.status === 'failed' && (
                        <button
                          onClick={() => retrySms(m.id)}
                          className="flex items-center gap-1 text-xs text-amber-400 hover:text-amber-300 transition-colors ml-auto"
                        >
                          <RotateCcw size={11} /> retry
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
