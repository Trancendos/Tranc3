import React, { useEffect, useState } from 'react'

interface ServiceDef {
  id: string
  name: string
  leadAI: string
  description: string
  path: string
  port: number
  icon: string
  status?: 'healthy' | 'degraded' | 'unreachable' | 'unknown'
  latency_ms?: number
  profile: string
}

const SERVICES: ServiceDef[] = [
  {
    id: 'library',
    name: 'The Library',
    leadAI: 'Zimik',
    description: 'Knowledge base & wiki — structured documentation for the entire platform.',
    path: '/library',
    port: 3300,
    icon: '📚',
    profile: 'library',
  },
  {
    id: 'documents',
    name: 'DocUtari',
    leadAI: 'To be Defined',
    description: 'Document management hub — OCR, search, and archive for all documents.',
    path: '/documents',
    port: 8765,
    icon: '🗂️',
    profile: 'documents',
  },
  {
    id: 'design',
    name: 'Fabulousa',
    leadAI: 'Baron Von Hilton',
    description: 'Styling, UX, UI & design centre — self-hosted Figma alternative.',
    path: '/design',
    port: 9001,
    icon: '🎨',
    profile: 'design',
  },
  {
    id: 'workshop',
    name: 'The Workshop',
    leadAI: 'Larry Lowhammer',
    description: 'CI/CD hub — Forgejo self-hosted git + pipelines + act-runner.',
    path: '/the-workshop',
    port: 3456,
    icon: '🔧',
    profile: 'workshop',
  },
  {
    id: 'scheduling',
    name: 'ChronosSphere',
    leadAI: 'Chronos',
    description: 'Task, time & scheduling management — self-hosted Cal.com.',
    path: '/scheduling',
    port: 3001,
    icon: '⏱️',
    profile: 'scheduling',
  },
  {
    id: 'registry',
    name: 'The Artifactory',
    leadAI: 'Lunascene',
    description: 'OCI artifact registry — Docker images, Helm charts, WASM modules.',
    path: '/registry',
    port: 5001,
    icon: '📦',
    profile: 'registry',
  },
  {
    id: 'api-marketplace',
    name: 'API Marketplace',
    leadAI: 'Solarscene',
    description: 'Central integration hub — REST, webhooks, OAuth, rate limiting via Gravitee.',
    path: '/api-marketplace',
    port: 8084,
    icon: '🌐',
    profile: 'api-marketplace',
  },
  {
    id: 'sandbox',
    name: 'The Ice Box',
    leadAI: 'Neonach',
    description: 'Sandbox threat isolation & quarantine — malware analysis and containment.',
    path: '/sandbox',
    port: 8090,
    icon: '🧊',
    profile: 'sandbox',
  },
]

const STATUS_COLORS: Record<string, string> = {
  healthy: 'bg-emerald-500',
  degraded: 'bg-amber-500',
  unreachable: 'bg-red-500',
  unknown: 'bg-gray-500',
}

const STATUS_LABELS: Record<string, string> = {
  healthy: 'Online',
  degraded: 'Degraded',
  unreachable: 'Offline',
  unknown: 'Unknown',
}

