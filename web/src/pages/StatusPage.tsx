/**
 * StatusPage — real-time health of all Trancendos workers and CF services.
 * Polls /health on each service, falls back to graceful "unknown" state.
 */

import React, { useEffect, useState, useCallback } from 'react'
import { RefreshCw, CheckCircle, XCircle, AlertCircle, Loader } from 'lucide-react'

const API    = import.meta.env.VITE_API_URL || 'http://localhost:8000'
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

const STATUS_CONFIG: Record<HealthStatus, { icon: React.ReactNode; label: string; color: string }> = {
  ok:       { icon: <CheckCircle size={16} aria-hidden="true" />, label: 'Online',   color: 'text-green-400' },
  degraded: { icon: <AlertCircle size={16} aria-hidden="true" />, label: 'Degraded', color: 'text-yellow-400' },
  down:     { icon: <XCircle     size={16} aria-hidden="true" />, label: 'Down',     color: 'text-red-400' },
  unknown:  { icon: <AlertCircle size={16} aria-hidden="true" />, label: 'Unknown',  color: 'text-gray-500' },
}

function StatusBadge({ status, checking }: { status: HealthStatus; checking?: boolean }) {
  if (checking && status === 'unknown') {
    return (
      <span className="inline-flex items-center gap-1.5 text-gray-400" aria-label="Checking">
        <Loader size={16} aria-hidden="true" className="animate-spin" />
        <span className="capitalize">Checking</span>
      </span>
    )
  }
  const { icon, label, color } = STATUS_CONFIG[status]
  return (
    <span className={`inline-flex items-center gap-1.5 ${color}`} aria-label={label}>
      {icon}
      <span className="capitalize">{label}</span>
    </span>
  )
}

const SUMMARY_ITEMS = [
  { key: 'ok'      as HealthStatus, label: 'Online',   border: 'border-green-500',  text: 'text-green-400' },
  { key: 'degraded'as HealthStatus, label: 'Degraded', border: 'border-yellow-500', text: 'text-yellow-400' },
  { key: 'down'    as HealthStatus, label: 'Down',     border: 'border-red-500',    text: 'text-red-400' },
  { key: 'unknown' as HealthStatus, label: 'Unknown',  border: 'border-gray-600',   text: 'text-gray-400' },
]

