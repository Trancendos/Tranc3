import React, { useRef } from 'react'
import NavBar from './NavBar'
import { usePageTitle } from '../hooks/usePageTitle'
import { useRouteAnnouncer } from '../hooks/useRouteAnnouncer'

interface LayoutProps {
  children: React.ReactNode
  username?: string
  onLogout?: () => void
}

export default function Layout({ children, username, onLogout }: LayoutProps) {
  const announceRef = useRef<HTMLDivElement>(null)

  usePageTitle()
  useRouteAnnouncer(announceRef)

  return (
    <div className="flex h-screen overflow-hidden bg-gray-950 text-white">
      {/* Skip navigation — visible only on focus */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[9999] focus:px-4 focus:py-2 focus:rounded-md focus:bg-indigo-600 focus:text-white focus:font-semibold focus:text-sm focus:shadow-lg focus:outline-none focus:ring-2 focus:ring-white"
      >
        Skip to main content
      </a>

      {/* Screen-reader route announcement region */}
      <div
        ref={announceRef}
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
      />

      <NavBar username={username} onLogout={onLogout} />

      <main id="main-content" className="flex-1 overflow-auto" tabIndex={-1}>
        {children}
      </main>
    </div>
  )
}
