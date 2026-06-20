import React, { useCallback, useEffect, useState } from 'react'
import { Layers, RefreshCw, Play, Pause, Trash2 } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const HIVE_API = '/hive-svc'
const INTERNAL = { 'X-Internal-Secret': 'dev-secret' }

interface Pipeline {
  pipeline_id: string
  name: string
  status: string
  priority: string
  source_id: string
  sink_ids: string[]
  replication_factor: number
  created_at: number
}

interface Swarm {
  swarm_id: string
  name: string
  purpose: string
  status: string
  data_type: string
  nodes: { node_id: string; role: string; capacity: number; status: string }[]
}

interface FlowSummary {
  total_chunks_routed: number
  failed_chunks: number
  pending_chunks: number
  avg_latency_ms: Record<string, number>
  throughput_mbps: Record<string, number>
}

const PIPELINE_COLORS: Record<string, string> = {
  active:  'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  paused:  'bg-amber-500/20 text-amber-300 border-amber-500/30',
  created: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  error:   'bg-red-500/20 text-red-300 border-red-500/30',
}

const SWARM_COLORS: Record<string, string> = {
  active:   'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  idle:     'bg-slate-500/20 text-slate-300 border-slate-500/30',
  forming:  'bg-blue-500/20 text-blue-300 border-blue-500/30',
  dissolving: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
}

const PRIORITY_COLORS: Record<string, string> = {
  critical: 'text-red-400',
  high:     'text-orange-400',
  normal:   'text-slate-300',
  low:      'text-slate-500',
  bulk:     'text-slate-600',
}

