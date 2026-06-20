import React, { useCallback, useEffect, useState } from 'react'
import { GitMerge, RefreshCw, Server, Activity } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const API = '/gateway-svc'

interface WorkerStatus {
  status: string
  [key: string]: unknown
}

interface GatewayStats {
  upstream_workers: number
  reachable: number
  unreachable: number
  ws_connections: number
  abac_threat_level: string
}

const THREAT_COLORS: Record<string, string> = {
  low: 'text-emerald-400',
  medium: 'text-amber-400',
  high: 'text-orange-400',
  critical: 'text-red-400',
}

export default function GatewayPage() {
  const { trackPageView } = useAnalytics()
  const [upstreamCount, setUpstreamCount] = useState(0)
  const [wsConnections, setWsConnections] = useState(0)
  const [sentinelRunning, setSentinelRunning] = useState(false)
  const [stats, setStats] = useState<GatewayStats | null>(null)
  const [overview, setOverview] = useState<Record<string, WorkerStatus> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => { trackPageView('/gateway') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [healthRes, statsRes] = await Promise.all([
        fetch(`${API}/health`),
        fetch(`${API}/stats`),
      ])
      if (!healthRes.ok) throw new Error('Gateway unavailable')
      const h = await healthRes.json()
      setUpstreamCount(h.upstream_workers ?? 0)
      setWsConnections(h.ws_connections ?? 0)
      setSentinelRunning(h.sentinel_station?.running ?? false)
      if (statsRes.ok) {
        const s = await statsRes.json()
        setStats({
          upstream_workers: s.upstream_workers ?? 0,
          reachable: s.reachable ?? 0,
          unreachable: s.unreachable ?? 0,
          ws_connections: s.ws_connections ?? 0,
          abac_threat_level: s.abac_threat_level ?? 'low',
        })
      }
      // Try overview (may require auth)
      const overviewRes = await fetch(`${API}/api/overview`)
      if (overviewRes.ok) {
        setOverview(await overviewRes.json())
      }
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
            <GitMerge size={22} className="text-teal-400" /> Gateway Service
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Aggregation gateway — orchestrates upstream workers — Port 8040</p>
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
          {error} — is gateway-service running on port 8040?
        </div>
      )}

      <div className="grid grid-cols-4 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Upstream Workers</p>
          <p className="text-2xl font-bold text-white">{stats?.upstream_workers ?? upstreamCount}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Reachable</p>
          <p className="text-2xl font-bold text-emerald-400">{stats?.reachable ?? '—'}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">WS Connections</p>
          <p className="text-2xl font-bold text-blue-400">{stats?.ws_connections ?? wsConnections}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Threat Level</p>
          <p className={`text-2xl font-bold ${THREAT_COLORS[stats?.abac_threat_level ?? 'low'] ?? 'text-slate-400'}`}>
            {stats?.abac_threat_level ?? '—'}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2 mb-3"><Activity size={14} className="text-teal-400" /> System Status</h2>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-400">Sentinel Station</span>
              <span className={`text-xs ${sentinelRunning ? 'text-emerald-400' : 'text-red-400'}`}>
                {sentinelRunning ? 'running' : 'stopped'}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-400">Unreachable workers</span>
              <span className={`text-xs ${(stats?.unreachable ?? 0) > 0 ? 'text-red-400' : 'text-emerald-400'}`}>
                {stats?.unreachable ?? 0}
              </span>
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2 mb-3"><Server size={14} className="text-teal-400" /> Platform Overview</h2>
          {overview ? (
            <div className="space-y-1 max-h-48 overflow-y-auto">
              {Object.entries(overview).slice(0, 15).map(([name, info]) => (
                <div key={name} className="flex items-center justify-between">
                  <span className="text-xs text-slate-400 truncate">{name}</span>
                  <span className={`text-xs shrink-0 ml-2 ${info?.status === 'ok' || info?.status === 'healthy' ? 'text-emerald-400' : 'text-red-400'}`}>
                    {String(info?.status ?? '—')}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-slate-500">Overview requires auth or service offline</p>
          )}
        </div>
      </div>
    </div>
  )
}
