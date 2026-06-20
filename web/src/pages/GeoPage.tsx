import React, { useCallback, useEffect, useState } from 'react'
import { Globe, RefreshCw, Search } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const GEO_API = '/geo-svc'
const INTERNAL = { 'X-Internal-Secret': 'dev-secret' }

interface GeoResult {
  ip: string
  country?: string
  country_code?: string
  city?: string
  lat?: number
  lon?: number
  timezone?: string
  source?: string
  cached?: boolean
}

interface CacheStats {
  total_cached: number
  fresh: number
  stale: number
  by_source: { source: string; c: number }[]
}

export default function GeoPage() {
  const { trackPageView } = useAnalytics()
  const [cachedIps, setCachedIps] = useState(0)
  const [cacheStats, setCacheStats] = useState<CacheStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lookupIp, setLookupIp] = useState('')
  const [lookupResult, setLookupResult] = useState<GeoResult | null>(null)
  const [lookupLoading, setLookupLoading] = useState(false)
  const [lookupError, setLookupError] = useState<string | null>(null)

  useEffect(() => { trackPageView('/geo') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [hRes, cRes] = await Promise.all([
        fetch(`${GEO_API}/health`),
        fetch(`${GEO_API}/cache`, { headers: INTERNAL }),
      ])
      if (!hRes.ok) throw new Error('Service unavailable')
      const [h, c] = await Promise.all([hRes.json(), cRes.ok ? cRes.json() : null])
      setCachedIps(h.cached_ips ?? 0)
      if (c) setCacheStats(c)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const doLookup = async () => {
    const ip = lookupIp.trim()
    if (!ip) return
    setLookupLoading(true)
    setLookupResult(null)
    setLookupError(null)
    try {
      const r = await fetch(`${GEO_API}/lookup/${encodeURIComponent(ip)}`, { headers: INTERNAL })
      if (r.ok) {
        setLookupResult(await r.json())
        loadData()
      } else {
        const d = await r.json()
        setLookupError(d.detail ?? 'Lookup failed')
      }
    } catch {
      setLookupError('Request failed')
    } finally {
      setLookupLoading(false)
    }
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Globe size={22} className="text-slate-400" /> Geo Service
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">IP geolocation with SQLite cache — country, city, timezone, coordinates</p>
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
          {error} — is geo-service running on port 8027?
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-4 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Cached IPs</p>
          <p className="text-2xl font-bold text-white">{cachedIps}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Fresh</p>
          <p className="text-2xl font-bold text-emerald-400">{cacheStats?.fresh ?? '—'}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Stale</p>
          <p className="text-2xl font-bold text-amber-400">{cacheStats?.stale ?? '—'}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Sources</p>
          <p className="text-2xl font-bold text-slate-300">{cacheStats?.by_source?.length ?? '—'}</p>
        </div>
      </div>

      {/* IP Lookup */}
      <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4 space-y-4">
        <h2 className="text-sm font-semibold text-white">IP Lookup</h2>
        <div className="flex items-center gap-2">
          <input
            type="text"
            placeholder="Enter IP address (e.g. 8.8.8.8)"
            value={lookupIp}
            onChange={e => setLookupIp(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && doLookup()}
            className="flex-1 rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-slate-500"
          />
          <button
            onClick={doLookup}
            disabled={lookupLoading || !lookupIp.trim()}
            className="flex items-center gap-1.5 rounded-lg border border-indigo-600/50 bg-indigo-600/20 px-4 py-1.5 text-sm text-indigo-300 hover:bg-indigo-600/30 disabled:opacity-50 transition-colors"
          >
            <Search size={14} /> {lookupLoading ? 'Looking up…' : 'Lookup'}
          </button>
        </div>

        {lookupError && (
          <p className="text-sm text-red-400">{lookupError}</p>
        )}

        {lookupResult && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-2">
            {[
              { label: 'IP', value: lookupResult.ip },
              { label: 'Country', value: lookupResult.country ?? '—' },
              { label: 'City', value: lookupResult.city ?? '—' },
              { label: 'Code', value: lookupResult.country_code ?? '—' },
              { label: 'Latitude', value: lookupResult.lat?.toFixed(4) ?? '—' },
              { label: 'Longitude', value: lookupResult.lon?.toFixed(4) ?? '—' },
              { label: 'Timezone', value: lookupResult.timezone ?? '—' },
              { label: 'Source', value: lookupResult.source ?? '—' },
            ].map(({ label, value }) => (
              <div key={label} className="rounded-lg bg-slate-800/50 p-3">
                <p className="text-xs text-slate-500 mb-0.5">{label}</p>
                <p className="text-sm text-slate-200 font-medium">{value}</p>
              </div>
            ))}
            {lookupResult.cached !== undefined && (
              <div className="col-span-2 sm:col-span-4">
                <span className={`text-xs px-2 py-0.5 rounded border ${lookupResult.cached ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' : 'bg-blue-500/20 text-blue-300 border-blue-500/30'}`}>
                  {lookupResult.cached ? 'Served from cache' : 'Fresh lookup'}
                </span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Cache sources */}
      {cacheStats?.by_source && cacheStats.by_source.length > 0 && (
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <h2 className="text-sm font-semibold text-white mb-3">Cache by Source</h2>
          <div className="space-y-2">
            {cacheStats.by_source.map(({ source, c }) => {
              const total = cacheStats.total_cached || 1
              return (
                <div key={source} className="flex items-center gap-3">
                  <span className="text-xs text-slate-400 w-28 truncate">{source}</span>
                  <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-indigo-500 rounded-full"
                      style={{ width: `${(c / total) * 100}%` }}
                    />
                  </div>
                  <span className="text-xs text-slate-500 w-8 text-right">{c}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
