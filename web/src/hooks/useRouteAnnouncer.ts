import { useEffect, useRef, type RefObject } from 'react'
import { useLocation } from 'react-router'
import ROUTE_META from '../config/routeMeta'

export function useRouteAnnouncer(regionRef: RefObject<HTMLElement | null>): void {
  const location = useLocation()
  const prevPathRef = useRef<string>(location.pathname)

  useEffect(() => {
    if (location.pathname === prevPathRef.current) return
    prevPathRef.current = location.pathname

    const el = regionRef.current
    if (!el) return

    const label =
      ROUTE_META[location.pathname]?.label ??
      `${location.pathname.replace(/^\//, '').replace(/-/g, ' ')} page`

    el.textContent = ''
    // Defer so screen readers detect the content change
    requestAnimationFrame(() => {
      el.textContent = `Navigated to ${label}`
    })
  }, [location.pathname, regionRef])
}
