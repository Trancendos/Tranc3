import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface AuthUser {
  id: string
  name: string
  email: string
  role: string
}

interface AuthState {
  token: string | null
  user: AuthUser | null
  expiresAt: number | null
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  isAuthenticated: () => boolean
  refreshIfNeeded: () => Promise<void>
}

const API = import.meta.env.VITE_API_URL || ''
const FIVE_MINUTES = 5 * 60 * 1000

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      expiresAt: null,

      login: async (email: string, password: string) => {
        const r = await fetch(`${API}/api/auth/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        })
        if (!r.ok) {
          const d = await r.json().catch(() => ({})) as { detail?: string }
          throw new Error(d.detail ?? 'Login failed')
        }
        const data = await r.json() as {
          access_token: string
          expires_in?: number
          user?: AuthUser
        }
        const expiresAt = Date.now() + (data.expires_in ?? 3600) * 1000
        set({
          token: data.access_token,
          expiresAt,
          user: data.user ?? null,
        })
      },

      logout: () => {
        set({ token: null, user: null, expiresAt: null })
      },

      isAuthenticated: () => {
        const { token, expiresAt } = get()
        return token != null && Date.now() < (expiresAt ?? 0)
      },

      refreshIfNeeded: async () => {
        const { token, expiresAt } = get()
        if (!token || !expiresAt) return
        if (expiresAt - Date.now() >= FIVE_MINUTES) return
        try {
          const r = await fetch(`${API}/api/auth/refresh`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${token}`,
            },
          })
          if (!r.ok) return
          const data = await r.json() as {
            access_token: string
            expires_in?: number
          }
          set({
            token: data.access_token,
            expiresAt: Date.now() + (data.expires_in ?? 3600) * 1000,
          })
        } catch {
          // Silently ignore refresh failures — let the token expire naturally
        }
      },
    }),
    {
      name: 'tranc3-auth',
      partialize: (state) => ({
        token: state.token,
        user: state.user,
        expiresAt: state.expiresAt,
      }),
    }
  )
)
