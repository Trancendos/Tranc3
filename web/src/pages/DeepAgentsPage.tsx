/**
 * DeepAgentsPage — Multi-Agent Orchestration (Port 8037)
 *
 * Displays live agent roster, task pipeline, delegation depth,
 * and skill registry from the deepagents-orchestrator service.
 */
import React, { useEffect, useState, useCallback } from 'react'
import { Network, RefreshCw, User, ListChecks, GitBranch, Zap } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const AGENTS_API = '/dagents'

interface AgentStats {
  agents: { total: number; active: number }
  tasks: { total: number; pending: number; running: number; completed: number; failed: number }
  delegations: number
  skills: number
  execution_logs: number
}

interface Agent {
  id: string
  name: string
  status: string
  capabilities: string[]
  priority: number
  task_count: number
}

interface Task {
  id: string
  title: string
  status: string
  priority: number
  created_at: number
  assigned_agent_id?: string
}

const STATUS_COLOR: Record<string, string> = {
  active:    'text-green-400',
  idle:      'text-gray-400',
  busy:      'text-yellow-400',
  offline:   'text-red-400',
  pending:   'text-gray-400',
  assigned:  'text-blue-400',
  running:   'text-yellow-400',
  completed: 'text-green-400',
  failed:    'text-red-400',
}

function StatTile({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="bg-gray-900 border border-gray-700 rounded-lg p-4">
      <div className={`text-2xl font-bold tabular-nums ${color}`}>{value}</div>
      <div className="text-gray-400 text-sm mt-1">{label}</div>
    </div>
  )
}

