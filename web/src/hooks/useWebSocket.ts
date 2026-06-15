import { useCallback, useEffect, useRef, useState } from 'react'

export interface WebSocketHookResult {
  connected: boolean
  lastMessage: unknown
  send: (msg: object) => void
  error: string | null
}

const MAX_BACKOFF_MS = 30_000
const BASE_BACKOFF_MS = 500

function resolveUrl(url: string): string {
  if (typeof window === 'undefined') return url
  const secure = window.location.protocol === 'https:'
  const wsScheme = secure ? 'wss:' : 'ws:'
  // Replace any explicit scheme with the protocol-appropriate one
  return url.replace(/^wss?:/, wsScheme)
}

export function useWebSocket(
  url: string,
  onMessage?: (msg: unknown) => void
): WebSocketHookResult {
  const [connected, setConnected] = useState(false)
  const [lastMessage, setLastMessage] = useState<unknown>(null)
  const [error, setError] = useState<string | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const retryCountRef = useRef(0)
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const unmountedRef = useRef(false)
  const onMessageRef = useRef(onMessage)
  onMessageRef.current = onMessage

  const clearRetryTimer = () => {
    if (retryTimerRef.current !== null) {
      clearTimeout(retryTimerRef.current)
      retryTimerRef.current = null
    }
  }

  const connect = useCallback(() => {
    if (unmountedRef.current) return

    try {
      const resolvedUrl = resolveUrl(url)
      const ws = new WebSocket(resolvedUrl)
      wsRef.current = ws

      ws.onopen = () => {
        if (unmountedRef.current) { ws.close(); return }
        setConnected(true)
        setError(null)
        retryCountRef.current = 0
      }

      ws.onmessage = (event: MessageEvent) => {
        if (unmountedRef.current) return
        let parsed: unknown = event.data
        try { parsed = JSON.parse(event.data as string) } catch { /* keep raw */ }
        setLastMessage(parsed)
        onMessageRef.current?.(parsed)
      }

      ws.onerror = () => {
        if (unmountedRef.current) return
        setError('WebSocket connection error')
      }

      ws.onclose = () => {
        if (unmountedRef.current) return
        setConnected(false)
        wsRef.current = null
        const backoff = Math.min(
          BASE_BACKOFF_MS * Math.pow(2, retryCountRef.current),
          MAX_BACKOFF_MS
        )
        retryCountRef.current += 1
        retryTimerRef.current = setTimeout(connect, backoff)
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to open WebSocket'
      setError(msg)
      const backoff = Math.min(
        BASE_BACKOFF_MS * Math.pow(2, retryCountRef.current),
        MAX_BACKOFF_MS
      )
      retryCountRef.current += 1
      retryTimerRef.current = setTimeout(connect, backoff)
    }
  }, [url])

  useEffect(() => {
    unmountedRef.current = false
    connect()
    return () => {
      unmountedRef.current = true
      clearRetryTimer()
      if (wsRef.current) {
        wsRef.current.onclose = null
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [connect])

  const send = useCallback((msg: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg))
    }
  }, [])

  return { connected, lastMessage, send, error }
}
