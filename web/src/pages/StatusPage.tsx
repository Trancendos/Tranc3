/**
 * StatusPage — real-time health of all Trancendos workers.
 * Uses the health-aggregator (port 8029) for a single bulk status call,
 * eliminating 23 individual cross-origin requests.
 */

import React, { useEffect, useState, useCallback } from 'react'
import { RefreshCw, CheckCircle, XCircle, AlertCircle, Loader } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

type HealthStatus = 'ok' | 'degraded' | 'down' | 'unknown'

interface ServiceHealth {
  name: string
  port: number
  status: HealthStatus
  latencyMs?: number
  details?: string
  lastChecked?: string
}

interface AiProviderInfo { status: string; available: boolean; utilisation_pct: number; daily_req: string }
interface AiDashboard { active_provider: string; zero_cost_operational: boolean; providers: Record<string, AiProviderInfo> }

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
        <span>Checking</span>
      </span>
    )
  }
  const { icon, label, color } = STATUS_CONFIG[status]
  return (
    <span className={`inline-flex items-center gap-1.5 ${color}`} aria-label={label}>
      {icon}
      <span>{label}</span>
    </span>
  )
}

const SUMMARY_ITEMS = [
  { key: 'ok'       as HealthStatus, label: 'Online',   border: 'border-green-500',  text: 'text-green-400' },
  { key: 'degraded' as HealthStatus, label: 'Degraded', border: 'border-yellow-500', text: 'text-yellow-400' },
  { key: 'down'     as HealthStatus, label: 'Down',     border: 'border-red-500',    text: 'text-red-400' },
  { key: 'unknown'  as HealthStatus, label: 'Unknown',  border: 'border-gray-600',   text: 'text-gray-400' },
]

