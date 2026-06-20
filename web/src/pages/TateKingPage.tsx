import React, { useCallback, useEffect, useState } from 'react'
import { Clapperboard, RefreshCw, Plus, VideoIcon } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const API = '/tateking-svc'
const HEADERS = { 'X-Internal-Secret': 'dev-secret' }
const INTERNAL = { 'X-Internal-Secret': 'dev-secret', 'Content-Type': 'application/json' }

interface Project {
  id: number
  title: string
  description: string | null
  created_by: string
  created_at: number
}

interface Clip {
  id: number
  title: string
  project_id: number | null
  format: string | null
  resolution: string | null
  duration_s: number | null
}

export default function TateKingPage() {
  const { trackPageView } = useAnalytics()
  const [projects, setProjects] = useState<Project[]>([])
  const [clips, setClips] = useState<Clip[]>([])
  const [totalProjects, setTotalProjects] = useState(0)
  const [totalClips, setTotalClips] = useState(0)
  const [ffmpegAvailable, setFfmpegAvailable] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [creating, setCreating] = useState(false)
  const [createMsg, setCreateMsg] = useState<string | null>(null)

  useEffect(() => { trackPageView('/tateking') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [healthRes, projectsRes, clipsRes] = await Promise.all([
        fetch(`${API}/health`),
        fetch(`${API}/projects?limit=10`, { headers: HEADERS }),
        fetch(`${API}/clips?limit=10`, { headers: HEADERS }),
      ])
      if (!healthRes.ok) throw new Error('TateKing unavailable')
      const h = await healthRes.json()
      setTotalProjects(h.projects ?? 0)
      setTotalClips(h.clips ?? 0)
      setFfmpegAvailable(h.ffmpeg_available ?? false)
      if (projectsRes.ok) {
        const p = await projectsRes.json()
        setProjects(p.projects ?? p)
      }
      if (clipsRes.ok) {
        const c = await clipsRes.json()
        setClips(c.clips ?? c)
      }
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
        body: JSON.stringify({ title, description: description || null, created_by: 'demo' }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setCreateMsg('Project created!')
      setTitle('')
      setDescription('')
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
            <Clapperboard size={22} className="text-blue-400" /> TateKing
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Video creation & editing platform — Lead AI: Benji Tate &amp; Sam King</p>
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
          {error} — is tateking running on port 8066?
        </div>
      )}

      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Projects</p>
          <p className="text-2xl font-bold text-white">{totalProjects}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Clips</p>
          <p className="text-2xl font-bold text-blue-400">{totalClips}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">FFmpeg</p>
          <p className={`text-2xl font-bold ${ffmpegAvailable ? 'text-emerald-400' : 'text-red-400'}`}>
            {ffmpegAvailable ? 'Ready' : 'N/A'}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4 space-y-3">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2"><Plus size={14} className="text-blue-400" /> New Project</h2>
          <input
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder="Project title"
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
          />
          <input
            value={description}
            onChange={e => setDescription(e.target.value)}
            placeholder="Description (optional)"
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
          />
          <button
            onClick={createProject}
            disabled={creating || !title.trim()}
            className="w-full flex items-center justify-center gap-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-50 px-4 py-1.5 text-xs text-white font-medium transition-colors"
          >
            <Plus size={11} /> {creating ? 'Creating…' : 'Create'}
          </button>
          {createMsg && <p className="text-xs text-emerald-400">{createMsg}</p>}
        </div>

        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2 mb-3"><Clapperboard size={14} className="text-blue-400" /> Projects</h2>
          {projects.length === 0 ? (
            <p className="text-xs text-slate-500">No projects yet</p>
          ) : (
            <div className="space-y-2">
              {projects.map(p => (
                <div key={p.id} className="py-2 border-b border-slate-800 last:border-0">
                  <p className="text-xs font-medium text-slate-200 truncate">{p.title}</p>
                  {p.description && <p className="text-xs text-slate-500 truncate">{p.description}</p>}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2 mb-3"><VideoIcon size={14} className="text-blue-400" /> Clips</h2>
          {clips.length === 0 ? (
            <p className="text-xs text-slate-500">No clips yet</p>
          ) : (
            <div className="space-y-2">
              {clips.map(c => (
                <div key={c.id} className="py-2 border-b border-slate-800 last:border-0">
                  <p className="text-xs font-medium text-slate-200 truncate">{c.title}</p>
                  <p className="text-xs text-slate-500">
                    {[c.format, c.resolution, c.duration_s != null ? `${c.duration_s}s` : null].filter(Boolean).join(' · ') || 'no metadata'}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
