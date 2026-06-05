/**
 * StatusPage — real-time health of all Trancendos workers and CF services.
 * Polls /health on each service, falls back to graceful "unknown" state.
 */

import React, { useEffect, useState, useCallback } from 'react'
import { RefreshCw, CheckCircle, XCircle, AlertCircle, Loader } from 'lucide-react'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const CF_BASE = 'https://luminous-aimastermind.workers.dev'

type HealthStatus = 'ok' | 'degraded' | 'down' | 'unknown'

interface ServiceHealth {
  name: string
  url: string
  status: HealthStatus
  latencyMs?: number
  provider?: string
  details?: string
  lastChecked?: string
}

const SERVICES: Pick<ServiceHealth, 'name' | 'url'>[] = [
  // Self-hosted workers
  { name: 'API Gateway',         url: `${API}/health` },
  { name: 'AI Gateway',          url: `${API.replace(':8000', ':8009')}/health` },
  { name: 'Infinity Auth',       url: `${API.replace(':8000', ':8005')}/health` },
  { name: 'Infinity Portal',     url: `${API.replace(':8000', ':8042')}/health` },
  { name: 'Infinity One',        url: `${API.replace(':8000', ':8043')}/health` },
  { name: 'Infinity Admin',      url: `${API.replace(':8000', ':8044')}/health` },
  { name: 'Infinity Bridge',     url: `${API.replace(':8000', ':8070')}/health` },
  { name: 'Infinity WebSocket',  url: `${API.replace(':8000', ':8004')}/health` },
  { name: 'Users Service',       url: `${API.replace(':8000', ':8006')}/health` },
  { name: 'Monitoring',          url: `${API.replace(':8000', ':8007')}/health` },
  { name: 'Notifications',       url: `${API.replace(':8000', ':8008')}/health` },
  { name: 'The Digital Grid',    url: `${API.replace(':8000', ':8010')}/health` },
  { name: 'Products Service',    url: `${API.replace(':8000', ':8011')}/health` },
  { name: 'Orders Service',      url: `${API.replace(':8000', ':8012')}/health` },
  { name: 'Payments Service',    url: `${API.replace(':8000', ':8013')}/health` },
  { name: 'Search Service',      url: `${API.replace(':8000', ':8024')}/health` },
  { name: 'Queue Service',       url: `${API.replace(':8000', ':8027')}/health` },
  { name: 'Vault Service',       url: `${API.replace(':8000', ':8038')}/health` },
  // Cloudflare Workers
  { name: 'CF: tranc3-ai',           url: `https://tranc3-ai.${CF_BASE.split('workers.dev')[0].replace('https://', '')}workers.dev/health` },
  { name: 'CF: tranc3-notifications', url: `https://tranc3-notifications.luminous-aimastermind.workers.dev/health` },
  { name: 'CF: tranc3-storage',      url: `https://tranc3-storage.luminous-aimastermind.workers.dev/health` },
  { name: 'CF: tranc3-search',       url: `https://tranc3-search.luminous-aimastermind.workers.dev/health` },
  { name: 'CF: tranc3-queue',        url: `https://tranc3-queue.luminous-aimastermind.workers.dev/health` },
]

const CF_AI_STATUS_URL = 'https://tranc3-ai.luminous-aimastermind.workers.dev/api/v1/ai/status'

async function checkHealth(url: string): Promise<{ status: HealthStatus; latencyMs: number; details?: string }> {
  const t0 = performance.now()
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(5000) })
    const latencyMs = Math.round(performance.now() - t0)
    if (res.ok) {
      const body = await res.json().catch(() => ({}))
      return {
        status: body.status === 'degraded' ? 'degraded' : 'ok',
        latencyMs,
        details: body.provider || body.version || undefined,
      }
    }
    return { status: 'down', latencyMs, details: `HTTP ${res.status}` }
  } catch (e: unknown) {
    const latencyMs = Math.round(performance.now() - t0)
    const msg = e instanceof Error ? e.message : 'unreachable'
    return { status: 'unknown', latencyMs, details: msg.includes('timeout') ? 'timeout' : 'unreachable' }
  }
}

function StatusBadge({ status }: { status: HealthStatus }) {
  if (status === 'ok')      return <CheckCircle size={16} className="text-green-400" />
  if (status === 'degraded') return <AlertCircle size={16} className="text-yellow-400" />
  if (status === 'down')    return <XCircle size={16} className="text-red-400" />
  return <AlertCircle size={16} className="text-gray-500" />
}

function statusColor(s: HealthStatus) {
  if (s === 'ok')       return 'text-green-400'
  if (s === 'degraded') return 'text-yellow-400'
  if (s === 'down')     return 'text-red-400'
  return 'text-gray-500'
}

