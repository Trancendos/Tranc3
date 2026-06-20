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
import AdminPage from './pages/AdminPage'
import WorkersPage from './pages/WorkersPage'
import QueuePage from './pages/QueuePage'
import StoragePage from './pages/StoragePage'
import SearchPage from './pages/SearchPage'
import SettingsPage from './pages/SettingsPage'
import StatusPage from './pages/StatusPage'
import SparkDashboard from './components/spark/SparkDashboard'
import AuthGuard from './components/AuthGuard'
import Layout from './components/Layout'
import RealtimeStatusBar from './components/ui/RealtimeStatusBar'

const isDev = import.meta.env.DEV || import.meta.env.MODE === 'development'

function Protected({ children }: { children: React.ReactNode }) {
  return <AuthGuard><Layout>{children}</Layout></AuthGuard>
}

export default function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public */}
        <Route path="/login" element={<LoginPage />} />

        {/* Protected — all wrapped in persistent Layout */}
        <Route path="/"             element={<Protected><ChatView /></Protected>} />
        <Route path="/dashboard"    element={<Protected><TrancendosDashboard /></Protected>} />
        <Route path="/spark"        element={<Protected><SparkDashboard /></Protected>} />
        <Route path="/status"       element={<Protected><StatusPage /></Protected>} />
        <Route path="/compliance"   element={<Protected><ComplianceDashboard /></Protected>} />
        <Route path="/grid"         element={<Protected><DigitalGridPage /></Protected>} />
        <Route path="/notifications" element={<Protected><NotificationsPage /></Protected>} />
        <Route path="/services"     element={<Protected><ServicesPage /></Protected>} />
        <Route path="/ai-providers" element={<Protected><AIProvidersPage /></Protected>} />
        <Route path="/storage"      element={<Protected><StoragePage /></Protected>} />
        <Route path="/search"       element={<Protected><SearchPage /></Protected>} />
        <Route path="/queue"        element={<Protected><QueuePage /></Protected>} />
        <Route path="/admin"        element={<Protected><AdminPage /></Protected>} />
        <Route path="/workers"      element={<Protected><WorkersPage /></Protected>} />
        <Route path="/settings"     element={<Protected><SettingsPage /></Protected>} />
        {isDev && (
          <Route path="/ux-showcase" element={<Protected><UxShowcasePage /></Protected>} />
        )}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>

      <RealtimeStatusBar />
    </BrowserRouter>
  )
}
