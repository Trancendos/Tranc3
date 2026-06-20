/**
 * LangChainPage — LangChain / LangGraph Orchestration (Port 8036)
 *
 * Displays prompt templates, chain definitions, execution history,
 * documents (RAG), and agent tools from the langchain-integration-service.
 */
import React, { useEffect, useState, useCallback } from 'react'
import { Layers, RefreshCw, FileText, Link2, Play, Database, Wrench, GitBranch } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const LC_API = '/lchain'
const INTERNAL = { 'X-Internal-Secret': 'dev-secret' }

interface LCStats {
  templates: number
  chains: number
  executions: number
  documents: number
  tools: number
  graphs: number
}

interface Template {
  id: string
  name: string
  description: string
  version: number
  variables: string[]
  created_at: string
}

interface Chain {
  id: string
  name: string
  chain_type: string
  steps: unknown[]
  created_at: string
}

interface Execution {
  id: string
  chain_id: string
  status: string
  input_data: Record<string, unknown>
  output_data: Record<string, unknown> | null
  tokens_used: number
  cost_usd: number
  created_at: string
  completed_at: string | null
}

interface Document {
  id: string
  title: string
  source: string
  chunk_count: number
  embedding_status: string
  created_at: string
}

interface AgentTool {
  id: string
  name: string
  description: string
  tool_type: string
  is_active: boolean
  created_at: string
}

type Tab = 'templates' | 'chains' | 'executions' | 'documents' | 'tools'

const STATUS_COLOR: Record<string, string> = {
  success:   'text-green-400',
  completed: 'text-green-400',
  running:   'text-yellow-400',
  pending:   'text-gray-400',
  failed:    'text-red-400',
  error:     'text-red-400',
  indexed:   'text-green-400',
  pending_embed: 'text-yellow-400',
}

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: 'templates',  label: 'Templates',  icon: <FileText    size={12} aria-hidden="true" /> },
  { id: 'chains',     label: 'Chains',     icon: <Link2       size={12} aria-hidden="true" /> },
  { id: 'executions', label: 'Executions', icon: <Play        size={12} aria-hidden="true" /> },
  { id: 'documents',  label: 'Documents',  icon: <Database    size={12} aria-hidden="true" /> },
  { id: 'tools',      label: 'Tools',      icon: <Wrench      size={12} aria-hidden="true" /> },
]

