import React, { useEffect, useState } from 'react'
import { useAnalytics } from '../hooks/useAnalytics'

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
  tier: 'optional' | 'planned'
}

const OPTIONAL_SERVICES: ServiceDef[] = [
  {
    id: 'library',
    name: 'The Library',
    leadAI: 'Zimik',
    description: 'Knowledge base & wiki — structured documentation for the entire platform.',
    path: '/library',
    port: 3300,
    icon: '📚',
    profile: 'library',
    tier: 'optional',
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
    tier: 'optional',
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
    tier: 'optional',
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
    tier: 'optional',
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
    tier: 'optional',
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
    tier: 'optional',
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
    tier: 'optional',
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
    tier: 'optional',
  },
]

const PLANNED_SERVICES: ServiceDef[] = [
  {
    id: 'academy',
    name: 'The Academy',
    leadAI: 'Shimshi',
    description: 'Learning management — education & skill training. Courses, lessons, progress tracking.',
    path: '/academy',
    port: 8040,
    icon: '🎓',
    profile: 'academy',
    tier: 'planned',
  },
  {
    id: 'basement',
    name: 'The Basement',
    leadAI: 'Gary Glowman',
    description: 'Cold archive — compressed, indexed long-term storage from The Observatory.',
    path: '/basement',
    port: 8041,
    icon: '🗄️',
    profile: 'basement',
    tier: 'planned',
  },
  {
    id: 'studio',
    name: 'The Studio',
    leadAI: 'Voxx',
    description: 'Central hub of the Creativity Center — orchestrates all creative sub-services.',
    path: '/studio',
    port: 8050,
    icon: '🎬',
    profile: 'studio',
    tier: 'planned',
  },
  {
    id: 'photo',
    name: 'Sashas Photo Studio',
    leadAI: 'Madam Krystal',
    description: 'Photo & image generation — Stable Diffusion with adaptive free-tier rotation.',
    path: '/photo',
    port: 8051,
    icon: '📸',
    profile: 'photo',
    tier: 'planned',
  },
  {
    id: 'tranceflow',
    name: 'TranceFlow',
    leadAI: 'Junior Cesar',
    description: '3D modeling & games — asset pipeline, GLTF export, Three.js scene builder.',
    path: '/tranceflow',
    port: 8052,
    icon: '🎮',
    profile: 'tranceflow',
    tier: 'planned',
  },
  {
    id: 'tateking',
    name: 'TateKing',
    leadAI: 'Benji Tate & Sam King',
    description: 'Video creation & editing — FFmpeg transcoding, thumbnail extraction, job queue.',
    path: '/video',
    port: 8053,
    icon: '🎥',
    profile: 'tateking',
    tier: 'planned',
  },
  {
    id: 'imaginarium',
    name: 'Imaginarium',
    leadAI: 'Voxx',
    description: 'Omni-creative wizard — routes to image, video, 3D, or design based on intent.',
    path: '/imaginarium',
    port: 8054,
    icon: '✨',
    profile: 'imaginarium',
    tier: 'planned',
  },
  {
    id: 'lab',
    name: 'The Lab',
    leadAI: 'The Dr. & Slime',
    description: 'Code creation platform — generate, review, and manage code via The Spark MCP.',
    path: '/lab',
    port: 8055,
    icon: '🔬',
    profile: 'lab',
    tier: 'planned',
  },
  {
    id: 'warp-tunnel',
    name: 'The Warp Tunnel',
    leadAI: 'Rocking Ricki',
    description: 'Cryptographic scanner & quarantine transport — ClamAV + YARA threat detection.',
    path: '/warp-tunnel',
    port: 8056,
    icon: '🌀',
    profile: 'warp-tunnel',
    tier: 'planned',
  },
  {
    id: 'radio',
    name: 'Warp Radio',
    leadAI: 'Rocking Ricki',
    description: 'Music & audio streaming — Navidrome backend with library scanning.',
    path: '/radio',
    port: 8057,
    icon: '📻',
    profile: 'radio',
    tier: 'planned',
  },
  {
    id: 'dutchy',
    name: 'The Dutchy',
    leadAI: 'Predictive lore',
    description: 'Intelligence & market analysis — RSS signals, keyword extraction, daily reports.',
    path: '/dutchy',
    port: 8058,
    icon: '📊',
    profile: 'dutchy',
    tier: 'planned',
  },
  {
    id: 'devocity',
    name: 'DevOcity',
    leadAI: 'Kitty',
    description: 'Development operations hub — service topology graph and health matrix.',
    path: '/devocity',
    port: 8059,
    icon: '🏙️',
    profile: 'devocity',
    tier: 'planned',
  },
  {
    id: 'tranquility',
    name: 'Tranquility',
    leadAI: 'Savania',
    description: 'Wellbeing central — habit tracker, mindfulness timer, mood journal.',
    path: '/tranquility',
    port: 8060,
    icon: '🌿',
    profile: 'tranquility',
    tier: 'planned',
  },
  {
    id: 'imind',
    name: 'I-Mind',
    leadAI: 'Elouise',
    description: 'Emotion sensitivity engine — real-time sentiment analysis and emotional profiling.',
    path: '/imind',
    port: 8061,
    icon: '🧠',
    profile: 'imind',
    tier: 'planned',
  },
  {
    id: 'taimra',
    name: 'tAimra',
    leadAI: 'tAImra',
    description: 'Opt-in digital twin & life assistant — personal context store and advisor.',
    path: '/taimra',
    port: 8062,
    icon: '👤',
    profile: 'taimra',
    tier: 'planned',
  },
  {
    id: 'vrar3d',
    name: 'VRAR3D',
    leadAI: 'Entari',
    description: 'Standalone 3D / VR immersion — Three.js scene server with AR marker generation.',
    path: '/vrar3d',
    port: 8063,
    icon: '🥽',
    profile: 'vrar3d',
    tier: 'planned',
  },
  {
    id: 'resonate',
    name: 'Resonate',
    leadAI: 'Magdalena',
    description: 'Empathy engine — scores and rewrites text for maximum empathetic resonance.',
    path: '/resonate',
    port: 8064,
    icon: '💜',
    profile: 'resonate',
    tier: 'planned',
  },
  {
    id: 'chaos',
    name: 'The Chaos Party',
    leadAI: 'The Mad Hatter',
    description: 'Central testing platform — chaos testing, validation & compliance (Alice in Wonderland themed).',
    path: '/chaos',
    port: 8065,
    icon: '🎩',
    profile: 'chaos',
    tier: 'planned',
  },
]

