import React, { useCallback, useEffect, useState } from 'react'
import { Sparkles, RefreshCw, Plus, Puzzle } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const API = '/infinity-shards-svc'
const HEADERS = { 'X-Internal-Secret': 'dev-secret' }
const INTERNAL = { 'X-Internal-Secret': 'dev-secret', 'Content-Type': 'application/json' }

interface ShardSummary {
  total_shards: number
  active_shards: number
  installed_shards: number
  by_category: Record<string, number>
}

interface Shard {
  shard_id: string
  name: string
  category: string
  version: string
  is_active: boolean
  description: string
}

const CATEGORY_COLORS: Record<string, string> = {
  auth: 'text-indigo-400',
  analytics: 'text-blue-400',
  storage: 'text-emerald-400',
  ui: 'text-pink-400',
  ai: 'text-purple-400',
  integration: 'text-amber-400',
}

export default function InfinityShardsPage() {
  const { trackPageView } = useAnalytics()
  const [summary, setSummary] = useState<ShardSummary | null>(null)
  const [shards, setShards] = useState<Shard[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [shardName, setShardName] = useState('')
  const [category, setCategory] = useState('integration')
  const [creating, setCreating] = useState(false)
  const [createMsg, setCreateMsg] = useState<string | null>(null)

  useEffect(() => { trackPageView('/infinity-shards') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [healthRes, summaryRes, shardsRes] = await Promise.all([
        fetch(`${API}/health`),
        fetch(`${API}/shards/summary`, { headers: HEADERS }),
        fetch(`${API}/shards?limit=15`, { headers: HEADERS }),
      ])
      if (!healthRes.ok) throw new Error('Infinity-Shards unavailable')
      if (summaryRes.ok) setSummary(await summaryRes.json())
      if (shardsRes.ok) {
        const r = await shardsRes.json()
        setShards(r.shards ?? r)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const createShard = async () => {
    if (!shardName.trim()) return
    setCreating(true)
    setCreateMsg(null)
    try {
      const res = await fetch(`${API}/shards`, {
        method: 'POST',
        headers: INTERNAL,
        body: JSON.stringify({ name: shardName, category, version: '1.0.0', description: `${shardName} power-up shard` }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setCreateMsg('Shard registered!')
      setShardName('')
      loadData()
    } catch (e) {
      setCreateMsg(e instanceof Error ? e.message : 'Failed')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Sparkles size={22} className="text-purple-400" /> Infinity Shards
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Pluggable entity power-ups — modular capability extensions — Port 8045</p>
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
          {error} — is infinity-shards-service running on port 8045?
        </div>
      )}

      <div className="grid grid-cols-4 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Total Shards</p>
          <p className="text-2xl font-bold text-white">{summary?.total_shards ?? 0}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Active</p>
          <p className="text-2xl font-bold text-emerald-400">{summary?.active_shards ?? 0}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Installed</p>
          <p className="text-2xl font-bold text-purple-400">{summary?.installed_shards ?? 0}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Categories</p>
          <p className="text-2xl font-bold text-blue-400">{Object.keys(summary?.by_category ?? {}).length}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4 space-y-3">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2"><Plus size={14} className="text-purple-400" /> Register Shard</h2>
          <input
            value={shardName}
            onChange={e => setShardName(e.target.value)}
            placeholder="Shard name"
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-purple-500"
          />
          <select
            value={category}
            onChange={e => setCategory(e.target.value)}
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-purple-500"
          >
            {Object.keys(CATEGORY_COLORS).map(c => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
          <button
            onClick={createShard}
            disabled={creating || !shardName.trim()}
            className="w-full flex items-center justify-center gap-1.5 rounded-lg bg-purple-600 hover:bg-purple-700 disabled:opacity-50 px-4 py-1.5 text-xs text-white font-medium transition-colors"
          >
            <Plus size={11} /> {creating ? 'Registering…' : 'Register'}
          </button>
          {createMsg && <p className="text-xs text-emerald-400">{createMsg}</p>}
        </div>

        <div className="md:col-span-2 rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2 mb-3"><Puzzle size={14} className="text-purple-400" /> Shards</h2>
          {shards.length === 0 ? (
            <p className="text-xs text-slate-500">No shards registered yet</p>
          ) : (
            <div className="space-y-2">
              {shards.map(s => (
                <div key={s.shard_id} className="flex items-center gap-3 py-2 border-b border-slate-800 last:border-0">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-slate-200 truncate">{s.name}</p>
                    <p className="text-xs text-slate-500 truncate">{s.description || s.shard_id}</p>
                  </div>
                  <span className={`text-xs shrink-0 ${CATEGORY_COLORS[s.category] ?? 'text-slate-400'}`}>{s.category}</span>
                  <span className="text-xs text-slate-500 shrink-0">v{s.version}</span>
                  <span className={`text-xs shrink-0 ${s.is_active ? 'text-emerald-400' : 'text-red-400'}`}>
                    {s.is_active ? 'active' : 'inactive'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