export default function DeepAgentsPage() {
  const [stats, setStats]         = useState<AgentStats | null>(null)
  const [agents, setAgents]       = useState<Agent[]>([])
  const [tasks, setTasks]         = useState<Task[]>([])
  const [loading, setLoading]     = useState(false)
  const [workerDown, setWorkerDown] = useState(false)
  const [tab, setTab]             = useState<'agents' | 'tasks'>('agents')
  const { trackPageView } = useAnalytics()

  useEffect(() => { trackPageView('/deep-agents') }, [trackPageView])

  const load = useCallback(async () => {
    setLoading(true)
    setWorkerDown(false)
    try {
      const [sRes, aRes, tRes] = await Promise.all([
        fetch(`${AGENTS_API}/stats`,  { signal: AbortSignal.timeout(4000) }),
        fetch(`${AGENTS_API}/agents`, { signal: AbortSignal.timeout(4000) }),
        fetch(`${AGENTS_API}/tasks`,  { signal: AbortSignal.timeout(4000) }),
      ])
      if (sRes.ok) setStats(await sRes.json())
      if (aRes.ok) {
        const body = await aRes.json()
        setAgents(Array.isArray(body) ? body : (body.agents ?? []))
      }
      if (tRes.ok) {
        const body = await tRes.json()
        setTasks(Array.isArray(body) ? body.slice(0, 50) : (body.tasks ?? []).slice(0, 50))
      }
      if (!sRes.ok && !aRes.ok) setWorkerDown(true)
    } catch {
      setWorkerDown(true)
    }
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  const fmtTs = (ts: number) => new Date(ts * 1000).toLocaleString()

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Network size={22} aria-hidden="true" className="text-orange-400" />
            Deep Agents
          </h1>
          <p className="text-gray-400 text-sm mt-1">
            Multi-Agent Orchestration · Port 8037
            {stats && ` · ${stats.agents.total} agents · ${stats.tasks.total} tasks`}
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
          Deep Agents worker (port 8037) is unreachable. Start with{' '}
          <code className="font-mono bg-gray-800 px-1 rounded">make dev-api</code>.
        </div>
      )}

      {/* Stats tiles */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
          <StatTile label="Agents"     value={stats.agents.total}      color="text-orange-400" />
          <StatTile label="Active"     value={stats.agents.active}     color="text-green-400" />
          <StatTile label="Tasks"      value={stats.tasks.total}       color="text-blue-400" />
          <StatTile label="Skills"     value={stats.skills}            color="text-purple-400" />
          <StatTile label="Pending"    value={stats.tasks.pending}     color="text-gray-400" />
          <StatTile label="Running"    value={stats.tasks.running}     color="text-yellow-400" />
          <StatTile label="Completed"  value={stats.tasks.completed}   color="text-green-400" />
          <StatTile label="Delegations" value={stats.delegations}      color="text-indigo-400" />
        </div>
      )}

      {/* Tabs */}
      <div role="tablist" className="flex gap-2 mb-5">
        {(['agents', 'tasks'] as const).map(t => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium border transition-colors ${
              tab === t
                ? 'bg-indigo-600 text-white border-indigo-500'
                : 'bg-gray-900 text-gray-400 border-gray-700 hover:border-gray-500'
            }`}
          >
            {t === 'agents'
              ? <><User size={12} className="inline mr-1.5" aria-hidden="true" />Agents</>
              : <><ListChecks size={12} className="inline mr-1.5" aria-hidden="true" />Tasks</>}
          </button>
        ))}
      </div>

      {/* Agents tab */}
      {tab === 'agents' && (
        agents.length === 0 && !loading ? (
          <div className="bg-gray-900 rounded-lg border border-gray-700 p-8 text-center text-gray-500">
            {workerDown ? 'Worker offline' : 'No agents registered.'}
          </div>
        ) : (
          <div className="bg-gray-900 rounded-lg border border-gray-700 overflow-hidden">
            <table className="w-full text-sm" aria-label="Agent roster" aria-busy={loading}>
              <thead>
                <tr className="border-b border-gray-700">
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Agent</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Status</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Priority</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Tasks</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Capabilities</th>
                </tr>
              </thead>
              <tbody>
                {agents.map(a => (
                  <tr key={a.id} className="border-b border-gray-800 hover:bg-gray-800/50">
                    <td className="px-4 py-3">
                      <div className="text-gray-200 font-medium">{a.name}</div>
                      <div className="text-gray-600 text-xs font-mono">{a.id.slice(0, 8)}…</div>
                    </td>
                    <td className={`px-4 py-3 text-sm ${STATUS_COLOR[a.status] ?? 'text-gray-400'}`}>
                      {a.status}
                    </td>
                    <td className="px-4 py-3 text-gray-400 tabular-nums text-sm">{a.priority}</td>
                    <td className="px-4 py-3 text-gray-400 tabular-nums text-sm">{a.task_count ?? 0}</td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {(a.capabilities ?? []).slice(0, 4).map(c => (
                          <span key={c} className="text-xs bg-gray-800 text-gray-400 rounded px-1.5 py-0.5">{c}</span>
                        ))}
                        {(a.capabilities ?? []).length > 4 && (
                          <span className="text-xs text-gray-600">+{a.capabilities.length - 4}</span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* Tasks tab */}
      {tab === 'tasks' && (
        tasks.length === 0 && !loading ? (
          <div className="bg-gray-900 rounded-lg border border-gray-700 p-8 text-center text-gray-500">
            {workerDown ? 'Worker offline' : 'No tasks in queue.'}
          </div>
        ) : (
          <div className="bg-gray-900 rounded-lg border border-gray-700 overflow-hidden">
            <table className="w-full text-sm" aria-label="Task pipeline" aria-busy={loading}>
              <thead>
                <tr className="border-b border-gray-700">
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Task</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Status</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Priority</th>
                  <th scope="col" className="text-left px-4 py-3 text-gray-400 font-medium">Created</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map(t => (
                  <tr key={t.id} className="border-b border-gray-800 hover:bg-gray-800/50">
                    <td className="px-4 py-3">
                      <div className="text-gray-200 font-medium">{t.title}</div>
                      <div className="text-gray-600 text-xs font-mono">{t.id.slice(0, 8)}…</div>
                    </td>
                    <td className={`px-4 py-3 text-sm ${STATUS_COLOR[t.status] ?? 'text-gray-400'}`}>
                      {t.status}
                    </td>
                    <td className="px-4 py-3 text-gray-400 tabular-nums text-sm">{t.priority}</td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{fmtTs(t.created_at)}</td>
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