function StatusDot({ status = 'unknown' }: { status?: string }) {
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full ${STATUS_COLORS[status] ?? 'bg-gray-500'}`}
      aria-label={STATUS_LABELS[status] ?? 'Unknown'}
    />
  )
}

export default function ServicesPage() {
  const [services, setServices] = useState<ServiceDef[]>(SERVICES)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    fetch('/optional-health/health')
      .then(r => r.json())
      .then((data: { services?: Array<{ name: string; status: string; latency_ms?: number }> }) => {
        if (cancelled) return
        const statusMap: Record<string, { status: string; latency_ms?: number }> = {}
        for (const s of data.services ?? []) {
          statusMap[s.name] = { status: s.status, latency_ms: s.latency_ms }
        }
        setServices(prev =>
          prev.map(svc => ({
            ...svc,
            status: (statusMap[svc.id]?.status as ServiceDef['status']) ?? 'unknown',
            latency_ms: statusMap[svc.id]?.latency_ms,
          }))
        )
      })
      .catch(() => {
        if (!cancelled) {
          setServices(prev => prev.map(s => ({ ...s, status: 'unknown' })))
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [])

  const healthy = services.filter(s => s.status === 'healthy').length
  const total = services.length

  return (
    <div className="min-h-screen bg-gray-950 text-white p-6">
      {/* Header */}
      <div className="max-w-6xl mx-auto">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white mb-1">Platform Services</h1>
          <p className="text-gray-400 text-sm">
            All optional Trancendos services — start any service with{' '}
            <code className="bg-gray-800 px-1.5 py-0.5 rounded text-xs text-indigo-300">
              bash scripts/optional-services.sh start &lt;profile&gt;
            </code>
          </p>
          {!loading && (
            <p className="mt-2 text-xs text-gray-500">
              {healthy}/{total} services reachable
            </p>
          )}
        </div>

        {/* Service grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {services.map(svc => (
            <ServiceCard key={svc.id} service={svc} loading={loading} />
          ))}
        </div>

        {/* Start instructions */}
        <div className="mt-10 p-5 bg-gray-900 border border-gray-700 rounded-xl">
          <h2 className="text-sm font-semibold text-gray-300 mb-3 uppercase tracking-wider">
            Quick Start
          </h2>
          <div className="space-y-1.5">
            {[
              ['Start all services', 'bash scripts/optional-services.sh start all'],
              ['Start specific service', 'bash scripts/optional-services.sh start library'],
              ['Generate secrets', 'bash scripts/optional-services.sh gen-secrets'],
              ['Check status', 'bash scripts/optional-services.sh status'],
            ].map(([label, cmd]) => (
              <div key={cmd} className="flex items-start gap-3">
                <span className="text-xs text-gray-500 w-40 shrink-0 pt-0.5">{label}</span>
                <code className="text-xs text-indigo-300 bg-gray-800 px-2 py-0.5 rounded font-mono">
                  {cmd}
                </code>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function ServiceCard({ service: svc, loading }: { service: ServiceDef; loading: boolean }) {
  const isOnline = svc.status === 'healthy'

  return (
    <div className="flex flex-col bg-gray-900 border border-gray-700 rounded-xl p-4 hover:border-gray-500 transition-colors">
      {/* Top row */}
      <div className="flex items-start justify-between mb-3">
        <span className="text-2xl" role="img" aria-label={svc.name}>
          {svc.icon}
        </span>
        <div className="flex items-center gap-1.5">
          {loading ? (
            <span className="inline-block w-2 h-2 rounded-full bg-gray-600 animate-pulse" />
          ) : (
            <StatusDot status={svc.status} />
          )}
          <span className="text-xs text-gray-400">
            {loading ? '…' : (STATUS_LABELS[svc.status ?? 'unknown'] ?? 'Unknown')}
          </span>
        </div>
      </div>

      {/* Name + Lead AI */}
      <h3 className="font-semibold text-white text-sm mb-0.5">{svc.name}</h3>
      <p className="text-xs text-indigo-400 mb-2">{svc.leadAI}</p>
      <p className="text-xs text-gray-400 flex-1 leading-relaxed">{svc.description}</p>

      {/* Footer */}
      <div className="mt-4 flex items-center justify-between">
        <span className="text-xs text-gray-600">:{svc.port}</span>
        {svc.latency_ms !== undefined && (
          <span className="text-xs text-gray-600">{svc.latency_ms}ms</span>
        )}
        <a
          href={svc.path}
          target="_blank"
          rel="noopener noreferrer"
          className={`text-xs px-3 py-1 rounded-lg font-medium transition-colors ${
            isOnline
              ? 'bg-indigo-600 hover:bg-indigo-500 text-white'
              : 'bg-gray-700 text-gray-500 cursor-not-allowed pointer-events-none'
          }`}
          aria-disabled={!isOnline}
          tabIndex={isOnline ? 0 : -1}
        >
          Open →
        </a>
      </div>

      {/* Profile badge */}
      <div className="mt-2">
        <span className="text-xs text-gray-600">
          profile: <code className="text-gray-500">{svc.profile}</code>
        </span>
      </div>
    </div>
  )
}
