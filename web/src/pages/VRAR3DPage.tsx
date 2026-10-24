import React, { useCallback, useEffect, useState } from 'react'
import { Eye, Layers, Plus, RefreshCw } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'
import { useAuthStore } from '../store/authStore'

// The browser only uses a user-scoped platform JWT. Internal worker secrets
// are injected by the backend gateway and are never available to JavaScript.
const API = `${import.meta.env.VITE_API_URL || ''}/api/spatial`
const SCENE_TYPES = ['3d', 'vr', 'ar', 'xr', 'panorama', 'spatial'] as const
type SceneType = typeof SCENE_TYPES[number]

interface SpatialScene {
  scene_id: string
  name: string
  scene_type: SceneType
  objects?: unknown[]
}

const TYPE_COLORS: Record<SceneType, string> = {
  '3d': '#f59e0b', vr: '#6366f1', ar: '#10b981', xr: '#14b8a6',
  panorama: '#ec4899', spatial: '#06b6d4',
}

export default function VRAR3DPage() {
  const { trackPageView } = useAnalytics()
  const token = useAuthStore(state => state.token)
  const expiresAt = useAuthStore(state => state.expiresAt)
  const [scenes, setScenes] = useState<SpatialScene[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [sceneType, setSceneType] = useState<SceneType>('3d')
  const [creating, setCreating] = useState(false)
  const [createMessage, setCreateMessage] = useState<string | null>(null)

  useEffect(() => { trackPageView('/vrar3d') }, [trackPageView])
  const authorized = Boolean(token && expiresAt && Date.now() < expiresAt)
  const requestHeaders = useCallback((json = false): Record<string, string> => ({
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(json ? { 'Content-Type': 'application/json' } : {}),
  }), [token])

  const loadData = useCallback(async () => {
    if (!authorized) {
      setLoading(false)
      setError('Your session has expired. Sign in again to view your scenes.')
      setScenes([])
      return
    }
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API}/scenes?limit=200`, { headers: requestHeaders() })
      if (res.status === 401 || res.status === 403) {
        throw new Error('Your session is not authorised for VRAR3D.')
      }
      if (!res.ok) throw new Error(`VRAR3D gateway unavailable (HTTP ${res.status}).`)
      const data: unknown = await res.json()
      if (!Array.isArray(data)) throw new Error('Unexpected scene list returned by the platform.')
      setScenes(data as SpatialScene[])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load VRAR3D scenes')
      setScenes([])
    } finally {
      setLoading(false)
    }
  }, [authorized, requestHeaders])

  useEffect(() => { void loadData() }, [loadData])

  const createScene = async () => {
    if (!name.trim() || !authorized) return
    setCreating(true)
    setCreateMessage(null)
    try {
      const res = await fetch(`${API}/scenes`, {
        method: 'POST',
        headers: requestHeaders(true),
        body: JSON.stringify({ name: name.trim(), scene_type: sceneType }),
      })
      if (!res.ok) throw new Error(`Could not create scene (HTTP ${res.status}).`)
      setCreateMessage('Scene record created. Preview is available after validated geometry is attached.')
      setName('')
      await loadData()
    } catch (err) {
      setCreateMessage(err instanceof Error ? err.message : 'Scene creation failed')
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
          <p className="text-sm text-slate-400 mt-0.5">Spatial computing and immersive scenes · Lead AI: Entari</p>
        </div>
        <button
          onClick={() => void loadData()} disabled={loading} aria-label="Refresh VRAR3D scenes"
          className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-300 hover:text-white disabled:opacity-50"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin motion-reduce:animate-none' : ''} /> Refresh
        </button>
      </div>

      {error && <p role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">{error}</p>}
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400">My scenes</p>
          <p className="text-2xl font-bold text-white">{scenes.length}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400">Supported scene types</p>
          <p className="text-2xl font-bold text-cyan-400">{SCENE_TYPES.length}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <section className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4 space-y-3">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2">
            <Plus size={14} className="text-indigo-400" /> New scene
          </h2>
          <label htmlFor="vrar-scene-name" className="text-xs text-slate-300">Scene name</label>
          <input
            id="vrar-scene-name" maxLength={120} value={name} onChange={e => setName(e.target.value)}
            placeholder="Scene name" className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-xs text-slate-200"
          />
          <label htmlFor="vrar-scene-type" className="text-xs text-slate-300">Scene type</label>
          <select
            id="vrar-scene-type" value={sceneType} onChange={e => setSceneType(e.target.value as SceneType)}
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-xs text-slate-200"
          >
            {SCENE_TYPES.map(type => <option key={type} value={type}>{type.toUpperCase()}</option>)}
          </select>
          <button onClick={() => void createScene()} disabled={!authorized || creating || !name.trim()}
            className="w-full flex items-center justify-center gap-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 px-4 py-2 text-xs text-white font-medium"
          >
            <Plus size={12} /> {creating ? 'Creating…' : 'Create scene'}
          </button>
          {createMessage && <p role="status" className="text-xs text-slate-300">{createMessage}</p>}
        </section>

        <section className="md:col-span-2 rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2 mb-3">
            <Layers size={14} className="text-indigo-400" /> My spatial scenes
          </h2>
          {loading ? <p role="status" className="text-xs text-slate-400">Loading scenes…</p> :
            scenes.length === 0 ?
              <p className="text-xs text-slate-400">No scenes to display. Create a private scene to get started.</p> :
              <div className="space-y-2">
                {scenes.map(scene => (
                  <div key={scene.scene_id} className="flex items-center gap-3 py-2 border-b border-slate-800 last:border-0">
                    <span aria-hidden="true" className="h-2 w-2 rounded-full shrink-0"
                      style={{ backgroundColor: TYPE_COLORS[scene.scene_type] ?? '#94a3b8' }}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-slate-200 truncate">{scene.name}</p>
                      <p className="text-xs text-slate-400">{scene.scene_type} · {scene.objects?.length ?? 0} objects</p>
                    </div>
                    <span className="text-xs text-slate-400">Private</span>
                  </div>
                ))}
              </div>
          }
        </section>
      </div>
    </div>
  )
}
