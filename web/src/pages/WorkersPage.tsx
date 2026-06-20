import React, { useEffect, useState, useCallback } from 'react'
import { Server, RefreshCw, CheckCircle, XCircle, AlertCircle } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface Worker {
  name: string
  port: number
  priority: 'P0' | 'P1' | 'P2' | 'P3'
  path: string
  status: 'ok' | 'degraded' | 'down' | 'unknown'
  latencyMs?: number
  uptime?: string
}

const WORKERS: Worker[] = [
  { name: 'API Gateway',           port: 8000, priority: 'P0', path: '/', status: 'unknown' },
  { name: 'Infinity WebSocket',    port: 8004, priority: 'P0', path: 'workers/infinity-ws', status: 'unknown' },
  { name: 'Infinity Auth',         port: 8005, priority: 'P0', path: 'workers/infinity-auth', status: 'unknown' },
  { name: 'AI Gateway',            port: 8009, priority: 'P0', path: 'workers/infinity-ai', status: 'unknown' },
  { name: 'Users Service',         port: 8006, priority: 'P1', path: 'workers/users-service', status: 'unknown' },
  { name: 'Monitoring',            port: 8007, priority: 'P1', path: 'workers/monitoring', status: 'unknown' },
  { name: 'Notifications',         port: 8008, priority: 'P1', path: 'workers/notifications', status: 'unknown' },
  { name: 'Infinity Portal',       port: 8042, priority: 'P1', path: 'workers/infinity-portal-service', status: 'unknown' },
  { name: 'Infinity One',          port: 8043, priority: 'P1', path: 'workers/infinity-one-service', status: 'unknown' },
  { name: 'Infinity Admin',        port: 8044, priority: 'P1', path: 'workers/infinity-admin-service', status: 'unknown' },
  { name: 'Infinity Bridge',       port: 8070, priority: 'P1', path: 'workers/infinity-bridge-service', status: 'unknown' },
  { name: 'The Digital Grid',      port: 8010, priority: 'P2', path: 'workers/the-grid', status: 'unknown' },
  { name: 'Products Service',      port: 8011, priority: 'P2', path: 'workers/products-service', status: 'unknown' },
  { name: 'Orders Service',        port: 8012, priority: 'P2', path: 'workers/orders-service', status: 'unknown' },
  { name: 'Payments Service',      port: 8013, priority: 'P2', path: 'workers/payments-service', status: 'unknown' },
  { name: 'Search Service',        port: 8024, priority: 'P3', path: 'workers/search-service', status: 'unknown' },
  { name: 'Queue Service',         port: 8027, priority: 'P3', path: 'workers/queue-service', status: 'unknown' },
  { name: 'Vault Service',         port: 8038, priority: 'P3', path: 'workers/vault-service', status: 'unknown' },
]

const PRIORITY_COLORS: Record<Worker['priority'], string> = {
  P0: 'bg-red-900/40 text-red-400 border-red-700',
  P1: 'bg-orange-900/40 text-orange-400 border-orange-700',
  P2: 'bg-yellow-900/40 text-yellow-400 border-yellow-700',
  P3: 'bg-gray-800 text-gray-400 border-gray-600',
}

const STATUS_LABEL: Record<Worker['status'], string> = {
  ok: 'Online',
  degraded: 'Degraded',
  down: 'Down',
  unknown: 'Unknown',
}

function StatusIcon({ status }: { status: Worker['status'] }) {
  const label = STATUS_LABEL[status]
  if (status === 'ok')       return <CheckCircle size={14} aria-hidden="true" className="text-green-400" />
  if (status === 'degraded') return <AlertCircle size={14} aria-hidden="true" className="text-yellow-400" />
  if (status === 'down')     return <XCircle     size={14} aria-hidden="true" className="text-red-400" />
  return                            <AlertCircle size={14} aria-hidden="true" className="text-gray-600" />
}

const FILTERS = ['all', 'P0', 'P1', 'P2', 'P3'] as const
type Filter = typeof FILTERS[number]

