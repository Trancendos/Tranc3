import React, { useCallback, useEffect, useState } from 'react'
import { Network, RefreshCw } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const API = '/dnexus-svc'

interface NexusHealth {
  status: string
  service: string
  port: number
}

const NEXUS_SERVICES = [
  { id: 'nexus-self', name: 'The Nexus', pillar: 'nexus' },
  { id: 'infinity-portal', name: 'Infinity Portal', pillar: 'infinity' },
  { id: 'infinity-auth', name: 'Infinity Auth', pillar: 'infinity' },
  { id: 'sentinel-station', name: 'Sentinel Station', pillar: 'infinity' },
  { id: 'health-aggregator', name: 'Health Aggregator', pillar: 'monitoring' },
  { id: 'the-grid', name: 'The Grid', pillar: 'infrastructure' },
  { id: 'tranc3-ai', name: 'Tranc3 AI', pillar: 'ai' },
  { id: 'deepagents-orchestrator', name: 'DeepAgents Orchestrator', pillar: 'agents' },
]

const PILLAR_COLORS: Record<string, string> = {
  nexus:          'bg-violet-500/20 text-violet-300 border-violet-500/30',
  infinity:       'bg-indigo-500/20 text-indigo-300 border-indigo-500/30',
  monitoring:     'bg-teal-500/20 text-teal-300 border-teal-500/30',
  infrastructure: 'bg-slate-600/40 text-slate-300 border-slate-600/30',
  ai:             'bg-purple-500/20 text-purple-300 border-purple-500/30',
  agents:         'bg-amber-500/20 text-amber-300 border-amber-500/30',
}

const NEXUS_EDGES = [
  { src: 'nexus-self', tgt: 'infinity-portal', type: 'control' },
  { src: 'nexus-self', tgt: 'infinity-auth', type: 'control' },
  { src: 'nexus-self', tgt: 'sentinel-station', type: 'events' },
  { src: 'nexus-self', tgt: 'health-aggregator', type: 'monitoring' },
  { src: 'nexus-self', tgt: 'tranc3-ai', type: 'coordination' },
  { src: 'nexus-self', tgt: 'deepagents-orchestrator', type: 'coordination' },
  { src: 'tranc3-ai', tgt: 'deepagents-orchestrator', type: 'task-dispatch' },
  { src: 'deepagents-orchestrator', tgt: 'the-grid', type: 'compute' },
]

export default function DimensionalNexusPage() {
  const { trackPageView } = useAnalytics()
  const [health, setHealth] = useState<NexusHealth | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => { trackPageView('/dimensional-nexus') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API}/health`)
      if (!res.ok) throw new Error('Dimensional Nexus unavailable')
      setHealth(await res.json())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Network size={22} className="text-violet-400" /> Dimensional Nexus
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">AI, Agent & Bot traffic coordination hub — The Nexus bridge</p>
        </div>
        <div className="flex items-center gap-2">
          {health && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400">{health.status}</span>
          )}
          <button
            onClick={loadData}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-300 hover:text-white disabled:opacity-50 transition-colors"
          >
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg bg-red-500/10 border border-red-500/30 px-4 py-3 text-sm text-red-300">
          {error} — is dimensional-nexus-service running on port 8050?
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Registered Services</p>
          <p className="text-2xl font-bold text-white">{NEXUS_SERVICES.length}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Topology Edges</p>
          <p className="text-2xl font-bold text-violet-400">{NEXUS_EDGES.length}</p>
        </div>
      </div>

      <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
        <h2 className="text-sm font-semibold text-white mb-3">Nexus Services</h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {NEXUS_SERVICES.map((svc) => (
            <div key={svc.id} className="rounded-lg border border-slate-700/40 bg-slate-800/40 p-2.5">
              <p className="text-xs font-medium text-slate-200 truncate">{svc.name}</p>
              <span className={`text-xs px-1.5 py-0.5 rounded border mt-1 inline-block ${PILLAR_COLORS[svc.pillar] ?? 'bg-slate-700/40 text-slate-400 border-slate-600/30'}`}>
                {svc.pillar}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
        <h2 className="text-sm font-semibold text-white mb-3">Topology Edges</h2>
        <div className="space-y-1.5">
          {NEXUS_EDGES.map((e, i) => (
            <div key={i} className="flex items-center gap-2 text-xs">
              <span className="text-slate-300 w-44 truncate font-mono">{e.src}</span>
              <span className="text-violet-500">→</span>
              <span className="text-slate-300 w-48 truncate font-mono">{e.tgt}</span>
              <span className="text-slate-500 ml-auto">{e.type}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
