import React, { useState } from 'react'
import { Settings, Save, Eye, EyeOff, CheckCircle } from 'lucide-react'

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
  { key: 'COHERE_API_KEY',        label: 'Cohere API Key',        placeholder: 'co-…',           required: false, secret: true,  hint: 'Free tier — 100K tokens/month (token-based, not requests)' },
  { key: 'DEEPSEEK_API_KEY',      label: 'DeepSeek API Key',      placeholder: 'sk-…',           required: false, secret: true,  hint: 'Free tier with soft daily limits' },
  { key: 'OLLAMA_URL',            label: 'Ollama URL',            placeholder: 'http://localhost:11434', required: false, secret: false, hint: 'Self-hosted local LLM — zero-cost' },
  { key: 'SECRET_KEY',            label: 'FastAPI Secret Key',    placeholder: '64-char hex',    required: true,  secret: true,  hint: 'Required — generates JWT tokens' },
  { key: 'JWT_SECRET',            label: 'JWT Secret',            placeholder: '64-char hex',    required: true,  secret: true,  hint: 'Required — signs auth tokens' },
  { key: 'DATABASE_URL',          label: 'Database URL',          placeholder: 'postgresql://…', required: false, secret: true,  hint: 'Optional — defaults to SQLite per worker' },
  { key: 'REDIS_URL',             label: 'Redis URL',             placeholder: 'rediss://…',     required: false, secret: true,  hint: 'Optional — Upstash free tier (10K req/day)' },
]

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

export default function SettingsPage() {
  const [values, setValues] = useState<Record<string, string>>(() => {
    const stored: Record<string, string> = {}
    ENV_VARS.forEach((v) => {
      stored[v.key] = localStorage.getItem(`setting_${v.key}`) ?? ''
    })
    return stored
  })
  const [visible, setVisible] = useState<Record<string, boolean>>({})
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')
  const [activeTab, setActiveTab] = useState<'providers' | 'backend'>('providers')

  const toggle = (key: string) =>
    setVisible((prev) => ({ ...prev, [key]: !prev[key] }))

  const handleChange = (key: string, val: string) =>
    setValues((prev) => ({ ...prev, [key]: val }))

  async function save() {
    setSaveStatus('saving')
    // Persist in localStorage as a convenience (not secure for production, but helpful in dev)
    ENV_VARS.forEach((v) => {
      if (values[v.key]) {
        localStorage.setItem(`setting_${v.key}`, values[v.key])
      } else {
        localStorage.removeItem(`setting_${v.key}`)
      }
    })

    // Attempt to push to backend
    try {
      const body: Record<string, string> = {}
      ENV_VARS.forEach((v) => { if (values[v.key]) body[v.key] = values[v.key] })
      await fetch(`${API}/admin/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(5000),
      })
    } catch { /* backend may not be running */ }

    setSaveStatus('saved')
    setTimeout(() => setSaveStatus('idle'), 2500)
  }

  const providerVars = ENV_VARS.filter((v) =>
    ['GROQ_API_KEY','GOOGLE_GEMINI_API_KEY','GITHUB_TOKEN','CEREBRAS_API_KEY',
     'SAMBANOVA_API_KEY','MISTRAL_API_KEY','COHERE_API_KEY','DEEPSEEK_API_KEY','OLLAMA_URL'].includes(v.key)
  )
  const backendVars = ENV_VARS.filter((v) => !providerVars.includes(v))

  const tabs: { id: 'providers' | 'backend'; label: string }[] = [
    { id: 'providers', label: 'AI Providers' },
    { id: 'backend', label: 'Backend / Database' },
  ]

  const shown = activeTab === 'providers' ? providerVars : backendVars

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Settings size={22} className="text-indigo-400" />
          Settings
        </h1>
        <p className="text-gray-400 text-sm mt-1">
          Configure API keys and environment variables. Values are stored in localStorage for dev convenience.
        </p>
      </div>

      <p className="text-yellow-500 text-xs mb-5 bg-yellow-900/20 border border-yellow-800 rounded-lg px-3 py-2">
        In production, set these as environment variables on your server or in Docker Compose — never commit real secrets to git.
      </p>

      {/* Tabs */}
      <div className="flex gap-1 mb-5 border-b border-gray-700">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
              activeTab === t.id
                ? 'border-indigo-500 text-white'
                : 'border-transparent text-gray-400 hover:text-white'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Fields */}
      <div className="space-y-4">
        {shown.map((v) => (
          <div key={v.key}>
            <label className="block text-gray-300 text-sm font-medium mb-1">
              {v.label}
              {v.required && <span className="text-red-400 ml-1">*</span>}
            </label>
            <div className="relative">
              <input
                type={v.secret && !visible[v.key] ? 'password' : 'text'}
                value={values[v.key] ?? ''}
                onChange={(e) => handleChange(v.key, e.target.value)}
                placeholder={v.placeholder}
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm placeholder-gray-600 focus:outline-none focus:border-indigo-500 pr-10"
              />
              {v.secret && (
                <button
                  type="button"
                  onClick={() => toggle(v.key)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
                >
                  {visible[v.key] ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              )}
            </div>
            <p className="text-gray-600 text-xs mt-1">{v.hint}</p>
          </div>
        ))}
      </div>

      {/* Save */}
      <div className="mt-8 flex items-center gap-3">
        <button
          onClick={save}
          disabled={saveStatus === 'saving'}
          className="flex items-center gap-2 px-5 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg text-sm text-white transition-colors"
        >
          {saveStatus === 'saving' ? (
            <Settings size={14} className="animate-spin" />
          ) : saveStatus === 'saved' ? (
            <CheckCircle size={14} />
          ) : (
            <Save size={14} />
          )}
          {saveStatus === 'saved' ? 'Saved!' : 'Save Settings'}
        </button>
        {saveStatus === 'saved' && (
          <span className="text-green-400 text-sm">Settings saved to localStorage.</span>
        )}
      </div>
    </div>
  )
}
