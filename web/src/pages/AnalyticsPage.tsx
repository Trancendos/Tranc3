import React, { useCallback, useEffect, useState } from 'react'
import { BarChart3, RefreshCw, TrendingUp } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const ANALYTICS_API = '/analytics'
const INTERNAL = { 'X-Internal-Secret': 'dev-secret' }

interface Summary {
  total_events: number
  total_metric_points: number
  top_event_types: Array<{ event_type: string; c: number }>
  top_metrics_by_avg: Array<{ name: string; avg_val: number }>
}

interface Event {
  id: number
  event_type: string
  user_id: string | null
  session_id: string | null
  properties: string
  timestamp: number
  date_str: string
}

interface EventTypeStat {
  event_type: string
  count: number
}

type Tab = 'overview' | 'events'

function StatTile({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
      <p className="text-xs text-slate-400 mb-1">{label}</p>
      <p className="text-2xl font-bold text-white">{value}</p>
      {sub && <p className="text-xs text-slate-500 mt-0.5">{sub}</p>}
    </div>
  )
}

export default function AnalyticsPage() {
  const { trackPageView } = useAnalytics()
  const [summary, setSummary] = useState<Summary | null>(null)
  const [eventTypes, setEventTypes] = useState<EventTypeStat[]>([])
  const [events, setEvents] = useState<Event[]>([])
  const [tab, setTab] = useState<Tab>('overview')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filterType, setFilterType] = useState('')

  useEffect(() => { trackPageView('/analytics') }, [trackPageView])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({ limit: '100' })
      if (filterType) params.set('event_type', filterType)
      const [sRes, etRes, evRes] = await Promise.all([
        fetch(`${ANALYTICS_API}/summary`, { headers: INTERNAL }),
        fetch(`${ANALYTICS_API}/events/types`, { headers: INTERNAL }),
        fetch(`${ANALYTICS_API}/events?${params}`, { headers: INTERNAL }),
      ])
      if (!sRes.ok || !etRes.ok || !evRes.ok) throw new Error('Service unavailable')
      const [s, et, ev] = await Promise.all([sRes.json(), etRes.json(), evRes.json()])
      setSummary(s)
      setEventTypes(et.types ?? [])
      setEvents(ev.events ?? [])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [filterType])

  useEffect(() => { load() }, [load])

  const fmt = (ts: number) => {
    try { return new Date(ts * 1000).toLocaleString() } catch { return String(ts) }
  }

  const props = (raw: string) => {
    try {
      const p = JSON.parse(raw)
      return Object.entries(p).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(' · ')
    } catch { return raw }
  }

  const maxCount = Math.max(...eventTypes.map(e => e.count), 1)

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <BarChart3 size={22} className="text-indigo-400" /> Analytics
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Platform event ingestion · metrics store · funnel analysis</p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-300 hover:text-white disabled:opacity-50 transition-colors"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-lg bg-red-500/10 border border-red-500/30 px-4 py-3 text-sm text-red-300">
          {error} — is analytics-service running on port 8016?
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatTile label="Total Events" value={summary?.total_events ?? '—'} />
        <StatTile label="Metric Points" value={summary?.total_metric_points ?? '—'} />
        <StatTile label="Event Types" value={eventTypes.length} sub="distinct types" />
        <StatTile label="Top Event" value={summary?.top_event_types?.[0]?.event_type ?? '—'} sub={summary?.top_event_types?.[0] ? `${summary.top_event_types[0].c} times` : undefined} />
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-700/60">
        {(['overview', 'events'] as Tab[]).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium capitalize transition-colors border-b-2 -mb-px ${
              tab === t ? 'border-indigo-500 text-indigo-400' : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            {t === 'overview' ? 'Event Types' : 'Recent Events'}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <div className="space-y-4">
          {/* Event type breakdown */}
          <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
            <h2 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
              <TrendingUp size={14} className="text-indigo-400" /> Event Distribution
            </h2>
            {loading && !eventTypes.length ? (
              <div className="text-center text-slate-500 text-sm py-4">Loading…</div>
            ) : eventTypes.length === 0 ? (
              <div className="text-center text-slate-500 text-sm py-4">No events ingested yet.</div>
            ) : (
              <div className="space-y-2">
                {eventTypes.map(et => (
                  <div key={et.event_type} className="flex items-center gap-3">
                    <span className="text-xs font-mono text-slate-300 w-48 truncate">{et.event_type}</span>
                    <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full bg-indigo-500 transition-all"
                        style={{ width: `${(et.count / maxCount) * 100}%` }}
                      />
                    </div>
                    <span className="text-xs text-slate-500 w-10 text-right">{et.count}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Top metrics */}
          {summary?.top_metrics_by_avg && summary.top_metrics_by_avg.length > 0 && (
            <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
              <h2 className="text-sm font-semibold text-white mb-3">Top Metrics (by avg value)</h2>
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                {summary.top_metrics_by_avg.map(m => (
                  <div key={m.name} className="rounded-lg border border-slate-700/40 bg-slate-800/40 p-3">
                    <p className="text-xs font-mono text-slate-400 truncate mb-1">{m.name}</p>
                    <p className="text-lg font-bold text-white">{m.avg_val.toFixed(2)}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {tab === 'events' && (
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 overflow-hidden">
          <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-700/60">
            <h2 className="text-sm font-semibold text-white">Recent Events</h2>
            <input
              type="text"
              placeholder="Filter by type…"
              value={filterType}
              onChange={e => setFilterType(e.target.value)}
              className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-slate-500 w-40"
            />
            <span className="text-xs text-slate-500 ml-auto">{events.length} events</span>
          </div>
          {loading && !events.length ? (
            <div className="p-8 text-center text-slate-500 text-sm">Loading events…</div>
          ) : events.length === 0 ? (
            <div className="p-8 text-center text-slate-500 text-sm">No events found.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700/60 text-xs text-slate-500 uppercase tracking-wider">
                    <th className="text-left px-4 py-2">Timestamp</th>
                    <th className="text-left px-4 py-2">Type</th>
                    <th className="text-left px-4 py-2">User</th>
                    <th className="text-left px-4 py-2">Properties</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map(e => (
                    <tr key={e.id} className="border-b border-slate-800 hover:bg-slate-800/30 transition-colors">
                      <td className="px-4 py-2.5 text-slate-400 whitespace-nowrap text-xs">{fmt(e.timestamp)}</td>
                      <td className="px-4 py-2.5">
                        <span className="text-xs px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 font-mono">
                          {e.event_type}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-slate-400 text-xs">{e.user_id ?? '—'}</td>
                      <td className="px-4 py-2.5 text-slate-500 text-xs truncate max-w-xs">{props(e.properties)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
