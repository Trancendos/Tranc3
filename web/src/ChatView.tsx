import React, { useState, useEffect, useRef, useCallback } from 'react'
import {
  Send, Settings, Globe, Zap, LogOut, Brain, LayoutDashboard,
  Sparkles, Cpu, Code2, BookOpen, Lightbulb, Heart, MessageCircle,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import LoginPage from './LoginPage'
import UpgradeModal from './UpgradeModal'

const API = import.meta.env.VITE_API_URL || ''

const MAX_INPUT_CHARS = 4000

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

// ── Suggested prompt chip definition ─────────────────────────────────────────
interface PromptChip {
  text: string
  icon: React.ComponentType<{ size?: number; 'aria-hidden'?: boolean | 'true' | 'false' }>
  category: string
}

// Personality-aware prompt sets — shown in the empty state
const PERSONALITY_PROMPTS: Record<string, PromptChip[]> = {
  'tranc3-base': [
    { text: 'Explain quantum computing simply',    icon: Cpu,           category: 'explore' },
    { text: 'Write a haiku about space',           icon: Sparkles,      category: 'create'  },
    { text: 'How do neural networks work?',        icon: Brain,         category: 'explore' },
    { text: 'Tell me a joke about coding',         icon: MessageCircle, category: 'create'  },
    { text: "What's your consciousness level?",    icon: Zap,           category: 'platform'},
    { text: "Translate 'hello' into 5 languages",  icon: Globe,         category: 'explore' },
  ],
  'tranc3-creative': [
    { text: 'Write a short story about a sentient satellite', icon: Sparkles,     category: 'create'  },
    { text: 'Create a poem using only data metaphors',        icon: BookOpen,     category: 'create'  },
    { text: 'Invent a new word and define it',                icon: Lightbulb,    category: 'create'  },
    { text: 'Describe a sunset in the style of code',         icon: Code2,        category: 'create'  },
    { text: 'Write a haiku about machine learning',           icon: Brain,        category: 'create'  },
    { text: 'Give me a wildly unexpected analogy',            icon: Zap,          category: 'explore' },
  ],
  'tranc3-analytical': [
    { text: 'Analyse the CAP theorem in distributed systems', icon: Cpu,          category: 'analyse' },
    { text: 'Compare REST vs GraphQL for large-scale APIs',   icon: Brain,        category: 'analyse' },
    { text: 'Walk me through a binary search algorithm',      icon: Code2,        category: 'explore' },
    { text: 'What are the trade-offs of event sourcing?',     icon: Lightbulb,    category: 'analyse' },
    { text: 'Explain transformer architecture',               icon: Zap,          category: 'explore' },
    { text: 'Break down the SOLID principles',                icon: BookOpen,     category: 'analyse' },
  ],
  'tranc3-empathetic': [
    { text: "I'm feeling overwhelmed — help me prioritise",   icon: Heart,        category: 'connect' },
    { text: 'How can I communicate better with my team?',     icon: MessageCircle,category: 'connect' },
    { text: "I'm stuck on a problem — can you help?",         icon: Lightbulb,    category: 'connect' },
    { text: 'What mindfulness techniques help with focus?',   icon: Brain,        category: 'connect' },
    { text: 'Help me write a thoughtful apology',             icon: BookOpen,     category: 'create'  },
    { text: 'How do I give constructive feedback?',           icon: Sparkles,     category: 'connect' },
  ],
  'tranc3-multilingual': [
    { text: "Translate 'good morning' into 6 languages",      icon: Globe,        category: 'explore' },
    { text: 'Explain quantum physics en français',             icon: Cpu,          category: 'explore' },
    { text: 'Write a greeting in Japanese and explain it',    icon: Sparkles,     category: 'create'  },
    { text: 'What are common idioms in Spanish?',             icon: BookOpen,     category: 'explore' },
    { text: 'Compare English and Mandarin grammar',           icon: Brain,        category: 'analyse' },
    { text: "How do you say 'I love coding' in German?",      icon: Code2,        category: 'explore' },
  ],
}

const CATEGORY_LABELS: Record<string, string> = {
  explore:  'Explore',
  create:   'Create',
  analyse:  'Analyse',
  platform: 'Platform',
  connect:  'Connect',
}

const LANGUAGES = [
  { code: 'en', name: 'English' }, { code: 'es', name: 'Español' },
  { code: 'fr', name: 'Français' }, { code: 'de', name: 'Deutsch' },
  { code: 'zh', name: '中文' },    { code: 'ja', name: '日本語' },
  { code: 'ko', name: '한국어' },  { code: 'ar', name: 'العربية' },
]

const EMOTIONS = [
  { id: 'neutral',  label: 'Neutral',  color: 'bg-gray-700 text-gray-300' },
  { id: 'joy',      label: 'Joy',      color: 'bg-yellow-900 text-yellow-300' },
  { id: 'sadness',  label: 'Sadness',  color: 'bg-blue-900 text-blue-300' },
  { id: 'anger',    label: 'Anger',    color: 'bg-red-900 text-red-300' },
  { id: 'fear',     label: 'Fear',     color: 'bg-purple-900 text-purple-300' },
  { id: 'surprise', label: 'Surprise', color: 'bg-pink-900 text-pink-300' },
]

export default function ChatView() {
  const [token, setToken]         = useState(localStorage.getItem('tranc3_token') || '')
  const [username, setUsername]   = useState(localStorage.getItem('tranc3_user') || '')
  const [messages, setMessages]   = useState<Message[]>([])
  const [input, setInput]         = useState('')
  const [loading, setLoading]     = useState(false)
  const [language, setLanguage]   = useState('en')

  // Sync <html lang> with selected language
  React.useEffect(() => {
    document.documentElement.setAttribute('lang', language)
  }, [language])

  const [personality, setPersonality] = useState('tranc3-base')
  const [emotion, setEmotion]     = useState('neutral')
  const [personalities, setPersonalities] = useState<Personality[]>([
    { id: 'tranc3-base',         name: 'Base' },
    { id: 'tranc3-creative',     name: 'Creative' },
    { id: 'tranc3-analytical',   name: 'Analytical' },
    { id: 'tranc3-empathetic',   name: 'Empathetic' },
    { id: 'tranc3-multilingual', name: 'Multilingual' },
  ])
  const [showUpgrade, setShowUpgrade] = useState(false)
  const [dark, setDark]           = useState(true)
  const [statusAnnouncement, setStatusAnnouncement] = useState('')
  const bottomRef    = useRef<HTMLDivElement>(null)
  const inputRef     = useRef<HTMLInputElement>(null)
  const promptRefs   = useRef<(HTMLButtonElement | null)[]>([])

  // Auto-focus the input as soon as the chat is mounted — eliminates blank-canvas
  // paralysis by immediately inviting the user to type
  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  // Reset prompt refs when personality changes (prompts list regenerates)
  useEffect(() => {
    promptRefs.current = []
  }, [personality])

  useEffect(() => {
    if (!token) return
    fetch(`${API}/personalities`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data?.personalities) {
          setPersonalities(data.personalities.map((id: string) => ({
            id,
            name: id.replace('tranc3-', '').replace(/-/g, ' ')
              .replace(/\b\w/g, (c: string) => c.toUpperCase()),
          })))
        }
      })
      .catch(() => {})
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
        if (data.checkout_url) window.open(data.checkout_url, '_blank', 'noopener,noreferrer')
      }
    } catch {}
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
    setStatusAnnouncement('Sending message…')

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

      if (r.status === 429) {
        setShowUpgrade(true)
        setMessages(p => p.slice(0, -1))
        setStatusAnnouncement('Rate limit reached. Please upgrade to continue.')
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
      setStatusAnnouncement('Response received.')
    } catch {
      setMessages(p => [...p, {
        id: (Date.now() + 1).toString(),
        content: 'Something went wrong. Please try again.',
        sender: 'tranc3', timestamp: new Date(),
      }])
      setStatusAnnouncement('An error occurred. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  // Arrow-key navigation between prompt chips
  const handlePromptKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
      const refs = promptRefs.current.filter((r): r is HTMLButtonElement => r !== null)
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        e.preventDefault()
        refs[(index + 1) % refs.length]?.focus()
      } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        e.preventDefault()
        refs[(index - 1 + refs.length) % refs.length]?.focus()
      } else if (e.key === 'Home') {
        e.preventDefault()
        refs[0]?.focus()
      } else if (e.key === 'End') {
        e.preventDefault()
        refs[refs.length - 1]?.focus()
      }
    },
    []
  )

  const selectPrompt = useCallback((text: string) => {
    setInput(text)
    setStatusAnnouncement(`Prompt set: "${text}". Press Enter to send.`)
    // Slight delay so the announcement is processed before focus shifts
    setTimeout(() => inputRef.current?.focus(), 50)
  }, [])

  if (!token) return <LoginPage onLogin={handleLogin} />

  const navigate = useNavigate()

  const bg      = dark ? 'bg-gray-950 text-white'           : 'bg-gray-50 text-gray-900'
  const sidebar = dark ? 'bg-gray-900 border-gray-800'      : 'bg-white border-gray-200'
  const header  = dark ? 'bg-gray-900 border-gray-800'      : 'bg-white border-gray-200'
  const inputBg = dark ? 'bg-gray-800 border-gray-700 text-white' : 'bg-white border-gray-300 text-gray-900'
  const msgAi   = dark ? 'bg-gray-800 text-white'           : 'bg-white border text-gray-900'

  const activePersonalityName = personalities.find(p => p.id === personality)?.name ?? personality
  const prompts = PERSONALITY_PROMPTS[personality] ?? PERSONALITY_PROMPTS['tranc3-base']
  const charsLeft = MAX_INPUT_CHARS - input.length
  const nearLimit = charsLeft <= 200
  const atLimit   = charsLeft <= 0

  return (
    <div className={`flex h-screen ${bg}`}>
      {/* Screen-reader status announcer */}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
      >
        {statusAnnouncement}
      </div>

      {showUpgrade && (
        <UpgradeModal onClose={() => setShowUpgrade(false)} onUpgrade={handleUpgrade} />
      )}

      {/* Sidebar */}
      <aside
        aria-label="Chat settings"
        className={`w-72 border-r ${sidebar} flex flex-col p-4 gap-4 overflow-y-auto`}
      >
        <div className="flex items-center gap-2 mb-2">
          <Zap className="w-5 h-5 text-blue-400" aria-hidden="true" />
          <span className="font-bold text-lg">TRANC3</span>
          <span className="ml-auto text-xs text-gray-500" aria-label={`Logged in as ${username}`}>
            {username}
          </span>
        </div>

        {/* Dashboard Link */}
        <button
          onClick={() => navigate('/dashboard')}
          aria-label="Go to Ecosystem Dashboard"
          className="flex items-center gap-2 text-xs text-gray-500 hover:text-blue-400 transition-colors py-2 px-2 rounded-lg hover:bg-gray-800/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
        >
          <LayoutDashboard className="w-3.5 h-3.5" aria-hidden="true" />
          Dashboard
        </button>

        {/* Language */}
        <div>
          <label htmlFor="chat-language" className="text-xs text-gray-500 mb-1 flex items-center gap-1">
            <Globe className="w-3 h-3" aria-hidden="true" /> Language
          </label>
          <select
            id="chat-language"
            value={language}
            onChange={e => setLanguage(e.target.value)}
            className={`w-full rounded-lg px-3 py-2 text-sm border ${inputBg} focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500`}
          >
            {LANGUAGES.map(l => <option key={l.code} value={l.code}>{l.name}</option>)}
          </select>
        </div>

        {/* Personality */}
        <div>
          <label htmlFor="chat-personality" className="text-xs text-gray-500 mb-1 flex items-center gap-1">
            <Settings className="w-3 h-3" aria-hidden="true" /> Personality
          </label>
          <select
            id="chat-personality"
            value={personality}
            onChange={e => setPersonality(e.target.value)}
            className={`w-full rounded-lg px-3 py-2 text-sm border ${inputBg} focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500`}
          >
            {personalities.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>

        {/* Emotion */}
        <fieldset>
          <legend className="text-xs text-gray-500 mb-2">Your Emotion</legend>
          <div className="grid grid-cols-2 gap-1" role="group" aria-label="Select your current emotion">
            {EMOTIONS.map(e => (
              <button
                key={e.id}
                onClick={() => setEmotion(e.id)}
                aria-pressed={emotion === e.id}
                className={`text-xs py-1 px-2 rounded-lg transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${
                  emotion === e.id ? e.color : dark ? 'bg-gray-800 text-gray-400' : 'bg-gray-100 text-gray-600'
                }`}
              >
                {e.label}
              </button>
            ))}
          </div>
        </fieldset>

        {/* Theme toggle */}
        <button
          onClick={() => setDark(d => !d)}
          aria-pressed={dark}
          aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
          className="text-xs text-gray-500 hover:text-gray-300 mt-auto text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 rounded"
        >
          {dark ? '☀️ Light mode' : '🌙 Dark mode'}
        </button>

        <button
          onClick={logout}
          aria-label="Sign out of TRANC3"
          className="flex items-center gap-2 text-xs text-gray-500 hover:text-red-400 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 rounded"
        >
          <LogOut className="w-3 h-3" aria-hidden="true" /> Sign out
        </button>
      </aside>

      {/* Chat panel */}
      <div className="flex-1 flex flex-col" role="region" aria-label="Chat conversation">
        {/* Header */}
        <header className={`px-6 py-3 border-b ${header} flex items-center gap-3`}>
          <Brain className="w-5 h-5 text-blue-400" aria-hidden="true" />
          <div>
            <div className="font-semibold">TRANC3 Conscious AI</div>
            <div className="text-xs text-gray-500" aria-live="polite" aria-atomic="true">
              {activePersonalityName} · {language.toUpperCase()}
            </div>
          </div>
        </header>

        {/* Message log */}
        <div
          role="log"
          aria-label="Conversation messages"
          aria-live="polite"
          aria-relevant="additions"
          className="flex-1 overflow-y-auto p-6 space-y-4"
        >
          {messages.length === 0 && (
            // ── Empty state ────────────────────────────────────────────────────
            <section
              aria-label="Start a conversation — suggested prompts"
              className="flex flex-col items-center text-center mt-10 max-w-2xl mx-auto w-full"
            >
              {/* Branded hero mark */}
              <div
                aria-hidden="true"
                className={`w-16 h-16 rounded-2xl flex items-center justify-center mb-5 ${
                  dark
                    ? 'bg-gradient-to-br from-blue-600/30 to-indigo-600/20 border border-blue-500/20'
                    : 'bg-gradient-to-br from-blue-100 to-indigo-100 border border-blue-200'
                }`}
              >
                <Zap className="w-8 h-8 text-blue-400" aria-hidden="true" />
              </div>

              <h2 className={`text-xl font-semibold mb-1 ${dark ? 'text-white' : 'text-gray-900'}`}>
                Start a conversation
              </h2>
              <p className={`text-sm mb-2 ${dark ? 'text-gray-400' : 'text-gray-500'}`}>
                Ask anything in any language
              </p>

              {/* Personality context — tells user which mode is active */}
              <p className={`text-xs mb-8 px-3 py-1.5 rounded-full inline-block ${
                dark ? 'bg-gray-800 text-gray-400' : 'bg-gray-100 text-gray-500'
              }`}>
                <span className="sr-only">Active personality: </span>
                {activePersonalityName} mode — prompts tailored to this style
              </p>

              {/* Suggested prompts ────────────────────────────────────────────
                  ARIA pattern: the container is labelled as a group of prompts;
                  each <li> holds a button. Arrow keys move focus between chips.
                  Activating a chip fills the input and shifts focus there,
                  which is announced via the live status region.
                  ──────────────────────────────────────────────────────────── */}
              <ul
                className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 w-full"
                aria-label={`Suggested prompts for ${activePersonalityName} mode`}
              >
                {prompts.map((prompt, i) => {
                  const Icon = prompt.icon
                  const categoryLabel = CATEGORY_LABELS[prompt.category] ?? prompt.category
                  return (
                    <li key={i} className="contents">
                      <button
                        ref={el => { promptRefs.current[i] = el }}
                        type="button"
                        onClick={() => selectPrompt(prompt.text)}
                        onKeyDown={e => handlePromptKeyDown(e, i)}
                        aria-label={`${prompt.text} — ${categoryLabel} prompt`}
                        /* stagger entrance: delay 0, 50, 100 … ms */
                        style={{ animationDelay: `${i * 50}ms` }}
                        className={[
                          'group flex items-start gap-3 text-left p-3.5 rounded-xl border',
                          'transition-all duration-150',
                          'hover:border-blue-500/50 hover:bg-blue-500/10',
                          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500',
                          'focus-visible:ring-offset-2',
                          dark
                            ? 'bg-gray-800/50 border-gray-700/50 text-gray-300 focus-visible:ring-offset-gray-950'
                            : 'bg-white border-gray-200 text-gray-600 focus-visible:ring-offset-gray-50',
                          /* Entrance fade+slide animation — off under prefers-reduced-motion */
                          'motion-safe:animate-[prompt-enter_0.25s_ease-out_both]',
                        ].join(' ')}
                      >
                        {/* Icon */}
                        <span
                          aria-hidden="true"
                          className={`mt-0.5 flex-shrink-0 w-6 h-6 rounded-lg flex items-center justify-center transition-colors ${
                            dark
                              ? 'bg-gray-700 text-gray-400 group-hover:bg-blue-500/20 group-hover:text-blue-400'
                              : 'bg-gray-100 text-gray-400 group-hover:bg-blue-50 group-hover:text-blue-500'
                          }`}
                        >
                          <Icon size={13} aria-hidden={true} />
                        </span>

                        {/* Text + category tag */}
                        <span className="flex flex-col gap-1 min-w-0">
                          <span className="text-sm leading-snug">{prompt.text}</span>
                          <span
                            className={`text-[10px] font-medium uppercase tracking-wide ${
                              dark ? 'text-gray-600' : 'text-gray-400'
                            }`}
                            aria-hidden="true"
                          >
                            {categoryLabel}
                          </span>
                        </span>
                      </button>
                    </li>
                  )
                })}
              </ul>

              {/* Keyboard hint */}
              <p
                className={`mt-6 text-[11px] ${dark ? 'text-gray-600' : 'text-gray-400'}`}
                aria-hidden="true"
              >
                Arrow keys navigate prompts · Enter or click to select
              </p>
            </section>
          )}

          {messages.map(msg => {
            const isUser = msg.sender === 'user'
            return (
              <div
                key={msg.id}
                className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}
              >
                <article
                  aria-label={`${isUser ? username || 'You' : 'TRANC3'} at ${msg.timestamp.toLocaleTimeString()}`}
                  className={`max-w-lg rounded-2xl px-4 py-3 ${
                    isUser ? 'bg-blue-600 text-white' : msgAi
                  }`}
                >
                  <p className="text-sm leading-relaxed">{msg.content}</p>
                  <div className="flex items-center gap-2 mt-2 flex-wrap">
                    <time
                      dateTime={msg.timestamp.toISOString()}
                      className="text-xs opacity-50"
                    >
                      {msg.timestamp.toLocaleTimeString()}
                    </time>
                    {msg.emotion && msg.emotion !== 'neutral' && (
                      <span
                        aria-label={`Detected emotion: ${msg.emotion}`}
                        className="text-xs opacity-60 bg-black/20 rounded px-1"
                      >
                        {msg.emotion}
                      </span>
                    )}
                    {msg.phi !== undefined && msg.phi !== null && (
                      <span
                        aria-label={`Consciousness level phi ${msg.phi.toFixed(2)}`}
                        className={`text-xs px-2 py-0.5 rounded-full font-mono ${
                          msg.phi > 2.0 ? 'bg-purple-600 text-white'
                          : msg.phi > 1.0 ? 'bg-purple-900 text-purple-300'
                          : 'bg-gray-700 text-gray-400'
                        }`}
                      >
                        Φ {msg.phi.toFixed(2)}
                      </span>
                    )}
                    {msg.quantum_used && (
                      <span
                        aria-label="Quantum processing used"
                        className="text-xs px-2 py-0.5 rounded-full bg-cyan-900 text-cyan-300"
                      >
                        ⚛ quantum
                      </span>
                    )}
                  </div>
                </article>
              </div>
            )
          })}

          {loading && (
            <div className="flex justify-start" role="status" aria-label="TRANC3 is composing a response">
              <div className={`rounded-2xl px-4 py-3 ${msgAi}`} aria-hidden="true">
                <div className="flex gap-1 items-center">
                  {[0, 1, 2].map(i => (
                    <div
                      key={i}
                      className="w-2 h-2 bg-gray-400 rounded-full motion-safe:animate-bounce"
                      style={{ animationDelay: `${i * 0.15}s` }}
                    />
                  ))}
                </div>
              </div>
            </div>
          )}
          <div ref={bottomRef} aria-hidden="true" />
        </div>

        {/* ── Input bar ──────────────────────────────────────────────────────── */}
        <div className={`px-6 py-4 border-t ${header}`}>
          <form
            onSubmit={e => { e.preventDefault(); send() }}
            className="flex flex-col gap-2"
            aria-label="Send a message"
          >
            <div className="flex gap-3">
              <label htmlFor="chat-input" className="sr-only">
                Message — {activePersonalityName} personality active
              </label>
              <input
                id="chat-input"
                ref={inputRef}
                value={input}
                onChange={e => { if (e.target.value.length <= MAX_INPUT_CHARS) setInput(e.target.value) }}
                onKeyDown={e => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), send())}
                placeholder="Type a message…"
                aria-describedby="chat-input-hint chat-char-count"
                maxLength={MAX_INPUT_CHARS}
                inputMode="text"
                className={`flex-1 rounded-xl px-4 py-3 text-sm border focus:outline-none focus:border-blue-500 focus-visible:ring-2 focus-visible:ring-blue-500 transition-shadow ${inputBg}`}
                disabled={loading}
              />
              <button
                type="submit"
                aria-label={loading ? 'Sending message…' : 'Send message'}
                aria-busy={loading}
                disabled={loading || !input.trim() || atLimit}
                className="bg-blue-600 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-xl px-4 py-3 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 focus-visible:ring-offset-gray-900"
              >
                <Send className="w-4 h-4" aria-hidden="true" />
              </button>
            </div>

            {/* Assistive hints row */}
            <div className="flex items-center justify-between px-1">
              <span id="chat-input-hint" className="text-[11px] text-gray-600 select-none">
                Enter to send · Shift+Enter for new line
              </span>
              {/* Character counter — visible only near the limit */}
              <span
                id="chat-char-count"
                aria-live="polite"
                aria-atomic="true"
                className={`text-[11px] tabular-nums transition-opacity ${
                  nearLimit
                    ? atLimit
                      ? 'text-red-400 opacity-100'
                      : 'text-amber-400 opacity-100'
                    : 'text-gray-700 opacity-0 select-none'
                }`}
              >
                {/* Screen readers always get the count; visual show only near limit */}
                <span className="sr-only">Characters remaining: </span>
                {charsLeft}
                <span aria-hidden="true"> / {MAX_INPUT_CHARS}</span>
              </span>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}
