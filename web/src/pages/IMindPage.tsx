import React, { useCallback, useEffect, useState } from 'react'
import { Brain, RefreshCw, Send } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const API = '/imind-svc'
const INTERNAL = { 'X-Internal-Secret': 'dev-secret', 'Content-Type': 'application/json' }

interface AnalysisResult {
  dominant_emotion: string
  confidence: number
  scores: Record<string, number>
  matched_words: Record<string, string[]>
  sentiment: string
  sentiment_score: number
}

interface EmotionsInfo {
  emotions: string[]
  keyword_counts: Record<string, number>
}

const EMOTION_COLORS: Record<string, string> = {
  joy:       'bg-yellow-500/20 text-yellow-300',
  sadness:   'bg-blue-500/20 text-blue-300',
  anger:     'bg-red-500/20 text-red-300',
  fear:      'bg-purple-500/20 text-purple-300',
  surprise:  'bg-cyan-500/20 text-cyan-300',
  disgust:   'bg-green-500/20 text-green-300',
  trust:     'bg-emerald-500/20 text-emerald-300',
  anticipation: 'bg-orange-500/20 text-orange-300',
}

export default function IMindPage() {
  const { trackPageView } = useAnalytics()
  const [totalAnalyses, setTotalAnalyses] = useState(0)
  const [userProfiles, setUserProfiles] = useState(0)
  const [emotions, setEmotions] = useState<EmotionsInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [text, setText] = useState('')
  const [analysing, setAnalysing] = useState(false)
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [analyseError, setAnalyseError] = useState<string | null>(null)

  useEffect(() => { trackPageView('/imind') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [hRes, eRes] = await Promise.all([
        fetch(`${API}/health`),
        fetch(`${API}/emotions`, { headers: INTERNAL }),
      ])
      if (!hRes.ok) throw new Error('I-Mind unavailable')
      const h = await hRes.json()
      setTotalAnalyses(h.total_analyses ?? 0)
      setUserProfiles(h.user_profiles ?? 0)
      if (eRes.ok) setEmotions(await eRes.json())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const analyse = async () => {
    if (!text.trim()) return
    setAnalysing(true)
    setResult(null)
    setAnalyseError(null)
    try {
      const res = await fetch(`${API}/analyse`, {
        method: 'POST',
        headers: INTERNAL,
        body: JSON.stringify({ text, user_id: 'demo' }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setResult(await res.json())
      setTotalAnalyses(t => t + 1)
    } catch (e) {
      setAnalyseError(e instanceof Error ? e.message : 'Analysis failed')
    } finally {
      setAnalysing(false)
    }
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Brain size={22} className="text-pink-400" /> I-Mind
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Sensitivity to emotion engine — Lead AI: Elouise</p>
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
          {error} — is imind running on port 8059?
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Total Analyses</p>
          <p className="text-2xl font-bold text-white">{totalAnalyses}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Tracked Profiles</p>
          <p className="text-2xl font-bold text-pink-400">{userProfiles}</p>
        </div>
      </div>

      {emotions && (
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <h2 className="text-sm font-semibold text-white mb-3">Emotion Lexicon</h2>
          <div className="flex flex-wrap gap-2">
            {emotions.emotions.map(e => (
              <span key={e} className={`text-xs px-2 py-1 rounded ${EMOTION_COLORS[e] ?? 'bg-slate-700/40 text-slate-300'}`}>
                {e} <span className="opacity-60">({emotions.keyword_counts[e]} kw)</span>
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4 space-y-3">
        <h2 className="text-sm font-semibold text-white">Emotion Analysis</h2>
        <textarea
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && e.ctrlKey && analyse()}
          placeholder="Enter text to analyse emotions… (Ctrl+Enter to send)"
          rows={3}
          className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-pink-500 resize-none"
        />
        <button
          onClick={analyse}
          disabled={analysing || !text.trim()}
          className="flex items-center gap-1.5 rounded-lg bg-pink-600 hover:bg-pink-700 disabled:opacity-50 px-4 py-1.5 text-xs text-white font-medium transition-colors"
        >
          <Send size={11} /> {analysing ? 'Analysing…' : 'Analyse'}
        </button>
        {analyseError && <p className="text-xs text-red-400">{analyseError}</p>}
      </div>

      {result && (
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4 space-y-3">
          <div className="flex items-center gap-3">
            <span className={`text-sm font-bold px-3 py-1 rounded-full ${EMOTION_COLORS[result.dominant_emotion] ?? 'bg-slate-700/40 text-slate-300'}`}>
              {result.dominant_emotion}
            </span>
            <span className="text-xs text-slate-400">confidence: <span className="text-white">{(result.confidence * 100).toFixed(1)}%</span></span>
            <span className="text-xs text-slate-400 ml-auto">sentiment: <span className={result.sentiment === 'positive' ? 'text-emerald-400' : result.sentiment === 'negative' ? 'text-red-400' : 'text-slate-300'}>{result.sentiment}</span></span>
          </div>
          <div className="space-y-1.5">
            {Object.entries(result.scores)
              .filter(([, v]) => v > 0)
              .sort(([, a], [, b]) => b - a)
              .map(([emotion, score]) => (
                <div key={emotion} className="flex items-center gap-2 text-xs">
                  <span className="text-slate-400 w-24">{emotion}</span>
                  <div className="flex-1 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                    <div className="h-full bg-pink-500/60 rounded-full" style={{ width: `${score * 100}%` }} />
                  </div>
                  <span className="text-slate-500 w-10 text-right">{(score * 100).toFixed(0)}%</span>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  )
}
