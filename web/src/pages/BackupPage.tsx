import React, { useCallback, useEffect, useState } from 'react'
import { Archive, RefreshCw, CheckCircle, XCircle, AlertTriangle, Play } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const BACKUP_API = '/backup-svc'
const INTERNAL = { 'X-Internal-Secret': 'dev-secret', 'Content-Type': 'application/json' }

interface WorkerStatus {
  worker: string
  last_backup: string | null
  age_hours: number | null
  rpo_hours: number
  rpo_breached: boolean
  backup_count: number
  last_size_bytes: number | null
  healthy: boolean
}

interface BackupStatus {
  total_workers: number
  healthy: number
  degraded: number
  health_pct: number
  workers: WorkerStatus[]
}

interface RpoStatus {
  total_workers: number
  rpo_compliant: number
  rpo_breached: number
  breached_workers: WorkerStatus[]
}

interface BackupFile {
  worker: string
  path: string
  size_bytes: number
  created_at: string
}

function fmtBytes(b: number) {
  if (b < 1024) return `${b}B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)}KB`
  return `${(b / 1024 / 1024).toFixed(2)}MB`
}

export default function BackupPage() {
  const { trackPageView } = useAnalytics()
  const [status, setStatus] = useState<BackupStatus | null>(null)
  const [rpo, setRpo] = useState<RpoStatus | null>(null)
  const [backups, setBackups] = useState<BackupFile[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [runMsg, setRunMsg] = useState('')

  useEffect(() => { trackPageView('/backup') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [hRes, stRes, rpoRes, listRes] = await Promise.all([
        fetch(`${BACKUP_API}/health`),
        fetch(`${BACKUP_API}/status`, { headers: INTERNAL }),
        fetch(`${BACKUP_API}/rpo-status`, { headers: INTERNAL }),
        fetch(`${BACKUP_API}/list`, { headers: INTERNAL }),
      ])
      if (!hRes.ok) throw new Error('Backup service unavailable')
      const [st, rp, ls] = await Promise.all([
        stRes.ok ? stRes.json() : null,
        rpoRes.ok ? rpoRes.json() : null,
        listRes.ok ? listRes.json() : null,
      ])
      if (st) setStatus(st)
      if (rp) setRpo(rp)
      if (ls) setBackups(ls.backups ?? [])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const runAll = async () => {
    setRunning(true)
    setRunMsg('')
    try {
      const res = await fetch(`${BACKUP_API}/run-all`, { method: 'POST', headers: INTERNAL })
      if (res.ok) {
        const d = await res.json()
        setRunMsg(`Backup complete: ${d.success}/${d.total} succeeded`)
        setTimeout(() => setRunMsg(''), 5000)
        loadData()
      }
    } catch { /* ignore */ }
    finally { setRunning(false) }
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Archive size={22} className="text-slate-400" /> Backup Service
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Platform-wide SQLite backup with RPO monitoring and verification</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={runAll}
            disabled={running}
            className="flex items-center gap-1.5 rounded-lg border border-emerald-700 bg-emerald-900/40 px-3 py-1.5 text-xs text-emerald-300 hover:bg-emerald-900/70 disabled:opacity-50 transition-colors"
          >
            <Play size={12} className={running ? 'animate-pulse' : ''} /> Backup All
          </button>
          <button
            onClick={loadData}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-300 hover:text-white disabled:opacity-50 transition-colors"
          >
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg bg-red-500/10 border border-red-500/30 px-4 py-3 text-sm text-red-300">
          {error} — is backup-service running on port 8039?
        </div>
      )}
      {runMsg && (
        <div className="rounded-lg bg-emerald-500/10 border border-emerald-500/30 px-4 py-3 text-sm text-emerald-300">
          {runMsg}
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Total Workers</p>
          <p className="text-2xl font-bold text-white">{status?.total_workers ?? '—'}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Healthy</p>
          <p className="text-2xl font-bold text-emerald-400">{status?.healthy ?? '—'}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Health</p>
          <p className={`text-2xl font-bold ${(status?.health_pct ?? 0) >= 80 ? 'text-emerald-400' : 'text-amber-400'}`}>
            {status?.health_pct !== undefined ? `${status.health_pct}%` : '—'}
          </p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">RPO Breaches</p>
          <p className={`text-2xl font-bold ${(rpo?.rpo_breached ?? 0) > 0 ? 'text-red-400' : 'text-slate-300'}`}>
            {rpo?.rpo_breached ?? '—'}
          </p>
        </div>
      </div>

      {/* RPO breaches */}
      {rpo && rpo.rpo_breached > 0 && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-4">
          <h2 className="text-sm font-semibold text-red-300 mb-3 flex items-center gap-2">
            <AlertTriangle size={14} /> RPO Breaches ({rpo.rpo_breached})
          </h2>
          <div className="space-y-2">
            {rpo.breached_workers.map(w => (
              <div key={w.worker} className="flex items-center justify-between text-xs">
                <span className="text-slate-300 font-mono">{w.worker}</span>
                <span className="text-red-400">
                  {w.age_hours != null ? `${w.age_hours.toFixed(1)}h ago` : 'never'} (RPO: {w.rpo_hours}h)
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Worker status table */}
      {status && status.workers.length > 0 && (
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-700/60">
            <h2 className="text-sm font-semibold text-white">Worker Backup Status</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700/60 text-xs text-slate-500 uppercase tracking-wider">
                  <th className="text-left px-4 py-2">Worker</th>
                  <th className="text-left px-4 py-2">Health</th>
                  <th className="text-right px-4 py-2">Backups</th>
                  <th className="text-right px-4 py-2">Last Size</th>
                  <th className="text-right px-4 py-2">Age</th>
                  <th className="text-right px-4 py-2">RPO</th>
                </tr>
              </thead>
              <tbody>
                {status.workers.map(w => (
                  <tr key={w.worker} className="border-b border-slate-800 hover:bg-slate-800/30 transition-colors">
                    <td className="px-4 py-2.5 text-xs font-mono text-slate-300">{w.worker}</td>
                    <td className="px-4 py-2.5">
                      {w.healthy
                        ? <CheckCircle size={13} className="text-emerald-400" />
                        : <XCircle size={13} className="text-red-400" />}
                    </td>
                    <td className="px-4 py-2.5 text-right text-xs text-slate-400">{w.backup_count}</td>
                    <td className="px-4 py-2.5 text-right text-xs text-slate-500">
                      {w.last_size_bytes != null ? fmtBytes(w.last_size_bytes) : '—'}
                    </td>
                    <td className="px-4 py-2.5 text-right text-xs text-slate-500">
                      {w.age_hours != null ? `${w.age_hours.toFixed(1)}h` : 'never'}
                    </td>
                    <td className={`px-4 py-2.5 text-right text-xs font-medium ${w.rpo_breached ? 'text-red-400' : 'text-emerald-400'}`}>
                      {w.rpo_breached ? '⚠ breach' : '✓ ok'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Recent backup files */}
      {backups.length > 0 && (
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <h2 className="text-sm font-semibold text-white mb-3">Recent Backup Files ({backups.length})</h2>
          <div className="space-y-1.5">
            {backups.slice(0, 20).map((b, i) => (
              <div key={i} className="flex items-center justify-between text-xs">
                <span className="text-indigo-300 font-mono truncate max-w-xs">{b.path}</span>
                <div className="flex items-center gap-3 ml-2">
                  <span className="text-slate-500">{fmtBytes(b.size_bytes)}</span>
                  <span className="text-slate-600 whitespace-nowrap">{b.created_at}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
