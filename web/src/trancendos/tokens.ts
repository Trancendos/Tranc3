/**
 * Trancendos Ecosystem Design Tokens
 * 
 * Central source of truth for all visual constants across the platform.
 * Maps to Tailwind CSS custom properties and component-level tokens.
 * 
 * Taxonomy alignment:
 * - PID-hub colors mapped per pillar
 * - Tier indicators (1-5) with distinct visual language
 * - SYSTEM_MODE environment indicators (TRUE_NAS / HYBRID / CLOUD_ONLY)
 */

// ─── Color Palette ──────────────────────────────────────────────────────────

export const colors = {
  // Core brand
  brand: {
    primary: '#3B82F6',      // Blue-500 — The Sovereign / Nexus
    secondary: '#8B5CF6',    // Violet-500 — Neural Protocol
    accent: '#06B6D4',       // Cyan-500 — Quantum / Innovation
    surface: '#0F172A',      // Slate-900 — Deep background
    elevated: '#1E293B',     // Slate-800 — Card background
    border: '#334155',       // Slate-700 — Borders
  },

  // Pillar colors — each pillar has a distinct hue
  pillars: {
    architectural: '#3B82F6',  // Blue — Structure, Foundation
    creativity: '#F59E0B',     // Amber — Imagination, Art
    development: '#10B981',    // Emerald — Code, Building
    commercial: '#F97316',     // Orange — Commerce, Trade
    knowledge: '#8B5CF6',     // Violet — Wisdom, Learning
    security: '#EF4444',      // Red — Protection, Defense
    devops: '#06B6D4',        // Cyan — Operations, Flow
    wellbeing: '#EC4899',     // Pink — Health, Harmony
    foresight: '#A78BFA',     // Purple — Prediction, Vision
    governance: '#6366F1',    // Indigo — Rules, Order
  },

  // Hub-specific colors — derived from pillar but unique per hub
  hubs: {
    'the-nexus': '#3B82F6',
    'the-observatory': '#8B5CF6',
    'infinity': '#F59E0B',
    'the-void': '#6366F1',
    'the-lighthouse': '#FBBF24',
    'the-warp-tunnel': '#06B6D4',
    'the-ice-box': '#67E8F9',
    'devocity': '#10B981',
    'turings-hub': '#34D399',
    'chronosphere': '#A78BFA',
    'the-citadel': '#EF4444',
    'the-dutchy': '#F97316',
    'the-studio': '#F59E0B',
    'imaginarium': '#FBBF24',
    'tranquility': '#EC4899',
    'i-mind': '#8B5CF6',
    'taimra': '#C084FC',
    'vrar3d': '#F472B6',
    'resonate': '#FB923C',
    'royal-bank': '#F97316',
    'arcadian-exchange': '#FB923C',
    'the-artifactory': '#10B981',
    'api-marketplace': '#34D399',
    'the-digital-grid': '#06B6D4',
    'the-lab': '#10B981',
    'the-workshop': '#34D399',
    'the-chaos-party': '#EF4444',
    'the-library': '#8B5CF6',
    'the-basement': '#6366F1',
    'the-hive': '#F59E0B',
    'the-swarm': '#FBBF24',
    'the-town-hall': '#6366F1',
    'fablousa': '#EC4899',
    'luminous': '#A78BFA',
  },

  // System mode environment colors
  systemMode: {
    TRUE_NAS: '#10B981',    // Emerald — Local, secure, full power
    HYBRID: '#F59E0B',      // Amber — Mixed, adaptive
    CLOUD_ONLY: '#3B82F6',  // Blue — Remote, free-tier
  },

  // Tier colors — visual hierarchy for AI tiers
  tier: {
    1: '#FFD700',   // Gold — Prime AI (The Sovereign)
    2: '#C0C0C0',   // Silver — Primes (Cornelius, Doctor, Guardian)
    3: '#CD7F32',   // Bronze — Lead AIs
    4: '#60A5FA',   // Blue-400 — Agents / Microservices
    5: '#9CA3AF',   // Gray-400 — Bots / Nanoservices
  },

  // Status colors
  status: {
    online: '#10B981',
    degraded: '#F59E0B',
    offline: '#EF4444',
    maintenance: '#8B5CF6',
    booting: '#06B6D4',
    unknown: '#6B7280',
  },

  // Severity colors (maps to security scanner)
  severity: {
    critical: '#EF4444',
    high: '#F97316',
    medium: '#F59E0B',
    low: '#10B981',
    info: '#3B82F6',
    suppressed: '#6B7280',
  },

  // Circuit breaker states
  circuitBreaker: {
    closed: '#10B981',    // Green — healthy, flowing
    open: '#EF4444',      // Red — tripped, blocking
    half_open: '#F59E0B', // Amber — probing, cautious
  },
} as const

// ─── Typography ─────────────────────────────────────────────────────────────

export const typography = {
  fontFamily: {
    display: 'Inter, system-ui, -apple-system, sans-serif',
    mono: 'JetBrains Mono, Fira Code, Consolas, monospace',
  },
  fontSize: {
    xs: '0.75rem',    // 12px
    sm: '0.875rem',   // 14px
    base: '1rem',     // 16px
    lg: '1.125rem',   // 18px
    xl: '1.25rem',    // 20px
    '2xl': '1.5rem',  // 24px
    '3xl': '1.875rem', // 30px
  },
  fontWeight: {
    normal: 400,
    medium: 500,
    semibold: 600,
    bold: 700,
  },
} as const

