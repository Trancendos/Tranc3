import React, { useCallback, useEffect, useState } from 'react'
import { Heart, RefreshCw, Send } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const API = '/resonate-svc'
const INTERNAL = { 'X-Internal-Secret': 'dev-secret', 'Content-Type': 'application/json' }

interface EmpathyScore {
  empathy_score: number
  emotional_intensity: number
  tone: string
  sentiment: string
  sentiment_score: number
  signals: string[]
}

export default function ResonatePage() {
  const { trackPageView } = useAnalytics()
  const [totalScored, setTotalScored] = useState(0)
  const [conversations, setConversations] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [text, setText] = useState('')
  const [scoring, setScoring] = useState(false)
  const [result, setResult] = useState<EmpathyScore | null>(null)
  const [scoreError, setScoreError] = useState<string | null>(null)

  useEffect(() => { trackPageView('/resonate') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API}/health`)
      if (!res.ok) throw new Error('Resonate unavailable')
      const h = await res.json()
      setTotalScored(h.total_scored ?? 0)
      setConversations(h.conversations ?? 0)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const score = async () => {
    if (!text.trim()) return
    setScoring(true)
    setResult(null)
    setScoreError(null)
    try {
      const res = await fetch(`${API}/score`, {
        method: 'POST',
        headers: INTERNAL,
        body: JSON.stringify({ text }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setResult(await res.json())
      setTotalScored(t => t + 1)
    } catch (e) {
      setScoreError(e instanceof Error ? e.message : 'Scoring failed')
    } finally {
      setScoring(false)
    }
  }

  const empathyColor = (score: number) => {
    if (score >= 0.7) return 'text-emerald-400'
    if (score >= 0.4) return 'text-amber-400'
    return 'text-red-400'
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Heart size={22} className="text-rose-400" /> Resonate
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Empathy engine — Lead AI: Magdalena</p>
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
          {error} — is resonate running on port 8060?
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Total Scored</p>
          <p className="text-2xl font-bold text-white">{totalScored}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Conversations</p>
          <p className="text-2xl font-bold text-rose-400">{conversations}</p>
        </div>
      </div>

      <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4 space-y-3">
        <h2 className="text-sm font-semibold text-white">Empathy Scoring</h2>
        <textarea
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && e.ctrlKey && score()}
          placeholder="Enter text to score for empathy… (Ctrl+Enter)"
          rows={3}
          className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-rose-500 resize-none"
        />
        <button
          onClick={score}
          disabled={scoring || !text.trim()}
          className="flex items-center gap-1.5 rounded-lg bg-rose-600 hover:bg-rose-700 disabled:opacity-50 px-4 py-1.5 text-xs text-white font-medium transition-colors"
        >
          <Send size={11} /> {scoring ? 'Scoring…' : 'Score'}
        </button>
        {scoreError && <p className="text-xs text-red-400">{scoreError}</p>}
      </div>

      {result && (
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4 space-y-4">
          <div className="flex items-center gap-6">
            <div>
              <p className="text-xs text-slate-400 mb-1">Empathy Score</p>
              <p className={`text-3xl font-bold ${empathyColor(result.empathy_score)}`}>
                {(result.empathy_score * 100).toFixed(0)}%
              </p>
            </div>
            <div>
              <p className="text-xs text-slate-400 mb-1">Tone</p>
              <p className="text-sm font-medium text-white capitalize">{result.tone}</p>
            </div>
            <div>
              <p className="text-xs text-slate-400 mb-1">Sentiment</p>
              <p className={`text-sm font-medium capitalize ${result.sentiment === 'positive' ? 'text-emerald-400' : result.sentiment === 'negative' ? 'text-red-400' : 'text-slate-300'}`}>
                {result.sentiment}
              </p>
            </div>
            <div>
              <p className="text-xs text-slate-400 mb-1">Emotional Intensity</p>
              <p className="text-sm font-medium text-amber-400">{(result.emotional_intensity * 100).toFixed(0)}%</p>
            </div>
          </div>
          {result.signals.length > 0 && (
            <div>
              <p className="text-xs text-slate-400 mb-2">Empathy Signals</p>
              <div className="flex flex-wrap gap-1.5">
                {result.signals.map((s, i) => (
                  <span key={i} className="text-xs bg-rose-500/20 text-rose-300 border border-rose-500/30 px-2 py-0.5 rounded">{s}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
