import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Brain, RefreshCw, Search, GitBranch, Zap } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const GBRAIN_API = '/gbrain-svc'
const INTERNAL = { 'X-Internal-Secret': 'dev-secret', 'Content-Type': 'application/json' }

interface GraphStats {
  node_count: number
  edge_count: number
  avg_importance: number
  avg_degree: number
  top_nodes: { node_id: string; title: string; importance: number }[]
}

interface SearchResult {
  node_id: string
  title: string
  content: string
  source: string
  relevance_score: number
  importance: number
}

interface SearchResponse {
  query: string
  direct_results: SearchResult[]
  expanded_results: SearchResult[]
  total: number
}

export default function GBrainPage() {
  const { trackPageView } = useAnalytics()
  const [stats, setStats] = useState<GraphStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [searchResult, setSearchResult] = useState<SearchResponse | null>(null)
  const [recomputeMsg, setRecomputeMsg] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => { trackPageView('/gbrain') }, [trackPageView])

  const loadStats = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [hRes, sRes] = await Promise.all([
        fetch(`${GBRAIN_API}/health`),
        fetch(`${GBRAIN_API}/graph/stats`, { headers: INTERNAL }),
      ])
      if (!hRes.ok) throw new Error('GBrain service unavailable')
      if (sRes.ok) setStats(await sRes.json())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadStats() }, [loadStats])

  const doSearch = async () => {
    if (!query.trim()) return
    setSearching(true)
    setSearchResult(null)
    try {
      const res = await fetch(`${GBRAIN_API}/search`, {
        method: 'POST',
        headers: INTERNAL,
        body: JSON.stringify({ query: query.trim(), top_k: 10, max_hops: 2, max_results: 10 }),
      })
      if (res.ok) setSearchResult(await res.json())
    } catch { /* ignore */ }
    finally { setSearching(false) }
  }

  const recomputePageRank = async () => {
    try {
      const res = await fetch(`${GBRAIN_API}/pagerank/recompute`, { method: 'POST', headers: INTERNAL })
      if (res.ok) {
        const d = await res.json()
        setRecomputeMsg(`PageRank recomputed for ${d.node_count} nodes`)
        setTimeout(() => setRecomputeMsg(''), 4000)
        loadStats()
      }
    } catch { /* ignore */ }
  }

  const importanceBar = (v: number) => {
    const pct = Math.min(100, Math.round(v * 100))
    return (
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1.5 bg-slate-800 rounded-full overflow-hidden">
          <div className="h-full rounded-full bg-indigo-500 transition-all" style={{ width: `${pct}%` }} />
        </div>
        <span className="text-xs text-slate-500 w-8 text-right">{v.toFixed(2)}</span>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Brain size={22} className="text-purple-400" /> GBrain Bridge
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Associative knowledge graph — nodes, edges, semantic search, PageRank</p>
        </div>
        <button
          onClick={loadStats}
          disabled={loading}
          className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-300 hover:text-white disabled:opacity-50 transition-colors"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-lg bg-red-500/10 border border-red-500/30 px-4 py-3 text-sm text-red-300">
          {error} — is gbrain-bridge running on port 8030?
        </div>
      )}

      {recomputeMsg && (
        <div className="rounded-lg bg-emerald-500/10 border border-emerald-500/30 px-4 py-3 text-sm text-emerald-300">
          {recomputeMsg}
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Nodes</p>
          <p className="text-2xl font-bold text-white">{loading ? '—' : (stats?.node_count ?? 0)}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Edges</p>
          <p className="text-2xl font-bold text-indigo-400">{loading ? '—' : (stats?.edge_count ?? 0)}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Avg Degree</p>
          <p className="text-2xl font-bold text-slate-200">{loading ? '—' : (stats?.avg_degree.toFixed(1) ?? '—')}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Avg Importance</p>
          <p className="text-2xl font-bold text-purple-400">{loading ? '—' : (stats?.avg_importance.toFixed(3) ?? '—')}</p>
        </div>
      </div>

      {/* Semantic search */}
      <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
        <h2 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
          <Search size={14} className="text-slate-400" /> Associative Search
        </h2>
        <div className="flex gap-2">
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && doSearch()}
            placeholder="Search the knowledge graph…"
            className="flex-1 rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
          <button
            onClick={doSearch}
            disabled={searching || !query.trim()}
            className="flex items-center gap-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 px-4 py-2 text-xs text-white font-medium transition-colors"
          >
            {searching ? <RefreshCw size={12} className="animate-spin" /> : <Search size={12} />} Search
          </button>
        </div>

        {searchResult && (
          <div className="mt-4 space-y-2">
            <p className="text-xs text-slate-500">{searchResult.total} results for <span className="text-slate-300">"{searchResult.query}"</span></p>
            {searchResult.direct_results.map(r => (
              <div key={r.node_id} className="rounded-lg bg-slate-800/60 p-3 border border-slate-700/40">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-medium text-slate-200">{r.title}</p>
                  <span className="text-xs text-indigo-400 whitespace-nowrap">{(r.relevance_score * 100).toFixed(0)}%</span>
                </div>
                <p className="text-xs text-slate-500 mt-0.5 line-clamp-2">{r.content}</p>
                {r.source && <p className="text-xs text-slate-600 mt-1">source: {r.source}</p>}
              </div>
            ))}
            {searchResult.expanded_results.length > 0 && (
              <>
                <p className="text-xs text-slate-500 pt-1 flex items-center gap-1">
                  <GitBranch size={11} /> {searchResult.expanded_results.length} expanded (multi-hop)
                </p>
                {searchResult.expanded_results.slice(0, 3).map(r => (
                  <div key={r.node_id} className="rounded-lg bg-slate-800/30 p-3 border border-slate-700/20">
                    <p className="text-sm font-medium text-slate-400">{r.title}</p>
                    <p className="text-xs text-slate-600 mt-0.5 line-clamp-1">{r.content}</p>
                  </div>
                ))}
              </>
            )}
          </div>
        )}
      </div>

      {/* Top nodes by importance */}
      {stats && stats.top_nodes.length > 0 && (
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-white flex items-center gap-2">
              <Zap size={14} className="text-amber-400" /> Top Nodes by Importance
            </h2>
            <button
              onClick={recomputePageRank}
              className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
            >
              Recompute PageRank
            </button>
          </div>
          <div className="space-y-2">
            {stats.top_nodes.map((n, i) => (
              <div key={n.node_id} className="flex items-center gap-3">
                <span className="text-xs text-slate-600 w-5 text-right">{i + 1}</span>
                <span className="text-xs text-slate-300 flex-1 truncate">{n.title}</span>
                <div className="w-40">{importanceBar(n.importance)}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
