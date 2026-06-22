import * as React from "react"
import { cn } from "@/lib/utils"

export type WorkflowRunStatus = "pending" | "running" | "completed" | "failed" | "cancelled" | "paused"

export interface WorkflowCardProps {
  workflowId: string
  name: string
  description?: string
  stepCount?: number
  status?: WorkflowRunStatus
  engineUsed?: string
  lastRunAt?: string
  onRun?: (id: string) => void
  onDelete?: (id: string) => void
  variant?: "default" | "fluid" | "glass"
  className?: string
}

const STATUS_STYLES: Record<WorkflowRunStatus, string> = {
  pending:   "bg-muted/60 text-muted-foreground",
  running:   "bg-blue-500/20 text-blue-400 animate-pulse",
  completed: "bg-emerald-500/20 text-emerald-400",
  failed:    "bg-destructive/20 text-destructive",
  cancelled: "bg-muted/60 text-muted-foreground line-through",
  paused:    "bg-amber-500/20 text-amber-400",
}

const STATUS_DOT: Record<WorkflowRunStatus, string> = {
  pending:   "bg-muted-foreground",
  running:   "bg-blue-400 animate-ping",
  completed: "bg-emerald-400",
  failed:    "bg-destructive",
  cancelled: "bg-muted-foreground",
  paused:    "bg-amber-400",
}

const ENGINE_ICONS: Record<string, string> = {
  internal: "⚡",
  n8n:      "🔗",
  prefect:  "🐍",
  temporal: "⏳",
  airflow:  "🌀",
  dagster:  "💎",
  luigi:    "🍄",
  offline:  "📦",
}

export function WorkflowCard({
  workflowId,
  name,
  description,
  stepCount = 0,
  status,
  engineUsed,
  lastRunAt,
  onRun,
  onDelete,
  variant = "fluid",
  className,
}: WorkflowCardProps) {
  return (
    <div
      className={cn(
        "group relative rounded-xl border p-4 transition-all duration-200",
        variant === "fluid"   && "border-primary/20 bg-primary/5 hover:border-primary/40 hover:bg-primary/10",
        variant === "glass"   && "glass border-white/10 hover:border-white/25",
        variant === "default" && "border-border bg-card hover:border-primary/30",
        className,
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="truncate font-semibold text-sm text-foreground">{name}</h3>
          {description && (
            <p className="mt-0.5 text-xs text-muted-foreground line-clamp-2">{description}</p>
          )}
        </div>
        {status && (
          <span
            className={cn(
              "flex shrink-0 items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-semibold",
              STATUS_STYLES[status],
            )}
          >
            <span className={cn("h-1.5 w-1.5 rounded-full", STATUS_DOT[status])} />
            {status}
          </span>
        )}
      </div>

      {/* Meta */}
      <div className="mt-3 flex flex-wrap items-center gap-3 text-[10px] text-muted-foreground">
        <span>{stepCount} step{stepCount !== 1 ? "s" : ""}</span>
        {engineUsed && (
          <span className="flex items-center gap-1">
            {ENGINE_ICONS[engineUsed] ?? "🔧"} {engineUsed}
          </span>
        )}
        {lastRunAt && <span>Last run: {new Date(lastRunAt).toLocaleString()}</span>}
        <span className="font-mono text-[9px] opacity-50">{workflowId.slice(0, 8)}</span>
      </div>

      {/* Actions */}
      <div className="mt-3 flex gap-2 opacity-0 transition-opacity duration-150 group-hover:opacity-100">
        {onRun && (
          <button
            onClick={() => onRun(workflowId)}
            className="rounded-lg border border-primary/30 bg-primary/10 px-3 py-1 text-[11px] font-semibold text-primary hover:bg-primary/20 transition-colors"
          >
            ▶ Run
          </button>
        )}
        {onDelete && (
          <button
            onClick={() => onDelete(workflowId)}
            className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-1 text-[11px] font-semibold text-destructive hover:bg-destructive/20 transition-colors"
          >
            ✕ Delete
          </button>
        )}
      </div>
    </div>
  )
}
