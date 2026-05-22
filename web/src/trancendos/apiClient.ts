/**
 * Trancendos Ecosystem API Client
 *
 * Talks to the api_ecosystem.py FastAPI backend.
 * Falls back to mock data when the API is unreachable (dev mode).
 */

import type { HubState, SystemMode } from './tokens'

const API_BASE = import.meta.env.VITE_ECOSYSTEM_API_URL || '/api/ecosystem'

// ─── Types ──────────────────────────────────────────────────────────────────

export interface HubsResponse {
  hubs: HubState[]
  totalHubs: number
  onlineHubs: number
  totalServices: number
  totalAgents: number
  avgHealth: number
  totalAlerts: number
  systemMode: SystemMode
}

export interface SecurityPosture {
  violations: number
  suppressed: number
  audit_chain_valid: boolean
  secret_leaks: number
  vault_status: string
  last_scan_time: string | null
}

export interface CitadelOverview {
  total_services: number
  total_agents: number
  open_circuits: number
  half_open_circuits: number
  avg_health: number
  system_mode: SystemMode
}

export interface NeuralBusState {
  activeNodes: number
  nodes: { id: string; name: string; color: string; health: number }[]
  connections: { from: string; to: string }[]
  protocol: string
  status: string
}

interface PillarInfo {
  id: string
  name: string
  color: string
  hubCount: number
  onlineHubs: number
  alerts: number
  hubs: string[]
}

// ─── Generic Fetch with Error Handling ──────────────────────────────────────

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T | null> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      headers: { 'Content-Type': 'application/json', ...options?.headers },
      ...options,
    })
    if (!res.ok) {
      console.warn(`[EcosystemAPI] ${path} returned ${res.status}`)
      return null
    }
    return await res.json()
  } catch (err) {
    console.warn(`[EcosystemAPI] ${path} failed:`, err)
    return null
  }
}

// ─── API Functions ──────────────────────────────────────────────────────────

export async function fetchHubs(pillar?: string): Promise<HubsResponse | null> {
  const query = pillar ? `?pillar=${pillar}` : ''
  return fetchAPI<HubsResponse>(`/hubs${query}`)
}

export async function fetchHubDetail(hubId: string): Promise<HubState | null> {
  return fetchAPI<HubState>(`/hubs/${hubId}`)
}

export async function fetchCitadelOverview(): Promise<CitadelOverview | null> {
  return fetchAPI<CitadelOverview>('/citadel')
}

export async function fetchSecurityPosture(): Promise<SecurityPosture | null> {
  return fetchAPI<SecurityPosture>('/security')
}

export async function fetchPillars(): Promise<PillarInfo[] | null> {
  return fetchAPI<PillarInfo[]>('/pillars')
}

export async function fetchNeuralBus(): Promise<NeuralBusState | null> {
  return fetchAPI<NeuralBusState>('/neural-bus')
}

export async function setSystemMode(mode: SystemMode): Promise<{ status: string; mode: string } | null> {
  return fetchAPI<{ status: string; mode: string }>('/mode', {
    method: 'POST',
    body: JSON.stringify({ mode }),
  })
}

export async function fetchHealthCheck(): Promise<{ status: string; timestamp: string; systemMode: string } | null> {
  return fetchAPI('/health')
}

// ─── Hook-friendly data fetcher ─────────────────────────────────────────────

export interface EcosystemData {
  hubs: HubsResponse | null
  citadel: CitadelOverview | null
  security: SecurityPosture | null
  neuralBus: NeuralBusState | null
  pillars: PillarInfo[] | null
  loading: boolean
  error: string | null
}

export async function fetchAllEcosystemData(): Promise<EcosystemData> {
  const [hubs, citadel, security, neuralBus, pillars] = await Promise.all([
    fetchHubs(),
    fetchCitadelOverview(),
    fetchSecurityPosture(),
    fetchNeuralBus(),
    fetchPillars(),
  ])

  return {
    hubs,
    citadel,
    security,
    neuralBus,
    pillars,
    loading: false,
    error: null,
  }
}
