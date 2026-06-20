import React, { useCallback, useEffect, useState } from 'react'
import { Users, RefreshCw, Plus, UserCheck } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const API = '/users-svc'
const HEADERS = { 'X-Internal-Secret': 'dev-secret' }
const INTERNAL = { 'X-Internal-Secret': 'dev-secret', 'Content-Type': 'application/json' }

interface UserStats {
  total_users: number
  active_users: number
  verified_users: number
  new_today: number
}

interface PlatformUser {
  user_id: string
  username: string
  email: string
  tier: string
  is_active: boolean
  created_at: string
}

const TIER_COLORS: Record<string, string> = {
  free: 'text-slate-400',
  pro: 'text-blue-400',
  business: 'text-purple-400',
  enterprise: 'text-amber-400',
}

export default function UsersServicePage() {
  const { trackPageView } = useAnalytics()
  const [stats, setStats] = useState<UserStats | null>(null)
  const [users, setUsers] = useState<PlatformUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [tier, setTier] = useState('free')
  const [creating, setCreating] = useState(false)
  const [createMsg, setCreateMsg] = useState<string | null>(null)

  useEffect(() => { trackPageView('/users-service') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [healthRes, statsRes, usersRes] = await Promise.all([
        fetch(`${API}/health`),
        fetch(`${API}/users/stats`, { headers: HEADERS }),
        fetch(`${API}/users?limit=15`, { headers: HEADERS }),
      ])
      if (!healthRes.ok) throw new Error('Users service unavailable')
      if (statsRes.ok) setStats(await statsRes.json())
      if (usersRes.ok) {
        const r = await usersRes.json()
        setUsers(r.users ?? r)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const createUser = async () => {
    if (!username.trim() || !email.trim()) return
    setCreating(true)
    setCreateMsg(null)
    try {
      const res = await fetch(`${API}/users`, {
        method: 'POST',
        headers: INTERNAL,
        body: JSON.stringify({ username, email, tier }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setCreateMsg('User created!')
      setUsername('')
      setEmail('')
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
            <Users size={22} className="text-blue-400" /> Users Service
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Platform user management — accounts & billing tiers — Port 8006</p>
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
          {error} — is users-service running on port 8006?
        </div>
      )}

      <div className="grid grid-cols-4 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Total Users</p>
          <p className="text-2xl font-bold text-white">{stats?.total_users ?? 0}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Active</p>
          <p className="text-2xl font-bold text-emerald-400">{stats?.active_users ?? 0}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Verified</p>
          <p className="text-2xl font-bold text-blue-400">{stats?.verified_users ?? 0}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">New Today</p>
          <p className="text-2xl font-bold text-purple-400">{stats?.new_today ?? 0}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4 space-y-3">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2"><Plus size={14} className="text-blue-400" /> Create User</h2>
          <input
            value={username}
            onChange={e => setUsername(e.target.value)}
            placeholder="Username"
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
          />
          <input
            value={email}
            onChange={e => setEmail(e.target.value)}
            placeholder="Email address"
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
          />
          <select
            value={tier}
            onChange={e => setTier(e.target.value)}
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-blue-500"
          >
            {Object.keys(TIER_COLORS).map(t => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <button
            onClick={createUser}
            disabled={creating || !username.trim() || !email.trim()}
            className="w-full flex items-center justify-center gap-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-50 px-4 py-1.5 text-xs text-white font-medium transition-colors"
          >
            <Plus size={11} /> {creating ? 'Creating…' : 'Create'}
          </button>
          {createMsg && <p className="text-xs text-emerald-400">{createMsg}</p>}
        </div>

        <div className="md:col-span-2 rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2 mb-3"><UserCheck size={14} className="text-blue-400" /> Users</h2>
          {users.length === 0 ? (
            <p className="text-xs text-slate-500">No users yet</p>
          ) : (
            <div className="space-y-2">
              {users.map(u => (
                <div key={u.user_id} className="flex items-center gap-3 py-2 border-b border-slate-800 last:border-0">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-slate-200 truncate">{u.username}</p>
                    <p className="text-xs text-slate-500 truncate">{u.email}</p>
                  </div>
                  <span className={`text-xs shrink-0 ${TIER_COLORS[u.tier] ?? 'text-slate-400'}`}>{u.tier}</span>
                  <span className={`text-xs shrink-0 ${u.is_active ? 'text-emerald-400' : 'text-red-400'}`}>
                    {u.is_active ? 'active' : 'inactive'}
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