export default function LangChainPage() {
  const [stats, setStats]           = useState<LCStats | null>(null)
  const [templates, setTemplates]   = useState<Template[]>([])
  const [chains, setChains]         = useState<Chain[]>([])
  const [executions, setExecutions] = useState<Execution[]>([])
  const [documents, setDocuments]   = useState<Document[]>([])
  const [tools, setTools]           = useState<AgentTool[]>([])
  const [tab, setTab]               = useState<Tab>('templates')
  const [loading, setLoading]       = useState(false)
  const [workerDown, setWorkerDown] = useState(false)
  const { trackPageView } = useAnalytics()

  useEffect(() => { trackPageView('/langchain') }, [trackPageView])

  const load = useCallback(async () => {
    setLoading(true)
    setWorkerDown(false)
    try {
      const opts = { headers: INTERNAL, signal: AbortSignal.timeout(5000) }
      const [sRes, tRes, cRes, eRes, dRes, toolRes] = await Promise.all([
        fetch(`${LC_API}/stats`,       opts),
        fetch(`${LC_API}/templates`,   opts),
        fetch(`${LC_API}/chains`,      opts),
        fetch(`${LC_API}/executions`,  opts),
        fetch(`${LC_API}/documents`,   opts),
        fetch(`${LC_API}/tools`,       opts),
      ])
      if (sRes.ok)    setStats(await sRes.json())
      if (tRes.ok)    { const b = await tRes.json(); setTemplates(Array.isArray(b) ? b : (b.templates ?? [])) }
      if (cRes.ok)    { const b = await cRes.json(); setChains(Array.isArray(b) ? b : (b.chains ?? [])) }
      if (eRes.ok)    { const b = await eRes.json(); setExecutions(Array.isArray(b) ? b : (b.executions ?? [])) }
      if (dRes.ok)    { const b = await dRes.json(); setDocuments(Array.isArray(b) ? b : (b.documents ?? [])) }
      if (toolRes.ok) { const b = await toolRes.json(); setTools(Array.isArray(b) ? b : (b.tools ?? [])) }
      if (!sRes.ok && !tRes.ok) setWorkerDown(true)
    } catch {
      setWorkerDown(true)
    }
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  const fmtTs = (iso: string | null) => {
    if (!iso) return '—'
    try { return new Date(iso).toLocaleString() } catch { return iso }
  }

  const empty = (msg: string) => (
    <div className="bg-gray-900 rounded-lg border border-gray-700 p-8 text-center text-gray-500">
      {workerDown ? 'Worker offline' : msg}
    </div>
  )

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Layers size={22} aria-hidden="true" className="text-violet-400" />
            LangChain Integration
          </h1>
          <p className="text-gray-400 text-sm mt-1">
            LangChain / LangGraph Orchestration · Port 8036
            {stats && ` · ${stats.templates} templates · ${stats.chains} chains`}
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg text-sm text-white transition-colors"
        >
          <RefreshCw size={14} aria-hidden="true" className={loading ? 'animate-spin' : ''} />
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>

      {/* Worker banner */}
      {workerDown && (
        <div role="alert" className="mb-4 p-3 bg-yellow-900/30 border border-yellow-700 rounded-lg text-yellow-300 text-sm">
          LangChain worker (port 8036) is unreachable. Start with{' '}
          <code className="font-mono bg-gray-800 px-1 rounded">make dev-api</code>.
        </div>
      )}

      {/* Stats tiles */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
          {[
            { label: 'Templates',  value: stats.templates,  color: 'text-violet-400' },
            { label: 'Chains',     value: stats.chains,     color: 'text-blue-400' },
            { label: 'Executions', value: stats.executions, color: 'text-yellow-400' },
            { label: 'Documents',  value: stats.documents,  color: 'text-green-400' },
            { label: 'Tools',      value: stats.tools,      color: 'text-orange-400' },
            { label: 'Graphs',     value: stats.graphs,     color: 'text-pink-400' },
          ].map(({ label, value, color }) => (
            <div key={label} className="bg-gray-900 border border-gray-700 rounded-lg p-3">
              <div className={`text-2xl font-bold tabular-nums ${color}`}>{value}</div>
              <div className="text-gray-400 text-xs mt-1">{label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div role="tablist" className="flex gap-2 mb-5 flex-wrap">
        {TABS.map(t => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium border transition-colors ${
              tab === t.id
                ? 'bg-indigo-600 text-white border-indigo-500'
                : 'bg-gray-900 text-gray-400 border-gray-700 hover:border-gray-500'
            }`}
          >
            {t.icon}{t.label}
          </button>
        ))}
      </div>

      {/* Templates */}
      {tab === 'templates' && (
        templates.length === 0 && !loading ? empty('No prompt templates found.') : (
          <div className="bg-gray-900 rounded-lg border border-gray-700 overflow-hidden">
            <table className="w-full text-sm" aria-label="Prompt templates" aria-busy={loading}>
              <thead>
                <tr className="border-b border-gray-700">
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Name</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Description</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Variables</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Version</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Created</th>
                </tr>
              </thead>
              <tbody>
                {templates.map(t => (
                  <tr key={t.id} className="border-b border-gray-800 hover:bg-gray-800/50">
                    <td className="px-4 py-3 text-gray-200 font-medium text-sm">{t.name}</td>
                    <td className="px-4 py-3 text-gray-400 text-xs max-w-xs truncate">{t.description || '—'}</td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {(t.variables ?? []).map(v => (
                          <span key={v} className="text-xs bg-violet-900/30 text-violet-300 border border-violet-700 rounded px-1.5 py-0.5">{v}</span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-gray-400 tabular-nums text-xs">v{t.version}</td>
                    <td className="px-4 py-3 text-gray-500 text-xs whitespace-nowrap">{fmtTs(t.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* Chains */}
      {tab === 'chains' && (
        chains.length === 0 && !loading ? empty('No chains defined.') : (
          <div className="bg-gray-900 rounded-lg border border-gray-700 overflow-hidden">
            <table className="w-full text-sm" aria-label="Chain definitions" aria-busy={loading}>
              <thead>
                <tr className="border-b border-gray-700">
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Name</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Type</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Steps</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Created</th>
                </tr>
              </thead>
              <tbody>
                {chains.map(c => (
                  <tr key={c.id} className="border-b border-gray-800 hover:bg-gray-800/50">
                    <td className="px-4 py-3 text-gray-200 font-medium">{c.name}</td>
                    <td className="px-4 py-3">
                      <span className="text-xs bg-blue-900/30 text-blue-300 border border-blue-700 rounded-full px-2 py-0.5">{c.chain_type}</span>
                    </td>
                    <td className="px-4 py-3 text-gray-400 tabular-nums text-sm">{(c.steps as unknown[]).length}</td>
                    <td className="px-4 py-3 text-gray-500 text-xs whitespace-nowrap">{fmtTs(c.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* Executions */}
      {tab === 'executions' && (
        executions.length === 0 && !loading ? empty('No executions yet.') : (
          <div className="bg-gray-900 rounded-lg border border-gray-700 overflow-hidden">
            <table className="w-full text-sm" aria-label="Chain executions" aria-busy={loading}>
              <thead>
                <tr className="border-b border-gray-700">
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">ID</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Status</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Tokens</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Cost</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Started</th>
                </tr>
              </thead>
              <tbody>
                {executions.map(e => (
                  <tr key={e.id} className="border-b border-gray-800 hover:bg-gray-800/50">
                    <td className="px-4 py-3 text-gray-500 text-xs font-mono">{e.id.slice(0, 8)}…</td>
                    <td className={`px-4 py-3 text-xs ${STATUS_COLOR[e.status] ?? 'text-gray-400'}`}>{e.status}</td>
                    <td className="px-4 py-3 text-gray-400 tabular-nums text-xs">{e.tokens_used ?? 0}</td>
                    <td className="px-4 py-3 text-gray-400 tabular-nums text-xs">${(e.cost_usd ?? 0).toFixed(4)}</td>
                    <td className="px-4 py-3 text-gray-500 text-xs whitespace-nowrap">{fmtTs(e.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* Documents (RAG) */}
      {tab === 'documents' && (
        documents.length === 0 && !loading ? empty('No documents ingested.') : (
          <div className="bg-gray-900 rounded-lg border border-gray-700 overflow-hidden">
            <table className="w-full text-sm" aria-label="RAG documents" aria-busy={loading}>
              <thead>
                <tr className="border-b border-gray-700">
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Title</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Source</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Chunks</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Embedding</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Created</th>
                </tr>
              </thead>
              <tbody>
                {documents.map(d => (
                  <tr key={d.id} className="border-b border-gray-800 hover:bg-gray-800/50">
                    <td className="px-4 py-3 text-gray-200 font-medium text-sm">{d.title}</td>
                    <td className="px-4 py-3 text-gray-500 text-xs font-mono truncate max-w-xs">{d.source || '—'}</td>
                    <td className="px-4 py-3 text-gray-400 tabular-nums text-sm">{d.chunk_count ?? 0}</td>
                    <td className={`px-4 py-3 text-xs ${STATUS_COLOR[d.embedding_status] ?? 'text-gray-400'}`}>{d.embedding_status}</td>
                    <td className="px-4 py-3 text-gray-500 text-xs whitespace-nowrap">{fmtTs(d.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* Agent Tools */}
      {tab === 'tools' && (
        tools.length === 0 && !loading ? empty('No agent tools registered.') : (
          <div className="bg-gray-900 rounded-lg border border-gray-700 overflow-hidden">
            <table className="w-full text-sm" aria-label="Agent tools" aria-busy={loading}>
              <thead>
                <tr className="border-b border-gray-700">
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Name</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Description</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Type</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Active</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Created</th>
                </tr>
              </thead>
              <tbody>
                {tools.map(t => (
                  <tr key={t.id} className="border-b border-gray-800 hover:bg-gray-800/50">
                    <td className="px-4 py-3 text-gray-200 font-medium font-mono text-sm">{t.name}</td>
                    <td className="px-4 py-3 text-gray-400 text-xs max-w-xs truncate">{t.description || '—'}</td>
                    <td className="px-4 py-3">
                      <span className="text-xs bg-orange-900/30 text-orange-300 border border-orange-700 rounded-full px-2 py-0.5">{t.tool_type}</span>
                    </td>
                    <td className="px-4 py-3 text-xs">
                      <span className={t.is_active ? 'text-green-400' : 'text-gray-600'}>{t.is_active ? 'yes' : 'no'}</span>
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs whitespace-nowrap">{fmtTs(t.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  )
}
