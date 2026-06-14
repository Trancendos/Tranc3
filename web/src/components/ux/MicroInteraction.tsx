/**
 * MicroInteraction — UpSlide: Micro-interaction Design Patterns
 *                  + Impala: Delightful Responsive Feedback
 *                  + IxDF: Emotional Design via Functional Animation
 *
 * Wraps any element with contextual micro-interaction responses:
 *   ripple   — material-style radial ripple on click (touch-friendly)
 *   pulse    — attention pulse (for new/changed content)
 *   shake    — error shake (wrong input, denied action)
 *   bounce   — success bounce (completion, positive feedback)
 *   glow     — highlight glow (selection, focus draw)
 *   breathe  — idle breathing animation (loading, processing)
 *
 * Micro-interactions serve a dual purpose:
 *   1. Functional: confirm actions, indicate state, guide attention
 *   2. Emotional: delight, reduce anxiety, communicate personality
 *
 * Principle: animation duration must match action weight.
 * Quick confirmations → 100–200ms. State transitions → 300–500ms.
 * Celebrations → 600–800ms. Never exceed 1s for functional feedback.
 */
import React, { useCallback, useId, useRef, useState } from 'react'

type MicroEffect = 'ripple' | 'pulse' | 'shake' | 'bounce' | 'glow' | 'breathe'

interface MicroInteractionProps {
  children: React.ReactNode
  effect: MicroEffect
  /** Trigger programmatically — increment to replay */
  trigger?: number
  /** For ripple: trigger on click automatically */
  autoRipple?: boolean
  color?: string
  className?: string
  style?: React.CSSProperties
  as?: keyof JSX.IntrinsicElements
}

const KEYFRAMES: Record<Exclude<MicroEffect, 'ripple'>, string> = {
  pulse:   'ux-mi-pulse',
  shake:   'ux-mi-shake',
  bounce:  'ux-mi-bounce',
  glow:    'ux-mi-glow',
  breathe: 'ux-mi-breathe',
}

const DURATIONS: Record<MicroEffect, number> = {
  ripple:  400,
  pulse:   400,
  shake:   400,
  bounce:  500,
  glow:    600,
  breathe: 2000,
}

export function MicroInteraction({
  children,
  effect,
  trigger,
  autoRipple = true,
  color = 'var(--ux-accent)',
  className = '',
  style,
  as: Tag = 'div',
}: MicroInteractionProps) {
  const ref = useRef<HTMLElement>(null)
  const [ripples, setRipples] = useState<Array<{ id: string; x: number; y: number }>>([])
  const [animKey, setAnimKey] = useState(0)
  const id = useId()

  const prevTrigger = useRef(trigger)
  if (trigger !== prevTrigger.current) {
    prevTrigger.current = trigger
    if (effect !== 'ripple') setAnimKey(k => k + 1)
  }

  const addRipple = useCallback((e: React.MouseEvent<HTMLElement>) => {
    if (effect !== 'ripple' || !autoRipple) return
    const rect = e.currentTarget.getBoundingClientRect()
    const rippleId = `${id}-${Date.now()}`
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    setRipples(prev => [...prev, { id: rippleId, x, y }])
    setTimeout(() => setRipples(prev => prev.filter(r => r.id !== rippleId)), DURATIONS.ripple)
  }, [effect, autoRipple, id])

  const animClass = effect !== 'ripple' && animKey > 0 ? KEYFRAMES[effect as keyof typeof KEYFRAMES] : ''
  const isContinuous = effect === 'breathe'

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const TagAny = Tag as any
  return (
    <TagAny
      ref={ref}
      className={`ux-micro-interaction ${className} ${isContinuous ? KEYFRAMES.breathe : animClass}`}
      key={effect !== 'ripple' && !isContinuous ? animKey : undefined}
      onClick={addRipple}
      style={{
        position: 'relative',
        overflow: effect === 'ripple' ? 'hidden' : undefined,
        display: 'inline-block',
        ...style,
      }}
    >
      {children}
      {effect === 'ripple' && ripples.map(r => (
        <span
          key={r.id}
          aria-hidden="true"
          style={{
            position: 'absolute',
            left: r.x,
            top: r.y,
            width: '4px',
            height: '4px',
            borderRadius: '50%',
            background: color,
            opacity: 0.4,
            transform: 'translate(-50%, -50%) scale(0)',
            animation: `ux-mi-ripple-expand ${DURATIONS.ripple}ms var(--ux-ease-out) forwards`,
            pointerEvents: 'none',
          }}
        />
      ))}
    </TagAny>
  )
}

/** Inject micro-interaction keyframes once into the document head */
if (typeof document !== 'undefined') {
  const styleId = 'ux-micro-interaction-keyframes'
  if (!document.getElementById(styleId)) {
    const style = document.createElement('style')
    style.id = styleId
    style.textContent = `
      @keyframes ux-mi-ripple-expand {
        to { transform: translate(-50%, -50%) scale(60); opacity: 0; }
      }
      @keyframes ux-mi-pulse {
        0%, 100% { transform: scale(1); }
        50% { transform: scale(1.04); }
      }
      @keyframes ux-mi-shake {
        0%, 100% { transform: translateX(0); }
        20% { transform: translateX(-6px); }
        40% { transform: translateX(6px); }
        60% { transform: translateX(-4px); }
        80% { transform: translateX(4px); }
      }
      @keyframes ux-mi-bounce {
        0%, 100% { transform: translateY(0); }
        30% { transform: translateY(-8px); }
        60% { transform: translateY(-3px); }
        80% { transform: translateY(-5px); }
      }
      @keyframes ux-mi-glow {
        0%, 100% { box-shadow: 0 0 0 0 rgba(var(--ux-brand-rgb, 37 99 235), 0); }
        50% { box-shadow: 0 0 0 8px rgba(var(--ux-brand-rgb, 37 99 235), 0.18); }
      }
      @keyframes ux-mi-breathe {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.55; }
      }
      .ux-mi-pulse  { animation: ux-mi-pulse  400ms var(--ux-ease-out, ease-out) both; }
      .ux-mi-shake  { animation: ux-mi-shake  400ms var(--ux-ease-out, ease-out) both; }
      .ux-mi-bounce { animation: ux-mi-bounce 500ms var(--ux-ease-out, ease-out) both; }
      .ux-mi-glow   { animation: ux-mi-glow   600ms var(--ux-ease-out, ease-out) both; }
      .ux-mi-breathe { animation: ux-mi-breathe 2s ease-in-out infinite; }
      @media (prefers-reduced-motion: reduce) {
        .ux-mi-pulse, .ux-mi-shake, .ux-mi-bounce, .ux-mi-glow, .ux-mi-breathe {
          animation: none !important;
        }
      }
    `
    document.head.appendChild(style)
  }
}
