import React, { useCallback, useEffect, useState } from 'react'
import { Palette, RefreshCw, Image, Clock } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const API = '/photo-svc'
const INTERNAL = { 'X-Internal-Secret': 'dev-secret', 'Content-Type': 'application/json' }

interface Job {
  id: number
  prompt: string
  width: number
  height: number
  model: string
  status: string
  created_at: number
  completed_at: number | null
  image_id: number | null
  error: string | null
}

interface StudioImage {
  id: number
  job_id: number
  model: string
  prompt: string
  width: number
  height: number
  created_at: number
}

const JOB_STATUS_COLORS: Record<string, string> = {
  pending:    'bg-amber-500/20 text-amber-300 border-amber-500/30',
  processing: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  completed:  'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  failed:     'bg-red-500/20 text-red-300 border-red-500/30',
}

const MODELS = ['flux', 'turbo', 'flux-realism', 'flux-anime', 'flux-3d']

export default function SashasPhotoStudioPage() {
  const { trackPageView } = useAnalytics()
  const [totalJobs, setTotalJobs] = useState(0)
  const [totalImages, setTotalImages] = useState(0)
  const [jobs, setJobs] = useState<Job[]>([])
  const [images, setImages] = useState<StudioImage[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<'jobs' | 'images'>('jobs')
  const [prompt, setPrompt] = useState('')
  const [model, setModel] = useState('flux')
  const [generating, setGenerating] = useState(false)
  const [genMsg, setGenMsg] = useState<string | null>(null)

  useEffect(() => { trackPageView('/sashas-photo-studio') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [hRes, jRes, iRes] = await Promise.all([
        fetch(`${API}/health`),
        fetch(`${API}/jobs?limit=30`, { headers: INTERNAL }),
        fetch(`${API}/images?limit=20`, { headers: INTERNAL }),
      ])
      if (!hRes.ok) throw new Error("Sasha's Photo Studio unavailable")
      const h = await hRes.json()
      setTotalJobs(h.total_jobs ?? 0)
      setTotalImages(h.total_images ?? 0)
      if (jRes.ok) { const d = await jRes.json(); setJobs(d.jobs ?? d ?? []) }
      if (iRes.ok) { const d = await iRes.json(); setImages(d.images ?? d ?? []) }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const generate = async () => {
    if (!prompt.trim()) return
    setGenerating(true)
    setGenMsg(null)
    try {
      const res = await fetch(`${API}/generate`, {
        method: 'POST',
        headers: INTERNAL,
        body: JSON.stringify({ prompt, model, width: 512, height: 512 }),
      })
      const data = await res.json()
      setGenMsg(`Job #${data.job_id ?? '?'} queued`)
      setPrompt('')
      setTimeout(loadData, 1000)
    } catch {
      setGenMsg('error generating')
    } finally {
      setGenerating(false)
    }
  }

  const fmt = (ts: number) => {
    try { return new Date(ts * 1000).toLocaleString() } catch { return String(ts) }
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Palette size={22} className="text-pink-400" /> Sasha's Photo Studio
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Photo & image generation — Lead AI: Madam Krystal</p>
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
          {error} — is sashas-photo-studio running on port 8051?
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1 flex items-center gap-1"><Clock size={11} /> Total Jobs</p>
          <p className="text-2xl font-bold text-white">{totalJobs}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1 flex items-center gap-1"><Image size={11} /> Generated Images</p>
          <p className="text-2xl font-bold text-pink-400">{totalImages}</p>
        </div>
      </div>

      <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4 space-y-3">
        <h2 className="text-sm font-semibold text-white">Generate Image</h2>
        <textarea
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          placeholder="Describe the image to generate…"
          rows={2}
          className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-pink-500 resize-none"
        />
        <div className="flex items-center gap-2">
          <select
            value={model}
            onChange={e => setModel(e.target.value)}
            className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-pink-500"
          >
            {MODELS.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
          <button
            onClick={generate}
            disabled={generating || !prompt.trim()}
            className="rounded-lg bg-pink-600 hover:bg-pink-700 disabled:opacity-50 px-4 py-1.5 text-xs text-white font-medium transition-colors"
          >
            {generating ? 'Generating…' : 'Generate'}
          </button>
          {genMsg && <span className="text-xs text-slate-400">{genMsg}</span>}
        </div>
      </div>

      <div className="flex gap-2 border-b border-slate-700/60">
        {(['jobs', 'images'] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-1.5 text-xs font-medium transition-colors ${tab === t ? 'text-white border-b-2 border-pink-500' : 'text-slate-400 hover:text-slate-200'}`}
          >
            {t === 'jobs' ? 'Jobs' : 'Images'}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-center text-slate-500 text-sm py-8">Loading…</div>
      ) : tab === 'jobs' ? (
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 overflow-hidden">
          {jobs.length === 0 ? (
            <div className="p-8 text-center text-slate-500 text-sm">No jobs yet.</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700/60 text-xs text-slate-500 uppercase tracking-wider">
                  <th className="text-left px-4 py-2">ID</th>
                  <th className="text-left px-4 py-2">Prompt</th>
                  <th className="text-left px-4 py-2">Model</th>
                  <th className="text-left px-4 py-2">Status</th>
                  <th className="text-right px-4 py-2">Created</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map(j => (
                  <tr key={j.id} className="border-b border-slate-800 hover:bg-slate-800/30 transition-colors">
                    <td className="px-4 py-2.5 text-xs text-slate-500">{j.id}</td>
                    <td className="px-4 py-2.5 text-xs text-slate-300 max-w-xs truncate">{j.prompt}</td>
                    <td className="px-4 py-2.5 text-xs text-slate-500">{j.model}</td>
                    <td className="px-4 py-2.5">
                      <span className={`text-xs px-1.5 py-0.5 rounded border ${JOB_STATUS_COLORS[j.status] ?? 'bg-slate-700/40 text-slate-400 border-slate-600/30'}`}>
                        {j.status}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-right text-xs text-slate-600 whitespace-nowrap">{fmt(j.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : (
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          {images.length === 0 ? (
            <div className="p-4 text-center text-slate-500 text-sm">No images yet.</div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {images.map(img => (
                <div key={img.id} className="rounded-lg border border-slate-700/40 bg-slate-800/40 p-2.5">
                  <div className="w-full aspect-square bg-slate-700/40 rounded mb-2 flex items-center justify-center">
                    <Image size={24} className="text-slate-600" />
                  </div>
                  <p className="text-xs text-slate-400 truncate">{img.prompt}</p>
                  <p className="text-xs text-slate-600 mt-0.5">{img.model} · {img.width}×{img.height}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
