/**
 * TuringsHubPage — AI Creation Centre (Turing's Hub · Port 8035)
 * Lead AI: Samantha Turing
 *
 * Lists all platform AI entity manifests — voice engine, avatar, animations.
 * Gateway to the 3D embodiment layer of every Trancendos Lead AI.
 */
import React, { useEffect, useState, useCallback } from 'react'
import { Cpu, RefreshCw, Mic, User, Film, Brain, CheckCircle, XCircle } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const TURINGS_API = '/turings'

interface EntitySummary {
  entity_id: string
  lead_ai: string | null
  voice_engine: string
  has_vrm: boolean
  has_portrait: boolean
}

interface HubHealth {
  status: string
  purpose: string
  tts: { kokoro: string; piper: string }
  lip_sync: { rhubarb: string }
  entities_configured: number
  vrm_assets: number
  animation_assets: number
}

const VOICE_COLORS: Record<string, string> = {
  kokoro:  'bg-purple-900/40 text-purple-300 border-purple-700',
  piper:   'bg-blue-900/40 text-blue-300 border-blue-700',
  unknown: 'bg-gray-800 text-gray-400 border-gray-600',
}

function AssetBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={`inline-flex items-center gap-1 text-xs ${ok ? 'text-green-400' : 'text-gray-600'}`}>
      {ok ? <CheckCircle size={11} aria-hidden="true" /> : <XCircle size={11} aria-hidden="true" />}
      {label}
    </span>
  )
}

export default function TuringsHubPage() {
  const [entities, setEntities]   = useState<EntitySummary[]>([])
  const [health, setHealth]       = useState<HubHealth | null>(null)
  const [loading, setLoading]     = useState(false)
  const [workerDown, setWorkerDown] = useState(false)
  const { trackPageView } = useAnalytics()

  useEffect(() => { trackPageView('/turings-hub') }, [trackPageView])

  const load = useCallback(async () => {
    setLoading(true)
    setWorkerDown(false)
    try {
      const [hResp, eResp] = await Promise.all([
        fetch(`${TURINGS_API}/health`, { signal: AbortSignal.timeout(4000) }),
        fetch(`${TURINGS_API}/entities`, { signal: AbortSignal.timeout(4000) }),
      ])
      if (hResp.ok) setHealth(await hResp.json())
      if (eResp.ok) {
        const body = await eResp.json()
        setEntities(body.entities ?? [])
      }
      if (!hResp.ok && !eResp.ok) setWorkerDown(true)
    } catch {
      setWorkerDown(true)
    }
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  const isServiceUp = (desc: string) => !desc.toLowerCase().includes('unavailable')

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Cpu size={22} aria-hidden="true" className="text-teal-400" />
            Turing's Hub
          </h1>
          <p className="text-gray-400 text-sm mt-1">
            AI Creation Centre · Lead AI: Samantha Turing · Port 8035
            {health && ` · ${health.entities_configured} entities configured`}
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
          Turing's Hub worker (port 8035) is unreachable. Start with{' '}
          <code className="font-mono bg-gray-800 px-1 rounded">make dev-api</code>.
        </div>
      )}

      {/* Health tiles */}
      {health && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-4">
            <div className="text-2xl font-bold text-teal-400 tabular-nums">{health.entities_configured}</div>
            <div className="text-gray-400 text-sm mt-1">Entities</div>
          </div>
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-4">
            <div className="text-2xl font-bold text-purple-400 tabular-nums">{health.vrm_assets}</div>
            <div className="text-gray-400 text-sm mt-1">VRM Avatars</div>
          </div>
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-4">
            <div className="text-2xl font-bold text-blue-400 tabular-nums">{health.animation_assets}</div>
            <div className="text-gray-400 text-sm mt-1">Animations</div>
          </div>
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-4">
            <div className="flex flex-col gap-1.5 mt-0.5">
              <div className={`text-xs flex items-center gap-1.5 ${isServiceUp(health.tts.kokoro) ? 'text-green-400' : 'text-gray-500'}`}>
                <Mic size={11} aria-hidden="true" />
                Kokoro TTS: {isServiceUp(health.tts.kokoro) ? 'up' : 'offline'}
              </div>
              <div className={`text-xs flex items-center gap-1.5 ${isServiceUp(health.lip_sync.rhubarb) ? 'text-green-400' : 'text-gray-500'}`}>
                <Film size={11} aria-hidden="true" />
                Rhubarb: {isServiceUp(health.lip_sync.rhubarb) ? 'up' : 'offline'}
              </div>
            </div>
            <div className="text-gray-400 text-sm mt-1">Toolchain</div>
          </div>
        </div>
      )}

      {/* Entity grid */}
      {entities.length === 0 && !loading ? (
        <div className="bg-gray-900 rounded-lg border border-gray-700 p-8 text-center text-gray-500">
          {workerDown ? 'Worker offline' : 'No entities found.'}
        </div>
      ) : (
        <>
          <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-widest mb-3">
            Entity Manifests
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {entities.map(e => (
              <div
                key={e.entity_id}
                className="bg-gray-900 border border-gray-700 rounded-lg p-4 hover:border-gray-500 transition-colors"
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-full bg-teal-900/50 border border-teal-700 flex items-center justify-center">
                      <Brain size={14} className="text-teal-400" aria-hidden="true" />
                    </div>
                    <div>
                      <p className="text-gray-200 font-medium text-sm">{e.lead_ai ?? '—'}</p>
                      <p className="text-gray-600 text-xs font-mono">{e.entity_id}</p>
                    </div>
                  </div>
                  <span className={`text-xs border rounded-full px-2 py-0.5 ${VOICE_COLORS[e.voice_engine] ?? VOICE_COLORS.unknown}`}>
                    {e.voice_engine}
                  </span>
                </div>
                <div className="flex gap-3">
                  <AssetBadge ok={e.has_vrm} label="VRM" />
                  <AssetBadge ok={e.has_portrait} label="Portrait" />
                </div>
              </div>
            ))}
          </div>

          {/* 3D viewer note */}
          <div className="mt-6 p-4 bg-gray-900/50 border border-gray-700 rounded-lg text-sm text-gray-500">
            <p className="flex items-center gap-2">
              <Film size={14} aria-hidden="true" />
              <span>
                3D VRM avatar viewer powered by Three.js + three-vrm. VRM assets must be placed in{' '}
                <code className="font-mono text-gray-400 bg-gray-800 px-1 rounded">
                  workers/turings-hub-service/assets/vrm/
                </code>
                . Lip-sync via Rhubarb + Kokoro TTS when running locally.
              </span>
            </p>
          </div>
        </>
      )}
    </div>
  )
}
