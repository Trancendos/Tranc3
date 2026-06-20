import React, { useCallback, useEffect, useState } from 'react'
import { Box, RefreshCw, Plus, Gamepad2 } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const API = '/tranceflow-svc'
const HEADERS = { 'X-Internal-Secret': 'dev-secret' }
const INTERNAL = { 'X-Internal-Secret': 'dev-secret', 'Content-Type': 'application/json' }

const GAME_ENGINES = ['godot', 'unity', 'unreal', 'custom']
const ASSET_TYPES = ['mesh', 'texture', 'material', 'scene', 'animation', 'audio', 'script', 'prefab']

interface Game {
  id: number
  title: string
  engine: string
  genre: string | null
  status: string
}

interface Asset {
  id: number
  name: string
  asset_type: string
  file_path: string | null
  game_id: number | null
}

const STATUS_COLORS: Record<string, string> = {
  development: 'text-blue-400',
  alpha: 'text-amber-400',
  beta: 'text-purple-400',
  released: 'text-emerald-400',
  archived: 'text-slate-500',
}

export default function TranceFlowPage() {
  const { trackPageView } = useAnalytics()
  const [games, setGames] = useState<Game[]>([])
  const [assets, setAssets] = useState<Asset[]>([])
  const [totalGames, setTotalGames] = useState(0)
  const [totalAssets, setTotalAssets] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [title, setTitle] = useState('')
  const [engine, setEngine] = useState('godot')
  const [creating, setCreating] = useState(false)
  const [createMsg, setCreateMsg] = useState<string | null>(null)

  useEffect(() => { trackPageView('/tranceflow') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [healthRes, gamesRes, assetsRes] = await Promise.all([
        fetch(`${API}/health`),
        fetch(`${API}/games?limit=10`, { headers: HEADERS }),
        fetch(`${API}/assets?limit=10`, { headers: HEADERS }),
      ])
      if (!healthRes.ok) throw new Error('TranceFlow unavailable')
      const h = await healthRes.json()
      setTotalGames(h.games ?? 0)
      setTotalAssets(h.assets ?? 0)
      if (gamesRes.ok) {
        const g = await gamesRes.json()
        setGames(g.games ?? g)
      }
      if (assetsRes.ok) {
        const a = await assetsRes.json()
        setAssets(a.assets ?? a)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const createGame = async () => {
    if (!title.trim()) return
    setCreating(true)
    setCreateMsg(null)
    try {
      const res = await fetch(`${API}/games`, {
        method: 'POST',
        headers: INTERNAL,
        body: JSON.stringify({ title, engine, created_by: 'demo' }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setCreateMsg('Game created!')
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
            <Box size={22} className="text-purple-400" /> TranceFlow
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">3D modelling &amp; games creation studio — Lead AI: Junior Cesar</p>
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
          {error} — is tranceflow running on port 8067?
        </div>
      )}

      <div className="grid grid-cols-4 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Games</p>
          <p className="text-2xl font-bold text-white">{totalGames}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Assets</p>
          <p className="text-2xl font-bold text-purple-400">{totalAssets}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Engines</p>
          <p className="text-2xl font-bold text-blue-400">{GAME_ENGINES.length}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Asset Types</p>
          <p className="text-2xl font-bold text-cyan-400">{ASSET_TYPES.length}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4 space-y-3">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2"><Plus size={14} className="text-purple-400" /> New Game</h2>
          <input
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder="Game title"
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-purple-500"
          />
          <select
            value={engine}
            onChange={e => setEngine(e.target.value)}
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-purple-500"
          >
            {GAME_ENGINES.map(e => <option key={e} value={e}>{e}</option>)}
          </select>
          <button
            onClick={createGame}
            disabled={creating || !title.trim()}
            className="w-full flex items-center justify-center gap-1.5 rounded-lg bg-purple-600 hover:bg-purple-700 disabled:opacity-50 px-4 py-1.5 text-xs text-white font-medium transition-colors"
          >
            <Plus size={11} /> {creating ? 'Creating…' : 'Create'}
          </button>
          {createMsg && <p className="text-xs text-emerald-400">{createMsg}</p>}
        </div>

        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2 mb-3"><Gamepad2 size={14} className="text-purple-400" /> Games</h2>
          {games.length === 0 ? (
            <p className="text-xs text-slate-500">No games yet</p>
          ) : (
            <div className="space-y-2">
              {games.map(g => (
                <div key={g.id} className="flex items-center gap-2 py-2 border-b border-slate-800 last:border-0">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-slate-200 truncate">{g.title}</p>
                    <p className="text-xs text-slate-500">{g.engine}{g.genre ? ` · ${g.genre}` : ''}</p>
                  </div>
                  <span className={`text-xs shrink-0 ${STATUS_COLORS[g.status] ?? 'text-slate-400'}`}>{g.status}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2 mb-3"><Box size={14} className="text-purple-400" /> Assets</h2>
          {assets.length === 0 ? (
            <p className="text-xs text-slate-500">No assets yet</p>
          ) : (
            <div className="space-y-2">
              {assets.map(a => (
                <div key={a.id} className="py-2 border-b border-slate-800 last:border-0">
                  <p className="text-xs font-medium text-slate-200 truncate">{a.name}</p>
                  <p className="text-xs text-slate-500">{a.asset_type}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
