import React, { useCallback, useEffect, useState } from 'react'
import { ArrowLeftRight, RefreshCw, Send, Activity } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const API = '/infinity-bridge-svc'
const HEADERS = { 'X-Internal-Secret': 'dev-secret' }
const INTERNAL = { 'X-Internal-Secret': 'dev-secret', 'Content-Type': 'application/json' }

interface BridgeStats {
  active_transfers: number
  completed_transfers: number
  failed_transfers: number
  connected_entities: number
}

interface Transfer {
  transfer_id: string
  source_entity: string
  target_entity: string
  status: string
  payload_size: number
  created_at: string
}

const STATUS_COLORS: Record<string, string> = {
  pending: 'text-amber-400',
  in_progress: 'text-blue-400',
  completed: 'text-emerald-400',
  failed: 'text-red-400',
}

export default function InfinityBridgePage() {
  const { trackPageView } = useAnalytics()
  const [stats, setStats] = useState<BridgeStats | null>(null)
  const [transfers, setTransfers] = useState<Transfer[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [source, setSource] = useState('')
  const [target, setTarget] = useState('')
  const [payload, setPayload] = useState('')
  const [sending, setSending] = useState(false)
  const [sendMsg, setSendMsg] = useState<string | null>(null)

  useEffect(() => { trackPageView('/infinity-bridge') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [healthRes, statsRes, transfersRes] = await Promise.all([
        fetch(`${API}/health`),
        fetch(`${API}/bridge/stats`, { headers: HEADERS }),
        fetch(`${API}/bridge/transfers?limit=10`, { headers: HEADERS }),
      ])
      if (!healthRes.ok) throw new Error('Infinity-Bridge unavailable')
      if (statsRes.ok) setStats(await statsRes.json())
      if (transfersRes.ok) {
        const r = await transfersRes.json()
        setTransfers(r.transfers ?? r)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const initiateTransfer = async () => {
    if (!source.trim() || !target.trim()) return
    setSending(true)
    setSendMsg(null)
    try {
      const res = await fetch(`${API}/bridge/transfer`, {
        method: 'POST',
        headers: INTERNAL,
        body: JSON.stringify({ source_entity: source, target_entity: target, payload: payload || '{}' }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setSendMsg('Transfer initiated!')
      setSource('')
      setTarget('')
      setPayload('')
      loadData()
    } catch (e) {
      setSendMsg(e instanceof Error ? e.message : 'Failed')
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <ArrowLeftRight size={22} className="text-teal-400" /> Infinity Bridge
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Human traffic transfer hub — cross-entity routing — Port 8070</p>
        </div>
        <button
          onClick={loadData}
          disabled={loading}
          className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-300 hover:text-white disabled:opacity-50 transition-colors"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-lg bg-red-500/10 border border-red-500/30 px-4 py-3 text-sm text-red-300">
          {error} — is infinity-bridge-service running on port 8070?
        </div>
      )}

      <div className="grid grid-cols-4 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Active Transfers</p>
          <p className="text-2xl font-bold text-blue-400">{stats?.active_transfers ?? 0}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Completed</p>
          <p className="text-2xl font-bold text-emerald-400">{stats?.completed_transfers ?? 0}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Failed</p>
          <p className="text-2xl font-bold text-red-400">{stats?.failed_transfers ?? 0}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Connected Entities</p>
          <p className="text-2xl font-bold text-teal-400">{stats?.connected_entities ?? 0}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4 space-y-3">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2"><Send size={14} className="text-teal-400" /> Initiate Transfer</h2>
          <input
            value={source}
            onChange={e => setSource(e.target.value)}
            placeholder="Source entity"
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-teal-500"
          />
          <input
            value={target}
            onChange={e => setTarget(e.target.value)}
            placeholder="Target entity"
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-teal-500"
          />
          <input
            value={payload}
            onChange={e => setPayload(e.target.value)}
            placeholder='Payload JSON (optional)'
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-teal-500"
          />
          <button
            onClick={initiateTransfer}
            disabled={sending || !source.trim() || !target.trim()}
            className="w-full flex items-center justify-center gap-1.5 rounded-lg bg-teal-600 hover:bg-teal-700 disabled:opacity-50 px-4 py-1.5 text-xs text-white font-medium transition-colors"
          >
            <Send size={11} /> {sending ? 'Sending…' : 'Transfer'}
          </button>
          {sendMsg && <p className="text-xs text-emerald-400">{sendMsg}</p>}
        </div>

        <div className="md:col-span-2 rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2 mb-3"><Activity size={14} className="text-teal-400" /> Recent Transfers</h2>
          {transfers.length === 0 ? (
            <p className="text-xs text-slate-500">No transfers yet</p>
          ) : (
            <div className="space-y-2">
              {transfers.map(t => (
                <div key={t.transfer_id} className="flex items-center gap-3 py-2 border-b border-slate-800 last:border-0">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-slate-200 truncate">{t.source_entity} → {t.target_entity}</p>
                    <p className="text-xs text-slate-500">{t.transfer_id} · {t.payload_size}B</p>
                  </div>
                  <span className={`text-xs shrink-0 ${STATUS_COLORS[t.status] ?? 'text-slate-400'}`}>{t.status}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
