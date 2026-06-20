import React, { useCallback, useEffect, useState } from 'react'
import { Music, RefreshCw, Play, Radio } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const API = '/warp-radio-svc'
const HEADERS = { 'X-Internal-Secret': 'dev-secret' }
const INTERNAL = { 'X-Internal-Secret': 'dev-secret', 'Content-Type': 'application/json' }

interface Playlist {
  id: number
  name: string
  genre: string | null
  owner: string | null
  is_public: boolean
}

interface TopTrack {
  title: string
  artist: string
  plays: number
}

export default function WarpRadioPage() {
  const { trackPageView } = useAnalytics()
  const [playlists, setPlaylists] = useState<Playlist[]>([])
  const [totalPlaylists, setTotalPlaylists] = useState(0)
  const [totalTracks, setTotalTracks] = useState(0)
  const [topTracks, setTopTracks] = useState<TopTrack[]>([])
  const [totalPlays, setTotalPlays] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Create playlist form
  const [name, setName] = useState('')
  const [genre, setGenre] = useState('')
  const [creating, setCreating] = useState(false)
  const [createMsg, setCreateMsg] = useState<string | null>(null)

  useEffect(() => { trackPageView('/warp-radio') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [healthRes, playlistsRes, statsRes] = await Promise.all([
        fetch(`${API}/health`),
        fetch(`${API}/playlists?limit=10`, { headers: HEADERS }),
        fetch(`${API}/stats`, { headers: HEADERS }),
      ])
      if (!healthRes.ok) throw new Error('Warp Radio unavailable')
      const h = await healthRes.json()
      setTotalPlaylists(h.playlists ?? 0)
      setTotalTracks(h.tracks ?? 0)
      if (playlistsRes.ok) {
        const p = await playlistsRes.json()
        setPlaylists(p.playlists ?? p)
      }
      if (statsRes.ok) {
        const s = await statsRes.json()
        setTotalPlays(s.total_plays ?? 0)
        setTopTracks(s.top_tracks ?? [])
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const createPlaylist = async () => {
    if (!name.trim()) return
    setCreating(true)
    setCreateMsg(null)
    try {
      const res = await fetch(`${API}/playlists`, {
        method: 'POST',
        headers: INTERNAL,
        body: JSON.stringify({ name, genre: genre || undefined, owner: 'demo', is_public: true }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setCreateMsg('Playlist created!')
      setName('')
      setGenre('')
      loadData()
    } catch (e) {
      setCreateMsg(e instanceof Error ? e.message : 'Failed')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Radio size={22} className="text-amber-400" /> Warp Radio
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Music & audio streaming — Lead AI: Rocking Ricki</p>
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
          {error} — is warp-radio running on port 8057?
        </div>
      )}

      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Playlists</p>
          <p className="text-2xl font-bold text-white">{totalPlaylists}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Tracks</p>
          <p className="text-2xl font-bold text-amber-400">{totalTracks}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Total Plays</p>
          <p className="text-2xl font-bold text-emerald-400">{totalPlays}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Create playlist */}
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4 space-y-3">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2"><Music size={14} className="text-amber-400" /> New Playlist</h2>
          <input
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="Playlist name"
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-amber-500"
          />
          <input
            value={genre}
            onChange={e => setGenre(e.target.value)}
            placeholder="Genre (optional)"
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-amber-500"
          />
          <button
            onClick={createPlaylist}
            disabled={creating || !name.trim()}
            className="flex items-center gap-1.5 rounded-lg bg-amber-600 hover:bg-amber-700 disabled:opacity-50 px-4 py-1.5 text-xs text-white font-medium transition-colors"
          >
            <Music size={11} /> {creating ? 'Creating…' : 'Create Playlist'}
          </button>
          {createMsg && <p className="text-xs text-emerald-400">{createMsg}</p>}
        </div>

        {/* Playlists */}
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <h2 className="text-sm font-semibold text-white mb-3">Playlists</h2>
          {playlists.length === 0 ? (
            <p className="text-xs text-slate-500">No playlists yet</p>
          ) : (
            <div className="space-y-2">
              {playlists.map(p => (
                <div key={p.id} className="flex items-center justify-between py-1.5 border-b border-slate-800 last:border-0">
                  <div>
                    <p className="text-xs font-medium text-slate-200">{p.name}</p>
                    {p.genre && <p className="text-xs text-slate-500">{p.genre}</p>}
                  </div>
                  <span className={`text-xs ${p.is_public ? 'text-emerald-400' : 'text-slate-500'}`}>
                    {p.is_public ? 'public' : 'private'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {topTracks.length > 0 && (
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2 mb-3">
            <Play size={14} className="text-amber-400" /> Top Tracks
          </h2>
          <div className="space-y-1.5">
            {topTracks.map((t, i) => (
              <div key={i} className="flex items-center justify-between py-1.5 border-b border-slate-800 last:border-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-slate-600 w-4">{i + 1}</span>
                  <div>
                    <p className="text-xs font-medium text-slate-200">{t.title}</p>
                    <p className="text-xs text-slate-500">{t.artist}</p>
                  </div>
                </div>
                <span className="text-xs text-amber-400">{t.plays} plays</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