// ─── Spacing & Layout ───────────────────────────────────────────────────────

export const layout = {
  sidebar: {
    width: '280px',
    collapsed: '64px',
  },
  header: {
    height: '56px',
  },
  hubCard: {
    minWidth: '280px',
    gap: '16px',
  },
  panel: {
    padding: '24px',
    radius: '12px',
  },
} as const

// ─── Animation ──────────────────────────────────────────────────────────────

export const animation = {
  pulse: {
    duration: '2s',
    timing: 'ease-in-out',
  },
  fade: {
    duration: '150ms',
    timing: 'ease-out',
  },
  slide: {
    duration: '200ms',
    timing: 'cubic-bezier(0.4, 0, 0.2, 1)',
  },
  neuralBus: {
    particleSpeed: '1.5s',
    glowIntensity: '0.6',
  },
} as const

// ─── Icon Mapping ───────────────────────────────────────────────────────────

export const hubIcons: Record<string, string> = {
  'the-nexus': 'Brain',
  'the-observatory': 'Eye',
  'infinity': 'Infinite',
  'the-void': 'CircleDot',
  'the-lighthouse': 'RadioTower',
  'the-warp-tunnel': 'Zap',
  'the-ice-box': 'Snowflake',
  'devocity': 'GitBranch',
  'turings-hub': 'Cpu',
  'chronosphere': 'Clock',
  'the-citadel': 'Shield',
  'the-dutchy': 'Crown',
  'the-studio': 'Palette',
  'imaginarium': 'Sparkles',
  'tranquility': 'Heart',
  'i-mind': 'BrainCircuit',
  'taimra': 'MessageSquare',
  'vrar3d': 'Box',
  'resonate': 'Volume2',
  'royal-bank': 'Landmark',
  'arcadian-exchange': 'TrendingUp',
  'the-artifactory': 'Package',
  'api-marketplace': 'Store',
  'the-digital-grid': 'Grid3x3',
  'the-lab': 'FlaskConical',
  'the-workshop': 'Wrench',
  'the-chaos-party': 'Flame',
  'the-library': 'BookOpen',
  'the-basement': 'Archive',
  'the-hive': 'Hexagon',
  'the-swarm': 'Bug',
  'the-town-hall': 'Building2',
  'fablousa': 'Feather',
  'luminous': 'Sun',
}

// ─── Pillar Definitions ─────────────────────────────────────────────────────

export interface PillarDef {
  id: string
  name: string
  color: string
  hubs: string[]
}

export const pillars: PillarDef[] = [
  {
    id: 'architectural',
    name: 'Architectural',
    color: colors.pillars.architectural,
    hubs: ['the-nexus', 'infinity', 'the-void', 'the-lighthouse', 'the-warp-tunnel', 'the-ice-box'],
  },
  {
    id: 'development',
    name: 'Development',
    color: colors.pillars.development,
    hubs: ['devocity', 'turings-hub', 'the-workshop', 'the-lab'],
  },
  {
    id: 'creativity',
    name: 'Creativity',
    color: colors.pillars.creativity,
    hubs: ['the-studio', 'imaginarium', 'fablousa'],
  },
  {
    id: 'commercial',
    name: 'Commercial & Financial',
    color: colors.pillars.commercial,
    hubs: ['the-dutchy', 'royal-bank', 'arcadian-exchange', 'the-artifactory', 'api-marketplace', 'the-digital-grid'],
  },
  {
    id: 'knowledge',
    name: 'Knowledge',
    color: colors.pillars.knowledge,
    hubs: ['the-observatory', 'the-library', 'the-basement'],
  },
  {
    id: 'security',
    name: 'Security',
    color: colors.pillars.security,
    hubs: ['the-citadel', 'the-chaos-party'],
  },
  {
    id: 'devops',
    name: 'DevOps',
    color: colors.pillars.devops,
    hubs: ['the-hive', 'the-swarm'],
  },
  {
    id: 'wellbeing',
    name: 'Wellbeing',
    color: colors.pillars.wellbeing,
    hubs: ['tranquility', 'i-mind', 'taimra'],
  },
  {
    id: 'foresight',
    name: 'Foresight',
    color: colors.pillars.foresight,
    hubs: ['chronosphere', 'luminous'],
  },
  {
    id: 'governance',
    name: 'Governance',
    color: colors.pillars.governance,
    hubs: ['the-town-hall'],
  },
  {
    id: 'immersive',
    name: 'Immersive',
    color: '#F472B6',
    hubs: ['vrar3d', 'resonate'],
  },
]

// ─── Hub Status Type ────────────────────────────────────────────────────────

export type SystemMode = 'TRUE_NAS' | 'HYBRID' | 'CLOUD_ONLY'
export type HubStatus = 'online' | 'degraded' | 'offline' | 'maintenance' | 'booting' | 'unknown'
export type CircuitState = 'closed' | 'open' | 'half_open'
export type SeverityLevel = 'critical' | 'high' | 'medium' | 'low' | 'info' | 'suppressed'
export type TierLevel = 1 | 2 | 3 | 4 | 5

export interface HubState {
  id: string
  name: string
  pillar: string
  tier: TierLevel
  status: HubStatus
  systemMode: SystemMode
  services: number
  activeAgents: number
  circuitBreaker: CircuitState
  healthScore: number       // 0-100
  lastHeartbeat: string
  alerts: number
}
