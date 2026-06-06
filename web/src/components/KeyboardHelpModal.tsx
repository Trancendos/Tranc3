import React, { useEffect, useId } from 'react'
import { X, Keyboard } from 'lucide-react'
import { useFocusTrap } from '../hooks/useFocusTrap'

interface ShortcutGroup {
  group: string
  shortcuts: { keys: string[]; description: string }[]
}

const SHORTCUTS: ShortcutGroup[] = [
  {
    group: 'Navigation',
    shortcuts: [
      { keys: ['?'],         description: 'Open this help dialog' },
      { keys: ['Esc'],       description: 'Close dialogs / cancel' },
      { keys: ['Tab'],       description: 'Move focus forward' },
      { keys: ['Shift', 'Tab'], description: 'Move focus backward' },
    ],
  },
  {
    group: 'Chat',
    shortcuts: [
      { keys: ['Enter'],          description: 'Send message' },
      { keys: ['Shift', 'Enter'], description: 'New line in message' },
    ],
  },
  {
    group: 'Settings tabs',
    shortcuts: [
      { keys: ['←', '→'],   description: 'Switch between tabs' },
      { keys: ['Home'],      description: 'Go to first tab' },
      { keys: ['End'],       description: 'Go to last tab' },
    ],
  },
  {
    group: 'Skip links',
    shortcuts: [
      { keys: ['Tab (on page load)'], description: 'Reveal skip to main content link' },
    ],
  },
]

interface Props {
  open: boolean
  onClose: () => void
}

export default function KeyboardHelpModal({ open, onClose }: Props) {
  const titleId  = useId()
  const trapRef  = useFocusTrap(open, onClose)

  // Close on Escape is handled by useFocusTrap; also close on ? key
  useEffect(() => {
    if (!open) return
    function onKey(e: KeyboardEvent) {
      if (e.key === '?' && !e.ctrlKey && !e.altKey && !e.metaKey) onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      aria-hidden={!open}
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Dialog */}
      <div
        ref={trapRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative z-10 bg-gray-900 border border-gray-700 rounded-xl shadow-2xl w-full max-w-lg max-h-[85vh] overflow-y-auto"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
          <h2 id={titleId} className="text-white font-semibold flex items-center gap-2">
            <Keyboard size={18} aria-hidden="true" className="text-indigo-400" />
            Keyboard Shortcuts
          </h2>
          <button
            onClick={onClose}
            aria-label="Close keyboard shortcuts dialog"
            className="p-1.5 rounded-lg text-gray-500 hover:text-white hover:bg-gray-800 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>

        {/* Shortcut groups */}
        <div className="px-6 py-4 space-y-6">
          {SHORTCUTS.map((grp) => (
            <section key={grp.group} aria-labelledby={`group-${grp.group}`}>
              <h3
                id={`group-${grp.group}`}
                className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3"
              >
                {grp.group}
              </h3>
              <dl className="space-y-2">
                {grp.shortcuts.map((s) => (
                  <div key={s.description} className="flex items-center justify-between gap-4">
                    <dt className="text-gray-400 text-sm">{s.description}</dt>
                    <dd className="flex items-center gap-1 flex-shrink-0">
                      {s.keys.map((k, i) => (
                        <React.Fragment key={k}>
                          <kbd className="px-2 py-0.5 bg-gray-800 border border-gray-600 rounded text-xs font-mono text-gray-300">
                            {k}
                          </kbd>
                          {i < s.keys.length - 1 && (
                            <span className="text-gray-600 text-xs">+</span>
                          )}
                        </React.Fragment>
                      ))}
                    </dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>

        <div className="px-6 pb-4">
          <p className="text-gray-600 text-xs">
            Press <kbd className="px-1 py-0.5 bg-gray-800 border border-gray-600 rounded font-mono">?</kbd> or <kbd className="px-1 py-0.5 bg-gray-800 border border-gray-600 rounded font-mono">Esc</kbd> to close
          </p>
        </div>
      </div>
    </div>
  )
}
