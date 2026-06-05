import React, { useState } from 'react'
import { Shield, Users, Key, Database, Activity, ChevronRight, AlertTriangle } from 'lucide-react'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface AdminSection {
  id: string
  title: string
  description: string
  icon: React.ReactNode
  color: string
  href?: string
}

const SECTIONS: AdminSection[] = [
  {
    id: 'users',
    title: 'User Management',
    description: 'Manage users, roles, and permissions across Infinity.',
    icon: <Users size={20} aria-hidden="true" />,
    color: 'border-indigo-700 hover:border-indigo-500',
    href: `${API}/admin/users`,
  },
  {
    id: 'auth',
    title: 'Auth & Sessions',
    description: 'Active sessions, OAuth clients, MFA policies.',
    icon: <Key size={20} aria-hidden="true" />,
    color: 'border-blue-700 hover:border-blue-500',
    href: `${API}/admin/auth`,
  },
  {
    id: 'database',
    title: 'Database',
    description: 'SQLite worker databases, migration status, Alembic history.',
    icon: <Database size={20} aria-hidden="true" />,
    color: 'border-purple-700 hover:border-purple-500',
    href: `${API}/admin/db`,
  },
  {
    id: 'observability',
    title: 'Observability',
    description: 'Prometheus metrics, Grafana dashboards, Loki logs.',
    icon: <Activity size={20} aria-hidden="true" />,
    color: 'border-green-700 hover:border-green-500',
    href: 'http://localhost:3000',
  },
  {
    id: 'security',
    title: 'Security',
    description: 'Cryptex threat intel, Zero Trust IAM policies, CVE registry.',
    icon: <Shield size={20} aria-hidden="true" />,
    color: 'border-yellow-700 hover:border-yellow-500',
  },
]

interface SystemStat {
  label: string
  value: string
  color?: string
}

export default function AdminPage() {
  const [stats] = useState<SystemStat[]>([
    { label: 'Platform', value: 'Trancendos v1' },
    { label: 'Architecture', value: 'Zero-Cost Self-Hosted' },
    { label: 'Workers', value: '38 services (P0–P3)' },
    { label: 'CF Workers', value: '26 (migrating to self-hosted)' },
    { label: 'AI Providers', value: '13 (cloud) + Ollama (local)' },
    { label: 'Daily AI Capacity', value: '~18,048 requests' },
    { label: 'Storage Tiers', value: 'R2 + B2 + Oracle + IPFS' },
    { label: 'CI/CD', value: 'Forgejo + Woodpecker CI' },
  ])

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Shield size={22} aria-hidden="true" className="text-indigo-400" />
          Admin
        </h1>
        <p className="text-gray-400 text-sm mt-1">Infinity Admin — system configuration and management</p>
      </div>

      {/* Warning */}
      <div
        role="note"
        className="flex items-start gap-3 bg-yellow-900/20 border border-yellow-700 rounded-lg p-4 mb-6"
      >
        <AlertTriangle size={16} aria-hidden="true" className="text-yellow-400 mt-0.5 flex-shrink-0" />
        <p className="text-yellow-300 text-sm">
          This admin panel connects to the running backend. Most operations require the full Docker Compose
          stack or individual workers to be running locally.
        </p>
      </div>

      {/* System stats */}
      <div className="bg-gray-900 border border-gray-700 rounded-lg p-5 mb-6">
        <h2 className="text-white font-semibold mb-4">Platform Overview</h2>
        <dl className="grid grid-cols-2 md:grid-cols-4 gap-y-3 gap-x-6">
          {stats.map((s) => (
            <div key={s.label}>
              <dt className="text-gray-500 text-xs">{s.label}</dt>
              <dd className={`text-sm font-medium ${s.color ?? 'text-gray-200'}`}>{s.value}</dd>
            </div>
          ))}
        </dl>
      </div>

      {/* Admin sections */}
      <h2 className="text-white font-semibold mb-3">Management</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {SECTIONS.map((sec) =>
          sec.href ? (
            <a
              key={sec.id}
              href={sec.href}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={`${sec.title} — opens in new tab`}
              className={`bg-gray-900 border rounded-lg p-5 transition-colors ${sec.color} focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400`}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-indigo-400">{sec.icon}</span>
                  <div>
                    <p className="text-white font-medium text-sm">{sec.title}</p>
                    <p className="text-gray-500 text-xs mt-0.5">{sec.description}</p>
                  </div>
                </div>
                <ChevronRight size={16} aria-hidden="true" className="text-gray-600 flex-shrink-0 mt-1" />
              </div>
            </a>
          ) : (
            <div
              key={sec.id}
              aria-label={sec.title}
              className={`bg-gray-900 border rounded-lg p-5 opacity-60 ${sec.color}`}
            >
              <div className="flex items-start">
                <div className="flex items-center gap-3">
                  <span className="text-indigo-400">{sec.icon}</span>
                  <div>
                    <p className="text-white font-medium text-sm">{sec.title}</p>
                    <p className="text-gray-500 text-xs mt-0.5">{sec.description}</p>
                  </div>
                </div>
              </div>
              <p className="text-gray-700 text-xs mt-2">Coming soon — service not yet implemented</p>
            </div>
          )
        )}
      </div>
    </div>
  )
}
