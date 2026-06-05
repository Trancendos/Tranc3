import React, { useEffect, useState, useCallback } from 'react'
import { ListTodo, RefreshCw, Play, Pause, Trash2, CheckCircle, Clock, XCircle } from 'lucide-react'

const CF_QUEUE_URL = 'https://tranc3-queue.luminous-aimastermind.workers.dev'
const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface QueueStats {
  name: string
  provider: string
  depth: number
  inFlight: number
  processed: number
  failed: number
  status: 'ok' | 'degraded' | 'down' | 'unknown'
  note?: string
}

const QUEUES: QueueStats[] = [
  { name: 'CF Queues', provider: 'cloudflare-queues', depth: 0, inFlight: 0, processed: 0, failed: 0, status: 'unknown', note: '100K operations/day free' },
  { name: 'Upstash Redis', provider: 'upstash', depth: 0, inFlight: 0, processed: 0, failed: 0, status: 'unknown', note: '10K requests/day free tier' },
  { name: 'KV Queue', provider: 'cf-kv', depth: 0, inFlight: 0, processed: 0, failed: 0, status: 'unknown', note: '100K reads + 1K writes/day free' },
]

interface Job {
  id: string
  type: string
  status: 'pending' | 'running' | 'done' | 'failed'
  created: string
  payload?: string
  error?: string
}

function statusIcon(s: Job['status']) {
  if (s === 'done') return <CheckCircle size={14} className="text-green-400" />
  if (s === 'running') return <Play size={14} className="text-indigo-400" />
  if (s === 'failed') return <XCircle size={14} className="text-red-400" />
  return <Clock size={14} className="text-gray-400" />
}

function queueStatusColor(s: QueueStats['status']) {
  if (s === 'ok') return 'text-green-400'
  if (s === 'degraded') return 'text-yellow-400'
  if (s === 'down') return 'text-red-400'
  return 'text-gray-500'
}

export default function QueuePage() {
  const [queues, setQueues] = useState<QueueStats[]>(QUEUES)
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(false)
  const [lastRun, setLastRun] = useState<string | null>(null)

  const fetchStatus = useCallback(async () => {
    setLoading(true)
    const endpoints = [
      `${CF_QUEUE_URL}/health`,
      `${API.replace(':8000', ':8027')}/health`,
    ]

    for (const url of endpoints) {
      try {
        const r = await fetch(url, { signal: AbortSignal.timeout(5000) })
        if (r.ok) {
          const body = await r.json().catch(() => ({}))
          if (body.queues) {
            setQueues((prev) =>
              prev.map((q, i) => ({ ...q, ...(body.queues[i] ?? {}) }))
            )
          }
          if (body.jobs) setJobs(body.jobs)
          break
        }
      } catch { /* try next */ }
    }
    setLastRun(new Date().toLocaleTimeString())
    setLoading(false)
  }, [])

  useEffect(() => {
    fetchStatus()
    const iv = setInterval(fetchStatus, 15_000)
    return () => clearInterval(iv)
  }, [fetchStatus])

  const totalDepth = queues.reduce((a, q) => a + q.depth, 0)
  const totalProcessed = queues.reduce((a, q) => a + q.processed, 0)
  const totalFailed = queues.reduce((a, q) => a + q.failed, 0)

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <ListTodo size={22} className="text-indigo-400" />
            Queue
          </h1>
          <p className="text-gray-400 text-sm mt-1">
            The HIVE task queue — zero-cost rotation
            {lastRun ? ` · ${lastRun}` : ''}
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
      <div className="grid grid-cols-3 gap-4 mb-6">
        {[
          { label: 'Pending', value: totalDepth, color: 'text-yellow-400 border-yellow-700' },
          { label: 'Processed', value: totalProcessed, color: 'text-green-400 border-green-700' },
          { label: 'Failed', value: totalFailed, color: 'text-red-400 border-red-700' },
        ].map(({ label, value, color }) => (
          <div key={label} className={`bg-gray-900 border ${color} rounded-lg p-4`}>
            <div className={`text-3xl font-bold ${color.split(' ')[0]}`}>{value}</div>
            <div className="text-gray-400 text-sm mt-1">{label}</div>
          </div>
        ))}
      </div>

      {/* Queue backends */}
      <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden mb-6">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-700">
              <th className="text-left px-4 py-3 text-gray-400 font-medium">Provider</th>
              <th className="text-right px-4 py-3 text-gray-400 font-medium">Depth</th>
              <th className="text-right px-4 py-3 text-gray-400 font-medium">In Flight</th>
              <th className="text-right px-4 py-3 text-gray-400 font-medium">Processed</th>
              <th className="text-right px-4 py-3 text-gray-400 font-medium">Failed</th>
              <th className="text-left px-4 py-3 text-gray-400 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {queues.map((q) => (
              <tr key={q.name} className="border-b border-gray-800 hover:bg-gray-800/50">
                <td className="px-4 py-3">
                  <p className="text-gray-200 font-medium">{q.name}</p>
                  {q.note && <p className="text-gray-600 text-xs">{q.note}</p>}
                </td>
                <td className="px-4 py-3 text-right text-yellow-400">{q.depth}</td>
                <td className="px-4 py-3 text-right text-indigo-400">{q.inFlight}</td>
                <td className="px-4 py-3 text-right text-green-400">{q.processed}</td>
                <td className="px-4 py-3 text-right text-red-400">{q.failed}</td>
                <td className={`px-4 py-3 text-sm capitalize ${queueStatusColor(q.status)}`}>
                  {q.status}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Recent jobs */}
      {jobs.length > 0 && (
        <div>
          <h2 className="text-white font-semibold mb-3">Recent Jobs</h2>
          <div className="space-y-2">
            {jobs.map((j) => (
              <div key={j.id} className="bg-gray-900 border border-gray-700 rounded-lg px-4 py-3 flex items-center gap-3">
                {statusIcon(j.status)}
                <div className="flex-1 min-w-0">
                  <p className="text-gray-200 text-sm truncate">{j.type}</p>
                  {j.error && <p className="text-red-400 text-xs truncate">{j.error}</p>}
                </div>
                <span className="text-gray-600 text-xs whitespace-nowrap">
                  {new Date(j.created).toLocaleTimeString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
