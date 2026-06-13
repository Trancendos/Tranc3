import React, { useEffect, useState } from "react";
import type { WorkflowDef } from "./types";
import { useGridApi } from "./useGridApi";

interface Props {
  onOpen: (wf: WorkflowDef) => void;
  onCreate: () => void;
}

export default function WorkflowDashboard({ onOpen, onCreate }: Props) {
  const { listWorkflows, runWorkflow, loading, error } = useGridApi();
  const [workflows, setWorkflows] = useState<WorkflowDef[]>([]);
  const [runningId, setRunningId] = useState<string | null>(null);

  useEffect(() => {
    listWorkflows().then((wfs) => {
      if (wfs) setWorkflows(wfs);
    });
  }, [listWorkflows]);

  const handleRun = async (wf: WorkflowDef) => {
    if (!wf.id) return;
    setRunningId(wf.id);
    await runWorkflow(wf.id);
    setRunningId(null);
  };

  return (
    <div className="flex-1 p-6 overflow-y-auto">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-xl font-bold text-white">The Digital Grid</h2>
            <p className="text-gray-400 text-sm mt-0.5">Workflow orchestration — DAG builder & executor</p>
          </div>
          <button
            onClick={onCreate}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg transition-colors"
          >
            + New Workflow
          </button>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-900/30 border border-red-800 rounded-lg text-red-300 text-sm">
            {error}
          </div>
        )}

        {loading ? (
          <div className="text-center py-12 text-gray-500">Loading workflows…</div>
        ) : workflows.length === 0 ? (
          <div className="text-center py-16">
            <div className="text-4xl mb-3">⚡</div>
            <p className="text-gray-400 font-medium">No workflows yet</p>
            <p className="text-gray-600 text-sm mt-1 mb-4">Create your first workflow to connect AI nodes into intelligent pipelines.</p>
            <button
              onClick={onCreate}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg transition-colors"
            >
              Create Workflow
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {workflows.map((wf) => (
              <div
                key={wf.id}
                className="bg-gray-800 border border-gray-700 rounded-xl p-4 hover:border-indigo-600/50 transition-colors"
              >
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div className="min-w-0">
                    <h3 className="font-semibold text-white truncate">{wf.name}</h3>
                    {wf.description && (
                      <p className="text-gray-400 text-xs mt-0.5 line-clamp-2">{wf.description}</p>
                    )}
                  </div>
                  <span className="flex-shrink-0 text-xs px-2 py-0.5 rounded-full bg-gray-700 text-gray-400">
                    {wf.nodes.length} node{wf.nodes.length !== 1 ? "s" : ""}
                  </span>
                </div>

                <div className="flex gap-2 mt-3">
                  <button
                    onClick={() => onOpen(wf)}
                    className="flex-1 py-1.5 text-xs font-medium bg-gray-700 hover:bg-gray-600 text-gray-200 rounded-lg transition-colors"
                  >
                    Open Editor
                  </button>
                  <button
                    onClick={() => handleRun(wf)}
                    disabled={runningId === wf.id}
                    className="flex-1 py-1.5 text-xs font-medium bg-indigo-700 hover:bg-indigo-600 disabled:opacity-50 text-white rounded-lg transition-colors"
                  >
                    {runningId === wf.id ? "Running…" : "▶ Run"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
