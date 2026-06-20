import React, { useCallback, useEffect, useState } from 'react'
import { Cpu, RefreshCw, Zap, CheckCircle, XCircle, Activity } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const MR_API = '/mrouter'
const INTERNAL = { 'X-Internal-Secret': 'dev-secret' }

interface Model {
  id: string
  name: string
  provider: string
  model_id: string
  is_free: number
  capabilities: string
  cost_per_1k_tokens: number
  avg_latency_ms: number
  priority: number
  is_active: number
  total_requests: number
  last_used: string | null
  created_at: string
}

interface Stats {
  total_models: number
  free_models: number
  active_models: number
  total_requests: number
}

function StatTile({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
      <p className="text-xs text-slate-400 mb-1">{label}</p>
      <p className="text-2xl font-bold text-white">{value}</p>
      {sub && <p className="text-xs text-slate-500 mt-0.5">{sub}</p>}
    </div>
  )
}

function CapBadge({ cap }: { cap: string }) {
  return (
    <span className="text-xs px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
      {cap}
    </span>
  )
}

export default function ModelRouterPage() {
  const { trackPageView } = useAnalytics()
  const [stats, setStats] = useState<Stats | null>(null)
  const [models, setModels] = useState<Model[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeOnly, setActiveOnly] = useState(false)

  useEffect(() => { trackPageView('/model-router') }, [trackPageView])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [sRes, mRes] = await Promise.all([
        fetch(`${MR_API}/stats`, { headers: INTERNAL }),
        fetch(`${MR_API}/models?active_only=${activeOnly}&limit=100`, { headers: INTERNAL }),
      ])
      if (!sRes.ok || !mRes.ok) throw new Error('Service unavailable')
      const [s, m] = await Promise.all([sRes.json(), mRes.json()])
      setStats(s)
      setModels(m)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [activeOnly])

  useEffect(() => { load() }, [load])

  const caps = (raw: string) => {
    try { return JSON.parse(raw) as string[] } catch { return [] }
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Cpu size={22} className="text-indigo-400" /> Model Router
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">AI model registry · intelligent routing · zero-cost enforcement</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
            <input
              type="checkbox"
              checked={activeOnly}
              onChange={e => setActiveOnly(e.target.checked)}
              className="accent-indigo-500"
            />
            Active only
          </label>
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
          {error} — is model-router-service running on port 8033?
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatTile label="Total Models" value={stats?.total_models ?? '—'} />
        <StatTile label="Free Models" value={stats?.free_models ?? '—'} sub="zero-cost only" />
        <StatTile label="Active" value={stats?.active_models ?? '—'} sub="circuit breaker open" />
        <StatTile label="Total Requests" value={stats?.total_requests ?? '—'} sub="all time" />
      </div>

      {/* Model registry */}
      <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/60">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2">
            <Activity size={14} className="text-indigo-400" /> Model Registry
          </h2>
          <span className="text-xs text-slate-500">{models.length} model{models.length !== 1 ? 's' : ''}</span>
        </div>

        {loading && !models.length ? (
          <div className="p-8 text-center text-slate-500 text-sm">Loading models…</div>
        ) : models.length === 0 ? (
          <div className="p-8 text-center text-slate-500 text-sm">
            No models registered. Add models via <code className="text-slate-400">POST /mrouter/models</code>.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700/60 text-xs text-slate-500 uppercase tracking-wider">
                  <th className="text-left px-4 py-2">Name</th>
                  <th className="text-left px-4 py-2">Provider</th>
                  <th className="text-left px-4 py-2">Capabilities</th>
                  <th className="text-right px-4 py-2">Latency</th>
                  <th className="text-right px-4 py-2">Requests</th>
                  <th className="text-right px-4 py-2">Priority</th>
                  <th className="text-center px-4 py-2">Status</th>
                  <th className="text-center px-4 py-2">Free</th>
                </tr>
              </thead>
              <tbody>
                {models.map((m) => {
                  const capList = caps(m.capabilities)
                  return (
                    <tr key={m.id} className="border-b border-slate-800 hover:bg-slate-800/30 transition-colors">
                      <td className="px-4 py-2.5 font-medium text-white">
                        <div>{m.name}</div>
                        <div className="text-xs text-slate-500 font-mono">{m.model_id}</div>
                      </td>
                      <td className="px-4 py-2.5 text-slate-300">{m.provider || '—'}</td>
                      <td className="px-4 py-2.5">
                        <div className="flex flex-wrap gap-1">
                          {capList.length > 0
                            ? capList.map((c: string) => <CapBadge key={c} cap={c} />)
                            : <span className="text-slate-600 text-xs">—</span>}
                        </div>
                      </td>
                      <td className="px-4 py-2.5 text-right text-slate-300">
                        {m.avg_latency_ms > 0 ? `${m.avg_latency_ms.toFixed(0)}ms` : '—'}
                      </td>
                      <td className="px-4 py-2.5 text-right text-slate-300">{m.total_requests}</td>
                      <td className="px-4 py-2.5 text-right text-slate-300">{m.priority}</td>
                      <td className="px-4 py-2.5 text-center">
                        {m.is_active ? (
                          <span className="inline-flex items-center gap-1 text-xs text-emerald-400">
                            <CheckCircle size={12} /> active
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-xs text-red-400">
                            <XCircle size={12} /> inactive
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-center">
                        {m.is_free ? (
                          <span className="inline-flex items-center gap-1 text-xs text-emerald-400">
                            <Zap size={11} /> free
                          </span>
                        ) : (
                          <span className="text-xs text-amber-400">paid</span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Routing info */}
      <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
        <h3 className="text-sm font-semibold text-white mb-3">Routing Strategies</h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { name: 'cost_aware', desc: 'Prefer lowest-cost models first' },
            { name: 'latency_aware', desc: 'Prefer models with lowest avg latency' },
            { name: 'priority', desc: 'Use model priority weighting' },
            { name: 'round_robin', desc: 'Distribute evenly across models' },
          ].map(s => (
            <div key={s.name} className="rounded-lg border border-slate-700/40 bg-slate-800/40 p-3">
              <p className="text-xs font-mono text-indigo-300 mb-1">{s.name}</p>
              <p className="text-xs text-slate-400">{s.desc}</p>
            </div>
          ))}
        </div>
        <p className="text-xs text-slate-500 mt-3">
          Zero-cost enforcement: all routing is restricted to <code className="text-slate-400">is_free=1</code> models only.
          Unhealthy models are auto-deactivated via circuit breaker.
        </p>
      </div>
    </div>
  )
}
