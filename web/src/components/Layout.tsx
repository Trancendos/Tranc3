import React from 'react'
import NavBar from './NavBar'

interface LayoutProps {
  children: React.ReactNode
  username?: string
  onLogout?: () => void
}

export default function Layout({ children, username, onLogout }: LayoutProps) {
  return (
    <div className="flex h-screen overflow-hidden bg-gray-950 text-white">
      <NavBar username={username} onLogout={onLogout} />
      <main className="flex-1 overflow-auto">{children}</main>
    </div>
  )
}
