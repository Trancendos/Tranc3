/**
 * TheDutchyPage — Intelligence & Market Analysis (The Dutchy · Port 8061)
 * Lead AI: Predictive lore
 *
 * Displays RSS feeds, trending articles, and market intelligence reports.
 */
import React, { useEffect, useState, useCallback } from 'react'
import { BarChart3, RefreshCw, Rss, TrendingUp, ExternalLink, Play } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const API = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'
const DUTCHY_API = API.replace(/:\d+$/, ':8061')

const CATEGORY_COLORS: Record<string, string> = {
  tech:     'bg-blue-900/40 text-blue-300 border-blue-700',
  business: 'bg-green-900/40 text-green-300 border-green-700',
  finance:  'bg-yellow-900/40 text-yellow-300 border-yellow-700',
  general:  'bg-gray-800 text-gray-400 border-gray-600',
}

interface Feed {
  id: number
  name: string
  url: string
  category: string
  active: number
  last_fetched: number | null
  article_count: number
}

interface Article {
  id: number
  title: string
  url: string | null
  summary: string | null
  author: string | null
  published_at: number | null
  trend_score: number
  category: string
  tags: string
}

export default function TheDutchyPage() {
  const [feeds, setFeeds]       = useState<Feed[]>([])
  const [articles, setArticles] = useState<Article[]>([])
  const [totalArt, setTotalArt] = useState(0)
  const [loading, setLoading]   = useState(false)
  const [fetching, setFetching] = useState(false)
  const [healthOk, setHealthOk] = useState<boolean | null>(null)
  const [tab, setTab]           = useState<'articles' | 'feeds'>('articles')
  const [minScore, setMinScore] = useState(0)
  const { trackPageView } = useAnalytics()

  useEffect(() => { trackPageView('/the-dutchy') }, [trackPageView])

  const headers = { 'X-Internal-Secret': 'dev-secret' }

  const loadFeeds = useCallback(async () => {
    try {
      const r = await fetch('/dutchy/feeds', { headers })
      if (r.ok) setFeeds(await r.json())
    } catch { /* swallow */ }
  }, [])

  const loadArticles = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ limit: '60', offset: '0' })
      if (minScore > 0) params.set('min_score', String(minScore))
      const r = await fetch(`/dutchy/articles?${params}`, { headers })
      if (r.ok) {
        const body = await r.json()
        setArticles(body.articles ?? [])
        setTotalArt(body.total ?? 0)
        setHealthOk(true)
      } else {
        setHealthOk(false)
      }
    } catch {
      setHealthOk(false)
    }
    setLoading(false)
  }, [minScore])

  useEffect(() => {
    loadFeeds()
    loadArticles()
  }, [loadFeeds, loadArticles])

  const fetchAll = useCallback(async () => {
    setFetching(true)
    try {
      await fetch('/dutchy/fetch/all', { method: 'POST', headers })
      setTimeout(() => { loadFeeds(); loadArticles() }, 3000)
    } catch { /* swallow */ }
    setFetching(false)
  }, [loadFeeds, loadArticles])

  const fmtDate = (ts: number | null) => {
    if (!ts) return '—'
    return new Date(ts * 1000).toLocaleDateString()
  }

  const scoreColor = (s: number) =>
    s >= 3 ? 'text-red-400' : s >= 1.5 ? 'text-yellow-400' : 'text-gray-500'

  const parseTags = (raw: string): string[] => {
    try { return JSON.parse(raw) } catch { return [] }
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <BarChart3 size={22} aria-hidden="true" className="text-emerald-400" />
            The Dutchy
          </h1>
          <p className="text-gray-400 text-sm mt-1">
            Intelligence &amp; Market Analysis · Lead AI: Predictive lore · Port 8061
            {totalArt > 0 && ` · ${totalArt} articles indexed`}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={fetchAll}
            disabled={fetching}
            className="flex items-center gap-2 px-3 py-2 bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 rounded-lg text-sm text-white transition-colors"
          >
            <Play size={14} aria-hidden="true" className={fetching ? 'animate-spin' : ''} />
            {fetching ? 'Fetching…' : 'Fetch All Feeds'}
          </button>
          <button
            onClick={() => { loadFeeds(); loadArticles() }}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg text-sm text-white transition-colors"
          >
            <RefreshCw size={14} aria-hidden="true" className={loading ? 'animate-spin' : ''} />
            {loading ? 'Loading…' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Health banner */}
      {healthOk === false && (
        <div role="alert" className="mb-4 p-3 bg-yellow-900/30 border border-yellow-700 rounded-lg text-yellow-300 text-sm">
          The Dutchy worker (port 8061) is unreachable. Start with{' '}
          <code className="font-mono bg-gray-800 px-1 rounded">make dev-api</code>.
        </div>
      )}

      {/* Summary tiles */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="bg-gray-900 border border-gray-700 rounded-lg p-4">
          <div className="text-2xl font-bold text-emerald-400 tabular-nums">{feeds.filter(f => f.active).length}</div>
          <div className="text-gray-400 text-sm mt-1">Active Feeds</div>
        </div>
        <div className="bg-gray-900 border border-gray-700 rounded-lg p-4">
          <div className="text-2xl font-bold text-blue-400 tabular-nums">{totalArt}</div>
          <div className="text-gray-400 text-sm mt-1">Articles Indexed</div>
        </div>
        <div className="bg-gray-900 border border-gray-700 rounded-lg p-4">
          <div className="text-2xl font-bold text-yellow-400 tabular-nums">
            {articles.filter(a => a.trend_score >= 1.5).length}
          </div>
          <div className="text-gray-400 text-sm mt-1">Trending</div>
        </div>
      </div>

      {/* Tabs */}
      <div role="tablist" className="flex gap-2 mb-5">
        {(['articles', 'feeds'] as const).map(t => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium border transition-colors ${
              tab === t
                ? 'bg-indigo-600 text-white border-indigo-500'
                : 'bg-gray-900 text-gray-400 border-gray-700 hover:border-gray-500'
            }`}
          >
            {t === 'articles' ? <><TrendingUp size={12} className="inline mr-1.5" aria-hidden="true" />Articles</> : <><Rss size={12} className="inline mr-1.5" aria-hidden="true" />Feeds</>}
          </button>
        ))}
        {tab === 'articles' && (
          <div className="ml-auto flex items-center gap-2 text-sm text-gray-400">
            <label htmlFor="min-score">Min score:</label>
            <select
              id="min-score"
              value={minScore}
              onChange={e => setMinScore(Number(e.target.value))}
              className="bg-gray-900 border border-gray-700 rounded px-2 py-1 text-sm text-white focus:outline-none"
            >
              <option value={0}>All</option>
              <option value={0.5}>≥ 0.5</option>
              <option value={1.5}>≥ 1.5 (trending)</option>
              <option value={3}>≥ 3.0 (hot)</option>
            </select>
          </div>
        )}
      </div>

      {/* Articles tab */}
      {tab === 'articles' && (
        articles.length === 0 && !loading ? (
          <div className="bg-gray-900 rounded-lg border border-gray-700 p-8 text-center text-gray-500">
            {healthOk === false ? 'Worker offline' : 'No articles yet — click "Fetch All Feeds" to ingest.'}
          </div>
        ) : (
          <div className="bg-gray-900 rounded-lg border border-gray-700 overflow-hidden">
            <table className="w-full text-sm" aria-label="Intelligence articles" aria-busy={loading}>
              <thead>
                <tr className="border-b border-gray-700">
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Title</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Category</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Score</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Published</th>
                </tr>
              </thead>
              <tbody>
                {articles.map(art => (
                  <tr key={art.id} className="border-b border-gray-800 hover:bg-gray-800/50">
                    <td className="px-4 py-3 text-gray-200 max-w-sm">
                      {art.url ? (
                        <a
                          href={art.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="hover:text-indigo-300 transition-colors flex items-start gap-1 group"
                        >
                          <span className="line-clamp-2">{art.title}</span>
                          <ExternalLink size={11} className="shrink-0 mt-0.5 opacity-0 group-hover:opacity-100 transition-opacity" aria-hidden="true" />
                        </a>
                      ) : (
                        <span className="line-clamp-2">{art.title}</span>
                      )}
                      {art.summary && (
                        <p className="text-xs text-gray-500 mt-0.5 line-clamp-1">{art.summary}</p>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-xs border rounded-full px-2 py-0.5 ${CATEGORY_COLORS[art.category] ?? 'bg-gray-800 text-gray-400 border-gray-600'}`}>
                        {art.category}
                      </span>
                    </td>
                    <td className={`px-4 py-3 font-mono text-xs tabular-nums ${scoreColor(art.trend_score)}`}>
                      {art.trend_score.toFixed(1)}
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{fmtDate(art.published_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* Feeds tab */}
      {tab === 'feeds' && (
        feeds.length === 0 ? (
          <div className="bg-gray-900 rounded-lg border border-gray-700 p-8 text-center text-gray-500">
            No feeds configured.
          </div>
        ) : (
          <div className="bg-gray-900 rounded-lg border border-gray-700 overflow-hidden">
            <table className="w-full text-sm" aria-label="RSS feeds">
              <thead>
                <tr className="border-b border-gray-700">
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Feed</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Category</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Articles</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Last Fetched</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {feeds.map(feed => (
                  <tr key={feed.id} className="border-b border-gray-800 hover:bg-gray-800/50">
                    <td className="px-4 py-3">
                      <div className="text-gray-200 font-medium">{feed.name}</div>
                      <div className="text-gray-600 text-xs font-mono truncate max-w-xs">{feed.url}</div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-xs border rounded-full px-2 py-0.5 ${CATEGORY_COLORS[feed.category] ?? 'bg-gray-800 text-gray-400 border-gray-600'}`}>
                        {feed.category}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-400 tabular-nums text-sm">{feed.article_count}</td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{fmtDate(feed.last_fetched)}</td>
                    <td className="px-4 py-3">
                      <span className={`text-xs ${feed.active ? 'text-green-400' : 'text-gray-500'}`}>
                        {feed.active ? '● active' : '○ inactive'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  )
}
