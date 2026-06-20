import React, { useCallback, useEffect, useState } from 'react'
import { ShieldCheck, RefreshCw, Plus, Users } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const API = '/infinity-admin-svc'
const HEADERS = { 'X-Internal-Secret': 'dev-secret' }
const INTERNAL = { 'X-Internal-Secret': 'dev-secret', 'Content-Type': 'application/json' }

interface AdminSummary {
  total_admins: number
  active_sessions: number
  pending_actions: number
  audit_events_today: number
}

interface AdminUser {
  admin_id: string
  username: string
  role: string
  last_login: string | null
  is_active: boolean
}

export default function InfinityAdminPage() {
  const { trackPageView } = useAnalytics()
  const [summary, setSummary] = useState<AdminSummary | null>(null)
  const [admins, setAdmins] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [username, setUsername] = useState('')
  const [adminRole, setAdminRole] = useState('admin')
  const [creating, setCreating] = useState(false)
  const [createMsg, setCreateMsg] = useState<string | null>(null)

  useEffect(() => { trackPageView('/infinity-admin') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [healthRes, summaryRes, adminsRes] = await Promise.all([
        fetch(`${API}/health`),
        fetch(`${API}/admin/summary`, { headers: HEADERS }),
        fetch(`${API}/admin/users?limit=15`, { headers: HEADERS }),
      ])
      if (!healthRes.ok) throw new Error('Infinity-Admin unavailable')
      if (summaryRes.ok) setSummary(await summaryRes.json())
      if (adminsRes.ok) {
        const r = await adminsRes.json()
        setAdmins(r.users ?? r.admins ?? r)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const createAdmin = async () => {
    if (!username.trim()) return
    setCreating(true)
    setCreateMsg(null)
    try {
      const res = await fetch(`${API}/admin/users`, {
        method: 'POST',
        headers: INTERNAL,
        body: JSON.stringify({ username, role: adminRole, email: `${username}@admin.local` }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setCreateMsg('Admin user created!')
      setUsername('')
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
            <ShieldCheck size={22} className="text-indigo-400" /> Infinity Admin
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Admin OS — platform administration & oversight — Port 8044</p>
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
          {error} — is infinity-admin-service running on port 8044?
        </div>
      )}

      <div className="grid grid-cols-4 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Total Admins</p>
          <p className="text-2xl font-bold text-white">{summary?.total_admins ?? 0}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Active Sessions</p>
          <p className="text-2xl font-bold text-emerald-400">{summary?.active_sessions ?? 0}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Pending Actions</p>
          <p className="text-2xl font-bold text-amber-400">{summary?.pending_actions ?? 0}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Audit Events Today</p>
          <p className="text-2xl font-bold text-blue-400">{summary?.audit_events_today ?? 0}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4 space-y-3">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2"><Plus size={14} className="text-indigo-400" /> New Admin User</h2>
          <input
            value={username}
            onChange={e => setUsername(e.target.value)}
            placeholder="Username"
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
          <select
            value={adminRole}
            onChange={e => setAdminRole(e.target.value)}
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
          >
            {['admin', 'super_admin', 'moderator', 'support', 'readonly'].map(r => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
          <button
            onClick={createAdmin}
            disabled={creating || !username.trim()}
            className="w-full flex items-center justify-center gap-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 px-4 py-1.5 text-xs text-white font-medium transition-colors"
          >
            <Plus size={11} /> {creating ? 'Creating…' : 'Create'}
          </button>
          {createMsg && <p className="text-xs text-emerald-400">{createMsg}</p>}
        </div>

        <div className="md:col-span-2 rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2 mb-3"><Users size={14} className="text-indigo-400" /> Admin Users</h2>
          {admins.length === 0 ? (
            <p className="text-xs text-slate-500">No admin users yet</p>
          ) : (
            <div className="space-y-2">
              {admins.map(a => (
                <div key={a.admin_id} className="flex items-center gap-3 py-2 border-b border-slate-800 last:border-0">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-slate-200 truncate">{a.username}</p>
                    <p className="text-xs text-slate-500">{a.admin_id}{a.last_login ? ` · ${new Date(a.last_login).toLocaleDateString()}` : ''}</p>
                  </div>
                  <span className="text-xs text-slate-400 shrink-0">{a.role}</span>
                  <span className={`text-xs shrink-0 ${a.is_active ? 'text-emerald-400' : 'text-red-400'}`}>
                    {a.is_active ? 'active' : 'inactive'}
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
