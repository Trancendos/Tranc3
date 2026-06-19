import React, { useState, useCallback } from "react";
import type { GridNode, GridEdge, WorkflowDef, NodeType } from "./types";
import { NODE_META } from "./types";
import NodePalette from "./NodePalette";
import WorkflowCanvas from "./WorkflowCanvas";
import ExecutionPanel from "./ExecutionPanel";
import WorkflowDashboard from "./WorkflowDashboard";
import { useGridApi } from "./useGridApi";

type View = "dashboard" | "editor";

function makeId() {
  return Math.random().toString(36).slice(2, 9);
}

function emptyWorkflow(): WorkflowDef {
  return { name: "Untitled Workflow", description: "", nodes: [], edges: [], created_at: new Date().toISOString() };
}

export default function DigitalGridPage() {
  const { saveWorkflow, runWorkflow } = useGridApi();

  const [view, setView] = useState<View>("dashboard");
  const [workflow, setWorkflow] = useState<WorkflowDef>(emptyWorkflow());
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [executionId, setExecutionId] = useState<string | null>(null);
  const [dragNodeType, setDragNodeType] = useState<NodeType | null>(null);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [nameEdit, setNameEdit] = useState(false);

  const openEditor = useCallback((wf: WorkflowDef) => {
    setWorkflow(wf);
    setView("editor");
    setSelectedId(null);
    setExecutionId(null);
  }, []);

  const handleDrop = useCallback((type: NodeType, x: number, y: number) => {
    const meta = NODE_META[type];
    const node: GridNode = {
      id: `node-${makeId()}`,
      type,
      label: meta.label,
      config: {},
      x,
      y,
    };
    setWorkflow((wf) => ({ ...wf, nodes: [...wf.nodes, node] }));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    const result = await saveWorkflow(workflow);
    if (result?.id && !workflow.id) {
      setWorkflow((wf) => ({ ...wf, id: result.id }));
    }
    setSaving(false);
  };

  const handleRun = async () => {
    if (!workflow.id) {
      // Save first
      setSaving(true);
      const result = await saveWorkflow(workflow);
      if (result?.id) {
        const id = result.id;
        setWorkflow((wf) => ({ ...wf, id }));
        setSaving(false);
        setRunning(true);
        const exec = await runWorkflow(id);
        if (exec) setExecutionId(exec.id);
        setRunning(false);
      } else {
        setSaving(false);
      }
    } else {
      setRunning(true);
      const exec = await runWorkflow(workflow.id);
      if (exec) setExecutionId(exec.id);
      setRunning(false);
    }
  };

  const selectedNode = workflow.nodes.find((n) => n.id === selectedId) ?? null;

  return (
    <div className="h-full flex flex-col bg-gray-950">
      {view === "dashboard" ? (
        <WorkflowDashboard
          onOpen={openEditor}
          onCreate={() => { setWorkflow(emptyWorkflow()); setView("editor"); }}
        />
      ) : (
        <>
          {/* Toolbar */}
          <div className="flex items-center gap-3 px-4 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0">
            <button
              onClick={() => setView("dashboard")}
              className="text-gray-400 hover:text-gray-200 text-sm transition-colors"
            >
              ← Workflows
            </button>

            <div className="w-px h-4 bg-gray-700" />

            {nameEdit ? (
              <input
                autoFocus
                className="bg-gray-800 text-white text-sm font-semibold px-2 py-0.5 rounded border border-indigo-500 outline-none w-48"
                value={workflow.name}
                onChange={(e) => setWorkflow((wf) => ({ ...wf, name: e.target.value }))}
                onBlur={() => setNameEdit(false)}
                onKeyDown={(e) => { if (e.key === "Enter") setNameEdit(false); }}
              />
            ) : (
              <button
                className="text-sm font-semibold text-white hover:text-indigo-300 transition-colors"
                onClick={() => setNameEdit(true)}
              >
                {workflow.name}
              </button>
            )}

            <span className="text-gray-600 text-xs">
              {workflow.nodes.length} node{workflow.nodes.length !== 1 ? "s" : ""} · {workflow.edges.length} edge{workflow.edges.length !== 1 ? "s" : ""}
            </span>

            <div className="flex-1" />

            <button
              onClick={handleSave}
              disabled={saving}
              className="px-3 py-1.5 text-xs font-medium bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-gray-200 rounded-lg transition-colors"
            >
              {saving ? "Saving…" : "Save"}
            </button>

            <button
              onClick={handleRun}
              disabled={running || saving}
              className="px-3 py-1.5 text-xs font-medium bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg transition-colors flex items-center gap-1.5"
            >
              {running ? "Running…" : "▶ Run"}
            </button>
          </div>

          {/* Editor area */}
          <div className="flex-1 flex overflow-hidden">
            <NodePalette onDragStart={setDragNodeType} />

            <WorkflowCanvas
              nodes={workflow.nodes}
              edges={workflow.edges}
              selectedId={selectedId}
              onSelect={setSelectedId}
              onNodesChange={(nodes) => setWorkflow((wf) => ({ ...wf, nodes }))}
              onEdgesChange={(edges) => setWorkflow((wf) => ({ ...wf, edges }))}
              onDrop={handleDrop}
              dragNodeType={dragNodeType}
            />

            {/* Node config panel */}
            {selectedNode && (
              <div className="w-64 bg-gray-900 border-l border-gray-700 flex-shrink-0 p-3 overflow-y-auto">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Properties</p>
                  <button onClick={() => setSelectedId(null)} aria-label="Close properties panel" className="text-gray-500 hover:text-gray-300 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 rounded px-1">✕</button>
                </div>
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Label</label>
                    <input
                      className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-white outline-none focus:border-indigo-500"
                      value={selectedNode.label}
                      onChange={(e) => setWorkflow((wf) => ({
                        ...wf,
                        nodes: wf.nodes.map((n) => n.id === selectedNode.id ? { ...n, label: e.target.value } : n),
                      }))}
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Type</label>
                    <p className="text-xs text-gray-300">{NODE_META[selectedNode.type].label}</p>
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Description</label>
                    <p className="text-xs text-gray-500">{NODE_META[selectedNode.type].description}</p>
                  </div>
                  <div className="pt-1">
                    <button
                      onClick={() => {
                        setWorkflow((wf) => ({
                          ...wf,
                          nodes: wf.nodes.filter((n) => n.id !== selectedNode.id),
                          edges: wf.edges.filter((e) => e.sourceId !== selectedNode.id && e.targetId !== selectedNode.id),
                        }));
                        setSelectedId(null);
                      }}
                      className="w-full py-1.5 text-xs text-red-400 hover:text-red-300 border border-red-900/50 hover:border-red-800 rounded transition-colors"
                    >
                      Delete Node
                    </button>
                  </div>
                </div>
              </div>
            )}

            <ExecutionPanel
              executionId={executionId}
              onClose={() => setExecutionId(null)}
            />
          </div>
        </>
      )}
    </div>
  );
}
