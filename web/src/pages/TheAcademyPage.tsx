import React, { useCallback, useEffect, useState } from 'react'
import { BookOpen, RefreshCw, Plus, GraduationCap } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const API = '/academy-svc'
const HEADERS = { 'X-Internal-Secret': 'dev-secret' }
const INTERNAL = { 'X-Internal-Secret': 'dev-secret', 'Content-Type': 'application/json' }

interface Course {
  id: number
  title: string
  category: string | null
  difficulty: string | null
  published: boolean
  created_at: number
}

const DIFF_COLORS: Record<string, string> = {
  beginner: 'text-emerald-400',
  intermediate: 'text-amber-400',
  advanced: 'text-red-400',
}

export default function TheAcademyPage() {
  const { trackPageView } = useAnalytics()
  const [courses, setCourses] = useState<Course[]>([])
  const [totalCourses, setTotalCourses] = useState(0)
  const [totalEnrolments, setTotalEnrolments] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Create form
  const [title, setTitle] = useState('')
  const [category, setCategory] = useState('')
  const [difficulty, setDifficulty] = useState('beginner')
  const [creating, setCreating] = useState(false)
  const [createMsg, setCreateMsg] = useState<string | null>(null)

  useEffect(() => { trackPageView('/academy') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [healthRes, coursesRes] = await Promise.all([
        fetch(`${API}/health`),
        fetch(`${API}/courses?limit=20`, { headers: HEADERS }),
      ])
      if (!healthRes.ok) throw new Error('The Academy unavailable')
      const h = await healthRes.json()
      setTotalCourses(h.courses ?? 0)
      setTotalEnrolments(h.enrolments ?? 0)
      if (coursesRes.ok) {
        const c = await coursesRes.json()
        setCourses(c.courses ?? c)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const createCourse = async () => {
    if (!title.trim()) return
    setCreating(true)
    setCreateMsg(null)
    try {
      const res = await fetch(`${API}/courses`, {
        method: 'POST',
        headers: INTERNAL,
        body: JSON.stringify({ title, category: category || undefined, difficulty, created_by: 'demo' }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setCreateMsg('Course created!')
      setTitle('')
      setCategory('')
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
            <GraduationCap size={22} className="text-violet-400" /> The Academy
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Learning management system — Lead AI: Shimshi</p>
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
          {error} — is the-academy running on port 8056?
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Total Courses</p>
          <p className="text-2xl font-bold text-white">{totalCourses}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Enrolments</p>
          <p className="text-2xl font-bold text-violet-400">{totalEnrolments}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Create */}
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4 space-y-3">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2"><Plus size={14} className="text-violet-400" /> New Course</h2>
          <input
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder="Course title"
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-violet-500"
          />
          <input
            value={category}
            onChange={e => setCategory(e.target.value)}
            placeholder="Category (optional)"
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-violet-500"
          />
          <select
            value={difficulty}
            onChange={e => setDifficulty(e.target.value)}
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-violet-500"
          >
            <option value="beginner">Beginner</option>
            <option value="intermediate">Intermediate</option>
            <option value="advanced">Advanced</option>
          </select>
          <button
            onClick={createCourse}
            disabled={creating || !title.trim()}
            className="w-full flex items-center justify-center gap-1.5 rounded-lg bg-violet-600 hover:bg-violet-700 disabled:opacity-50 px-4 py-1.5 text-xs text-white font-medium transition-colors"
          >
            <Plus size={11} /> {creating ? 'Creating…' : 'Create'}
          </button>
          {createMsg && <p className="text-xs text-emerald-400">{createMsg}</p>}
        </div>

        {/* Course list */}
        <div className="md:col-span-2 rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2 mb-3"><BookOpen size={14} className="text-violet-400" /> Courses</h2>
          {courses.length === 0 ? (
            <p className="text-xs text-slate-500">No courses yet</p>
          ) : (
            <div className="space-y-2">
              {courses.map(c => (
                <div key={c.id} className="flex items-center justify-between gap-2 py-2 border-b border-slate-800 last:border-0">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-slate-200 truncate">{c.title}</p>
                    <p className="text-xs text-slate-500">{c.category ?? 'Uncategorised'}</p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {c.difficulty && <span className={`text-xs ${DIFF_COLORS[c.difficulty] ?? 'text-slate-400'}`}>{c.difficulty}</span>}
                    <span className={`text-xs ${c.published ? 'text-emerald-400' : 'text-slate-500'}`}>
                      {c.published ? 'published' : 'draft'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
