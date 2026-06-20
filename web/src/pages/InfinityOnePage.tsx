import React, { useCallback, useEffect, useState } from 'react'
import { Fingerprint, RefreshCw, Plus, Users } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const API = '/infinity-one-svc'
const HEADERS = { 'X-Internal-Secret': 'dev-secret' }
const INTERNAL = { 'X-Internal-Secret': 'dev-secret', 'Content-Type': 'application/json' }

interface IdentitySummary {
  total_identities: number
  active_identities: number
  by_role: Record<string, number>
  by_tier: Record<string, number>
}

interface Identity {
  user_id: string
  display_name: string
  role: string
  tier: number
  is_active: boolean
}

export default function InfinityOnePage() {
  const { trackPageView } = useAnalytics()
  const [summary, setSummary] = useState<IdentitySummary | null>(null)
  const [identities, setIdentities] = useState<Identity[]>([])
  const [healthScore, setHealthScore] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [userId, setUserId] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [role, setRole] = useState('user')
  const [creating, setCreating] = useState(false)
  const [createMsg, setCreateMsg] = useState<string | null>(null)

  useEffect(() => { trackPageView('/infinity-one') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [healthRes, summaryRes, idsRes] = await Promise.all([
        fetch(`${API}/health`),
        fetch(`${API}/one/summary`, { headers: HEADERS }),
        fetch(`${API}/one/identities?limit=15`, { headers: HEADERS }),
      ])
      if (!healthRes.ok) throw new Error('Infinity-One unavailable')
      const h = await healthRes.json()
      setHealthScore(h.health_score ?? null)
      if (summaryRes.ok) setSummary(await summaryRes.json())
      if (idsRes.ok) {
        const r = await idsRes.json()
        setIdentities(r.identities ?? r)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const createIdentity = async () => {
    if (!userId.trim() || !displayName.trim()) return
    setCreating(true)
    setCreateMsg(null)
    try {
      const res = await fetch(`${API}/one/identities`, {
        method: 'POST',
        headers: INTERNAL,
        body: JSON.stringify({ user_id: userId, display_name: displayName, role, email: `${userId}@demo.local` }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setCreateMsg('Identity created!')
      setUserId('')
      setDisplayName('')
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
            <Fingerprint size={22} className="text-indigo-400" /> Infinity One
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Single identity layer — one login, multi-app access — Port 8043</p>
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
          {error} — is infinity-one-service running on port 8043?
        </div>
      )}

      <div className="grid grid-cols-4 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Total Identities</p>
          <p className="text-2xl font-bold text-white">{summary?.total_identities ?? 0}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Active</p>
          <p className="text-2xl font-bold text-emerald-400">{summary?.active_identities ?? 0}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Roles</p>
          <p className="text-2xl font-bold text-indigo-400">{Object.keys(summary?.by_role ?? {}).length}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Health</p>
          <p className="text-2xl font-bold text-blue-400">
            {healthScore !== null ? (healthScore * 100).toFixed(0) + '%' : '—'}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4 space-y-3">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2"><Plus size={14} className="text-indigo-400" /> New Identity</h2>
          <input
            value={userId}
            onChange={e => setUserId(e.target.value)}
            placeholder="User ID (unique)"
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
          <input
            value={displayName}
            onChange={e => setDisplayName(e.target.value)}
            placeholder="Display name"
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
          <select
            value={role}
            onChange={e => setRole(e.target.value)}
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
          >
            {['user', 'admin', 'moderator', 'developer', 'ai_entity'].map(r => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
          <button
            onClick={createIdentity}
            disabled={creating || !userId.trim() || !displayName.trim()}
            className="w-full flex items-center justify-center gap-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 px-4 py-1.5 text-xs text-white font-medium transition-colors"
          >
            <Plus size={11} /> {creating ? 'Creating…' : 'Create'}
          </button>
          {createMsg && <p className="text-xs text-emerald-400">{createMsg}</p>}
        </div>

        <div className="md:col-span-2 rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2 mb-3"><Users size={14} className="text-indigo-400" /> Identities</h2>
          {identities.length === 0 ? (
            <p className="text-xs text-slate-500">No identities yet</p>
          ) : (
            <div className="space-y-2">
              {identities.map(id => (
                <div key={id.user_id} className="flex items-center gap-3 py-2 border-b border-slate-800 last:border-0">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-slate-200 truncate">{id.display_name}</p>
                    <p className="text-xs text-slate-500">{id.user_id} · tier {id.tier}</p>
                  </div>
                  <span className="text-xs text-slate-400 shrink-0">{id.role}</span>
                  <span className={`text-xs shrink-0 ${id.is_active ? 'text-emerald-400' : 'text-red-400'}`}>
                    {id.is_active ? 'active' : 'inactive'}
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
