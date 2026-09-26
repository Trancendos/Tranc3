/**
 * AdaptiveCard — Liquidic, reactive, modular card component.
 *
 * Features:
 * - Automatic layout adaptation (compact/standard/expanded based on content)
 * - Health-aware styling (ok/warning/critical colour states)
 * - Reactive: subscribes to live data via polling or SSE
 * - Modular: accepts slot-based children (header, body, footer, actions)
 */

import React, { useState, useEffect, useRef, type ReactNode } from 'react'

type HealthState = 'ok' | 'warning' | 'critical' | 'unknown' | 'unlimited'
type CardSize = 'nano' | 'micro' | 'compact' | 'standard' | 'expanded'

interface AdaptiveCardProps {
  title?: string
  subtitle?: string
  health?: HealthState
  size?: CardSize
  liveUrl?: string        // if set, polls this URL every `pollInterval`ms
  pollInterval?: number   // default 10000ms
  header?: ReactNode
  footer?: ReactNode
  actions?: ReactNode
  className?: string
  onClick?: () => void
  children?: ReactNode
}

const HEALTH_STYLES: Record<HealthState, string> = {
  ok:       'border-emerald-500/40 bg-emerald-950/20',
  warning:  'border-amber-500/40 bg-amber-950/20',
  critical: 'border-red-500/40 bg-red-950/20',
  unknown:  'border-slate-600/40 bg-slate-900/20',
  unlimited:'border-violet-500/40 bg-violet-950/20',
}

const HEALTH_DOT: Record<HealthState, string> = {
  ok:       'bg-emerald-400 shadow-emerald-400/50',
  warning:  'bg-amber-400 shadow-amber-400/50',
  critical: 'bg-red-400 shadow-red-400/50 animate-pulse',
  unknown:  'bg-slate-400',
  unlimited:'bg-violet-400 shadow-violet-400/50',
}

const SIZE_STYLES: Record<CardSize, string> = {
  nano:     'p-2 text-xs',
  micro:    'p-3 text-sm',
  compact:  'p-4 text-sm',
  standard: 'p-5 text-base',
  expanded: 'p-6 text-base',
}

// Extra origins a card's liveUrl may point at, beyond the page's own.
// Comma-separated, e.g. "api.trancendos.com,status.trancendos.com".
const EXTRA_LIVE_HOSTS: string[] = (import.meta.env.VITE_ALLOWED_LIVE_HOSTS || '')
  .split(',')
  .map((host: string) => host.trim())
  .filter((host: string) => host.length > 0)

/**
 * Resolve a card's liveUrl and refuse anything outside the permitted origins.
 *
 * Two things the Aikido fix this came from got wrong, both of which stopped
 * every card from ever fetching:
 *
 *   1. `allowedDomains = ['example.com']  // add your allowed domains here`
 *      rejected every real endpoint. A placeholder allowlist is not a strict
 *      control; it is the feature switched off for all callers at once.
 *   2. `new URL(baseUrl)` throws on a relative path, and `liveUrl` has always
 *      accepted same-origin relative URLs such as `/api/health`.
 *
 * The policy that actually fits a browser component polling its own backend is
 * same-origin by default, which needs no list to maintain and cannot drift,
 * plus an explicit deployment-configured set for the cross-origin cases.
 * (CodeRabbit, chatgpt-codex-connector, codeant-ai on #1239)
 */
function buildValidatedUrl(baseUrl: string): string {
  try {
    if (baseUrl.includes('/../') || /\/%2e%2e\//i.test(baseUrl)) {
      throw new Error('Invalid path');
    }

    // A relative liveUrl resolves against the page, which is the common case.
    const origin = typeof window !== 'undefined' ? window.location.origin : undefined;
    const url = new URL(baseUrl, origin);

    if (!['http:', 'https:'].includes(url.protocol)) {
      throw new Error('Invalid protocol');
    }

    const sameOrigin = origin !== undefined && url.origin === origin;
    const permittedHost = EXTRA_LIVE_HOSTS.some(
      (host) => url.hostname === host || url.hostname.endsWith('.' + host),
    );
    if (!sameOrigin && !permittedHost) {
      throw new Error('Invalid host');
    }

    return url.href;
  } catch {
    throw new Error('Invalid URL');
  }
}

export function AdaptiveCard({
  title,
  subtitle,
  health = 'unknown',
  size = 'standard',
  liveUrl,
  pollInterval = 10000,
  header,
  footer,
  actions,
  className = '',
  onClick,
  children,
}: AdaptiveCardProps) {
  const [liveData, setLiveData] = useState<object | null>(null)
  const [liveError, setLiveError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!liveUrl) return
    let active = true
    const fetch_ = async () => {
      setLoading(true)
      try {
        const res = await fetch(buildValidatedUrl(liveUrl))
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json() as object
        if (active) {
          setLiveData(data)
          setLiveError(null)
        }
      } catch (e) {
        if (active) setLiveError(String(e))
      } finally {
        if (active) setLoading(false)
      }
    }
    fetch_()
    timerRef.current = setInterval(fetch_, pollInterval)
    return () => {
      active = false
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [liveUrl, pollInterval])

  return (
    <div
      onClick={onClick}
      className={[
        'rounded-xl border transition-all duration-300',
        HEALTH_STYLES[health],
        SIZE_STYLES[size],
        onClick ? 'cursor-pointer hover:scale-[1.01] active:scale-[0.99]' : '',
        className,
      ].join(' ')}
    >
      {/* Header slot */}
      {(header || title) && (
        <div className="flex items-center justify-between mb-3">
          {header || (
            <div className="flex items-center gap-2">
              <span
                className={`w-2 h-2 rounded-full shadow-md ${HEALTH_DOT[health]}`}
                title={health}
              />
              <div>
                {title && <p className="font-semibold text-white leading-tight">{title}</p>}
                {subtitle && <p className="text-slate-400 text-xs mt-0.5">{subtitle}</p>}
              </div>
            </div>
          )}
          {loading && (
            <span className="text-xs text-slate-500 animate-pulse">live</span>
          )}
        </div>
      )}

      {/* Body */}
      <div className={liveError ? 'text-red-400 text-xs' : ''}>
        {liveError ? `⚠ ${liveError}` : children}
        {liveData && !children && (
          <pre className="text-xs text-slate-300 overflow-auto max-h-48">
            {JSON.stringify(liveData, null, 2)}
          </pre>
        )}
      </div>

      {/* Footer slot */}
      {footer && (
        <div className="mt-3 pt-3 border-t border-white/5 text-slate-400 text-xs">
          {footer}
        </div>
      )}

      {/* Actions slot */}
      {actions && (
        <div className="mt-3 flex gap-2 justify-end">
          {actions}
        </div>
      )}
    </div>
  )
}

export default AdaptiveCard
