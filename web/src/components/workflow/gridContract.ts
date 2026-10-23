/**
 * Digital Grid editor ⇆ Tranc3 monolith API v1 contract.
 * The editor stores node arrays and screen coordinates; src/workflow/builder.py
 * accepts an ID-indexed NodeConfig dictionary and from/to graph edges.
 *
 * Do not silently coerce unsupported steps or fabricate execution success.
 */
import type { ExecutionStatus, GridEdge, GridNode, NodeType, WorkflowDef } from "./types";

const NODE_TO_SERVER: Partial<Record<NodeType, string>> = {
  trigger: "TRIGGER",
  llm: "LLM",
  http: "HTTP_REQUEST",
  code: "CODE_EXEC",
  condition: "CONDITION",
  transform: "TRANSFORM",
  parallel: "PARALLEL",
  loop: "LOOP",
  merge: "MERGE",
  output: "OUTPUT",
  spark_tool: "SPARK_TOOL",
  skill_call: "SKILL_CALL",
  vector_search: "VECTOR_SEARCH",
  ml_predict: "ML_PREDICT",
};
const SERVER_TO_NODE = Object.fromEntries(
  Object.entries(NODE_TO_SERVER).map(([key, value]) => [value, key]),
) as Record<string, NodeType>;

interface WireNode {
  id: string;
  type: string;
  name: string;
  config: Record<string, unknown>;
  inputs: string[];
  outputs: string[];
  timeout_sec: number;
  retry_count: number;
}
export interface WireWorkflow {
  id?: string;
  name: string;
  description: string;
  version: string;
  nodes: Record<string, WireNode>;
  edges: { from: string; to: string; label: string }[];
  triggers: string[];
  metadata: Record<string, unknown>;
}

function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Invalid Digital Grid API object");
  }
  return value as Record<string, unknown>;
}

function optionalObject(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function requiredString(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`Invalid Digital Grid ${label}`);
  }
  return value;
}

function assertAcyclic(nodeIds: string[], edges: GridEdge[]): void {
  const degree = new Map(nodeIds.map(id => [id, 0]));
  const outgoing = new Map(nodeIds.map(id => [id, [] as string[]]));
  for (const edge of edges) {
    if (!degree.has(edge.sourceId) || !degree.has(edge.targetId)) {
      throw new Error("Workflow edge refers to an unknown node");
    }
    degree.set(edge.targetId, degree.get(edge.targetId)! + 1);
    outgoing.get(edge.sourceId)!.push(edge.targetId);
  }
  const ready = nodeIds.filter(id => degree.get(id) === 0);
  let visited = 0;
  while (ready.length) {
    const id = ready.shift()!;
    visited++;
    for (const next of outgoing.get(id)!) {
      const remaining = degree.get(next)! - 1;
      degree.set(next, remaining);
      if (remaining === 0) ready.push(next);
    }
  }
  if (visited !== nodeIds.length) throw new Error("Workflow graph contains a cycle");
}

export function isSupportedNodeType(type: NodeType): boolean {
  return Object.prototype.hasOwnProperty.call(NODE_TO_SERVER, type);
}

export function encodeWorkflow(workflow: WorkflowDef): WireWorkflow {
  requiredString(workflow.name, "name");
  if (!workflow.nodes.length) throw new Error("Workflow must contain at least one node");
  const ids = workflow.nodes.map(node => requiredString(node.id, "node ID"));
  if (new Set(ids).size !== ids.length) throw new Error("Duplicate workflow node ID");
  assertAcyclic(ids, workflow.edges);
  const nodes: Record<string, WireNode> = Object.create(null);
  const layout: Record<string, unknown> = Object.create(null);
  for (const node of workflow.nodes) {
    const serverType = Object.prototype.hasOwnProperty.call(NODE_TO_SERVER, node.type)
      ? NODE_TO_SERVER[node.type] : undefined;
    if (!serverType) throw new Error(`Node type "${node.type}" is not supported by the current workflow engine`);
    nodes[node.id] = {
      id: node.id,
      type: serverType,
      name: node.label,
      config: node.config,
      inputs: workflow.edges.filter(e => e.targetId === node.id).map(e => e.sourceId),
      outputs: workflow.edges.filter(e => e.sourceId === node.id).map(e => e.targetId),
      timeout_sec: 30,
      retry_count: 3,
    };
    layout[node.id] = {
      x: node.x,
      y: node.y,
      ...(node.inputs ? { inputs: node.inputs } : {}),
      ...(node.outputs ? { outputs: node.outputs } : {}),
    };
  }
  return {
    ...(workflow.id ? { id: workflow.id } : {}),
    name: workflow.name,
    description: workflow.description,
    version: workflow.version || "1.0",
    nodes,
    edges: workflow.edges.map(e => ({ from: e.sourceId, to: e.targetId, label: "default" })),
    triggers: workflow.triggers || [],
    metadata: {
      ...(workflow.metadata || {}),
      grid_ui: {
        layout,
        edges: workflow.edges.map(e => ({
          id: e.id,
          ...(e.sourcePort ? { sourcePort: e.sourcePort } : {}),
          ...(e.targetPort ? { targetPort: e.targetPort } : {}),
        })),
        ...(workflow.created_at ? { created_at: workflow.created_at } : {}),
        ...(workflow.updated_at ? { updated_at: workflow.updated_at } : {}),
      },
    },
  };
}

