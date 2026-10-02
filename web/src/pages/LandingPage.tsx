import React from 'react'
import { useNavigate } from 'react-router'

const STATS = [
  { value: '43', label: 'Connected Services' },
  { value: '£0', label: 'External API Cost' },
  { value: '5-tier', label: 'AI Fallback Chain' },
  { value: '100%', label: 'Self-Hosted' },
]

const PILLARS = [
  {
    icon: '⚡',
    name: 'The Spark',
    tag: 'AI Tool Registry',
    desc: 'MCP server exposing JSON-RPC 2.0 tool registry with semantic RAG-based tool selection.',
  },
  {
    icon: '🧠',
    name: 'Luminous',
    tag: 'AI Orchestration',
    desc: 'Bio-neural consciousness engine with IIT processing and neuromorphic architecture.',
  },
  {
    icon: '⬡',
    name: 'The Digital Grid',
    tag: 'Workflow Engine',
    desc: 'Visual DAG builder with topological BFS executor and parallel layer processing.',
  },
  {
    icon: '🔒',
    name: 'The Void',
    tag: 'Secrets Vault',
    desc: 'AES-GCM encrypted secrets vault with PBKDF2 key derivation and audit trail.',
  },
  {
    icon: '🏛️',
    name: 'Infinity',
    tag: 'SSO & Auth',
    desc: 'OAuth2/OIDC identity hub — one account, all 43 services, zero password reuse.',
  },
  {
    icon: '🔭',
    name: 'The Observatory',
    tag: 'Audit & Metrics',
    desc: 'Immutable audit log for every action across the platform, with Prometheus metrics.',
  },
]

