import { useEffect, useRef, useState } from 'react'

export interface SSEEvent {
  type: string
  data: unknown
  id: string
}

export interface SSEHookResult {
  connected: boolean
  events: SSEEvent[]
  lastEvent: SSEEvent | null
}

const MAX_EVENTS = 100
const RECONNECT_DELAY_MS = 3_000

let _eventCounter = 0
function nextId(): string {
  return String(++_eventCounter)
}

export function useSSE(url: string = '/api/mcp/sse'): SSEHookResult {
  const [connected, setConnected] = useState(false)
  const [events, setEvents] = useState<SSEEvent[]>([])
  const [lastEvent, setLastEvent] = useState<SSEEvent | null>(null)

  const esRef = useRef<EventSource | null>(null)
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const unmountedRef = useRef(false)

  const clearRetry = () => {
    if (retryTimerRef.current !== null) {
      clearTimeout(retryTimerRef.current)
      retryTimerRef.current = null
    }
  }

  useEffect(() => {
    unmountedRef.current = false

    function connect() {
      if (unmountedRef.current) return

      const es = new EventSource(url)
      esRef.current = es

      es.onopen = () => {
        if (unmountedRef.current) return
        setConnected(true)
      }

      es.onerror = () => {
        if (unmountedRef.current) return
        setConnected(false)
        es.close()
        esRef.current = null
        clearRetry()
        retryTimerRef.current = setTimeout(connect, RECONNECT_DELAY_MS)
      }

      es.onmessage = (event: MessageEvent) => {
        if (unmountedRef.current) return
        let parsed: unknown = event.data
        try { parsed = JSON.parse(event.data as string) } catch { /* keep raw */ }
        const entry: SSEEvent = {
          type: 'message',
          data: parsed,
          id: event.lastEventId || nextId(),
        }
        pushEvent(entry)
      }

      // Listen for named event types the platform emits
      const namedTypes = ['mcp_tool_call', 'workflow_complete', 'alert', 'health_change']
      for (const evtType of namedTypes) {
        es.addEventListener(evtType, (event: Event) => {
          if (unmountedRef.current) return
          const msgEvent = event as MessageEvent
          let parsed: unknown = msgEvent.data
          try { parsed = JSON.parse(msgEvent.data as string) } catch { /* keep raw */ }
          const entry: SSEEvent = {
            type: evtType,
            data: parsed,
            id: msgEvent.lastEventId || nextId(),
          }
          pushEvent(entry)
        })
      }
    }

    function pushEvent(entry: SSEEvent) {
      setEvents(prev => {
        const next = [...prev, entry]
        return next.length > MAX_EVENTS ? next.slice(next.length - MAX_EVENTS) : next
      })
      setLastEvent(entry)
    }

    connect()

    return () => {
      unmountedRef.current = true
      clearRetry()
      if (esRef.current) {
        esRef.current.close()
        esRef.current = null
      }
    }
  }, [url])

  return { connected, events, lastEvent }
}
