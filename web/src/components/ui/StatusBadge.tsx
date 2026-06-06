import React from 'react'
import { CheckCircle, XCircle, AlertCircle, Loader } from 'lucide-react'

export type HealthStatus = 'ok' | 'degraded' | 'down' | 'unknown' | 'checking'

const CONFIG: Record<HealthStatus, { icon: React.ReactNode; label: string; color: string }> = {
  ok:       { icon: <CheckCircle size={16} aria-hidden="true" />, label: 'Online',   color: 'text-green-400' },
  degraded: { icon: <AlertCircle  size={16} aria-hidden="true" />, label: 'Degraded', color: 'text-yellow-400' },
  down:     { icon: <XCircle      size={16} aria-hidden="true" />, label: 'Down',     color: 'text-red-400' },
  unknown:  { icon: <AlertCircle  size={16} aria-hidden="true" />, label: 'Unknown',  color: 'text-gray-500' },
  checking: { icon: <Loader       size={16} aria-hidden="true" className="animate-spin" />, label: 'Checking', color: 'text-gray-400' },
}

interface Props {
  status: HealthStatus
  showLabel?: boolean
}

export function StatusBadge({ status, showLabel = true }: Props) {
  const { icon, label, color } = CONFIG[status]
  return (
    <span className={`inline-flex items-center gap-1.5 ${color}`} aria-label={label}>
      {icon}
      {showLabel && <span className="capitalize text-sm">{label}</span>}
      <span className="sr-only">{label}</span>
    </span>
  )
}

export function statusColor(s: HealthStatus) {
  return CONFIG[s]?.color ?? 'text-gray-500'
}
