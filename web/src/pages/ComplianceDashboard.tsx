/**
 * ComplianceDashboard — DEFSTAN Compliance Framework
 *
 * Live compliance status pulled from GET /compliance/status and /compliance/report.
 * Falls back to mock data when backend is offline.
 *
 * Features:
 * - Overall compliance score donut gauge (SVG, no external deps)
 * - Per-standard breakdown table
 * - Full requirements table with filters (by standard, by status)
 * - Traceability panel: click a requirement to see evidence links
 * - "Generate Report" button downloading full report JSON
 * - Status badges: COMPLIANT (green), PARTIAL (amber), PLANNED (blue),
 *   NA (grey), WAIVED (purple)
 */

import React, { useEffect, useState, useCallback } from 'react'
import {
  ShieldCheck,
  AlertTriangle,
  Clock,
  Ban,
  MinusCircle,
  RefreshCw,
  Download,
  ChevronDown,
  ChevronRight,
  ExternalLink,
} from 'lucide-react'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// ── Types ─────────────────────────────────────────────────────────────────────

interface AreaSummary {
  area: string
  standard: string
  total: number
  compliant: number
  partial: number
  planned: number
  score_pct: number
}

interface Evidence {
  type: string
  path: string
  description: string
  exists: boolean
}

interface Requirement {
  id: string
  standard: string
  title: string
  status: string
  area: string
  all_evidence_present: boolean
  notes: string
  evidence: Evidence[]
}

interface ComplianceStatus {
  platform: string
  classification: string
  overall_score: number
  generated_at: string
  ci_pass: boolean
  status_counts: Record<string, number>
  areas: Record<string, AreaSummary>
}

interface ComplianceReport extends ComplianceStatus {
  requirements: Requirement[]
}

// ── Mock data (shown when backend offline) ────────────────────────────────────

