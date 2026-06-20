/**
 * useAnalytics — PostHog wrapper with safe no-op fallback.
 *
 * Calling posthog.capture() when PostHog isn't initialised throws; this hook
 * silences that and provides typed helpers for the platform's key events.
 */
import { useCallback } from 'react'

type Properties = Record<string, unknown>

function ph() {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const w = typeof window !== 'undefined' ? (window as any) : {}
  return w.__posthog__ ?? null
}

function capture(event: string, props?: Properties) {
  try {
    const posthog = ph()
    if (posthog?.capture) posthog.capture(event, props)
    else {
      // Try the module-level import path (posthog-js sets window.__ph__)
      // @ts-ignore dynamic import
      import('posthog-js').then(m => m.default?.capture?.(event, props)).catch(() => {})
    }
  } catch { /* PostHog not loaded — ignore */ }
}

export function useAnalytics() {
  const trackChat = useCallback((props: { personality?: string; language?: string; emotion?: string }) => {
    capture('chat_message_sent', props)
  }, [])

  const trackProviderSwitch = useCallback((from: string, to: string) => {
    capture('ai_provider_switch', { from, to })
  }, [])

  const trackSearch = useCallback((query: string, resultCount: number, provider?: string) => {
    capture('search_performed', { query_length: query.length, result_count: resultCount, provider })
  }, [])

  const trackPageView = useCallback((page: string) => {
    capture('$pageview', { $current_url: page })
  }, [])

  const trackError = useCallback((error: string, context?: string) => {
    capture('error_encountered', { error, context })
  }, [])

  const trackNotificationRead = useCallback((count: number) => {
    capture('notifications_read', { count })
  }, [])

  const trackWorkerRefresh = useCallback((workerCount: number) => {
    capture('workers_health_refresh', { worker_count: workerCount })
  }, [])

  const identify = useCallback((userId: string, traits?: Properties) => {
    try {
      // @ts-ignore
      import('posthog-js').then(m => m.default?.identify?.(userId, traits)).catch(() => {})
    } catch { /* ignore */ }
  }, [])

  return { trackChat, trackProviderSwitch, trackSearch, trackPageView, trackError, trackNotificationRead, trackWorkerRefresh, identify }
}
