import React, { useState, useRef, useId } from 'react'
import { Search, Loader, ExternalLink, AlertCircle } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const SEARCH_API = API.replace(':8000', ':8024')

interface SearchResult {
  id: string
  title: string
  excerpt: string
  url?: string
  score?: number
  source?: string
}

interface SearchResponse {
  results: SearchResult[]
  total: number
  query: string
  took_ms: number
  provider?: string
}

export default function SearchPage() {
  const [query, setQuery]     = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [meta, setMeta]       = useState<Omit<SearchResponse, 'results'> | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState<string | null>(null)
  const inputRef              = useRef<HTMLInputElement>(null)
  const errorId               = useId()
  const resultsStatusId       = useId()
  const { trackSearch, trackError } = useAnalytics()

  async function runSearch(e: React.FormEvent) {
    e.preventDefault()
    if (!query.trim()) return
    setLoading(true)
    setError(null)
    setResults([])
    setMeta(null)

    const t0 = performance.now()
    const endpoints = [
      `${SEARCH_API}/search?q=${encodeURIComponent(query)}`,
      `${API}/search?q=${encodeURIComponent(query)}`,
    ]

    for (const url of endpoints) {
      try {
        const r = await fetch(url, { signal: AbortSignal.timeout(8000) })
        if (r.ok) {
          const body: SearchResponse = await r.json()
          const total = body.total ?? body.results?.length ?? 0
          setResults(body.results ?? [])
          setMeta({
            total,
            query:    body.query ?? query,
            took_ms:  body.took_ms ?? Math.round(performance.now() - t0),
            provider: body.provider,
          })
          trackSearch(query, total, body.provider)
          setLoading(false)
          return
        }
      } catch { /* try next endpoint */ }
    }

    const errMsg = 'Search service unavailable. Make sure tranc3-search worker is running.'
    setError(errMsg)
    trackError('search_unavailable', query)
    setLoading(false)
  }

  const announcement = loading
    ? 'Searching…'
    : error
    ? `Error: ${error}`
    : meta
    ? `${meta.total} result${meta.total !== 1 ? 's' : ''} for "${meta.query}"${meta.took_ms != null ? `, ${meta.took_ms}ms` : ''}`
    : ''

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white flex items-center gap-2 mb-1">
          <Search size={22} className="text-indigo-400" aria-hidden="true" />
          Search
        </h1>
        <p className="text-gray-400 text-sm">
          Full-text + semantic search across the platform
        </p>
      </div>

      {/* Screen-reader results announcer */}
      <div
        id={resultsStatusId}
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
      >
        {announcement}
      </div>

      {/* Search form */}
      <form
        role="search"
        aria-label="Platform search"
        onSubmit={runSearch}
        className="flex gap-2 mb-6"
      >
        <div className="flex-1 relative">
          <Search
            size={16}
            aria-hidden="true"
            className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none"
          />
          <label htmlFor="search-input" className="sr-only">Search query</label>
          <input
            id="search-input"
            ref={inputRef}
            type="search"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search platform data…"
            aria-describedby={error ? errorId : undefined}
            autoComplete="off"
            spellCheck="false"
            className="w-full bg-gray-900 border border-gray-700 rounded-lg pl-9 pr-4 py-2.5 text-white text-sm placeholder-gray-500 focus:outline-none focus:border-indigo-500 focus-visible:ring-2 focus-visible:ring-indigo-500"
          />
        </div>
        <button
          type="submit"
          disabled={loading || !query.trim()}
          aria-busy={loading}
          className="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg text-sm text-white transition-colors flex items-center gap-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
        >
          {loading
            ? <Loader size={14} aria-hidden="true" className="animate-spin" />
            : <Search size={14} aria-hidden="true" />}
          {loading ? 'Searching…' : 'Search'}
        </button>
      </form>

      {/* Error */}
      {error && (
        <div
          id={errorId}
          role="alert"
          className="flex items-center gap-2 bg-red-900/30 border border-red-700 rounded-lg p-4 mb-4 text-red-400 text-sm"
        >
          <AlertCircle size={16} aria-hidden="true" />
          {error}
        </div>
      )}

      {/* Result count */}
      {meta && (
        <p className="text-gray-500 text-xs mb-4" aria-hidden="true">
          {meta.total} result{meta.total !== 1 ? 's' : ''} for &ldquo;{meta.query}&rdquo;
          {meta.took_ms != null ? ` · ${meta.took_ms}ms` : ''}
          {meta.provider ? ` · via ${meta.provider}` : ''}
        </p>
      )}

      {/* Results */}
      {results.length > 0 ? (
        <ol
          aria-label={`Search results for "${meta?.query ?? query}"`}
          className="space-y-3 list-none"
        >
          {results.map(r => (
            <li key={r.id}>
              <article
                aria-label={r.title}
                className="bg-gray-900 border border-gray-700 rounded-lg p-4 hover:border-indigo-600 transition-colors"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h2 className="text-white text-sm font-medium mb-1">{r.title}</h2>
                    {r.excerpt && (
                      <p className="text-gray-400 text-xs leading-relaxed">{r.excerpt}</p>
                    )}
                    {r.source && (
                      <span className="text-indigo-400 text-xs mt-1 inline-block">{r.source}</span>
                    )}
                  </div>
                  <div className="flex-shrink-0 flex flex-col items-end gap-1">
                    {r.score != null && (
                      <span
                        aria-label={`Relevance score ${Math.round(r.score * 100)}%`}
                        className="text-gray-600 text-xs tabular-nums"
                      >
                        {(r.score * 100).toFixed(0)}%
                      </span>
                    )}
                    {r.url && (
                      <a
                        href={r.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        aria-label={`Open "${r.title}" in a new tab`}
                        className="text-gray-500 hover:text-indigo-400 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 rounded"
                      >
                        <ExternalLink size={14} aria-hidden="true" />
                      </a>
                    )}
                  </div>
                </div>
              </article>
            </li>
          ))}
        </ol>
      ) : meta && results.length === 0 ? (
        <div className="text-center py-12 text-gray-500" role="status" aria-live="polite">
          <Search size={32} aria-hidden="true" className="mx-auto mb-2 opacity-30" />
          <p>No results for &ldquo;{meta.query}&rdquo;</p>
        </div>
      ) : !loading && !error ? (
        <div className="text-center py-12 text-gray-600">
          <Search size={32} aria-hidden="true" className="mx-auto mb-2 opacity-20" />
          <p className="text-sm">Enter a query above to search</p>
        </div>
      ) : null}
    </div>
  )
}