const MOCK_STATUS: ComplianceStatus = {
  platform: 'Tranc3 / Trancendos (offline — mock data)',
  classification: 'UNCLASSIFIED — PUBLIC',
  overall_score: 83.6,
  generated_at: new Date().toISOString(),
  ci_pass: true,
  status_counts: { COMPLIANT: 38, PARTIAL: 9, PLANNED: 3, WAIVED: 0, NA: 0 },
  areas: {
    IA: { area: 'IA', standard: 'DEF STAN 00-700', total: 10, compliant: 8, partial: 1, planned: 0, score_pct: 85.0 },
    SA: { area: 'SA', standard: 'DEF STAN 00-055', total: 6, compliant: 3, partial: 2, planned: 1, score_pct: 66.7 },
    QA: { area: 'QA', standard: 'DEF STAN 05-086', total: 7, compliant: 6, partial: 1, planned: 0, score_pct: 92.9 },
    CM: { area: 'CM', standard: 'DEF STAN 00-044', total: 6, compliant: 5, partial: 1, planned: 0, score_pct: 91.7 },
    SU: { area: 'SU', standard: 'DEF STAN 00-600', total: 7, compliant: 4, partial: 2, planned: 1, score_pct: 71.4 },
    SD: { area: 'SD', standard: 'DEF STAN 00-056', total: 7, compliant: 5, partial: 2, planned: 0, score_pct: 85.7 },
    TD: { area: 'TD', standard: 'DEF STAN 05-057', total: 7, compliant: 6, partial: 1, planned: 0, score_pct: 92.9 },
  },
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const STATUS_STYLES: Record<string, string> = {
  COMPLIANT: 'bg-green-500/15 text-green-400 border border-green-500/30',
  PARTIAL:   'bg-amber-500/15 text-amber-400 border border-amber-500/30',
  PLANNED:   'bg-blue-500/15 text-blue-400 border border-blue-500/30',
  WAIVED:    'bg-purple-500/15 text-purple-400 border border-purple-500/30',
  NA:        'bg-gray-500/15 text-gray-400 border border-gray-500/30',
}

const STATUS_ICONS: Record<string, React.ReactNode> = {
  COMPLIANT: <ShieldCheck className="w-3 h-3" />,
  PARTIAL:   <AlertTriangle className="w-3 h-3" />,
  PLANNED:   <Clock className="w-3 h-3" />,
  WAIVED:    <Ban className="w-3 h-3" />,
  NA:        <MinusCircle className="w-3 h-3" />,
}

function StatusBadge({ status }: { status: string }) {
  const s = status.toUpperCase()
  const cls = STATUS_STYLES[s] ?? 'bg-gray-500/15 text-gray-400'
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold uppercase tracking-wide ${cls}`}>
      {STATUS_ICONS[s]}
      {s}
    </span>
  )
}

function ScoreDonut({ score }: { score: number }) {
  const radius = 42
  const circ = 2 * Math.PI * radius
  const filled = circ * (score / 100)
  const gap = circ - filled
  const offset = circ * 0.25

  const colour = score >= 80 ? '#22c55e' : score >= 50 ? '#f59e0b' : '#ef4444'

  return (
    <svg viewBox="0 0 100 100" className="w-32 h-32">
      <circle cx="50" cy="50" r={radius} fill="none" stroke="#1f2937" strokeWidth="10" />
      <circle
        cx="50" cy="50" r={radius} fill="none"
        stroke={colour} strokeWidth="10"
        strokeDasharray={`${filled.toFixed(1)} ${gap.toFixed(1)}`}
        strokeDashoffset={offset.toFixed(1)}
        strokeLinecap="round"
      />
      <text x="50" y="46" textAnchor="middle" fill={colour} fontSize="18" fontWeight="800" fontFamily="system-ui">
        {score.toFixed(0)}%
      </text>
      <text x="50" y="60" textAnchor="middle" fill="#6b7280" fontSize="7" fontFamily="system-ui">
        COMPLIANCE
      </text>
    </svg>
  )
}

function ScoreBar({ score }: { score: number }) {
  const colour = score >= 80 ? 'bg-green-500' : score >= 50 ? 'bg-amber-500' : 'bg-red-500'
  return (
    <div className="w-full bg-gray-800 rounded-full h-1.5">
      <div className={`${colour} h-1.5 rounded-full transition-all duration-500`} style={{ width: `${score}%` }} />
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function ComplianceDashboard() {
  const [status, setStatus] = useState<ComplianceStatus | null>(null)
  const [report, setReport] = useState<ComplianceReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [offline, setOffline] = useState(false)
  const [filterStatus, setFilterStatus] = useState<string>('ALL')
  const [filterArea, setFilterArea] = useState<string>('ALL')
  const [expandedReq, setExpandedReq] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const [statusRes, reportRes] = await Promise.all([
        fetch(`${API}/compliance/status`),
        fetch(`${API}/compliance/report`),
      ])
      if (!statusRes.ok || !reportRes.ok) throw new Error('non-ok')
      const [s, r] = await Promise.all([statusRes.json(), reportRes.json()])
      setStatus(s)
      setReport(r)
      setOffline(false)
    } catch {
      setStatus(MOCK_STATUS)
      setReport(null)
      setOffline(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const downloadReport = async () => {
    try {
      const res = await fetch(`${API}/compliance/export/html`)
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'defstan_compliance_report.html'
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      // Fallback: download mock JSON
      const blob = new Blob([JSON.stringify(status, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'defstan_compliance_report.json'
      a.click()
      URL.revokeObjectURL(url)
    }
  }

  const filteredReqs = (report?.requirements ?? []).filter(r => {
    const matchStatus = filterStatus === 'ALL' || r.status === filterStatus
    const matchArea = filterArea === 'ALL' || r.area === filterArea
    return matchStatus && matchArea
  })

  const areas = Object.values(status?.areas ?? {}).sort((a, b) => a.area.localeCompare(b.area))
  const counts = status?.status_counts ?? {}
  const score = status?.overall_score ?? 0

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-6 space-y-6">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <ShieldCheck className="w-7 h-7 text-green-400" />
            DEFSTAN Compliance
          </h1>
          <p className="text-gray-400 text-sm mt-1">
            {status?.platform ?? 'Tranc3 / Trancendos'} &bull; {status?.classification}
          </p>
          {offline && (
            <span className="inline-block mt-1 text-xs text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded">
              Offline — showing mock data
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={fetchData}
            className="flex items-center gap-2 px-3 py-1.5 text-sm text-gray-300 bg-gray-800 rounded-lg hover:bg-gray-700 transition"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          <button
            onClick={downloadReport}
            className="flex items-center gap-2 px-3 py-1.5 text-sm text-white bg-blue-600 rounded-lg hover:bg-blue-500 transition"
          >
            <Download className="w-4 h-4" />
            Generate Report
          </button>
        </div>
      </div>

      {/* Score + Status Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Donut gauge */}
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 flex flex-col items-center justify-center gap-2">
          <ScoreDonut score={score} />
          <div className="text-center">
            <div className={`text-sm font-semibold ${status?.ci_pass ? 'text-green-400' : 'text-red-400'}`}>
              CI Gate: {status?.ci_pass ? 'PASS' : 'FAIL'}
            </div>
            <div className="text-xs text-gray-500 mt-0.5">Threshold: 70%</div>
          </div>
          {status?.generated_at && (
            <div className="text-xs text-gray-600 text-center">
              {new Date(status.generated_at).toLocaleString()}
            </div>
          )}
        </div>

        {/* Status counts */}
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">Status Breakdown</h2>
          <div className="space-y-3">
            {(['COMPLIANT', 'PARTIAL', 'PLANNED', 'WAIVED', 'NA'] as const).map(s => (
              <div key={s} className="flex items-center justify-between">
                <StatusBadge status={s} />
                <span className="text-gray-300 font-mono text-sm">{counts[s] ?? 0}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Summary */}
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">Quick Stats</h2>
          <div className="space-y-3">
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">Total Requirements</span>
              <span className="text-white font-semibold">
                {Object.values(status?.areas ?? {}).reduce((s, a) => s + a.total, 0)}
              </span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">Standard Areas</span>
              <span className="text-white font-semibold">{areas.length}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">Review Date</span>
              <span className="text-white font-semibold">2026-06-06</span>
            </div>
          </div>
        </div>
      </div>

      {/* Per-standard breakdown */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
          Compliance by Standard Area
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 text-xs uppercase tracking-wider border-b border-gray-800">
                <th className="pb-3 pr-4">Area</th>
                <th className="pb-3 pr-4">Standard</th>
                <th className="pb-3 pr-4 text-right">Total</th>
                <th className="pb-3 pr-4 text-right">Compliant</th>
                <th className="pb-3 pr-4 text-right">Partial</th>
                <th className="pb-3 pr-4 text-right">Planned</th>
                <th className="pb-3 text-right">Score</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {areas.map(a => (
                <tr key={a.area} className="hover:bg-gray-800/50 transition">
                  <td className="py-3 pr-4 font-mono font-bold text-gray-200">{a.area}</td>
                  <td className="py-3 pr-4 text-gray-400">{a.standard}</td>
                  <td className="py-3 pr-4 text-right text-gray-300">{a.total}</td>
                  <td className="py-3 pr-4 text-right text-green-400">{a.compliant}</td>
                  <td className="py-3 pr-4 text-right text-amber-400">{a.partial}</td>
                  <td className="py-3 pr-4 text-right text-blue-400">{a.planned}</td>
                  <td className="py-3 text-right">
                    <div className="flex flex-col items-end gap-1">
                      <span className={`font-bold ${a.score_pct >= 80 ? 'text-green-400' : a.score_pct >= 50 ? 'text-amber-400' : 'text-red-400'}`}>
                        {a.score_pct.toFixed(1)}%
                      </span>
                      <ScoreBar score={a.score_pct} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Requirements table */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
            Requirements Register
          </h2>
          {/* Filters */}
          <div className="flex items-center gap-3">
            <select
              value={filterArea}
              onChange={e => setFilterArea(e.target.value)}
              className="text-xs bg-gray-800 text-gray-300 border border-gray-700 rounded px-2 py-1.5 focus:outline-none"
            >
              <option value="ALL">All Areas</option>
              {areas.map(a => (
                <option key={a.area} value={a.area}>{a.area} — {a.standard}</option>
              ))}
            </select>
            <select
              value={filterStatus}
              onChange={e => setFilterStatus(e.target.value)}
              className="text-xs bg-gray-800 text-gray-300 border border-gray-700 rounded px-2 py-1.5 focus:outline-none"
            >
              <option value="ALL">All Statuses</option>
              {['COMPLIANT', 'PARTIAL', 'PLANNED', 'WAIVED', 'NA'].map(s => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
        </div>

        {report ? (
          <div className="space-y-1">
            {filteredReqs.length === 0 ? (
              <div className="text-center text-gray-600 py-8">No requirements match the current filters.</div>
            ) : filteredReqs.map(r => (
              <div key={r.id} className="border border-gray-800 rounded-lg overflow-hidden">
                {/* Row header */}
                <button
                  className="w-full flex items-center gap-3 px-4 py-3 hover:bg-gray-800/50 transition text-left"
                  onClick={() => setExpandedReq(expandedReq === r.id ? null : r.id)}
                >
                  {expandedReq === r.id
                    ? <ChevronDown className="w-4 h-4 text-gray-500 flex-shrink-0" />
                    : <ChevronRight className="w-4 h-4 text-gray-500 flex-shrink-0" />
                  }
                  <span className="font-mono text-xs text-gray-400 flex-shrink-0 w-24">{r.id}</span>
                  <span className="text-sm text-gray-200 flex-1 min-w-0 truncate">{r.title}</span>
                  <span className="text-xs text-gray-500 flex-shrink-0 mr-3">{r.standard}</span>
                  <StatusBadge status={r.status} />
                  {!r.all_evidence_present && (
                    <span title="Missing evidence"><AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 ml-2" aria-hidden="true" /></span>
                  )}
                </button>

                {/* Expanded panel */}
                {expandedReq === r.id && (
                  <div className="px-4 pb-4 border-t border-gray-800 bg-gray-900/50">
                    {r.notes && (
                      <p className="text-xs text-gray-400 mt-3 italic">{r.notes}</p>
                    )}
                    {r.evidence.length > 0 ? (
                      <div className="mt-3">
                        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Evidence</p>
                        <div className="space-y-1.5">
                          {r.evidence.map((e, i) => (
                            <div key={i} className={`flex items-start gap-2 text-xs rounded px-2 py-1.5 ${
                              e.exists ? 'bg-green-500/5 border border-green-500/20' : 'bg-red-500/5 border border-red-500/20'
                            }`}>
                              <span className={`flex-shrink-0 font-semibold uppercase ${e.exists ? 'text-green-400' : 'text-red-400'}`}>
                                {e.exists ? 'OK' : 'MISSING'}
                              </span>
                              <span className={`font-semibold uppercase tracking-wide flex-shrink-0 ${
                                e.type === 'code' ? 'text-blue-400' : 'text-purple-400'
                              }`}>[{e.type}]</span>
                              <code className="text-gray-300 flex-1">{e.path}</code>
                              <span className="text-gray-500 flex-1">{e.description}</span>
                              <ExternalLink className="w-3 h-3 text-gray-600 flex-shrink-0 mt-0.5" />
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <p className="text-xs text-gray-600 mt-3">No evidence recorded for this requirement.</p>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center text-gray-600 py-8">
            {loading ? 'Loading requirements...' : 'Requirements not available (backend offline — showing status only).'}
          </div>
        )}
      </div>
    </div>
  )
}
