import React, { useState, useRef, useId, useEffect, useCallback } from 'react'
import { Settings, Save, Eye, EyeOff, CheckCircle, Lock, Trash2, RefreshCw, AlertCircle } from 'lucide-react'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface EnvVar {
  key: string
  label: string
  placeholder: string
  required: boolean
  hint: string
  secret?: boolean
}

const ENV_VARS: EnvVar[] = [
  { key: 'GROQ_API_KEY',          label: 'Groq API Key',          placeholder: 'gsk_…',          required: false, secret: true,  hint: 'Free tier — 14,400 req/day' },
  { key: 'GOOGLE_GEMINI_API_KEY', label: 'Gemini API Key',        placeholder: 'AIza…',          required: false, secret: true,  hint: 'Free tier — 1,500 req/day' },
  { key: 'GITHUB_TOKEN',          label: 'GitHub Token',          placeholder: 'github_pat_…',   required: false, secret: true,  hint: 'Any PAT — 150 req/day gpt-4o-mini, no credit card' },
  { key: 'CEREBRAS_API_KEY',      label: 'Cerebras API Key',      placeholder: 'csk-…',          required: false, secret: true,  hint: 'Free tier — 1,000 req/day' },
  { key: 'SAMBANOVA_API_KEY',     label: 'SambaNova API Key',     placeholder: 'sb-…',           required: false, secret: true,  hint: 'Free tier — 1,000 req/day' },
  { key: 'MISTRAL_API_KEY',       label: 'Mistral API Key',       placeholder: 'mistral-…',      required: false, secret: true,  hint: 'Free tier — 500K tokens/month' },
  { key: 'COHERE_API_KEY',        label: 'Cohere API Key',        placeholder: 'co-…',           required: false, secret: true,  hint: 'Free tier — 100K tokens/month' },
  { key: 'DEEPSEEK_API_KEY',      label: 'DeepSeek API Key',      placeholder: 'sk-…',           required: false, secret: true,  hint: 'Free tier with soft daily limits' },
  { key: 'OLLAMA_URL',            label: 'Ollama URL',            placeholder: 'http://localhost:11434', required: false, secret: false, hint: 'Self-hosted local LLM — zero-cost' },
  { key: 'SECRET_KEY',            label: 'FastAPI Secret Key',    placeholder: '64-char hex',    required: true,  secret: true,  hint: 'Required — generates JWT tokens' },
  { key: 'JWT_SECRET',            label: 'JWT Secret',            placeholder: '64-char hex',    required: true,  secret: true,  hint: 'Required — signs auth tokens' },
  { key: 'DATABASE_URL',          label: 'Database URL',          placeholder: 'postgresql://…', required: false, secret: true,  hint: 'Optional — defaults to SQLite per worker' },
  { key: 'REDIS_URL',             label: 'Redis URL',             placeholder: 'rediss://…',     required: false, secret: true,  hint: 'Optional — Upstash free tier (10K req/day)' },
]

type FieldStatus = 'idle' | 'saving' | 'saved' | 'deleting' | 'error'
type TabId = 'providers' | 'backend'

const TABS: { id: TabId; label: string }[] = [
  { id: 'providers', label: 'AI Providers' },
  { id: 'backend',   label: 'Backend / Database' },
]

const PROVIDER_KEYS = new Set([
  'GROQ_API_KEY','GOOGLE_GEMINI_API_KEY','GITHUB_TOKEN','CEREBRAS_API_KEY',
  'SAMBANOVA_API_KEY','MISTRAL_API_KEY','COHERE_API_KEY','DEEPSEEK_API_KEY','OLLAMA_URL',
])

function authHeaders(): HeadersInit {
  const token = localStorage.getItem('tranc3_token') || localStorage.getItem('token') || ''
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
}

