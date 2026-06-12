/**
 * ProgressBar — Zeigarnik + Goal-Gradient Effect
 *
 * Shows incomplete tasks prominently, accelerates animation near completion,
 * and celebrates with a pulse when reaching 100%.
 */
import React from 'react'
import { useGoalGradient, usePeakEnd } from '../../hooks/useUxLaws'

interface ProgressBarProps {
  current: number
  total: number
  label?: string
  showPercent?: boolean
  className?: string
}

export function ProgressBar({ current, total, label, showPercent = true, className = '' }: ProgressBarProps) {
  const { percent, completion, isComplete } = useGoalGradient(current, total)
  const { celebrate, celebrateClass } = usePeakEnd()

  React.useEffect(() => {
    if (isComplete) celebrate()
  }, [isComplete, celebrate])

  return (
    <div className={`ux-flex-col ux-gap-1 ${className}`} role="group" aria-label={label ?? 'Progress'}>
      {(label || showPercent) && (
        <div className="ux-flex ux-items-center ux-justify-between">
          {label && <span className="ux-attention-meta">{label}</span>}
          {showPercent && (
            <span
              className={`ux-attention-meta ${celebrateClass}`}
              aria-live="polite"
              aria-atomic="true"
            >
              {percent}%
            </span>
          )}
        </div>
      )}
      <div
        className="ux-progress-track"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label ? `${label}: ${percent}%` : `${percent}%`}
      >
        <div
          className={`ux-progress-fill ${isComplete ? 'ux-peak-success-ring' : ''}`}
          data-completion={completion}
          style={{ width: `${percent}%` }}
        />
      </div>
      {isComplete && (
        <span className="ux-postel-success" role="status">
          Complete
        </span>
      )}
    </div>
  )
}
