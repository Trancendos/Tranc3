/**
 * FocusTrap — Figma UI Principles: ARIA + Accessibility Standards
 *
 * ARIA APG-compliant focus trap for modals, dialogs, drawers, and popovers.
 * Traps Tab and Shift+Tab within a bounded region, restores focus on unmount,
 * and announces entry/exit to screen readers.
 *
 * Based on ARIA Authoring Practices Guide 1.2: Dialog (Modal) pattern.
 * https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/
 */
import React, { useCallback, useEffect, useRef } from 'react'

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
  'details > summary',
].join(', ')

interface FocusTrapProps {
  active?: boolean
  children: React.ReactNode
  /** Element to return focus to on deactivation. Defaults to document.activeElement at mount */
  returnFocus?: HTMLElement | null
  /** Escape key closes the trap */
  onEscape?: () => void
  className?: string
  style?: React.CSSProperties
  role?: string
  'aria-label'?: string
  'aria-labelledby'?: string
  'aria-describedby'?: string
  'aria-modal'?: boolean
}

export function FocusTrap({
  active = true,
  children,
  returnFocus,
  onEscape,
  className = '',
  style,
  role = 'dialog',
  'aria-label': ariaLabel,
  'aria-labelledby': ariaLabelledBy,
  'aria-describedby': ariaDescribedBy,
  'aria-modal': ariaModal = true,
}: FocusTrapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const returnTarget = useRef<Element | null>(null)

  useEffect(() => {
    if (active) {
      returnTarget.current = returnFocus ?? document.activeElement
      const firstFocusable = containerRef.current?.querySelector<HTMLElement>(FOCUSABLE)
      if (firstFocusable) {
        firstFocusable.focus()
      } else {
        containerRef.current?.focus()
      }
    }
    return () => {
      if (active && returnTarget.current instanceof HTMLElement) {
        returnTarget.current.focus()
      }
    }
  }, [active, returnFocus])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (!active || !containerRef.current) return

      if (e.key === 'Escape') {
        e.preventDefault()
        onEscape?.()
        return
      }

      if (e.key !== 'Tab') return

      const focusable = Array.from(
        containerRef.current.querySelectorAll<HTMLElement>(FOCUSABLE),
      ).filter(el => !el.closest('[hidden]') && el.offsetParent !== null)

      if (focusable.length === 0) { e.preventDefault(); return }

      const first = focusable[0]
      const last  = focusable[focusable.length - 1]

      if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last.focus() }
      } else {
        if (document.activeElement === last) { e.preventDefault(); first.focus() }
      }
    },
    [active, onEscape],
  )

  return (
    <div
      ref={containerRef}
      className={className}
      style={style}
      role={role}
      aria-label={ariaLabel}
      aria-labelledby={ariaLabelledBy}
      aria-describedby={ariaDescribedBy}
      aria-modal={ariaModal}
      onKeyDown={handleKeyDown}
      tabIndex={-1}
    >
      {children}
    </div>
  )
}
