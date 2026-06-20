import React, { useEffect, useState, useCallback } from 'react'
import { Database, RefreshCw, HardDrive, Cloud, Server, CheckCircle, AlertCircle, XCircle } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const _API = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'
const STORAGE_API = _API.replace(':8000', ':8026')

interface StoreBucket {
  id: string
  name: string
  provider: 'local' | 'ipfs' | 'oracle-storage'
  usedBytes?: number
  limitBytes?: number
  files?: number
  status: 'ok' | 'degraded' | 'down' | 'unknown'
  note?: string
}

const BUCKETS: StoreBucket[] = [
  {
    id: 'local',
    name: 'Local Volume (primary)',
    provider: 'local',
    status: 'unknown',
    note: 'Docker-managed volume · zero-cost · The Citadel self-hosted stack',
  },
  {
    id: 'ipfs',
    name: 'IPFS (content-addressed)',
    provider: 'ipfs',
    status: 'unknown',
    note: 'Distributed · content-addressed · zero-cost on self-hosted node',
  },
  {
    id: 'oracle',
    name: 'Oracle Object Storage',
    provider: 'oracle-storage',
    status: 'unknown',
    note: '20 GB Always Free cloud tier — overflow / off-site backup',
  },
]

const STATUS_META: Record<StoreBucket['status'], { label: string; icon: React.ReactNode; cls: string }> = {
  ok:       { label: 'Online',   icon: <CheckCircle size={12} aria-hidden="true" />, cls: 'bg-green-900/40 text-green-400 border-green-700' },
  degraded: { label: 'Degraded', icon: <AlertCircle size={12} aria-hidden="true" />, cls: 'bg-yellow-900/40 text-yellow-400 border-yellow-700' },
  down:     { label: 'Down',     icon: <XCircle     size={12} aria-hidden="true" />, cls: 'bg-red-900/40 text-red-400 border-red-700' },
  unknown:  { label: 'Unknown',  icon: <AlertCircle size={12} aria-hidden="true" />, cls: 'bg-gray-800 text-gray-500 border-gray-700' },
}

function providerIcon(p: StoreBucket['provider']) {
  if (p === 'ipfs')          return <Server    size={16} aria-hidden="true" className="text-indigo-400" />
  if (p === 'oracle-storage') return <Cloud    size={16} aria-hidden="true" className="text-blue-400" />
  return                             <HardDrive size={16} aria-hidden="true" className="text-emerald-400" />
}

function fmtBytes(b: number) {
  if (b >= 1e9) return `${(b / 1e9).toFixed(2)} GB`
  if (b >= 1e6) return `${(b / 1e6).toFixed(1)} MB`
  return `${(b / 1e3).toFixed(0)} KB`
}

export default function StoragePage() {
  const [buckets, setBuckets] = useState<StoreBucket[]>(BUCKETS)
  const [loading, setLoading] = useState(false)
  const [lastRun, setLastRun] = useState<string | null>(null)
  const { trackPageView } = useAnalytics()

  useEffect(() => { trackPageView('/storage') }, [trackPageView])

  const fetchStatus = useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetch(`${STORAGE_API}/health`, { signal: AbortSignal.timeout(5000) })
      if (r.ok) {
        const body = await r.json().catch(() => ({}))
        if (body.buckets) {
          setBuckets((prev) =>
            prev.map((b) => {
              const live = body.buckets[b.id]
              return live ? { ...b, ...live } : b
            })
          )
        }
      }
    } catch { /* show unknown state */ }
    setLastRun(new Date().toLocaleTimeString())
    setLoading(false)
  }, [])

  useEffect(() => {
    fetchStatus()
    const iv = setInterval(fetchStatus, 60_000)
    return () => clearInterval(iv)
  }, [fetchStatus])

  const totalUsed = buckets.reduce((acc, b) => acc + (b.usedBytes ?? 0), 0)

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <HardDrive size={22} aria-hidden="true" className="text-indigo-400" />
            Storage
          </h1>
          <p className="text-gray-400 text-sm mt-1">
            Zero-cost distributed storage across all providers
            {lastRun ? ` · Last checked: ${lastRun}` : ''}
          </p>
        </div>
        <button
          onClick={fetchStatus}
          disabled={loading}
          aria-busy={loading}
          aria-label={loading ? 'Refreshing storage status' : 'Refresh storage status'}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg text-sm text-white transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
        >
          <RefreshCw size={14} aria-hidden="true" className={loading ? 'animate-spin' : ''} />
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {/* Summary */}
      {totalUsed > 0 && (
        <div className="bg-gray-900 border border-gray-700 rounded-lg p-4 mb-6">
          <p className="text-gray-400 text-sm">Total used across all providers</p>
          <p className="text-2xl font-bold text-white">{fmtBytes(totalUsed)}</p>
        </div>
      )}

      {/* Buckets */}
      <ul className="grid grid-cols-1 md:grid-cols-2 gap-4 list-none" aria-label="Storage providers">
        {buckets.map((b) => {
          const pct = b.usedBytes != null && b.limitBytes
            ? Math.round(b.usedBytes / b.limitBytes * 100)
            : null
          const meta = STATUS_META[b.status]
          return (
            <li key={b.id}>
              <article
                aria-label={`${b.name} — ${meta.label}`}
                className="bg-gray-900 border border-gray-700 rounded-lg p-5 h-full"
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    {providerIcon(b.provider)}
                    <span className="text-white font-medium">{b.name}</span>
                  </div>
                  <span className={`flex items-center gap-1 text-xs border rounded-full px-2 py-0.5 ${meta.cls}`}>
                    {meta.icon}
                    {meta.label}
                  </span>
                </div>

                {pct != null && (
                  <>
                    <div
                      role="progressbar"
                      aria-valuenow={pct}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-label={`${b.name} storage: ${pct}% used`}
                      className="h-2 bg-gray-700 rounded-full overflow-hidden mb-1"
                    >
                      <div
                        aria-hidden="true"
                        className={`h-full rounded-full transition-all ${
                          pct > 90 ? 'bg-red-500' : pct > 70 ? 'bg-yellow-500' : 'bg-indigo-500'
                        }`}
                        style={{ width: `${Math.min(pct, 100)}%` }}
                      />
                    </div>
                    <p className="text-gray-500 text-xs mb-2" aria-hidden="true">
                      {fmtBytes(b.usedBytes!)} / {fmtBytes(b.limitBytes!)} ({pct}%)
                      {b.files != null && ` · ${b.files.toLocaleString()} files`}
                    </p>
                  </>
                )}

                {b.note && (
                  <p className="text-gray-600 text-xs border-t border-gray-800 pt-2 mt-2">{b.note}</p>
                )}
              </article>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
