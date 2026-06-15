/**
 * Accessibility audit — axe-core component tests.
 *
 * Each test renders a component in jsdom, runs axe-core against it,
 * and asserts zero violations. This is the fast CI layer (<5s total).
 *
 * The complementary Lighthouse audit (scripts/lighthouse-audit.mjs)
 * runs against the built app with a real browser and produces
 * reports/lighthouse.html + reports/a11y-summary.json.
 */
import React from 'react'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { axe, toHaveNoViolations } from 'jest-axe'
import { expect, describe, it } from 'vitest'

expect.extend(toHaveNoViolations)

// ── helpers ──────────────────────────────────────────────────────────────────

function withRouter(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

// ── NavBar ────────────────────────────────────────────────────────────────────

describe('NavBar a11y', () => {
  it('has no axe violations (expanded)', async () => {
    const { container } = await import('../components/NavBar').then(({ default: NavBar }) =>
      withRouter(<NavBar username="alice" onLogout={() => {}} />)
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})

// ── Layout ────────────────────────────────────────────────────────────────────

describe('Layout a11y', () => {
  it('has no axe violations', async () => {
    const { container } = await import('../components/Layout').then(({ default: Layout }) =>
      withRouter(
        <Layout username="alice">
          <p>Page content</p>
        </Layout>
      )
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})

// ── KeyboardHelpModal ─────────────────────────────────────────────────────────

describe('KeyboardHelpModal a11y', () => {
  it('has no axe violations when open', async () => {
    const { container } = await import('../components/KeyboardHelpModal').then(
      ({ default: KeyboardHelpModal }) =>
        render(<KeyboardHelpModal open onClose={() => {}} />)
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('renders nothing when closed (no orphan ARIA)', async () => {
    const { container } = await import('../components/KeyboardHelpModal').then(
      ({ default: KeyboardHelpModal }) =>
        render(<KeyboardHelpModal open={false} onClose={() => {}} />)
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})

// ── SettingsPage ──────────────────────────────────────────────────────────────

describe('SettingsPage a11y', () => {
  it('has no axe violations', async () => {
    // Mock fetch so the GET /user/settings call doesn't fail in jsdom
    global.fetch = async () =>
      new Response(JSON.stringify({}), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })

    const { container } = await import('../pages/SettingsPage').then(({ default: SettingsPage }) =>
      withRouter(<SettingsPage />)
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})

// ── StatusPage ────────────────────────────────────────────────────────────────

describe('StatusPage a11y', () => {
  it('has no axe violations', async () => {
    global.fetch = async () =>
      new Response(JSON.stringify({ status: 'ok', services: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })

    const { container } = await import('../pages/StatusPage').then(({ default: StatusPage }) =>
      withRouter(<StatusPage />)
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})

// ── SearchPage ────────────────────────────────────────────────────────────────

describe('SearchPage a11y', () => {
  it('has no axe violations (idle state)', async () => {
    const { container } = await import('../pages/SearchPage').then(({ default: SearchPage }) =>
      withRouter(<SearchPage />)
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})

// ── NotificationsPage ─────────────────────────────────────────────────────────

describe('NotificationsPage a11y', () => {
  it('has no axe violations', async () => {
    global.fetch = async () =>
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })

    const { container } = await import('../pages/NotificationsPage').then(
      ({ default: NotificationsPage }) => withRouter(<NotificationsPage />)
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})

// ── TrancendosDashboard ───────────────────────────────────────────────────────

describe('TrancendosDashboard a11y', () => {
  it('has no axe violations (loading / mock-data state)', async () => {
    global.fetch = async () => new Response('null', { status: 503 })

    const { ThemeProvider } = await import('../contexts/ThemeContext')
    const { container } = await import('../trancendos/Dashboard').then(
      ({ default: TrancendosDashboard }) =>
        withRouter(
          <ThemeProvider>
            <TrancendosDashboard />
          </ThemeProvider>
        )
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})

// ── SparkDashboard ────────────────────────────────────────────────────────────

describe('SparkDashboard a11y', () => {
  it('has no axe violations (idle / empty tools state)', async () => {
    global.fetch = async (url: RequestInfo | URL) => {
      const u = url.toString()
      if (u.includes('/mcp/health')) {
        return new Response(JSON.stringify({ status: 'ok' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      return new Response(JSON.stringify({ tools: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }

    const { container } = await import('../trancendos/SparkDashboard').then(
      ({ default: SparkDashboard }) => withRouter(<SparkDashboard />)
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
