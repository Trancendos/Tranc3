/**
 * AI Providers Dashboard — live view of zero-cost provider rotation.
 * Shows all 11 providers, their limits, utilisation, and hard-stop status.
 * Polls /ai/providers every 15s.
 */

import React, { useState, useEffect, useRef } from 'react'
import { AdaptiveCard } from '../components/ui/AdaptiveCard'
import { useAnalytics } from '../hooks/useAnalytics'

interface ProviderInfo {
  status: 'ok' | 'rotating' | 'hard_stop' | 'cooling_down' | 'unlimited'
  available: boolean
  utilisation_pct: number
  daily_req: string
  hourly_req: string
  consecutive_errors: number
}

interface Dashboard {
  active_provider: string
  available_providers: string[]
  rotating_providers: string[]
  hard_stopped_providers: string[]
  zero_cost_operational: boolean
  providers: Record<string, ProviderInfo>
}

const API = import.meta.env.VITE_API_URL ?? ''

const STATUS_EMOJI: Record<string, string> = {
  ok: '✅',
  rotating: '🔄',
  hard_stop: '🛑',
  cooling_down: '❄️',
  unlimited: '♾️',
}

const PROVIDER_LABELS: Record<string, string> = {
  ollama: 'Ollama (local)',
  groq: 'Groq LPU',
  cerebras: 'Cerebras RDU',
  openrouter: 'OpenRouter',
  huggingface: 'HuggingFace',
  together: 'Together AI',
  deepseek: 'DeepSeek',
  offline: 'Offline (stub)',
}

function UtilBar({ pct }: { pct: number }) {
  const colour =
    pct >= 95 ? 'bg-red-500'
    : pct >= 80 ? 'bg-amber-500'
    : 'bg-emerald-500'
  return (
    <div className="w-full bg-slate-800 rounded-full h-1.5 mt-1">
      <div
        className={`h-1.5 rounded-full transition-all duration-500 ${colour}`}
        style={{ width: `${Math.min(pct, 100)}%` }}
      />
    </div>
  )
}

export function AIProvidersPage() {
  const [data, setData] = useState<Dashboard | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)
  const { trackProviderSwitch } = useAnalytics()
  const prevProvider = useRef<string | null>(null)

  useEffect(() => {
    let active = true
    const fetchData = async () => {
      try {
        const res = await fetch(`${API}/ai/providers`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const json = await res.json()
        if (
          !json ||
          typeof json.active_provider !== 'string' ||
          typeof json.providers !== 'object'
        ) {
          throw new Error('Unexpected response shape from /ai/providers')
        }
        if (active) {
          if (prevProvider.current && prevProvider.current !== json.active_provider) {
            trackProviderSwitch(prevProvider.current, json.active_provider)
          }
          prevProvider.current = json.active_provider
          setData(json as Dashboard)
          setLastUpdate(new Date())
          setError(null)
        }
      } catch (e) {
        if (active) setError(String(e))
      }
    }
    fetchData()
    const t = setInterval(fetchData, 15000)
    return () => {
      active = false
      clearInterval(t)
    }
  }, [])

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">AI Provider Rotation</h1>
          <p className="text-slate-400 text-sm mt-1">
            Zero-cost adaptive rotation · x8 free providers · hard stops at 95%
          </p>
        </div>
        <div className="text-right">
          {data && (
            <div className={`text-sm font-medium ${data.zero_cost_operational ? 'text-emerald-400' : 'text-red-400'}`}>
              {data.zero_cost_operational ? '● OPERATIONAL' : '● OFFLINE MODE'}
            </div>
          )}
          {lastUpdate && (
            <div className="text-xs text-slate-500 mt-1">
              Updated {lastUpdate.toLocaleTimeString()}
            </div>
          )}
        </div>
      </div>

      {error && (
        <AdaptiveCard health="critical" title="Connection Error" size="compact">
          <p className="text-red-300 text-sm">{error}</p>
          <p className="text-slate-400 text-xs mt-1">Backend may not be running. Start with: <code className="text-violet-300">make dev-api</code></p>
        </AdaptiveCard>
      )}

      {data && (
        <>
          {/* Active Provider Banner */}
          <AdaptiveCard health="ok" size="compact" className="border-violet-500/50 bg-violet-950/30">
            <div className="flex items-center gap-3">
              <span className="text-2xl">🎯</span>
              <div>
                <p className="text-white font-semibold">
                  Active: {PROVIDER_LABELS[data.active_provider] ?? data.active_provider}
                </p>
                <p className="text-slate-400 text-sm">
                  {data.available_providers.length} available ·{' '}
                  {data.rotating_providers.length} rotating ·{' '}
                  {data.hard_stopped_providers.length} stopped
                </p>
              </div>
            </div>
          </AdaptiveCard>

          {/* Provider Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {Object.entries(data.providers).map(([name, info]) => (
              <AdaptiveCard
                key={name}
                title={PROVIDER_LABELS[name] ?? name}
                subtitle={`${info.daily_req} daily · ${info.hourly_req}/hr`}
                health={
                  info.status === 'hard_stop' ? 'critical'
                  : info.status === 'rotating' ? 'warning'
                  : info.status === 'unlimited' ? 'unlimited'
                  : info.available ? 'ok'
                  : 'critical'
                }
                size="compact"
              >
                <div className="space-y-2 mt-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-slate-400">Utilisation</span>
                    <span className={
                      info.utilisation_pct >= 95 ? 'text-red-400'
                      : info.utilisation_pct >= 80 ? 'text-amber-400'
                      : 'text-emerald-400'
                    }>
                      {info.utilisation_pct}%
                    </span>
                  </div>
                  <UtilBar pct={info.utilisation_pct} />
                  <div className="flex items-center justify-between text-xs mt-1">
                    <span className="text-slate-500">
                      {STATUS_EMOJI[info.status]} {info.status}
                    </span>
                    {info.consecutive_errors > 0 && (
                      <span className="text-amber-400">⚠ {info.consecutive_errors} errors</span>
                    )}
                    {name === data.active_provider && (
                      <span className="text-violet-400 font-medium">← active</span>
                    )}
                  </div>
                </div>
              </AdaptiveCard>
            ))}
          </div>

          {/* Legend */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs text-slate-400">
            <div>♾️ unlimited — no rate limits (Ollama local)</div>
            <div>✅ ok — within 80% of daily limit</div>
            <div>🔄 rotating — &gt;80% utilised, rotating to next</div>
            <div>🛑 hard_stop — &gt;95% — provider suspended for 24h</div>
          </div>
        </>
      )}
    </div>
  )
}

export default AIProvidersPage
