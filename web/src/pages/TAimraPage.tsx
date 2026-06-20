import React, { useCallback, useEffect, useState } from 'react'
import { User, RefreshCw, Target, Brain } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const API = '/taimra-svc'
const HEADERS = { 'X-Internal-Secret': 'dev-secret' }
const INTERNAL = { 'X-Internal-Secret': 'dev-secret', 'Content-Type': 'application/json' }
const USER_ID = 'demo'

interface Twin {
  user_id: string
  display_name: string | null
  opted_in: boolean
  created_at: number
}

interface Summary {
  twin: Twin
  preferences_set: number
  active_goals: number
  memories: number
  active_routines: number
}

interface Goal {
  id: number
  title: string
  description: string | null
  status: string
  created_at: number
}

export default function TAimraPage() {
  const { trackPageView } = useAnalytics()
  const [activeTwins, setActiveTwins] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [summary, setSummary] = useState<Summary | null>(null)
  const [goals, setGoals] = useState<Goal[]>([])

  // Goal form
  const [goalTitle, setGoalTitle] = useState('')
  const [goalDesc, setGoalDesc] = useState('')
  const [addingGoal, setAddingGoal] = useState(false)
  const [goalMsg, setGoalMsg] = useState<string | null>(null)

  useEffect(() => { trackPageView('/taimra') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [healthRes, sumRes, goalsRes] = await Promise.all([
        fetch(`${API}/health`),
        fetch(`${API}/twin/${USER_ID}/summary`, { headers: HEADERS }),
        fetch(`${API}/twin/${USER_ID}/goals`, { headers: HEADERS }),
      ])
      if (!healthRes.ok) throw new Error('tAimra unavailable')
      const h = await healthRes.json()
      setActiveTwins(h.active_twins ?? 0)
      if (sumRes.ok) setSummary(await sumRes.json())
      if (goalsRes.ok) {
        const g = await goalsRes.json()
        setGoals(g.goals ?? [])
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const addGoal = async () => {
    if (!goalTitle.trim()) return
    setAddingGoal(true)
    setGoalMsg(null)
    try {
      const res = await fetch(`${API}/twin/${USER_ID}/goals`, {
        method: 'POST',
        headers: INTERNAL,
        body: JSON.stringify({ title: goalTitle, description: goalDesc }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setGoalMsg('Goal added!')
      setGoalTitle('')
      setGoalDesc('')
      loadData()
    } catch (e) {
      setGoalMsg(e instanceof Error ? e.message : 'Failed')
    } finally {
      setAddingGoal(false)
    }
  }

  const STATUS_COLORS: Record<string, string> = {
    active: 'text-emerald-400',
    completed: 'text-blue-400',
    abandoned: 'text-slate-500',
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <User size={22} className="text-violet-400" /> tAimra
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Opt-in digital twin & life assistant — Lead AI: tAImra</p>
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
          {error} — is tAimra running on port 8065?
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Active Twins</p>
          <p className="text-2xl font-bold text-violet-400">{activeTwins}</p>
        </div>
        {summary && (
          <>
            <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
              <p className="text-xs text-slate-400 mb-1">Active Goals</p>
              <p className="text-2xl font-bold text-emerald-400">{summary.active_goals}</p>
            </div>
            <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
              <p className="text-xs text-slate-400 mb-1">Memories</p>
              <p className="text-2xl font-bold text-amber-400">{summary.memories}</p>
            </div>
            <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
              <p className="text-xs text-slate-400 mb-1">Preferences</p>
              <p className="text-2xl font-bold text-blue-400">{summary.preferences_set}</p>
            </div>
          </>
        )}
      </div>

      {summary && (
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2 mb-3">
            <Brain size={14} className="text-violet-400" /> Your Digital Twin
          </h2>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-violet-600/30 border border-violet-500/40 flex items-center justify-center">
              <User size={18} className="text-violet-300" />
            </div>
            <div>
              <p className="text-sm font-medium text-white">{summary.twin.display_name ?? USER_ID}</p>
              <p className={`text-xs ${summary.twin.opted_in ? 'text-emerald-400' : 'text-slate-500'}`}>
                {summary.twin.opted_in ? '✓ Opted in' : 'Not opted in'}
              </p>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Add goal */}
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4 space-y-3">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2">
            <Target size={14} className="text-emerald-400" /> Add Goal
          </h2>
          <input
            value={goalTitle}
            onChange={e => setGoalTitle(e.target.value)}
            placeholder="Goal title"
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-violet-500"
          />
          <input
            value={goalDesc}
            onChange={e => setGoalDesc(e.target.value)}
            placeholder="Description (optional)"
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-violet-500"
          />
          <button
            onClick={addGoal}
            disabled={addingGoal || !goalTitle.trim()}
            className="flex items-center gap-1.5 rounded-lg bg-violet-600 hover:bg-violet-700 disabled:opacity-50 px-4 py-1.5 text-xs text-white font-medium transition-colors"
          >
            <Target size={11} /> {addingGoal ? 'Adding…' : 'Add Goal'}
          </button>
          {goalMsg && <p className="text-xs text-emerald-400">{goalMsg}</p>}
        </div>

        {/* Goals list */}
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4 space-y-2">
          <h2 className="text-sm font-semibold text-white mb-3">Goals</h2>
          {goals.length === 0 ? (
            <p className="text-xs text-slate-500">No goals yet</p>
          ) : (
            goals.slice(0, 8).map(g => (
              <div key={g.id} className="flex items-start justify-between gap-2 py-1.5 border-b border-slate-800 last:border-0">
                <div>
                  <p className="text-xs font-medium text-slate-200">{g.title}</p>
                  {g.description && <p className="text-xs text-slate-500 truncate">{g.description}</p>}
                </div>
                <span className={`text-xs shrink-0 ${STATUS_COLORS[g.status] ?? 'text-slate-400'}`}>{g.status}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
