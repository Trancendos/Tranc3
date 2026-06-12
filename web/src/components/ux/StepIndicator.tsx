/**
 * StepIndicator — Goal-Gradient Effect + Serial Position Effect
 *
 * Step-based progress wizard. Earlier steps use "recency" primacy;
 * the current step shows proximity-to-goal excitement.
 */
import React from 'react'

interface Step {
  id: string
  label: string
}

interface StepIndicatorProps {
  steps: Step[]
  currentStep: number
  className?: string
}

export function StepIndicator({ steps, currentStep: rawStep, className = '' }: StepIndicatorProps) {
  const currentStep = Math.min(steps.length, Math.max(0, rawStep))
  return (
    <nav aria-label="Progress steps" className={className}>
      <ol className="ux-goal-steps" role="list">
        {steps.map((step, i) => {
          const status = i < currentStep ? 'complete' : i === currentStep ? 'active' : 'pending'
          return (
            <li
              key={step.id}
              className="ux-goal-step"
              data-status={status}
              aria-current={i === currentStep ? 'step' : undefined}
            >
              <div
                className="ux-goal-step-dot"
                aria-hidden="true"
              >
                {status === 'complete' ? '✓' : i + 1}
              </div>
              <span className="ux-attention-meta" style={{ textAlign: 'center', maxWidth: '80px' }}>
                {step.label}
              </span>
              <span className="ux-sr-only">
                {status === 'complete' ? 'Completed: ' : status === 'active' ? 'Current: ' : 'Upcoming: '}
                {step.label}
              </span>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
