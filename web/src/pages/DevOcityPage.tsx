import React, { useCallback, useEffect, useState } from 'react'
import { Boxes, RefreshCw, CheckCircle, XCircle, Clock, AlertCircle } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const DEV_API = '/devocity-svc'
const INTERNAL = { 'X-Internal-Secret': 'dev-secret' }

interface Project {
  id: number
  name: string
  description: string
  repo_url: string
  language: string
  status: string
  owner: string
  tags: string
  created_at: number
}

interface Deploy {
  id: number
  project_id: number
  environment: string
  version: string
  status: string
  triggered_by: string
  duration_s: number | null
  deployed_at: number
}

interface Service {
  id: number
  name: string
  description: string
  owner: string
  port: number
  health_url: string
  status: string
}

interface Stats {
  total_projects: number
  active_projects: number
  total_deploys: number
  successful_deploys: number
  deploy_success_rate: number
  by_environment: { environment: string; c: number }[]
}

const PROJECT_STATUS: Record<string, string> = {
  active:   'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  paused:   'bg-amber-500/20 text-amber-300 border-amber-500/30',
  archived: 'bg-slate-700/40 text-slate-400 border-slate-600/30',
}

const DEPLOY_STATUS_ICON: Record<string, React.ReactNode> = {
  success: <CheckCircle size={13} className="text-emerald-400" />,
  failed:  <XCircle size={13} className="text-red-400" />,
  running: <Clock size={13} className="text-amber-400" />,
  pending: <AlertCircle size={13} className="text-slate-400" />,
}

const LANG_COLORS: Record<string, string> = {
  python:     'bg-blue-500/20 text-blue-300',
  typescript: 'bg-cyan-500/20 text-cyan-300',
  javascript: 'bg-yellow-500/20 text-yellow-300',
  go:         'bg-teal-500/20 text-teal-300',
  rust:       'bg-orange-500/20 text-orange-300',
}

