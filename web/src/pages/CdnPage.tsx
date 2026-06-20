import React, { useCallback, useEffect, useState } from 'react'
import { Globe, RefreshCw, FileText } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const CDN_API = '/cdn-svc'
const INTERNAL = { 'X-Internal-Secret': 'dev-secret' }

interface Asset {
  path: string
  size: number
  content_type: string
  cache_policy: string
  serve_count: number
  etag: string
  last_served: number | null
}

interface AssetStats {
  by_policy: { cache_policy: string; count: number; bytes: number }[]
  top_assets: { path: string; serve_count: number }[]
}

const POLICY_COLORS: Record<string, string> = {
  immutable: 'bg-purple-500/20 text-purple-300 border-purple-500/30',
  long:      'bg-blue-500/20 text-blue-300 border-blue-500/30',
  medium:    'bg-teal-500/20 text-teal-300 border-teal-500/30',
  short:     'bg-amber-500/20 text-amber-300 border-amber-500/30',
  no_cache:  'bg-slate-700/40 text-slate-400 border-slate-600/30',
}

function fmtBytes(b: number) {
  if (b < 1024) return `${b}B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)}KB`
  if (b < 1024 * 1024 * 1024) return `${(b / 1024 / 1024).toFixed(2)}MB`
  return `${(b / 1024 / 1024 / 1024).toFixed(2)}GB`
}

export default function CdnPage() {
  const { trackPageView } = useAnalytics()
  const [assetCt, setAssetCt] = useState(0)
  const [totalBytes, setTotalBytes] = useState(0)
  const [totalServes, setTotalServes] = useState(0)
  const [assets, setAssets] = useState<Asset[]>([])
  const [stats, setStats] = useState<AssetStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [prefix, setPrefix] = useState('')

  useEffect(() => { trackPageView('/cdn') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const q = prefix ? `?prefix=${encodeURIComponent(prefix)}&limit=50` : '?limit=50'
      const [hRes, aRes, stRes] = await Promise.all([
        fetch(`${CDN_API}/health`),
        fetch(`${CDN_API}/assets${q}`, { headers: INTERNAL }),
        fetch(`${CDN_API}/assets/stats`, { headers: INTERNAL }),
      ])
      if (!hRes.ok) throw new Error('CDN service unavailable')
      const h = await hRes.json()
      setAssetCt(h.registered_assets ?? 0)
      setTotalBytes(h.total_bytes ?? 0)
      setTotalServes(h.total_serves ?? 0)
      const [a, st] = await Promise.all([
        aRes.ok ? aRes.json() : null,
        stRes.ok ? stRes.json() : null,
      ])
      if (a) setAssets(a.assets ?? [])
      if (st) setStats(st)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [prefix])

  useEffect(() => { loadData() }, [loadData])

  const fmt = (ts: number) => {
    try { return new Date(ts * 1000).toLocaleString() } catch { return String(ts) }
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Globe size={22} className="text-blue-400" /> CDN Service
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Static asset delivery with ETag caching, cache policies, and serve log</p>
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
          {error} — is cdn-service running on port 8028?
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Registered Assets</p>
          <p className="text-2xl font-bold text-white">{assetCt}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Total Size</p>
          <p className="text-2xl font-bold text-blue-400">{fmtBytes(totalBytes)}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Total Serves</p>
          <p className="text-2xl font-bold text-slate-200">{totalServes.toLocaleString()}</p>
        </div>
      </div>

      {/* Cache policy breakdown */}
      {stats && stats.by_policy.length > 0 && (
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <h2 className="text-sm font-semibold text-white mb-3">By Cache Policy</h2>
          <div className="flex flex-wrap gap-2">
            {stats.by_policy.map(({ cache_policy, count, bytes }) => (
              <span key={cache_policy} className={`text-xs px-2 py-1 rounded border ${POLICY_COLORS[cache_policy] ?? 'bg-slate-700/40 text-slate-300 border-slate-600/30'}`}>
                {cache_policy}: <span className="font-bold">{count}</span> <span className="opacity-60">({fmtBytes(bytes)})</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Top assets */}
      {stats && stats.top_assets.length > 0 && (
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <h2 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
            <FileText size={14} className="text-slate-400" /> Top Assets by Serves
          </h2>
          <div className="space-y-1.5">
            {stats.top_assets.map((a, i) => (
              <div key={a.path} className="flex items-center gap-3 text-xs">
                <span className="text-slate-600 w-5 text-right">{i + 1}</span>
                <span className="text-slate-300 font-mono truncate flex-1">{a.path}</span>
                <span className="text-indigo-400 font-medium">{a.serve_count.toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Asset browser */}
      <div>
        <div className="flex gap-2 mb-3">
          <input
            value={prefix}
            onChange={e => setPrefix(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && loadData()}
            placeholder="Filter by path prefix…"
            className="flex-1 rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
          <button
            onClick={loadData}
            className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-300 hover:text-white transition-colors"
          >
            Filter
          </button>
        </div>

        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 overflow-hidden">
          {loading ? (
            <div className="p-8 text-center text-slate-500 text-sm">Loading…</div>
          ) : assets.length === 0 ? (
            <div className="p-8 text-center text-slate-500 text-sm">No assets registered.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700/60 text-xs text-slate-500 uppercase tracking-wider">
                    <th className="text-left px-4 py-2">Path</th>
                    <th className="text-left px-4 py-2">Type</th>
                    <th className="text-left px-4 py-2">Policy</th>
                    <th className="text-right px-4 py-2">Size</th>
                    <th className="text-right px-4 py-2">Serves</th>
                    <th className="text-right px-4 py-2">Last Served</th>
                  </tr>
                </thead>
                <tbody>
                  {assets.map(a => (
                    <tr key={a.path} className="border-b border-slate-800 hover:bg-slate-800/30 transition-colors">
                      <td className="px-4 py-2.5 text-xs font-mono text-slate-300 max-w-xs truncate">{a.path}</td>
                      <td className="px-4 py-2.5 text-xs text-slate-500">{a.content_type}</td>
                      <td className="px-4 py-2.5">
                        <span className={`text-xs px-1.5 py-0.5 rounded border ${POLICY_COLORS[a.cache_policy] ?? 'bg-slate-700/40 text-slate-400 border-slate-600/30'}`}>
                          {a.cache_policy}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-right text-xs text-slate-500">{fmtBytes(a.size)}</td>
                      <td className="px-4 py-2.5 text-right text-xs text-indigo-400">{a.serve_count.toLocaleString()}</td>
                      <td className="px-4 py-2.5 text-right text-xs text-slate-600 whitespace-nowrap">
                        {a.last_served ? fmt(a.last_served) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