export default function WorkersPage() {
  const [workers, setWorkers] = useState<Worker[]>(WORKERS)
  const [checking, setChecking] = useState(false)
  const [lastRun, setLastRun] = useState<string | null>(null)
  const [filter, setFilter] = useState<Filter>('all')
  const { trackWorkerRefresh } = useAnalytics()

  const checkAll = useCallback(async () => {
    setChecking(true)
    const results = await Promise.all(
      WORKERS.map(async (w) => {
        const t0 = performance.now()
        const url = `${API.replace(':8000', `:${w.port}`)}/health`
        try {
          const r = await fetch(url, { signal: AbortSignal.timeout(4000) })
          const latencyMs = Math.round(performance.now() - t0)
          if (r.ok) {
            const body = await r.json().catch(() => ({}))
            return { ...w, status: (body.status === 'degraded' ? 'degraded' : 'ok') as Worker['status'], latencyMs }
          }
          return { ...w, status: 'down' as Worker['status'], latencyMs }
        } catch {
          return { ...w, status: 'unknown' as Worker['status'], latencyMs: Math.round(performance.now() - t0) }
        }
      })
    )
    setWorkers(results)
    setLastRun(new Date().toLocaleTimeString())
    setChecking(false)
    trackWorkerRefresh(results.length)
  }, [trackWorkerRefresh])

  useEffect(() => {
    checkAll()
    const iv = setInterval(checkAll, 30_000)
    return () => clearInterval(iv)
  }, [checkAll])

  const visible = filter === 'all' ? workers : workers.filter((w) => w.priority === filter)
  const ok   = workers.filter((w) => w.status === 'ok').length
  const down = workers.filter((w) => w.status === 'down').length

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Live announcer */}
      <div role="status" aria-live="polite" aria-atomic="true" className="sr-only">
        {lastRun
          ? `Health check complete at ${lastRun}. ${ok} of ${workers.length} workers online.`
          : 'Checking worker health…'}
      </div>

      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Server size={22} aria-hidden="true" className="text-indigo-400" />
            Workers
          </h1>
          <p className="text-gray-400 text-sm mt-1">
            Self-hosted FastAPI workers · {ok}/{workers.length} online
            {lastRun ? ` · ${lastRun}` : ''}
          </p>
        </div>
        <button
          onClick={checkAll}
          disabled={checking}
          aria-busy={checking}
          aria-label={checking ? 'Checking all workers' : 'Check all workers'}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg text-sm text-white transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
        >
          <RefreshCw size={14} aria-hidden="true" className={checking ? 'animate-spin' : ''} />
          {checking ? 'Checking…' : 'Check All'}
        </button>
      </div>

      {/* Priority filter */}
      <div role="group" aria-label="Filter by priority" className="flex gap-2 mb-5 flex-wrap">
        {FILTERS.map((p) => (
          <button
            key={p}
            onClick={() => setFilter(p)}
            aria-pressed={filter === p}
            className={`px-3 py-1.5 rounded-md text-xs font-medium border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 ${
              filter === p
                ? 'bg-indigo-600 text-white border-indigo-500'
                : 'bg-gray-900 text-gray-400 border-gray-700 hover:border-gray-500'
            }`}
          >
            {p === 'all' ? 'All' : p}
          </button>
        ))}
      </div>

      {/* Workers table */}
      <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden">
        <table className="w-full text-sm" aria-label="Worker service health" aria-busy={checking}>
          <thead>
            <tr className="border-b border-gray-700">
              <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Service</th>
              <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Priority</th>
              <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Port</th>
              <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Status</th>
              <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Latency</th>
              <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Path</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((w) => (
              <tr key={w.name} className="border-b border-gray-800 hover:bg-gray-800/50">
                <td className="px-4 py-3 text-gray-200 font-medium">{w.name}</td>
                <td className="px-4 py-3">
                  <span className={`text-xs border rounded-full px-2 py-0.5 ${PRIORITY_COLORS[w.priority]}`}>
                    {w.priority}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-500 font-mono text-xs">{w.port}</td>
                <td className="px-4 py-3">
                  <div
                    className="flex items-center gap-1.5"
                    aria-label={`${w.name}: ${STATUS_LABEL[w.status]}`}
                  >
                    <StatusIcon status={w.status} />
                    <span className={`capitalize text-xs ${
                      w.status === 'ok'       ? 'text-green-400' :
                      w.status === 'degraded' ? 'text-yellow-400' :
                      w.status === 'down'     ? 'text-red-400' : 'text-gray-500'
                    }`}>{STATUS_LABEL[w.status]}</span>
                  </div>
                </td>
                <td className="px-4 py-3 text-gray-400 text-xs tabular-nums">
                  {w.latencyMs != null
                    ? <span aria-label={`${w.latencyMs} milliseconds`}>{w.latencyMs}ms</span>
                    : <span aria-label="Not yet measured">—</span>}
                </td>
                <td className="px-4 py-3 text-gray-600 text-xs font-mono">{w.path}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {down > 0 && (
        <p className="text-yellow-500 text-xs mt-3" role="note">
          {down} worker{down > 1 ? 's are' : ' is'} down — start with{' '}
          <code className="font-mono bg-gray-800 px-1 rounded">make dev-api</code> or the Docker Compose stack.
        </p>
      )}
    </div>
  )
}