export default function DevOcityPage() {
  const { trackPageView } = useAnalytics()
  const [stats, setStats] = useState<Stats | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [deploys, setDeploys] = useState<Deploy[]>([])
  const [services, setServices] = useState<Service[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<'projects' | 'deploys' | 'services'>('projects')
  const [statusFilter, setStatusFilter] = useState('')

  useEffect(() => { trackPageView('/devocity') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const search = new URLSearchParams({ limit: '50' })
      if (statusFilter) search.set('status', statusFilter)
      const [hRes, stRes, pRes, dRes, svcRes] = await Promise.all([
        fetch(`${DEV_API}/health`),
        fetch(`${DEV_API}/stats`, { headers: INTERNAL }),
        fetch(`${DEV_API}/projects?${search.toString()}`, { headers: INTERNAL }),
        fetch(`${DEV_API}/deploys?limit=30`, { headers: INTERNAL }),
        fetch(`${DEV_API}/services`, { headers: INTERNAL }),
      ])
      if (!hRes.ok) throw new Error('DevOcity service unavailable')
      const [st, p, d, svc] = await Promise.all([
        stRes.ok ? stRes.json() : null,
        pRes.ok ? pRes.json() : null,
        dRes.ok ? dRes.json() : null,
        svcRes.ok ? svcRes.json() : [],
      ])
      if (st) setStats(st)
      if (p) setProjects(p.projects ?? [])
      if (d) setDeploys(d.deploys ?? [])
      setServices(Array.isArray(svc) ? svc : [])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => { loadData() }, [loadData])

  const fmt = (ts: number) => {
    try { return new Date(ts * 1000).toLocaleString() } catch { return String(ts) }
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Boxes size={22} className="text-slate-400" /> DevOcity
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Development operations hub — project registry, deploy events, service catalogue</p>
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
          {error} — is devocity-service running on port 8062?
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Active Projects</p>
          <p className="text-2xl font-bold text-emerald-400">{stats?.active_projects ?? '—'}</p>
          <p className="text-xs text-slate-500 mt-0.5">of {stats?.total_projects ?? '—'} total</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Total Deploys</p>
          <p className="text-2xl font-bold text-white">{stats?.total_deploys ?? '—'}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Success Rate</p>
          <p className={`text-2xl font-bold ${(stats?.deploy_success_rate ?? 0) >= 80 ? 'text-emerald-400' : 'text-amber-400'}`}>
            {stats?.deploy_success_rate !== undefined ? `${stats.deploy_success_rate}%` : '—'}
          </p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Services</p>
          <p className="text-2xl font-bold text-indigo-400">{services.length}</p>
        </div>
      </div>

      {/* Deploy env breakdown */}
      {stats && stats.by_environment.length > 0 && (
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <h2 className="text-sm font-semibold text-white mb-3">Deploys by Environment</h2>
          <div className="flex flex-wrap gap-2">
            {stats.by_environment.map(({ environment: env, c }) => (
              <span key={env} className="text-xs px-2 py-1 rounded bg-slate-800 text-slate-300 border border-slate-700/60">
                {env}: <span className="font-bold text-white">{c}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Tabs */}
      <div>
        <div className="flex gap-2 mb-4">
          {(['projects', 'deploys', 'services'] as const).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${tab === t ? 'bg-indigo-600 text-white' : 'bg-slate-800 text-slate-400 hover:text-white'}`}
            >
              {t === 'projects' ? `Projects (${projects.length})` : t === 'deploys' ? `Deploys (${deploys.length})` : `Services (${services.length})`}
            </button>
          ))}
        </div>

        {tab === 'projects' && (
          <div className="space-y-2">
            <div className="flex gap-2 mb-3">
              <select
                value={statusFilter}
                onChange={e => setStatusFilter(e.target.value)}
                className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:outline-none"
              >
                <option value="">All statuses</option>
                <option value="active">Active</option>
                <option value="paused">Paused</option>
                <option value="archived">Archived</option>
              </select>
            </div>
            {loading ? (
              <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-8 text-center text-slate-500 text-sm">Loading…</div>
            ) : projects.length === 0 ? (
              <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-8 text-center text-slate-500 text-sm">No projects registered.</div>
            ) : projects.map(p => (
              <div key={p.id} className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4 flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-medium text-slate-200">{p.name}</p>
                    <span className={`text-xs px-1.5 py-0.5 rounded border ${PROJECT_STATUS[p.status] ?? 'bg-slate-700/40 text-slate-400 border-slate-600/30'}`}>{p.status}</span>
                    {p.language && (
                      <span className={`text-xs px-1.5 py-0.5 rounded ${LANG_COLORS[p.language.toLowerCase()] ?? 'bg-slate-700/40 text-slate-300'}`}>{p.language}</span>
                    )}
                  </div>
                  {p.description && <p className="text-xs text-slate-500 mt-0.5">{p.description}</p>}
                  <p className="text-xs text-slate-600 mt-1">owner: {p.owner} · created {fmt(p.created_at)}</p>
                </div>
                {p.repo_url && (
                  <a href={p.repo_url} target="_blank" rel="noreferrer" className="text-xs text-indigo-400 hover:underline ml-4 shrink-0">repo →</a>
                )}
              </div>
            ))}
          </div>
        )}

        {tab === 'deploys' && (
          <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 overflow-hidden">
            {loading ? (
              <div className="p-8 text-center text-slate-500 text-sm">Loading…</div>
            ) : deploys.length === 0 ? (
              <div className="p-8 text-center text-slate-500 text-sm">No deploy events recorded.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-700/60 text-xs text-slate-500 uppercase tracking-wider">
                      <th className="text-left px-4 py-2">Status</th>
                      <th className="text-left px-4 py-2">Project</th>
                      <th className="text-left px-4 py-2">Env</th>
                      <th className="text-left px-4 py-2">Version</th>
                      <th className="text-left px-4 py-2">By</th>
                      <th className="text-right px-4 py-2">Duration</th>
                      <th className="text-right px-4 py-2">When</th>
                    </tr>
                  </thead>
                  <tbody>
                    {deploys.map(d => (
                      <tr key={d.id} className="border-b border-slate-800 hover:bg-slate-800/30 transition-colors">
                        <td className="px-4 py-2.5">
                          <div className="flex items-center gap-1.5">
                            {DEPLOY_STATUS_ICON[d.status] ?? null}
                            <span className="text-xs text-slate-300">{d.status}</span>
                          </div>
                        </td>
                        <td className="px-4 py-2.5 text-xs text-slate-400">#{d.project_id}</td>
                        <td className="px-4 py-2.5 text-xs text-indigo-300">{d.environment}</td>
                        <td className="px-4 py-2.5 text-xs text-slate-400 font-mono">{d.version}</td>
                        <td className="px-4 py-2.5 text-xs text-slate-500">{d.triggered_by}</td>
                        <td className="px-4 py-2.5 text-right text-xs text-slate-500">
                          {d.duration_s != null ? `${d.duration_s.toFixed(1)}s` : '—'}
                        </td>
                        <td className="px-4 py-2.5 text-right text-xs text-slate-500 whitespace-nowrap">{fmt(d.deployed_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {tab === 'services' && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {loading ? (
              <div className="col-span-2 rounded-xl border border-slate-700/60 bg-slate-900/70 p-8 text-center text-slate-500 text-sm">Loading…</div>
            ) : services.length === 0 ? (
              <div className="col-span-2 rounded-xl border border-slate-700/60 bg-slate-900/70 p-8 text-center text-slate-500 text-sm">No services in catalogue.</div>
            ) : services.map(s => (
              <div key={s.id} className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
                <div className="flex items-center justify-between mb-1">
                  <p className="text-sm font-medium text-slate-200">{s.name}</p>
                  <span className={`text-xs px-1.5 py-0.5 rounded ${s.status === 'healthy' ? 'text-emerald-400 bg-emerald-500/10' : 'text-slate-400 bg-slate-700/40'}`}>{s.status}</span>
                </div>
                {s.description && <p className="text-xs text-slate-500 mb-1">{s.description}</p>}
                <p className="text-xs text-slate-600">port {s.port} · {s.owner}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
