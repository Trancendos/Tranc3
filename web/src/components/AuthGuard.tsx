import React, { useEffect, useState } from 'react'
import { Navigate } from 'react-router'
import { useAuthStore } from '../store/authStore'

interface Props {
  children: React.ReactNode
}

export default function AuthGuard({ children }: Props) {
  const { isAuthenticated, refreshIfNeeded } = useAuthStore()
  const [checking, setChecking] = useState(true)

  useEffect(() => {
    let cancelled = false
    refreshIfNeeded().finally(() => {
      if (!cancelled) setChecking(false)
    })
    return () => { cancelled = true }
  }, [refreshIfNeeded])

  if (checking) {
    return (
      <div
        role="status"
        aria-label="Checking authentication"
        className="min-h-screen bg-background flex items-center justify-center"
      >
        <div className="flex flex-col items-center gap-3">
          <div
            className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin motion-reduce:animate-none"
            aria-hidden="true"
          />
          <p className="text-muted-foreground text-sm">Checking authentication…</p>
        </div>
      </div>
    )
  }

  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />
  }

  return <>{children}</>
}