export default function SettingsPage() {
  // Draft values the user is typing — empty = not changed / will keep server value
  const [drafts, setDrafts]   = useState<Record<string, string>>({})
  // Server-side status for each key
  const [stored, setStored]   = useState<Record<string, 'set' | 'unset'>>({})
  const [visible, setVisible] = useState<Record<string, boolean>>({})
  const [fieldStatus, setFieldStatus] = useState<Record<string, FieldStatus>>({})
  const [loadError, setLoadError]     = useState<string | null>(null)
  const [loadingKeys, setLoadingKeys] = useState(true)
  const [activeTab, setActiveTab]     = useState<TabId>('providers')

  const tablistRef = useRef<HTMLDivElement>(null)
  const announceId = useId()
  const tabPanelId = useId()

  // ── Load which keys are already stored ──────────────────────────────────────
  const loadStatus = useCallback(async () => {
    setLoadingKeys(true)
    setLoadError(null)
    try {
      const res = await fetch(`${API}/user/settings`, {
        headers: authHeaders(),
        signal: AbortSignal.timeout(6000),
      })
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
      const data: Record<string, 'set' | 'unset'> = await res.json()
      setStored(data)
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Failed to load settings status')
    } finally {
      setLoadingKeys(false)
    }
  }, [])

  useEffect(() => { loadStatus() }, [loadStatus])

  // ── Helpers ─────────────────────────────────────────────────────────────────
  const toggle = (key: string) => setVisible((p: Record<string, boolean>) => ({ ...p, [key]: !p[key] }))
  const handleChange = (key: string, val: string) => setDrafts((p: Record<string, string>) => ({ ...p, [key]: val }))

  function setField(key: string, status: FieldStatus) {
    setFieldStatus((p: Record<string, FieldStatus>) => ({ ...p, [key]: status }))
  }

  // ── Save a single field ──────────────────────────────────────────────────────
  async function saveField(key: string) {
    const value = drafts[key] ?? ''
    if (!value.trim()) return
    setField(key, 'saving')
    try {
      const res = await fetch(`${API}/user/settings`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ key, value }),
        signal: AbortSignal.timeout(8000),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail ?? `${res.status}`)
      }
      setStored((p: Record<string, 'set' | 'unset'>) => ({ ...p, [key]: 'set' }))
      setDrafts((p: Record<string, string>) => { const n = { ...p }; delete n[key]; return n })
      setField(key, 'saved')
      setTimeout(() => setField(key, 'idle'), 2500)
    } catch (err) {
      console.error('save failed', key, err)
      setField(key, 'error')
      setTimeout(() => setField(key, 'idle'), 3000)
    }
  }

  // ── Clear a stored field ─────────────────────────────────────────────────────
  async function clearField(key: string) {
    setField(key, 'deleting')
    try {
      const res = await fetch(`${API}/user/settings/${encodeURIComponent(key)}`, {
        method: 'DELETE',
        headers: authHeaders(),
        signal: AbortSignal.timeout(8000),
      })
      if (!res.ok && res.status !== 404) throw new Error(`${res.status}`)
      setStored((p: Record<string, 'set' | 'unset'>) => ({ ...p, [key]: 'unset' }))
      setDrafts((p: Record<string, string>) => { const n = { ...p }; delete n[key]; return n })
      setField(key, 'idle')
    } catch (err) {
      console.error('clear failed', key, err)
      setField(key, 'error')
      setTimeout(() => setField(key, 'idle'), 3000)
    }
  }

  // ── Save all dirty (non-empty draft) fields at once ─────────────────────────
  async function saveAll() {
    const dirty = ENV_VARS.filter((v) => (drafts[v.key] ?? '').trim())
    await Promise.all(dirty.map((v) => saveField(v.key)))
  }

  // ── Tab keyboard nav ─────────────────────────────────────────────────────────
  function handleTabKeyDown(e: React.KeyboardEvent, tabId: TabId) {
    const ids = TABS.map((t) => t.id)
    const idx = ids.indexOf(tabId)
    if (e.key === 'ArrowRight') { e.preventDefault(); const n = ids[(idx+1)%ids.length]; setActiveTab(n); focusTab(n) }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); const n = ids[(idx-1+ids.length)%ids.length]; setActiveTab(n); focusTab(n) }
    else if (e.key === 'Home') { e.preventDefault(); setActiveTab(ids[0]); focusTab(ids[0]) }
    else if (e.key === 'End') { e.preventDefault(); setActiveTab(ids[ids.length-1]); focusTab(ids[ids.length-1]) }
  }
  function focusTab(id: TabId) {
    tablistRef.current?.querySelector<HTMLButtonElement>(`[data-tab="${id}"]`)?.focus()
  }

  const shown = activeTab === 'providers'
    ? ENV_VARS.filter((v) => PROVIDER_KEYS.has(v.key))
    : ENV_VARS.filter((v) => !PROVIDER_KEYS.has(v.key))

  const anyDirty = ENV_VARS.some((v) => (drafts[v.key] ?? '').trim())

  return (
    <div className="p-6 max-w-3xl mx-auto">
      {/* Live region */}
      <div id={announceId} role="status" aria-live="polite" aria-atomic="true" className="sr-only" />

      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Settings size={22} aria-hidden="true" className="text-indigo-400" />
          Settings
        </h1>
        <p className="text-gray-400 text-sm mt-1">
          Configure API keys and environment variables.
        </p>
      </div>

      {/* Security badge */}
      <div className="flex items-center gap-2 text-green-400 text-xs mb-5 bg-green-900/20 border border-green-800 rounded-lg px-3 py-2" role="note">
        <Lock size={13} aria-hidden="true" />
        Secrets are encrypted (AES-128-CBC + HMAC) and stored server-side. Nothing sensitive is written to localStorage.
      </div>

      {/* Load error */}
      {loadError && (
        <div className="flex items-center gap-2 text-amber-400 text-xs mb-4 bg-amber-900/20 border border-amber-800 rounded-lg px-3 py-2" role="alert">
          <AlertCircle size={13} aria-hidden="true" />
          Could not load settings status: {loadError}
          <button onClick={loadStatus} className="ml-auto underline hover:no-underline">Retry</button>
        </div>
      )}

      {/* Tabs */}
      <div
        ref={tablistRef}
        role="tablist"
        aria-label="Settings sections"
        className="flex gap-1 mb-5 border-b border-gray-700"
      >
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            id={`tab-${t.id}`}
            data-tab={t.id}
            aria-selected={activeTab === t.id}
            aria-controls={`${tabPanelId}-${t.id}`}
            tabIndex={activeTab === t.id ? 0 : -1}
            onClick={() => setActiveTab(t.id)}
            onKeyDown={(e) => handleTabKeyDown(e, t.id)}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 ${
              activeTab === t.id
                ? 'border-indigo-500 text-white'
                : 'border-transparent text-gray-400 hover:text-white'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab panels */}
      {TABS.map((t) => (
        <div
          key={t.id}
          role="tabpanel"
          id={`${tabPanelId}-${t.id}`}
          aria-labelledby={`tab-${t.id}`}
          hidden={activeTab !== t.id}
          tabIndex={0}
          className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 rounded"
        >
          {activeTab === t.id && (
            <div className="space-y-5">
              {shown.map((v) => {
                const inputId   = `setting-${v.key}`
                const hintId    = `hint-${v.key}`
                const status    = fieldStatus[v.key] ?? 'idle'
                const isSet     = stored[v.key] === 'set'
                const draft     = drafts[v.key] ?? ''
                const isBusy    = status === 'saving' || status === 'deleting'

                return (
                  <div key={v.key} className="group">
                    <div className="flex items-center justify-between mb-1">
                      <label htmlFor={inputId} className="text-gray-300 text-sm font-medium flex items-center gap-1.5">
                        {v.label}
                        {v.required && <span className="text-red-400" aria-label="required">*</span>}
                      </label>
                      <div className="flex items-center gap-1.5">
                        {/* Server-stored badge */}
                        {isSet && !loadingKeys && (
                          <span className="flex items-center gap-1 text-green-500 text-xs bg-green-900/30 border border-green-800/50 rounded px-1.5 py-0.5">
                            <Lock size={10} aria-hidden="true" />
                            Stored
                          </span>
                        )}
                        {/* Per-field status badge */}
                        {status === 'saved' && (
                          <span className="text-green-400 text-xs flex items-center gap-1">
                            <CheckCircle size={11} aria-hidden="true" /> Saved
                          </span>
                        )}
                        {status === 'error' && (
                          <span className="text-red-400 text-xs flex items-center gap-1">
                            <AlertCircle size={11} aria-hidden="true" /> Error
                          </span>
                        )}
                        {/* Clear stored value */}
                        {isSet && (
                          <button
                            type="button"
                            onClick={() => clearField(v.key)}
                            disabled={isBusy}
                            aria-label={`Clear stored ${v.label}`}
                            className="text-gray-600 hover:text-red-400 disabled:opacity-40 transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-red-400 rounded"
                          >
                            {status === 'deleting'
                              ? <RefreshCw size={13} aria-hidden="true" className="animate-spin" />
                              : <Trash2 size={13} aria-hidden="true" />}
                          </button>
                        )}
                      </div>
                    </div>

                    <div className="relative flex gap-2">
                      <div className="relative flex-1">
                        <input
                          id={inputId}
                          type={v.secret && !visible[v.key] ? 'password' : 'text'}
                          value={draft}
                          onChange={(e) => handleChange(v.key, e.target.value)}
                          placeholder={isSet && !loadingKeys ? '●●●●●●●●' : v.placeholder}
                          aria-required={v.required}
                          aria-describedby={hintId}
                          autoComplete={v.secret ? 'new-password' : undefined}
                          disabled={isBusy}
                          className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm placeholder-gray-600 focus:outline-none focus:border-indigo-500 focus-visible:ring-2 focus-visible:ring-indigo-500 pr-10 disabled:opacity-60"
                        />
                        {v.secret && (
                          <button
                            type="button"
                            onClick={() => toggle(v.key)}
                            aria-label={visible[v.key] ? `Hide ${v.label}` : `Show ${v.label}`}
                            aria-pressed={visible[v.key]}
                            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 rounded"
                          >
                            {visible[v.key]
                              ? <EyeOff size={14} aria-hidden="true" />
                              : <Eye    size={14} aria-hidden="true" />}
                          </button>
                        )}
                      </div>
                      {/* Per-field save button — only shown when there's a draft */}
                      {draft.trim() && (
                        <button
                          type="button"
                          onClick={() => saveField(v.key)}
                          disabled={isBusy}
                          aria-label={`Save ${v.label}`}
                          className="flex items-center gap-1.5 px-3 py-2 bg-indigo-700 hover:bg-indigo-600 disabled:opacity-50 rounded-lg text-xs text-white transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 shrink-0"
                        >
                          {status === 'saving'
                            ? <RefreshCw size={12} aria-hidden="true" className="animate-spin" />
                            : <Save size={12} aria-hidden="true" />}
                          Save
                        </button>
                      )}
                    </div>
                    <p id={hintId} className="text-gray-600 text-xs mt-1">{v.hint}</p>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      ))}

      {/* Save-all footer */}
      <div className="mt-8 flex items-center gap-3">
        <button
          onClick={saveAll}
          disabled={!anyDirty}
          aria-describedby={announceId}
          className="flex items-center gap-2 px-5 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg text-sm text-white transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
        >
          <Save size={14} aria-hidden="true" />
          Save All Changes
        </button>
        <button
          onClick={loadStatus}
          disabled={loadingKeys}
          aria-label="Refresh settings status from server"
          className="flex items-center gap-1.5 px-3 py-2 border border-gray-700 hover:border-gray-500 disabled:opacity-40 rounded-lg text-sm text-gray-400 hover:text-white transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
        >
          <RefreshCw size={13} aria-hidden="true" className={loadingKeys ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>
    </div>
  )
}
