import React, { useState } from 'react'

interface Props {
    onLogin: (token: string, username: string) => void
}

const API = import.meta.env.VITE_API_URL || ''

export default function LoginPage({ onLogin }: Props) {
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
                    const d = await r.json()
                    throw new Error(d.detail || 'Registration failed')
                }
            }
            const r = await fetch(`${API}/auth/token`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password }),
            })
            if (!r.ok) {
                const d = await r.json()
                throw new Error(d.detail || 'Login failed')
            }
            const data = await r.json()
            localStorage.setItem('tranc3_token', data.access_token)
            localStorage.setItem('tranc3_user', username)
            onLogin(data.access_token, username)
        } catch (err: any) {
            setError(err.message)
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
                            className={`flex-1 py-2 rounded-md text-sm font-medium transition-all ${mode === m ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'
                                }`}>
                            {m === 'login' ? 'Sign In' : 'Register'}
                        </button>
                    ))}
                </div>

                <form onSubmit={submit} className="space-y-4">
                    <div>
                        <label className="block text-sm text-gray-400 mb-1">Username</label>
                        <input value={username} onChange={e => setUsername(e.target.value)}
                            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
                            placeholder="your_username" required />
                    </div>
                    <div>
                        <label className="block text-sm text-gray-400 mb-1">Password</label>
                        <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
                            placeholder="••••••••" required />
                    </div>
                    {error && <p className="text-red-400 text-sm">{error}</p>}
                    <button type="submit" disabled={loading}
                        className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-medium py-2 rounded-lg transition-colors">
                        {loading ? '...' : mode === 'login' ? 'Sign In' : 'Create Account'}
                    </button>
                </form>

                <p className="text-center text-gray-600 text-xs mt-6">
                    Free tier: 100 requests/hour
                </p>
            </div>
        </div>
    )
}
