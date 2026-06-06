import React, { useState, useEffect, useCallback } from 'react'
import AppRouter from './AppRouter'
import KeyboardHelpModal from './components/KeyboardHelpModal'

export default function App() {
  const [helpOpen, setHelpOpen] = useState(false)

  const openHelp  = useCallback(() => setHelpOpen(true),  [])
  const closeHelp = useCallback(() => setHelpOpen(false), [])

  // Global ? key opens keyboard help (ignore when focus is in an input/textarea)
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (document.activeElement?.tagName ?? '').toLowerCase()
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return
      if (e.key === '?' && !e.ctrlKey && !e.altKey && !e.metaKey) {
        e.preventDefault()
        setHelpOpen((prev) => !prev)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <>
      <AppRouter />
      <KeyboardHelpModal open={helpOpen} onClose={closeHelp} />
    </>
  )
}
