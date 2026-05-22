import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import {
  Brain, Eye, Infinity as InfinityIcon, CircleDot, Lightbulb, Zap, Snowflake,
  GitBranch, Cpu, Clock, Shield, Crown, Palette, Sparkles, Heart,
  MessageSquare, Box, Volume2, Landmark, TrendingUp, Package, Store,
  Grid3X3, FlaskConical, Wrench, Flame, BookOpen, Archive, Hexagon,
  Bug, Building2, Feather, Sun, Activity, AlertTriangle, CheckCircle2,
  XCircle, Radio, Server, HardDrive, Cloud, ArrowLeftRight,
  ChevronDown, ChevronRight, Search, Bell, Settings, LayoutDashboard,
  RefreshCw, Wifi, WifiOff, ShieldAlert, Layers, CircuitBoard,
  BarChart3, Network, Lock, Unlock, EyeIcon, Gauge,
  RadioTower, BrainCircuit, Loader2
} from 'lucide-react'
import { colors, pillars, hubIcons, type HubState, type SystemMode, type PillarDef } from './tokens'
import { useNavigate } from 'react-router-dom'
import {
  fetchHubs, fetchCitadelOverview, fetchSecurityPosture,
  fetchNeuralBus, setSystemMode as apiSetSystemMode,
  fetchHubDetail,
  type HubsResponse, type CitadelOverview, type SecurityPosture,
  type NeuralBusState,
} from './apiClient'

// ─────────────────────────────────────────────────────────────────────────────
// Icon Resolver
// ─────────────────────────────────────────────────────────────────────────────

const iconMap: Record<string, React.FC<any>> = {
  Brain, Eye, ['Infinity']: InfinityIcon, CircleDot, Lightbulb, Zap, Snowflake,
  GitBranch, Cpu, Clock, Shield, Crown, Palette, Sparkles, Heart,
  MessageSquare, Box, Volume2, Landmark, TrendingUp, Package, Store,
  Grid3X3, FlaskConical, Wrench, Flame, BookOpen, Archive, Hexagon,
  Bug, Building2, Feather, Sun, RadioTower, BrainCircuit,
}

function HubIcon({ hubId, size = 20, color }: { hubId: string; size?: number; color?: string }) {
  const iconName = hubIcons[hubId] || 'Hexagon'
  const IconComp = iconMap[iconName] || Hexagon
  return <IconComp size={size} color={color} />
}

// ─────────────────────────────────────────────────────────────────────────────
// Mock Data Generator (fallback when API is unreachable)
// ─────────────────────────────────────────────────────────────────────────────

function generateMockHubs(): HubState[] {
  const allHubs: HubState[] = []
  const modes: SystemMode[] = ['CLOUD_ONLY', 'HYBRID', 'TRUE_NAS']
  const statuses: HubState['status'][] = ['online', 'online', 'online', 'online', 'degraded', 'offline', 'booting']

  for (const pillar of pillars) {
    for (const hubId of pillar.hubs) {
      const status = statuses[Math.floor(Math.random() * statuses.length)]
      allHubs.push({
        id: hubId,
        name: hubId.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' '),
        pillar: pillar.id,
        tier: (Math.floor(Math.random() * 5) + 1) as HubState['tier'],
        status,
        systemMode: modes[Math.floor(Math.random() * modes.length)],
        services: Math.floor(Math.random() * 24) + 1,
        activeAgents: Math.floor(Math.random() * 12),
        circuitBreaker: status === 'online' ? 'closed' : status === 'degraded' ? 'half_open' : 'open',
        healthScore: status === 'online' ? 85 + Math.floor(Math.random() * 16) :
                     status === 'degraded' ? 50 + Math.floor(Math.random() * 35) :
                     status === 'booting' ? 20 + Math.floor(Math.random() * 30) :
                     Math.floor(Math.random() * 25),
        lastHeartbeat: new Date(Date.now() - Math.random() * 300000).toISOString(),
        alerts: status === 'degraded' ? Math.floor(Math.random() * 5) + 1 :
                status === 'offline' ? Math.floor(Math.random() * 10) + 1 : 0,
      })
    }
  }
  return allHubs
}

// ─────────────────────────────────────────────────────────────────────────────
// Live Data Hook — fetches from api_ecosystem.py, falls back to mock
// ─────────────────────────────────────────────────────────────────────────────

interface EcosystemLiveData {
  hubStates: HubState[]
  systemMode: SystemMode
  citadel: CitadelOverview | null
  security: SecurityPosture | null
  neuralBus: NeuralBusState | null
  loading: boolean
  lastRefresh: Date | null
  apiConnected: boolean
  refresh: () => void
}

