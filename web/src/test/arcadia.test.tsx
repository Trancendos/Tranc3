import React from 'react'
import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import ArcadiaPage from '../pages/ArcadiaPage'

function openArcadia() {
  return render(
    <MemoryRouter>
      <ArcadiaPage />
    </MemoryRouter>,
  )
}

describe('Arcadia protected shell', () => {
  it('identifies the community and marketplace as not yet connected', () => {
    openArcadia()
    expect(screen.getByRole('heading', { name: 'Arcadia' })).toBeTruthy()
    const community = screen.getByTestId('arcadia-community')
    const marketplace = screen.getByTestId('arcadia-marketplace')
    expect(within(community).getByText('Not connected')).toBeTruthy()
    expect(within(marketplace).getByText('Not connected')).toBeTruthy()
    expect(within(community).queryByRole('link')).toBeNull()
    expect(within(marketplace).queryByRole('link')).toBeNull()
  })

  it('only links to existing protected platform views', () => {
    openArcadia()
    expect(screen.getByRole('link', { name: /Search the platform/i }).getAttribute('href')).toBe('/search')
    expect(screen.getByRole('link', { name: /Notifications/i }).getAttribute('href')).toBe('/notifications')
    expect(screen.getByRole('link', { name: /Platform status/i }).getAttribute('href')).toBe('/status')
  })

  it('explains financial controls and never presents live trading as available', () => {
    openArcadia()
    expect(screen.getByText(/Financial transactions are unavailable/i)).toBeTruthy()
    expect(screen.queryByRole('button', { name: /buy|purchase|transfer|checkout/i })).toBeNull()
  })
})
