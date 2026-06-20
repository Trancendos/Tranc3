import React, { useCallback, useEffect, useState } from 'react'
import { Database, RefreshCw, Trash2 } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const CACHE_API = '/cache-svc'
const INTERNAL = { 'X-Internal-Secret': 'dev-secret' }
const JSON_INTERNAL = { ...INTERNAL, 'Content-Type': 'application/json' }

interface CacheKey {
  key: string
}

interface CacheStats {
  total_keys: number
  no_expiry: number
  with_expiry: number
  expiring_in_60s: number
}

export default function CachePage() {
  const { trackPageView } = useAnalytics()
  const [keys, setKeys] = useState<string[]>([])
  const [stats, setStats] = useState<CacheStats | null>(null)
  const [activeKeys, setActiveKeys] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pattern, setPattern] = useState('')
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const [keyValue, setKeyValue] = useState<string | null>(null)
  const [keyTtl, setKeyTtl] = useState<number | null>(null)
  const [flushMsg, setFlushMsg] = useState<string | null>(null)

  useEffect(() => { trackPageView('/cache') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [hRes, sRes, kRes] = await Promise.all([
        fetch(`${CACHE_API}/health`),
        fetch(`${CACHE_API}/stats`, { headers: INTERNAL }),
        fetch(`${CACHE_API}/cache${pattern ? `?pattern=${encodeURIComponent(pattern)}` : ''}`, { headers: INTERNAL }),
      ])
      if (!hRes.ok) throw new Error('Service unavailable')
      const [h, s, k] = await Promise.all([hRes.json(), sRes.ok ? sRes.json() : null, kRes.ok ? kRes.json() : null])
      setActiveKeys(h.keys_active ?? 0)
      if (s) setStats(s)
      if (k) setKeys(k.keys ?? [])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [pattern])

  useEffect(() => { loadData() }, [loadData])

  const loadKey = async (key: string) => {
    setSelectedKey(key)
    setKeyValue(null)
    setKeyTtl(null)
    try {
      const r = await fetch(`${CACHE_API}/cache/${encodeURIComponent(key)}`, { headers: INTERNAL })
      if (r.ok) {
        const data = await r.json()
        setKeyValue(typeof data.value === 'object' ? JSON.stringify(data.value, null, 2) : String(data.value))
        setKeyTtl(data.ttl_remaining ?? null)
      }
    } catch { /* ignore */ }
  }

  const deleteKey = async (key: string) => {
    try {
      await fetch(`${CACHE_API}/cache/${encodeURIComponent(key)}`, { method: 'DELETE', headers: INTERNAL })
      setSelectedKey(null)
      setKeyValue(null)
      loadData()
    } catch { /* ignore */ }
  }

  const flushAll = async () => {
    setFlushMsg(null)
    try {
      const r = await fetch(`${CACHE_API}/cache`, { method: 'DELETE', headers: INTERNAL })
      if (r.ok) {
        const data = await r.json()
        setFlushMsg(`Flushed ${data.flushed} keys`)
        setSelectedKey(null)
        setKeyValue(null)
        loadData()
      }
    } catch {
      setFlushMsg('Flush failed')
    }
  }

  const fmt = (secs: number | null) => {
    if (secs === null) return '∞'
    if (secs < 60) return `${Math.round(secs)}s`
    if (secs < 3600) return `${Math.round(secs / 60)}m`
    return `${Math.round(secs / 3600)}h`
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Database size={22} className="text-slate-400" /> Cache Service
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Distributed in-memory key-value cache with TTL expiry</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={flushAll}
            className="flex items-center gap-1.5 rounded-lg border border-red-700/50 bg-red-900/20 px-3 py-1.5 text-xs text-red-300 hover:bg-red-900/40 transition-colors"
          >
            <Trash2 size={12} /> Flush All
          </button>
          <button
            onClick={loadData}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-300 hover:text-white disabled:opacity-50 transition-colors"
          >
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg bg-red-500/10 border border-red-500/30 px-4 py-3 text-sm text-red-300">
          {error} — is cache-service running on port 8023?
        </div>
      )}

      {flushMsg && (
        <div className="rounded-lg bg-amber-500/10 border border-amber-500/30 px-4 py-3 text-sm text-amber-300">
          {flushMsg}
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-4 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Active Keys</p>
          <p className="text-2xl font-bold text-white">{activeKeys}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">No Expiry</p>
          <p className="text-2xl font-bold text-slate-300">{stats?.no_expiry ?? '—'}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">With Expiry</p>
          <p className="text-2xl font-bold text-slate-300">{stats?.with_expiry ?? '—'}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Expiring Soon</p>
          <p className={`text-2xl font-bold ${(stats?.expiring_in_60s ?? 0) > 0 ? 'text-amber-400' : 'text-slate-300'}`}>
            {stats?.expiring_in_60s ?? '—'}
          </p>
        </div>
      </div>

      {/* Filter */}
      <div className="flex items-center gap-3">
        <input
          type="text"
          placeholder="Filter by prefix…"
          value={pattern}
          onChange={e => setPattern(e.target.value)}
          className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-slate-500 w-48"
        />
        <span className="text-xs text-slate-500">{keys.length} key{keys.length !== 1 ? 's' : ''}</span>
      </div>

      {/* Two-column: key list + value viewer */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-700/60">
            <h2 className="text-sm font-semibold text-white">Keys</h2>
          </div>
          {loading ? (
            <div className="p-4 text-center text-slate-500 text-xs">Loading…</div>
          ) : keys.length === 0 ? (
            <div className="p-4 text-center text-slate-500 text-xs">No keys in cache.</div>
          ) : (
            <ul className="py-1 max-h-96 overflow-y-auto">
              {keys.map(key => (
                <li key={key}>
                  <button
                    onClick={() => loadKey(key)}
                    className={`w-full flex items-center justify-between px-4 py-2.5 text-left transition-colors ${
                      selectedKey === key
                        ? 'bg-indigo-600/30 text-white border-r-2 border-indigo-500'
                        : 'text-slate-400 hover:bg-slate-800 hover:text-white'
                    }`}
                  >
                    <span className="font-mono text-xs truncate">{key}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-700/60 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-white">
              {selectedKey ? <span className="font-mono text-indigo-300">{selectedKey}</span> : 'Value Viewer'}
            </h2>
            {selectedKey && (
              <div className="flex items-center gap-2">
                {keyTtl !== null && (
                  <span className="text-xs text-slate-500">TTL: {fmt(keyTtl)}</span>
                )}
                <button
                  onClick={() => deleteKey(selectedKey)}
                  className="flex items-center gap-1 text-xs text-red-400 hover:text-red-300 transition-colors"
                >
                  <Trash2 size={11} /> Delete
                </button>
              </div>
            )}
          </div>
          <div className="p-4">
            {!selectedKey ? (
              <p className="text-slate-500 text-sm">Select a key to view its value.</p>
            ) : keyValue === null ? (
              <p className="text-slate-500 text-sm">Loading…</p>
            ) : (
              <pre className="text-xs text-slate-300 font-mono whitespace-pre-wrap break-all max-h-80 overflow-y-auto">
                {keyValue}
              </pre>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
