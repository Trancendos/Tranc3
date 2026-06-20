/**
 * TheLabPage — Code Creation Platform (The Lab · Port 8055)
 * Lead AI: The Dr. & Slime
 *
 * Displays code snippets stored in the-lab worker, supports inline
 * code execution (python3 / node / bash) and snippet creation.
 */
import React, { useEffect, useState, useCallback } from 'react'
import { FlaskConical, RefreshCw, Play, Plus, Search, X, CheckCircle, XCircle, Clock } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const API = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'
const LAB_API = API.replace(/:\d+$/, ':8055')

const LANG_COLORS: Record<string, string> = {
  python3: 'bg-blue-900/40 text-blue-300 border-blue-700',
  python:  'bg-blue-900/40 text-blue-300 border-blue-700',
  node:    'bg-green-900/40 text-green-300 border-green-700',
  bash:    'bg-yellow-900/40 text-yellow-300 border-yellow-700',
}

interface Snippet {
  id: number
  title: string
  language: string
  code: string
  description: string | null
  tags: string
  runs: number
  created_at: number
}

interface ExecResult {
  stdout: string
  stderr: string
  exit_code: number
  duration_ms: number
}

interface NewSnippet {
  title: string
  language: string
  code: string
  description: string
}

export default function TheLabPage() {
  const [snippets, setSnippets] = useState<Snippet[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [query, setQuery] = useState('')
  const [langFilter, setLangFilter] = useState('')
  const [execResults, setExecResults] = useState<Record<number, ExecResult | null>>({})
  const [running, setRunning] = useState<Record<number, boolean>>({})
  const [healthOk, setHealthOk] = useState<boolean | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState<NewSnippet>({ title: '', language: 'python3', code: '', description: '' })
  const [creating, setCreating] = useState(false)
  const { trackPageView } = useAnalytics()

  useEffect(() => { trackPageView('/the-lab') }, [trackPageView])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ limit: '50', offset: '0' })
      if (query) params.set('q', query)
      if (langFilter) params.set('language', langFilter)
      const resp = await fetch(`/lab/snippets?${params}`, { headers: { 'X-Internal-Secret': 'dev-secret' } })
      if (resp.ok) {
        const body = await resp.json()
        setSnippets(body.snippets ?? [])
        setTotal(body.total ?? 0)
        setHealthOk(true)
      } else {
        setHealthOk(false)
      }
    } catch {
      setHealthOk(false)
    }
    setLoading(false)
  }, [query, langFilter])

  useEffect(() => { load() }, [load])

  const runSnippet = useCallback(async (id: number) => {
    setRunning(r => ({ ...r, [id]: true }))
    setExecResults(r => ({ ...r, [id]: null }))
    try {
      const resp = await fetch(`/lab/snippets/${id}/run`, {
        method: 'POST',
        headers: { 'X-Internal-Secret': 'dev-secret' },
      })
      if (resp.ok) {
        const body = await resp.json()
        setExecResults(r => ({ ...r, [id]: body }))
      }
    } catch { /* swallow */ }
    setRunning(r => ({ ...r, [id]: false }))
  }, [])

  const createSnippet = useCallback(async () => {
    if (!form.title || !form.code) return
    setCreating(true)
    try {
      const resp = await fetch('/lab/snippets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Internal-Secret': 'dev-secret' },
        body: JSON.stringify(form),
      })
      if (resp.ok) {
        setShowCreate(false)
        setForm({ title: '', language: 'python3', code: '', description: '' })
        load()
      }
    } catch { /* swallow */ }
    setCreating(false)
  }, [form, load])

  const parseTags = (raw: string): string[] => {
    try { return JSON.parse(raw) } catch { return [] }
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <FlaskConical size={22} aria-hidden="true" className="text-purple-400" />
            The Lab
          </h1>
          <p className="text-gray-400 text-sm mt-1">
            Code creation platform · Lead AI: The Dr. &amp; Slime · Port 8055 · {total} snippets
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 px-3 py-2 bg-purple-600 hover:bg-purple-500 rounded-lg text-sm text-white transition-colors"
          >
            <Plus size={14} aria-hidden="true" /> New Snippet
          </button>
          <button
            onClick={load}
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
          The Lab worker (port 8055) is unreachable. Start with{' '}
          <code className="font-mono bg-gray-800 px-1 rounded">make dev-api</code>.
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-3 mb-5 flex-wrap">
        <div className="relative flex-1 min-w-48">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" aria-hidden="true" />
          <input
            type="search"
            placeholder="Search snippets…"
            value={query}
            onChange={e => setQuery(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 bg-gray-900 border border-gray-700 rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        {['', 'python3', 'node', 'bash'].map(lang => (
          <button
            key={lang}
            onClick={() => setLangFilter(lang)}
            aria-pressed={langFilter === lang}
            className={`px-3 py-1.5 rounded-md text-xs font-medium border transition-colors ${
              langFilter === lang
                ? 'bg-indigo-600 text-white border-indigo-500'
                : 'bg-gray-900 text-gray-400 border-gray-700 hover:border-gray-500'
            }`}
          >
            {lang || 'All'}
          </button>
        ))}
      </div>

      {/* Snippet list */}
      {snippets.length === 0 && !loading ? (
        <div className="bg-gray-900 rounded-lg border border-gray-700 p-8 text-center text-gray-500">
          {healthOk === false ? 'Worker offline' : 'No snippets found. Create your first one!'}
        </div>
      ) : (
        <div className="space-y-4">
          {snippets.map(snip => {
            const tags = parseTags(snip.tags)
            const res = execResults[snip.id]
            return (
              <div key={snip.id} className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden">
                <div className="px-4 py-3 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className={`text-xs border rounded-full px-2 py-0.5 ${LANG_COLORS[snip.language] ?? 'bg-gray-800 text-gray-400 border-gray-600'}`}>
                      {snip.language}
                    </span>
                    <span className="text-gray-200 font-medium text-sm">{snip.title}</span>
                    {tags.map(t => (
                      <span key={t} className="text-xs bg-gray-800 text-gray-400 rounded px-1.5 py-0.5">{t}</span>
                    ))}
                  </div>
                  <div className="flex items-center gap-3 text-xs text-gray-500">
                    <span>{snip.runs} run{snip.runs !== 1 ? 's' : ''}</span>
                    <button
                      onClick={() => runSnippet(snip.id)}
                      disabled={running[snip.id]}
                      aria-label={`Run ${snip.title}`}
                      className="flex items-center gap-1 px-2 py-1 bg-green-900/40 hover:bg-green-800/40 text-green-400 border border-green-700 rounded transition-colors disabled:opacity-50"
                    >
                      {running[snip.id] ? <Clock size={12} className="animate-spin" /> : <Play size={12} />}
                      {running[snip.id] ? 'Running…' : 'Run'}
                    </button>
                  </div>
                </div>

                <pre className="text-xs text-gray-300 bg-gray-950 px-4 py-3 overflow-x-auto max-h-40 border-t border-gray-800">
                  <code>{snip.code}</code>
                </pre>

                {res && (
                  <div className="border-t border-gray-800 px-4 py-3 bg-gray-950/50">
                    <div className="flex items-center gap-2 mb-1.5 text-xs">
                      {res.exit_code === 0
                        ? <CheckCircle size={12} className="text-green-400" />
                        : <XCircle    size={12} className="text-red-400" />}
                      <span className={res.exit_code === 0 ? 'text-green-400' : 'text-red-400'}>
                        exit {res.exit_code}
                      </span>
                      <span className="text-gray-500">{res.duration_ms}ms</span>
                    </div>
                    {res.stdout && (
                      <pre className="text-xs text-gray-300 max-h-32 overflow-auto whitespace-pre-wrap">{res.stdout}</pre>
                    )}
                    {res.stderr && (
                      <pre className="text-xs text-red-400 max-h-24 overflow-auto whitespace-pre-wrap">{res.stderr}</pre>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Create modal */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-lg">
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-700">
              <h2 className="text-white font-semibold">New Snippet</h2>
              <button onClick={() => setShowCreate(false)} className="text-gray-400 hover:text-white">
                <X size={18} />
              </button>
            </div>
            <div className="p-5 space-y-3">
              <input
                type="text"
                placeholder="Title"
                value={form.title}
                onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
              <select
                value={form.language}
                onChange={e => setForm(f => ({ ...f, language: e.target.value }))}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="python3">Python 3</option>
                <option value="node">Node.js</option>
                <option value="bash">Bash</option>
              </select>
              <textarea
                placeholder="Description (optional)"
                value={form.description}
                onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                rows={2}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
              />
              <textarea
                placeholder="Code…"
                value={form.code}
                onChange={e => setForm(f => ({ ...f, code: e.target.value }))}
                rows={8}
                className="w-full px-3 py-2 bg-gray-950 border border-gray-600 rounded-lg text-sm text-green-300 font-mono placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
              />
            </div>
            <div className="flex justify-end gap-2 px-5 pb-4">
              <button
                onClick={() => setShowCreate(false)}
                className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={createSnippet}
                disabled={creating || !form.title || !form.code}
                className="px-4 py-2 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-sm rounded-lg transition-colors"
              >
                {creating ? 'Creating…' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
