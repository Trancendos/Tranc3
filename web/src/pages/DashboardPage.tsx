/**
 * DashboardPage — Trancendos mission control.
 *
 * Central hub showing live platform health, AI provider status,
 * entity grid (all 43 platform entities), and quick-action links.
 * Fluidic layout: cluster grid, adaptive cards, reactive polling.
 */
import React, { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import {
  Brain, Zap, GitBranch, Shield, Eye, Crown, Cpu, Globe,
  BookOpen, Palette, Music, FlaskConical, Layers, Archive,
  Lock, Boxes, Radio, Clock, Mail, Search, Database,
  Server, Network, Activity, Settings, BarChart3, Sparkles, ScrollText
} from 'lucide-react'
import PlatformPulse from '../components/ui/PlatformPulse'
import useReactiveQuery from '../hooks/useReactiveQuery'
import { useAnalytics } from '../hooks/useAnalytics'

const API = (import.meta.env.VITE_API_URL as string | undefined) ?? ''

interface ProviderDashboard {
  active_provider: string
  zero_cost_operational: boolean
  providers: Record<string, {
    status: string
    available: boolean
    utilisation_pct: number
    daily_req: string
  }>
}

const ENTITY_GRID = [
  { name: 'The Spark',         icon: Zap,         path: '/spark',       status: 'live',    color: '#f59e0b' },
  { name: 'The Digital Grid',  icon: GitBranch,    path: '/grid',        status: 'live',    color: '#10b981' },
  { name: 'Infinity',          icon: Shield,       path: '/services',    status: 'live',    color: '#6366f1' },
  { name: 'The Observatory',   icon: Eye,          path: '/status',      status: 'live',    color: '#06b6d4' },
  { name: 'The Nexus',         icon: Radio,        path: '/services',    status: 'live',    color: '#8b5cf6' },
  { name: 'The Town Hall',     icon: Crown,        path: '/services',    status: 'live',    color: '#f97316' },
  { name: 'Luminous',          icon: Brain,        path: '/services',    status: 'partial', color: '#ec4899' },
  { name: "Turing's Hub",      icon: Cpu,          path: '/turings-hub', status: 'partial', color: '#14b8a6' },
  { name: 'Arcadia',           icon: Globe,        path: '/services',    status: 'partial', color: '#84cc16' },
  { name: 'The Library',       icon: BookOpen,     path: '/services',    status: 'planned', color: '#64748b' },
  { name: 'The Academy',       icon: Sparkles,     path: '/services',    status: 'planned', color: '#64748b' },
  { name: 'The Studio',        icon: Palette,      path: '/services',    status: 'planned', color: '#64748b' },
  { name: 'Warp Radio',        icon: Music,        path: '/services',    status: 'planned', color: '#64748b' },
  { name: 'The Lab',           icon: FlaskConical, path: '/the-lab',     status: 'partial', color: '#a855f7' },
  { name: 'LangChain',         icon: Layers,       path: '/langchain',   status: 'partial', color: '#7c3aed' },
  { name: 'Think Tank',        icon: Brain,        path: '/services',    status: 'partial', color: '#a78bfa' },
  { name: 'The Void',          icon: Lock,         path: '/services',    status: 'live',    color: '#ef4444' },
  { name: 'The HIVE',          icon: Layers,       path: '/queue',       status: 'live',    color: '#f59e0b' },
  { name: 'The Basement',      icon: Archive,      path: '/services',    status: 'planned', color: '#64748b' },
  { name: 'DocUtari',          icon: Database,     path: '/storage',     status: 'partial', color: '#0ea5e9' },
  { name: 'Cryptex',           icon: Shield,       path: '/services',    status: 'planned', color: '#64748b' },
  { name: 'The Citadel',       icon: Server,       path: '/admin',       status: 'live',    color: '#22c55e' },
  { name: 'The Workshop',      icon: Settings,     path: '/admin',       status: 'live',    color: '#fb923c' },
  { name: 'ChronosSphere',     icon: Clock,        path: '/services',    status: 'planned', color: '#64748b' },
  { name: 'API Marketplace',   icon: Network,      path: '/services',    status: 'planned', color: '#64748b' },
  { name: 'Royal Bank',        icon: Crown,        path: '/services',    status: 'live',    color: '#eab308' },
  { name: 'Arcadian Exchange', icon: BarChart3,    path: '/services',    status: 'live',    color: '#06b6d4' },
  { name: 'Arcadia Email',     icon: Mail,         path: '/notifications', status: 'partial', color: '#8b5cf6' },
  { name: 'Search',            icon: Search,       path: '/search',      status: 'live',    color: '#10b981' },
  { name: 'The Dutchy',        icon: BarChart3,     path: '/the-dutchy',  status: 'partial', color: '#10b981' },
  { name: 'DevOcity',          icon: Boxes,        path: '/workers',     status: 'planned', color: '#64748b' },
  { name: 'Model Router',      icon: Cpu,          path: '/model-router', status: 'partial', color: '#818cf8' },
  { name: 'Royal Bank Ledger', icon: ScrollText,   path: '/ledger',       status: 'partial', color: '#22c55e' },
  { name: 'Service Topology',  icon: Network,      path: '/topology',     status: 'partial', color: '#3b82f6' },
  { name: 'The Void (Vault)',  icon: Lock,         path: '/vault',        status: 'partial', color: '#ef4444' },
  { name: 'Analytics',         icon: BarChart3,    path: '/analytics',    status: 'partial', color: '#6366f1' },
  { name: 'Config Store',      icon: Settings,     path: '/config',       status: 'partial', color: '#94a3b8' },
  { name: 'ChronosSphere',    icon: Clock,        path: '/cron',         status: 'partial', color: '#a78bfa' },
  { name: 'Cache Service',    icon: Database,     path: '/cache',        status: 'partial', color: '#0ea5e9' },
]

const STATUS_COLORS: Record<string, string> = {
  live:    'text-emerald-400',
  partial: 'text-amber-400',
  planned: 'text-slate-500',
}

const STATUS_DOT: Record<string, string> = {
  live:    'ux-nano-dot--ok',
  partial: 'ux-nano-dot--warn',
  planned: 'ux-nano-dot--unknown',
}

function ProviderBar({ dashboard }: { dashboard: ProviderDashboard }) {
  const entries = Object.entries(dashboard.providers).filter(([p]) => p !== 'offline')
  return (
    <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-white">AI Providers</h3>
        <span className={`text-xs px-2 py-0.5 rounded-full ${dashboard.zero_cost_operational ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'}`}>
          {dashboard.zero_cost_operational ? '✓ zero-cost' : '⚠ degraded'}
        </span>
      </div>
      <p className="text-xs text-slate-400 mb-3">
        Active: <span className="text-white font-medium">{dashboard.active_provider}</span>
      </p>
      <div className="space-y-1.5">
        {entries.map(([name, info]) => (
          <div key={name} className="flex items-center gap-2">
            <span className={`ux-nano-dot ${info.available ? 'ux-nano-dot--ok' : 'ux-nano-dot--critical'}`} />
            <span className="text-xs text-slate-300 w-28 truncate capitalize">{name}</span>
            <div className="flex-1 h-1.5 bg-slate-800 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${info.utilisation_pct > 80 ? 'bg-red-500' : info.utilisation_pct > 60 ? 'bg-amber-500' : 'bg-emerald-500'}`}
                style={{ width: `${Math.min(info.utilisation_pct, 100)}%` }}
              />
            </div>
            <span className="text-xs text-slate-500 w-10 text-right">{info.utilisation_pct}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function DashboardPage() {
  const { data: providers } = useReactiveQuery<ProviderDashboard>({
    url: `${API}/ai/providers`,
    intervalMs: 30_000,
    transform: (raw) => raw as ProviderDashboard,
  })
  const { trackProviderSwitch } = useAnalytics()
  const prevProvider = useRef<string | null>(null)
  useEffect(() => {
    if (!providers?.active_provider) return
    if (prevProvider.current && prevProvider.current !== providers.active_provider) {
      trackProviderSwitch(prevProvider.current, providers.active_provider)
    }
    prevProvider.current = providers.active_provider
  }, [providers?.active_provider, trackProviderSwitch])

  const liveCt  = ENTITY_GRID.filter(e => e.status === 'live').length
  const partCt  = ENTITY_GRID.filter(e => e.status === 'partial').length
  const planCt  = ENTITY_GRID.filter(e => e.status === 'planned').length

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Mission Control</h1>
          <p className="text-sm text-slate-400 mt-0.5">Trancendos Platform — {liveCt} live · {partCt} partial · {planCt} planned</p>
        </div>
        <Link to="/status" className="text-xs text-slate-400 hover:text-slate-200 transition-colors">
          Full status →
        </Link>
      </div>

      {/* Top row: platform pulse + provider bar */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <PlatformPulse />
        {providers ? (
          <ProviderBar dashboard={providers} />
        ) : (
          <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
            <div className="ux-cluster" style={{'--ux-cluster-min': '100px'} as React.CSSProperties}>
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="ux-shimmer rounded h-6" />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Entity grid */}
      <div>
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-widest mb-3">Platform Entities</h2>
        <div className="ux-cluster" style={{'--ux-cluster-min': '160px'} as React.CSSProperties}>
          {ENTITY_GRID.map((entity) => {
            const Icon = entity.icon
            return (
              <Link
                key={entity.name}
                to={entity.path}
                className="ux-liquid ux-card-raised rounded-xl p-3 bg-slate-800/50 hover:bg-slate-800/80 transition-all group block"
              >
                <div className="flex items-start justify-between mb-2">
                  <Icon size={18} style={{ color: entity.color }} />
                  <span className={`ux-nano-dot ${STATUS_DOT[entity.status]}`} />
                </div>
                <p className="text-xs font-medium text-slate-200 truncate">{entity.name}</p>
                <p className={`text-xs mt-0.5 ${STATUS_COLORS[entity.status]}`}>{entity.status}</p>
              </Link>
            )
          })}
        </div>
      </div>

      {/* Quick actions */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: 'AI Providers',  path: '/ai-providers', icon: Brain },
          { label: 'Workers',       path: '/workers',      icon: Cpu },
          { label: 'Search',        path: '/search',       icon: Search },
          { label: 'Compliance',    path: '/compliance',   icon: Shield },
        ].map(({ label, path, icon: Icon }) => (
          <Link
            key={path}
            to={path}
            className="flex items-center gap-2 rounded-lg border border-slate-700/50 bg-slate-900/50 px-3 py-2 text-sm text-slate-300 hover:text-white hover:border-slate-600 transition-all"
          >
            <Icon size={15} className="text-slate-400" />
            {label}
          </Link>
        ))}
      </div>
    </div>
  )
}
