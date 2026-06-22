import type { Meta, StoryObj } from "@storybook/react"
import * as React from "react"
import { WorkflowCard } from "@/components/shadcn/workflow-card"
import { WorkflowEngineStatus, type EngineStatusData } from "@/components/shadcn/workflow-engine-status"

// ── WorkflowCard stories ──────────────────────────────────────────────────────

const wfMeta: Meta<typeof WorkflowCard> = {
  title: "The Digital Grid/WorkflowCard",
  component: WorkflowCard,
  args: {
    workflowId: "abc12345-0000-0000-0000-000000000001",
    name: "Daily Report Pipeline",
    description: "Fetches data from 3 sources, transforms, and emails the result.",
    stepCount: 7,
    variant: "fluid",
  },
}
export default wfMeta

type WfStory = StoryObj<typeof WorkflowCard>

export const Default: WfStory = {}

export const Running: WfStory = {
  args: { status: "running", engineUsed: "n8n", lastRunAt: new Date().toISOString() },
}

export const Completed: WfStory = {
  args: { status: "completed", engineUsed: "internal", lastRunAt: new Date(Date.now() - 60000).toISOString() },
}

export const Failed: WfStory = {
  args: { status: "failed", engineUsed: "prefect", lastRunAt: new Date(Date.now() - 3600000).toISOString() },
}

export const GlassVariant: WfStory = {
  args: { variant: "glass", status: "paused", engineUsed: "temporal" },
  decorators: [
    (Story) => (
      <div className="bg-gradient-to-br from-violet-900 to-indigo-950 min-h-screen p-8">
        <Story />
      </div>
    ),
  ],
}

export const WithActions: WfStory = {
  args: {
    status: "completed",
    engineUsed: "airflow",
    onRun: (id) => alert(`Run: ${id}`),
    onDelete: (id) => alert(`Delete: ${id}`),
  },
}

// ── WorkflowEngineStatus stories ──────────────────────────────────────────────

const MOCK_ENGINES: EngineStatusData[] = [
  { engine: "internal",  healthy: true,  pheromone: 0.95, requests_in_window: 12,  threshold: 999999, blocked: false },
  { engine: "n8n",       healthy: true,  pheromone: 0.82, requests_in_window: 234, threshold: 500,    blocked: false },
  { engine: "prefect",   healthy: true,  pheromone: 0.74, requests_in_window: 89,  threshold: 500,    blocked: false },
  { engine: "temporal",  healthy: true,  pheromone: 0.68, requests_in_window: 45,  threshold: 500,    blocked: false },
  { engine: "airflow",   healthy: false, pheromone: 0.35, requests_in_window: 0,   threshold: 500,    blocked: false },
  { engine: "dagster",   healthy: true,  pheromone: 0.60, requests_in_window: 501, threshold: 500,    blocked: true  },
  { engine: "luigi",     healthy: true,  pheromone: 0.50, requests_in_window: 150, threshold: 1000,   blocked: false },
  { engine: "offline",   healthy: true,  pheromone: 0.10, requests_in_window: 0,   threshold: 999999, blocked: false },
]

export const EngineStatusPanel: StoryObj = {
  render: () => <WorkflowEngineStatus engines={MOCK_ENGINES} variant="fluid" className="max-w-sm" />,
}

export const EngineStatusGlass: StoryObj = {
  render: () => (
    <div className="bg-gradient-to-br from-slate-900 to-violet-950 min-h-screen p-8">
      <WorkflowEngineStatus engines={MOCK_ENGINES} variant="glass" className="max-w-sm" />
    </div>
  ),
}

export const FullDashboard: StoryObj = {
  render: () => (
    <div className="p-6 space-y-6 max-w-4xl">
      <h2 className="text-lg font-bold text-foreground">The Digital Grid — Tyler Towncroft</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {[
          { name: "Daily ETL Pipeline",      desc: "Transforms sales data nightly",        steps: 5, status: "completed" as const, engine: "n8n" },
          { name: "User Sync Flow",           desc: "Syncs users from 4 identity sources",  steps: 3, status: "running"   as const, engine: "internal" },
          { name: "Invoice Generator",        desc: "Creates invoices from order events",   steps: 8, status: "failed"    as const, engine: "prefect" },
          { name: "Compliance Audit",         desc: "Scans for Magna Carta violations",     steps: 12, status: "paused"   as const, engine: "airflow" },
          { name: "Observatory Rollup",       desc: "Aggregates metrics from all workers",  steps: 6, status: "pending"  as const, engine: undefined },
          { name: "AI Model Warmup",          desc: "Pre-loads Ollama models on schedule",  steps: 2, status: "completed" as const, engine: "luigi" },
        ].map((wf, i) => (
          <WorkflowCard
            key={i}
            workflowId={`00000000-0000-0000-0000-00000000000${i + 1}`}
            name={wf.name}
            description={wf.desc}
            stepCount={wf.steps}
            status={wf.status}
            engineUsed={wf.engine}
            lastRunAt={new Date(Date.now() - i * 3600000).toISOString()}
            variant="fluid"
          />
        ))}
      </div>
      <WorkflowEngineStatus engines={MOCK_ENGINES} variant="fluid" />
    </div>
  ),
}
