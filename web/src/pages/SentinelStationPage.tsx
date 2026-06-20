import React, { useCallback, useEffect, useState } from 'react'
import { Radio, RefreshCw, Send, List } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const API = '/sentinel-svc'
const INTERNAL = { 'X-Internal-Secret': 'dev-secret', 'Content-Type': 'application/json' }

interface ChannelInfo {
  name: string
  subscribers: number
  events_published?: number
}

interface EventHistory {
  event_id: string
  channel: string
  event_type: string
  published_at: string
}

export default function SentinelStationPage() {
  const { trackPageView } = useAnalytics()
  const [healthScore, setHealthScore] = useState<number | null>(null)
  const [healthTier, setHealthTier] = useState<string>('')
  const [channels, setChannels] = useState<ChannelInfo[]>([])
  const [history, setHistory] = useState<EventHistory[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [channel, setChannel] = useState('platform.events')
  const [eventType, setEventType] = useState('ping')
  const [payload, setPayload] = useState('{}')
  const [publishing, setPublishing] = useState(false)
  const [publishMsg, setPublishMsg] = useState<string | null>(null)

  useEffect(() => { trackPageView('/sentinel-station') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [healthRes, channelsRes, historyRes] = await Promise.all([
        fetch(`${API}/health`),
        fetch(`${API}/api/channels`),
        fetch(`${API}/api/events/history?limit=10`),
      ])
      if (!healthRes.ok) throw new Error('Sentinel Station unavailable')
      const h = await healthRes.json()
      setHealthScore(h.health_score ?? null)
      setHealthTier(h.health_tier ?? '')
      if (channelsRes.ok) {
        const c = await channelsRes.json()
        setChannels(c.channels ?? c)
      }
      if (historyRes.ok) {
        const e = await historyRes.json()
        setHistory(e.events ?? e)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const publishEvent = async () => {
    setPublishing(true)
    setPublishMsg(null)
    try {
      let parsedPayload = {}
      try { parsedPayload = JSON.parse(payload) } catch { /* use empty */ }
      const res = await fetch(`${API}/api/events/publish`, {
        method: 'POST',
        headers: INTERNAL,
        body: JSON.stringify({ channel, event_type: eventType, payload: parsedPayload }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setPublishMsg('Event published!')
      loadData()
    } catch (e) {
      setPublishMsg(e instanceof Error ? e.message : 'Failed')
    } finally {
      setPublishing(false)
    }
  }

  const tierColor = (tier: string) => {
    if (tier === 'EXCELLENT') return 'text-emerald-400'
    if (tier === 'GOOD') return 'text-blue-400'
    if (tier === 'DEGRADED') return 'text-amber-400'
    return 'text-red-400'
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Radio size={22} className="text-violet-400" /> Sentinel Station
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Event bus bridge &amp; channel coordinator — Port 8041</p>
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
          {error} — is sentinel-station-service running on port 8041?
        </div>
      )}

      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Health Score</p>
          <p className="text-2xl font-bold text-white">
            {healthScore !== null ? (healthScore * 100).toFixed(0) + '%' : '—'}
          </p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Tier</p>
          <p className={`text-2xl font-bold ${tierColor(healthTier)}`}>{healthTier || '—'}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Channels</p>
          <p className="text-2xl font-bold text-violet-400">{channels.length}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4 space-y-3">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2"><Send size={14} className="text-violet-400" /> Publish Event</h2>
          <input
            value={channel}
            onChange={e => setChannel(e.target.value)}
            placeholder="Channel (e.g. platform.events)"
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-violet-500"
          />
          <input
            value={eventType}
            onChange={e => setEventType(e.target.value)}
            placeholder="Event type (e.g. ping)"
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-violet-500"
          />
          <textarea
            value={payload}
            onChange={e => setPayload(e.target.value)}
            placeholder='{"key": "value"}'
            rows={3}
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-violet-500 resize-none font-mono"
          />
          <button
            onClick={publishEvent}
            disabled={publishing}
            className="w-full flex items-center justify-center gap-1.5 rounded-lg bg-violet-600 hover:bg-violet-700 disabled:opacity-50 px-4 py-1.5 text-xs text-white font-medium transition-colors"
          >
            <Send size={11} /> {publishing ? 'Publishing…' : 'Publish'}
          </button>
          {publishMsg && <p className="text-xs text-emerald-400">{publishMsg}</p>}
        </div>

        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2 mb-3"><List size={14} className="text-violet-400" /> Event History</h2>
          {history.length === 0 ? (
            <p className="text-xs text-slate-500">No events yet</p>
          ) : (
            <div className="space-y-2">
              {history.map(e => (
                <div key={e.event_id} className="py-2 border-b border-slate-800 last:border-0">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-slate-200">{e.event_type}</span>
                    <span className="text-xs text-slate-500">{e.channel}</span>
                  </div>
                  <p className="text-xs text-slate-600 font-mono">{e.event_id.slice(0, 16)}…</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
