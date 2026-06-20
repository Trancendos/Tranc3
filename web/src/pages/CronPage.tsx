import React, { useCallback, useEffect, useState } from 'react'
import { Clock, RefreshCw, Play, CheckCircle, XCircle, AlertCircle } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const CRON_API = '/cron-svc'
const INTERNAL = { 'X-Internal-Secret': 'dev-secret' }

interface Job {
  id: string
  name: string
  schedule: string
  url: string
  method: string
  enabled: number
  created_at: number
}

interface JobRun {
  id: string
  job_id: string
  started_at: number
  finished_at: number | null
  status: string
  response_code: number | null
  error: string | null
}

export default function CronPage() {
  const { trackPageView } = useAnalytics()
  const [jobs, setJobs] = useState<Job[]>([])
  const [runs, setRuns] = useState<JobRun[]>([])
  const [totalJobs, setTotalJobs] = useState(0)
  const [activeJobs, setActiveJobs] = useState(0)
  const [loading, setLoading] = useState(true)
  const [runsLoading, setRunsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedJob, setSelectedJob] = useState<string | null>(null)
  const [triggerMsg, setTriggerMsg] = useState<string | null>(null)
  const [enabledOnly, setEnabledOnly] = useState(false)

  useEffect(() => { trackPageView('/cron') }, [trackPageView])

  const loadJobs = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [hRes, jRes] = await Promise.all([
        fetch(`${CRON_API}/health`),
        fetch(`${CRON_API}/jobs${enabledOnly ? '?enabled=true' : ''}`, { headers: INTERNAL }),
      ])
      if (!hRes.ok || !jRes.ok) throw new Error('Service unavailable')
      const [h, j] = await Promise.all([hRes.json(), jRes.json()])
      setTotalJobs(h.total_jobs ?? 0)
      setActiveJobs(h.active_jobs ?? 0)
      setJobs(j.jobs ?? [])
      if (!selectedJob && j.jobs?.length > 0) setSelectedJob(j.jobs[0].id)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [selectedJob, enabledOnly])

  useEffect(() => { loadJobs() }, [loadJobs])

  const loadRuns = useCallback(async () => {
    if (!selectedJob) return
    setRunsLoading(true)
    try {
      const r = await fetch(`${CRON_API}/jobs/${selectedJob}/runs?limit=20`, { headers: INTERNAL })
      if (r.ok) {
        const data = await r.json()
        setRuns(data.runs ?? [])
      }
    } catch { /* ignore */ } finally {
      setRunsLoading(false)
    }
  }, [selectedJob])

  useEffect(() => { loadRuns() }, [loadRuns])

  const triggerJob = async (jobId: string) => {
    setTriggerMsg(null)
    try {
      const r = await fetch(`${CRON_API}/jobs/${jobId}/trigger`, {
        method: 'POST',
        headers: INTERNAL,
      })
      const data = await r.json()
      setTriggerMsg(r.ok ? `Triggered: ${data.message ?? 'queued'}` : `Error: ${data.detail ?? 'failed'}`)
    } catch {
      setTriggerMsg('Error: request failed')
    }
  }

  const fmt = (ts: number) => {
    try { return new Date(ts * 1000).toLocaleString() } catch { return String(ts) }
  }

  const STATUS_ICON: Record<string, React.ReactNode> = {
    success: <CheckCircle size={14} className="text-emerald-400" />,
    error:   <XCircle size={14} className="text-red-400" />,
    running: <AlertCircle size={14} className="text-amber-400 animate-pulse" />,
  }

  const selectedJobData = jobs.find(j => j.id === selectedJob)

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Clock size={22} className="text-slate-400" /> ChronosSphere
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Task, time & scheduling management — cron job registry</p>
        </div>
        <button
          onClick={loadJobs}
          disabled={loading}
          className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-300 hover:text-white disabled:opacity-50 transition-colors"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-lg bg-red-500/10 border border-red-500/30 px-4 py-3 text-sm text-red-300">
          {error} — is cron-service running on port 8021?
        </div>
      )}

      {triggerMsg && (
        <div className={`rounded-lg border px-4 py-3 text-sm ${triggerMsg.startsWith('Error') ? 'bg-red-500/10 border-red-500/30 text-red-300' : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'}`}>
          {triggerMsg}
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Total Jobs</p>
          <p className="text-2xl font-bold text-white">{totalJobs}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Active Jobs</p>
          <p className="text-2xl font-bold text-emerald-400">{activeJobs}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Disabled Jobs</p>
          <p className="text-2xl font-bold text-slate-400">{totalJobs - activeJobs}</p>
        </div>
      </div>

      {/* Filter */}
      <div className="flex items-center gap-3">
        <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
          <input
            type="checkbox"
            checked={enabledOnly}
            onChange={e => setEnabledOnly(e.target.checked)}
            className="rounded"
          />
          Show enabled only
        </label>
      </div>

      {/* Two-column: job list + runs */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        {/* Job list */}
        <div className="lg:col-span-2 rounded-xl border border-slate-700/60 bg-slate-900/70 overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-700/60">
            <h2 className="text-sm font-semibold text-white">Scheduled Jobs</h2>
          </div>
          {loading ? (
            <div className="p-4 text-center text-slate-500 text-xs">Loading…</div>
          ) : jobs.length === 0 ? (
            <div className="p-4 text-center text-slate-500 text-xs">No jobs found.</div>
          ) : (
            <ul className="py-1">
              {jobs.map(job => (
                <li key={job.id}>
                  <button
                    onClick={() => setSelectedJob(job.id)}
                    className={`w-full flex items-start gap-3 px-4 py-3 text-left transition-colors ${
                      selectedJob === job.id
                        ? 'bg-indigo-600/30 text-white border-r-2 border-indigo-500'
                        : 'text-slate-400 hover:bg-slate-800 hover:text-white'
                    }`}
                  >
                    <span className={`ux-nano-dot mt-1.5 flex-shrink-0 ${job.enabled ? 'ux-nano-dot--ok' : 'ux-nano-dot--unknown'}`} />
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">{job.name}</p>
                      <p className="text-xs font-mono text-slate-500 mt-0.5">{job.schedule}</p>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Job detail + runs */}
        <div className="lg:col-span-3 space-y-4">
          {selectedJobData && (
            <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-white">{selectedJobData.name}</h2>
                <button
                  onClick={() => triggerJob(selectedJobData.id)}
                  className="flex items-center gap-1.5 rounded-lg border border-indigo-600/50 bg-indigo-600/20 px-3 py-1.5 text-xs text-indigo-300 hover:bg-indigo-600/30 transition-colors"
                >
                  <Play size={11} /> Trigger Now
                </button>
              </div>
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <p className="text-slate-500 mb-0.5">Schedule</p>
                  <p className="font-mono text-slate-200">{selectedJobData.schedule}</p>
                </div>
                <div>
                  <p className="text-slate-500 mb-0.5">Method</p>
                  <p className="font-mono text-slate-200">{selectedJobData.method}</p>
                </div>
                <div className="col-span-2">
                  <p className="text-slate-500 mb-0.5">Target URL</p>
                  <p className="font-mono text-slate-300 truncate">{selectedJobData.url}</p>
                </div>
                <div>
                  <p className="text-slate-500 mb-0.5">Status</p>
                  <span className={`text-xs px-1.5 py-0.5 rounded border ${selectedJobData.enabled ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' : 'bg-slate-700/40 text-slate-400 border-slate-600/30'}`}>
                    {selectedJobData.enabled ? 'enabled' : 'disabled'}
                  </span>
                </div>
                <div>
                  <p className="text-slate-500 mb-0.5">Created</p>
                  <p className="text-slate-300">{fmt(selectedJobData.created_at)}</p>
                </div>
              </div>
            </div>
          )}

          <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-700/60 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-white">Recent Runs</h2>
              <span className="text-xs text-slate-500">{runs.length} runs</span>
            </div>
            {runsLoading ? (
              <div className="p-6 text-center text-slate-500 text-sm">Loading runs…</div>
            ) : !selectedJob ? (
              <div className="p-6 text-center text-slate-500 text-sm">Select a job.</div>
            ) : runs.length === 0 ? (
              <div className="p-6 text-center text-slate-500 text-sm">No runs yet.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-700/60 text-xs text-slate-500 uppercase tracking-wider">
                      <th className="text-left px-4 py-2">Status</th>
                      <th className="text-left px-4 py-2">Started</th>
                      <th className="text-right px-4 py-2">Code</th>
                      <th className="text-left px-4 py-2">Error</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map(run => (
                      <tr key={run.id} className="border-b border-slate-800 hover:bg-slate-800/30 transition-colors">
                        <td className="px-4 py-2.5">
                          <div className="flex items-center gap-1.5">
                            {STATUS_ICON[run.status] ?? <AlertCircle size={14} className="text-slate-500" />}
                            <span className="text-xs text-slate-300">{run.status}</span>
                          </div>
                        </td>
                        <td className="px-4 py-2.5 text-xs text-slate-400 whitespace-nowrap">{fmt(run.started_at)}</td>
                        <td className="px-4 py-2.5 text-right text-xs text-slate-500">{run.response_code ?? '—'}</td>
                        <td className="px-4 py-2.5 text-xs text-red-400 max-w-xs truncate">{run.error ?? ''}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
