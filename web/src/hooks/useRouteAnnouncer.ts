import { useEffect, useRef, type RefObject } from 'react'
import { useLocation } from 'react-router'

const ROUTE_LABELS: Record<string, string> = {
  '/': 'Home page',
  '/chat': 'Chat page',
  '/dashboard': 'Dashboard page',
  '/spark': 'The Spark page',
  '/status': 'Status page',
  '/compliance': 'Compliance page',
  '/grid': 'Digital Grid page',
  '/notifications': 'Alerts page',
  '/services': 'Services page',
  '/ai-providers': 'AI Providers page',
  '/storage': 'Storage page',
  '/search': 'Search page',
  '/queue': 'Queue page',
  '/admin': 'Admin page',
  '/workers': 'Workers page',
  '/settings': 'Settings page',
  '/login': 'Sign in page',
}

export function useRouteAnnouncer(regionRef: RefObject<HTMLElement | null>): void {
  const location = useLocation()
  const prevPathRef = useRef<string>('')

  useEffect(() => {
    if (location.pathname === prevPathRef.current) return
    prevPathRef.current = location.pathname

    const el = regionRef.current
    if (!el) return

    const label =
      ROUTE_LABELS[location.pathname] ??
      `${location.pathname.replace(/^\//, '').replace(/-/g, ' ')} page`

    el.textContent = ''
    // Defer so screen readers detect the content change
    requestAnimationFrame(() => {
      el.textContent = `Navigated to ${label}`
    })
  }, [location.pathname, regionRef])
}
