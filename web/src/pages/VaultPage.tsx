import React, { useCallback, useEffect, useState } from 'react'
import { Lock, RefreshCw, ShieldAlert, ShieldCheck, ScanLine } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'

const VAULT_API = '/vault'
const INTERNAL = { 'X-Internal-Secret': 'dev-secret' }

interface Stats {
  total_secrets: number
  active_secrets: number
  revoked_secrets: number
  audit_entries: number
  open_leak_detections: number
}

interface Secret {
  id: string
  key: string
  tags: string[]
  ttl: number | null
  version: number
  is_active: number
  created_at: string
  updated_at: string
  expires_at: string | null
}

interface AuditEntry {
  id: string
  secret_id: string
  action: string
  details: string
  hash: string
  prev_hash: string
  created_at: string
}

interface ScanResult {
  leaks_found: number
  leaks: Array<{ variable_name: string; preview: string; severity: string }>
}

type Tab = 'secrets' | 'audit'

function StatTile({ label, value, warn }: { label: string; value: string | number; warn?: boolean }) {
  return (
    <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
      <p className="text-xs text-slate-400 mb-1">{label}</p>
      <p className={`text-2xl font-bold ${warn ? 'text-red-400' : 'text-white'}`}>{value}</p>
    </div>
  )
}

export default function VaultPage() {
  const { trackPageView } = useAnalytics()
  const [stats, setStats] = useState<Stats | null>(null)
  const [secrets, setSecrets] = useState<Secret[]>([])
  const [audit, setAudit] = useState<AuditEntry[]>([])
  const [scanResult, setScanResult] = useState<ScanResult | null>(null)
  const [scanning, setScanning] = useState(false)
  const [tab, setTab] = useState<Tab>('secrets')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeOnly, setActiveOnly] = useState(true)

  useEffect(() => { trackPageView('/vault') }, [trackPageView])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [sRes, secRes, aRes] = await Promise.all([
        fetch(`${VAULT_API}/stats`, { headers: INTERNAL }),
        fetch(`${VAULT_API}/secrets?active_only=${activeOnly}&limit=100`, { headers: INTERNAL }),
        fetch(`${VAULT_API}/audit?limit=100`, { headers: INTERNAL }),
      ])
      if (!sRes.ok || !secRes.ok || !aRes.ok) throw new Error('Service unavailable')
      const [s, sec, a] = await Promise.all([sRes.json(), secRes.json(), aRes.json()])
      setStats(s)
      setSecrets(sec)
      setAudit(a)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [activeOnly])

  useEffect(() => { load() }, [load])

  const runScan = useCallback(async () => {
    setScanning(true)
    try {
      const r = await fetch(`${VAULT_API}/scan/leaks`, { headers: INTERNAL, signal: AbortSignal.timeout(15000) })
      if (r.ok) setScanResult(await r.json())
    } catch { /* ignore */ } finally {
      setScanning(false)
      load()
    }
  }, [load])

  const fmt = (iso: string) => {
    try { return new Date(iso).toLocaleString() } catch { return iso }
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Lock size={22} className="text-red-400" /> The Void — Vault
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">AES-GCM encrypted secrets · audit chain · leak detection</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={runScan}
            disabled={scanning}
            className="flex items-center gap-1.5 rounded-lg border border-amber-700/50 bg-amber-900/20 px-3 py-1.5 text-xs text-amber-300 hover:text-amber-100 disabled:opacity-50 transition-colors"
          >
            <ScanLine size={12} className={scanning ? 'animate-pulse' : ''} /> Scan for Leaks
          </button>
          <button
            onClick={load}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-300 hover:text-white disabled:opacity-50 transition-colors"
          >
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg bg-red-500/10 border border-red-500/30 px-4 py-3 text-sm text-red-300">
          {error} — is vault-service running on port 8038?
        </div>
      )}

      {scanResult && (
        <div className={`rounded-lg border px-4 py-3 flex items-start gap-3 ${scanResult.leaks_found === 0 ? 'bg-emerald-500/10 border-emerald-500/30' : 'bg-red-500/10 border-red-500/30'}`}>
          {scanResult.leaks_found === 0
            ? <ShieldCheck size={16} className="text-emerald-400 flex-shrink-0 mt-0.5" />
            : <ShieldAlert size={16} className="text-red-400 flex-shrink-0 mt-0.5" />}
          <div className="flex-1">
            <p className={`text-sm font-medium ${scanResult.leaks_found === 0 ? 'text-emerald-300' : 'text-red-300'}`}>
              {scanResult.leaks_found === 0 ? 'No credential leaks detected' : `${scanResult.leaks_found} potential leak${scanResult.leaks_found !== 1 ? 's' : ''} found`}
            </p>
            {scanResult.leaks.map((l, i) => (
              <p key={i} className="text-xs text-slate-400 mt-0.5">
                <code className="text-red-300">{l.variable_name}</code>: {l.preview}
              </p>
            ))}
          </div>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <StatTile label="Total Secrets" value={stats?.total_secrets ?? '—'} />
        <StatTile label="Active" value={stats?.active_secrets ?? '—'} />
        <StatTile label="Revoked" value={stats?.revoked_secrets ?? '—'} />
        <StatTile label="Audit Entries" value={stats?.audit_entries ?? '—'} />
        <StatTile label="Open Leaks" value={stats?.open_leak_detections ?? '—'} warn={(stats?.open_leak_detections ?? 0) > 0} />
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-700/60">
        {(['secrets', 'audit'] as Tab[]).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium capitalize transition-colors border-b-2 -mb-px ${
              tab === t ? 'border-red-500 text-red-400' : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            {t === 'secrets' ? 'Secrets' : 'Audit Log'}
          </button>
        ))}
      </div>

      {tab === 'secrets' && (
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/60">
            <h2 className="text-sm font-semibold text-white">Secret Registry</h2>
            <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
              <input type="checkbox" checked={activeOnly} onChange={e => setActiveOnly(e.target.checked)} className="accent-red-500" />
              Active only
            </label>
          </div>
          {loading && !secrets.length ? (
            <div className="p-8 text-center text-slate-500 text-sm">Loading secrets…</div>
          ) : secrets.length === 0 ? (
            <div className="p-8 text-center text-slate-500 text-sm">No secrets in vault.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700/60 text-xs text-slate-500 uppercase tracking-wider">
                    <th className="text-left px-4 py-2">Key</th>
                    <th className="text-left px-4 py-2">Tags</th>
                    <th className="text-right px-4 py-2">Version</th>
                    <th className="text-right px-4 py-2">TTL</th>
                    <th className="text-center px-4 py-2">Status</th>
                    <th className="text-right px-4 py-2">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {secrets.map(s => (
                    <tr key={s.id} className="border-b border-slate-800 hover:bg-slate-800/30 transition-colors">
                      <td className="px-4 py-2.5 font-mono text-sm text-slate-200">{s.key}</td>
                      <td className="px-4 py-2.5">
                        <div className="flex flex-wrap gap-1">
                          {s.tags?.map((t: string) => (
                            <span key={t} className="text-xs px-1 py-0.5 rounded bg-slate-700/60 text-slate-400">{t}</span>
                          ))}
                        </div>
                      </td>
                      <td className="px-4 py-2.5 text-right text-slate-300">v{s.version}</td>
                      <td className="px-4 py-2.5 text-right text-slate-400">{s.ttl ? `${s.ttl}s` : '∞'}</td>
                      <td className="px-4 py-2.5 text-center">
                        <span className={`text-xs px-1.5 py-0.5 rounded border ${s.is_active ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' : 'bg-red-500/20 text-red-300 border-red-500/30'}`}>
                          {s.is_active ? 'active' : 'revoked'}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-right text-slate-500 whitespace-nowrap text-xs">{fmt(s.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === 'audit' && (
        <div className="rounded-xl border border-slate-700/60 bg-slate-900/70 overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-700/60">
            <h2 className="text-sm font-semibold text-white">Vault Audit Log</h2>
          </div>
          {loading && !audit.length ? (
            <div className="p-8 text-center text-slate-500 text-sm">Loading audit log…</div>
          ) : audit.length === 0 ? (
            <div className="p-8 text-center text-slate-500 text-sm">No audit entries.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700/60 text-xs text-slate-500 uppercase tracking-wider">
                    <th className="text-left px-4 py-2">Timestamp</th>
                    <th className="text-left px-4 py-2">Action</th>
                    <th className="text-left px-4 py-2">Secret ID</th>
                    <th className="text-left px-4 py-2">Hash</th>
                  </tr>
                </thead>
                <tbody>
                  {audit.map(a => (
                    <tr key={a.id} className="border-b border-slate-800 hover:bg-slate-800/30 transition-colors">
                      <td className="px-4 py-2.5 text-slate-400 whitespace-nowrap text-xs">{fmt(a.created_at)}</td>
                      <td className="px-4 py-2.5">
                        <span className="text-xs px-1.5 py-0.5 rounded bg-red-500/20 text-red-300 border border-red-500/30 font-mono">{a.action}</span>
                      </td>
                      <td className="px-4 py-2.5 font-mono text-xs text-slate-500">{a.secret_id?.slice(0, 12)}…</td>
                      <td className="px-4 py-2.5 font-mono text-xs text-slate-600" title={a.hash}>{a.hash?.slice(0, 16)}…</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