export default function LandingPage() {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-gray-950 text-white overflow-x-hidden">
      <style>{`
        @keyframes gradient-drift {
          0% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
          100% { background-position: 0% 50%; }
        }
        @keyframes float-up {
          0%, 100% { transform: translateY(0px) rotate(0deg); opacity: 0.15; }
          50% { transform: translateY(-30px) rotate(180deg); opacity: 0.3; }
        }
        .hero-gradient {
          background: linear-gradient(270deg, #0f172a, #1e3a8a, #1d4ed8, #0ea5e9, #7c3aed, #1e3a8a, #0f172a);
          background-size: 400% 400%;
          animation: gradient-drift 14s ease infinite;
        }
        .particle {
          position: absolute;
          width: 4px;
          height: 4px;
          border-radius: 50%;
          background: rgba(147,197,253,0.4);
        }
        .p1 { top: 15%; left: 10%; animation: float-up 7s ease-in-out infinite; }
        .p2 { top: 60%; left: 25%; animation: float-up 9s ease-in-out 1s infinite; }
        .p3 { top: 30%; left: 75%; animation: float-up 6s ease-in-out 2s infinite; }
        .p4 { top: 75%; left: 60%; animation: float-up 8s ease-in-out 3s infinite; }
        .p5 { top: 45%; left: 45%; animation: float-up 11s ease-in-out 0.5s infinite; }
        .p6 { top: 20%; left: 85%; animation: float-up 10s ease-in-out 1.5s infinite; }
        @keyframes fade-in-up {
          from { opacity: 0; transform: translateY(24px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        .anim-in { animation: fade-in-up 0.7s ease forwards; }
        .anim-in-2 { animation: fade-in-up 0.7s 0.15s ease both; }
        .anim-in-3 { animation: fade-in-up 0.7s 0.3s ease both; }
      `}</style>

      {/* Hero */}
      <section className="hero-gradient relative min-h-screen flex flex-col items-center justify-center text-center px-6 py-24">
        {/* Particles */}
        <div className="particle p1" /><div className="particle p2" /><div className="particle p3" />
        <div className="particle p4" /><div className="particle p5" /><div className="particle p6" />

        {/* Nav */}
        <nav className="absolute top-0 left-0 right-0 flex items-center justify-between px-8 py-5 z-20">
          <div className="flex items-center gap-2">
            <span className="text-2xl">⚡</span>
            <span className="font-black text-xl tracking-tight">Trancendos</span>
          </div>
          <button
            onClick={() => navigate('/login')}
            className="text-sm font-medium text-blue-300 hover:text-white transition-colors border border-blue-700/50 hover:border-blue-500 rounded-lg px-4 py-1.5"
          >
            Sign In
          </button>
        </nav>

        <div className="relative z-10 max-w-4xl mx-auto">
          <div className="anim-in inline-flex items-center gap-2 bg-blue-950/60 border border-blue-700/40 rounded-full px-4 py-1.5 text-xs text-blue-300 mb-8">
            <span className="w-1.5 h-1.5 rounded-full bg-green-400 inline-block" style={{ boxShadow: '0 0 6px #4ade80' }} />
            Zero-cost self-hosted architecture · 43 services
          </div>

          <h1
            className="anim-in-2 text-6xl lg:text-8xl font-black tracking-tight mb-6 leading-none"
            style={{
              background: 'linear-gradient(135deg, #fff 20%, #93c5fd 60%, #c4b5fd 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
            }}
          >
            Trancendos
          </h1>

          <p className="anim-in-3 text-xl lg:text-2xl text-blue-200 font-light mb-4">
            The Conscious AI Platform
          </p>
          <p className="anim-in-3 text-gray-400 max-w-2xl mx-auto mb-12 text-sm lg:text-base leading-relaxed">
            A fully self-hosted, zero-vendor-cost AI infrastructure platform.
            43 interconnected services spanning AI orchestration, identity, financials, security, creativity and governance — all yours.
          </p>

          <div className="anim-in-3 flex flex-col sm:flex-row gap-4 justify-center mb-16">
            <button
              onClick={() => navigate('/login')}
              className="group relative px-8 py-3.5 rounded-xl font-semibold text-white overflow-hidden"
              style={{
                background: 'linear-gradient(135deg, #1d4ed8, #7c3aed)',
                boxShadow: '0 0 30px rgba(37,99,235,0.4)',
              }}
            >
              <span className="relative z-10">Get Started →</span>
              <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity"
                style={{ background: 'linear-gradient(135deg, #2563eb, #8b5cf6)' }} />
            </button>
            <button
              onClick={() => navigate('/login')}
              className="px-8 py-3.5 rounded-xl font-semibold border border-gray-700 hover:border-gray-500 text-gray-300 hover:text-white transition-colors"
            >
              Sign In
            </button>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 max-w-2xl mx-auto">
            {STATS.map(s => (
              <div key={s.label} className="bg-gray-950/60 border border-gray-800 rounded-xl p-4 text-center backdrop-blur">
                <div className="text-3xl font-black text-blue-400 mb-1">{s.value}</div>
                <div className="text-xs text-gray-500">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Zero Cost callout */}
      <section className="py-16 px-6 border-y border-gray-800 bg-gray-900/40">
        <div className="max-w-4xl mx-auto text-center">
          <div className="inline-flex items-center gap-3 bg-green-950/50 border border-green-800/50 rounded-2xl px-8 py-6">
            <span className="text-4xl">🏗️</span>
            <div className="text-left">
              <div className="font-bold text-green-400 text-lg">Zero Cost Architecture</div>
              <div className="text-gray-400 text-sm mt-1">
                No Cloudflare billing. No OpenAI API costs. No SaaS subscriptions.
                FastAPI + SQLite + Ollama running on your own hardware — permanently free.
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Core services */}
      <section className="py-20 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-12">
            <h2 className="text-3xl lg:text-4xl font-bold mb-4">
              Built from the ground up
            </h2>
            <p className="text-gray-400 max-w-xl mx-auto text-sm">
              Every service purpose-built, named, and assigned a Lead AI — no off-the-shelf SaaS subscriptions.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {PILLARS.map(p => (
              <div
                key={p.name}
                className="group bg-gray-900/60 border border-gray-800 hover:border-blue-700/50 rounded-xl p-6 transition-all duration-200 hover:bg-gray-900"
              >
                <div className="text-3xl mb-3">{p.icon}</div>
                <div className="font-bold text-white mb-0.5">{p.name}</div>
                <div className="text-xs text-blue-400 mb-3">{p.tag}</div>
                <p className="text-sm text-gray-500 group-hover:text-gray-400 transition-colors leading-relaxed">
                  {p.desc}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-24 px-6 text-center">
        <div
          className="max-w-2xl mx-auto rounded-3xl p-12 border border-blue-800/30"
          style={{
            background: 'radial-gradient(ellipse at 50% 0%, rgba(37,99,235,0.2) 0%, transparent 70%), #0f172a',
          }}
        >
          <h2 className="text-3xl lg:text-4xl font-bold mb-4">Ready to take control?</h2>
          <p className="text-gray-400 mb-8 text-sm">
            Join the platform. One account. Every service. No subscriptions.
          </p>
          <button
            onClick={() => navigate('/login')}
            className="px-10 py-4 rounded-xl font-bold text-white text-lg"
            style={{
              background: 'linear-gradient(135deg, #1d4ed8, #7c3aed)',
              boxShadow: '0 0 40px rgba(37,99,235,0.35)',
            }}
          >
            Get Started — It's Free →
          </button>
        </div>
      </section>

      <footer className="py-8 text-center text-gray-700 text-xs border-t border-gray-900">
        Trancendos Platform · Self-hosted · Zero vendor lock-in
      </footer>
    </div>
  )
}