export default function HivePage() {
  const { trackPageView } = useAnalytics()
  const [pipelines, setPipelines] = useState<Pipeline[]>([])
  const [swarms, setSwarms] = useState<Swarm[]>([])
  const [flow, setFlow] = useState<FlowSummary | null>(null)
  const [sourceCt, setSourceCt] = useState(0)
  const [sinkCt, setSinkCt] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<'pipelines' | 'swarms'>('pipelines')

  useEffect(() => { trackPageView('/hive') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [hRes, pRes, sRes, srcRes, snkRes, fRes] = await Promise.all([
        fetch(`${HIVE_API}/health`),
        fetch(`${HIVE_API}/pipelines`, { headers: INTERNAL }),
        fetch(`${HIVE_API}/swarms`, { headers: INTERNAL }),
        fetch(`${HIVE_API}/sources`, { headers: INTERNAL }),
        fetch(`${HIVE_API}/sinks`, { headers: INTERNAL }),
        fetch(`${HIVE_API}/flow`, { headers: INTERNAL }),
      ])
      if (!hRes.ok) throw new Error('HIVE service unavailable')
      const [p, s, src, snk, f] = await Promise.all([
        pRes.ok ? pRes.json() : [],
        sRes.ok ? sRes.json() : [],
        srcRes.ok ? srcRes.json() : {},
        snkRes.ok ? snkRes.json() : {},
        fRes.ok ? fRes.json() : null,
      ])
      setPipelines(Array.isArray(p) ? p : [])
      setSwarms(Array.isArray(s) ? s : [])
      setSourceCt(Object.keys(src).length)
      setSinkCt(Object.keys(snk).length)
      if (f) setFlow(f)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const pipelineAction = async (id: string, action: 'start' | 'pause') => {
    try {
      await fetch(`${HIVE_API}/pipelines/${id}/${action}`, { method: 'POST', headers: INTERNAL })
      loadData()
    } catch { /* ignore */ }
  }

  const dissolveSwarm = async (id: string) => {
    try {
      await fetch(`${HIVE_API}/swarms/${id}`, { method: 'DELETE', headers: INTERNAL })
      loadData()
    } catch { /* ignore */ }
  }

  const activePipelines = pipelines.filter(p => p.status === 'active').length
  const activeSwarms   = swarms.filter(s => s.status === 'active').length

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Layers size={22} className="text-amber-400" /> The HIVE
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Data movement & swarm system coordination — Bridge 3</p>
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
          {error} — is hive-service running on port 8060?
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Pipelines</p>
          <p className="text-2xl font-bold text-white">{pipelines.length}</p>
          <p className="text-xs text-emerald-400 mt-0.5">{activePipelines} active</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Swarms</p>
          <p className="text-2xl font-bold text-white">{swarms.length}</p>
          <p className="text-xs text-emerald-400 mt-0.5">{activeSwarms} active</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Sources</p>
          <p className="text-2xl font-bold text-blue-400">{sourceCt}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Sinks</p>
          <p className="text-2xl font-bold text-purple-400">{sinkCt}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Chunks Routed</p>
          <p className="text-2xl font-bold text-slate-200">{flow?.total_chunks_routed ?? '—'}</p>
          {flow && flow.failed_chunks > 0 && (
            <p className="text-xs text-red-400 mt-0.5">{flow.failed_chunks} failed</p>
          )}
        </div>
      </div>

      {/* Flow throughput */}
      {flow && Object.keys(flow.throughput_mbps).length > 0 && (
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <h2 className="text-sm font-semibold text-white mb-3">Live Throughput (Mbps)</h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {Object.entries(flow.throughput_mbps).map(([pid, mbps]) => (
              <div key={pid} className="rounded-lg bg-slate-800/60 p-3">
                <p className="text-xs text-slate-500 truncate">{pid.slice(0, 8)}…</p>
                <p className="text-lg font-bold text-amber-400">{mbps.toFixed(1)}</p>
                {flow.avg_latency_ms[pid] !== undefined && (
                  <p className="text-xs text-slate-500">{flow.avg_latency_ms[pid].toFixed(0)} ms</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tabs */}
      <div>
        <div className="flex gap-2 mb-4">
          {(['pipelines', 'swarms'] as const).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${tab === t ? 'bg-indigo-600 text-white' : 'bg-slate-800 text-slate-400 hover:text-white'}`}
            >
              {t === 'pipelines' ? `Pipelines (${pipelines.length})` : `Swarms (${swarms.length})`}
            </button>
          ))}
        </div>

        {tab === 'pipelines' && (
          <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 overflow-hidden">
            {loading ? (
              <div className="p-8 text-center text-slate-500 text-sm">Loading…</div>
            ) : pipelines.length === 0 ? (
              <div className="p-8 text-center text-slate-500 text-sm">No pipelines registered.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-700/60 text-xs text-slate-500 uppercase tracking-wider">
                      <th className="text-left px-4 py-2">Name</th>
                      <th className="text-left px-4 py-2">Status</th>
                      <th className="text-left px-4 py-2">Priority</th>
                      <th className="text-right px-4 py-2">Sinks</th>
                      <th className="text-right px-4 py-2">Replication</th>
                      <th className="text-right px-4 py-2"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {pipelines.map(p => (
                      <tr key={p.pipeline_id} className="border-b border-slate-800 hover:bg-slate-800/30 transition-colors">
                        <td className="px-4 py-2.5">
                          <p className="text-xs font-medium text-slate-200">{p.name}</p>
                          <p className="text-xs text-slate-600 font-mono">{p.pipeline_id.slice(0, 8)}…</p>
                        </td>
                        <td className="px-4 py-2.5">
                          <span className={`text-xs px-1.5 py-0.5 rounded border ${PIPELINE_COLORS[p.status] ?? 'bg-slate-700/40 text-slate-400 border-slate-600/30'}`}>
                            {p.status}
                          </span>
                        </td>
                        <td className={`px-4 py-2.5 text-xs font-medium ${PRIORITY_COLORS[p.priority] ?? 'text-slate-300'}`}>
                          {p.priority}
                        </td>
                        <td className="px-4 py-2.5 text-right text-xs text-slate-400">{p.sink_ids.length}</td>
                        <td className="px-4 py-2.5 text-right text-xs text-slate-400">×{p.replication_factor}</td>
                        <td className="px-4 py-2.5 text-right">
                          <div className="flex items-center justify-end gap-2">
                            {p.status !== 'active' ? (
                              <button onClick={() => pipelineAction(p.pipeline_id, 'start')} className="text-emerald-400 hover:text-emerald-300 transition-colors" title="Start">
                                <Play size={13} />
                              </button>
                            ) : (
                              <button onClick={() => pipelineAction(p.pipeline_id, 'pause')} className="text-amber-400 hover:text-amber-300 transition-colors" title="Pause">
                                <Pause size={13} />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {tab === 'swarms' && (
          <div className="space-y-3">
            {loading ? (
              <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-8 text-center text-slate-500 text-sm">Loading…</div>
            ) : swarms.length === 0 ? (
              <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-8 text-center text-slate-500 text-sm">No swarms registered.</div>
            ) : swarms.map(s => (
              <div key={s.swarm_id} className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium text-slate-200">{s.name}</p>
                      <span className={`text-xs px-1.5 py-0.5 rounded border ${SWARM_COLORS[s.status] ?? 'bg-slate-700/40 text-slate-400 border-slate-600/30'}`}>
                        {s.status}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500 mt-0.5">{s.purpose}</p>
                  </div>
                  <button
                    onClick={() => dissolveSwarm(s.swarm_id)}
                    className="text-red-400/60 hover:text-red-400 transition-colors"
                    title="Dissolve swarm"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
                {s.nodes.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {s.nodes.map(n => (
                      <span key={n.node_id} className="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700/60">
                        {n.node_id} <span className="text-slate-500">({n.role})</span>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
