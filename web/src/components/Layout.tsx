import React from 'react'
import NavBar from './NavBar'

interface LayoutProps {
  children: React.ReactNode
  username?: string
  onLogout?: () => void
}

export default function Layout({ children, username, onLogout }: LayoutProps) {
  return (
    <div className="flex h-screen overflow-hidden bg-[hsl(var(--background))] text-[hsl(var(--foreground))]">
      {/* Skip navigation — visible only on focus */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[9999] focus:px-4 focus:py-2 focus:rounded-md focus:bg-indigo-600 focus:text-white focus:font-semibold focus:text-sm focus:shadow-lg focus:outline-none focus:ring-2 focus:ring-white"
      >
        Skip to main content
      </a>

      <NavBar username={username} onLogout={onLogout} />

      <main id="main-content" className="flex-1 overflow-auto" tabIndex={-1}>
        {children}
      </main>
    </div>
  )
}
