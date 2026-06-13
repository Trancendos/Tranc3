/**
 * The Digital Grid — Visual DAG Builder Types
 * Tyler Towncroft (Lead AI)
 */

export type NodeType =
  | "llm"
  | "http"
  | "code"
  | "condition"
  | "transform"
  | "trigger"
  | "parallel"
  | "loop"
  | "merge"
  | "output"
  | "spark_tool"
  | "vector_search"
  | "ml_predict"
  | "delay"
  | "notify";

export interface NodePort {
  id: string;
  label: string;
}

export interface GridNode {
  id: string;
  type: NodeType;
  label: string;
  x: number;
  y: number;
  config: Record<string, unknown>;
  inputs?: NodePort[];
  outputs?: NodePort[];
}

export interface GridEdge {
  id: string;
  sourceId: string;
  targetId: string;
  sourcePort?: string;
  targetPort?: string;
}

export interface WorkflowDef {
  id?: string;
  name: string;
  description: string;
  nodes: GridNode[];
  edges: GridEdge[];
  created_at?: string;
  updated_at?: string;
}

export interface ExecutionStatus {
  id: string;
  workflow_id: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  node_statuses: Record<string, "pending" | "running" | "done" | "error" | "skipped">;
  outputs: Record<string, unknown>;
  error?: string;
  started_at?: string;
  completed_at?: string;
}

export const NODE_META: Record<
  NodeType,
  { label: string; color: string; icon: string; description: string }
> = {
  trigger: {
    label: "Trigger",
    color: "#7c3aed",
    icon: "⚡",
    description: "Start the workflow",
  },
  llm: { label: "LLM", color: "#2563eb", icon: "🧠", description: "Call an AI language model" },
  http: {
    label: "HTTP",
    color: "#0891b2",
    icon: "🌐",
    description: "Make an HTTP request",
  },
  code: {
    label: "Code",
    color: "#059669",
    icon: "{ }",
    description: "Execute Python code",
  },
  condition: {
    label: "Condition",
    color: "#d97706",
    icon: "⑂",
    description: "Branch on condition",
  },
  transform: {
    label: "Transform",
    color: "#7c3aed",
    icon: "⇌",
    description: "Transform data",
  },
  parallel: {
    label: "Parallel",
    color: "#db2777",
    icon: "⫤",
    description: "Run branches in parallel",
  },
  loop: {
    label: "Loop",
    color: "#b45309",
    icon: "↺",
    description: "Iterate over a list",
  },
  merge: {
    label: "Merge",
    color: "#4f46e5",
    icon: "⊕",
    description: "Merge parallel branches",
  },
  output: {
    label: "Output",
    color: "#16a34a",
    icon: "✓",
    description: "Workflow output",
  },
  spark_tool: {
    label: "Spark Tool",
    color: "#9333ea",
    icon: "✦",
    description: "Call a Spark MCP tool",
  },
  vector_search: {
    label: "Vector Search",
    color: "#0369a1",
    icon: "⊛",
    description: "Semantic vector search",
  },
  ml_predict: {
    label: "ML Predict",
    color: "#1d4ed8",
    icon: "∿",
    description: "Run ML prediction",
  },
  delay: { label: "Delay", color: "#6b7280", icon: "⏱", description: "Wait N seconds" },
  notify: {
    label: "Notify",
    color: "#b91c1c",
    icon: "🔔",
    description: "Send notification",
  },
};
