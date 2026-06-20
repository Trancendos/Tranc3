import React, { useCallback, useEffect, useState } from 'react'
import { Palette, RefreshCw, Plus, Clock } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const API = '/studio-svc'
const HEADERS = { 'X-Internal-Secret': 'dev-secret' }
const INTERNAL = { 'X-Internal-Secret': 'dev-secret', 'Content-Type': 'application/json' }

const PROJECT_TYPES = ['music', 'visual', 'video', 'game', 'mixed', 'branding', 'interactive']

interface Project {
  id: number
  title: string
  project_type: string
  status: string
  client: string | null
  priority: number
  created_at: number
}

interface Stats {
  total_projects: number
  total_hours_logged: number
  by_type: { project_type: string; c: number }[]
  by_status: { status: string; c: number }[]
}

const STATUS_COLORS: Record<string, string> = {
  draft: 'text-slate-400',
  in_progress: 'text-blue-400',
  review: 'text-amber-400',
  approved: 'text-emerald-400',
  published: 'text-green-400',
  archived: 'text-slate-600',
}

const TYPE_COLORS: Record<string, string> = {
  music: '#f59e0b', visual: '#ec4899', video: '#3b82f6', game: '#8b5cf6',
  mixed: '#14b8a6', branding: '#f97316', interactive: '#06b6d4',
}

export default function TheStudioPage() {
  const { trackPageView } = useAnalytics()
  const [projects, setProjects] = useState<Project[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Create project form
  const [title, setTitle] = useState('')
  const [projectType, setProjectType] = useState('visual')
  const [client, setClient] = useState('')
  const [creating, setCreating] = useState(false)
  const [createMsg, setCreateMsg] = useState<string | null>(null)

  useEffect(() => { trackPageView('/studio') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [projRes, statsRes] = await Promise.all([
        fetch(`${API}/projects?limit=20`, { headers: HEADERS }),
        fetch(`${API}/stats`, { headers: HEADERS }),
      ])
      if (!projRes.ok) throw new Error('The Studio unavailable')
      const p = await projRes.json()
      setProjects(p.projects ?? p)
      if (statsRes.ok) setStats(await statsRes.json())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const createProject = async () => {
    if (!title.trim()) return
    setCreating(true)
    setCreateMsg(null)
    try {
      const res = await fetch(`${API}/projects`, {
        method: 'POST',
        headers: INTERNAL,
        body: JSON.stringify({ title, project_type: projectType, client: client || undefined, created_by: 'demo' }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setCreateMsg('Project created!')
      setTitle('')
      setClient('')
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
            <Palette size={22} className="text-pink-400" /> The Studio
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Central creativity hub — Lead AI: Voxx</p>
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
          {error} — is the-studio running on port 8069?
        </div>
      )}

      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
            <p className="text-xs text-slate-400 mb-1">Total Projects</p>
            <p className="text-2xl font-bold text-white">{stats.total_projects}</p>
          </div>
          <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
            <p className="text-xs text-slate-400 mb-1">Hours Logged</p>
            <p className="text-2xl font-bold text-pink-400">{stats.total_hours_logged}</p>
          </div>
          {stats.by_status.filter(s => s.status === 'in_progress').map(s => (
            <div key={s.status} className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
              <p className="text-xs text-slate-400 mb-1">In Progress</p>
              <p className="text-2xl font-bold text-blue-400">{s.c}</p>
            </div>
          ))}
          {stats.by_status.filter(s => s.status === 'published').map(s => (
            <div key={s.status} className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
              <p className="text-xs text-slate-400 mb-1">Published</p>
              <p className="text-2xl font-bold text-emerald-400">{s.c}</p>
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Create form */}
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4 space-y-3">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2"><Plus size={14} className="text-pink-400" /> New Project</h2>
          <input
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder="Project title"
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-pink-500"
          />
          <select
            value={projectType}
            onChange={e => setProjectType(e.target.value)}
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-pink-500"
          >
            {PROJECT_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
          <input
            value={client}
            onChange={e => setClient(e.target.value)}
            placeholder="Client (optional)"
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-pink-500"
          />
          <button
            onClick={createProject}
            disabled={creating || !title.trim()}
            className="w-full flex items-center justify-center gap-1.5 rounded-lg bg-pink-600 hover:bg-pink-700 disabled:opacity-50 px-4 py-1.5 text-xs text-white font-medium transition-colors"
          >
            <Plus size={11} /> {creating ? 'Creating…' : 'Create'}
          </button>
          {createMsg && <p className="text-xs text-emerald-400">{createMsg}</p>}
        </div>

        {/* Project list */}
        <div className="md:col-span-2 rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <h2 className="text-sm font-semibold text-white mb-3">Recent Projects</h2>
          {projects.length === 0 ? (
            <p className="text-xs text-slate-500">No projects yet</p>
          ) : (
            <div className="space-y-2">
              {projects.map(p => (
                <div key={p.id} className="flex items-center gap-3 py-2 border-b border-slate-800 last:border-0">
                  <span
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{ backgroundColor: TYPE_COLORS[p.project_type] ?? '#94a3b8' }}
                  />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-slate-200 truncate">{p.title}</p>
                    <p className="text-xs text-slate-500">{p.project_type}{p.client ? ` · ${p.client}` : ''}</p>
                  </div>
                  <span className={`text-xs shrink-0 ${STATUS_COLORS[p.status] ?? 'text-slate-400'}`}>{p.status}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {stats && stats.by_type.length > 0 && (
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2 mb-3">
            <Clock size={14} className="text-slate-400" /> Projects by Type
          </h2>
          <div className="flex flex-wrap gap-2">
            {stats.by_type.map(t => (
              <span key={t.project_type} className="text-xs px-2 py-1 rounded border border-slate-700 text-slate-300">
                <span style={{ color: TYPE_COLORS[t.project_type] ?? '#94a3b8' }}>●</span> {t.project_type} ({t.c})
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
