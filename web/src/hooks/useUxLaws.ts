/**
 * Tranc3 UX Laws Hook Library
 *
 * Each hook encodes a specific Law of UX as reactive, composable behaviour.
 * Import only what you need — tree-shakeable by design.
 */

import { useState, useEffect, useRef, useCallback, useMemo } from 'react'

/* ── Doherty Threshold ───────────────────────────────────────────────────────
   Productivity peaks when neither user nor system waits.
   Shows content immediately; only shows skeleton after 100ms.
   This prevents skeleton flash on fast responses (< 100ms).            */
export function useDoherty(isLoading: boolean, delayMs = 100) {
  const [showSkeleton, setShowSkeleton] = useState(false)
  useEffect(() => {
    if (!isLoading) { setShowSkeleton(false); return }
    const t = setTimeout(() => setShowSkeleton(true), delayMs)
    return () => clearTimeout(t)
  }, [isLoading, delayMs])
  return showSkeleton
}

/* ── Fitts's Law ─────────────────────────────────────────────────────────────
   Time to target ∝ distance / size.
   Returns ARIA + size props for a button based on its importance.      */
export type FittsImportance = 'primary' | 'secondary' | 'tertiary'

export function useFitts(importance: FittsImportance = 'secondary') {
  return useMemo(() => ({
    className: `ux-fitts-${importance}`,
    'data-importance': importance,
  }), [importance])
}

/* ── Hick's Law ──────────────────────────────────────────────────────────────
   Decision time grows with number + complexity of choices.
   Returns visible items (max 7) and a toggle to reveal the rest.      */
export function useHicks<T>(items: T[], maxVisible = 7) {
  const [expanded, setExpanded] = useState(false)
  const visible = expanded ? items : items.slice(0, maxVisible)
  const hasMore = items.length > maxVisible
  const toggle = useCallback(() => setExpanded(e => !e), [])
  return { visible, hasMore, expanded, toggle, hiddenCount: items.length - maxVisible }
}

/* ── Miller's Law ────────────────────────────────────────────────────────────
   Average person holds 7 ± 2 items in working memory.
   Chunks an array into groups of chunkSize (default 7).               */
export function useMiller<T>(items: T[], chunkSize = 7): T[][] {
  return useMemo(() => {
    const chunks: T[][] = []
    for (let i = 0; i < items.length; i += chunkSize) {
      chunks.push(items.slice(i, i + chunkSize))
    }
    return chunks
  }, [items, chunkSize])
}

/* ── Goal-Gradient Effect ────────────────────────────────────────────────────
   Motivation increases as goal proximity increases.
   Returns progress metadata including "near completion" signals.       */
export function useGoalGradient(current: number, total: number) {
  const percent = total > 0 ? Math.round((current / total) * 100) : 0
  const completion: 'low' | 'medium' | 'high' = percent < 33 ? 'low' : percent < 75 ? 'medium' : 'high'
  const isComplete = total > 0 && current >= total
  return { percent, completion, isComplete, remaining: total - current }
}

/* ── Zeigarnik Effect ────────────────────────────────────────────────────────
   Incomplete tasks are remembered better than completed ones.
   Surfaces incomplete items and tracks completion state.               */
export function useZeigarnik<T extends { id: string | number; completed?: boolean }>(items: T[]) {
  const incomplete = useMemo(() => items.filter(i => !i.completed), [items])
  const complete   = useMemo(() => items.filter(i =>  i.completed), [items])
  const percent    = items.length > 0 ? Math.round((complete.length / items.length) * 100) : 0
  return { incomplete, complete, percent, hasIncomplete: incomplete.length > 0 }
}

/* ── Peak-End Rule ───────────────────────────────────────────────────────────
   Experiences judged by peak moment + end moment, not average.
   Triggers a celebratory animation at key positive moments.           */
export function usePeakEnd() {
  const [celebrating, setCelebrating] = useState(false)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const celebrate = useCallback(() => {
    setCelebrating(true)
    if (timeoutRef.current) clearTimeout(timeoutRef.current)
    timeoutRef.current = setTimeout(() => {
      setCelebrating(false)
      timeoutRef.current = null
    }, 700)
  }, [])

  useEffect(() => () => { if (timeoutRef.current) clearTimeout(timeoutRef.current) }, [])

  return { celebrating, celebrate, celebrateClass: celebrating ? 'ux-peak-celebrate' : '' }
}

/* ── Aesthetic-Usability Effect ─────────────────────────────────────────────
   Visually appealing designs are perceived as more usable.
   Provides a hover/focus elevation state for interactive surfaces.    */
export function useAesthetic() {
  const [elevated, setElevated] = useState(false)
  const props = useMemo(() => ({
    'data-interactive': 'true' as const,
    onMouseEnter: () => setElevated(true),
    onMouseLeave: () => setElevated(false),
    onFocus:      () => setElevated(true),
    onBlur:       () => setElevated(false),
  }), [])
  return { elevated, props }
}

/* ── Serial Position Effect ──────────────────────────────────────────────────
   First and last items in a series are best remembered.
   Returns position metadata for list rendering decisions.             */
export function useSerialPosition<T>(items: T[]) {
  return useMemo(() => items.map((item, index) => ({
    item,
    index,
    isFirst: index === 0,
    isLast:  index === items.length - 1,
    isPrime: index === 0 || index === items.length - 1,
    position: index + 1,
  })), [items])
}

/* ── Von Restorff Effect ─────────────────────────────────────────────────────
   Distinctive items are more memorable.
   Returns a className token that applies the highlight style.         */