function useEcosystemData(refreshIntervalMs = 30000): EcosystemLiveData {
  const [hubStates, setHubStates] = useState<HubState[]>(() => generateMockHubs())
  const [systemMode, setSystemModeState] = useState<SystemMode>('CLOUD_ONLY')
  const [citadel, setCitadel] = useState<CitadelOverview | null>(null)
  const [security, setSecurity] = useState<SecurityPosture | null>(null)
  const [neuralBus, setNeuralBus] = useState<NeuralBusState | null>(null)
  const [loading, setLoading] = useState(true)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)
  const [apiConnected, setApiConnected] = useState(false)
  const mountedRef = useRef(true)

  const loadAll = useCallback(async () => {
    setLoading(true)
    try {
      const [hubsRes, citadelRes, securityRes, neuralBusRes] = await Promise.all([
        fetchHubs(),
        fetchCitadelOverview(),
        fetchSecurityPosture(),
        fetchNeuralBus(),
      ])

      if (!mountedRef.current) return

      if (hubsRes) {
        // Live API data available
        setHubStates(hubsRes.hubs)
        setSystemModeState(hubsRes.systemMode)
        setApiConnected(true)
      } else {
        // API unreachable — keep existing data or use mock on first load
        if (!lastRefresh) {
          setHubStates(generateMockHubs())
        }
        setApiConnected(false)
      }

      if (citadelRes) setCitadel(citadelRes)
      if (securityRes) setSecurity(securityRes)
      if (neuralBusRes) setNeuralBus(neuralBusRes)

      setLastRefresh(new Date())
    } catch (err) {
      console.warn('[EcosystemData] fetch error:', err)
      if (!lastRefresh && mountedRef.current) {
        setHubStates(generateMockHubs())
      }
      setApiConnected(false)
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [lastRefresh])

  // Initial load + periodic refresh
  useEffect(() => {
    mountedRef.current = true
    loadAll()
    const interval = setInterval(loadAll, refreshIntervalMs)
    return () => {
      mountedRef.current = false
      clearInterval(interval)
    }
  }, [refreshIntervalMs]) // eslint-disable-line react-hooks/exhaustive-deps

  // Simulate real-time health micro-updates between full refreshes
  useEffect(() => {
    const micro = setInterval(() => {
      setHubStates(prev => prev.map(hub => ({
        ...hub,
        healthScore: Math.max(0, Math.min(100, hub.healthScore + (Math.random() > 0.7 ? Math.floor(Math.random() * 7) - 3 : 0))),
        lastHeartbeat: new Date().toISOString(),
      })))
    }, 5000)
    return () => clearInterval(micro)
  }, [])

  return {
    hubStates,
    systemMode,
    citadel,
    security,
    neuralBus,
    loading,
    lastRefresh,
    apiConnected,
    refresh: loadAll,
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// System Mode Indicator
// ─────────────────────────────────────────────────────────────────────────────

function SystemModeBadge({ mode, size = 'sm' }: { mode: SystemMode; size?: 'sm' | 'md' }) {
  const modeConfig = {
    TRUE_NAS: { icon: HardDrive, color: colors.systemMode.TRUE_NAS, label: 'TrueNAS' },
    HYBRID: { icon: ArrowLeftRight, color: colors.systemMode.HYBRID, label: 'Hybrid' },
    CLOUD_ONLY: { icon: Cloud, color: colors.systemMode.CLOUD_ONLY, label: 'Cloud' },
  }
  const config = modeConfig[mode]
  const Icon = config.icon
  const sz = size === 'sm' ? 12 : 16
  const textSz = size === 'sm' ? 'text-[10px]' : 'text-xs'

  return (
    <div className={`flex items-center gap-1 px-2 py-0.5 rounded-full`}
         style={{ backgroundColor: config.color + '20', border: `1px solid ${config.color}40` }}>
      <Icon size={sz} color={config.color} />
      <span className={`${textSz} font-medium`} style={{ color: config.color }}>{config.label}</span>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Status Indicator
// ─────────────────────────────────────────────────────────────────────────────

function StatusDot({ status, pulse = false }: { status: HubState['status']; pulse?: boolean }) {
  const colorMap: Record<string, string> = {
    online: colors.status.online,
    degraded: colors.status.degraded,
    offline: colors.status.offline,
    maintenance: colors.status.maintenance,
    booting: colors.status.booting,
    unknown: colors.status.unknown,
  }
  const c = colorMap[status] || colors.status.unknown

  return (
    <div className="relative flex items-center justify-center">
      <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: c }} />
      {(pulse && (status === 'online' || status === 'booting')) && (
        <div className="absolute w-2.5 h-2.5 rounded-full animate-ping" style={{ backgroundColor: c, opacity: 0.4 }} />
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Circuit Breaker Badge
// ─────────────────────────────────────────────────────────────────────────────

function CircuitBreakerBadge({ state }: { state: HubState['circuitBreaker'] }) {
  const config = {
    closed: { color: colors.circuitBreaker.closed, label: 'CLOSED', icon: CheckCircle2 },
    open: { color: colors.circuitBreaker.open, label: 'OPEN', icon: XCircle },
    half_open: { color: colors.circuitBreaker.half_open, label: 'HALF-OPEN', icon: AlertTriangle },
  }
  const c = config[state]
  const Icon = c.icon

  return (
    <div className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono font-bold tracking-wider"
         style={{ backgroundColor: c.color + '20', color: c.color, border: `1px solid ${c.color}40` }}>
      <Icon size={10} />
      {c.label}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Health Score Ring
// ─────────────────────────────────────────────────────────────────────────────

function HealthRing({ score, size = 40 }: { score: number; size?: number }) {
  const radius = (size - 6) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (score / 100) * circumference
  const color = score >= 85 ? colors.status.online :
                score >= 50 ? colors.status.degraded :
                colors.status.offline

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#1E293B" strokeWidth={3} />
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={color} strokeWidth={3}
                strokeDasharray={circumference} strokeDashoffset={offset}
                strokeLinecap="round" className="transition-all duration-700" />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-[10px] font-mono font-bold" style={{ color }}>{score}</span>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// API Connection Indicator
// ─────────────────────────────────────────────────────────────────────────────

function ApiStatusBadge({ connected, lastRefresh }: { connected: boolean; lastRefresh: Date | null }) {
  return (
    <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full"
         style={{
           backgroundColor: connected ? '#10B98115' : '#F59E0B15',
           border: `1px solid ${connected ? '#10B98130' : '#F59E0B30'}`,
         }}>
      {connected ? (
        <Wifi size={10} className="text-green-400" />
      ) : (
        <WifiOff size={10} className="text-amber-400" />
      )}
      <span className={`text-[10px] font-medium ${connected ? 'text-green-400' : 'text-amber-400'}`}>
        {connected ? 'Live' : 'Mock'}
      </span>
      {lastRefresh && (
        <span className="text-[9px] text-gray-600">
          {lastRefresh.toLocaleTimeString()}
        </span>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Hub Card
// ─────────────────────────────────────────────────────────────────────────────

function HubCard({ hub, onClick }: { hub: HubState; onClick: (hub: HubState) => void }) {
  const pillarColor = colors.hubs[hub.id as keyof typeof colors.hubs] || colors.brand.primary

  return (
    <div
      onClick={() => onClick(hub)}
      className="group relative flex flex-col gap-3 p-4 rounded-xl border cursor-pointer transition-all duration-200 hover:scale-[1.02] hover:shadow-lg"
      style={{
        backgroundColor: colors.brand.elevated,
        borderColor: hub.status === 'degraded' ? colors.status.degraded + '60' :
                     hub.status === 'offline' ? colors.status.offline + '60' :
                     colors.brand.border,
        boxShadow: hub.status === 'online' ? `0 0 0 1px ${pillarColor}10` : undefined,
      }}
    >
      {/* Header row */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg flex items-center justify-center transition-colors"
               style={{ backgroundColor: pillarColor + '20' }}>
            <HubIcon hubId={hub.id} size={18} color={pillarColor} />
          </div>
          <div>
            <div className="text-sm font-semibold text-white leading-tight">{hub.name}</div>
            <div className="flex items-center gap-1.5 mt-0.5">
              <StatusDot status={hub.status} pulse={hub.status === 'online'} />
              <span className="text-[10px] text-gray-500 capitalize">{hub.status}</span>
            </div>
          </div>
        </div>
        <HealthRing score={hub.healthScore} size={38} />
      </div>

      {/* Metrics row */}
      <div className="grid grid-cols-3 gap-2">
        <div className="flex flex-col items-center py-1.5 px-1 rounded-lg bg-gray-800/50">
          <span className="text-[10px] text-gray-500">Services</span>
          <span className="text-xs font-mono font-bold text-white">{hub.services}</span>
        </div>
        <div className="flex flex-col items-center py-1.5 px-1 rounded-lg bg-gray-800/50">
          <span className="text-[10px] text-gray-500">Agents</span>
          <span className="text-xs font-mono font-bold text-white">{hub.activeAgents}</span>
        </div>
        <div className="flex flex-col items-center py-1.5 px-1 rounded-lg bg-gray-800/50">
          <span className="text-[10px] text-gray-500">Alerts</span>
          <span className={`text-xs font-mono font-bold ${hub.alerts > 0 ? 'text-red-400' : 'text-green-400'}`}>
            {hub.alerts}
          </span>
        </div>
      </div>

      {/* Footer row */}
      <div className="flex items-center justify-between pt-1 border-t border-gray-800">
        <SystemModeBadge mode={hub.systemMode} />
        <CircuitBreakerBadge state={hub.circuitBreaker} />
      </div>

      {/* Tier indicator */}
      <div className="absolute top-2 right-2 w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-bold"
           style={{ backgroundColor: colors.tier[hub.tier as keyof typeof colors.tier] + '30',
                    color: colors.tier[hub.tier as keyof typeof colors.tier] }}>
        T{hub.tier}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Hub Detail Panel (with live API detail fetch)
// ─────────────────────────────────────────────────────────────────────────────

function HubDetailPanel({ hub, onClose }: { hub: HubState; onClose: () => void }) {
  const pillarColor = colors.hubs[hub.id as keyof typeof colors.hubs] || colors.brand.primary
  const pillarDef = pillars.find(p => p.id === hub.pillar)
  const [liveDetail, setLiveDetail] = useState<HubState | null>(null)
  const [detailLoading, setDetailLoading] = useState(true)

  // Fetch detailed hub info from API when panel opens
  useEffect(() => {
    let mounted = true
    setDetailLoading(true)
    fetchHubDetail(hub.id).then(detail => {
      if (mounted && detail) {
        setLiveDetail(detail)
      }
    }).finally(() => {
      if (mounted) setDetailLoading(false)
    })
    return () => { mounted = false }
  }, [hub.id])

  const displayHub = liveDetail || hub

  return (
    <div className="fixed inset-y-0 right-0 w-[420px] bg-gray-950 border-l border-gray-800 shadow-2xl z-50 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="p-6 border-b border-gray-800" style={{ background: `linear-gradient(135deg, ${pillarColor}15, transparent)` }}>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl flex items-center justify-center"
                 style={{ backgroundColor: pillarColor + '25' }}>
              <HubIcon hubId={hub.id} size={24} color={pillarColor} />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white">{displayHub.name}</h2>
              <span className="text-xs text-gray-500">{pillarDef?.name} Pillar · Tier {displayHub.tier}</span>
            </div>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-gray-800 text-gray-500 hover:text-white transition-colors">
            ✕
          </button>
        </div>

        <div className="flex items-center gap-3">
          <StatusDot status={displayHub.status} pulse />
          <span className="text-sm capitalize" style={{ color: colors.status[displayHub.status] }}>{displayHub.status}</span>
          <SystemModeBadge mode={displayHub.systemMode} size="md" />
          <CircuitBreakerBadge state={displayHub.circuitBreaker} />
        </div>
      </div>

      {/* Health Score */}
      <div className="p-6 border-b border-gray-800">
        <div className="flex items-center gap-4">
          <HealthRing score={displayHub.healthScore} size={72} />
          <div>
            <div className="text-sm text-gray-400 mb-1">System Health</div>
            <div className="text-2xl font-bold" style={{ color: displayHub.healthScore >= 85 ? colors.status.online : displayHub.healthScore >= 50 ? colors.status.degraded : colors.status.offline }}>
              {displayHub.healthScore}%
            </div>
            <div className="text-xs text-gray-600 mt-1">
              Last heartbeat: {new Date(displayHub.lastHeartbeat).toLocaleTimeString()}
            </div>
          </div>
        </div>
      </div>

      {/* Services Grid */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {detailLoading && (
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <Loader2 size={12} className="animate-spin" />
            <span>Loading detail from API...</span>
          </div>
        )}

        <div>
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Active Services</h3>
          <div className="grid grid-cols-2 gap-2">
            {Array.from({ length: Math.min(displayHub.services, 8) }, (_, i) => (
              <div key={i} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-900 border border-gray-800">
                <div className="w-1.5 h-1.5 rounded-full bg-green-400" />
                <span className="text-xs text-gray-300 font-mono">
                  SID-{String(i + 1).padStart(3, '0')}
                </span>
              </div>
            ))}
            {displayHub.services > 8 && (
              <div className="flex items-center justify-center px-3 py-2 rounded-lg bg-gray-900/50 border border-dashed border-gray-800">
                <span className="text-xs text-gray-600">+{displayHub.services - 8} more</span>
              </div>
            )}
          </div>
        </div>

        {/* Dependency Graph Visualization */}
        <div>
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Dependency Graph</h3>
          <div className="p-4 rounded-lg bg-gray-900 border border-gray-800">
            <div className="flex items-center justify-center gap-2">
              <div className="px-3 py-1.5 rounded-lg text-xs font-mono"
                   style={{ backgroundColor: pillarColor + '20', color: pillarColor }}>
                {displayHub.id}
              </div>
              <div className="flex-1 border-t border-dashed border-gray-700" />
              <div className="px-2 py-1 rounded text-[10px] text-gray-500 bg-gray-800">Neural Bus</div>
              <div className="flex-1 border-t border-dashed border-gray-700" />
              <div className="px-3 py-1.5 rounded-lg text-xs font-mono bg-gray-800 text-gray-400">
                {displayHub.pillar}-core
              </div>
            </div>
          </div>
        </div>

        {/* Audit Trail Preview */}
        <div>
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Recent Audit Events</h3>
          <div className="space-y-1.5">
            {['health_check', 'config_sync', 'secret_rotation', 'deployment'].map((event, i) => (
              <div key={i} className="flex items-center gap-2 px-3 py-1.5 rounded bg-gray-900/50">
                <div className="w-1 h-1 rounded-full bg-blue-400" />
                <span className="text-[10px] font-mono text-gray-500 flex-1">{event}</span>
                <span className="text-[10px] font-mono text-gray-700">
                  {new Date(Date.now() - (i + 1) * 60000).toLocaleTimeString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Sidebar
// ─────────────────────────────────────────────────────────────────────────────

function Sidebar({
  activePillar,
  onSelectPillar,
  systemMode,
  onModeChange,
  hubStates,
  apiConnected,
}: {
  activePillar: string | null
  onSelectPillar: (id: string | null) => void
  systemMode: SystemMode
  onModeChange: (mode: SystemMode) => void
  hubStates: HubState[]
  apiConnected: boolean
}) {
  const [collapsed, setCollapsed] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const navigate = useNavigate()

  const totalAlerts = hubStates.reduce((sum, h) => sum + h.alerts, 0)
  const onlineCount = hubStates.filter(h => h.status === 'online').length
  const degradedCount = hubStates.filter(h => h.status === 'degraded').length

  return (
    <div className={`flex flex-col border-r border-gray-800 bg-gray-950 transition-all duration-200 ${collapsed ? 'w-16' : 'w-72'}`}>
      {/* Brand */}
      <div className="flex items-center gap-2 px-4 py-4 border-b border-gray-800">
        <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center flex-shrink-0">
          <Brain size={18} className="text-white" />
        </div>
        {!collapsed && (
          <div className="flex-1 min-w-0">
            <div className="text-sm font-bold text-white tracking-tight">Trancendos</div>
            <div className="text-[10px] text-gray-600">Ecosystem Command</div>
          </div>
        )}
        <button onClick={() => setCollapsed(!collapsed)}
                className="p-1 rounded hover:bg-gray-800 text-gray-600 hover:text-white transition-colors">
          <ChevronRight size={14} className={`transition-transform ${collapsed ? '' : 'rotate-180'}`} />
        </button>
      </div>

      {!collapsed && (
        <>
          {/* Nav to Chat */}
          <div className="px-3 py-2 border-b border-gray-800">
            <button onClick={() => navigate('/')}
                    className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs text-gray-500 hover:text-white hover:bg-gray-900 transition-colors">
              <MessageSquare size={14} />
              <span>Back to Chat</span>
            </button>
          </div>

          {/* System Mode Switcher */}
          <div className="px-3 py-3 border-b border-gray-800">
            <div className="text-[10px] text-gray-600 uppercase tracking-wider mb-2 px-1">System Mode</div>
            <div className="flex gap-1">
              {(['TRUE_NAS', 'HYBRID', 'CLOUD_ONLY'] as SystemMode[]).map(mode => (
                <button key={mode} onClick={() => onModeChange(mode)}
                        className={`flex-1 py-1.5 rounded-lg text-[10px] font-semibold transition-all ${
                          systemMode === mode ? 'text-white' : 'text-gray-600 hover:text-gray-400'
                        }`}
                        style={systemMode === mode ? {
                          backgroundColor: colors.systemMode[mode] + '25',
                          border: `1px solid ${colors.systemMode[mode]}50`,
                          color: colors.systemMode[mode],
                        } : { border: '1px solid transparent' }}>
                  {mode === 'TRUE_NAS' ? 'NAS' : mode === 'HYBRID' ? 'Mix' : 'Cloud'}
                </button>
              ))}
            </div>
            {/* API status indicator */}
            <div className="mt-2 flex items-center gap-1 px-1">
              {apiConnected ? (
                <Wifi size={10} className="text-green-500" />
              ) : (
                <WifiOff size={10} className="text-amber-500" />
              )}
              <span className={`text-[9px] ${apiConnected ? 'text-green-500' : 'text-amber-500'}`}>
                {apiConnected ? 'Connected to API' : 'Using mock data'}
              </span>
            </div>
          </div>

          {/* Search */}
          <div className="px-3 py-2 border-b border-gray-800">
            <div className="relative">
              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-600" />
              <input value={searchQuery} onChange={e => setSearchQuery(e.target.value)}
                     placeholder="Search hubs..."
                     className="w-full bg-gray-900 border border-gray-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-gray-700" />
            </div>
          </div>

          {/* Overview */}
          <div className="px-3 py-2">
            <button onClick={() => onSelectPillar(null)}
                    className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs transition-colors ${
                      activePillar === null ? 'bg-gray-800 text-white' : 'text-gray-400 hover:text-white hover:bg-gray-900'
                    }`}>
              <LayoutDashboard size={14} />
              <span className="flex-1 text-left">Overview</span>
              <div className="flex items-center gap-1.5">
                <span className="text-green-400">{onlineCount}</span>
                {degradedCount > 0 && <span className="text-amber-400">{degradedCount}</span>}
                {totalAlerts > 0 && (
                  <span className="bg-red-600 text-white text-[9px] font-bold px-1.5 py-0.5 rounded-full">{totalAlerts}</span>
                )}
              </div>
            </button>
          </div>

          {/* Pillars */}
          <div className="flex-1 overflow-y-auto px-3 pb-3 space-y-0.5">
            <div className="text-[10px] text-gray-600 uppercase tracking-wider px-2 py-1">Pillars</div>
            {pillars.map(pillar => {
              const pillarHubs = hubStates.filter(h => h.pillar === pillar.id)
              const pillarAlerts = pillarHubs.reduce((s, h) => s + h.alerts, 0)
              const isFiltered = searchQuery && !pillar.name.toLowerCase().includes(searchQuery.toLowerCase()) &&
                                !pillar.hubs.some(h => h.includes(searchQuery.toLowerCase()))

              if (isFiltered) return null

              return (
                <button key={pillar.id} onClick={() => onSelectPillar(pillar.id)}
                        className={`w-full flex items-center gap-2.5 px-2 py-2 rounded-lg text-xs transition-colors ${
                          activePillar === pillar.id ? 'bg-gray-800 text-white' : 'text-gray-400 hover:text-white hover:bg-gray-900'
                        }`}>
                  <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: pillar.color }} />
                  <span className="flex-1 text-left truncate">{pillar.name}</span>
                  <span className="text-[10px] text-gray-600">{pillar.hubs.length}</span>
                  {pillarAlerts > 0 && (
                    <span className="bg-red-900 text-red-300 text-[9px] font-bold px-1 py-0.5 rounded-full">{pillarAlerts}</span>
                  )}
                </button>
              )
            })}
          </div>
        </>
      )}

      {collapsed && (
        <div className="flex-1 flex flex-col items-center py-3 gap-2">
          <button onClick={() => onSelectPillar(null)}
                  className={`w-10 h-10 rounded-lg flex items-center justify-center transition-colors ${
                    activePillar === null ? 'bg-gray-800 text-white' : 'text-gray-600 hover:text-white hover:bg-gray-900'
                  }`}>
            <LayoutDashboard size={16} />
          </button>
          {pillars.map(pillar => (
            <button key={pillar.id} onClick={() => onSelectPillar(pillar.id)}
                    className={`w-10 h-10 rounded-lg flex items-center justify-center transition-colors ${
                      activePillar === pillar.id ? 'bg-gray-800' : 'hover:bg-gray-900'
                    }`}
                    title={pillar.name}>
              <div className="w-3 h-3 rounded-full" style={{ backgroundColor: pillar.color }} />
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Top Bar
// ─────────────────────────────────────────────────────────────────────────────

function TopBar({
  hubStates,
  systemMode,
  apiConnected,
  lastRefresh,
  onRefresh,
  refreshing,
}: {
  hubStates: HubState[]
  systemMode: SystemMode
  apiConnected: boolean
  lastRefresh: Date | null
  onRefresh: () => void
  refreshing: boolean
}) {
  const totalHubs = hubStates.length
  const onlineHubs = hubStates.filter(h => h.status === 'online').length
  const totalServices = hubStates.reduce((s, h) => s + h.services, 0)
  const totalAlerts = hubStates.reduce((s, h) => s + h.alerts, 0)
  const avgHealth = Math.round(hubStates.reduce((s, h) => s + h.healthScore, 0) / totalHubs)
  const modeColor = colors.systemMode[systemMode]

  return (
    <div className="flex items-center justify-between px-6 h-14 border-b border-gray-800 bg-gray-950/80 backdrop-blur-sm">
      <div className="flex items-center gap-6">
        <h1 className="text-sm font-semibold text-white">Ecosystem Dashboard</h1>
        <SystemModeBadge mode={systemMode} size="md" />
        <ApiStatusBadge connected={apiConnected} lastRefresh={lastRefresh} />
      </div>

      <div className="flex items-center gap-6">
        {/* Stats */}
        <div className="flex items-center gap-5 text-xs">
          <div className="flex items-center gap-1.5">
            <Activity size={14} className="text-green-400" />
            <span className="text-gray-400">{onlineHubs}/{totalHubs}</span>
            <span className="text-gray-600">hubs</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Server size={14} className="text-blue-400" />
            <span className="text-gray-400">{totalServices}</span>
            <span className="text-gray-600">services</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Gauge size={14} style={{ color: modeColor }} />
            <span className="text-gray-400">{avgHealth}%</span>
            <span className="text-gray-600">health</span>
          </div>
          {totalAlerts > 0 && (
            <div className="flex items-center gap-1.5">
              <AlertTriangle size={14} className="text-amber-400" />
              <span className="text-amber-400 font-semibold">{totalAlerts}</span>
              <span className="text-gray-600">alerts</span>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          <button onClick={onRefresh}
                  className={`p-2 rounded-lg hover:bg-gray-800 text-gray-500 hover:text-white transition-colors ${refreshing ? 'animate-spin' : ''}`}>
            <RefreshCw size={16} />
          </button>
          <button className="p-2 rounded-lg hover:bg-gray-800 text-gray-500 hover:text-white transition-colors relative">
            <Bell size={16} />
            {totalAlerts > 0 && (
              <div className="absolute -top-0.5 -right-0.5 w-3.5 h-3.5 bg-red-500 rounded-full flex items-center justify-center">
                <span className="text-[8px] font-bold text-white">{totalAlerts > 9 ? '9+' : totalAlerts}</span>
              </div>
            )}
          </button>
          <button className="p-2 rounded-lg hover:bg-gray-800 text-gray-500 hover:text-white transition-colors">
            <Settings size={16} />
          </button>
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Neural Bus Visualization (wired to live API data)
// ─────────────────────────────────────────────────────────────────────────────

function NeuralBusViz({
  hubStates,
  neuralBus,
}: {
  hubStates: HubState[]
  neuralBus: NeuralBusState | null
}) {
  const onlineHubs = hubStates.filter(h => h.status === 'online')
  const visibleHubs = onlineHubs.slice(0, 12)

  // Use API-provided neural bus data if available
  const activeNodes = neuralBus?.activeNodes ?? onlineHubs.length
  const busStatus = neuralBus?.status ?? 'active'
  const protocol = neuralBus?.protocol ?? 'Neural-Bus/v1'

  return (
    <div className="p-4 rounded-xl border border-gray-800 bg-gray-900/50">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Radio size={14} className="text-violet-400" />
          <span className="text-xs font-semibold text-gray-300">Neural Bus</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[9px] text-gray-600 font-mono">{protocol}</span>
          <span className="text-[10px] text-gray-600">{activeNodes} nodes active</span>
        </div>
      </div>

      <div className="relative h-24 flex items-center justify-center">
        {/* Central node */}
        <div className="absolute w-8 h-8 rounded-full bg-violet-600/30 border border-violet-500/50 flex items-center justify-center">
          <Brain size={14} className="text-violet-300" />
        </div>

        {/* Orbiting nodes — prefer API topology data, fall back to hub states */}
        {(neuralBus?.nodes ?? visibleHubs).slice(0, 12).map((node: { id?: string; name?: string; color?: string; health?: number } | HubState, i: number) => {
          const totalNodes = Math.min((neuralBus?.nodes ?? visibleHubs).length, 12)
          const angle = (i / totalNodes) * 2 * Math.PI - Math.PI / 2
          const rx = 80, ry = 35
          const x = Math.cos(angle) * rx
          const y = Math.sin(angle) * ry
          const hubId = 'id' in node ? node.id! : ''
          const hubColor = 'color' in node && node.color
            ? node.color
            : (colors.hubs[hubId as keyof typeof colors.hubs] || colors.brand.primary)

          return (
            <div key={hubId}
                 className="absolute w-5 h-5 rounded-full flex items-center justify-center transition-all duration-500"
                 style={{
                   transform: `translate(${x}px, ${y}px)`,
                   backgroundColor: hubColor + '30',
                   border: `1.5px solid ${hubColor}60`,
                 }}
                 title={hubId}>
              <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: hubColor }} />
            </div>
          )
        })}

        {/* Connection lines */}
        <svg className="absolute inset-0 w-full h-full" style={{ opacity: 0.15 }}>
          {visibleHubs.map((_, i) => {
            const totalNodes = Math.min((neuralBus?.nodes ?? visibleHubs).length, 12)
            const angle = (i / totalNodes) * 2 * Math.PI - Math.PI / 2
            const x = 50 + Math.cos(angle) * 38
            const y = 50 + Math.sin(angle) * 17
            return <line key={i} x1="50%" y1="50%" x2={`${x}%`} y2={`${y}%`} stroke="#8B5CF6" strokeWidth="0.5" />
          })}
        </svg>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Citadel Dashboard Widget (wired to live API data)
// ─────────────────────────────────────────────────────────────────────────────

function CitadelWidget({
  hubStates,
  citadel,
}: {
  hubStates: HubState[]
  citadel: CitadelOverview | null
}) {
  // Use API data when available, otherwise compute from hub states
  const totalServices = citadel?.total_services ?? hubStates.reduce((s, h) => s + h.services, 0)
  const totalAgents = citadel?.total_agents ?? hubStates.reduce((s, h) => s + h.activeAgents, 0)
  const openCircuits = citadel?.open_circuits ?? hubStates.filter(h => h.circuitBreaker === 'open').length
  const halfOpenCircuits = citadel?.half_open_circuits ?? hubStates.filter(h => h.circuitBreaker === 'half_open').length
  const avgHealth = citadel?.avg_health ?? Math.round(hubStates.reduce((s, h) => s + h.healthScore, 0) / hubStates.length)

  return (
    <div className="p-4 rounded-xl border border-gray-800 bg-gray-900/50">
      <div className="flex items-center gap-2 mb-3">
        <Shield size={14} className="text-red-400" />
        <span className="text-xs font-semibold text-gray-300">The Citadel — Master OS</span>
      </div>

      <div className="grid grid-cols-4 gap-2">
        <div className="flex flex-col items-center py-2 px-1 rounded-lg bg-gray-800/50">
          <Server size={14} className="text-blue-400 mb-1" />
          <span className="text-sm font-bold text-white">{totalServices}</span>
          <span className="text-[9px] text-gray-600">Services</span>
        </div>
        <div className="flex flex-col items-center py-2 px-1 rounded-lg bg-gray-800/50">
          <Cpu size={14} className="text-emerald-400 mb-1" />
          <span className="text-sm font-bold text-white">{totalAgents}</span>
          <span className="text-[9px] text-gray-600">Agents</span>
        </div>
        <div className="flex flex-col items-center py-2 px-1 rounded-lg bg-gray-800/50">
          <ShieldAlert size={14} className={openCircuits > 0 ? 'text-red-400 mb-1' : 'text-green-400 mb-1'} />
          <span className={`text-sm font-bold ${openCircuits > 0 ? 'text-red-400' : 'text-green-400'}`}>{openCircuits}</span>
          <span className="text-[9px] text-gray-600">Tripped</span>
        </div>
        <div className="flex flex-col items-center py-2 px-1 rounded-lg bg-gray-800/50">
          <Gauge size={14} style={{ color: avgHealth >= 85 ? '#10B981' : avgHealth >= 50 ? '#F59E0B' : '#EF4444' }} className="mb-1" />
          <span className="text-sm font-bold text-white">{avgHealth}%</span>
          <span className="text-[9px] text-gray-600">Health</span>
        </div>
      </div>

      {halfOpenCircuits > 0 && (
        <div className="mt-2 flex items-center gap-1.5 px-2 py-1 rounded-lg bg-amber-900/20 border border-amber-800/30">
          <AlertTriangle size={12} className="text-amber-400" />
          <span className="text-[10px] text-amber-400">{halfOpenCircuits} circuit(s) in half-open state</span>
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Security Overview Widget (wired to live API data)
// ─────────────────────────────────────────────────────────────────────────────

function SecurityWidget({ security }: { security: SecurityPosture | null }) {
  const [scanStatus, setScanStatus] = useState<'idle' | 'scanning' | 'complete'>('idle')

  // Use API data when available, otherwise show placeholder values
  const violations = security?.violations ?? 0
  const suppressed = security?.suppressed ?? 2
  const auditChainValid = security?.audit_chain_valid ?? true
  const secretLeaks = security?.secret_leaks ?? 0
  const vaultStatus = security?.vault_status ?? 'Sealed'

  return (
    <div className="p-4 rounded-xl border border-gray-800 bg-gray-900/50">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Lock size={14} className="text-emerald-400" />
          <span className="text-xs font-semibold text-gray-300">Security Posture</span>
        </div>
        <button onClick={() => { setScanStatus('scanning'); setTimeout(() => setScanStatus('complete'), 2000) }}
                className="text-[10px] px-2 py-1 rounded bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700 transition-colors">
          {scanStatus === 'scanning' ? 'Scanning...' : scanStatus === 'complete' ? '✓ Done' : 'Run Scan'}
        </button>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-gray-500">Violations</span>
          <span className={`text-xs font-mono ${violations === 0 ? 'text-green-400' : 'text-red-400'}`}>{violations}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-gray-500">Suppressed (FP)</span>
          <span className="text-xs font-mono text-gray-500">{suppressed}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-gray-500">Audit Chain</span>
          <span className={`text-xs font-mono ${auditChainValid ? 'text-green-400' : 'text-red-400'}`}>
            {auditChainValid ? '✓ Valid' : '✗ Invalid'}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-gray-500">Secret Leaks</span>
          <span className={`text-xs font-mono ${secretLeaks === 0 ? 'text-green-400' : 'text-red-400'}`}>{secretLeaks}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-gray-500">Vault Status</span>
          <span className={`text-xs font-mono ${vaultStatus === 'Sealed' ? 'text-green-400' : 'text-amber-400'}`}>{vaultStatus}</span>
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Main Dashboard Component
// ─────────────────────────────────────────────────────────────────────────────

export default function TrancendosDashboard() {
  const {
    hubStates,
    systemMode,
    citadel,
    security,
    neuralBus,
    loading,
    lastRefresh,
    apiConnected,
    refresh,
  } = useEcosystemData()

  const [activePillar, setActivePillar] = useState<string | null>(null)
  const [selectedHub, setSelectedHub] = useState<HubState | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  // Filter hubs by active pillar
  const filteredHubs = useMemo(() => {
    if (!activePillar) return hubStates
    return hubStates.filter(h => h.pillar === activePillar)
  }, [hubStates, activePillar])

  // Mode change handler — calls API; the hook's periodic refresh will pick up the change
  const handleModeChange = useCallback(async (mode: SystemMode) => {
    // Call the API to change mode on the backend
    const result = await apiSetSystemMode(mode)
    if (result) {
      console.log(`[Dashboard] System mode changed to ${mode} via API`)
      // Trigger an immediate refresh to update all data from the backend
      refresh()
    } else {
      console.warn(`[Dashboard] API mode change failed, local state unchanged until next refresh`)
    }
  }, [refresh])

  // Group filtered hubs by pillar for display
  const groupedHubs = useMemo(() => {
    if (activePillar) {
      return [{ pillar: pillars.find(p => p.id === activePillar)!, hubs: filteredHubs }]
    }
    return pillars.map(pillar => ({
      pillar,
      hubs: filteredHubs.filter(h => h.pillar === pillar.id),
    })).filter(g => g.hubs.length > 0)
  }, [filteredHubs, activePillar])

  const handleRefresh = useCallback(() => {
    setRefreshing(true)
    refresh()
    setTimeout(() => setRefreshing(false), 1500)
  }, [refresh])

  if (loading && hubStates.length === 0) {
    return (
      <div className="flex h-screen bg-gray-950 text-white items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <Loader2 size={32} className="animate-spin text-blue-500" />
          <span className="text-sm text-gray-400">Loading Ecosystem Data...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-screen bg-gray-950 text-white overflow-hidden">
      {/* Sidebar */}
      <Sidebar
        activePillar={activePillar}
        onSelectPillar={setActivePillar}
        systemMode={systemMode}
        onModeChange={handleModeChange}
        hubStates={hubStates}
        apiConnected={apiConnected}
      />

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <TopBar
          hubStates={hubStates}
          systemMode={systemMode}
          apiConnected={apiConnected}
          lastRefresh={lastRefresh}
          onRefresh={handleRefresh}
          refreshing={refreshing}
        />

        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* System Overview Row */}
          <div className="grid grid-cols-3 gap-4">
            <NeuralBusViz hubStates={hubStates} neuralBus={neuralBus} />
            <CitadelWidget hubStates={hubStates} citadel={citadel} />
            <SecurityWidget security={security} />
          </div>

          {/* Hub Grid by Pillar */}
          {groupedHubs.map(({ pillar, hubs }) => (
            <div key={pillar.id}>
              <div className="flex items-center gap-2 mb-3">
                <div className="w-2 h-2 rounded-full" style={{ backgroundColor: pillar.color }} />
                <h2 className="text-sm font-semibold text-gray-300">{pillar.name} Pillar</h2>
                <span className="text-[10px] text-gray-600">{hubs.length} hub{hubs.length !== 1 ? 's' : ''}</span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                {hubs.map(hub => (
                  <HubCard key={hub.id} hub={hub} onClick={setSelectedHub} />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Hub Detail Slide-over */}
      {selectedHub && (
        <HubDetailPanel hub={selectedHub} onClose={() => setSelectedHub(null)} />
      )}
    </div>
  )
}
