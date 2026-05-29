import React, { useState, useEffect, useRef } from 'react'
import { Send, Settings, Globe, Zap, LogOut, Brain, LayoutDashboard } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import LoginPage from './LoginPage'
import UpgradeModal from './UpgradeModal'

const API = import.meta.env.VITE_API_URL || ''

interface Message {
  id: string
  content: string
  sender: 'user' | 'tranc3'
  timestamp: Date
  emotion?: string
  phi?: number
  quantum_used?: boolean
}

interface Personality { id: string; name: string }

const LANGUAGES = [
  { code: 'en', name: 'English' }, { code: 'es', name: 'Español' },
  { code: 'fr', name: 'Français' }, { code: 'de', name: 'Deutsch' },
  { code: 'zh', name: '中文' }, { code: 'ja', name: '日本語' },
  { code: 'ko', name: '한국어' }, { code: 'ar', name: 'العربية' },
]

const EMOTIONS = [
  { id: 'neutral', label: 'Neutral', color: 'bg-gray-700 text-gray-300' },
  { id: 'joy', label: 'Joy', color: 'bg-yellow-900 text-yellow-300' },
  { id: 'sadness', label: 'Sadness', color: 'bg-blue-900 text-blue-300' },
  { id: 'anger', label: 'Anger', color: 'bg-red-900 text-red-300' },
  { id: 'fear', label: 'Fear', color: 'bg-purple-900 text-purple-300' },
  { id: 'surprise', label: 'Surprise', color: 'bg-pink-900 text-pink-300' },
]

