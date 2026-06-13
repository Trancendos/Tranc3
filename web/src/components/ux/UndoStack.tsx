/**
 * UndoStack — Shneiderman Rule 6: Permit Easy Reversal of Actions
 *
 * Manages a reversible action history with keyboard shortcut support (Ctrl/Cmd+Z).
 * Implements the IxDF principle that users must always be able to undo — reducing
 * anxiety, encouraging exploration, and building trust. Pairs error prevention
 * (Rule 5) with recovery (Rule 6): guard first, reverse if needed.
 *
 * Stack model: committed actions → undo → redo. Capped at `maxDepth` to bound
 * memory. Each action carries a label for the UI feedback trail.
 */
import React, { createContext, useCallback, useContext, useEffect, useReducer } from 'react'

export interface UndoAction<T = unknown> {
  id: string
  label: string
  do: () => T
  undo: () => T
  timestamp: number
}

interface UndoStackState {
  past: UndoAction[]
  future: UndoAction[]
}

type UndoStackEvent =
  | { type: 'COMMIT'; action: UndoAction; maxDepth: number }
  | { type: 'UNDO' }
  | { type: 'REDO' }
  | { type: 'CLEAR' }

function stackReducer(state: UndoStackState, event: UndoStackEvent): UndoStackState {
  switch (event.type) {
    case 'COMMIT': {
      const past = [...state.past, event.action]
      return { past: past.length > event.maxDepth ? past.slice(-event.maxDepth) : past, future: [] }
    }
    case 'UNDO': {
      if (!state.past.length) return state
      const [action, ...rest] = [...state.past].reverse()
      return { past: rest.reverse(), future: [action, ...state.future] }
    }
    case 'REDO': {
      if (!state.future.length) return state
      const [action, ...rest] = state.future
      return { past: [...state.past, action], future: rest }
    }
    case 'CLEAR':
      return { past: [], future: [] }
    default:
      return state
  }
}

interface UndoStackControls {
  commit: (action: Omit<UndoAction, 'id' | 'timestamp'>) => void
  undo: () => void
  redo: () => void
  clear: () => void
  canUndo: boolean
  canRedo: boolean
  lastAction: UndoAction | null
  undoLabel: string | null
  redoLabel: string | null
  historyLength: number
}

const UndoStackCtx = createContext<UndoStackControls | null>(null)

export function useUndoStack(): UndoStackControls {
  const ctx = useContext(UndoStackCtx)
  if (!ctx) throw new Error('useUndoStack must be used within <UndoStack>')
  return ctx
}

interface UndoStackProps {
  children: React.ReactNode
  maxDepth?: number
  /** Enable Ctrl/Cmd+Z and Ctrl/Cmd+Shift+Z keyboard shortcuts */
  keyboardShortcuts?: boolean
  className?: string
}

export function UndoStack({ children, maxDepth = 50, keyboardShortcuts = true, className = '' }: UndoStackProps) {
  const [state, dispatch] = useReducer(stackReducer, { past: [], future: [] })

  const commit = useCallback((action: Omit<UndoAction, 'id' | 'timestamp'>) => {
    const full: UndoAction = {
      ...action,
      id: `undo-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      timestamp: Date.now(),
    }
    full.do()
    dispatch({ type: 'COMMIT', action: full, maxDepth })
  }, [])

  const undo = useCallback(() => {
    const last = state.past[state.past.length - 1]
    if (last) { last.undo(); dispatch({ type: 'UNDO' }) }
  }, [state.past])

  const redo = useCallback(() => {
    const next = state.future[0]
    if (next) { next.do(); dispatch({ type: 'REDO' }) }
  }, [state.future])

  const clear = useCallback(() => dispatch({ type: 'CLEAR' }), [])

  useEffect(() => {
    if (!keyboardShortcuts) return
    const handler = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey
      if (!mod) return
      if (e.key === 'z' && !e.shiftKey) { e.preventDefault(); undo() }
      if ((e.key === 'z' && e.shiftKey) || e.key === 'y') { e.preventDefault(); redo() }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [keyboardShortcuts, undo, redo])

  const cappedPast = state.past
  const controls: UndoStackControls = {
    commit,
    undo,
    redo,
    clear,
    canUndo: cappedPast.length > 0,
    canRedo: state.future.length > 0,
    lastAction: cappedPast[cappedPast.length - 1] ?? null,
    undoLabel: cappedPast[cappedPast.length - 1]?.label ?? null,
    redoLabel: state.future[0]?.label ?? null,
    historyLength: cappedPast.length,
  }

  return (
    <UndoStackCtx.Provider value={controls}>
      <div className={`ux-undo-stack ${className}`}>{children}</div>
    </UndoStackCtx.Provider>
  )
}

interface UndoBarProps {
  className?: string
}

/** Compact undo/redo action bar — attach near editable content */
export function UndoBar({ className = '' }: UndoBarProps) {
  const { undo, redo, canUndo, canRedo, undoLabel, redoLabel } = useUndoStack()
  if (!canUndo && !canRedo) return null
  return (
    <div
      className={`ux-undo-bar ${className}`}
      role="toolbar"
      aria-label="Action history"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 'var(--ux-space-1)',
        padding: '2px var(--ux-space-2)',
        borderRadius: 'var(--ux-radius-full)',
        background: 'var(--ux-surface-raised)',
        border: '1px solid var(--ux-border)',
        fontSize: 'var(--ux-text-xs)',
      }}
    >
      <button
        onClick={undo}
        disabled={!canUndo}
        title={undoLabel ? `Undo: ${undoLabel} (Ctrl+Z)` : 'Nothing to undo'}
        aria-label={undoLabel ? `Undo ${undoLabel}` : 'Undo'}
        style={{
          background: 'none',
          border: 'none',
          cursor: canUndo ? 'pointer' : 'default',
          opacity: canUndo ? 1 : 0.35,
          padding: '2px var(--ux-space-1)',
          color: 'var(--ux-text-primary)',
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--ux-space-1)',
        }}
      >
        ↩ {undoLabel ? <span style={{ maxWidth: '120px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{undoLabel}</span> : null}
      </button>
      {canRedo && (
        <button
          onClick={redo}
          title={redoLabel ? `Redo: ${redoLabel} (Ctrl+Shift+Z)` : 'Nothing to redo'}
          aria-label={redoLabel ? `Redo ${redoLabel}` : 'Redo'}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: '2px var(--ux-space-1)',
            color: 'var(--ux-text-muted)',
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--ux-space-1)',
          }}
        >
          ↪ {redoLabel ? <span style={{ maxWidth: '120px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{redoLabel}</span> : null}
        </button>
      )}
    </div>
  )
}