export default function StatusPage() {
  const [services, setServices] = useState<ServiceHealth[]>(
    SERVICES.map((s) => ({ ...s, status: 'unknown' as HealthStatus }))
  )
  const [aiProviders, setAiProviders] = useState<Record<string, unknown> | null>(null)
  const [checking, setChecking] = useState(false)
  const [lastRun, setLastRun] = useState<string | null>(null)

  const runChecks = useCallback(async () => {
    setChecking(true)
    const results = await Promise.all(
      SERVICES.map(async (svc) => {
        const { status, latencyMs, details } = await checkHealth(svc.url)
        return {
          ...svc,
          status,
          latencyMs,
          details,
          lastChecked: new Date().toISOString(),
        }
      })
    )
    setServices(results)

    // Also fetch AI rotation status
    try {
      const r = await fetch(CF_AI_STATUS_URL, { signal: AbortSignal.timeout(5000) })
      if (r.ok) setAiProviders(await r.json())
    } catch { /* ignore */ }

    setLastRun(new Date().toLocaleTimeString())
    setChecking(false)
  }, [])

  useEffect(() => {
    runChecks()
    const interval = setInterval(runChecks, 30_000)
    return () => clearInterval(interval)
  }, [runChecks])

  const ok = services.filter((s) => s.status === 'ok').length
  const down = services.filter((s) => s.status === 'down').length
  const degraded = services.filter((s) => s.status === 'degraded').length
  const unknown = services.filter((s) => s.status === 'unknown').length

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Platform Status</h1>
          <p className="text-gray-400 text-sm mt-1">
            {lastRun ? `Last checked: ${lastRun}` : 'Checking…'}
          </p>
        </div>
        <button
          onClick={runChecks}
          disabled={checking}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg text-sm text-white transition-colors"
        >
          <RefreshCw size={14} className={checking ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        {[
          { label: 'Online',   count: ok,       color: 'border-green-500 text-green-400' },
          { label: 'Degraded', count: degraded, color: 'border-yellow-500 text-yellow-400' },
          { label: 'Down',     count: down,     color: 'border-red-500 text-red-400' },
          { label: 'Unknown',  count: unknown,  color: 'border-gray-600 text-gray-400' },
        ].map(({ label, count, color }) => (
          <div key={label} className={`bg-gray-900 border ${color} rounded-lg p-4`}>
            <div className={`text-3xl font-bold ${color.split(' ')[1]}`}>{count}</div>
            <div className="text-gray-400 text-sm mt-1">{label}</div>
          </div>
        ))}
      </div>

      {/* Service list */}
      <div className="bg-gray-900 rounded-lg border border-gray-700 overflow-hidden mb-6">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-700">
              <th className="text-left px-4 py-3 text-gray-400 font-medium">Service</th>
              <th className="text-left px-4 py-3 text-gray-400 font-medium">Status</th>
              <th className="text-left px-4 py-3 text-gray-400 font-medium">Latency</th>
              <th className="text-left px-4 py-3 text-gray-400 font-medium">Details</th>
            </tr>
          </thead>
          <tbody>
            {services.map((svc) => (
              <tr key={svc.name} className="border-b border-gray-800 hover:bg-gray-800/50">
                <td className="px-4 py-3 text-gray-200 font-medium">{svc.name}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    {checking && svc.status === 'unknown'
                      ? <Loader size={16} className="text-gray-500 animate-spin" />
                      : <StatusBadge status={svc.status} />
                    }
                    <span className={`capitalize ${statusColor(svc.status)}`}>{svc.status}</span>
                  </div>
                </td>
                <td className="px-4 py-3 text-gray-400">
                  {svc.latencyMs != null ? `${svc.latencyMs}ms` : '—'}
                </td>
                <td className="px-4 py-3 text-gray-500 text-xs truncate max-w-xs">
                  {svc.details || '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* AI Provider Rotation Status */}
      {aiProviders && (
        <div className="bg-gray-900 rounded-lg border border-gray-700 p-4">
          <h2 className="text-white font-semibold mb-3 flex items-center gap-2">
            AI Provider Rotation
            <span className="text-xs text-gray-500 font-normal">tranc3-ai Cloudflare Worker</span>
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {Object.entries(aiProviders as Record<string, unknown>).map(([id, info]) => {
              const p = info as { name?: string; used?: number; limit?: number; pct?: number; active?: boolean }
              const pct = p.pct ?? 0
              return (
                <div key={id} className="bg-gray-800 rounded p-3">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-gray-200 text-xs font-medium">{p.name || id}</span>
                    <span className={`text-xs ${p.active ? 'text-green-400' : 'text-gray-500'}`}>
                      {p.active ? 'active' : 'full'}
                    </span>
                  </div>
                  <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${
                        pct > 90 ? 'bg-red-500' : pct > 70 ? 'bg-yellow-500' : 'bg-indigo-500'
                      }`}
                      style={{ width: `${Math.min(pct, 100)}%` }}
                    />
                  </div>
                  <div className="text-gray-500 text-xs mt-1">
                    {p.used ?? 0} / {p.limit ?? '?'} today
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
