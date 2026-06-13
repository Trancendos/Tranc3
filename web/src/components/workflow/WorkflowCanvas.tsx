import React, { useRef, useState, useCallback, useEffect } from "react";
import type { GridNode, GridEdge, NodeType } from "./types";
import { NODE_META } from "./types";

interface Props {
  nodes: GridNode[];
  edges: GridEdge[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onNodesChange: (nodes: GridNode[]) => void;
  onEdgesChange: (edges: GridEdge[]) => void;
  onDrop: (type: NodeType, x: number, y: number) => void;
  dragNodeType: NodeType | null;
}

interface DragState {
  nodeId: string;
  startX: number;
  startY: number;
  originX: number;
  originY: number;
}

interface ConnectState {
  sourceId: string;
  sourcePort: string;
  cursorX: number;
  cursorY: number;
}

const PORT_RADIUS = 6;
const NODE_W = 160;
const NODE_H = 56;

function portPos(node: GridNode, port: "in" | "out") {
  return port === "out"
    ? { x: node.x + NODE_W, y: node.y + NODE_H / 2 }
    : { x: node.x, y: node.y + NODE_H / 2 };
}

function bezier(x1: number, y1: number, x2: number, y2: number) {
  const cx = (x1 + x2) / 2;
  return `M ${x1} ${y1} C ${cx} ${y1}, ${cx} ${y2}, ${x2} ${y2}`;
}

export default function WorkflowCanvas({
  nodes,
  edges,
  selectedId,
  onSelect,
  onNodesChange,
  onEdgesChange,
  onDrop,
  dragNodeType,
}: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [drag, setDrag] = useState<DragState | null>(null);
  const [connect, setConnect] = useState<ConnectState | null>(null);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [panDrag, setPanDrag] = useState<{ startX: number; startY: number; originX: number; originY: number } | null>(null);

  const svgPoint = useCallback((e: React.MouseEvent | MouseEvent) => {
    const svg = svgRef.current;
    if (!svg) return { x: 0, y: 0 };
    const rect = svg.getBoundingClientRect();
    return {
      x: e.clientX - rect.left - pan.x,
      y: e.clientY - rect.top - pan.y,
    };
  }, [pan]);

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (drag) {
      const svg = svgRef.current;
      if (!svg) return;
      const rect = svg.getBoundingClientRect();
      const dx = e.clientX - rect.left - pan.x - drag.startX;
      const dy = e.clientY - rect.top - pan.y - drag.startY;
      onNodesChange(
        nodes.map((n) =>
          n.id === drag.nodeId
            ? { ...n, x: drag.originX + dx, y: drag.originY + dy }
            : n
        )
      );
    }
    if (connect) {
      const svg = svgRef.current;
      if (!svg) return;
      const rect = svg.getBoundingClientRect();
      setConnect((c) => c ? { ...c, cursorX: e.clientX - rect.left - pan.x, cursorY: e.clientY - rect.top - pan.y } : null);
    }
    if (panDrag) {
      const dx = e.clientX - panDrag.startX;
      const dy = e.clientY - panDrag.startY;
      setPan({ x: panDrag.originX + dx, y: panDrag.originY + dy });
    }
  }, [drag, connect, panDrag, nodes, onNodesChange, pan]);

  const handleMouseUp = useCallback(() => {
    setDrag(null);
    setConnect(null);
    setPanDrag(null);
  }, []);

  useEffect(() => {
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [handleMouseMove, handleMouseUp]);

  const startDrag = useCallback((e: React.MouseEvent, nodeId: string) => {
    e.stopPropagation();
    const pt = svgPoint(e);
    const node = nodes.find((n) => n.id === nodeId)!;
    setDrag({ nodeId, startX: pt.x, startY: pt.y, originX: node.x, originY: node.y });
    onSelect(nodeId);
  }, [nodes, svgPoint, onSelect]);

  const startConnect = useCallback((e: React.MouseEvent, nodeId: string) => {
    e.stopPropagation();
    const node = nodes.find((n) => n.id === nodeId)!;
    const out = portPos(node, "out");
    setConnect({ sourceId: nodeId, sourcePort: "out", cursorX: out.x, cursorY: out.y });
  }, [nodes]);

  const finishConnect = useCallback((e: React.MouseEvent, targetId: string) => {
    e.stopPropagation();
    if (!connect || connect.sourceId === targetId) return;
    const exists = edges.find(
      (ed) => ed.sourceId === connect.sourceId && ed.targetId === targetId
    );
    if (!exists) {
      onEdgesChange([
        ...edges,
        { id: `e-${Date.now()}`, sourceId: connect.sourceId, targetId },
      ]);
    }
    setConnect(null);
  }, [connect, edges, onEdgesChange]);

  const deleteEdge = useCallback((edgeId: string) => {
    onEdgesChange(edges.filter((e) => e.id !== edgeId));
  }, [edges, onEdgesChange]);

  const handleCanvasDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    if (!dragNodeType) return;
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const x = e.clientX - rect.left - pan.x;
    const y = e.clientY - rect.top - pan.y;
    onDrop(dragNodeType, x - NODE_W / 2, y - NODE_H / 2);
  }, [dragNodeType, pan, onDrop]);

  const handleCanvasMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button === 1 || (e.button === 0 && e.altKey)) {
      e.preventDefault();
      setPanDrag({ startX: e.clientX, startY: e.clientY, originX: pan.x, originY: pan.y });
    } else {
      onSelect(null);
      setConnect(null);
    }
  }, [pan, onSelect]);

  return (
    <div
      className="flex-1 relative overflow-hidden bg-gray-950"
      onDragOver={(e) => e.preventDefault()}
      onDrop={handleCanvasDrop}
    >
      {/* Grid dots */}
      <svg
        ref={svgRef}
        className="absolute inset-0 w-full h-full cursor-default"
        onMouseDown={handleCanvasMouseDown}
      >
        <defs>
          <pattern id="grid-dots" x={pan.x % 24} y={pan.y % 24} width="24" height="24" patternUnits="userSpaceOnUse">
            <circle cx="1" cy="1" r="1" fill="#374151" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#grid-dots)" />

        <g transform={`translate(${pan.x},${pan.y})`}>
          {/* Edges */}
          {edges.map((edge) => {
            const src = nodes.find((n) => n.id === edge.sourceId);
            const tgt = nodes.find((n) => n.id === edge.targetId);
            if (!src || !tgt) return null;
            const s = portPos(src, "out");
            const t = portPos(tgt, "in");
            return (
              <g key={edge.id}>
                <path
                  d={bezier(s.x, s.y, t.x, t.y)}
                  fill="none"
                  stroke="#6366f1"
                  strokeWidth={2}
                  strokeLinecap="round"
                  opacity={0.8}
                />
                {/* invisible wider hit area */}
                <path
                  d={bezier(s.x, s.y, t.x, t.y)}
                  fill="none"
                  stroke="transparent"
                  strokeWidth={12}
                  className="cursor-pointer"
                  onClick={() => deleteEdge(edge.id)}
                />
              </g>
            );
          })}

          {/* Live connection line */}
          {connect && (() => {
            const src = nodes.find((n) => n.id === connect.sourceId);
            if (!src) return null;
            const s = portPos(src, "out");
            return (
              <path
                d={bezier(s.x, s.y, connect.cursorX, connect.cursorY)}
                fill="none"
                stroke="#a78bfa"
                strokeWidth={2}
                strokeDasharray="6 3"
                strokeLinecap="round"
              />
            );
          })()}

          {/* Nodes */}
          {nodes.map((node) => {
            const meta = NODE_META[node.type];
            const selected = node.id === selectedId;
            const inPt = portPos(node, "in");
            const outPt = portPos(node, "out");

            return (
              <g key={node.id}>
                {/* Node card */}
                <rect
                  x={node.x}
                  y={node.y}
                  width={NODE_W}
                  height={NODE_H}
                  rx={8}
                  fill="#1f2937"
                  stroke={selected ? meta.color : "#374151"}
                  strokeWidth={selected ? 2 : 1}
                  className="cursor-move"
                  onMouseDown={(e) => startDrag(e, node.id)}
                />
                {/* Color accent bar */}
                <rect
                  x={node.x}
                  y={node.y}
                  width={4}
                  height={NODE_H}
                  rx={4}
                  fill={meta.color}
                  style={{ pointerEvents: "none" }}
                />
                {/* Icon */}
                <text
                  x={node.x + 20}
                  y={node.y + NODE_H / 2 + 5}
                  fontSize={14}
                  textAnchor="middle"
                  style={{ pointerEvents: "none", userSelect: "none" }}
                >
                  {meta.icon}
                </text>
                {/* Label */}
                <text
                  x={node.x + 36}
                  y={node.y + NODE_H / 2 - 4}
                  fontSize={11}
                  fontWeight={600}
                  fill="#e5e7eb"
                  style={{ pointerEvents: "none", userSelect: "none" }}
                >
                  {node.label.length > 16 ? node.label.slice(0, 15) + "…" : node.label}
                </text>
                <text
                  x={node.x + 36}
                  y={node.y + NODE_H / 2 + 10}
                  fontSize={9}
                  fill="#6b7280"
                  style={{ pointerEvents: "none", userSelect: "none" }}
                >
                  {meta.label}
                </text>

                {/* Input port */}
                {node.type !== "trigger" && (
                  <circle
                    cx={inPt.x}
                    cy={inPt.y}
                    r={PORT_RADIUS}
                    fill="#111827"
                    stroke="#4b5563"
                    strokeWidth={2}
                    className="cursor-crosshair"
                    onMouseUp={(e) => finishConnect(e, node.id)}
                  />
                )}

                {/* Output port */}
                <circle
                  cx={outPt.x}
                  cy={outPt.y}
                  r={PORT_RADIUS}
                  fill="#111827"
                  stroke={meta.color}
                  strokeWidth={2}
                  className="cursor-crosshair"
                  onMouseDown={(e) => startConnect(e, node.id)}
                />
              </g>
            );
          })}
        </g>
      </svg>

      {/* Empty state hint */}
      {nodes.length === 0 && (
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          <p className="text-gray-600 text-sm">Drag nodes from the palette to build a workflow</p>
          <p className="text-gray-700 text-xs mt-1">Alt + drag to pan · Click edge to delete · Drag output port to connect</p>
        </div>
      )}
    </div>
  );
}
