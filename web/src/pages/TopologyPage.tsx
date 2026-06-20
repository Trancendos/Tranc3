import React, { useCallback, useEffect, useState } from 'react'
import { Network, RefreshCw, CheckCircle, XCircle, AlertCircle } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const TOPO_API = '/topo'
const INTERNAL = { 'X-Internal-Secret': 'dev-secret' }

interface Stats {
  current_mode: string
  total_nodes: number
  healthy_nodes: number
  total_migrations: number
}

interface Node {
  id: string
  name: string
  node_type: string
  endpoint: string
  status: string
  latency_ms: number
  capabilities: string
  last_check: string | null
  created_at: string
}

interface Migration {
  id: string
  from_mode: string
  to_mode: string
  status: string
  progress: number
  completed_steps: number
  error_message: string | null
  created_at: string
}

type Tab = 'nodes' | 'migrations'

const MODE_COLORS: Record<string, string> = {
  CLOUDFLARE: 'bg-orange-500/20 text-orange-300 border-orange-500/30',
  HYBRID: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  SELF_HOSTED: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
}

const STATUS_ICON: Record<string, React.ReactNode> = {
  healthy: <CheckCircle size={13} className="text-emerald-400" />,
  unhealthy: <XCircle size={13} className="text-red-400" />,
  degraded: <AlertCircle size={13} className="text-amber-400" />,
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

export default function TopologyPage() {
  const { trackPageView } = useAnalytics()
  const [stats, setStats] = useState<Stats | null>(null)
  const [nodes, setNodes] = useState<Node[]>([])
  const [migrations, setMigrations] = useState<Migration[]>([])
  const [tab, setTab] = useState<Tab>('nodes')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => { trackPageView('/topology') }, [trackPageView])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [sRes, nRes, mRes] = await Promise.all([
        fetch(`${TOPO_API}/stats`, { headers: INTERNAL }),
        fetch(`${TOPO_API}/nodes?limit=100`, { headers: INTERNAL }),
        fetch(`${TOPO_API}/migrations?limit=50`, { headers: INTERNAL }),
      ])
      if (!sRes.ok || !nRes.ok || !mRes.ok) throw new Error('Service unavailable')
      const [s, n, m] = await Promise.all([sRes.json(), nRes.json(), mRes.json()])
      setStats(s)
      setNodes(n)
      setMigrations(m)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const caps = (raw: string) => {
    try { return JSON.parse(raw) as string[] } catch { return [] }
  }

  const fmt = (iso: string) => {
    try { return new Date(iso).toLocaleString() } catch { return iso }
  }

  const modeClass = stats ? (MODE_COLORS[stats.current_mode] ?? 'bg-slate-700/40 text-slate-300 border-slate-600/30') : ''

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Network size={22} className="text-blue-400" /> Service Topology
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Node health · migration tracking · CF→self-hosted topology modes</p>
        </div>
        <div className="flex items-center gap-3">
          {stats && (
            <span className={`text-xs px-2.5 py-1 rounded-full border font-medium ${modeClass}`}>
              {stats.current_mode}
            </span>
          )}
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
          {error} — is topology-service running on port 8031?
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatTile label="Current Mode" value={stats?.current_mode ?? '—'} />
        <StatTile label="Total Nodes" value={stats?.total_nodes ?? '—'} />
        <StatTile label="Healthy Nodes" value={stats?.healthy_nodes ?? '—'} sub="passing health checks" />
        <StatTile label="Migrations" value={stats?.total_migrations ?? '—'} sub="CF→self-hosted" />
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-700/60">
        {(['nodes', 'migrations'] as Tab[]).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium capitalize transition-colors border-b-2 -mb-px ${
              tab === t
                ? 'border-blue-500 text-blue-400'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === 'nodes' && (
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/60">
            <h2 className="text-sm font-semibold text-white">Registered Nodes</h2>
            <span className="text-xs text-slate-500">{nodes.length} node{nodes.length !== 1 ? 's' : ''}</span>
          </div>
          {loading && !nodes.length ? (
            <div className="p-8 text-center text-slate-500 text-sm">Loading nodes…</div>
          ) : nodes.length === 0 ? (
            <div className="p-8 text-center text-slate-500 text-sm">No nodes registered.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700/60 text-xs text-slate-500 uppercase tracking-wider">
                    <th className="text-left px-4 py-2">Name</th>
                    <th className="text-left px-4 py-2">Type</th>
                    <th className="text-left px-4 py-2">Endpoint</th>
                    <th className="text-left px-4 py-2">Capabilities</th>
                    <th className="text-right px-4 py-2">Latency</th>
                    <th className="text-center px-4 py-2">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {nodes.map(n => {
                    const capList = caps(n.capabilities)
                    return (
                      <tr key={n.id} className="border-b border-slate-800 hover:bg-slate-800/30 transition-colors">
                        <td className="px-4 py-2.5 font-medium text-white">{n.name}</td>
                        <td className="px-4 py-2.5">
                          <span className="text-xs px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30">
                            {n.node_type}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 font-mono text-xs text-slate-400">{n.endpoint}</td>
                        <td className="px-4 py-2.5">
                          <div className="flex flex-wrap gap-1">
                            {capList.map((c: string) => (
                              <span key={c} className="text-xs px-1 py-0.5 rounded bg-slate-700/60 text-slate-300">{c}</span>
                            ))}
                          </div>
                        </td>
                        <td className="px-4 py-2.5 text-right text-slate-300">
                          {n.latency_ms > 0 ? `${n.latency_ms.toFixed(0)}ms` : '—'}
                        </td>
                        <td className="px-4 py-2.5 text-center">
                          <span className="inline-flex items-center gap-1 text-xs capitalize">
                            {STATUS_ICON[n.status] ?? <AlertCircle size={13} className="text-slate-400" />}
                            {n.status}
                          </span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === 'migrations' && (
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/60">
            <h2 className="text-sm font-semibold text-white">CF → Self-Hosted Migrations</h2>
            <span className="text-xs text-slate-500">{migrations.length} migration{migrations.length !== 1 ? 's' : ''}</span>
          </div>
          {loading && !migrations.length ? (
            <div className="p-8 text-center text-slate-500 text-sm">Loading migrations…</div>
          ) : migrations.length === 0 ? (
            <div className="p-8 text-center text-slate-500 text-sm">No migrations recorded.</div>
          ) : (
            <div className="space-y-2 p-4">
              {migrations.map(m => (
                <div key={m.id} className="rounded-lg border border-slate-700/40 bg-slate-800/40 p-3">
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-sm text-slate-200">
                      <span className="text-orange-300">{m.from_mode}</span>
                      {' → '}
                      <span className="text-emerald-300">{m.to_mode}</span>
                    </span>
                    <span className={`text-xs px-1.5 py-0.5 rounded border ${
                      m.status === 'completed' ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' :
                      m.status === 'in_progress' ? 'bg-blue-500/20 text-blue-300 border-blue-500/30' :
                      'bg-slate-700/40 text-slate-400 border-slate-600/30'
                    }`}>{m.status}</span>
                  </div>
                  <div className="w-full h-1.5 bg-slate-700 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full bg-blue-500 transition-all"
                      style={{ width: `${m.progress}%` }}
                    />
                  </div>
                  <div className="flex items-center justify-between mt-1">
                    <span className="text-xs text-slate-500">{m.progress.toFixed(0)}% · {m.completed_steps} steps</span>
                    <span className="text-xs text-slate-600">{fmt(m.created_at)}</span>
                  </div>
                  {m.error_message && (
                    <p className="text-xs text-red-400 mt-1">{m.error_message}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
