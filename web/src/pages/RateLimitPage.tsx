import React, { useCallback, useEffect, useState } from 'react'
import { Shield, RefreshCw } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const RL_API = '/rlimit'
const INTERNAL = { 'X-Internal-Secret': 'dev-secret' }

interface Policy {
  name: string
  capacity: number
  refill_rate: number
  description: string | null
  created_at: number
}

interface Bucket {
  tokens: number
  policy: string
}

export default function RateLimitPage() {
  const { trackPageView } = useAnalytics()
  const [policies, setPolicies] = useState<Policy[]>([])
  const [buckets, setBuckets] = useState<Record<string, Bucket>>({})
  const [activeBuckets, setActiveBuckets] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<'policies' | 'buckets'>('policies')

  useEffect(() => { trackPageView('/rate-limit') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [hRes, pRes, sRes] = await Promise.all([
        fetch(`${RL_API}/health`),
        fetch(`${RL_API}/policies`, { headers: INTERNAL }),
        fetch(`${RL_API}/stats`, { headers: INTERNAL }),
      ])
      if (!hRes.ok) throw new Error('Service unavailable')
      const [h, p, s] = await Promise.all([hRes.json(), pRes.ok ? pRes.json() : null, sRes.ok ? sRes.json() : null])
      setActiveBuckets(h.active_buckets ?? 0)
      if (p) setPolicies(p.policies ?? [])
      if (s) {
        setBuckets(s.buckets ?? {})
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const resetBucket = async (key: string) => {
    try {
      await fetch(`${RL_API}/buckets/${encodeURIComponent(key)}`, { method: 'DELETE', headers: INTERNAL })
      loadData()
    } catch { /* ignore */ }
  }

  const fmt = (ts: number) => {
    try { return new Date(ts * 1000).toLocaleString() } catch { return String(ts) }
  }

  const bucketEntries = Object.entries(buckets)

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Shield size={22} className="text-slate-400" /> Rate Limiter
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Token-bucket rate limiting — policies and active buckets</p>
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
          {error} — is rate-limit-service running on port 8026?
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Active Buckets</p>
          <p className="text-2xl font-bold text-white">{activeBuckets}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Policies</p>
          <p className="text-2xl font-bold text-white">{policies.length}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Algorithm</p>
          <p className="text-lg font-bold text-slate-300">Token Bucket</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-700/60">
        {(['policies', 'buckets'] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm transition-colors capitalize ${tab === t ? 'border-b-2 border-indigo-500 text-white' : 'text-slate-400 hover:text-white'}`}
          >
            {t} {t === 'buckets' ? `(${bucketEntries.length})` : `(${policies.length})`}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="p-8 text-center text-slate-500">Loading…</div>
      ) : tab === 'policies' ? (
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 overflow-hidden">
          {policies.length === 0 ? (
            <div className="p-8 text-center text-slate-500 text-sm">No policies defined.</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700/60 text-xs text-slate-500 uppercase tracking-wider">
                  <th className="text-left px-4 py-2">Name</th>
                  <th className="text-right px-4 py-2">Capacity</th>
                  <th className="text-right px-4 py-2">Refill/s</th>
                  <th className="text-left px-4 py-2">Description</th>
                  <th className="text-right px-4 py-2">Created</th>
                </tr>
              </thead>
              <tbody>
                {policies.map(p => (
                  <tr key={p.name} className="border-b border-slate-800 hover:bg-slate-800/30 transition-colors">
                    <td className="px-4 py-2.5 font-mono text-xs text-indigo-300">{p.name}</td>
                    <td className="px-4 py-2.5 text-right text-slate-200 font-mono text-xs">{p.capacity}</td>
                    <td className="px-4 py-2.5 text-right text-slate-200 font-mono text-xs">{p.refill_rate}</td>
                    <td className="px-4 py-2.5 text-xs text-slate-400">{p.description ?? '—'}</td>
                    <td className="px-4 py-2.5 text-right text-xs text-slate-500 whitespace-nowrap">{fmt(p.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : (
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 overflow-hidden">
          {bucketEntries.length === 0 ? (
            <div className="p-8 text-center text-slate-500 text-sm">No active buckets.</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700/60 text-xs text-slate-500 uppercase tracking-wider">
                  <th className="text-left px-4 py-2">Key</th>
                  <th className="text-left px-4 py-2">Policy</th>
                  <th className="text-right px-4 py-2">Tokens</th>
                  <th className="text-right px-4 py-2">Fill %</th>
                  <th className="text-right px-4 py-2">Action</th>
                </tr>
              </thead>
              <tbody>
                {bucketEntries.map(([key, bucket]) => {
                  const policy = policies.find(p => p.name === bucket.policy)
                  const pct = policy ? Math.round((bucket.tokens / policy.capacity) * 100) : null
                  return (
                    <tr key={key} className="border-b border-slate-800 hover:bg-slate-800/30 transition-colors">
                      <td className="px-4 py-2.5 font-mono text-xs text-slate-200 max-w-xs truncate">{key}</td>
                      <td className="px-4 py-2.5 text-xs text-indigo-300">{bucket.policy}</td>
                      <td className="px-4 py-2.5 text-right text-xs text-slate-300 font-mono">{bucket.tokens.toFixed(1)}</td>
                      <td className="px-4 py-2.5 text-right">
                        {pct !== null ? (
                          <span className={`text-xs font-mono ${pct < 20 ? 'text-red-400' : pct < 60 ? 'text-amber-400' : 'text-emerald-400'}`}>
                            {pct}%
                          </span>
                        ) : '—'}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <button
                          onClick={() => resetBucket(key)}
                          className="text-xs text-slate-500 hover:text-amber-400 transition-colors"
                        >
                          reset
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}
