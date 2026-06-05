import React, { useEffect, useState, useCallback } from 'react'
import { Database, RefreshCw, HardDrive, Cloud, Server } from 'lucide-react'

const CF_STORAGE_URL = 'https://tranc3-storage.luminous-aimastermind.workers.dev'

interface StoreBucket {
  id: string
  name: string
  provider: 'cloudflare-r2' | 'backblaze-b2' | 'oracle-storage' | 'ipfs' | 'local'
  usedBytes?: number
  limitBytes?: number
  files?: number
  status: 'ok' | 'degraded' | 'down' | 'unknown'
  note?: string
}

const BUCKETS: StoreBucket[] = [
  {
    id: 'cf-r2',
    name: 'Cloudflare R2',
    provider: 'cloudflare-r2',
    status: 'unknown',
    note: '10 GB free, 1M Class-B ops/month — no egress fees',
  },
  {
    id: 'b2',
    name: 'Backblaze B2',
    provider: 'backblaze-b2',
    status: 'unknown',
    note: '10 GB free, 2,500 download ops/day',
  },
  {
    id: 'oracle',
    name: 'Oracle Object Storage',
    provider: 'oracle-storage',
    status: 'unknown',
    note: '20 GB Always Free — permanent (card required)',
  },
  {
    id: 'ipfs',
    name: 'IPFS (self-hosted)',
    provider: 'ipfs',
    status: 'unknown',
    note: 'Docker volume — content-addressed, zero-cost on Oracle VM',
  },
]

function providerIcon(p: StoreBucket['provider']) {
  if (p === 'cloudflare-r2') return <Cloud size={16} className="text-orange-400" />
  if (p === 'ipfs') return <Server size={16} className="text-indigo-400" />
  return <Database size={16} className="text-blue-400" />
}

function fmtBytes(b: number) {
  if (b >= 1e9) return `${(b / 1e9).toFixed(2)} GB`
  if (b >= 1e6) return `${(b / 1e6).toFixed(1)} MB`
  return `${(b / 1e3).toFixed(0)} KB`
}

function statusBadge(s: StoreBucket['status']) {
  const map: Record<StoreBucket['status'], string> = {
    ok: 'bg-green-900/40 text-green-400 border-green-700',
    degraded: 'bg-yellow-900/40 text-yellow-400 border-yellow-700',
    down: 'bg-red-900/40 text-red-400 border-red-700',
    unknown: 'bg-gray-800 text-gray-500 border-gray-700',
  }
  return map[s]
}

export default function StoragePage() {
  const [buckets, setBuckets] = useState<StoreBucket[]>(BUCKETS)
  const [loading, setLoading] = useState(false)
  const [lastRun, setLastRun] = useState<string | null>(null)

  const fetchStatus = useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetch(`${CF_STORAGE_URL}/health`, { signal: AbortSignal.timeout(5000) })
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
            <HardDrive size={22} className="text-indigo-400" />
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
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg text-sm text-white transition-colors"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Refresh
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
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {buckets.map((b) => {
          const pct = b.usedBytes != null && b.limitBytes
            ? Math.round(b.usedBytes / b.limitBytes * 100)
            : null
          return (
            <div key={b.id} className="bg-gray-900 border border-gray-700 rounded-lg p-5">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  {providerIcon(b.provider)}
                  <span className="text-white font-medium">{b.name}</span>
                </div>
                <span className={`text-xs border rounded-full px-2 py-0.5 ${statusBadge(b.status)}`}>
                  {b.status}
                </span>
              </div>

              {pct != null && (
                <>
                  <div className="h-2 bg-gray-700 rounded-full overflow-hidden mb-1">
                    <div
                      className={`h-full rounded-full transition-all ${
                        pct > 90 ? 'bg-red-500' : pct > 70 ? 'bg-yellow-500' : 'bg-indigo-500'
                      }`}
                      style={{ width: `${Math.min(pct, 100)}%` }}
                    />
                  </div>
                  <p className="text-gray-500 text-xs mb-2">
                    {fmtBytes(b.usedBytes!)} / {fmtBytes(b.limitBytes!)} ({pct}%)
                    {b.files != null && ` · ${b.files.toLocaleString()} files`}
                  </p>
                </>
              )}

              {b.note && (
                <p className="text-gray-600 text-xs border-t border-gray-800 pt-2 mt-2">{b.note}</p>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
