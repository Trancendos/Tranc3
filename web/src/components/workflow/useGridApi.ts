/**
 * The Digital Grid — REST API hook
 * Zero-cost: talks to the self-hosted grid worker at /grid/*
 */
import { useCallback, useState } from "react";
import type { WorkflowDef, ExecutionStatus } from "./types";

const GRID_BASE = "/grid";

export function useGridApi() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const request = useCallback(
    async <T>(path: string, options?: RequestInit): Promise<T | null> => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`${GRID_BASE}${path}`, {
          headers: { "Content-Type": "application/json" },
          ...options,
        });
        if (!res.ok) {
          const body = await res.text();
          throw new Error(`${res.status}: ${body}`);
        }
        return (await res.json()) as T;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Unknown error");
        return null;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const listWorkflows = useCallback(
    () => request<WorkflowDef[]>("/workflows"),
    [request]
  );

  const getWorkflow = useCallback(
    (id: string) => request<WorkflowDef>(`/workflows/${id}`),
    [request]
  );

  const saveWorkflow = useCallback(
    (wf: WorkflowDef) =>
      request<{ id: string }>("/workflows", {
        method: "POST",
        body: JSON.stringify(wf),
      }),
    [request]
  );

  const runWorkflow = useCallback(
    (id: string, inputs: Record<string, unknown> = {}) =>
      request<ExecutionStatus>(`/workflows/${id}/run`, {
        method: "POST",
        body: JSON.stringify({ inputs }),
      }),
    [request]
  );

  const getExecution = useCallback(
    (id: string) => request<ExecutionStatus>(`/executions/${id}`),
    [request]
  );

  const cancelExecution = useCallback(
    (id: string) =>
      request<{ cancelled: boolean }>(`/executions/${id}/cancel`, {
        method: "POST",
      }),
    [request]
  );

  const gridStatus = useCallback(
    () =>
      request<{
        registered_workflows: number;
        active_executions: number;
        node_types: string[];
      }>("/status"),
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
