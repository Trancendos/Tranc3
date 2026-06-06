import React, { useEffect, useState, useId } from 'react'
import { Zap, RefreshCw, CheckCircle, XCircle, Code, List } from 'lucide-react'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface MCPTool {
  name: string
  description: string
  schema?: Record<string, unknown>
  calls_today?: number
}

interface SparkHealth {
  status: 'ok' | 'degraded' | 'down' | 'unknown'
  tools: number
  latencyMs?: number
}

export default function SparkDashboard() {
  const [tools, setTools] = useState<MCPTool[]>([])
  const [health, setHealth] = useState<SparkHealth>({ status: 'unknown', tools: 0 })
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<MCPTool | null>(null)
  const [lastRun, setLastRun] = useState<string | null>(null)
  const toolDetailId = useId()
  const statusId = useId()

  async function fetchTools() {
    setLoading(true)
    const t0 = performance.now()
    try {
      const [healthRes, toolsRes] = await Promise.all([
        fetch(`${API}/mcp/health`, { signal: AbortSignal.timeout(5000) }),
        fetch(`${API}/mcp/tools`,  { signal: AbortSignal.timeout(5000) }),
      ])
      const latencyMs = Math.round(performance.now() - t0)

      if (healthRes.ok) {
        const h = await healthRes.json().catch(() => ({}))
        setHealth({ status: h.status ?? 'ok', tools: 0, latencyMs })
      } else {
        setHealth({ status: 'down', tools: 0, latencyMs })
      }

      if (toolsRes.ok) {
        const body = await toolsRes.json().catch(() => ({ tools: [] }))
        const list: MCPTool[] = Array.isArray(body) ? body : (body.tools ?? [])
        setTools(list)
        setHealth((prev) => ({ ...prev, tools: list.length }))
      }
    } catch {
      setHealth({ status: 'unknown', tools: 0 })
    }
    setLastRun(new Date().toLocaleTimeString())
    setLoading(false)
  }

  useEffect(() => {
    fetchTools()
    const iv = setInterval(fetchTools, 30_000)
    return () => clearInterval(iv)
  }, [])

  const statusLabel = health.status === 'ok' ? 'Online' :
                      health.status === 'degraded' ? 'Degraded' :
                      health.status === 'down' ? 'Down' : 'Unknown'

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Live status announcer */}
      <div id={statusId} role="status" aria-live="polite" aria-atomic="true" className="sr-only">
        {lastRun ? `The Spark status updated at ${lastRun}. MCP Server: ${statusLabel}. ${health.tools} tools registered.` : ''}
      </div>

      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Zap size={22} aria-hidden="true" className="text-yellow-400" />
            The Spark
          </h1>
          <p className="text-gray-400 text-sm mt-1">
            MCP Server — AI tool registry, JSON-RPC 2.0 over HTTP/SSE
            {lastRun ? ` · ${lastRun}` : ''}
          </p>
        </div>
        <button
          onClick={fetchTools}
          disabled={loading}
          aria-busy={loading}
          aria-label={loading ? 'Refreshing Spark status' : 'Refresh Spark status'}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg text-sm text-white transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
        >
          <RefreshCw size={14} aria-hidden="true" className={loading ? 'animate-spin' : ''} />
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {/* Health summary */}
      <div
        className="grid grid-cols-3 gap-4 mb-6"
        role="list"
        aria-label="Spark health summary"
      >
        {[
          {
            label: 'MCP Server',
            value: statusLabel,
            color: health.status === 'ok' ? 'text-green-400 border-green-600' : 'text-red-400 border-red-600',
            icon: health.status === 'ok'
              ? <CheckCircle size={18} aria-hidden="true" />
              : <XCircle    size={18} aria-hidden="true" />,
          },
          {
            label: 'Registered Tools',
            value: health.tools.toString(),
            color: 'text-indigo-400 border-indigo-700',
            icon: <List size={18} aria-hidden="true" />,
          },
          {
            label: 'Latency',
            value: health.latencyMs != null ? `${health.latencyMs}ms` : '—',
            color: 'text-gray-400 border-gray-600',
            icon: <Zap size={18} aria-hidden="true" />,
          },
        ].map(({ label, value, color, icon }) => (
          <div
            key={label}
            role="listitem"
            aria-label={`${label}: ${value}`}
            className={`bg-gray-900 border ${color} rounded-lg p-4`}
          >
            <div className={`flex items-center gap-2 ${color.split(' ')[0]}`} aria-hidden="true">
              {icon}
              <span className="text-xl font-bold capitalize">{value}</span>
            </div>
            <p className="text-gray-500 text-sm mt-1">{label}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Tool list */}
        <section aria-label="Registered tools" className="lg:col-span-1">
          <h2 className="text-white font-semibold mb-3 flex items-center gap-2">
            <List size={16} aria-hidden="true" />
            Tools ({tools.length})
          </h2>
          {tools.length === 0 ? (
            <div role="status" className="bg-gray-900 border border-gray-700 rounded-lg p-4 text-gray-500 text-sm text-center">
              {health.status === 'down' ? 'MCP server offline' : 'No tools registered'}
            </div>
          ) : (
            <ul
              aria-label="MCP tools"
              className="space-y-1 max-h-[60vh] overflow-y-auto pr-1 list-none"
            >
              {tools.map((t) => (
                <li key={t.name}>
                  <button
                    onClick={() => setSelected(t)}
                    aria-pressed={selected?.name === t.name}
                    aria-controls={toolDetailId}
                    className={`w-full text-left px-3 py-2 rounded-md text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 ${
                      selected?.name === t.name
                        ? 'bg-indigo-700 text-white'
                        : 'text-gray-300 hover:bg-gray-800'
                    }`}
                  >
                    <span className="font-mono text-xs">{t.name}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Tool detail */}
        <section aria-label="Tool detail" className="lg:col-span-2">
          <h2 className="text-white font-semibold mb-3 flex items-center gap-2">
            <Code size={16} aria-hidden="true" />
            Tool Detail
          </h2>
          <div id={toolDetailId}>
            {selected ? (
              <div className="bg-gray-900 border border-gray-700 rounded-lg p-5">
                <p className="text-indigo-400 font-mono text-sm mb-2">{selected.name}</p>
                <p className="text-gray-300 text-sm mb-4">{selected.description}</p>
                {selected.schema && (
                  <>
                    <p className="text-gray-500 text-xs mb-1" id="schema-label">Schema</p>
                    <pre
                      aria-labelledby="schema-label"
                      tabIndex={0}
                      className="bg-gray-950 rounded p-3 text-xs text-gray-400 overflow-auto max-h-48 whitespace-pre-wrap focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                    >
                      {JSON.stringify(selected.schema, null, 2)}
                    </pre>
                  </>
                )}
                {selected.calls_today != null && (
                  <p className="text-gray-600 text-xs mt-3">Calls today: {selected.calls_today}</p>
                )}
              </div>
            ) : (
              <div role="status" className="bg-gray-900 border border-gray-700 rounded-lg p-8 text-center text-gray-600">
                <Zap size={32} aria-hidden="true" className="mx-auto mb-2 opacity-20" />
                <p className="text-sm">Select a tool from the list</p>
              </div>
            )}
          </div>

          {/* Routes */}
          <h2 className="text-white font-semibold mt-5 mb-3">MCP Endpoints</h2>
          <div className="bg-gray-900 border border-gray-700 rounded-lg divide-y divide-gray-800">
            {[
              { method: 'POST', path: '/mcp/rpc',         desc: 'JSON-RPC 2.0 tool call endpoint' },
              { method: 'GET',  path: '/mcp/sse',         desc: 'Server-Sent Events stream' },
              { method: 'GET',  path: '/mcp/tools',       desc: 'List registered tools' },
              { method: 'GET',  path: '/mcp/health',      desc: 'Health check' },
              { method: 'GET',  path: '/mcp/grid/status', desc: 'Digital Grid workflow status' },
            ].map(({ method, path, desc }) => (
              <div key={path} className="px-4 py-2.5 flex items-center gap-3">
                <span className={`text-xs font-mono px-1.5 py-0.5 rounded ${
                  method === 'POST' ? 'bg-indigo-900/60 text-indigo-400' : 'bg-green-900/60 text-green-400'
                }`}>{method}</span>
                <code className="text-gray-300 text-xs font-mono flex-1">{path}</code>
                <span className="text-gray-600 text-xs">{desc}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}
