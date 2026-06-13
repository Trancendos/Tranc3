import React, { useEffect, useState } from "react";
import type { ExecutionStatus } from "./types";
import { useGridApi } from "./useGridApi";

interface Props {
  executionId: string | null;
  onClose: () => void;
}

const STATUS_COLOR: Record<string, string> = {
  pending: "text-yellow-400",
  running: "text-blue-400",
  completed: "text-green-400",
  failed: "text-red-400",
  cancelled: "text-gray-400",
};

export default function ExecutionPanel({ executionId, onClose }: Props) {
  const { getExecution, cancelExecution } = useGridApi();
  const [status, setStatus] = useState<ExecutionStatus | null>(null);
  const [polling, setPolling] = useState(false);

  useEffect(() => {
    if (!executionId) {
      setStatus(null);
      return;
    }

    let cancelled = false;

    async function poll() {
      setPolling(true);
      while (!cancelled) {
        const s = await getExecution(executionId!);
        if (cancelled) break;
        if (s) setStatus(s);
        if (s && (s.status === "completed" || s.status === "failed" || s.status === "cancelled")) {
          break;
        }
        await new Promise((r) => setTimeout(r, 1500));
      }
      setPolling(false);
    }

    poll();
    return () => { cancelled = true; };
  }, [executionId, getExecution]);

  if (!executionId) return null;

  return (
    <div className="w-72 bg-gray-900 border-l border-gray-700 flex flex-col flex-shrink-0">
      <div className="p-3 border-b border-gray-700 flex items-center justify-between">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Execution</p>
        <button onClick={onClose} className="text-gray-500 hover:text-gray-300 text-xs">✕</button>
      </div>

      {!status ? (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-gray-500 text-xs">Loading…</p>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-3 space-y-3">
          {/* Overall status */}
          <div className="bg-gray-800 rounded p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-gray-400">Status</span>
              <span className={`text-xs font-semibold ${STATUS_COLOR[status.status] ?? "text-gray-300"}`}>
                {status.status.toUpperCase()}
                {polling && status.status === "running" && " ●"}
              </span>
            </div>
            <p className="text-xs text-gray-500 font-mono break-all">{status.id}</p>
          </div>

          {/* Node statuses */}
          {status.node_statuses && Object.keys(status.node_statuses).length > 0 && (
            <div>
              <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Nodes</p>
              <div className="space-y-1">
                {Object.entries(status.node_statuses).map(([nodeId, ns]) => (
                  <div key={nodeId} className="flex items-center justify-between bg-gray-800 rounded px-2 py-1.5">
                    <span className="text-xs text-gray-400 truncate max-w-[120px]">{nodeId}</span>
                    <span className={`text-xs font-medium ${STATUS_COLOR[ns as string] ?? "text-gray-300"}`}>
                      {String(ns)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Outputs */}
          {status.outputs && Object.keys(status.outputs).length > 0 && (
            <div>
              <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Outputs</p>
              <pre className="text-xs text-gray-300 bg-gray-800 rounded p-2 overflow-auto max-h-48 whitespace-pre-wrap">
                {JSON.stringify(status.outputs, null, 2)}
              </pre>
            </div>
          )}

          {/* Error */}
          {status.error && (
            <div className="bg-red-900/30 border border-red-800 rounded p-2">
              <p className="text-xs text-red-400 font-medium mb-1">Error</p>
              <p className="text-xs text-red-300">{status.error}</p>
            </div>
          )}

          {/* Cancel */}
          {(status.status === "running" || status.status === "pending") && (
            <button
              onClick={() => cancelExecution(status.id)}
              className="w-full py-1.5 text-xs font-medium bg-red-900/50 hover:bg-red-900 text-red-300 rounded transition-colors"
            >
              Cancel Execution
            </button>
          )}
        </div>
      )}
    </div>
  );
}