const SERVICES = [...OPTIONAL_SERVICES, ...PLANNED_SERVICES]

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
  const { trackPageView } = useAnalytics()

  useEffect(() => { trackPageView('/services') }, [trackPageView])

  useEffect(() => {
    let cancelled = false
    // /optional-health proxies to health-aggregator :8029; /status returns bulk service list
    fetch('/optional-health/status')
      .then(r => r.json())
      .then((data: { services?: Array<{ name: string; status: string; latency_ms?: number }> }) => {
        if (cancelled) return
        const statusMap: Record<string, { status: string; latency_ms?: number }> = {}
        for (const s of data.services ?? []) {
          // health-aggregator uses "healthy" not "ok"
          const mappedStatus = s.status === 'healthy' ? 'healthy' : s.status
          statusMap[s.name] = { status: mappedStatus, latency_ms: s.latency_ms }
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

  const optional = services.filter(s => s.tier === 'optional')
  const planned = services.filter(s => s.tier === 'planned')
  const healthy = services.filter(s => s.status === 'healthy').length
  const total = services.length

  return (
    <div className="min-h-screen bg-gray-950 text-white p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white mb-1">Platform Services</h1>
          <p className="text-gray-400 text-sm">
            All 26 Trancendos services across 43 entities — start any with{' '}
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

        {/* Optional services */}
        <section className="mb-10">
          <div className="flex items-center gap-3 mb-4">
            <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
              Optional Services
            </h2>
            <span className="text-xs bg-indigo-900/50 text-indigo-300 px-2 py-0.5 rounded-full border border-indigo-700/50">
              {optional.length} services
            </span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {optional.map(svc => (
              <ServiceCard key={svc.id} service={svc} loading={loading} />
            ))}
          </div>
        </section>

        {/* Planned entities */}
        <section className="mb-10">
          <div className="flex items-center gap-3 mb-4">
            <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
              Planned Entities
            </h2>
            <span className="text-xs bg-violet-900/50 text-violet-300 px-2 py-0.5 rounded-full border border-violet-700/50">
              {planned.length} services
            </span>
            <span className="text-xs text-gray-600">
              — FastAPI workers ready, start with docker compose --profile &lt;name&gt;
            </span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {planned.map(svc => (
              <ServiceCard key={svc.id} service={svc} loading={loading} />
            ))}
          </div>
        </section>

        {/* Quick start */}
        <div className="p-5 bg-gray-900 border border-gray-700 rounded-xl">
          <h2 className="text-sm font-semibold text-gray-300 mb-3 uppercase tracking-wider">
            Quick Start
          </h2>
          <div className="space-y-1.5">
            {[
              ['Start optional services', 'bash scripts/optional-services.sh start all'],
              ['Start planned entities', 'docker compose -f docker-compose.planned-entities.yml --profile all up -d'],
              ['Generate secrets', 'bash scripts/optional-services.sh gen-secrets'],
              ['Check status', 'bash scripts/optional-services.sh status'],
            ].map(([label, cmd]) => (
              <div key={cmd} className="flex items-start gap-3">
                <span className="text-xs text-gray-500 w-44 shrink-0 pt-0.5">{label}</span>
                <code className="text-xs text-indigo-300 bg-gray-800 px-2 py-0.5 rounded font-mono break-all">
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
  const borderHover = svc.tier === 'planned' ? 'hover:border-violet-700' : 'hover:border-indigo-700'

  return (
    <div className={`flex flex-col bg-gray-900 border border-gray-700 rounded-xl p-4 transition-colors ${borderHover}`}>
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
