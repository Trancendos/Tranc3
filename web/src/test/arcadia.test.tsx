import React from 'react'
import { readFileSync } from 'node:fs'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import ArcadiaPage from '../pages/ArcadiaPage'

function renderArcadia(): string {
  return renderToStaticMarkup(
    <MemoryRouter>
      <ArcadiaPage />
    </MemoryRouter>,
  )
}

describe('Arcadia rendered frontend contract', () => {
  it('renders honest disconnected community and marketplace areas', () => {
    const html = renderArcadia()
    expect(html).toContain('>Arcadia</h1>')
    for (const name of ['arcadia-community', 'arcadia-marketplace']) {
      const area = html.match(new RegExp('data-testid="' + name + '"[\\s\\S]*?</article>'))?.[0]
      expect(area, name).toBeDefined()
      expect(area).toContain('Not connected')
      expect(area).not.toMatch(/<a\\b/)
    }
  })

  it('provides actual protected-view links without fabricating live services', () => {
    const html = renderArcadia()
    for (const route of ['/search', '/notifications', '/status']) {
      expect(html).toContain('href="' + route + '"')
    }
    expect(html).toContain('No live marketplace data')
    expect(html).toContain('Financial transactions are unavailable')
    expect(html).not.toMatch(/<button\\b|<form\\b/)
  })

  it('uses the existing authenticated route and contains no internal-worker secrets', () => {
    const router = readFileSync('src/AppRouter.tsx', 'utf8')
    const page = readFileSync('src/pages/ArcadiaPage.tsx', 'utf8')
    expect(router).toContain('path="/arcadia"')
    expect(router).toMatch(/path="\\/arcadia"\\s+element={<Protected><ArcadiaPage \\/><\\/Protected>} \\/>/)
    expect(page).not.toMatch(/X-Internal-Secret|dev-secret|fetch\\s*\\(/)
  })
})
