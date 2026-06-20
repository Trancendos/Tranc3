import React, { useCallback, useEffect, useState } from 'react'
import { Heart, RefreshCw, Send, Moon, BookOpen, Smile } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const API = '/tranquility-svc'
const INTERNAL = { 'X-Internal-Secret': 'dev-secret', 'Content-Type': 'application/json' }
const USER_ID = 'demo'

interface Summary {
  avg_mood_score: number | null
  avg_sleep_hours: number | null
  mindfulness_minutes: number
  journal_entries: number
}

const MOOD_LABELS: Record<number, string> = { 1: 'Terrible', 2: 'Bad', 3: 'Okay', 4: 'Good', 5: 'Great' }
const MOOD_COLORS: Record<number, string> = {
  1: 'text-red-400', 2: 'text-orange-400', 3: 'text-amber-400', 4: 'text-emerald-400', 5: 'text-green-400',
}

export default function TranquilityPage() {
  const { trackPageView } = useAnalytics()
  const [journalCount, setJournalCount] = useState(0)
  const [moodLogs, setMoodLogs] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [summary, setSummary] = useState<Summary | null>(null)

  // Mood logging
  const [moodScore, setMoodScore] = useState(3)
  const [moodNotes, setMoodNotes] = useState('')
  const [loggingMood, setLoggingMood] = useState(false)
  const [moodMsg, setMoodMsg] = useState<string | null>(null)

  // Journal
  const [journalText, setJournalText] = useState('')
  const [journalMood, setJournalMood] = useState(3)
  const [writingJournal, setWritingJournal] = useState(false)
  const [journalMsg, setJournalMsg] = useState<string | null>(null)

  useEffect(() => { trackPageView('/tranquility') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [healthRes, sumRes] = await Promise.all([
        fetch(`${API}/health`),
        fetch(`${API}/summary/${USER_ID}`, { headers: { 'X-Internal-Secret': 'dev-secret' } }),
      ])
      if (!healthRes.ok) throw new Error('Tranquility unavailable')
      const h = await healthRes.json()
      setJournalCount(h.journal_entries ?? 0)
      setMoodLogs(h.mood_logs ?? 0)
      if (sumRes.ok) setSummary(await sumRes.json())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const logMood = async () => {
    setLoggingMood(true)
    setMoodMsg(null)
    try {
      const res = await fetch(`${API}/mood`, {
        method: 'POST',
        headers: INTERNAL,
        body: JSON.stringify({ user_id: USER_ID, score: moodScore, notes: moodNotes }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setMoodMsg('Mood logged!')
      setMoodNotes('')
      setMoodLogs(m => m + 1)
    } catch (e) {
      setMoodMsg(e instanceof Error ? e.message : 'Failed')
    } finally {
      setLoggingMood(false)
    }
  }

  const writeJournal = async () => {
    if (!journalText.trim()) return
    setWritingJournal(true)
    setJournalMsg(null)
    try {
      const res = await fetch(`${API}/journal`, {
        method: 'POST',
        headers: INTERNAL,
        body: JSON.stringify({ user_id: USER_ID, content: journalText, mood_score: journalMood }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setJournalMsg('Journal entry saved!')
      setJournalText('')
      setJournalCount(j => j + 1)
    } catch (e) {
      setJournalMsg(e instanceof Error ? e.message : 'Failed')
    } finally {
      setWritingJournal(false)
    }
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Heart size={22} className="text-pink-400" /> Tranquility
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Wellbeing central hub — Lead AI: Savania</p>
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
          {error} — is tranquility running on port 8058?
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Journal Entries</p>
          <p className="text-2xl font-bold text-white">{journalCount}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Mood Logs</p>
          <p className="text-2xl font-bold text-pink-400">{moodLogs}</p>
        </div>
        {summary && (
          <>
            <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
              <p className="text-xs text-slate-400 mb-1">Avg Mood (7d)</p>
              <p className={`text-2xl font-bold ${summary.avg_mood_score ? MOOD_COLORS[Math.round(summary.avg_mood_score)] : 'text-slate-500'}`}>
                {summary.avg_mood_score ? summary.avg_mood_score.toFixed(1) : '—'}
              </p>
            </div>
            <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
              <p className="text-xs text-slate-400 mb-1">Mindfulness (7d)</p>
              <p className="text-2xl font-bold text-emerald-400">{summary.mindfulness_minutes}m</p>
            </div>
          </>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Mood logger */}
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4 space-y-3">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2"><Smile size={14} className="text-amber-400" /> Log Mood</h2>
          <div className="flex gap-2">
            {[1, 2, 3, 4, 5].map(s => (
              <button
                key={s}
                onClick={() => setMoodScore(s)}
                className={`flex-1 rounded-lg py-2 text-xs font-medium border transition-colors ${moodScore === s ? 'bg-pink-600 border-pink-500 text-white' : 'border-slate-700 text-slate-400 hover:text-white'}`}
              >
                {s}
              </button>
            ))}
          </div>
          <p className={`text-xs font-medium ${MOOD_COLORS[moodScore]}`}>{MOOD_LABELS[moodScore]}</p>
          <input
            value={moodNotes}
            onChange={e => setMoodNotes(e.target.value)}
            placeholder="Notes (optional)"
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-pink-500"
          />
          <button
            onClick={logMood}
            disabled={loggingMood}
            className="flex items-center gap-1.5 rounded-lg bg-pink-600 hover:bg-pink-700 disabled:opacity-50 px-4 py-1.5 text-xs text-white font-medium transition-colors"
          >
            <Send size={11} /> {loggingMood ? 'Logging…' : 'Log Mood'}
          </button>
          {moodMsg && <p className="text-xs text-emerald-400">{moodMsg}</p>}
        </div>

        {/* Journal */}
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4 space-y-3">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2"><BookOpen size={14} className="text-indigo-400" /> Journal</h2>
          <div className="flex gap-2">
            {[1, 2, 3, 4, 5].map(s => (
              <button
                key={s}
                onClick={() => setJournalMood(s)}
                className={`flex-1 rounded-lg py-1.5 text-xs font-medium border transition-colors ${journalMood === s ? 'bg-indigo-600 border-indigo-500 text-white' : 'border-slate-700 text-slate-400 hover:text-white'}`}
              >
                {s}
              </button>
            ))}
          </div>
          <textarea
            value={journalText}
            onChange={e => setJournalText(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && e.ctrlKey && writeJournal()}
            placeholder="Write your journal entry… (Ctrl+Enter)"
            rows={4}
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 resize-none"
          />
          <button
            onClick={writeJournal}
            disabled={writingJournal || !journalText.trim()}
            className="flex items-center gap-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 px-4 py-1.5 text-xs text-white font-medium transition-colors"
          >
            <Send size={11} /> {writingJournal ? 'Saving…' : 'Save Entry'}
          </button>
          {journalMsg && <p className="text-xs text-emerald-400">{journalMsg}</p>}
        </div>
      </div>

      {summary && (
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2 mb-3">
            <Moon size={14} className="text-blue-400" /> 7-Day Wellbeing Summary
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div>
              <p className="text-xs text-slate-400">Avg Mood</p>
              <p className={`text-lg font-bold ${summary.avg_mood_score ? MOOD_COLORS[Math.round(summary.avg_mood_score)] : 'text-slate-500'}`}>
                {summary.avg_mood_score ? `${summary.avg_mood_score.toFixed(1)}/5` : 'No data'}
              </p>
            </div>
            <div>
              <p className="text-xs text-slate-400">Avg Sleep</p>
              <p className="text-lg font-bold text-blue-400">
                {summary.avg_sleep_hours ? `${summary.avg_sleep_hours.toFixed(1)}h` : 'No data'}
              </p>
            </div>
            <div>
              <p className="text-xs text-slate-400">Mindfulness</p>
              <p className="text-lg font-bold text-emerald-400">{summary.mindfulness_minutes}m</p>
            </div>
            <div>
              <p className="text-xs text-slate-400">Journals</p>
              <p className="text-lg font-bold text-indigo-400">{summary.journal_entries}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
