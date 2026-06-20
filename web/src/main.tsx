import React from 'react'
import ReactDOM from 'react-dom/client'
import posthog from 'posthog-js'
import App from './App'
import ErrorBoundary from './components/ErrorBoundary'
import { ThemeProvider } from './contexts/ThemeContext'
import './index.css'
import './ux-system.css'

// PostHog — zero-cost product analytics + feature flags (1M events/month free tier)
// Set VITE_POSTHOG_KEY in .env to activate. Silently skipped when key is absent.
const _phKey = import.meta.env.VITE_POSTHOG_KEY as string | undefined
if (_phKey) {
  posthog.init(_phKey, {
    api_host: (import.meta.env.VITE_POSTHOG_HOST as string | undefined) ?? 'https://eu.i.posthog.com',
    person_profiles: 'identified_only',
    capture_pageview: true,
    capture_pageleave: true,
    autocapture: false,
  })
}

// Automated accessibility audits in development
if (import.meta.env.DEV) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  import('@axe-core/react').then(({ default: axe }) => { axe(React as any, ReactDOM as any, 1000) })
    .catch(() => { /* axe-core optional — skip if not installed */ })
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <ThemeProvider>
        <App />
      </ThemeProvider>
    </ErrorBoundary>
  </React.StrictMode>
)
