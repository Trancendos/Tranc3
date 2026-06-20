import React, { useCallback, useEffect, useState } from 'react'
import { Settings2, RefreshCw, ChevronRight } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const CONFIG_API = '/config-svc'
const INTERNAL = { 'X-Internal-Secret': 'dev-secret' }

interface Namespace {
  name: string
  description: string
  created_at: number
}

interface ConfigKey {
  id: number
  namespace: string
  key: string
  value: string
  value_type: string
  description: string
  version: number
  updated_at: number
  coerced_value: unknown
}

export default function ConfigPage() {
  const { trackPageView } = useAnalytics()
  const [namespaces, setNamespaces] = useState<Namespace[]>([])
  const [selectedNs, setSelectedNs] = useState<string | null>(null)
  const [keys, setKeys] = useState<ConfigKey[]>([])
  const [nsCount, setNsCount] = useState(0)
  const [keyCount, setKeyCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [keysLoading, setKeysLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [prefix, setPrefix] = useState('')

  useEffect(() => { trackPageView('/config') }, [trackPageView])

  const loadNamespaces = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [hRes, nsRes] = await Promise.all([
        fetch(`${CONFIG_API}/health`),
        fetch(`${CONFIG_API}/namespaces`, { headers: INTERNAL }),
      ])
      if (!hRes.ok || !nsRes.ok) throw new Error('Service unavailable')
      const [h, ns] = await Promise.all([hRes.json(), nsRes.json()])
      setNsCount(h.namespaces ?? 0)
      setKeyCount(h.config_keys ?? 0)
      setNamespaces(ns.namespaces ?? [])
      if (!selectedNs && ns.namespaces?.length > 0) {
        setSelectedNs(ns.namespaces[0].name)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [selectedNs])

  useEffect(() => { loadNamespaces() }, [loadNamespaces])

  const loadKeys = useCallback(async () => {
    if (!selectedNs) return
    setKeysLoading(true)
    try {
      const params = new URLSearchParams()
      if (prefix) params.set('prefix', prefix)
      const r = await fetch(`${CONFIG_API}/config/${selectedNs}?${params}`, { headers: INTERNAL })
      if (r.ok) {
        const data = await r.json()
        setKeys(data.keys ?? [])
      }
    } catch { /* ignore */ } finally {
      setKeysLoading(false)
    }
  }, [selectedNs, prefix])

  useEffect(() => { loadKeys() }, [loadKeys])

  const fmt = (ts: number) => {
    try { return new Date(ts * 1000).toLocaleString() } catch { return String(ts) }
  }

  const displayVal = (k: ConfigKey) => {
    if (k.value_type === 'json') {
      try { return JSON.stringify(JSON.parse(k.value), null, 0) } catch { return k.value }
    }
    return k.value
  }

  const TYPE_COLORS: Record<string, string> = {
    string: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
    int: 'bg-green-500/20 text-green-300 border-green-500/30',
    float: 'bg-teal-500/20 text-teal-300 border-teal-500/30',
    bool: 'bg-purple-500/20 text-purple-300 border-purple-500/30',
    json: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Settings2 size={22} className="text-slate-400" /> Central Config
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Namespaced key-value configuration store with version history</p>
        </div>
        <button
          onClick={loadNamespaces}
          disabled={loading}
          className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-300 hover:text-white disabled:opacity-50 transition-colors"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-lg bg-red-500/10 border border-red-500/30 px-4 py-3 text-sm text-red-300">
          {error} — is config-service running on port 8024?
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Namespaces</p>
          <p className="text-2xl font-bold text-white">{nsCount}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Config Keys</p>
          <p className="text-2xl font-bold text-white">{keyCount}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Selected Namespace</p>
          <p className="text-2xl font-bold text-white">{selectedNs ?? '—'}</p>
        </div>
      </div>

      {/* Two-column layout */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* Namespace list */}
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-700/60">
            <h2 className="text-sm font-semibold text-white">Namespaces</h2>
          </div>
          {loading ? (
            <div className="p-4 text-center text-slate-500 text-xs">Loading…</div>
          ) : namespaces.length === 0 ? (
            <div className="p-4 text-center text-slate-500 text-xs">No namespaces.</div>
          ) : (
            <ul className="py-1">
              {namespaces.map(ns => (
                <li key={ns.name}>
                  <button
                    onClick={() => setSelectedNs(ns.name)}
                    className={`w-full flex items-center justify-between px-4 py-2.5 text-sm transition-colors ${
                      selectedNs === ns.name
                        ? 'bg-indigo-600/30 text-white border-r-2 border-indigo-500'
                        : 'text-slate-400 hover:bg-slate-800 hover:text-white'
                    }`}
                  >
                    <span className="truncate">{ns.name}</span>
                    <ChevronRight size={12} className="flex-shrink-0 opacity-50" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Config keys */}
        <div className="lg:col-span-3 rounded-xl border border-slate-700/60 bg-slate-900/70 overflow-hidden">
          <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-700/60">
            <h2 className="text-sm font-semibold text-white">
              {selectedNs ? `${selectedNs} /` : 'Config Keys'}
            </h2>
            <input
              type="text"
              placeholder="Filter by prefix…"
              value={prefix}
              onChange={e => setPrefix(e.target.value)}
              className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-slate-500 w-36"
            />
            <span className="text-xs text-slate-500 ml-auto">{keys.length} key{keys.length !== 1 ? 's' : ''}</span>
          </div>
          {keysLoading ? (
            <div className="p-8 text-center text-slate-500 text-sm">Loading keys…</div>
          ) : !selectedNs ? (
            <div className="p-8 text-center text-slate-500 text-sm">Select a namespace.</div>
          ) : keys.length === 0 ? (
            <div className="p-8 text-center text-slate-500 text-sm">No keys in this namespace.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700/60 text-xs text-slate-500 uppercase tracking-wider">
                    <th className="text-left px-4 py-2">Key</th>
                    <th className="text-left px-4 py-2">Value</th>
                    <th className="text-left px-4 py-2">Type</th>
                    <th className="text-right px-4 py-2">v</th>
                    <th className="text-right px-4 py-2">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {keys.map(k => (
                    <tr key={k.id} className="border-b border-slate-800 hover:bg-slate-800/30 transition-colors">
                      <td className="px-4 py-2.5 font-mono text-xs text-slate-200">{k.key}</td>
                      <td className="px-4 py-2.5 font-mono text-xs text-slate-400 max-w-xs truncate" title={String(k.value)}>
                        {displayVal(k)}
                      </td>
                      <td className="px-4 py-2.5">
                        <span className={`text-xs px-1.5 py-0.5 rounded border ${TYPE_COLORS[k.value_type] ?? 'bg-slate-700/40 text-slate-400 border-slate-600/30'}`}>
                          {k.value_type}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-right text-slate-500 text-xs">v{k.version}</td>
                      <td className="px-4 py-2.5 text-right text-slate-500 whitespace-nowrap text-xs">{fmt(k.updated_at)}</td>
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
