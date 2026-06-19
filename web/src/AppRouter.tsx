import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router'
import ChatView from './ChatView'
import TrancendosDashboard from './trancendos/Dashboard'
import ComplianceDashboard from './pages/ComplianceDashboard'
import UxShowcasePage from './pages/UxShowcasePage'
import DigitalGridPage from './components/workflow/DigitalGridPage'
import LoginPage from './LoginPage'
import NotificationsPage from './pages/NotificationsPage'
import ServicesPage from './pages/ServicesPage'
import AIProvidersPage from './pages/AIProvidersPage'
import AuthGuard from './components/AuthGuard'
import RealtimeStatusBar from './components/ui/RealtimeStatusBar'

// Guard: ux-showcase is a dev/admin reference tool, not for production users.
const isDev = import.meta.env.DEV || import.meta.env.MODE === 'development'

export default function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public routes — no auth required */}
        <Route path="/login" element={<LoginPage />} />

        {/* Protected routes */}
        <Route path="/" element={<AuthGuard><ChatView /></AuthGuard>} />
        <Route path="/dashboard" element={<AuthGuard><TrancendosDashboard /></AuthGuard>} />
        <Route path="/compliance" element={<AuthGuard><ComplianceDashboard /></AuthGuard>} />
        <Route path="/grid" element={<AuthGuard><DigitalGridPage /></AuthGuard>} />
        <Route path="/notifications" element={<AuthGuard><NotificationsPage /></AuthGuard>} />
        <Route path="/services" element={<AuthGuard><ServicesPage /></AuthGuard>} />
        <Route path="/ai-providers" element={<AuthGuard><AIProvidersPage /></AuthGuard>} />
        {isDev && (
          <Route path="/ux-showcase" element={<AuthGuard><UxShowcasePage /></AuthGuard>} />
        )}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>

      {/* Real-time status bar rendered outside Routes so it persists across navigation */}
      <RealtimeStatusBar />
    </BrowserRouter>
  )
}
