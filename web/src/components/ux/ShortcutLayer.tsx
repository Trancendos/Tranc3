/**
 * ShortcutLayer — Shneiderman Rule 2: Enable Frequent Users to Use Shortcuts
 *              + IxDF: Power User Acceleration
 *              + Impala: Adaptive Interaction Depth
 *
 * Contextual keyboard shortcut registry with visual discovery overlay.
 * Novice users see no friction — shortcuts are hidden until invoked or
 * discovered via the `?` key. Expert users get a full command palette.
 *
 * Principles applied:
 *   - Accelerators: Ctrl+K command palette, per-scope shortcuts
 *   - Learnability: `?` reveals all active shortcuts in current scope
 *   - Feedback: brief visible flash on shortcut activation
 *   - Scope isolation: nested layers override parent bindings cleanly
 */
import React, { createContext, useCallback, useContext, useEffect, useId, useRef, useState } from 'react'

export interface Shortcut {
  key: string
  /** e.g. 'ctrl', 'meta', 'shift', 'alt' */
  modifiers?: Array<'ctrl' | 'meta' | 'shift' | 'alt'>
  label: string
  description?: string
  handler: (e: KeyboardEvent) => void
  /** Scope name for grouping in the discovery overlay */
  group?: string
}

interface ShortcutLayerCtx {
  register: (shortcut: Shortcut) => () => void
  shortcuts: Shortcut[]
}

const ShortcutCtx = createContext<ShortcutLayerCtx | null>(null)

function matchesShortcut(e: KeyboardEvent, s: Shortcut): boolean {
  const mods = s.modifiers ?? []
  if (mods.includes('ctrl') !== e.ctrlKey) return false
  if (mods.includes('meta') !== e.metaKey) return false
  if (mods.includes('shift') !== e.shiftKey) return false
  if (mods.includes('alt') !== e.altKey) return false
  return e.key.toLowerCase() === s.key.toLowerCase()
}

function formatShortcut(s: Shortcut): string {
  const mods = s.modifiers ?? []
  const parts: string[] = []
  if (mods.includes('ctrl')) parts.push('Ctrl')
  if (mods.includes('meta')) parts.push('⌘')
  if (mods.includes('shift')) parts.push('Shift')
  if (mods.includes('alt')) parts.push('Alt')
  parts.push(s.key.length === 1 ? s.key.toUpperCase() : s.key)
  return parts.join('+')
}

interface ShortcutLayerProps {
  children: React.ReactNode
  /** Show the `?` help shortcut */
  showHelp?: boolean
  className?: string
}