export default function ChatView() {
  const [token, setToken] = useState(localStorage.getItem('tranc3_token') || '')
  const [username, setUsername] = useState(localStorage.getItem('tranc3_user') || '')
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [language, setLanguage] = useState('en')
  const [personality, setPersonality] = useState('tranc3-base')
  const [emotion, setEmotion] = useState('neutral')
  const [personalities, setPersonalities] = useState<Personality[]>([
    { id: 'tranc3-base', name: 'Base' },
    { id: 'tranc3-creative', name: 'Creative' },
    { id: 'tranc3-analytical', name: 'Analytical' },
    { id: 'tranc3-empathetic', name: 'Empathetic' },
    { id: 'tranc3-multilingual', name: 'Multilingual' },
  ])
  const [showUpgrade, setShowUpgrade] = useState(false)
  const [dark, setDark] = useState(true)
  const bottomRef = useRef<HTMLDivElement>(null)

  // Fetch personalities from API on mount — Gap G20 action
  useEffect(() => {
    if (!token) return
    fetch(`${API}/personalities`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data?.personalities) {
          setPersonalities(data.personalities.map((id: string) => ({
            id,
            name: id.replace('tranc3-', '').replace(/-/g, ' ')
              .replace(/\b\w/g, c => c.toUpperCase()),
          })))
        }
      })
      .catch(() => { })
  }, [token])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleLogin = (t: string, u: string) => {
    setToken(t)
    setUsername(u)
  }

  const logout = () => {
    localStorage.removeItem('tranc3_token')
    localStorage.removeItem('tranc3_user')
    setToken('')
    setUsername('')
    setMessages([])
  }

  const handleUpgrade = async (tier: string) => {
    try {
      const r = await fetch(`${API}/billing/checkout?tier=${tier}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (r.ok) {
        const data = await r.json()
        if (data.checkout_url) window.open(data.checkout_url, '_blank')
      }
    } catch { }
    setShowUpgrade(false)
  }

  const send = async () => {
    if (!input.trim() || loading) return
    const userMsg: Message = {
      id: Date.now().toString(), content: input,
      sender: 'user', timestamp: new Date(), emotion,
    }
    setMessages(p => [...p, userMsg])
    const text = input
    setInput('')
    setLoading(true)

    try {
      const r = await fetch(`${API}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          message: text, language, personality,
          user_emotion: emotion,
          conversation_history: messages.slice(-10).map(m => ({
            role: m.sender === 'user' ? 'user' : 'assistant',
            content: m.content,
          })),
        }),
      })

      // Handle rate limit — Gap G11 action
      if (r.status === 429) {
        setShowUpgrade(true)
        setMessages(p => p.slice(0, -1)) // remove optimistic message
        return
      }

      if (!r.ok) throw new Error('Request failed')
      const data = await r.json()

      const aiMsg: Message = {
        id: (Date.now() + 1).toString(),
        content: data.response,
        sender: 'tranc3',
        timestamp: new Date(),
        emotion: data.detected_emotion,
        phi: data.consciousness_level,
        quantum_used: data.quantum_used,
      }
      setMessages(p => [...p, aiMsg])
    } catch {
      setMessages(p => [...p, {
        id: (Date.now() + 1).toString(),
        content: 'Something went wrong. Please try again.',
        sender: 'tranc3', timestamp: new Date(),
      }])
    } finally {
      setLoading(false)
    }
  }

  if (!token) return <LoginPage onLogin={handleLogin} />

  const navigate = useNavigate()

  const bg = dark ? 'bg-gray-950 text-white' : 'bg-gray-50 text-gray-900'
  const sidebar = dark ? 'bg-gray-900 border-gray-800' : 'bg-white border-gray-200'
  const header = dark ? 'bg-gray-900 border-gray-800' : 'bg-white border-gray-200'
  const inputBg = dark ? 'bg-gray-800 border-gray-700 text-white' : 'bg-white border-gray-300 text-gray-900'
  const msgAi = dark ? 'bg-gray-800 text-white' : 'bg-white border text-gray-900'

  return (
    <div className={`flex h-screen ${bg}`}>
      {showUpgrade && <UpgradeModal onClose={() => setShowUpgrade(false)} onUpgrade={handleUpgrade} />}

      {/* Sidebar */}
      <div className={`w-72 border-r ${sidebar} flex flex-col p-4 gap-4 overflow-y-auto`}>
        <div className="flex items-center gap-2 mb-2">
          <Zap className="w-5 h-5 text-blue-400" />
          <span className="font-bold text-lg">TRANC3</span>
          <span className="ml-auto text-xs text-gray-500">{username}</span>
        </div>

        {/* Dashboard Link */}
        <button onClick={() => navigate('/dashboard')}
          className="flex items-center gap-2 text-xs text-gray-500 hover:text-blue-400 transition-colors py-2 px-2 rounded-lg hover:bg-gray-800/50">
          <LayoutDashboard className="w-3.5 h-3.5" /> Dashboard
        </button>

        {/* Language */}
        <div>
          <label className="text-xs text-gray-500 mb-1 flex items-center gap-1"><Globe className="w-3 h-3" /> Language</label>
          <select value={language} onChange={e => setLanguage(e.target.value)}
            className={`w-full rounded-lg px-3 py-2 text-sm border ${inputBg}`}>
            {LANGUAGES.map(l => <option key={l.code} value={l.code}>{l.name}</option>)}
          </select>
        </div>

        {/* Personality — dynamic from API */}
        <div>
          <label className="text-xs text-gray-500 mb-1 flex items-center gap-1"><Settings className="w-3 h-3" /> Personality</label>
          <select value={personality} onChange={e => setPersonality(e.target.value)}
            className={`w-full rounded-lg px-3 py-2 text-sm border ${inputBg}`}>
            {personalities.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>

        {/* Emotion */}
        <div>
          <label className="text-xs text-gray-500 mb-1">Your Emotion</label>
          <div className="grid grid-cols-2 gap-1">
            {EMOTIONS.map(e => (
              <button key={e.id} onClick={() => setEmotion(e.id)}
                className={`text-xs py-1 px-2 rounded-lg transition-all ${emotion === e.id ? e.color : dark ? 'bg-gray-800 text-gray-400' : 'bg-gray-100 text-gray-600'
                  }`}>
                {e.label}
              </button>
            ))}
          </div>
        </div>

        {/* Theme toggle */}
        <button onClick={() => setDark(d => !d)}
          className="text-xs text-gray-500 hover:text-gray-300 mt-auto">
          {dark ? '☀️ Light mode' : '🌙 Dark mode'}
        </button>

        <button onClick={logout}
          className="flex items-center gap-2 text-xs text-gray-500 hover:text-red-400 transition-colors">
          <LogOut className="w-3 h-3" /> Sign out
        </button>
      </div>

      {/* Chat */}
      <div className="flex-1 flex flex-col">
        <div className={`px-6 py-3 border-b ${header} flex items-center gap-3`}>
          <Brain className="w-5 h-5 text-blue-400" />
          <div>
            <div className="font-semibold">TRANC3 Conscious AI</div>
            <div className="text-xs text-gray-500">
              {personalities.find(p => p.id === personality)?.name} · {language.toUpperCase()}
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {messages.length === 0 && (
            <div className="text-center text-gray-500 mt-16">
              <Zap className="w-12 h-12 mx-auto mb-4 opacity-30" />
              <p className="text-lg font-medium">Start a conversation</p>
              <p className="text-sm mt-1">Ask anything in any language</p>
            </div>
          )}

          {messages.map(msg => (
            <div key={msg.id} className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-lg rounded-2xl px-4 py-3 ${msg.sender === 'user' ? 'bg-blue-600 text-white' : msgAi
                }`}>
                <p className="text-sm leading-relaxed">{msg.content}</p>
                <div className="flex items-center gap-2 mt-2 flex-wrap">
                  <span className="text-xs opacity-50">{msg.timestamp.toLocaleTimeString()}</span>
                  {msg.emotion && msg.emotion !== 'neutral' && (
                    <span className="text-xs opacity-60 bg-black/20 rounded px-1">{msg.emotion}</span>
                  )}
                  {/* Φ badge — RR Round 2 P7 + Gap G22 action */}
                  {msg.phi !== undefined && msg.phi !== null && (
                    <span className={`text-xs px-2 py-0.5 rounded-full font-mono ${msg.phi > 2.0 ? 'bg-purple-600 text-white' :
                        msg.phi > 1.0 ? 'bg-purple-900 text-purple-300' :
                          'bg-gray-700 text-gray-400'
                      }`}>
                      Φ {msg.phi.toFixed(2)}
                    </span>
                  )}
                  {msg.quantum_used && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-cyan-900 text-cyan-300">⚛ quantum</span>
                  )}
                </div>
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <div className={`rounded-2xl px-4 py-3 ${msgAi}`}>
                <div className="flex gap-1">
                  {[0, 1, 2].map(i => (
                    <div key={i} className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                      style={{ animationDelay: `${i * 0.15}s` }} />
                  ))}
                </div>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className={`px-6 py-4 border-t ${header}`}>
          <div className="flex gap-3">
            <input value={input} onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), send())}
              placeholder="Type a message..."
              aria-label="Message input"
              className={`flex-1 rounded-xl px-4 py-3 text-sm border focus:outline-none focus:border-blue-500 ${inputBg}`}
              disabled={loading} />
            <button onClick={send} disabled={loading || !input.trim()}
              aria-label="Send message"
              title="Send message (Enter)"
              className="bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white rounded-xl px-4 py-3 transition-colors">
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
