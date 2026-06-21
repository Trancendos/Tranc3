import React, { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router'
import { Loader2 } from 'lucide-react'
import { useAuthStore } from './store/authStore'

const API = import.meta.env.VITE_API_URL || ''

interface HealthStatus {
  api: 'green' | 'amber' | 'red'
  auth: 'green' | 'amber' | 'red'
  ai: 'green' | 'amber' | 'red'
}

const DOT: Record<'green' | 'amber' | 'red', string> = {
  green: 'bg-green-400',
  amber: 'bg-yellow-400',
  red: 'bg-red-500',
}

const FEATURES = [
  { name: 'The Spark', subtitle: 'AI Tool Registry', icon: '⚡', desc: 'JSON-RPC 2.0 MCP server — discover, invoke and compose AI tools across the platform.' },
  { name: 'Luminous', subtitle: 'AI Brain', icon: '🧠', desc: 'Core intelligence & orchestration engine powered by bio-neural consciousness processing.' },
  { name: 'The Digital Grid', subtitle: 'Workflows', icon: '⬡', desc: 'Visual DAG workflow builder with topological execution and parallel layer processing.' },
  { name: 'The HIVE', subtitle: 'Data Transport', icon: '🐝', desc: 'Priority task queue with retry logic, DLQ, and real-time agent coordination.' },
  { name: 'Royal Bank', subtitle: 'Financials', icon: '🏦', desc: 'Full financial ledger — accounts, transfers, deposits and platform-wide AUM reporting.' },
  { name: 'The Observatory', subtitle: 'Audit & Metrics', icon: '🔭', desc: 'Every action, change and event on Trancendos — immutable audit log with live metrics.' },
]

export default function LoginPage() {
  const navigate = useNavigate()
  const { login } = useAuthStore()

  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [health, setHealth] = useState<HealthStatus>({ api: 'amber', auth: 'amber', ai: 'amber' })

  useEffect(() => {
    const check = async () => {
      try {
        const r = await fetch(`${API}/health`, { signal: AbortSignal.timeout(4000) })
        const data = r.ok ? await r.json().catch(() => ({})) : {}
        setHealth({
          api: r.ok ? 'green' : 'red',
          auth: data.auth === false ? 'amber' : r.ok ? 'green' : 'red',
          ai: data.ai_ready === false ? 'amber' : r.ok ? 'green' : 'red',
        })
      } catch {
        setHealth({ api: 'red', auth: 'red', ai: 'red' })
      }
    }
    check()
  }, [])

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
    <div className="min-h-screen bg-gray-950 text-white overflow-x-hidden">
      {/* Animated gradient hero */}
      <div className="relative overflow-hidden">
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: 'radial-gradient(ellipse 80% 60% at 50% -10%, rgba(37,99,235,0.35) 0%, transparent 70%)',
            animation: 'pulse-glow 6s ease-in-out infinite',
          }}
        />
        <style>{`
          @keyframes pulse-glow {
            0%, 100% { opacity: 0.7; transform: scale(1); }
            50% { opacity: 1; transform: scale(1.08); }
          }
          @keyframes gradient-shift {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
          }
          .animated-gradient {
            background: linear-gradient(270deg, #1e3a8a, #1d4ed8, #0ea5e9, #7c3aed, #1d4ed8);
            background-size: 300% 300%;
            animation: gradient-shift 10s ease infinite;
          }
          @keyframes float-dot {
            0%, 100% { transform: translateY(0px); }
            50% { transform: translateY(-8px); }
          }
        `}</style>

        <div className="relative z-10 flex flex-col lg:flex-row min-h-screen">
          {/* Left — hero + features */}
          <div className="flex-1 flex flex-col px-6 py-12 lg:px-16 lg:py-16">
            {/* Brand */}
            <div className="mb-12">
              <div className="flex items-center gap-3 mb-4">
                <span className="text-4xl" style={{ animation: 'float-dot 3s ease-in-out infinite' }}>⚡</span>
                <h1
                  className="text-5xl lg:text-6xl font-black tracking-tight"
                  style={{
                    background: 'linear-gradient(135deg, #fff 30%, #93c5fd 70%)',
                    WebkitBackgroundClip: 'text',
                    WebkitTextFillColor: 'transparent',
                    backgroundClip: 'text',
                  }}
                >
                  Trancendos
                </h1>
              </div>
              <p className="text-xl lg:text-2xl text-blue-300 font-light tracking-wide">
                The Conscious AI Platform
              </p>
              <p className="mt-4 text-gray-400 max-w-xl text-sm leading-relaxed">
                43 interconnected services. Self-hosted, zero-cost architecture. Full sovereignty over your AI infrastructure.
              </p>
            </div>

            {/* Platform Status bar */}
            <div className="mb-10 flex flex-wrap gap-4">
              {([
                { label: 'API', key: 'api' as const },
                { label: 'Auth', key: 'auth' as const },
                { label: 'AI Core', key: 'ai' as const },
              ]).map(({ label, key }) => (
                <div key={key} className="flex items-center gap-2 bg-gray-900/70 border border-gray-800 rounded-full px-4 py-1.5 text-xs">
                  <span className={`w-2 h-2 rounded-full ${DOT[health[key]]}`} style={health[key] === 'green' ? { boxShadow: '0 0 6px #4ade80' } : {}} />
                  <span className="text-gray-300">{label}</span>
                  <span className={`font-medium ${health[key] === 'green' ? 'text-green-400' : health[key] === 'amber' ? 'text-yellow-400' : 'text-red-400'}`}>
                    {health[key] === 'green' ? 'Online' : health[key] === 'amber' ? 'Checking' : 'Offline'}
                  </span>
                </div>
              ))}
            </div>

            {/* Feature grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4 mb-8">
              {FEATURES.map(f => (
                <div
                  key={f.name}
                  className="group bg-gray-900/60 border border-gray-800 hover:border-blue-700/60 rounded-xl p-4 transition-all duration-200 hover:bg-gray-900/90"
                >
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xl">{f.icon}</span>
                    <div>
                      <div className="text-sm font-semibold text-white leading-none">{f.name}</div>
                      <div className="text-xs text-blue-400">{f.subtitle}</div>
                    </div>
                  </div>
                  <p className="text-xs text-gray-500 group-hover:text-gray-400 transition-colors leading-relaxed">{f.desc}</p>
                </div>
              ))}
            </div>

            <p className="text-xs text-gray-600 mt-auto">
              <Link to="/" className="hover:text-gray-400 transition-colors">← Back to home</Link>
            </p>
          </div>

          {/* Right — auth panel */}
          <div className="lg:w-[420px] flex items-center justify-center p-6 lg:p-12 bg-gray-950/80 border-t lg:border-t-0 lg:border-l border-gray-800">
            <div className="w-full max-w-sm">
              <div className="text-center mb-8">
                <h2 className="text-2xl font-bold text-white">Welcome back</h2>
                <p className="text-gray-500 text-sm mt-1">Sign in to access the platform</p>
              </div>

              {/* Tabs */}
              <div className="flex rounded-lg bg-gray-900 border border-gray-800 p-1 mb-6">
                {(['login', 'register'] as const).map(m => (
                  <button
                    key={m}
                    onClick={() => { setMode(m); setError('') }}
                    className={`flex-1 py-2 rounded-md text-sm font-medium transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
                      mode === m
                        ? 'animated-gradient text-white shadow-sm'
                        : 'text-gray-400 hover:text-white'
                    }`}
                  >
                    {m === 'login' ? 'Sign In' : 'Register'}
                  </button>
                ))}
              </div>

              <form onSubmit={submit} className="space-y-4">
                <div>
                  <label htmlFor="username" className="block text-sm text-gray-400 mb-1.5">
                    Username / Email
                  </label>
                  <input
                    id="username"
                    value={username}
                    onChange={e => setUsername(e.target.value)}
                    autoComplete="username"
                    className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-600 transition-colors placeholder-gray-600"
                    placeholder="your_username"
                    required
                  />
                </div>
                <div>
                  <label htmlFor="password" className="block text-sm text-gray-400 mb-1.5">
                    Password
                  </label>
                  <input
                    id="password"
                    type="password"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                    className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-600 transition-colors placeholder-gray-600"
                    placeholder="••••••••"
                    required
                  />
                </div>

                {error && (
                  <p className="text-red-400 text-sm bg-red-950/40 border border-red-800/40 rounded-lg px-3 py-2" role="alert">
                    {error}
                  </p>
                )}

                <div aria-live="polite" aria-atomic="true" className="sr-only">
                  {loading ? (mode === 'login' ? 'Signing In…' : 'Creating Account…') : ''}
                </div>

                <button
                  type="submit"
                  disabled={loading}
                  aria-busy={loading}
                  className="w-full animated-gradient hover:opacity-90 disabled:opacity-50 text-white font-semibold py-2.5 rounded-lg transition-opacity focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 flex justify-center items-center gap-2 mt-2"
                >
                  {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                  {loading
                    ? (mode === 'login' ? 'Signing In...' : 'Creating Account...')
                    : (mode === 'login' ? 'Sign In' : 'Create Account')}
                </button>
              </form>

              <p className="text-center text-gray-600 text-xs mt-6">
                Free tier · 100 requests / hour · Zero vendor lock-in
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
