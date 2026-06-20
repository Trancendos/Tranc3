import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router'
import ChatView from './ChatView'
import TrancendosDashboard from './trancendos/Dashboard'
import DashboardPage from './pages/DashboardPage'
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
import TheLabPage from './pages/TheLabPage'
import TheDutchyPage from './pages/TheDutchyPage'
import TuringsHubPage from './pages/TuringsHubPage'
import DeepAgentsPage from './pages/DeepAgentsPage'
import AuditPage from './pages/AuditPage'
import LangChainPage from './pages/LangChainPage'
import ModelRouterPage from './pages/ModelRouterPage'
import LedgerPage from './pages/LedgerPage'
import TopologyPage from './pages/TopologyPage'
import VaultPage from './pages/VaultPage'
import AnalyticsPage from './pages/AnalyticsPage'
import ConfigPage from './pages/ConfigPage'
import CronPage from './pages/CronPage'
import CachePage from './pages/CachePage'
import RateLimitPage from './pages/RateLimitPage'
import GeoPage from './pages/GeoPage'
import EmailServicePage from './pages/EmailServicePage'
import SmsPage from './pages/SmsPage'
import HivePage from './pages/HivePage'
import GBrainPage from './pages/GBrainPage'
import DevOcityPage from './pages/DevOcityPage'
import BackupPage from './pages/BackupPage'
import CdnPage from './pages/CdnPage'
import InfinityPortalPage from './pages/InfinityPortalPage'
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
        <Route path="/dashboard"    element={<Protected><DashboardPage /></Protected>} />
        <Route path="/mission"      element={<Protected><TrancendosDashboard /></Protected>} />
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
        <Route path="/the-lab"       element={<Protected><TheLabPage /></Protected>} />
        <Route path="/the-dutchy"   element={<Protected><TheDutchyPage /></Protected>} />
        <Route path="/turings-hub"  element={<Protected><TuringsHubPage /></Protected>} />
        <Route path="/deep-agents"  element={<Protected><DeepAgentsPage /></Protected>} />
        <Route path="/audit"        element={<Protected><AuditPage /></Protected>} />
        <Route path="/langchain"    element={<Protected><LangChainPage /></Protected>} />
        <Route path="/model-router" element={<Protected><ModelRouterPage /></Protected>} />
        <Route path="/ledger"       element={<Protected><LedgerPage /></Protected>} />
        <Route path="/topology"     element={<Protected><TopologyPage /></Protected>} />
        <Route path="/vault"        element={<Protected><VaultPage /></Protected>} />
        <Route path="/analytics"    element={<Protected><AnalyticsPage /></Protected>} />
        <Route path="/config"       element={<Protected><ConfigPage /></Protected>} />
        <Route path="/cron"         element={<Protected><CronPage /></Protected>} />
        <Route path="/cache"        element={<Protected><CachePage /></Protected>} />
        <Route path="/rate-limit"   element={<Protected><RateLimitPage /></Protected>} />
        <Route path="/geo"          element={<Protected><GeoPage /></Protected>} />
        <Route path="/email-svc"    element={<Protected><EmailServicePage /></Protected>} />
        <Route path="/sms"          element={<Protected><SmsPage /></Protected>} />
        <Route path="/hive"         element={<Protected><HivePage /></Protected>} />
        <Route path="/gbrain"       element={<Protected><GBrainPage /></Protected>} />
        <Route path="/devocity"     element={<Protected><DevOcityPage /></Protected>} />
        <Route path="/backup"       element={<Protected><BackupPage /></Protected>} />
        <Route path="/cdn"              element={<Protected><CdnPage /></Protected>} />
        <Route path="/infinity-portal"  element={<Protected><InfinityPortalPage /></Protected>} />
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
