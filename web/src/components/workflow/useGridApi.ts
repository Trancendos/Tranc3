/** Digital Grid REST hook for the Tranc3 monolith /grid API. */
import { useCallback, useState } from "react";
import type { WorkflowDef, ExecutionStatus } from "./types";
import {
  encodeWorkflow,
  decodeWorkflow,
  decodeWorkflowList,
  decodeSaveResponse,
  decodeExecution,
  decodeCancellation,
} from "./gridContract";

const GRID_BASE = "/grid";

export function useGridApi() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const request = useCallback(
    async <T>(path: string, decode: (raw: unknown) => T, options?: RequestInit): Promise<T | null> => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`${GRID_BASE}${path}`, {
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          ...options,
        });
        if (!res.ok) {
          // Avoid echoing untrusted response bodies: they can contain node payloads or secrets.
          throw new Error(`Digital Grid API request failed (HTTP ${res.status})`);
        }
        return decode(await res.json());
      } catch (e) {
        setError(e instanceof Error ? e.message : "Digital Grid API request failed");
        return null;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const listWorkflows = useCallback(
    () => request<WorkflowDef[]>("/workflows", decodeWorkflowList),
    [request]
  );

  const getWorkflow = useCallback(
    (id: string) => request<WorkflowDef>(`/workflows/${encodeURIComponent(id)}`, decodeWorkflow),
    [request]
  );

  const saveWorkflow = useCallback(
    (wf: WorkflowDef) => {
      try {
        const body = JSON.stringify(encodeWorkflow(wf));
        return request<{ id: string }>("/workflows", decodeSaveResponse, { method: "POST", body });
      } catch (e) {
        setError(e instanceof Error ? e.message : "Invalid workflow");
        return Promise.resolve(null);
      }
    },
    [request]
  );

  const runWorkflow = useCallback(
    (id: string, inputs: Record<string, unknown> = {}) =>
      request<ExecutionStatus>(`/workflows/${encodeURIComponent(id)}/run`, decodeExecution, {
        method: "POST",
        // One FastAPI Body parameter: send the inputs dictionary as the body itself.
        body: JSON.stringify(inputs),
      }),
    [request]
  );

  const getExecution = useCallback(
    (id: string) => request<ExecutionStatus>(`/executions/${encodeURIComponent(id)}`, decodeExecution),
    [request]
  );

  const cancelExecution = useCallback(
    (id: string) => request<{ cancelled: boolean }>(
      `/executions/${encodeURIComponent(id)}/cancel`,
      decodeCancellation,
      { method: "POST" }
    ),
    [request]
  );

  const gridStatus = useCallback(
    () => request<{
      registered_workflows: number;
      active_executions: number;
      node_types?: string[];
    }>("/status", (raw) => {
      if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
        throw new Error("Invalid Digital Grid status response");
      }
      return raw as {
        registered_workflows: number;
        active_executions: number;
        node_types?: string[];
      };
    }),
    [request]
  );

  return {
    loading,
    error,
    listWorkflows,
    getWorkflow,
    saveWorkflow,
    runWorkflow,
    getExecution,
    cancelExecution,
    gridStatus,
  };
}
