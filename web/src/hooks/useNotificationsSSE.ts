import { useEffect, useRef, useState, useCallback } from 'react'
import { useAuthStore } from '../store/authStore'

const API = (import.meta.env.VITE_API_URL as string | undefined) ?? ''
const RECONNECT_BASE_MS = 3_000
const RECONNECT_MAX_MS = 60_000

export interface LiveNotification {
  id: string
  title: string
  message: string
  type: 'info' | 'warning' | 'error' | 'success'
  timestamp: string
  read: boolean
  channel?: string
}

export interface NotificationsSSEState {
  connected: boolean
  notifications: LiveNotification[]
  unreadCount: number
  markRead: (id: string) => void
  markAllRead: () => void
  clearAll: () => void
}

const MAX_LIVE = 100

export function useNotificationsSSE(): NotificationsSSEState {
  const user = useAuthStore((s) => s.user)
  const token = useAuthStore((s) => s.token)
  const [connected, setConnected] = useState(false)
  const [notifications, setNotifications] = useState<LiveNotification[]>([])

  const esRef = useRef<EventSource | null>(null)
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const retryDelayRef = useRef(RECONNECT_BASE_MS)
  const unmountedRef = useRef(false)

  const pushNotif = useCallback((n: LiveNotification) => {
    setNotifications((prev) => {
      const next = [n, ...prev.filter((x) => x.id !== n.id)]
      return next.length > MAX_LIVE ? next.slice(0, MAX_LIVE) : next
    })
  }, [])

  useEffect(() => {
    if (!user?.id || !token) return
    unmountedRef.current = false

    const userId = user.id

    const clearRetry = () => {
      if (retryRef.current !== null) {
        clearTimeout(retryRef.current)
        retryRef.current = null
      }
    }

    const connect = () => {
      if (unmountedRef.current) return

      // EventSource doesn't support custom headers — pass token as query param
      const url = `${API}/notifications/stream/${userId}?token=${encodeURIComponent(token)}`
      const es = new EventSource(url)
      esRef.current = es

      es.onopen = () => {
        if (unmountedRef.current) return
        setConnected(true)
        retryDelayRef.current = RECONNECT_BASE_MS
      }

      es.onerror = () => {
        if (unmountedRef.current) return
        setConnected(false)
        es.close()
        esRef.current = null
        clearRetry()
        const delay = Math.min(retryDelayRef.current, RECONNECT_MAX_MS)
        retryDelayRef.current = Math.min(delay * 2, RECONNECT_MAX_MS)
        retryRef.current = setTimeout(connect, delay)
      }

      es.onmessage = (ev) => {
        if (unmountedRef.current) return
        try {
          const data = JSON.parse(ev.data as string) as LiveNotification
          if (data.id) pushNotif({ ...data, read: false })
        } catch { /* ignore malformed events */ }
      }

      // Named event type from our fan-out bus
      es.addEventListener('notification', (ev) => {
        if (unmountedRef.current) return
        try {
          const data = JSON.parse((ev as MessageEvent).data as string) as LiveNotification
          if (data.id) pushNotif({ ...data, read: false })
        } catch { /* ignore */ }
      })
    }

    connect()

    return () => {
      unmountedRef.current = true
      if (retryRef.current !== null) clearTimeout(retryRef.current)
      if (esRef.current) { esRef.current.close(); esRef.current = null }
    }
  }, [user?.id, token, pushNotif])

  const markRead = useCallback((id: string) => {
    setNotifications((prev) => prev.map((n) => n.id === id ? { ...n, read: true } : n))
  }, [])

  const markAllRead = useCallback(() => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })))
  }, [])

  const clearAll = useCallback(() => setNotifications([]), [])

  const unreadCount = notifications.filter((n) => !n.read).length

  return { connected, notifications, unreadCount, markRead, markAllRead, clearAll }
}
