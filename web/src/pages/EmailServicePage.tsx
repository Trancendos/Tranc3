import React, { useCallback, useEffect, useState } from 'react'
import { Mail, RefreshCw, RotateCcw, CheckCircle, XCircle, Clock } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const EMAIL_API = '/email-svc'
const INTERNAL = { 'X-Internal-Secret': 'dev-secret' }

interface Email {
  id: number
  to_addr: string
  subject: string
  status: string
  retry_count: number
  queued_at: number
  sent_at: number | null
  error: string | null
}

interface Template {
  id: string
  name: string
  subject: string
  created_at: number
}

export default function EmailServicePage() {
  const { trackPageView } = useAnalytics()
  const [pending, setPending] = useState(0)
  const [sent, setSent] = useState(0)
  const [failed, setFailed] = useState(0)
  const [smtpOk, setSmtpOk] = useState(false)
  const [emails, setEmails] = useState<Email[]>([])
  const [templates, setTemplates] = useState<Template[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [tab, setTab] = useState<'outbox' | 'templates'>('outbox')
  const [total, setTotal] = useState(0)

  useEffect(() => { trackPageView('/email-svc') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = statusFilter ? `?status=${statusFilter}&limit=50` : '?limit=50'
      const [hRes, oRes, tRes] = await Promise.all([
        fetch(`${EMAIL_API}/health`),
        fetch(`${EMAIL_API}/outbox${params}`, { headers: INTERNAL }),
        fetch(`${EMAIL_API}/templates`, { headers: INTERNAL }),
      ])
      if (!hRes.ok) throw new Error('Service unavailable')
      const [h, o, t] = await Promise.all([hRes.json(), oRes.ok ? oRes.json() : null, tRes.ok ? tRes.json() : null])
      setPending(h.pending ?? 0)
      setSent(h.sent ?? 0)
      setFailed(h.failed ?? 0)
      setSmtpOk(h.smtp_configured ?? false)
      if (o) { setEmails(o.emails ?? []); setTotal(o.total ?? 0) }
      if (t) setTemplates(t.templates ?? [])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => { loadData() }, [loadData])

  const retryEmail = async (id: number) => {
    try {
      await fetch(`${EMAIL_API}/outbox/${id}/retry`, { method: 'POST', headers: INTERNAL })
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
            <Mail size={22} className="text-slate-400" /> Arcadia Email
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">SMTP outbox with template engine and delivery tracking</p>
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
          {error} — is email-service running on port 8018?
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-4 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">SMTP</p>
          <p className={`text-lg font-bold ${smtpOk ? 'text-emerald-400' : 'text-red-400'}`}>
            {smtpOk ? 'Configured' : 'Not configured'}
          </p>
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

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-700/60">
        {(['outbox', 'templates'] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm transition-colors capitalize ${tab === t ? 'border-b-2 border-indigo-500 text-white' : 'text-slate-400 hover:text-white'}`}
          >
            {t === 'outbox' ? `Outbox (${total})` : `Templates (${templates.length})`}
          </button>
        ))}
      </div>

      {tab === 'outbox' && (
        <>
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
          </div>

          <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 overflow-hidden">
            {loading ? (
              <div className="p-8 text-center text-slate-500 text-sm">Loading…</div>
            ) : emails.length === 0 ? (
              <div className="p-8 text-center text-slate-500 text-sm">No emails in outbox.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-700/60 text-xs text-slate-500 uppercase tracking-wider">
                      <th className="text-left px-4 py-2">Status</th>
                      <th className="text-left px-4 py-2">To</th>
                      <th className="text-left px-4 py-2">Subject</th>
                      <th className="text-right px-4 py-2">Retries</th>
                      <th className="text-right px-4 py-2">Queued</th>
                      <th className="text-right px-4 py-2"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {emails.map(e => (
                      <tr key={e.id} className="border-b border-slate-800 hover:bg-slate-800/30 transition-colors">
                        <td className="px-4 py-2.5">
                          <div className="flex items-center gap-1.5">
                            {STATUS_ICON[e.status] ?? null}
                            <span className={`text-xs px-1.5 py-0.5 rounded border ${STATUS_STYLE[e.status] ?? 'bg-slate-700/40 text-slate-400 border-slate-600/30'}`}>
                              {e.status}
                            </span>
                          </div>
                        </td>
                        <td className="px-4 py-2.5 text-xs text-slate-300 max-w-xs truncate">{e.to_addr}</td>
                        <td className="px-4 py-2.5 text-xs text-slate-400 max-w-xs truncate">{e.subject}</td>
                        <td className="px-4 py-2.5 text-right text-xs text-slate-500">{e.retry_count}</td>
                        <td className="px-4 py-2.5 text-right text-xs text-slate-500 whitespace-nowrap">{fmt(e.queued_at)}</td>
                        <td className="px-4 py-2.5 text-right">
                          {e.status === 'failed' && (
                            <button
                              onClick={() => retryEmail(e.id)}
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
        </>
      )}

      {tab === 'templates' && (
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 overflow-hidden">
          {templates.length === 0 ? (
            <div className="p-8 text-center text-slate-500 text-sm">No templates defined.</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700/60 text-xs text-slate-500 uppercase tracking-wider">
                  <th className="text-left px-4 py-2">ID</th>
                  <th className="text-left px-4 py-2">Name</th>
                  <th className="text-left px-4 py-2">Subject</th>
                  <th className="text-right px-4 py-2">Created</th>
                </tr>
              </thead>
              <tbody>
                {templates.map(t => (
                  <tr key={t.id} className="border-b border-slate-800 hover:bg-slate-800/30 transition-colors">
                    <td className="px-4 py-2.5 font-mono text-xs text-indigo-300">{t.id}</td>
                    <td className="px-4 py-2.5 text-xs text-slate-200">{t.name}</td>
                    <td className="px-4 py-2.5 text-xs text-slate-400 max-w-xs truncate">{t.subject}</td>
                    <td className="px-4 py-2.5 text-right text-xs text-slate-500 whitespace-nowrap">{fmt(t.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}
