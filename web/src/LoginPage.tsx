import React, { useState } from 'react'
import { useNavigate } from 'react-router'
import { Loader2 } from 'lucide-react'
import { useAuthStore } from './store/authStore'

const API = import.meta.env.VITE_API_URL || ''

export default function LoginPage() {
  const navigate = useNavigate()
  const { login } = useAuthStore()

  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      if (mode === 'register') {
        const r = await fetch(`${API}/auth/register`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password }),
        })
        if (!r.ok) {
          const d = await r.json().catch(() => ({})) as { detail?: string }
          throw new Error(d.detail ?? 'Registration failed')
        }
      }
      // Use authStore.login which posts to /api/auth/login
      // Fall back to legacy token endpoint for register flow
      await login(username, password)
      navigate('/dashboard', { replace: true })
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'An error occurred'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <div className="w-full max-w-sm bg-gray-900 rounded-2xl p-8 shadow-2xl border border-gray-800">
        <div className="text-center mb-8">
          <div className="text-4xl mb-2">⚡</div>
          <h1 className="text-2xl font-bold text-white">TRANC3</h1>
          <p className="text-gray-400 text-sm mt-1">Conscious AI Platform</p>
        </div>

        <div className="flex rounded-lg bg-gray-800 p-1 mb-6">
          {(['login', 'register'] as const).map(m => (
            <button key={m} onClick={() => setMode(m)}
              className={`focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:border-transparent flex-1 py-2 rounded-md text-sm font-medium transition-all ${mode === m ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'
                }`}>
              {m === 'login' ? 'Sign In' : 'Register'}
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="space-y-4">
          <div>
            <label htmlFor="username" className="block text-sm text-gray-400 mb-1">Username / Email</label>
            <input id="username" value={username} onChange={e => setUsername(e.target.value)}
              autoComplete="username"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-transparent"
              placeholder="your_username" required />
          </div>
          <div>
            <label htmlFor="password" className="block text-sm text-gray-400 mb-1">Password</label>
            <input id="password" type="password" value={password} onChange={e => setPassword(e.target.value)}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-transparent"
              placeholder="••••••••" required />
          </div>
          {error && <p className="text-red-400 text-sm" role="alert">{error}</p>}
          <div aria-live="polite" aria-atomic="true" className="sr-only">
            {loading ? (mode === 'login' ? 'Signing In…' : 'Creating Account…') : ''}
          </div>
          <button type="submit" disabled={loading} aria-busy={loading}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-medium py-2 rounded-lg transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:border-transparent flex justify-center items-center">
            {loading && <Loader2 className="w-4 h-4 mr-2 animate-spin inline" />}
            {loading ? (mode === 'login' ? 'Signing In...' : 'Creating Account...') : (mode === 'login' ? 'Sign In' : 'Create Account')}
          </button>
        </form>

        <p className="text-center text-gray-600 text-xs mt-6">
          Free tier: 100 requests/hour
        </p>
      </div>
    </div>
  )
}