export function decodeWorkflow(value: unknown): WorkflowDef {
  const wire = object(value);
  const id = typeof wire.id === "string" ? wire.id : undefined;
  const name = requiredString(wire.name, "workflow name");
  const rawNodes = object(wire.nodes);
  if (!Array.isArray(wire.edges)) throw new Error("Invalid Digital Grid workflow edges");
  const metadata = optionalObject(wire.metadata);
  const ui = optionalObject(metadata.grid_ui);
  const layout = optionalObject(ui.layout);
  const nodes: GridNode[] = Object.entries(rawNodes).map(([nodeId, value], index) => {
    const entry = object(value);
    const type = SERVER_TO_NODE[String(entry.type)];
    if (!type) throw new Error(`Unsupported backend node type: ${String(entry.type)}`);
    const positioning = optionalObject(layout[nodeId]);
    return {
      id: nodeId,
      type,
      label: typeof entry.name === "string" ? entry.name : nodeId,
      config: optionalObject(entry.config),
      x: typeof positioning.x === "number" ? positioning.x : index * 180 + 40,
      y: typeof positioning.y === "number" ? positioning.y : 40,
      ...(Array.isArray(positioning.inputs) ? { inputs: positioning.inputs as GridNode["inputs"] } : {}),
      ...(Array.isArray(positioning.outputs) ? { outputs: positioning.outputs as GridNode["outputs"] } : {}),
    };
  });
  const uiEdges = Array.isArray(ui.edges) ? ui.edges : [];
  const edges: GridEdge[] = wire.edges.map((edge, index) => {
    const e = object(edge);
    const display = optionalObject(uiEdges[index]);
    return {
      id: typeof display.id === "string" ? display.id : `edge-${index}`,
      sourceId: requiredString(e.from, "edge source"),
      targetId: requiredString(e.to, "edge target"),
      ...(typeof display.sourcePort === "string" ? { sourcePort: display.sourcePort } : {}),
      ...(typeof display.targetPort === "string" ? { targetPort: display.targetPort } : {}),
    };
  });
  assertAcyclic(nodes.map(node => node.id), edges);
  return {
    ...(id ? { id } : {}),
    name,
    description: typeof wire.description === "string" ? wire.description : "",
    version: typeof wire.version === "string" ? wire.version : "1.0",
    nodes,
    edges,
    triggers: Array.isArray(wire.triggers) ? wire.triggers as string[] : [],
    metadata,
    ...(typeof ui.created_at === "string" ? { created_at: ui.created_at } : {}),
    ...(typeof ui.updated_at === "string" ? { updated_at: ui.updated_at } : {}),
  };
}

export function decodeWorkflowList(value: unknown): WorkflowDef[] {
  if (!Array.isArray(value)) throw new Error("Invalid Digital Grid workflow list");
  return value.map(decodeWorkflow);
}

export function decodeSaveResponse(value: unknown): { id: string } {
  const response = object(value);
  return { id: requiredString(response.id ?? response.registered, "saved workflow ID") };
}

export function decodeExecution(value: unknown): ExecutionStatus {
  const response = object(value);
  const id = requiredString(response.id ?? response.execution_id, "execution ID");
  const status = requiredString(response.status, "execution status");
  if (!["pending", "running", "completed", "failed", "cancelled"].includes(status)) {
    throw new Error(`Unsupported Digital Grid execution status: ${status}`);
  }
  const rawStates = optionalObject(response.node_statuses);
  const node_statuses: ExecutionStatus["node_statuses"] = {};
  for (const [nodeId, state] of Object.entries(rawStates)) {
    const normalised = state === "completed" ? "done" : state === "failed" ? "error" : state;
    if (["pending", "running", "done", "error", "skipped"].includes(String(normalised))) {
      node_statuses[nodeId] = normalised as ExecutionStatus["node_statuses"][string];
    }
  }
  return {
    id,
    workflow_id: typeof response.workflow_id === "string" ? response.workflow_id : "",
    status: status as ExecutionStatus["status"],
    node_statuses,
    outputs: optionalObject(response.outputs),
    ...(typeof response.error === "string" ? { error: response.error } : {}),
  };
}

export function decodeCancellation(value: unknown): { cancelled: boolean } {
  const cancelled = object(value).cancelled;
  return { cancelled: typeof cancelled === "string" ? cancelled.length > 0 : cancelled === true };
}
