import React, { useCallback, useEffect, useState } from 'react'
import { BookOpen, RefreshCw, ShieldCheck, ShieldAlert, Link } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const LEDGER_API = '/ledger'
const INTERNAL = { 'X-Internal-Secret': 'dev-secret' }

interface LedgerEntry {
  id: string
  actor: string
  action: string
  resource_type: string
  resource_id: string
  details: Record<string, unknown>
  hash: string
  prev_hash: string
  signature: string
  created_at: string
}

interface Stats {
  total_entries: number
  chain_valid: boolean
  sentinel_checks: number
  last_sentinel_check: string | null
}

interface VerifyResult {
  chain_valid: boolean
  entry_count: number
  invalid_entries: string[]
}

function StatTile({ label, value, sub, ok }: { label: string; value: string | number; sub?: string; ok?: boolean }) {
  return (
    <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
      <p className="text-xs text-slate-400 mb-1">{label}</p>
      <p className={`text-2xl font-bold ${ok === undefined ? 'text-white' : ok ? 'text-emerald-400' : 'text-red-400'}`}>{value}</p>
      {sub && <p className="text-xs text-slate-500 mt-0.5">{sub}</p>}
    </div>
  )
}

export default function LedgerPage() {
  const { trackPageView } = useAnalytics()
  const [stats, setStats] = useState<Stats | null>(null)
  const [entries, setEntries] = useState<LedgerEntry[]>([])
  const [verify, setVerify] = useState<VerifyResult | null>(null)
  const [verifying, setVerifying] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actor, setActor] = useState('')
  const [action, setAction] = useState('')

  useEffect(() => { trackPageView('/ledger') }, [trackPageView])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({ limit: '100' })
      if (actor) params.set('actor', actor)
      if (action) params.set('action', action)
      const [sRes, eRes] = await Promise.all([
        fetch(`${LEDGER_API}/stats`, { headers: INTERNAL }),
        fetch(`${LEDGER_API}/entries?${params}`, { headers: INTERNAL }),
      ])
      if (!sRes.ok || !eRes.ok) throw new Error('Service unavailable')
      const [s, e] = await Promise.all([sRes.json(), eRes.json()])
      setStats(s)
      setEntries(e)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [actor, action])

  useEffect(() => { load() }, [load])

  const runVerify = useCallback(async () => {
    setVerifying(true)
    try {
      const r = await fetch(`${LEDGER_API}/verify`, { headers: INTERNAL, signal: AbortSignal.timeout(10000) })
      if (r.ok) setVerify(await r.json())
    } catch { /* ignore */ } finally {
      setVerifying(false)
      load()
    }
  }, [load])

  const fmt = (iso: string) => {
    try { return new Date(iso).toLocaleString() } catch { return iso }
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <BookOpen size={22} className="text-emerald-400" /> Royal Bank Ledger
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Tamper-evident hash-chained ledger · sentinel chain verification</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={runVerify}
            disabled={verifying}
            className="flex items-center gap-1.5 rounded-lg border border-emerald-700/50 bg-emerald-900/30 px-3 py-1.5 text-xs text-emerald-300 hover:text-emerald-100 disabled:opacity-50 transition-colors"
          >
            <Link size={12} className={verifying ? 'animate-pulse' : ''} /> Verify Chain
          </button>
          <button
            onClick={load}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-300 hover:text-white disabled:opacity-50 transition-colors"
          >
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg bg-red-500/10 border border-red-500/30 px-4 py-3 text-sm text-red-300">
          {error} — is ledger-service running on port 8032?
        </div>
      )}

      {verify && (
        <div className={`rounded-lg border px-4 py-3 flex items-center gap-3 ${verify.chain_valid ? 'bg-emerald-500/10 border-emerald-500/30' : 'bg-red-500/10 border-red-500/30'}`}>
          {verify.chain_valid
            ? <ShieldCheck size={16} className="text-emerald-400 flex-shrink-0" />
            : <ShieldAlert size={16} className="text-red-400 flex-shrink-0" />}
          <div>
            <p className={`text-sm font-medium ${verify.chain_valid ? 'text-emerald-300' : 'text-red-300'}`}>
              {verify.chain_valid ? 'Chain integrity verified' : 'Chain integrity FAILED'}
            </p>
            <p className="text-xs text-slate-400">
              {verify.entry_count} entries checked
              {verify.invalid_entries.length > 0 && ` · ${verify.invalid_entries.length} invalid`}
            </p>
          </div>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatTile label="Total Entries" value={stats?.total_entries ?? '—'} />
        <StatTile label="Chain Valid" value={stats?.chain_valid === undefined ? '—' : stats.chain_valid ? 'Valid' : 'BROKEN'} ok={stats?.chain_valid} />
        <StatTile label="Sentinel Checks" value={stats?.sentinel_checks ?? '—'} />
        <StatTile label="Last Check" value={stats?.last_sentinel_check ? fmt(stats.last_sentinel_check) : '—'} />
      </div>

      {/* Filters */}
      <div className="flex gap-3">
        <input
          type="text"
          placeholder="Filter by actor…"
          value={actor}
          onChange={e => setActor(e.target.value)}
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-slate-500 w-48"
        />
        <input
          type="text"
          placeholder="Filter by action…"
          value={action}
          onChange={e => setAction(e.target.value)}
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-slate-500 w-48"
        />
      </div>

      {/* Entries table */}
      <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/60">
          <h2 className="text-sm font-semibold text-white">Ledger Entries</h2>
          <span className="text-xs text-slate-500">{entries.length} entries</span>
        </div>
        {loading && !entries.length ? (
          <div className="p-8 text-center text-slate-500 text-sm">Loading entries…</div>
        ) : entries.length === 0 ? (
          <div className="p-8 text-center text-slate-500 text-sm">No ledger entries found.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700/60 text-xs text-slate-500 uppercase tracking-wider">
                  <th className="text-left px-4 py-2">Timestamp</th>
                  <th className="text-left px-4 py-2">Actor</th>
                  <th className="text-left px-4 py-2">Action</th>
                  <th className="text-left px-4 py-2">Resource</th>
                  <th className="text-left px-4 py-2">Hash</th>
                </tr>
              </thead>
              <tbody>
                {entries.map(e => (
                  <tr key={e.id} className="border-b border-slate-800 hover:bg-slate-800/30 transition-colors">
                    <td className="px-4 py-2.5 text-slate-400 whitespace-nowrap">{fmt(e.created_at)}</td>
                    <td className="px-4 py-2.5 text-slate-200">{e.actor}</td>
                    <td className="px-4 py-2.5">
                      <span className="text-xs px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30 font-mono">
                        {e.action}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-slate-300">
                      <span className="text-slate-500">{e.resource_type}</span>
                      {e.resource_id && <span className="text-slate-400">/{e.resource_id.slice(0, 8)}…</span>}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-xs text-slate-500" title={e.hash}>
                      {e.hash.slice(0, 16)}…
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
