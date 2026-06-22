import * as React from "react"
import { cn } from "@/lib/utils"

export interface EngineStatusData {
  engine: string
  healthy: boolean
  pheromone: number       // 0–1
  requests_in_window: number
  threshold: number
  blocked: boolean
}

export interface WorkflowEngineStatusProps {
  engines: EngineStatusData[]
  variant?: "default" | "fluid" | "glass"
  className?: string
}

const ENGINE_META: Record<string, { icon: string; label: string; tier: number }> = {
  internal: { icon: "⚡", label: "Internal DAG",    tier: 1 },
  n8n:      { icon: "🔗", label: "n8n",             tier: 2 },
  prefect:  { icon: "🐍", label: "Prefect",         tier: 3 },
  temporal: { icon: "⏳", label: "Temporal",        tier: 4 },
  airflow:  { icon: "🌀", label: "Airflow",         tier: 5 },
  dagster:  { icon: "💎", label: "Dagster",         tier: 6 },
  luigi:    { icon: "🍄", label: "Luigi",           tier: 7 },
  offline:  { icon: "📦", label: "Offline Stub",    tier: 8 },
}

function PheromoneBar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color =
    value > 0.7 ? "bg-emerald-500" :
    value > 0.4 ? "bg-amber-500" :
    "bg-destructive"
  return (
    <div className="flex items-center gap-2">
      <div className="relative h-1.5 flex-1 rounded-full bg-muted/40 overflow-hidden">
        <div
          className={cn("absolute inset-y-0 left-0 rounded-full transition-all duration-500", color)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[9px] font-mono w-7 text-right text-muted-foreground">{pct}%</span>
    </div>
  )
}

function ThresholdBar({ current, max }: { current: number; max: number }) {
  const pct = max > 0 ? Math.min(100, Math.round((current / max) * 100)) : 0
  const color =
    pct > 85 ? "bg-destructive" :
    pct > 60 ? "bg-amber-500" :
    "bg-blue-500"
  return (
    <div className="flex items-center gap-2">
      <div className="relative h-1.5 flex-1 rounded-full bg-muted/40 overflow-hidden">
        <div
          className={cn("absolute inset-y-0 left-0 rounded-full transition-all duration-500", color)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[9px] font-mono w-12 text-right text-muted-foreground">
        {current}/{max}
      </span>
    </div>
  )
}

export function WorkflowEngineStatus({
  engines,
  variant = "fluid",
  className,
}: WorkflowEngineStatusProps) {
  return (
    <div className={cn("space-y-2", className)}>
      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
        Engine Status — 8-Tier Adaptive Router
      </p>
      {engines.map((e) => {
        const meta = ENGINE_META[e.engine] ?? { icon: "🔧", label: e.engine, tier: 0 }
        return (
          <div
            key={e.engine}
            className={cn(
              "rounded-xl border p-3 transition-all duration-200",
              variant === "fluid"   && "border-primary/15 bg-primary/5",
              variant === "glass"   && "glass border-white/10",
              variant === "default" && "border-border bg-card",
              e.blocked && "opacity-50",
            )}
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className="text-base">{meta.icon}</span>
                <div>
                  <span className="text-xs font-semibold text-foreground">
                    Tier {meta.tier}: {meta.label}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-1.5">
                {e.blocked && (
                  <span className="rounded-full bg-destructive/20 px-1.5 py-0.5 text-[9px] font-bold text-destructive">
                    BLOCKED
                  </span>
                )}
                <span
                  className={cn(
                    "h-2 w-2 rounded-full",
                    e.healthy ? "bg-emerald-400" : "bg-destructive",
                  )}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-[9px] text-muted-foreground">
                <span>Pheromone (ACO weight)</span>
              </div>
              <PheromoneBar value={e.pheromone} />

              <div className="flex items-center justify-between text-[9px] text-muted-foreground mt-1">
                <span>Requests / window</span>
              </div>
              <ThresholdBar current={e.requests_in_window} max={e.threshold} />
            </div>
          </div>
        )
      })}
    </div>
  )
}
