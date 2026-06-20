/**
 * PlatformPulse — real-time living status widget.
 *
 * A "cell cluster" visualization: each service is a nano-cell that pulses
 * with its health state. Uses useReactiveQuery for adaptive polling with
 * exponential backoff on failure.
 *
 * Technologies encoded:
 *  - Fluidic: CSS liquidic morph on hover
 *  - DNA pulse: animation for active cells
 *  - Cluster layout: auto-reflow grid
 *  - Reactive: live polling, stale-while-revalidate
 *  - Nano-dot: status indicators
 *  - Adaptive: backoff on failures
 */
import React from 'react'
import useReactiveQuery from '../../hooks/useReactiveQuery'

const API = (import.meta.env.VITE_API_URL as string | undefined) ?? ''

interface ServiceCell {
  name: string
  status: 'ok' | 'degraded' | 'unreachable' | 'unknown'
  latency_ms?: number
  port?: number
}

interface PlatformHealth {
  overall: 'healthy' | 'degraded' | 'critical' | 'unknown'
  services: ServiceCell[]
  timestamp: string
}

function statusClass(s: ServiceCell['status']): string {
  switch (s) {
    case 'ok':          return 'ux-nano-dot--ok'
    case 'degraded':    return 'ux-nano-dot--warn'
    case 'unreachable': return 'ux-nano-dot--critical'
    default:            return 'ux-nano-dot--unknown'
  }
}

function badgeAttr(s: ServiceCell['status']): string {
  switch (s) {
    case 'ok':          return 'ok'
    case 'degraded':    return 'warn'
    case 'unreachable': return 'critical'
    default:            return 'unknown'
  }
}

export function PlatformPulse({ className = '' }: { className?: string }) {
  const { data, loading, error, lastFetched, invalidate } = useReactiveQuery<PlatformHealth>({
    url: `${API}/health/platform`,
    intervalMs: 20_000,
    transform: (raw) => {
      // Normalise whatever shape the backend returns
      if (raw && typeof raw === 'object' && 'services' in (raw as object)) {
        return raw as PlatformHealth
      }
      return { overall: 'unknown', services: [], timestamp: '' }
    },
  })

  const overallColor =
    data?.overall === 'healthy'  ? 'text-emerald-400' :
    data?.overall === 'degraded' ? 'text-amber-400'   :
    data?.overall === 'critical' ? 'text-red-400'      :
    'text-slate-500'

  return (
    <div className={`rounded-xl border border-slate-700/60 bg-slate-900/70 p-4 ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className={`ux-nano-dot ${data?.overall === 'healthy' ? 'ux-nano-dot--ok ux-pulse-dna' : 'ux-nano-dot--unknown'}`} />
          <h3 className="text-sm font-semibold text-white">Platform Pulse</h3>
        </div>
        <div className="flex items-center gap-2">
          {loading && <span className="text-xs text-slate-500">syncing…</span>}
          <button
            onClick={invalidate}
            className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
            aria-label="Refresh platform health"
          >
            ↻
          </button>
        </div>
      </div>

      {/* Overall status */}
      {data && (
        <p className={`text-xs font-medium uppercase tracking-widest mb-3 ${overallColor}`}>
          ● {data.overall}
        </p>
      )}

      {/* Service cells cluster */}
      {error ? (
        <p className="text-xs text-red-400">{error}</p>
      ) : data?.services?.length ? (
        <div className="ux-cluster" style={{'--ux-cluster-min': '120px'} as React.CSSProperties}>
          {data.services.map((svc) => (
            <div
              key={svc.name}
              className="ux-liquid ux-card-raised rounded-lg px-3 py-2 bg-slate-800/60"
            >
              <div className="flex items-center gap-1.5 mb-1">
                <span className={`ux-nano-dot ${statusClass(svc.status)}`} />
                <span
                  className="text-xs font-medium text-slate-200 truncate"
                  data-status={badgeAttr(svc.status)}
                >
                  {svc.name}
                </span>
              </div>
              {svc.latency_ms != null && (
                <p className="text-xs text-slate-500 tabular-nums">{Math.round(svc.latency_ms)}ms</p>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="ux-cluster" style={{'--ux-cluster-min': '90px'} as React.CSSProperties}>
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="ux-shimmer rounded-lg h-12" />
          ))}
        </div>
      )}

      {lastFetched && (
        <p className="text-xs text-slate-600 mt-3 text-right">
          {lastFetched.toLocaleTimeString()}
        </p>
      )}
    </div>
  )
}

export default PlatformPulse
