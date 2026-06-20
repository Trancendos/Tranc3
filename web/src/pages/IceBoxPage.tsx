import React, { useCallback, useEffect, useState } from 'react'
import { Snowflake, RefreshCw, Search, Shield } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const API = '/ice-box-svc'
const INTERNAL = { 'X-Internal-Secret': 'dev-secret', 'Content-Type': 'application/json' }

interface ScanResult {
  content_hash: string
  verdict: string
  allow: boolean
  findings_count: number
  critical_count: number
  high_count: number
  entropy: number
  analysis_ms: number
  quarantine_id: string | null
}

interface QuarantinedItem {
  quarantine_id: string
  content_hash: string
  verdict: string
  quarantined_at: number
}

const VERDICT_COLORS: Record<string, string> = {
  clean: 'text-emerald-400',
  suspicious: 'text-amber-400',
  malicious: 'text-red-400',
}

export default function IceBoxPage() {
  const { trackPageView } = useAnalytics()
  const [signaturesLoaded, setSignaturesLoaded] = useState(0)
  const [quarantined, setQuarantined] = useState<QuarantinedItem[]>([])
  const [stats, setStats] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [scanContent, setScanContent] = useState('')
  const [scanning, setScanning] = useState(false)
  const [scanResult, setScanResult] = useState<ScanResult | null>(null)
  const [scanError, setScanError] = useState<string | null>(null)

  useEffect(() => { trackPageView('/ice-box') }, [trackPageView])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [healthRes, quarantineRes, statsRes] = await Promise.all([
        fetch(`${API}/health`),
        fetch(`${API}/quarantine`),
        fetch(`${API}/stats`),
      ])
      if (!healthRes.ok) throw new Error('Ice Box unavailable')
      const h = await healthRes.json()
      setSignaturesLoaded(h.signatures_loaded ?? 0)
      if (quarantineRes.ok) {
        const q = await quarantineRes.json()
        setQuarantined(q.items ?? q)
      }
      if (statsRes.ok) {
        setStats(await statsRes.json())
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const runScan = async () => {
    if (!scanContent.trim()) return
    setScanning(true)
    setScanResult(null)
    setScanError(null)
    try {
      const res = await fetch(`${API}/scan`, {
        method: 'POST',
        headers: INTERNAL,
        body: JSON.stringify({ content: scanContent, source: 'demo', auto_quarantine: true }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setScanResult(await res.json())
      loadData()
    } catch (e) {
      setScanError(e instanceof Error ? e.message : 'Scan failed')
    } finally {
      setScanning(false)
    }
  }

  const qStats = stats ? (stats.quarantine as Record<string, number> | undefined) : null

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Snowflake size={22} className="text-cyan-400" /> The Ice Box
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">Sandbox threat isolation &amp; quarantine — Lead AI: Neonach</p>
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
          {error} — is ice-box-service running on port 8046?
        </div>
      )}

      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Signatures</p>
          <p className="text-2xl font-bold text-white">{signaturesLoaded}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Quarantined</p>
          <p className="text-2xl font-bold text-amber-400">{qStats?.total ?? quarantined.length}</p>
        </div>
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <p className="text-xs text-slate-400 mb-1">Active</p>
          <p className="text-2xl font-bold text-red-400">{qStats?.active ?? 0}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4 space-y-3">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2"><Search size={14} className="text-cyan-400" /> Threat Scan</h2>
          <textarea
            value={scanContent}
            onChange={e => setScanContent(e.target.value)}
            placeholder="Paste content to scan for threats…"
            rows={4}
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500 resize-none"
          />
          <button
            onClick={runScan}
            disabled={scanning || !scanContent.trim()}
            className="w-full flex items-center justify-center gap-1.5 rounded-lg bg-cyan-700 hover:bg-cyan-600 disabled:opacity-50 px-4 py-1.5 text-xs text-white font-medium transition-colors"
          >
            <Search size={11} /> {scanning ? 'Scanning…' : 'Run Scan'}
          </button>
          {scanError && <p className="text-xs text-red-400">{scanError}</p>}
          {scanResult && (
            <div className="rounded-lg bg-slate-800 p-3 space-y-1">
              <div className="flex items-center justify-between">
                <span className={`text-sm font-bold ${VERDICT_COLORS[scanResult.verdict] ?? 'text-slate-300'}`}>
                  {scanResult.verdict.toUpperCase()}
                </span>
                <span className={`text-xs ${scanResult.allow ? 'text-emerald-400' : 'text-red-400'}`}>
                  {scanResult.allow ? 'ALLOWED' : 'BLOCKED'}
                </span>
              </div>
              <p className="text-xs text-slate-400">Findings: {scanResult.findings_count} ({scanResult.critical_count} critical, {scanResult.high_count} high)</p>
              <p className="text-xs text-slate-500">Entropy: {scanResult.entropy.toFixed(3)} · {scanResult.analysis_ms.toFixed(1)}ms</p>
              {scanResult.quarantine_id && (
                <p className="text-xs text-amber-400">Quarantined: {scanResult.quarantine_id.slice(0, 12)}…</p>
              )}
            </div>
          )}
        </div>

        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2 mb-3"><Shield size={14} className="text-cyan-400" /> Quarantine</h2>
          {quarantined.length === 0 ? (
            <p className="text-xs text-slate-500">No items in quarantine</p>
          ) : (
            <div className="space-y-2">
              {quarantined.map(item => (
                <div key={item.quarantine_id} className="py-2 border-b border-slate-800 last:border-0">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-slate-400 font-mono">{item.quarantine_id.slice(0, 12)}…</span>
                    <span className={`text-xs ${VERDICT_COLORS[item.verdict] ?? 'text-slate-400'}`}>{item.verdict}</span>
                  </div>
                  <p className="text-xs text-slate-600 font-mono truncate">{item.content_hash.slice(0, 20)}…</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