export function useVonRestorff(highlighted: boolean) {
  return highlighted ? 'ux-restorff-highlight' : ''
}

/* ── Cognitive Load ──────────────────────────────────────────────────────────
   Minimise mental resources needed.
   Progressive disclosure: tracks which sections are expanded.         */
export function useCognitiveLoad(sections: string[]) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set(sections))
  const toggle = useCallback((id: string) => {
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }, [])
  const isExpanded = useCallback((id: string) => expanded.has(id), [expanded])
  return { isExpanded, toggle, expandedIds: expanded }
}

/* ── Working Memory ──────────────────────────────────────────────────────────
   Keep active information accessible.
   Sticky context: tracks scroll position to show/hide anchors.        */
export function useWorkingMemory(threshold = 60) {
  const [anchored, setAnchored] = useState(false)
  useEffect(() => {
    const handler = () => setAnchored(window.scrollY > threshold)
    window.addEventListener('scroll', handler, { passive: true })
    return () => window.removeEventListener('scroll', handler)
  }, [threshold])
  return anchored
}

/* ── Tesler's Law ────────────────────────────────────────────────────────────
   Every system has irreducible complexity — absorb it from the user.
   Smart form state: handles validation, dirty tracking, error display. */
export interface TeslerFieldState {
  value: string
  dirty: boolean
  error: string | null
  valid: boolean
}

export function useTesler(
  validate?: (v: string) => string | null,
  initialValue = '',
) {
  const [state, setState] = useState<TeslerFieldState>({
    value: initialValue,
    dirty: false,
    error: null,
    valid: !validate || !validate(initialValue),
  })

  const onChange = useCallback((value: string) => {
    const error = validate ? validate(value) : null
    setState({ value, dirty: true, error, valid: !error })
  }, [validate])

  const reset = useCallback(() => {
    setState({ value: initialValue, dirty: false, error: null, valid: !validate || !validate(initialValue) })
  }, [initialValue, validate])

  return { ...state, onChange, reset }
}

/* ── Postel's Law ────────────────────────────────────────────────────────────
   Be liberal in what you accept, conservative in what you send.
   Normalises user input (trim, lowercase, strip extra spaces).        */
export function usePostel() {
  const normalise = useCallback((raw: string) => raw.trim().replace(/\s+/g, ' '), [])
  const normaliseLower = useCallback((raw: string) => normalise(raw).toLowerCase(), [normalise])
  return { normalise, normaliseLower }
}

/* ── Selective Attention ─────────────────────────────────────────────────────
   Focus attention on goal-relevant stimuli.
   Returns props to apply reduced-opacity dimming on sibling elements. */
export function useSelectiveAttention() {
  const [focusedId, setFocusedId] = useState<string | null>(null)
  const getProps = useCallback((id: string) => ({
    'data-focused': focusedId === id ? 'true' : undefined,
    style: focusedId && focusedId !== id ? { opacity: 0.4, transition: `opacity 150ms ease` } : undefined,
    onMouseEnter: () => setFocusedId(id),
    onMouseLeave: () => setFocusedId(null),
    onFocus:      () => setFocusedId(id),
    onBlur:       () => setFocusedId(null),
  }), [focusedId])
  return { focusedId, getProps }
}

/* ── Pareto Principle ────────────────────────────────────────────────────────
   80% of effects from 20% of causes.
   Sorts items by a metric and returns the top 20%.                    */
export function usePareto<T>(items: T[], metric: (item: T) => number) {
  return useMemo(() => {
    const sorted = [...items].sort((a, b) => metric(b) - metric(a))
    const topCount = Math.max(1, Math.ceil(items.length * 0.2))
    return { top: sorted.slice(0, topCount), rest: sorted.slice(topCount), sorted }
  }, [items, metric])
}

/* ── Flow State ──────────────────────────────────────────────────────────────
   Complete immersion in an activity.
   Detects idle/active state and reduces UI chrome in active reading.  */
export function useFlow(idleMs = 3000) {
  const [inFlow, setInFlow] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout>>()
  useEffect(() => {
    const activate = () => {
      setInFlow(false)
      clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => setInFlow(true), idleMs)
    }
    const events = ['mousemove','keydown','scroll','touchstart']
    events.forEach(e => window.addEventListener(e, activate, { passive: true }))
    return () => {
      events.forEach(e => window.removeEventListener(e, activate))
      clearTimeout(timerRef.current)
    }
  }, [idleMs])
  return inFlow
}

/* ── Jakob's Law ─────────────────────────────────────────────────────────────
   Users expect your site to work like others they know.
   Returns conventional keyboard navigation handlers (arrow keys etc). */
export function useJakob(itemCount: number, orientation: 'horizontal' | 'vertical' = 'vertical') {
  const [activeIndex, setActiveIndex] = useState(0)
  const onKeyDown = useCallback((e: React.KeyboardEvent) => {
    const nextKey = orientation === 'vertical' ? 'ArrowDown' : 'ArrowRight'
    const prevKey = orientation === 'vertical' ? 'ArrowUp'   : 'ArrowLeft'
    if (e.key === nextKey) { e.preventDefault(); setActiveIndex(i => (i + 1) % itemCount) }
    if (e.key === prevKey) { e.preventDefault(); setActiveIndex(i => (i - 1 + itemCount) % itemCount) }
    if (e.key === 'Home')  { e.preventDefault(); setActiveIndex(0) }
    if (e.key === 'End')   { e.preventDefault(); setActiveIndex(itemCount - 1) }
  }, [itemCount, orientation])
  return { activeIndex, setActiveIndex, onKeyDown }
}