export function ShortcutLayer({ children, showHelp = true, className = '' }: ShortcutLayerProps) {
  const [shortcuts, setShortcuts] = useState<Shortcut[]>([])
  const [showOverlay, setShowOverlay] = useState(false)
  const [flash, setFlash] = useState<string | null>(null)
  const overlayId = useId()
  const overlayRef = useRef<HTMLDivElement>(null)
  const previousFocusRef = useRef<HTMLElement | null>(null)
  const shortcutsRef = useRef<Shortcut[]>(shortcuts)
  shortcutsRef.current = shortcuts

  useEffect(() => {
    if (showOverlay) {
      previousFocusRef.current = document.activeElement as HTMLElement
      const first = overlayRef.current?.querySelector<HTMLElement>('button, [tabindex]:not([tabindex="-1"])')
      first?.focus()
    } else {
      previousFocusRef.current?.focus()
    }
  }, [showOverlay])

  const register = useCallback((shortcut: Shortcut) => {
    setShortcuts(prev => [...prev, shortcut])
    return () => setShortcuts(prev => prev.filter(s => s !== shortcut))
  }, [])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return

      if (showHelp && e.key === '?' && !e.ctrlKey && !e.metaKey) {
        e.preventDefault()
        setShowOverlay(v => !v)
        return
      }

      if (e.key === 'Escape') {
        setShowOverlay(prev => { if (prev) { e.preventDefault(); return false } return prev })
        if (!shortcutsRef.current.some(s => s.key.toLowerCase() === 'escape')) return
      }

      for (const s of shortcutsRef.current) {
        if (matchesShortcut(e, s)) {
          e.preventDefault()
          s.handler(e)
          setFlash(s.label)
          setTimeout(() => setFlash(null), 800)
          break
        }
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [showHelp])

  const groups = shortcuts.reduce<Record<string, Shortcut[]>>((acc, s) => {
    const g = s.group ?? 'General'
    ;(acc[g] ??= []).push(s)
    return acc
  }, {})

  return (
    <ShortcutCtx.Provider value={{ register, shortcuts }}>
      <div className={`ux-shortcut-layer ${className}`} style={{ position: 'relative' }}>
        {children}

        {flash && (
          <div
            role="status"
            aria-live="polite"
            style={{
              position: 'fixed',
              bottom: 'var(--ux-space-6)',
              left: '50%',
              transform: 'translateX(-50%)',
              background: 'rgba(0,0,0,0.8)',
              color: '#fff',
              padding: 'var(--ux-space-2) var(--ux-space-4)',
              borderRadius: 'var(--ux-radius-full)',
              fontSize: 'var(--ux-text-sm)',
              zIndex: 9999,
              pointerEvents: 'none',
              whiteSpace: 'nowrap',
            }}
          >
            {flash}
          </div>
        )}

        {showOverlay && (
          <div
            id={overlayId}
            ref={overlayRef}
            role="dialog"
            aria-label="Keyboard shortcuts"
            aria-modal="true"
            onKeyDown={e => {
              if (e.key !== 'Tab') return
              const focusable = overlayRef.current?.querySelectorAll<HTMLElement>(
                'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
              )
              if (!focusable?.length) return
              const first = focusable[0]
              const last = focusable[focusable.length - 1]
              if (e.shiftKey) { if (document.activeElement === first) { e.preventDefault(); last.focus() } }
              else { if (document.activeElement === last) { e.preventDefault(); first.focus() } }
            }}
            style={{
              position: 'fixed',
              inset: 0,
              background: 'rgba(0,0,0,0.5)',
              zIndex: 9000,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            onClick={e => { if (e.target === e.currentTarget) setShowOverlay(false) }}
          >
            <div
              style={{
                background: 'var(--ux-surface-card)',
                borderRadius: 'var(--ux-radius-lg)',
                padding: 'var(--ux-space-6)',
                maxWidth: '480px',
                width: '90vw',
                maxHeight: '70vh',
                overflowY: 'auto',
                boxShadow: 'var(--ux-shadow-lg)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--ux-space-4)' }}>
                <h2 style={{ margin: 0, fontSize: 'var(--ux-text-lg)', fontWeight: 600 }}>Keyboard shortcuts</h2>
                <button
                  onClick={() => setShowOverlay(false)}
                  aria-label="Close"
                  style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 'var(--ux-text-lg)', color: 'var(--ux-text-muted)' }}
                >
                  ✕
                </button>
              </div>
              {Object.entries(groups).map(([group, items]) => (
                <div key={group} style={{ marginBottom: 'var(--ux-space-4)' }}>
                  <div style={{ fontSize: 'var(--ux-text-xs)', fontWeight: 600, color: 'var(--ux-text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 'var(--ux-space-2)' }}>
                    {group}
                  </div>
                  <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 'var(--ux-space-2)' }}>
                    {items.map(s => (
                      <li key={s.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontSize: 'var(--ux-text-sm)', color: 'var(--ux-text-secondary)' }}>{s.label}</span>
                        <kbd style={{
                          fontFamily: 'var(--ux-font-mono, monospace)',
                          fontSize: 'var(--ux-text-xs)',
                          background: 'var(--ux-surface-raised)',
                          border: '1px solid var(--ux-border)',
                          borderRadius: 'var(--ux-radius-sm)',
                          padding: '2px var(--ux-space-2)',
                          color: 'var(--ux-text-primary)',
                        }}>
                          {formatShortcut(s)}
                        </kbd>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
              {showHelp && (
                <p style={{ fontSize: 'var(--ux-text-xs)', color: 'var(--ux-text-muted)', margin: 0 }}>
                  Press <kbd style={{ fontFamily: 'var(--ux-font-mono, monospace)' }}>?</kbd> to toggle this panel · <kbd style={{ fontFamily: 'var(--ux-font-mono, monospace)' }}>Esc</kbd> to close
                </p>
              )}
            </div>
          </div>
        )}
      </div>
    </ShortcutCtx.Provider>
  )
}

export function useShortcut(shortcut: Shortcut) {
  const ctx = useContext(ShortcutCtx)
  if (!ctx) throw new Error('useShortcut must be used within <ShortcutLayer>')
  const stableHandler = useRef(shortcut.handler)
  stableHandler.current = shortcut.handler

  useEffect(() => {
    const s: Shortcut = { ...shortcut, handler: e => stableHandler.current(e) }
    return ctx.register(s)
  }, [shortcut.key, (shortcut.modifiers ?? []).join(','), shortcut.label, shortcut.group, ctx.register])
}
