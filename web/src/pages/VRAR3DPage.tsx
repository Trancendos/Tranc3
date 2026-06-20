import React, { useCallback, useEffect, useState } from 'react'
import { Layers, RefreshCw, Plus, Eye } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const API = '/vrar3d-svc'
const HEADERS = { 'X-Internal-Secret': 'dev-secret' }
const INTERNAL = { 'X-Internal-Secret': 'dev-secret', 'Content-Type': 'application/json' }

const SCENE_TYPES = ['vr', 'ar', '3d', '360_video', 'interactive']

interface Experience {
  id: number
  title: string
  experience_type: string
  renderer: string | null
  public: boolean
  created_at: number
}

const TYPE_COLORS: Record<string, string> = {
  vr: '#6366f1', ar: '#10b981', '3d': '#f59e0b',
  '360_video': '#ec4899', interactive: '#06b6d4',
}

export default function VRAR3DPage() {
  const { trackPageView } = useAnalytics()
  const [experiences, setExperiences] = useState<Experience[]>([])
  const [totalExps, setTotalExps] = useState(0)
  const [totalSessions, setTotalSessions] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Create form
  const [title, setTitle] = useState('')
  const [expType, setExpType] = useState('3d')
  const [creating, setCreating] = useState(false)
  const [createMsg, setCreateMsg] = useState<string | null>(null)

  useEffect(() => { trackPageView('/vrar3d') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [healthRes, expsRes] = await Promise.all([
        fetch(`${API}/health`),
        fetch(`${API}/experiences?limit=15`, { headers: HEADERS }),
      ])
      if (!healthRes.ok) throw new Error('VRAR3D unavailable')
      const h = await healthRes.json()
      setTotalExps(h.experiences ?? 0)
      setTotalSessions(h.total_sessions ?? 0)
      if (expsRes.ok) {
        const e = await expsRes.json()
        setExperiences(e.experiences ?? e)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const createExperience = async () => {
    if (!title.trim()) return
    setCreating(true)
    setCreateMsg(null)
    try {
      const res = await fetch(`${API}/experiences`, {
        method: 'POST',
        headers: INTERNAL,
        body: JSON.stringify({ title, experience_type: expType, created_by: 'demo', public: true }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setCreateMsg('Experience created!')
      setTitle('')
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
            <Eye size={22} className="text-indigo-400" /> VRAR3D
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Standalone 3D / VR immersion — Lead AI: Entari</p>
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
          {error} — is vrar3d running on port 8068?
        </div>
      )}

      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Experiences</p>
          <p className="text-2xl font-bold text-white">{totalExps}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Sessions</p>
          <p className="text-2xl font-bold text-indigo-400">{totalSessions}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Scene Types</p>
          <p className="text-2xl font-bold text-cyan-400">{SCENE_TYPES.length}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Create */}
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4 space-y-3">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2"><Plus size={14} className="text-indigo-400" /> New Experience</h2>
          <input
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder="Experience title"
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
          <select
            value={expType}
            onChange={e => setExpType(e.target.value)}
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
          >
            {SCENE_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
          <button
            onClick={createExperience}
            disabled={creating || !title.trim()}
            className="w-full flex items-center justify-center gap-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 px-4 py-1.5 text-xs text-white font-medium transition-colors"
          >
            <Plus size={11} /> {creating ? 'Creating…' : 'Create'}
          </button>
          {createMsg && <p className="text-xs text-emerald-400">{createMsg}</p>}
        </div>

        {/* Experiences */}
        <div className="md:col-span-2 rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2 mb-3"><Layers size={14} className="text-indigo-400" /> Experiences</h2>
          {experiences.length === 0 ? (
            <p className="text-xs text-slate-500">No experiences yet</p>
          ) : (
            <div className="space-y-2">
              {experiences.map(e => (
                <div key={e.id} className="flex items-center gap-3 py-2 border-b border-slate-800 last:border-0">
                  <span
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{ backgroundColor: TYPE_COLORS[e.experience_type] ?? '#94a3b8' }}
                  />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-slate-200 truncate">{e.title}</p>
                    <p className="text-xs text-slate-500">{e.experience_type}{e.renderer ? ` · ${e.renderer}` : ''}</p>
                  </div>
                  <span className={`text-xs shrink-0 ${e.public ? 'text-emerald-400' : 'text-slate-500'}`}>
                    {e.public ? 'public' : 'private'}
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
