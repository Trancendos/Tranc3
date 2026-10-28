/**
 * Arcadia — authenticated, read-only entry point.
 *
 * This deliberately does not call the internal catalogue, exchange, bank or
 * messaging workers. A future gateway must authorize user identity and
 * object access before exposing their data to the browser.
 */
import React from 'react'
import { Link } from 'react-router'
import {
  Activity, ArrowUpRight, Bell, Compass, Globe2, MessageCircle,
  Search, ShieldCheck, Store, Users,
} from 'lucide-react'

const AVAILABLE_DESTINATIONS = [
  {
    label: 'Search the platform',
    description: 'Discover existing services and published platform resources.',
    path: '/search',
    icon: Search,
  },
  {
    label: 'Notifications',
    description: 'View the platform notifications already available to your account.',
    path: '/notifications',
    icon: Bell,
  },
  {
    label: 'Platform status',
    description: 'Inspect platform service status in the existing Observatory view.',
    path: '/status',
    icon: Activity,
  },
] as const

const UNCONNECTED_AREAS = [
  {
    id: 'arcadia-community',
    name: 'Community',
    description: 'Discussions, groups and events will appear here after identity and durable storage integration.',
    icon: Users,
  },
  {
    id: 'arcadia-marketplace',
    name: 'Marketplace',
    description: 'Discovery and listings require a reviewed, user-authorised catalogue gateway. Trading is not enabled.',
    icon: Store,
  },
] as const

export default function ArcadiaPage() {
  return (
    <div className="mx-auto max-w-6xl space-y-8 px-4 py-6 sm:px-6 sm:py-9">
      <header className="relative overflow-hidden rounded-2xl border border-border bg-card px-5 py-8 sm:px-8 sm:py-12">
        <div aria-hidden="true" className="pointer-events-none absolute -right-20 -top-24 h-64 w-64 rounded-full bg-blue-500/10 blur-3xl" />
        <div aria-hidden="true" className="pointer-events-none absolute bottom-0 right-28 h-40 w-40 rounded-full bg-violet-500/10 blur-3xl" />
        <div className="relative space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-blue-400">
              <Globe2 size={15} aria-hidden="true" />
              Trancendos Universe
            </span>
            <span className="rounded-full border border-border bg-background/70 px-3 py-1 text-xs text-muted-foreground">
              Early access · Read-only
            </span>
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">Arcadia</h1>
          <p className="max-w-2xl text-sm leading-7 text-muted-foreground sm:text-base">
            Your future home for community, discovery and participation across Trancendos.
            This first stage provides safe navigation while dedicated services are connected and verified.
          </p>
          <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1.5">
              <ShieldCheck size={15} className="text-teal-400" aria-hidden="true" />
              Sign-in required
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Compass size={15} className="text-blue-400" aria-hidden="true" />
              No live marketplace data
            </span>
          </div>
        </div>
      </header>

      <section aria-labelledby="arcadia-spaces">
        <div className="mb-4 space-y-1">
          <h2 id="arcadia-spaces" className="text-lg font-semibold text-foreground">Arcadia spaces</h2>
          <p className="text-sm text-muted-foreground">Planned experiences are visible, but not presented as operational.</p>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          {UNCONNECTED_AREAS.map(({ id, name, description, icon: Icon }) => (
            <article
              key={id}
              data-testid={id}
              className="rounded-xl border border-border bg-card p-5 sm:p-6"
            >
              <div className="flex items-start justify-between gap-3">
                <span className="rounded-xl border border-border bg-background p-3 text-blue-400">
                  <Icon size={22} aria-hidden="true" />
                </span>
                <span className="text-xs font-medium text-muted-foreground">Not connected</span>
              </div>
              <h3 className="mt-5 text-base font-semibold text-foreground">{name}</h3>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">{description}</p>
            </article>
          ))}
        </div>
      </section>

      <section aria-labelledby="arcadia-explore">
        <div className="mb-4 space-y-1">
          <h2 id="arcadia-explore" className="text-lg font-semibold text-foreground">Explore what's available</h2>
          <p className="text-sm text-muted-foreground">Existing Trancendos views — these links do not bypass authentication.</p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {AVAILABLE_DESTINATIONS.map(({ label, description, path, icon: Icon }) => (
            <Link
              key={path}
              to={path}
              className="group rounded-xl border border-border bg-card p-5 transition-colors hover:border-blue-500/60 hover:bg-blue-500/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400"
            >
              <span className="flex items-start justify-between gap-3">
                <Icon className="text-blue-400" size={22} aria-hidden="true" />
                <ArrowUpRight size={16} className="text-muted-foreground group-hover:text-blue-400" aria-hidden="true" />
              </span>
              <span className="mt-5 block text-sm font-semibold text-foreground">{label}</span>
              <span className="mt-2 block text-xs leading-5 text-muted-foreground">{description}</span>
            </Link>
          ))}
        </div>
      </section>

      <aside aria-label="Financial services safeguard" className="flex items-start gap-3 rounded-xl border border-amber-600/30 bg-amber-500/5 p-4">
        <ShieldCheck size={20} className="mt-0.5 shrink-0 text-amber-400" aria-hidden="true" />
        <div className="space-y-1">
          <h2 className="text-sm font-semibold text-foreground">Financial services are separately governed</h2>
          <p className="text-sm leading-6 text-muted-foreground">
            Financial transactions are unavailable in Arcadia. The Royal Bank and Arcadian Exchange
            remain separate services until ledger isolation, identity, authorisation and recovery
            controls receive their own approval. This page cannot submit orders or transfers.
          </p>
        </div>
      </aside>

      <p className="flex items-center gap-2 text-xs text-muted-foreground">
        <MessageCircle size={14} aria-hidden="true" />
        Community messaging and forum content are not connected in this release.
      </p>
    </div>
  )
}
