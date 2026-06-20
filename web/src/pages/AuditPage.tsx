/**
 * AuditPage — Tamper-evident Audit Log (The Observatory · Port 8017)
 *
 * Browse, filter, and verify the audit trail from audit-service.
 * Events are hash-chained; the verify endpoint confirms chain integrity.
 */
import React, { useEffect, useState, useCallback } from 'react'
import { Shield, RefreshCw, Search, CheckCircle, XCircle, AlertCircle } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const AUDIT_API = '/audit'

const SEVERITY_COLORS: Record<string, string> = {
  info:     'text-blue-400',
  warning:  'text-yellow-400',
  error:    'text-red-400',
  critical: 'text-red-500',
}

const SEVERITY_BADGE: Record<string, string> = {
  info:     'bg-blue-900/40 text-blue-300 border-blue-700',
  warning:  'bg-yellow-900/40 text-yellow-300 border-yellow-700',
  error:    'bg-red-900/40 text-red-300 border-red-700',
  critical: 'bg-red-900/60 text-red-200 border-red-600',
}

const OUTCOME_COLORS: Record<string, string> = {
  success: 'text-green-400',
  failure: 'text-red-400',
  unknown: 'text-gray-500',
}

interface AuditEvent {
  event_id: string
  timestamp: string
  service: string
  actor: string
  action: string
  resource: string | null
  outcome: string
  severity: string
  metadata: Record<string, unknown>
}

interface AuditStats {
  last_24h: { total: number; by_severity: Record<string, number>; by_outcome: Record<string, number> }
  last_7d:  { total: number }
  last_30d: { total: number }
}

interface VerifyResult {
  valid: boolean
  checked: number
  errors: string[]
}