export default function StatusPage() {
  const [services, setServices]       = useState<ServiceHealth[]>([])
  const [aiProviders, setAiProviders] = useState<AiDashboard | null>(null)
  const [checking, setChecking]       = useState(false)
  const [lastRun, setLastRun]         = useState<string | null>(null)
  const [aggDown, setAggDown]         = useState(false)
  const { trackPageView } = useAnalytics()

  useEffect(() => { trackPageView('/status') }, [trackPageView])

  const runChecks = useCallback(async () => {
    setChecking(true)
    setAggDown(false)
    try {
      const resp = await fetch('/health-agg/status', { signal: AbortSignal.timeout(6000) })
      if (resp.ok) {
        const body = await resp.json() as {
          services?: Array<{ name: string; port: number; status: string; latency_ms?: number }>
        }
        const svcs: ServiceHealth[] = (body.services ?? []).map((s) => ({
          name: s.name,
          port: s.port,
          status: (
            s.status === 'healthy'  ? 'ok' :
            s.status === 'degraded' ? 'degraded' :
            s.status === 'down'     ? 'down' : 'unknown'
          ) as HealthStatus,
          latencyMs: s.latency_ms != null ? Math.round(s.latency_ms) : undefined,
          lastChecked: new Date().toISOString(),
        }))
        setServices(svcs)
      } else {
        setAggDown(true)
      }
    } catch {
      setAggDown(true)
    }

    // Fetch AI provider data separately (proxied via /api → :8000 or direct aggregator response)
    try {
      const r = await fetch('/health-agg/status/infinity-ai', { signal: AbortSignal.timeout(4000) })
      if (r.ok) {
        const detail = await r.json()
        const providers = detail?.current?.details?.providers
        if (providers) {
          setAiProviders({
            active_provider: detail?.current?.details?.active_provider ?? '',
            zero_cost_operational: detail?.current?.details?.zero_cost_operational ?? true,
            providers,
          })
        }
      }
    } catch { /* AI provider detail optional */ }

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
      <div role="status" aria-live="polite" aria-atomic="true" className="sr-only">
        {lastRun
          ? `Health check complete at ${lastRun}. ${counts['ok'] ?? 0} online, ${counts['down'] ?? 0} down.`
          : 'Checking service health…'}
      </div>

      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Platform Status</h1>
          <p className="text-gray-400 text-sm mt-1" aria-live="polite">
            {lastRun ? `Last checked: ${lastRun} · via health-aggregator` : 'Checking…'}
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

      {aggDown && (
        <div role="alert" className="mb-4 p-3 bg-yellow-900/30 border border-yellow-700 rounded-lg text-yellow-300 text-sm">
          Health-aggregator (port 8029) is unreachable. Start the stack with{' '}
          <code className="font-mono bg-gray-800 px-1 rounded">docker compose up health-aggregator</code>{' '}
          or{' '}
          <code className="font-mono bg-gray-800 px-1 rounded">make dev-api</code>.
        </div>
      )}

      <div
        className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6"
        role="list"
        aria-label="Service health summary"
      >
        {SUMMARY_ITEMS.map(({ key, label, border, text }) => (
          <div
            key={key}
            role="listitem"
            aria-label={`${counts[key] ?? 0} ${label}`}
            className={`bg-gray-900 border ${border} rounded-lg p-4`}
          >
            <div className={`text-3xl font-bold tabular-nums ${text}`} aria-hidden="true">
              {counts[key] ?? 0}
            </div>
            <div className="text-gray-400 text-sm mt-1">{label}</div>
          </div>
        ))}
      </div>

      {services.length > 0 ? (
        <div className="bg-gray-900 rounded-lg border border-gray-700 overflow-hidden mb-6">
          <table
            className="w-full text-sm"
            aria-label="Individual service health checks"
            aria-busy={checking}
          >
            <thead>
              <tr className="border-b border-gray-700">
                <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Service</th>
                <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Port</th>
                <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Status</th>
                <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Latency</th>
              </tr>
            </thead>
            <tbody>
              {services.map(svc => (
                <tr key={`${svc.name}-${svc.port}`} className="border-b border-gray-800 hover:bg-gray-800/50">
                  <td className="px-4 py-3 text-gray-200 font-medium">{svc.name}</td>
                  <td className="px-4 py-3 text-gray-500 font-mono text-xs">{svc.port}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={svc.status} checking={checking} />
                  </td>
                  <td className="px-4 py-3 text-gray-400 tabular-nums text-xs">
                    {svc.latencyMs != null
                      ? <span aria-label={`${svc.latencyMs} milliseconds`}>{svc.latencyMs}ms</span>
                      : <span aria-label="Not yet measured">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : !aggDown && (
        <div className="bg-gray-900 rounded-lg border border-gray-700 p-8 text-center text-gray-500 mb-6">
          {checking ? 'Polling health-aggregator…' : 'No services reported yet.'}
        </div>
      )}

      {aiProviders && (
        <section aria-labelledby="ai-providers-heading">
          <div className="bg-gray-900 rounded-lg border border-gray-700 p-4">
            <h2 id="ai-providers-heading" className="text-white font-semibold mb-3 flex items-center gap-2">
              AI Provider Rotation
              <span className="text-xs text-gray-500 font-normal">infinity-ai · :8009</span>
              {aiProviders.zero_cost_operational
                ? <span className="text-xs text-emerald-400">● operational</span>
                : <span className="text-xs text-red-400">● offline mode</span>}
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3" role="list">
              {Object.entries(aiProviders.providers).map(([id, info]) => {
                const pct = info.utilisation_pct ?? 0
                const isActive = id === aiProviders.active_provider
                const barColor = pct > 90 ? 'bg-red-500' : pct > 70 ? 'bg-yellow-500' : 'bg-indigo-500'
                return (
                  <div
                    key={id}
                    role="listitem"
                    className={`bg-gray-800 rounded p-3 ${isActive ? 'ring-1 ring-indigo-500/50' : ''}`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-gray-200 text-xs font-medium capitalize">{id}</span>
                      <span className={`text-xs ${isActive ? 'text-green-400' : info.available ? 'text-gray-400' : 'text-red-400'}`}>
                        {isActive ? 'active' : info.available ? 'ready' : info.status}
                      </span>
                    </div>
                    <div
                      role="progressbar"
                      aria-valuenow={Math.round(pct)}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      className="h-1.5 bg-gray-700 rounded-full overflow-hidden"
                    >
                      <div className={`h-full rounded-full transition-all ${barColor}`} style={{ width: `${Math.min(pct, 100)}%` }} />
                    </div>
                    <div className="text-gray-500 text-xs mt-1">{info.daily_req} today</div>
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
