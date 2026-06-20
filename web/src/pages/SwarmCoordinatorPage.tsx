import React, { useCallback, useEffect, useState } from 'react'
import { Network, RefreshCw, Play } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const API = '/swarm-svc'
const INTERNAL = { 'X-Internal-Secret': 'dev-secret' }

interface SwarmStatus {
  service: string
  running: boolean
  last_run: string | null
  manifests: string[]
}

export default function SwarmCoordinatorPage() {
  const { trackPageView } = useAnalytics()
  const [status, setStatus] = useState<SwarmStatus | null>(null)
  const [lastRun, setLastRun] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [triggering, setTriggering] = useState(false)
  const [runMsg, setRunMsg] = useState<string | null>(null)

  useEffect(() => { trackPageView('/swarm-coordinator') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [hRes, stRes] = await Promise.all([
        fetch(`${API}/health`),
        fetch(`${API}/status`, { headers: INTERNAL }),
      ])
      if (!hRes.ok) throw new Error('Swarm Coordinator unavailable')
      const h = await hRes.json()
      setLastRun(h.last_run ?? null)
      if (stRes.ok) setStatus(await stRes.json())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const triggerRun = async () => {
    setTriggering(true)
    setRunMsg(null)
    try {
      const res = await fetch(`${API}/run`, { method: 'POST', headers: INTERNAL })
      const data = await res.json()
      setRunMsg(data.status ?? 'triggered')
      await loadData()
    } catch {
      setRunMsg('error')
    } finally {
      setTriggering(false)
    }
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Network size={22} className="text-violet-400" /> Swarm Coordinator
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Manifest-driven swarm orchestration service</p>
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
          {error} — is swarm-coordinator-service running on port 8053?
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Status</p>
          <p className={`text-lg font-bold ${status?.running ? 'text-amber-400' : 'text-emerald-400'}`}>
            {status ? (status.running ? 'Running' : 'Idle') : '—'}
          </p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Last Run</p>
          <p className="text-xs font-mono text-slate-300">{lastRun ?? 'Never'}</p>
        </div>
      </div>

      <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-white">Manifests</h2>
          <span className="text-xs text-slate-400">{status?.manifests.length ?? 0} loaded</span>
        </div>
        {status?.manifests.length === 0 ? (
          <p className="text-sm text-slate-500 py-2">No manifest files found.</p>
        ) : (
          <div className="space-y-1">
            {(status?.manifests ?? []).map((m) => (
              <div key={m} className="text-xs font-mono text-slate-300 bg-slate-800/50 rounded px-2 py-1">{m}</div>
            ))}
          </div>
        )}
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={triggerRun}
          disabled={triggering || status?.running}
          className="flex items-center gap-1.5 rounded-lg bg-violet-600 hover:bg-violet-700 disabled:opacity-50 px-4 py-2 text-xs text-white font-medium transition-colors"
        >
          <Play size={12} /> Trigger Run Now
        </button>
        {runMsg && <span className="text-xs text-slate-400">{runMsg}</span>}
      </div>
    </div>
  )
}