export default function AuditPage() {
  const [events, setEvents]         = useState<AuditEvent[]>([])
  const [stats, setStats]           = useState<AuditStats | null>(null)
  const [verify, setVerify]         = useState<VerifyResult | null>(null)
  const [loading, setLoading]       = useState(false)
  const [verifying, setVerifying]   = useState(false)
  const [workerDown, setWorkerDown] = useState(false)
  const [serviceFilter, setServiceFilter] = useState('')
  const [severityFilter, setSeverityFilter] = useState('')
  const [actorFilter, setActorFilter]     = useState('')
  const { trackPageView } = useAnalytics()

  useEffect(() => { trackPageView('/audit') }, [trackPageView])

  const load = useCallback(async () => {
    setLoading(true)
    setWorkerDown(false)
    try {
      const params = new URLSearchParams({ limit: '100' })
      if (serviceFilter) params.set('service', serviceFilter)
      if (severityFilter) params.set('severity', severityFilter)
      if (actorFilter) params.set('actor', actorFilter)

      const [eRes, sRes] = await Promise.all([
        fetch(`${AUDIT_API}/events?${params}`, { signal: AbortSignal.timeout(5000) }),
        fetch(`${AUDIT_API}/stats`,            { signal: AbortSignal.timeout(5000) }),
      ])
      if (eRes.ok) setEvents(await eRes.json())
      if (sRes.ok) setStats(await sRes.json())
      if (!eRes.ok && !sRes.ok) setWorkerDown(true)
    } catch {
      setWorkerDown(true)
    }
    setLoading(false)
  }, [serviceFilter, severityFilter, actorFilter])

  useEffect(() => { load() }, [load])

  const runVerify = useCallback(async () => {
    setVerifying(true)
    setVerify(null)
    try {
      const r = await fetch(`${AUDIT_API}/verify`, { signal: AbortSignal.timeout(10000) })
      if (r.ok) setVerify(await r.json())
    } catch { /* swallow */ }
    setVerifying(false)
  }, [])

  const fmtTs = (iso: string) => {
    try { return new Date(iso).toLocaleString() } catch { return iso }
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Shield size={22} aria-hidden="true" className="text-cyan-400" />
            Audit Log
          </h1>
          <p className="text-gray-400 text-sm mt-1">
            Tamper-evident hash-chained event trail · The Observatory · Port 8017
            {stats && ` · ${stats.last_24h.total} events (24h)`}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={runVerify}
            disabled={verifying || workerDown}
            className="flex items-center gap-2 px-3 py-2 bg-cyan-700 hover:bg-cyan-600 disabled:opacity-50 rounded-lg text-sm text-white transition-colors"
          >
            {verifying
              ? <><RefreshCw size={14} className="animate-spin" aria-hidden="true" /> Verifying…</>
              : <><CheckCircle size={14} aria-hidden="true" /> Verify Chain</>}
          </button>
          <button
            onClick={load}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg text-sm text-white transition-colors"
          >
            <RefreshCw size={14} aria-hidden="true" className={loading ? 'animate-spin' : ''} />
            {loading ? 'Loading…' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Worker banner */}
      {workerDown && (
        <div role="alert" className="mb-4 p-3 bg-yellow-900/30 border border-yellow-700 rounded-lg text-yellow-300 text-sm">
          Audit service (port 8017) is unreachable. Start with{' '}
          <code className="font-mono bg-gray-800 px-1 rounded">make dev-api</code>.
        </div>
      )}

      {/* Verify result */}
      {verify && (
        <div className={`mb-4 p-3 border rounded-lg text-sm flex items-start gap-2 ${
          verify.valid
            ? 'bg-green-900/30 border-green-700 text-green-300'
            : 'bg-red-900/30 border-red-700 text-red-300'
        }`} role="status">
          {verify.valid
            ? <CheckCircle size={16} aria-hidden="true" className="shrink-0 mt-0.5" />
            : <XCircle     size={16} aria-hidden="true" className="shrink-0 mt-0.5" />}
          <div>
            <span className="font-medium">Chain {verify.valid ? 'intact' : 'BROKEN'}</span>
            {' — '}{verify.checked} events verified.
            {verify.errors.length > 0 && (
              <ul className="mt-1 list-disc list-inside">
                {verify.errors.map((e, i) => <li key={i}>{e}</li>)}
              </ul>
            )}
          </div>
        </div>
      )}

      {/* Stats tiles */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-4">
            <div className="text-2xl font-bold text-cyan-400 tabular-nums">{stats.last_24h.total}</div>
            <div className="text-gray-400 text-sm mt-1">Last 24h</div>
          </div>
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-4">
            <div className="text-2xl font-bold text-blue-400 tabular-nums">{stats.last_7d.total}</div>
            <div className="text-gray-400 text-sm mt-1">Last 7 Days</div>
          </div>
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-4">
            <div className="text-2xl font-bold text-indigo-400 tabular-nums">{stats.last_30d.total}</div>
            <div className="text-gray-400 text-sm mt-1">Last 30 Days</div>
          </div>
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-4">
            <div className="text-2xl font-bold text-red-400 tabular-nums">
              {(stats.last_24h.by_severity?.error ?? 0) + (stats.last_24h.by_severity?.critical ?? 0)}
            </div>
            <div className="text-gray-400 text-sm mt-1">Errors (24h)</div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-3 mb-5 flex-wrap">
        <div className="relative">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" aria-hidden="true" />
          <input
            type="text"
            placeholder="Service…"
            value={serviceFilter}
            onChange={e => setServiceFilter(e.target.value)}
            className="pl-8 pr-3 py-1.5 bg-gray-900 border border-gray-700 rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 w-40"
          />
        </div>
        <div className="relative">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" aria-hidden="true" />
          <input
            type="text"
            placeholder="Actor…"
            value={actorFilter}
            onChange={e => setActorFilter(e.target.value)}
            className="pl-8 pr-3 py-1.5 bg-gray-900 border border-gray-700 rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 w-36"
          />
        </div>
        {['', 'info', 'warning', 'error', 'critical'].map(s => (
          <button
            key={s}
            onClick={() => setSeverityFilter(s)}
            aria-pressed={severityFilter === s}
            className={`px-3 py-1.5 rounded-md text-xs font-medium border transition-colors ${
              severityFilter === s
                ? 'bg-indigo-600 text-white border-indigo-500'
                : 'bg-gray-900 text-gray-400 border-gray-700 hover:border-gray-500'
            }`}
          >
            {s || 'All'}
          </button>
        ))}
      </div>

      {/* Events table */}
      {events.length === 0 && !loading ? (
        <div className="bg-gray-900 rounded-lg border border-gray-700 p-8 text-center text-gray-500">
          {workerDown ? 'Worker offline' : 'No audit events found.'}
        </div>
      ) : (
        <div className="bg-gray-900 rounded-lg border border-gray-700 overflow-hidden">
          <table className="w-full text-sm" aria-label="Audit events" aria-busy={loading}>
            <thead>
              <tr className="border-b border-gray-700">
                <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Timestamp</th>
                <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Service</th>
                <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Actor</th>
                <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Action</th>
                <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Severity</th>
                <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Outcome</th>
              </tr>
            </thead>
            <tbody>
              {events.map(ev => (
                <tr key={ev.event_id} className="border-b border-gray-800 hover:bg-gray-800/50">
                  <td className="px-4 py-3 text-gray-500 text-xs whitespace-nowrap">{fmtTs(ev.timestamp)}</td>
                  <td className="px-4 py-3 text-gray-300 text-xs font-mono">{ev.service}</td>
                  <td className="px-4 py-3 text-gray-400 text-xs">{ev.actor}</td>
                  <td className="px-4 py-3 text-gray-200 text-sm">{ev.action}
                    {ev.resource && <span className="text-gray-500 text-xs ml-1">on {ev.resource}</span>}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-xs border rounded-full px-2 py-0.5 ${SEVERITY_BADGE[ev.severity] ?? 'bg-gray-800 text-gray-400 border-gray-600'}`}>
                      {ev.severity}
                    </span>
                  </td>
                  <td className={`px-4 py-3 text-xs ${OUTCOME_COLORS[ev.outcome] ?? 'text-gray-400'}`}>
                    {ev.outcome}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
