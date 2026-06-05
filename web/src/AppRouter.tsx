import React, { useState, useCallback, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import ChatView from './ChatView'
import TrancendosDashboard from './trancendos/Dashboard'
import StatusPage from './pages/StatusPage'
import NotificationsPage from './pages/NotificationsPage'
import StoragePage from './pages/StoragePage'
import SearchPage from './pages/SearchPage'
import QueuePage from './pages/QueuePage'
import WorkersPage from './pages/WorkersPage'
import AdminPage from './pages/AdminPage'
import SettingsPage from './pages/SettingsPage'
import LoginPage from './LoginPage'

// Lazy-load SparkDashboard
const SparkDashboard = React.lazy(() => import('./trancendos/SparkDashboard'))

function RequireAuth({
  children,
  username,
}: {
  children: React.ReactNode
  username: string | null
}) {
  if (!username) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function AppRouter() {
  const [username, setUsername] = useState<string | null>(() =>
    localStorage.getItem('tranc3_username')
  )

  // LoginPage calls onLogin(token, username) — match that signature
  const handleLogin = useCallback((token: string, user: string) => {
    localStorage.setItem('tranc3_username', user)
    localStorage.setItem('tranc3_token', token)
    setUsername(user)
  }, [])

  const handleLogout = useCallback(() => {
    localStorage.removeItem('tranc3_username')
    localStorage.removeItem('tranc3_token')
    setUsername(null)
  }, [])

  const wrap = (el: React.ReactNode) => (
    <RequireAuth username={username}>
      <Layout username={username ?? undefined} onLogout={handleLogout}>
        {el}
      </Layout>
    </RequireAuth>
  )

  return (
    <BrowserRouter>
      <React.Suspense
        fallback={
          <div
            role="status"
            aria-label="Loading page"
            aria-live="polite"
            className="flex items-center justify-center h-screen bg-gray-950 text-gray-400 text-sm"
          >
            <span aria-hidden="true">Loading…</span>
          </div>
        }
      >
        <Routes>
          <Route path="/login" element={<LoginPage onLogin={handleLogin} />} />

          <Route path="/"             element={wrap(<ChatView />)} />
          <Route path="/dashboard"   element={wrap(<TrancendosDashboard />)} />
          <Route path="/spark"       element={wrap(<SparkDashboard />)} />
          <Route path="/status"      element={wrap(<StatusPage />)} />
          <Route path="/notifications" element={wrap(<NotificationsPage />)} />
          <Route path="/storage"     element={wrap(<StoragePage />)} />
          <Route path="/search"      element={wrap(<SearchPage />)} />
          <Route path="/queue"       element={wrap(<QueuePage />)} />
          <Route path="/workers"     element={wrap(<WorkersPage />)} />
          <Route path="/admin"       element={wrap(<AdminPage />)} />
          <Route path="/settings"    element={wrap(<SettingsPage />)} />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </React.Suspense>
    </BrowserRouter>
  )
}
