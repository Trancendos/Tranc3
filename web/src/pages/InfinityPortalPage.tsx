import React, { useCallback, useEffect, useState } from 'react'
import { Shield, RefreshCw, Users, GitBranch, Activity } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const API = '/iportal-svc'
const INTERNAL = { 'X-Internal-Secret': 'dev-secret' }

interface PortalStats {
  sessions: { active: number; total: number }
  events: { total: number }
  gate_routing: { total: number }
}

interface PortalStatus {
  status: string
  portal_name: string
  ecosystem_name: string
  active_sessions: number
  locations: Record<string, unknown>
  gate_routing: Record<string, unknown>
}

interface PortalEvent {
  id: number
  event_type: string
  source?: string
  timestamp: number
}

export default function InfinityPortalPage() {
  const { trackPageView } = useAnalytics()
  const [stats, setStats] = useState<PortalStats | null>(null)
  const [status, setStatus] = useState<PortalStatus | null>(null)
  const [events, setEvents] = useState<PortalEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => { trackPageView('/infinity-portal') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [hRes, stRes, evRes] = await Promise.all([
        fetch(`${API}/health`),
        fetch(`${API}/stats`, { headers: INTERNAL }),
        fetch(`${API}/portal/events?limit=20`, { headers: INTERNAL }),
      ])
      if (!hRes.ok) throw new Error('Infinity Portal unavailable')
      const [st, ev] = await Promise.all([
        stRes.ok ? stRes.json() : null,
        evRes.ok ? evRes.json() : null,
      ])
      if (st) setStats(st)

      const [statusRes] = await Promise.all([
        fetch(`${API}/portal/status`, { headers: INTERNAL }),
      ])
      if (statusRes.ok) setStatus(await statusRes.json())

      if (ev) setEvents(Array.isArray(ev) ? ev : (ev.events ?? []))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const fmt = (ts: number) => {
    try { return new Date(ts * 1000).toLocaleString() } catch { return String(ts) }
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Shield size={22} className="text-indigo-400" /> Infinity Portal
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Central login & front entrance — Infinity Ecosystem gateway</p>
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
          {error} — is infinity-portal-service running on port 8042?
        </div>
      )}

      {status && (
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-semibold text-white">{status.portal_name}</p>
              <p className="text-xs text-slate-400 mt-0.5">{status.ecosystem_name}</p>
            </div>
            <span className={`text-xs px-2 py-0.5 rounded-full ${status.status === 'operational' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-amber-500/20 text-amber-400'}`}>
              {status.status}
            </span>
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1 flex items-center gap-1"><Users size={11} /> Active Sessions</p>
          <p className="text-2xl font-bold text-white">{stats?.sessions.active ?? '—'}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Total Sessions</p>
          <p className="text-2xl font-bold text-indigo-400">{stats?.sessions.total ?? '—'}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1 flex items-center gap-1"><Activity size={11} /> Events</p>
          <p className="text-2xl font-bold text-slate-200">{stats?.events.total ?? '—'}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1 flex items-center gap-1"><GitBranch size={11} /> Gate Routings</p>
          <p className="text-2xl font-bold text-slate-200">{stats?.gate_routing.total ?? '—'}</p>
        </div>
      </div>

      <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
        <h2 className="text-sm font-semibold text-white mb-3">Recent Portal Events</h2>
        {loading ? (
          <p className="text-sm text-slate-500 text-center py-4">Loading…</p>
        ) : events.length === 0 ? (
          <p className="text-sm text-slate-500 text-center py-4">No events recorded.</p>
        ) : (
          <div className="space-y-1.5">
            {events.map((ev) => (
              <div key={ev.id} className="flex items-center gap-3 text-xs border-b border-slate-800 pb-1.5">
                <span className="text-indigo-400 font-mono w-40 truncate">{ev.event_type}</span>
                {ev.source && <span className="text-slate-500 truncate flex-1">{ev.source}</span>}
                <span className="text-slate-600 whitespace-nowrap ml-auto">{fmt(ev.timestamp)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