export default function StatusPage() {
  const [services, setServices]     = useState<ServiceHealth[]>(
    SERVICES.map(s => ({ ...s, status: 'unknown' as HealthStatus }))
  )
  const [aiProviders, setAiProviders] = useState<Record<string, unknown> | null>(null)
  const [checking, setChecking]     = useState(false)
  const [lastRun, setLastRun]       = useState<string | null>(null)

  const runChecks = useCallback(async () => {
    setChecking(true)
    const results = await Promise.all(
      SERVICES.map(async svc => {
        const { status, latencyMs, details } = await checkHealth(svc.url)
        return { ...svc, status, latencyMs, details, lastChecked: new Date().toISOString() }
      })
    )
    setServices(results)

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

  const counts = SUMMARY_ITEMS.reduce<Record<string, number>>((acc, item) => {
    acc[item.key] = services.filter(s => s.status === item.key).length
    return acc
  }, {})

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Live status announcer */}
      <div role="status" aria-live="polite" aria-atomic="true" className="sr-only">
        {lastRun
          ? `Health check complete at ${lastRun}. ${counts['ok']} online, ${counts['down']} down, ${counts['degraded']} degraded.`
          : 'Checking service health…'}
      </div>

      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Platform Status</h1>
          <p className="text-gray-400 text-sm mt-1" aria-live="polite">
            {lastRun ? `Last checked: ${lastRun}` : 'Checking…'}
          </p>
        </div>
        <button
          onClick={runChecks}
          disabled={checking}
          aria-label={checking ? 'Refreshing health checks' : 'Refresh health checks'}
          aria-busy={checking}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg text-sm text-white transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
        >
          <RefreshCw size={14} aria-hidden="true" className={checking ? 'animate-spin' : ''} />
          {checking ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {/* Summary stats */}
      <div
        className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6"
        role="list"
        aria-label="Service health summary"
      >
        {SUMMARY_ITEMS.map(({ key, label, border, text }) => (
          <div
            key={key}
            role="listitem"
            aria-label={`${counts[key]} ${label}`}
            className={`bg-gray-900 border ${border} rounded-lg p-4`}
          >
            <div className={`text-3xl font-bold tabular-nums ${text}`} aria-hidden="true">
              {counts[key]}
            </div>
            <div className="text-gray-400 text-sm mt-1">{label}</div>
          </div>
        ))}
      </div>

      {/* Service table */}
      <div className="bg-gray-900 rounded-lg border border-gray-700 overflow-hidden mb-6">
        <table
          className="w-full text-sm"
          aria-label="Individual service health checks"
          aria-busy={checking}
        >
          <thead>
            <tr className="border-b border-gray-700">
              <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Service</th>
              <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Status</th>
              <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Latency</th>
              <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Details</th>
            </tr>
          </thead>
          <tbody>
            {services.map(svc => (
              <tr key={svc.name} className="border-b border-gray-800 hover:bg-gray-800/50">
                <td className="px-4 py-3 text-gray-200 font-medium">{svc.name}</td>
                <td className="px-4 py-3">
                  <StatusBadge status={svc.status} checking={checking} />
                </td>
                <td className="px-4 py-3 text-gray-400 tabular-nums">
                  {svc.latencyMs != null
                    ? <span aria-label={`${svc.latencyMs} milliseconds`}>{svc.latencyMs}ms</span>
                    : <span aria-label="Not yet measured">—</span>}
                </td>
                <td className="px-4 py-3 text-gray-500 text-xs truncate max-w-xs">
                  {svc.details || '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* AI Provider Rotation */}
      {aiProviders && (
        <section aria-labelledby="ai-providers-heading">
          <div className="bg-gray-900 rounded-lg border border-gray-700 p-4">
            <h2 id="ai-providers-heading" className="text-white font-semibold mb-3 flex items-center gap-2">
              AI Provider Rotation
              <span className="text-xs text-gray-500 font-normal">tranc3-ai Cloudflare Worker</span>
            </h2>
            <div
              className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3"
              role="list"
              aria-label="AI provider usage"
            >
              {Object.entries(aiProviders as Record<string, unknown>).map(([id, info]) => {
                const p = info as { name?: string; used?: number; limit?: number; pct?: number; active?: boolean }
                const pct = p.pct ?? 0
                const used  = p.used ?? 0
                const limit = p.limit ?? '?'
                const barColor = pct > 90 ? 'bg-red-500' : pct > 70 ? 'bg-yellow-500' : 'bg-indigo-500'
                return (
                  <div
                    key={id}
                    role="listitem"
                    aria-label={`${p.name || id}: ${used} of ${limit} requests used today${p.active ? ', currently active' : ''}`}
                    className="bg-gray-800 rounded p-3"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-gray-200 text-xs font-medium">{p.name || id}</span>
                      <span
                        aria-hidden="true"
                        className={`text-xs ${p.active ? 'text-green-400' : 'text-gray-500'}`}
                      >
                        {p.active ? 'active' : 'full'}
                      </span>
                    </div>
                    <div
                      role="progressbar"
                      aria-valuenow={Math.round(pct)}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-label={`${Math.round(pct)}% capacity used`}
                      className="h-1.5 bg-gray-700 rounded-full overflow-hidden"
                    >
                      <div
                        className={`h-full rounded-full transition-all ${barColor}`}
                        style={{ width: `${Math.min(pct, 100)}%` }}
                        aria-hidden="true"
                      />
                    </div>
                    <div className="text-gray-500 text-xs mt-1" aria-hidden="true">
                      {used} / {limit} today
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </section>
      )}
    </div>
  )
}
