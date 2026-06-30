import React, { useRef } from 'react'
import { usePageTitle } from '../hooks/usePageTitle'
import { useRouteAnnouncer } from '../hooks/useRouteAnnouncer'

export default function GlobalAccessibility() {
  const announceRef = useRef<HTMLDivElement>(null)

  usePageTitle()
  useRouteAnnouncer(announceRef)

  return (
    <div
      ref={announceRef}
      role="status"
      aria-live="polite"
      aria-atomic="true"
      className="sr-only"
    />
  )
}
